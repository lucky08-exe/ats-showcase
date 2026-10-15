#!/usr/bin/env python3
"""Crawler module to extract job listings from company career pages (Issue #309, #315).

Crawls job listing pages, extracts job titles/locations/links, generates unique job IDs,
and outputs per-company JSON files with full 9-field schema (id, title, company, location,
url, description, requirements, salary_min, salary_max, posted_date, crawled_at, status)
per Issue #309 spec for compatibility with loader.py.

Usage:
    python -m src.poc.tweak.crawl_list \\
        --config-dir config_test \\
        --output-dir data/work \\
        --company CarbonRobotics \\
        --headless
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.async_api import Browser, Page, Playwright

from src.id_generation.hash_generator import generate_job_id
from src.poc.tweak.common import (
    GENERIC_FALLBACK_SELECTORS,
    close_browser,
    init_browser,
    load_all_company_configs,
    retry_goto,
    setup_logging,
)

logger = logging.getLogger(__name__)


# ============================================================================
# JOB EXTRACTION
# ============================================================================


def extract_url_param(url: str, param_name: str) -> Optional[str]:
    """Extract a URL query parameter value.

    Args:
        url: Full URL with query parameters
        param_name: Parameter name to extract (e.g., 'jobId')

    Returns:
        Parameter value if found, None otherwise
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        # parse_qs returns lists of values, so we take the first
        return params.get(param_name, [None])[0]
    except Exception as e:
        logger.debug(f"Error extracting URL parameter '{param_name}' from '{url}': {e}")
        return None


async def extract_text(element: Any, selector: Optional[str]) -> Optional[str]:
    """Extract text from element using selector. Pierces shadow DOM if needed."""
    if not selector:
        return None
    try:
        # Try direct querySelector first
        sub_element = await element.query_selector(selector)
        if sub_element:
            text = await sub_element.text_content()
            return text.strip() if text else None

        # If not found, try piercing shadow DOM with evaluate()
        text = await element.evaluate(
            """(el, sel) => {
                const root = el.shadowRoot;
                if (!root) return null;
                const target = root.querySelector(sel);
                return target ? target.textContent.trim() : null;
            }""",
            selector,
        )
        return text if text else None
    except Exception as e:
        logger.debug(f"Error extracting text with selector '{selector}': {e}")
    return None


async def extract_link(element: Any, selector: Optional[str]) -> Optional[str]:
    """Extract href from element using selector. Pierces shadow DOM if needed."""
    if not selector:
        return None
    try:
        # Try direct querySelector first
        sub_element = await element.query_selector(selector)
        if sub_element:
            href = await sub_element.get_attribute("href")
            return cast(Optional[str], href)

        # If not found, try piercing shadow DOM with evaluate()
        href = await element.evaluate(
            """(el, sel) => {
                const root = el.shadowRoot;
                if (!root) return null;
                const target = root.querySelector(sel);
                return target ? target.getAttribute('href') : null;
            }""",
            selector,
        )
        return cast(Optional[str], href) if href else None
    except Exception as e:
        logger.debug(f"Error extracting link with selector '{selector}': {e}")
    return None


def parse_posted_date(text: Optional[str], reference: datetime) -> Optional[str]:
    """
    Parse Workday-style relative dates into ISO YYYY-MM-DD format.

    Args:
        text: Raw text like "Posted 8 Days Ago", "Posted Today", etc.
        reference: Reference datetime to calculate relative dates from.

    Returns:
        ISO YYYY-MM-DD string, or None if unparseable or input is None.

    Examples:
        parse_posted_date("Posted 8 Days Ago", datetime(2026, 9, 8, 10, 30)) -> "2026-08-31"
        parse_posted_date("Posted Today", datetime(2026, 9, 8, 10, 30)) -> "2026-09-08"
        parse_posted_date("Posted Yesterday", datetime(2026, 9, 8, 10, 30)) -> "2026-09-07"
        parse_posted_date("Posted 30+ Days Ago", datetime(2026, 9, 8, 10, 30)) -> "2026-08-09"
    """
    if not text:
        return None

    try:
        text_lower = text.strip().lower()

        # Handle "Posted Today"
        if "posted" in text_lower and "today" in text_lower:
            return reference.date().isoformat()

        # Handle "Posted Yesterday"
        if "posted" in text_lower and "yesterday" in text_lower:
            return (reference.date() - timedelta(days=1)).isoformat()

        # Handle "Posted N Days Ago" and "Posted 30+ Days Ago"
        match = re.search(r"posted\s+(\d+)\+?\s+days?\s+ago", text_lower)
        if match:
            days_ago = int(match.group(1))
            return (reference.date() - timedelta(days=days_ago)).isoformat()

        return None
    except Exception as e:
        logger.debug(f"Error parsing posted date '{text}': {e}")
        return None


