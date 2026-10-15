"""Shared utilities for enhanced crawler modules (Issue #309).

Provides browser initialization, config loading, selector resolution, and logging setup.
Used by crawl_list.py and crawl_details.py for independent crawler operation.
"""

import asyncio
import json
import logging
import logging.handlers
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast

from playwright.async_api import Browser, Playwright, async_playwright


# ============================================================================
# ASYNCIO CLEANUP HANDLER (Issue #309)
# ============================================================================
def _suppress_event_loop_closed_exception() -> None:
    """
    Suppress RuntimeError: Event loop is closed from subprocess cleanup.

    Root cause: Playwright subprocess cleanup happens during GC after event loop closes.
    This is a known issue with Playwright's asyncio integration. We suppress the exception
    since it's harmless (cleanup already happened, just lingering reference cleanup).

    Called via import to catch lingering subprocess exceptions during Python shutdown.
    """
    import sys

    old_excepthook = sys.excepthook

    def new_excepthook(exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if isinstance(exc_val, RuntimeError) and "Event loop is closed" in str(exc_val):
            # Suppress this specific exception; it's from subprocess cleanup
            pass
        else:
            old_excepthook(exc_type, exc_val, exc_tb)

    sys.excepthook = new_excepthook


# Register handler on module import
_suppress_event_loop_closed_exception()


# ============================================================================
# GENERIC FALLBACK SELECTORS
# ============================================================================
GENERIC_FALLBACK_SELECTORS = {
    "job_container": "[class*='job'], [class*='posting'], tr",
    "title": "h1, h2, h3, p.title, .job-title, [class*='title']",
    "location": "p, span, [class*='location'], [class*='place']",
    "link": "a[href]",
    "description_selector": "[class*='description'], [class*='details'], main, article, section",
}


# ============================================================================
# BROWSER INITIALIZATION
# ============================================================================


async def init_browser(headless: bool = True) -> Tuple[Playwright, Browser]:
    """
    Initialize and launch a Playwright Chromium browser.

    Returns both Playwright and Browser instances to ensure proper cleanup.
    Losing the Playwright reference causes subprocess to linger after event loop closes.

    Args:
        headless: If True, run browser in headless mode (default: True)

    Returns:
        Tuple of (Playwright instance, Browser instance)

    Raises:
        RuntimeError: If browser initialization fails (system/browser error)
    """
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=headless)
        return playwright, browser
    except Exception as e:
        raise RuntimeError(f"Failed to initialize browser: {e}") from e


async def close_browser(
    playwright: Optional[Playwright],
    browser: Optional[Browser],
) -> None:
    """
    Close a Playwright browser instance and stop the Playwright driver.

    Explicitly calls await playwright.stop() to clean up subprocess before event loop closes.
    This prevents RuntimeError: Event loop is closed during GC.

    Args:
        playwright: Playwright instance (from init_browser)
        browser: Browser instance (from init_browser)
    """
    if browser:
        try:
            await browser.close()
        except Exception as e:
            logging.warning(f"Error closing browser: {e}")

    if playwright:
        try:
            await playwright.stop()
        except Exception as e:
            logging.warning(f"Error stopping playwright: {e}")


# ============================================================================
# PAGE NAVIGATION WITH RETRY
# ============================================================================


