---
applyTo: 'src/**/*.py'
---

# Code Patterns & Conventions

Code patterns and architectural conventions for ATS Showcase. Use when writing production code.

---

## Pydantic Schema Patterns

All data models use Pydantic v2 with strict validation:

```python
from pydantic import BaseModel, Field, validator

class JobPosting(BaseModel):
    """Job posting with metadata."""
    job_id: str = Field(..., description="Unique identifier")
    title: str
    location: str
    company: str
    raw_html: str
    status: str = Field(default="pending_review")

    @validator('job_id')
    def validate_id(cls, v):
        if not v.strip():
            raise ValueError("job_id cannot be empty")
        return v

    model_config = {"extra": "forbid"}  # Reject unknown fields
```

**Rules:**
- Always use `Field(description="...")` for documentation
- Use validators for complex validation logic
- Set `model_config = {"extra": "forbid"}` to catch errors early
- Use union types instead of optional for clarity: `Field(union=[str, int])`

---

## Async Patterns

All I/O (network, file, database) must be async:

```python
import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def managed_browser():
    """Async context manager for browser resources."""
    browser = await BrowserManager()
    try:
        yield browser
    finally:
        await browser.close()

async def crawl_multiple(configs: list) -> dict:
    """Crawl jobs from multiple companies concurrently."""
    async with managed_browser() as browser:
        tasks = [browser.fetch_jobs(cfg) for cfg in configs]
        results = await asyncio.gather(*tasks)
    return {cfg.name: result for cfg, result in zip(configs, results)}

# Call with: await crawl_multiple(configs)
```

**Rules:**
- Use `async def` for I/O-bound functions (network, DB, file)
- Use `async with` for resource cleanup
- Use `asyncio.gather()` for concurrent tasks
- Never use `.result()` or blocking calls in async functions
- Don't mix sync/async; if any step is async, entire function should be

---

## Typer CLI Patterns

Commands follow this structure:

```python
import typer
from pathlib import Path
from typing import Optional

app = typer.Typer()

@app.command()
def crawl(
    config: str = typer.Option(
        ...,
        help="Config file path (JSON with selectors, delays)"
    ),
    headless: bool = typer.Option(
        True,
        help="Run browser in headless mode"
    ),
    dry_run: bool = typer.Option(
        False,
        help="Show what would be crawled without fetching"
    ),
) -> None:
    """Crawl job listings from configured companies."""
    if not Path(config).exists():
        typer.echo(f"Error: Config not found: {config}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Crawling {config}...")
    # implementation

# Register in main:
if __name__ == "__main__":
    app()
```

**Rules:**
- Every parameter must have `typer.Option()` with `help=`
- Use docstring visible in `--help`
- Use type hints on all parameters
- Return `None`; use `typer.Exit(code)` for error exit
- Use `typer.echo()` for output (works with piping)
- Use `typer.confirm()` for user input

---

## Error Handling Patterns

Always log before raising; show user-friendly messages:

```python
import logging
from src.models.errors import ConfigError

logger = logging.getLogger(__name__)

def load_config(path: str) -> dict:
    """Load and validate config file."""
    try:
        with open(path) as f:
            config = json.load(f)
    except FileNotFoundError as e:
        logger.error(f"Config not found: {path}")
        raise ConfigError(f"Config file not found: {path}") from e
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {path}: {e}")
        raise ConfigError(f"Invalid JSON in config: {str(e)}") from e

    return config
```

**Rules:**
- Log the full error with context (file path, line number, etc.)
- Raise a custom exception with user-friendly message
- Use `from e` to preserve stack trace
- Never swallow exceptions silently
- Catch specific exceptions, not bare `except Exception`

---

## Database Patterns

Always use `JobStore` abstraction; never write raw SQL:

```python
from src.storage.db import JobStore

def review_job(job_id: str, status: str) -> None:
    """Save job review status."""
    store = JobStore()

    # Use JobStore methods (safe, with type validation)
    store.save_review(
        job_id=job_id,
        status=status,
        title="Job Title",
        location="Remote"
    )

    store.close()
```

**Rules:**
- Use context manager if available: `with JobStore() as store:`
- Never construct SQL strings directly
- Use prepared statements (built into JobStore)
- Always close/commit after writes
- Check return values (rows affected, query results)

---

## Token Counting Patterns

Always estimate before sending to LLM:

