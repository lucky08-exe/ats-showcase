# CRAWL Phase: Multi-Site Crawler Maintenance

**Goal**: Crawl company career pages reliably and maintain extraction logic across multiple sites.

**Challenge**: Each company website has unique HTML structure. Selectors break when sites update.

**Solution**: Configuration-driven architecture + Adapter pattern + Fallback strategies

---

## Design Philosophy

### The Problem: Brittle Selectors

Traditional web scrapers hardcode selectors in code:
```python
# ❌ BAD: Selector hardcoded in code
def scrape_company_a():
    title_el = page.select_one("div.job-card h3.title")
```

Issues:
- Company changes HTML → code breaks
- Adding new company requires code change
- Testing is tied to company websites
- Non-developers can't update scrapers

### The Solution: Configuration-Driven

Store all site-specific logic in config files:
```json
{
  "name": "Company A",
  "url": "https://companya.com/careers",
  "selectors": {
    "container": "div.job-card",
    "title": "h3.title"
  }
}
```

Benefits:
- ✅ Update selectors without touching code
- ✅ Easy to add/remove companies
- ✅ Version control tracks changes
- ✅ Non-developers can maintain

---

## Configuration Schema

Store all companies in `config/companies.json`:

```json
{
  "companies": [
    {
      "id": "company_a",
      "name": "Company A",
      "url": "https://companya.com/careers",
      "enabled": true,
      "description": "Manufacturing company, MES/MOM roles",

      "crawler": {
        "type": "pagination",
        "headless": true,
        "timeout_ms": 30000,
        "max_pages": 5,
        "delay_between_pages_ms": 2000
      },

      "job_selectors": {
        "container": "div.job-card",
        "title": "h3.job-title",
        "description": "p.job-description",
        "salary": "span.salary",
        "url": "a.apply-link[href]",
        "location": "span.location"
      },

      "selectors_fallback": [
        {
          "container": "div[class*='job']",
          "title": "h2",
          "description": "div.description"
        }
      ],

      "pagination": {
        "enabled": true,
        "selector": "a.next-page"
      },

      "wait_for": {
        "selector": "div.job-card",
        "timeout_ms": 30000
      },

      "cleanup_patterns": [
        "Equal Opportunity Employer",
        "Salary determined based"
      ],

      "notes": "Updated 2025-01-15 after site redesign"
    }
  ]
}
```

---

## CLI Instrumentation: Click vs Typer

### Option 1: Click Framework (Traditional)

**Pros**: Mature, stable, widely used
**Cons**: Verbose boilerplate, decorators style

```python
# src/cli_click.py - Click Implementation

import click
import json
import asyncio
from pathlib import Path
from src.browser.adapter_factory import AdapterFactory

@click.group()
def cli():
    """ATS Showcase - Job Crawling Tool"""
    pass

@cli.command()
@click.option(
    "--config",
    type=click.Path(exists=True),
    default="config/companies.json",
    help="Company config file"
)
@click.option(
    "--company",
    type=str,
    default=None,
    help="Crawl single company only (e.g., 'Company A')"
)
@click.option(
    "--headless",
    type=bool,
    is_flag=True,
    default=True,
    help="Run Playwright in headless mode"
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default="data/extracted_jobs",
    help="Output directory for extracted jobs"
)
def crawl(config, company, headless, output_dir):
    """Crawl company careers pages and extract job postings."""
    click.echo(f"📡 Crawling from config: {config}")

    try:
        # Load config
        with open(config) as f:
            companies_config = json.load(f)

        # Filter by company if specified
        if company:
            companies_config["companies"] = [
                c for c in companies_config["companies"]
                if c["name"].lower() == company.lower()
            ]
            if not companies_config["companies"]:
                click.echo(f"❌ Company '{company}' not found", err=True)
                raise click.Exit(1)

        # Run crawler
        asyncio.run(_crawl_companies(companies_config, headless, output_dir))
        click.echo(f"✅ Crawl completed. Results in {output_dir}/")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Exit(1)

@cli.command()
@click.option(
    "--file",
    type=click.Path(exists=True),
    required=True,
    help="JSON file with extracted jobs"
)
@click.option(
    "--auto-approve-threshold",
    type=float,
    default=0.9,
    help="Auto-approve jobs with confidence > threshold"
)
def review(file, auto_approve_threshold):
    """Review and confirm extracted job data."""
    click.echo(f"👀 Reviewing {file}...")
    # Implementation...
    click.echo("✅ Review completed")

if __name__ == "__main__":
    cli()
```