def parse_field(text: Optional[str], label: str, next_field: Optional[str] = None) -> Optional[str]:
    """
    Extract a field value from text after a label.

    Finds the label in text, extracts content after it, and optionally stops
    at the next field. Used for parsing Workday-style job detail pages.

    Args:
        text: Full text containing the label and value
        label: Label to search for (e.g., "Job types:")
        next_field: Optional next field label to stop at (e.g., "Location type:")

    Returns:
        Extracted field value (stripped and limited to 100 chars), or None if label not found

    Examples:
        text = "Job types: Contract\nLocation type: Hybrid\nSkills: Python"
        parse_field(text, "Job types:", "Location type:") -> "Contract"
        parse_field(text, "Location type:", "Skills:") -> "Hybrid"
    """
    if not text or not label:
        return None

    try:
        if label not in text:
            return None

        # Find start position after label
        start = text.index(label) + len(label)

        # If next_field is provided, find end position
        if next_field and next_field in text[start:]:
            end = text.index(next_field, start)
            value = text[start:end].strip()
        else:
            # Extract rest of text after label
            value = text[start:].strip()

        # Limit length to 100 chars to prevent excess tokens
        return value[:100] if value else None
    except Exception as e:
        logger.debug(f"Error parsing field '{label}' from text: {e}")
        return None


async def extract_detail_page_fields(
    page: Page,
    detail_url: str,
    selectors: Dict[str, str],
) -> Dict[str, Optional[str]]:
    """
    Fetch detail page via jobId URL and extract additional fields.

    Navigates to detail page, extracts description, job_id, job_type,
    location_type, and compensation fields. Falls back gracefully if
    detail page is unreachable.

    Args:
        page: Playwright page object
        detail_url: Full URL to detail page (includes jobId parameter)
        selectors: Selector dict with optional detail_page_* keys

    Returns:
        Dict with keys: description, job_id, job_type, location_type, compensation.
        Values are None if extraction fails or detail page is unreachable.

    Example:
        fields = await extract_detail_page_fields(
            page,
            "https://example.com/jobs?jobId=abc123&pageId=xyz789",
            selectors
        )
        # Returns: {
        #   "description": "Senior Python role...",
        #   "job_id": "abc123",
        #   "job_type": "Contract",
        #   "location_type": "Hybrid",
        #   "compensation": "$120k - $150k"
        # }
    """
    result: Dict[str, Optional[str]] = {
        "description": None,
        "job_id": None,
        "job_type": None,
        "location_type": None,
        "compensation": None,
    }

    try:
        # Always extract job_id from URL first (works even if page navigation fails)
        job_id_param = extract_url_param(detail_url, "jobId")
        if job_id_param:
            result["job_id"] = job_id_param

        # Fetch detail page
        goto_success = await retry_goto(page, detail_url, max_attempts=2, timeout_ms=10000, logger=logger)
        if not goto_success:
            logger.debug(f"Failed to navigate to detail page: {detail_url}")
            return result

        # Wait a bit for page to stabilize
        await page.wait_for_timeout(500)

        # Extract description from detail_page_description selector
        description_selector = selectors.get("detail_page_description")
        if description_selector:
            description = await extract_text(page, description_selector)
            if description:
                result["description"] = description

        # Extract job_id from detail_page_job_id selector if not found in URL
        if not result["job_id"]:
            job_id_selector = selectors.get("detail_page_job_id")
            if job_id_selector:
                job_id = await extract_text(page, job_id_selector)
                if job_id:
                    result["job_id"] = job_id

        # Extract job_type from direct selector, or fall back to text parsing
        job_type_selector = selectors.get("detail_page_job_type")
        if job_type_selector:
            job_type = await extract_text(page, job_type_selector)
            if job_type:
                result["job_type"] = job_type

        # Fall back to text parsing if direct selector didn't work
        if not result["job_type"]:
            details_container_selector = selectors.get("detail_page_details_container")
            if details_container_selector:
                try:
                    container = await page.query_selector(details_container_selector)
                    if container:
                        details_text = await container.text_content()
                        if details_text:
                            # Parse job_type: text after "Job types:" and before next field
                            job_type = parse_field(details_text, "Job types:", "Location type:")
                            if job_type:
                                result["job_type"] = job_type
                except Exception as e:
                    logger.debug(f"Error extracting details from container: {e}")

        # Extract location_type from direct selector, or fall back to text parsing
        location_type_selector = selectors.get("detail_page_location_type")
        if location_type_selector:
            location_type = await extract_text(page, location_type_selector)
            if location_type:
                result["location_type"] = location_type

        # Fall back to text parsing if direct selector didn't work
        if not result["location_type"]:
            details_container_selector = selectors.get("detail_page_details_container")
            if details_container_selector:
                try:
                    container = await page.query_selector(details_container_selector)
                    if container:
                        details_text = await container.text_content()
                        if details_text:
                            # Parse location_type: text after "Location type:" and before next field
                            location_type = parse_field(details_text, "Location type:", "Skills")
                            if location_type:
                                result["location_type"] = location_type
                except Exception as e:
                    logger.debug(f"Error extracting details from container: {e}")

        # Extract compensation from detail_page_compensation selector
        compensation_selector = selectors.get("detail_page_compensation")
        if compensation_selector:
            compensation = await extract_text(page, compensation_selector)
            if compensation:
                result["compensation"] = compensation

        logger.debug(f"Extracted detail page fields: {result}")
        return result

    except Exception as e:
        logger.debug(f"Error extracting detail page fields: {e}")
        return result