```python
from src.tokenization.counter import count_tokens

def estimate_assessment_cost(job_text: str, cv_text: str) -> float:
    """Estimate cost before Claude API call."""
    combined = f"{cv_text}\n{job_text}"
    tokens = count_tokens(combined)
    cost_usd = tokens * 0.000003  # Claude 3.5 Sonnet input rate
    return cost_usd

# Show to user:
cost = estimate_assessment_cost(job, cv)
if typer.confirm(f"Estimated cost: ${cost:.4f}. Proceed?"):
    result = assess_job(job, cv)
```

**Rules:**
- Always count tokens before LLM calls
- Show cost estimate to user before proceeding
- Track actual vs estimated tokens in `cost_tracking` table
- Use `tiktoken` for estimates; Claude provides actual in API response

---

## Testing Patterns

Tests should be independent and deterministic:

```python
import pytest
from pathlib import Path
import tempfile

@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    Path(db_path).unlink(missing_ok=True)

class TestJobStore:
    def test_save_and_retrieve(self, temp_db):
        """Test saving and retrieving jobs."""
        store = JobStore(db_path=temp_db)

        store.save_review("job_1", "confirmed", title="Engineer", location="SF")
        status = store.get_review_status("job_1")

        assert status == "confirmed"
        store.close()

    def test_filters_rejected_jobs(self, temp_db):
        """Test that rejected jobs are filtered."""
        store = JobStore(db_path=temp_db)
        store.save_review("job_1", "rejected", reason="location")

        skip, reason = store.should_skip_job("job_1", skip_rejected=True)
        assert skip is True
        store.close()
```

**Rules:**
- Use fixtures for setup/teardown
- Test one behavior per test
- Use descriptive names: `test_<what>_<when>_<expected>`
- Clean up temporary files/databases
- Use `assert` for simple checks, `pytest.raises()` for exceptions
- Run with `uv run pytest tests/ -v --cov=src`

---

## Type Hints

Use type hints on all functions:

```python
from typing import Optional, List, Dict, Tuple

def process_jobs(
    jobs: List[JobPosting],
    min_score: Optional[float] = None
) -> Dict[str, float]:
    """Process jobs and return scores by job_id.

    Args:
        jobs: List of job postings
        min_score: Minimum score filter (optional)

    Returns:
        Mapping of job_id to score
    """
    results: Dict[str, float] = {}
    for job in jobs:
        score = calculate_score(job)
        if min_score is None or score >= min_score:
            results[job.job_id] = score
    return results
```

**Rules:**
- Add type hints to function parameters and return types
- Use `Optional[T]` for nullable, not `T | None` (Pydantic v1 compat)
- Use `List`, `Dict`, `Tuple` from `typing`
- Add brief docstring with Args/Returns sections
- Run `mypy src/ tests/` to check types

---

## Logging Patterns

Use structured logging with context:

```python
import logging

logger = logging.getLogger(__name__)

def assess_job(job_id: str, cv: str, job: str) -> Assessment:
    """Assess job fit with logging."""
    logger.info(f"Starting assessment for job_id={job_id}")

    try:
        tokens = count_tokens(cv + job)
        logger.debug(f"Token count: {tokens} for job_id={job_id}")

        result = llm_provider.assess(cv, job)
        logger.info(f"Assessment complete: job_id={job_id}, score={result.overall_score}")
        return result
    except Exception as e:
        logger.error(f"Assessment failed: job_id={job_id}, error={str(e)}", exc_info=True)
        raise
```

**Rules:**
- Include job_id or relevant context in all log messages
- Use `logger.debug()` for implementation details
- Use `logger.info()` for major milestones
- Use `logger.error()` with `exc_info=True` for exceptions
- Don't log sensitive data (API keys, emails)

---

## Comments

Minimal comments; code should be self-documenting:

```python
# BAD: Comment explains what code does
count = 0
for job in jobs:
    count += 1

# GOOD: Variable name explains intent
confirmed_job_count = sum(1 for job in jobs if job.status == "confirmed")

# ONLY ADD COMMENT: If WHY is non-obvious
# Retry with exponential backoff to respect rate limits
await asyncio.sleep(2 ** attempt)
```

**Rules:**
- Use descriptive variable/function names instead of comments
- Only comment WHY, not WHAT
- No multi-line comment blocks
- No commented-out code (use git history)

---

**Last Updated**: 2026-07-10
**Related**: [DESIGN.md](../../DESIGN.md), [CLAUDE.md](../../CLAUDE.md)