**Usage**:
```bash
python main.py crawl --config config/companies.json
python main.py crawl --company "Company A" --headless
python main.py review --file data/extracted_jobs/Company_A_jobs.json
```

---

### Option 2: Typer Framework (Modern)

**Pros**: Clean, type hints, auto-generated docs
**Cons**: Newer, smaller community

```python
# src/cli_typer.py - Typer Implementation

import typer
import json
import asyncio
from pathlib import Path
from typing import Optional
from src.browser.adapter_factory import AdapterFactory

app = typer.Typer(help="ATS Showcase - Job Crawling Tool")

@app.command()
def crawl(
    config: str = typer.Option(
        "config/companies.json",
        "--config",
        help="Company config file"
    ),
    company: Optional[str] = typer.Option(
        None,
        "--company",
        help="Crawl single company only (e.g., 'Company A')"
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--no-headless",
        help="Run Playwright in headless mode"
    ),
    output_dir: str = typer.Option(
        "data/extracted_jobs",
        "--output-dir",
        help="Output directory for extracted jobs"
    ),
):
    """Crawl company careers pages and extract job postings."""
    typer.echo(f"📡 Crawling from config: {config}")

    try:
        # Load config
        with open(config) as f:
            companies_config = json.load(f)

        # Filter by company if specified
        if company:
            companies_config["companies"] = [
                c for c in companies_config["companies"]
                if c["name"].lower() == company.lower()
            ]
            if not companies_config["companies"]:
                typer.echo(f"❌ Company '{company}' not found", err=True)
                raise typer.Exit(1)

        # Run crawler
        asyncio.run(_crawl_companies(companies_config, headless, output_dir))
        typer.echo(f"✅ Crawl completed. Results in {output_dir}/")

    except Exception as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)

@app.command()
def review(
    file: str = typer.Argument(..., help="JSON file with extracted jobs"),
    auto_approve_threshold: float = typer.Option(
        0.9,
        "--threshold",
        min=0.0,
        max=1.0,
        help="Auto-approve jobs with confidence > threshold"
    ),
):
    """Review and confirm extracted job data."""
    typer.echo(f"👀 Reviewing {file}...")
    # Implementation...
    typer.echo("✅ Review completed")

if __name__ == "__main__":
    app()
```

**Usage**:
```bash
python main.py crawl --config config/companies.json
python main.py crawl --company "Company A"  # headless is default
python main.py review data/extracted_jobs/Company_A_jobs.json
```

---

### Comparison

| Feature | Click | Typer |
|---------|-------|-------|
| Type hints | Optional | Required |
| Learning curve | Medium | Easy |
| Community | Large | Growing |
| Auto-docs | Manual | Automatic |
| Async support | Manual | Built-in |
| Decorator style | `@click.option` | `typer.Option()` |
| **Recommended** | Stable projects | New projects |

**For this project: Typer** (modern, cleaner, less boilerplate)

---

## Adapter Pattern (Extensible)

### Base Adapter

```python
# src/browser/adapters/base.py

from abc import ABC, abstractmethod
from typing import List
from src.models.job_posting import JobPosting

class SiteAdapter(ABC):
    """Base adapter for scraping a site."""

    def __init__(self, config: dict):
        self.config = config
        self.name = config["name"]
        self.url = config["url"]

    @abstractmethod
    async def crawl(self) -> List[JobPosting]:
        """Crawl site and return job postings."""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """Validate configuration is correct."""
        pass
```

### Pagination Adapter Implementation