async def retry_goto(
    page: Any,
    url: str,
    max_attempts: int = 3,
    timeout_ms: int = 30000,
    logger: Optional[logging.Logger] = None,
) -> bool:
    """
    Navigate to URL with exponential backoff retry logic.

    Attempts navigation up to max_attempts times with backoff: 2s, 4s, 8s, etc.

    Args:
        page: Playwright page instance
        url: URL to navigate to
        max_attempts: Maximum number of retry attempts (default: 3)
        timeout_ms: Page navigation timeout in milliseconds (default: 30000)
        logger: Optional logger instance for debug output

    Returns:
        True if navigation succeeded, False otherwise

    Side Effects:
        Updates page timeout and navigates to URL on success.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    page.set_default_timeout(timeout_ms)

    for attempt in range(1, max_attempts + 1):
        try:
            logger.debug(f"Navigation attempt {attempt}/{max_attempts} to {url}")
            await page.goto(url, wait_until="load")
            logger.debug(f"Successfully navigated to {url}")
            return True
        except Exception as e:
            if attempt < max_attempts:
                backoff_sec = 2 ** (attempt - 1)  # 2s, 4s, 8s, ...
                logger.debug(f"Navigation attempt {attempt} failed: {e}. Retrying in {backoff_sec}s...")
                await asyncio.sleep(backoff_sec)
            else:
                logger.warning(f"Navigation failed after {max_attempts} attempts: {e}")
                return False

    return False


# ============================================================================
# CONFIG LOADING & MERGING
# ============================================================================


def load_all_company_configs(config_dir: str = "config_test") -> Dict[str, Any]:
    """
    Load and merge all company configs from all JSON files in config_dir.

    Reads all *.json files from config_dir, extracts "companies" key from each,
    and merges into a single dict. Later files override earlier ones for conflicting keys.

    Args:
        config_dir: Directory containing config JSON files (default: "config_test")

    Returns:
        Merged dict of {company_key: company_config} from all files

    Raises:
        FileNotFoundError: If config_dir does not exist
        ValueError: If no JSON files found or parsing fails
    """
    config_path = Path(config_dir)
    if not config_path.exists():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    json_files = sorted(config_path.glob("*.json"))
    if not json_files:
        raise ValueError(f"No JSON files found in {config_dir}")

    merged_companies: Dict[str, Any] = {}

    for json_file in json_files:
        try:
            # utf-8-sig tolerates a leading BOM (common from Windows editors)
            with open(json_file, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
                companies = config.get("companies", {})
                merged_companies.update(companies)
                logging.debug(f"Loaded {len(companies)} companies from {json_file.name}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {json_file.name}: {e}") from e

    logging.info(f"Merged {len(merged_companies)} companies from {len(json_files)} config files")
    return merged_companies


# ============================================================================
# SELECTOR RESOLUTION
# ============================================================================


def resolve_company_selectors(job_company_name: str, merged_config: Dict[str, Any]) -> Dict[str, str]:
    """
    Resolve CSS selectors for a company, matching on both key and name field.

    Matches company_name case-insensitively against:
    1. Dict keys in merged_config (e.g., "CarbonRobotics")
    2. "name" field in company config (e.g., "Carbon Robotics")

    Handles key/name mismatches (e.g., "CarbonRobotics" key vs "Carbon Robotics" name).
    Returns selectors from matched config, or empty dict if not found.

    Args:
        job_company_name: Company name from job listing (e.g., "Carbon Robotics", "CarbonRobotics")
        merged_config: Merged company configurations dict

    Returns:
        Dict of selectors for the company (defaults to GENERIC_FALLBACK_SELECTORS if not found)
    """
    job_name_lower = job_company_name.strip().lower()

    # Try matching against keys
    for key, config in merged_config.items():
        if not isinstance(config, dict):
            continue
        if key.lower() == job_name_lower:
            selectors = config.get("selectors")
            if selectors and isinstance(selectors, dict):
                return cast(Dict[str, str], selectors)

    # Try matching against "name" field
    for _key, config in merged_config.items():
        if not isinstance(config, dict):
            continue
        name = config.get("name")
        if not isinstance(name, str):
            continue
        config_name = name.lower()
        if config_name == job_name_lower:
            selectors = config.get("selectors")
            if selectors and isinstance(selectors, dict):
                return cast(Dict[str, str], selectors)

    # No match found, return empty dict (caller will use fallbacks)
    logging.debug(f"No selector config found for company '{job_company_name}', using fallbacks")
    return {}


# ============================================================================
# LOGGING SETUP
# ============================================================================


def setup_logging(
    name: str,
    level: str = "INFO",
    log_file: str = "logs/crawl_modules.log",
) -> logging.Logger:
    """
    Set up logging with both console and file handlers.

    Creates logger with given name, adds console and file handlers.
    Creates logs directory if it doesn't exist.

    Args:
        name: Logger name (typically __name__)
        level: Logging level as string (default: "INFO")
        log_file: Path to log file (default: "logs/crawl_modules.log")

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Create logs directory if needed
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_format = logging.Formatter(
        "[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)

    # File handler (rotating, max 10MB per file, 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    file_format = logging.Formatter(
        "[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)

    # Add handlers to logger (avoid duplicates)
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger
