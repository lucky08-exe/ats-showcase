---
paths:
  - "src/browser/**"
  - "tests/browser/**"
  - "config/**"
---

# Crawl Phase Rules

Playwright automation patterns, CSS selectors, rate limiting, async coordination.

## Playwright Setup & Patterns

**Start browser:**
```python
from src.browser.manager import BrowserManager

async with BrowserManager() as browser:
    jobs = await browser.fetch_jobs(config)
```

**Always use async context manager** – ensures proper cleanup even if errors occur.

**CSS selector best practices:**
- Test selectors in browser DevTools first
- Include fallbacks: primary selector + secondary selector pair
- Don't hardcode page 1–10; use pagination loops
- Extract text with `.text_content()` or `.evaluate(js)` depending on dynamic content

**Handle dynamic content:**
- Rendered sites (React, Vue): Playwright waits for network idle
- Static sites: Just scrape with selectors
- Check for job count before/after to detect missing items

**Rate limiting:**
- Set in config: `crawl_delay: 2000` (ms between requests)
- Respects robots.txt implicitly via delay
- Network errors: retry with exponential backoff (max 3 attempts)

## Error Handling

See [Crawl-Phase Error Handling](./_common.md#crawl-phase-error-handling) for timeout, login, rate limiting, and selector issues.

## Config File Format

```json
{
  "companies": [
    {
      "name": "Company Name",
      "url": "https://careers.company.com/jobs",
      "selectors": {
        "job_title": ".job-title",
        "job_location": ".job-location",
        "job_description": ".job-description",
        "job_apply_url": "a.apply-btn"
      },
      "crawl_delay": 2000,
      "max_retries": 3
    }
  ]
}
```

## Verification Commands

See [Crawling Commands](./_common.md#crawling-extraction) for test, directory crawl, and log watching commands.