async def extract_job_from_container(
    page: Page,
    container: Any,
    company_name: str,
    selectors: Dict[str, str],
    base_url: str = "",
    company_key: str = "",
    container_index: int = 0,
) -> Optional[Dict[str, Any]]:
    """
    Extract job details from a single job container element.

    For WorkSource jobs, extracts jobId by clicking link and navigating to detail page.
    All other fields (title, location, company, description) are extracted from container
    BEFORE clicking to avoid stale DOM references.

    Args:
        page: Playwright page object
        container: Job container element
        company_name: Display name from config (e.g., "WorkSource for Jobs")
        selectors: CSS selectors for extraction
        base_url: Base URL for relative link joining
        company_key: Company key for special handling (e.g., "WorkSource")
        container_index: Container index for debug logging

    Returns:
        Dict with all 13 fields required for loader compatibility:
        id, title, company, location, url, description, requirements,
        salary_min, salary_max, posted_date, crawled_at, status, source_config.
        source_config is the config dict key (company_key), not the extracted
        display company. Returns None if extraction fails or title is missing.
    """
    try:
        # Debug logging at start of function
        container_type = container.tag_name if hasattr(container, "tag_name") else "unknown"
        logger.debug(f"Container {container_index}: Extracting job from container (type: {container_type})")

        # Extract title with detailed logging
        try:
            title = await extract_text(container, selectors.get("title"))
            logger.debug(f"Container {container_index} title extraction: {title}")
        except Exception as e:
            logger.warning(f"Container {container_index} title extraction failed: {e}")
            title = None

        # Extract location with detailed logging
        try:
            location = await extract_text(container, selectors.get("location"))
            logger.debug(f"Container {container_index} location extraction: {location}")
        except Exception as e:
            logger.warning(f"Container {container_index} location extraction failed: {e}")
            location = None

        # Extract link with detailed logging
        try:
            link = await extract_link(container, selectors.get("link"))
            logger.debug(f"Container {container_index} link extraction: {link}")
        except Exception as e:
            logger.warning(f"Container {container_index} link extraction failed: {e}")
            link = None

        # Extract posted_on_text
        try:
            posted_on_text = await extract_text(container, selectors.get("posted_on"))
            logger.debug(f"Container {container_index} posted_on extraction: {posted_on_text}")
        except Exception as e:
            logger.warning(f"Container {container_index} posted_on extraction failed: {e}")
            posted_on_text = None

        # Extract description with detailed logging
        try:
            description = await extract_text(container, selectors.get("description"))
            desc_preview = description[:50] if description else None
            logger.debug(f"Container {container_index} description extraction: {desc_preview}...")
        except Exception as e:
            logger.warning(f"Container {container_index} description extraction failed: {e}")
            description = None

        logger.debug(f"Container {container_index}: title={title}, link={link}, company_name={company_name}")

        if not title:
            logger.debug(f"Container {container_index}: Skipping container: no title found")
            return None

        # Extract company name from card (falls back to config name if absent)
        try:
            extracted_company = await extract_text(container, selectors.get("company"))
            logger.debug(f"Container {container_index} company extraction: {extracted_company}")
        except Exception as e:
            logger.warning(f"Container {container_index} company extraction failed: {e}")
            extracted_company = None

        company_to_use = extracted_company or company_name

        # Handle jobId extraction for WorkSource jobs via navigation
        # For WorkSource: click link → navigate → extract jobId from detail page URL → navigate back
        url = ""
        if link and company_key == "WorkSource":
            link_preview = link[:80] if link else "None"
            logger.debug(
                f"Container {container_index}: [jobId_extract] Processing WorkSource link with click: {link_preview}..."
            )
            try:
                # Step 1: Click the link selector on the container
                link_selector = selectors.get("link")
                if link_selector:
                    link_elem = await container.query_selector(link_selector)
                    if link_elem:
                        # Click the link to navigate to detail page
                        await link_elem.click()
                        logger.debug(f"Container {container_index}: [jobId_extract] Clicked link selector")

                        # Step 2: Wait for navigation to complete
                        await page.wait_for_timeout(1000)
                        logger.debug(f"Container {container_index}: [jobId_extract] Navigation wait completed")

                        # Step 3: Extract jobId from current page URL
                        current_url = page.url
                        job_id_param = extract_url_param(current_url, "jobId")
                        logger.debug(f"Container {container_index}: [jobId_extract] Current page URL: {current_url}")
                        logger.debug(f"Container {container_index}: [jobId_extract] jobId extracted: {job_id_param}")

                        if job_id_param:
                            # Construct URL with jobId parameter
                            separator = "&" if "?" in base_url else "?"
                            url = base_url + separator + f"jobId={job_id_param}"
                            logger.debug(
                                f"Container {container_index}: [jobId_extract] Constructed URL with jobId: {url}"
                            )

                        # Note: Don't navigate back. Page state remains valid for subsequent extractions.
                        logger.debug(
                            f"Container {container_index}: [jobId_extract] jobId extracted, ready for next container"
                        )
                    else:
                        logger.warning(
                            f"Container {container_index}: [jobId_extract] Could not find link element to click"
                        )
                else:
                    logger.warning(f"Container {container_index}: [jobId_extract] No link selector configured")
            except Exception as e:
                logger.warning(f"Container {container_index}: [jobId_extract] Click navigation failed: {e}")
                # Fallback to link-as-is if click fails
                if link:
                    if link.startswith("http"):
                        url = link
                    elif base_url:
                        url = urljoin(base_url, link)
                    else:
                        url = link
                    logger.debug(f"Container {container_index}: [jobId_extract] Fallback: using link directly: {url}")
        elif link and not base_url:
            # Link but no base_url: use as-is
            url = link
            logger.debug(f"Container {container_index}: [jobId_extract] No base_url, using link directly: {url}")
        elif link and base_url:
            # Link and base_url but not WorkSource: simple URL join
            if link.startswith("http"):
                url = link
                logger.debug(f"Container {container_index}: [jobId_extract] Absolute link, using as-is: {url}")
            else:
                url = urljoin(base_url, link)
                logger.debug(
                    f"Container {container_index}: [jobId_extract] Relative link, joining with base_url: {url}"
                )

        # Generate deterministic job ID
        job_id = generate_job_id(
            company=company_to_use,
            title=title,
            location=location or "",
            url=url or None,
        )

        # Get current timestamp in UTC (matching production crawler format)
        crawled_at_dt = datetime.now(UTC)
        crawled_at = crawled_at_dt.isoformat()

        # Parse posted date from Workday-style relative dates
        posted_date = parse_posted_date(posted_on_text, crawled_at_dt)

        logger.debug(f"Container {container_index}: Successfully created JobPosting with ID {job_id}")

        return {
            "id": job_id,
            "title": title,
            "company": company_to_use,
            "location": location or "",
            "url": url or "",
            "description": description,
            "requirements": None,
            "salary_min": None,
            "salary_max": None,
            "posted_date": posted_date,
            "crawled_at": crawled_at,
            "status": "pending_review",
            "source_config": company_key,
        }
    except Exception as e:
        logger.warning(f"Container {container_index}: Error extracting job from container: {e}")
        import traceback

        logger.debug(f"Container {container_index}: Exception traceback: {traceback.format_exc()}")
        return None