```python
# src/browser/adapters/pagination_adapter.py

import asyncio
import logging
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup
from src.models.job_posting import JobPosting

logger = logging.getLogger(__name__)

class PaginationAdapter(SiteAdapter):
    """Handle sites with traditional pagination."""

    async def crawl(self) -> List[JobPosting]:
        """Crawl multi-page site."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config["crawler"]["headless"]
            )
            page = await browser.new_page()

            try:
                jobs = await self._crawl_pages(page)
                return jobs
            finally:
                await browser.close()

    async def _crawl_pages(self, page: Page) -> List[JobPosting]:
        """Crawl all pages with pagination."""
        jobs = []
        url = self.config["url"]
        max_pages = self.config["crawler"]["max_pages"]

        for page_num in range(max_pages):
            try:
                # Navigate
                logger.info(f"{self.name} Page {page_num + 1}/{max_pages}")
                await page.goto(url, wait_until="networkidle")

                # Wait for content
                wait_config = self.config["wait_for"]
                await page.wait_for_selector(
                    wait_config["selector"],
                    timeout=wait_config["timeout_ms"]
                )

                # Extract jobs
                page_jobs = await self._extract_jobs(page)
                jobs.extend(page_jobs)
                logger.info(f"Extracted {len(page_jobs)} jobs")

                # Find next page
                next_url = await self._find_next_page_url(page)
                if not next_url:
                    break

                url = next_url

                # Respect server
                delay = self.config["crawler"]["delay_between_pages_ms"]
                await asyncio.sleep(delay / 1000)

            except Exception as e:
                logger.warning(f"Page {page_num} error: {e}")
                break

        return jobs

    async def _extract_jobs(self, page: Page) -> List[JobPosting]:
        """Extract jobs with fallback selectors."""
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        # Try primary selectors
        jobs = self._parse_jobs(soup, self.config["job_selectors"])

        if jobs:
            return jobs

        # Try fallback selectors
        logger.warning("Primary selectors failed, trying fallbacks")
        for fallback_sel in self.config.get("selectors_fallback", []):
            jobs = self._parse_jobs(soup, fallback_sel)
            if jobs:
                logger.warning(f"Used fallback selector")
                return jobs

        logger.error("All selectors failed")
        return []

    def _parse_jobs(self, soup, selectors: dict) -> List[JobPosting]:
        """Parse jobs with given selectors."""
        jobs = []

        for job_el in soup.select(selectors["container"]):
            try:
                title_el = job_el.select_one(selectors["title"])
                desc_el = job_el.select_one(selectors["description"])

                if not title_el or not desc_el:
                    continue

                job = JobPosting(
                    job_id=f"{self.name}_{len(jobs)}",
                    company=self.name,
                    title=title_el.get_text(strip=True),
                    raw_description=desc_el.get_text(strip=True),
                    url=self._extract_url(job_el, selectors),
                    extraction_confidence=0.95,
                    status="pending_review"
                )

                jobs.append(job)

            except Exception as e:
                logger.debug(f"Job extraction error: {e}")
                continue

        return jobs

    def _extract_url(self, element, selectors: dict) -> str | None:
        """Extract URL with relative path handling."""
        if "url" not in selectors:
            return None

        url_el = element.select_one(selectors["url"])
        if not url_el:
            return None

        href = url_el.get("href")

        # Handle relative URLs
        if href and not href.startswith(("http://", "https://")):
            from urllib.parse import urljoin
            return urljoin(self.url, href)

        return href

    async def _find_next_page_url(self, page: Page) -> str | None:
        """Find URL for next page."""
        pagination = self.config.get("pagination", {})

        if not pagination.get("enabled"):
            return None

        try:
            next_selector = pagination["selector"]
            next_el = await page.query_selector(next_selector)

            if not next_el:
                return None

            href = await next_el.get_attribute("href")

            if href and not href.startswith(("http://", "https://")):
                from urllib.parse import urljoin
                return urljoin(page.url, href)

            return href

        except Exception as e:
            logger.debug(f"Next page error: {e}")
            return None

    def validate_config(self) -> bool:
        """Validate required config fields."""
        required = ["url", "job_selectors", "wait_for", "crawler"]
        for field in required:
            if field not in self.config:
                logger.error(f"Missing: {field}")
                return False

        return True
```

### Factory Pattern