# ============================================================================
# COMPANY CRAWLING
# ============================================================================


async def crawl_company_jobs(
    browser: Browser,
    company_key: str,
    company_config: Dict[str, Any],
    timeout_ms: int = 30000,
) -> List[Dict[str, Any]]:
    """
    Crawl a company's career page and extract job listings.

    Args:
        browser: Playwright browser instance
        company_key: Company key (e.g., "CarbonRobotics")
        company_config: Company configuration dict with url, selectors, crawler
        timeout_ms: Page navigation timeout in milliseconds

    Returns:
        List of extracted job dicts with 12 fields:
        id, title, company, location, url, description, requirements,
        salary_min, salary_max, posted_date, crawled_at, status.
    """
    if not company_config.get("enabled", True):
        logger.info(f"Skipping disabled company: {company_key}")
        return []

    url = company_config.get("url")
    if not url:
        logger.warning(f"Company {company_key} has no URL configured")
        return []

    # Get display name from config (e.g., "Carbon Robotics" instead of "CarbonRobotics")
    company_display_name = company_config.get("name", company_key)

    crawler_config = company_config.get("crawler", {})
    selectors = company_config.get("selectors", {})

    try:
        logger.info(f"Crawling {company_key} at {url}")
        page = await browser.new_page()
        page.set_default_timeout(timeout_ms)

        # Navigate to career page
        if not await retry_goto(page, url, max_attempts=3, timeout_ms=timeout_ms, logger=logger):
            logger.warning(f"Failed to navigate to {company_key} career page")
            await page.close()
            return []

        # Wait for optional selector
        wait_selector = crawler_config.get("wait_for_selector", selectors.get("job_container"))
        if wait_selector:
            try:
                await page.wait_for_selector(wait_selector, timeout=10000)
                logger.debug(f"Found wait selector: {wait_selector}")
            except Exception as e:
                logger.warning(f"Wait selector '{wait_selector}' not found: {e}")

        # Delay before extraction
        delay_ms = crawler_config.get("delay_ms", 2000)
        await page.wait_for_timeout(delay_ms)

        # Extract job containers
        # For WorkSource, use job_card selector to iterate individual cards (20 cards)
        # For other companies, use job_container selector (prevents regression)
        if company_key == "WorkSource":
            job_selector = selectors.get("job_card") or GENERIC_FALLBACK_SELECTORS.get("job_card")
            selector_type = "job_card"
        else:
            job_selector = selectors.get("job_container") or GENERIC_FALLBACK_SELECTORS.get("job_container")
            selector_type = "job_container"

        if not job_selector:
            logger.error(f"No {selector_type} selector found for {company_key}")
            await page.close()
            return []

        job_containers = await page.query_selector_all(job_selector)
        logger.info(f"Found {len(job_containers)} {selector_type} elements in {company_key}")

        jobs: List[Dict[str, Any]] = []
        max_jobs_debug = crawler_config.get("max_jobs_debug")

        for i, container in enumerate(job_containers, 1):
            if max_jobs_debug and i > max_jobs_debug:
                logger.debug(f"Stopping at {max_jobs_debug} jobs (debug mode)")
                break

            try:
                job = await extract_job_from_container(
                    page, container, company_display_name, selectors, url, company_key=company_key, container_index=i
                )
                if job:
                    jobs.append(job)
                    logger.debug(f"Extracted job {i}/{len(job_containers)}: {job['title'][:50]}...")
            except Exception as e:
                logger.warning(f"Failed to extract job {i} from {company_key}: {e}")
                # Continue to next job on failure

        await page.close()
        logger.info(f"Successfully extracted {len(jobs)} jobs from {company_key}")
        return jobs

    except Exception as e:
        logger.error(f"Error crawling {company_key}: {e}")
        return []


# ============================================================================
# MAIN CRAWL FUNCTION
# ============================================================================


async def crawl_all_companies(
    config_dir: str = "config_test",
    output_dir: str = "data/work",
    company_filter: Optional[str] = None,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> int:
    """
    Crawl all enabled companies (or filtered set) and write job listings to JSON.

    Args:
        config_dir: Directory containing config JSON files
        output_dir: Directory to write output JSON files
        company_filter: Optional company key to crawl only one company
        headless: If True, run browser in headless mode
        timeout_ms: Page navigation timeout in milliseconds

    Returns:
        Exit code: 0 = success, 1 = config error, 2 = system/browser error
    """
    logger.info("Starting job listing crawler")
    logger.info(f"Config dir: {config_dir}")
    logger.info(f"Output dir: {output_dir}")

    # Create output directory
    output_path = Path(output_dir)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create output directory {output_dir}: {e}")
        return 1

    # Load config
    try:
        merged_config = load_all_company_configs(config_dir)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Config loading failed: {e}")
        return 1

    # Filter companies
    companies_to_crawl = merged_config
    if company_filter:
        if company_filter not in companies_to_crawl:
            logger.error(f"Company '{company_filter}' not found in config")
            logger.info(f"Available companies: {', '.join(companies_to_crawl.keys())}")
            return 1
        companies_to_crawl = {company_filter: companies_to_crawl[company_filter]}

    logger.info(f"Crawling {len(companies_to_crawl)} companies")

    # Initialize browser
    playwright: Optional[Playwright] = None
    browser: Optional[Browser] = None
    try:
        playwright, browser = await init_browser(headless=headless)
    except RuntimeError as e:
        logger.error(f"Browser initialization failed: {e}")
        return 2

    try:
        # Crawl each company sequentially
        for company_key, company_config in companies_to_crawl.items():
            try:
                jobs = await crawl_company_jobs(
                    browser,
                    company_key,
                    company_config,
                    timeout_ms=timeout_ms,
                )

                # Write output JSON (even if empty)
                output_file = output_path / f"{company_key}_jobs.json"
                try:
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(jobs, f, indent=2, ensure_ascii=False)
                    logger.info(f"Wrote {len(jobs)} jobs to {output_file}")
                except Exception as e:
                    logger.error(f"Failed to write {output_file}: {e}")

            except Exception as e:
                logger.error(f"Error processing company {company_key}: {e}")
                # Continue to next company on failure

        logger.info("Crawl completed successfully")
        return 0

    finally:
        await close_browser(playwright, browser)


# ============================================================================
# CLI ENTRY POINT
# ============================================================================


def main() -> int:
    """Parse CLI arguments and run crawler."""
    parser = argparse.ArgumentParser(
        description="Crawl job listings from company career pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Crawl all companies
  python -m src.poc.tweak.crawl_list --config-dir config_test --output-dir data/work

  # Crawl single company
  python -m src.poc.tweak.crawl_list --config-dir config_test --company CarbonRobotics

  # Show available companies
  python -m src.poc.tweak.crawl_list --config-dir config_test --list-companies
        """,
    )

    parser.add_argument(
        "--config-dir",
        type=str,
        default="config_test",
        help="Directory containing company config JSON files (default: config_test)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/work",
        help="Directory to write job listing JSON files (default: data/work)",
    )
    parser.add_argument(
        "--company",
        type=str,
        default=None,
        help="Optional: crawl only one company by key (e.g., CarbonRobotics)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Run browser in headed mode (for debugging)",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=30000,
        help="Page navigation timeout in milliseconds (default: 30000)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(__name__, level=args.log_level)

    # Run crawler
    try:
        exit_code = asyncio.run(
            crawl_all_companies(
                config_dir=args.config_dir,
                output_dir=args.output_dir,
                company_filter=args.company,
                headless=args.headless,
                timeout_ms=args.timeout_ms,
            )
        )
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Crawl interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