```python
# src/browser/adapter_factory.py

class AdapterFactory:
    """Factory to instantiate correct adapter for site."""

    ADAPTERS = {
        "pagination": PaginationAdapter,
        # Future:
        # "infinite_scroll": InfiniteScrollAdapter,
        # "api": ApiAdapter,
    }

    @staticmethod
    def create_adapter(config: dict):
        """Create appropriate adapter for config."""
        crawler_type = config.get("crawler", {}).get("type", "pagination")

        adapter_class = AdapterFactory.ADAPTERS.get(crawler_type)
        if not adapter_class:
            raise ValueError(f"Unknown crawler type: {crawler_type}")

        adapter = adapter_class(config)

        if not adapter.validate_config():
            raise ValueError(f"Invalid config for {config['name']}")

        return adapter
```

---

## Selector Testing

### Unit Tests (No Live Requests)

```python
# tests/test_crawl_unit.py

import pytest
from bs4 import BeautifulSoup
from src.browser.adapters.pagination_adapter import PaginationAdapter

def test_parse_jobs_from_html():
    """Test job parsing on sample HTML."""
    html = """
    <div class="job-card">
        <h3 class="job-title">Senior MES Developer</h3>
        <p class="job-description">5+ years experience</p>
        <a class="apply-link" href="/apply/123">Apply</a>
    </div>
    <div class="job-card">
        <h3 class="job-title">Junior Developer</h3>
        <p class="job-description">Entry level position</p>
        <a class="apply-link" href="/apply/124">Apply</a>
    </div>
    """

    config = {
        "name": "Test Company",
        "url": "https://test.com",
        "job_selectors": {
            "container": "div.job-card",
            "title": "h3.job-title",
            "description": "p.job-description",
            "url": "a.apply-link[href]"
        },
        "crawler": {"headless": True}
    }

    adapter = PaginationAdapter(config)
    soup = BeautifulSoup(html, "lxml")
    jobs = adapter._parse_jobs(soup, config["job_selectors"])

    assert len(jobs) == 2
    assert jobs[0].title == "Senior MES Developer"
    assert jobs[1].title == "Junior Developer"
```

### Integration Tests (Live - Pre-Deployment)

```python
# tests/test_crawl_live.py

import pytest
import json
import asyncio
from src.browser.adapter_factory import AdapterFactory

@pytest.mark.asyncio
@pytest.mark.live  # Skip in CI, run before deployment
async def test_crawl_live():
    """Test crawling live company websites."""
    with open("config/companies.json") as f:
        config = json.load(f)

    for company in config["companies"]:
        if not company.get("enabled"):
            continue

        adapter = AdapterFactory.create_adapter(company)
        jobs = await adapter.crawl()

        assert len(jobs) > 0, f"No jobs extracted from {company['name']}"
        assert all(j.title for j in jobs), f"Some jobs missing titles in {company['name']}"
```

Run tests:
```bash
# Fast unit tests (no network)
uv run pytest tests/test_crawl_unit.py -v

# All including slow live tests (run before deployment)
uv run pytest tests/ -v -m "live"
```

---

## Maintenance Workflow

### Add New Company

```bash
# 1. Find selectors using Playwright Inspector
uv run playwright codegen https://newco.com/careers

# 2. Add to config/companies.json with found selectors

# 3. Test extraction
uv run python main.py crawl --company "New Company"

# 4. Check results
cat data/extracted_jobs/New_Company_jobs.json | head -5

# 5. If OK, commit
git add config/companies.json
git commit -m "feat: add New Company crawling"
```

### Fix Broken Selectors

```bash
# 1. Find new selectors
uv run playwright codegen https://company.com/careers

# 2. Update config/companies.json

# 3. Test
uv run python main.py crawl --company "Company"

# 4. Commit
git add config/companies.json
git commit -m "fix: update Company selectors after redesign"
```

---

## Deployment Checklist

- [ ] All selectors tested on live websites
- [ ] Pagination config verified
- [ ] Timeout values appropriate
- [ ] Browser pool concurrency set (recommend 2-3)
- [ ] Error logging configured
- [ ] Unit tests passing
- [ ] Live tests passing (or pre-deployment)
- [ ] First crawl executed to verify
- [ ] Config changes committed to git

---

## Next Phase

✅ CRAWL complete → Job data extracted

→ Move to **PREPROCESS**: spaCy NLP, semantic chunking, token counting
