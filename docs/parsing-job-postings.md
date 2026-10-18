# Parsing Job Postings: Listing Page to Individual Job Posts

**Last Updated**: 2026-06-16
**Scope**: End-to-end job posting extraction workflow using Playwright and CSS selectors

---

## Overview

The ATS Showcase job parsing pipeline consists of three integrated components that work together to extract job postings from company career pages:

1. **Crawler** (`src/browser/crawler.py`) — Navigates listing pages and extracts structured job data
2. **Selector Manager** (`src/browser/selectors.py`) — Manages CSS selectors for multi-site support
3. **HTML Cleaner** (`src/parsers/html_cleaner.py`) — Converts raw HTML to clean, processable text

Configuration is provided via JSON files (e.g., `config_test/workdays.json`) that define selectors, platform types, and crawler behavior per company.

---

## Component Architecture

### 1. Crawler (`src/browser/crawler.py`)

**Purpose**: Orchestrates Playwright browser automation to navigate career pages and extract job listings.

**Key Classes & Methods**:

#### `Crawler` Class

| Method | Purpose |
|--------|---------|
| `__init__(headless, timeout_ms)` | Initialize browser with headless mode and timeout settings |
| `initialize()` | Launch Playwright Chromium browser and create context |
| `close()` | Gracefully shutdown browser and cleanup resources |
| `crawl_company()` | Main extraction logic for a single company |
| `crawl_multiple()` | Parallel crawling for multiple companies |
| `_extract_job_from_container()` | Extract job metadata from individual job card |
| `_extract_text()` | Helper to extract text via CSS selector |
| `_extract_link()` | Helper to extract href via CSS selector |

#### Configuration Parameters

The crawler accepts `crawler_config` dict with:

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `wait_for_selector` | str | `selectors["job_container"]` | Selector to wait for before proceeding |
| `delay_ms` | int | 2000 | Artificial delay (ms) after page load to allow async rendering |

#### Browser Initialization

```python
self.playwright = await async_playwright().start()
self.browser = await self.playwright.chromium.launch(headless=headless)
self.context = await self.browser.new_context()
```

- **Headless mode**: Renders page without UI (faster, suitable for CI/CD)
- **Context**: Isolated browser session; enables cookie/session management
- **Default timeout**: 30 seconds for all page operations

---

### 2. Selector Manager (`src/browser/selectors.py`)

**Purpose**: Centralize and validate CSS selector configuration for multi-site crawling.

**Key Classes & Methods**:

#### `SelectorManager` Class

| Method | Purpose |
|--------|---------|
| `__init__(selectors_file)` | Load selectors from JSON file |
| `load_selectors(filepath)` | Parse and store selector definitions |
| `get_selectors(company)` | Retrieve selector dict for company |
| `add_company(company, selectors)` | Add/update selectors for company |
| `validate_selectors(selectors)` | Verify required fields present |

#### Selector Requirements

```python
required_fields = ["job_container", "title", "description"]
```

Each company config must include these CSS selectors:

| Selector | Purpose | Example |
|----------|---------|---------|
| `job_container` | Root element containing all jobs (listing page) | `[data-automation-id="jobResults"]` |
| `job_list` | Container for individual job cards | `[role="list"]` |
| `job_card` | Individual job listing element | `li` |
| `title` | Job title text within card | `div.css-qiqmbt` |
| `location` | Job location (optional) | `span.location` |
| `link` | Job detail page URL | `a[href]` |
| `description` | Job description preview (optional) | `div.description` |

#### Compound Selectors

For complex DOM traversal, compound selectors allow nested queries:

```json
"compound_all_jobs": "[data-automation-id=\"jobResults\"] [role=\"list\"] li",
"compound_job_titles": "[data-automation-id=\"jobResults\"] [role=\"list\"] li div.css-qiqmbt"
```

These are useful for:
- Validating nesting hierarchy
- Direct selection without intermediate steps
- Debugging selector chains

---

### 3. HTML Cleaner (`src/parsers/html_cleaner.py`)

**Purpose**: Convert raw HTML to clean, structured text for preprocessing.

**Key Classes & Methods**:

#### `HTMLCleaner` Class

| Method | Purpose |
|--------|---------|
| `__init__(prefer_markitdown)` | Initialize with preferred cleaning library |
| `_check_markitdown()` | Verify MarkItDown availability |
| `clean(html)` | Main entry point; converts HTML to text |
| `_clean_with_markitdown(html)` | Primary cleaning using MarkItDown |
| `_clean_with_beautifulsoup(html)` | Fallback cleaning using BeautifulSoup + lxml |
| `_postprocess_text(text)` | Normalize whitespace and remove boilerplate |
| `extract_text(html, selector)` | Extract text using optional CSS selector |
| `remove_boilerplate(text)` | Remove legal/EEO/generic text |

#### Cleaning Pipeline

1. **HTML Parsing**
   - Primary: MarkItDown (Microsoft-maintained, structure-preserving)
   - Fallback: BeautifulSoup + lxml (removes script/style tags)

2. **Text Extraction**
   - Remove `<script>` and `<style>` tags
   - Extract text content
   - Preserve semantic structure (MarkItDown converts to Markdown)

3. **Postprocessing** (normalize_text → remove_boilerplate)
   ```
   1. Strip leading/trailing whitespace per line
   2. Split on double spaces and consolidate
   3. Normalize newlines (3+ → 2)
   4. Normalize spaces (2+ → 1)
   5. Remove boilerplate patterns (regex-based)
   6. Final strip
   ```

#### Boilerplate Patterns Removed

```python
BOILERPLATE_PATTERNS = [
    r"equal\s+opportunity\s+employer",
    r"EEO\s*statement",
    r"we\s+are\s+an\s+equal\s+opportunity",
    r"apply\s+now",
    r"job\s+id\s*[:=]",
    r"posted\s+on\s*:",
    r"job\s+posted",
    r"share\s+this\s+job",
    r"job\s+details",
]
```

---

## Data Flow: Listing Page to Job Details

### Phase 1: Page Load & DOM Wait

```
START
  ↓
Crawler.crawl_company(url, selectors, config)
  ↓
context.new_page()
  ↓
page.goto(url, wait_until="networkidle")
  ├─ Renders page
  ├─ Loads all network requests
  └─ Waits for async JS rendering
  ↓
[wait_for_selector] (optional, default: job_container)
  ├─ Default waits for job listing to load
  └─ Timeout: 10 seconds
  ↓
page.wait_for_timeout(delay_ms)
  └─ Additional wait (default: 2000ms) for SPA updates
```

**Why Multi-Stage Waits?**
- `wait_until="networkidle"` waits for page resources (CSS, JS)
- `wait_for_selector` waits for specific DOM element
- `delay_ms` allows SPA frameworks time to render job cards

Example (Workday):
```json
{
  "url": "https://boeing.wd1.myworkdayjobs.com/en-US/EXTERNAL_CAREERS",
  "crawler": {
    "wait_for_selector": "[data-automation-id=\"jobResults\"]",
    "delay_ms": 2000
  }
}
```

### Phase 2: Listing Page Extraction

```
page.query_selector_all(selectors["job_container"])
  ↓
Returns: job_containers[] (array of DOM elements)
  ↓
FOR EACH job_container:
  ├─ _extract_job_from_container(page, container)
  │  ├─ container.query_selector(selectors["title"])
  │  │  └─ Extract text → job.title
  │  ├─ container.query_selector(selectors["location"])
  │  │  └─ Extract text → job.location
  │  └─ container.query_selector(selectors["link"])
  │     └─ Extract href → job.url
  │
  └─ Create JobPosting object with:
     ├─ title: "Senior Software Engineer"
     ├─ company: "Boeing"
     ├─ location: "Seattle, WA"
     ├─ url: "https://boeing.wd1.myworkdayjobs.com/en-US/job/..."
     ├─ description: "" (empty from listing)
     ├─ requirements: None
     ├─ status: "pending_review"
     └─ crawled_date: datetime.utcnow()
```

**Key Points:**
- Only `title`, `location`, `url` are extracted from listing page
- `description` and `requirements` are left empty (populated later from job detail page)
- `status` set to `pending_review` for manual verification before LLM assessment
- Each job gets unique URL for individual page crawling (Phase 3)

### Phase 3: Individual Job Detail Page Extraction

The job URLs extracted in Phase 2 can be used to crawl individual job detail pages:

```
FOR EACH job IN jobs:
  ├─ Navigate to job.url
  ├─ Extract full description from detail page
  ├─ Parse requirements/qualifications
  ├─ Extract salary info (if available)
  └─ Update JobPosting with full content
```

**Current Implementation Status**:
- Phase 2 (listing extraction) ✅ Implemented
- Phase 3 (detail page extraction) ⏳ Planned (URLs captured, content extraction not yet implemented)

---

## Real-World Example: Boeing Workday

### Configuration (config_test/workdays.json)

```json
{
  "Boeing": {
    "name": "Boeing",
    "url": "https://boeing.wd1.myworkdayjobs.com/en-US/EXTERNAL_CAREERS",
    "selectors": {
      "job_container": "[data-automation-id=\"jobResults\"]",
      "job_list": "[role=\"list\"]",
      "job_card": "li",
      "title": "div.css-qiqmbt",
      "job_id": "div.css-248241",
      "metadata": "div.css-b3pn3b",
      "compound_all_jobs": "[data-automation-id=\"jobResults\"] [role=\"list\"] li",
      "compound_job_titles": "[data-automation-id=\"jobResults\"] [role=\"list\"] li div.css-qiqmbt"
    },
    "metadata": {
      "platform": "workday",
      "total_jobs_found": 40,
      "validation_rate": 100
    }
  }
}
```

### Execution Steps

1. **Page Load**
   ```
   goto("https://boeing.wd1.myworkdayjobs.com/en-US/EXTERNAL_CAREERS")
   wait_for_selector("[data-automation-id=\"jobResults\"]")  // Job listings present
   wait_for_timeout(2000)                                   // SPA rendering
   ```

2. **Locate Job Container**
   ```
   query_selector_all("[data-automation-id=\"jobResults\"]")
   → Returns: 1 container with all jobs
   ```

3. **Find Individual Job Cards**
   ```
   Within container, find all: [role="list"] li
   → Returns: 40 <li> elements (each is a job card)
   ```

4. **Extract Each Job**
   ```
   For li[0]:
     title = query_selector("div.css-qiqmbt").text_content()
     location = derived from metadata if available
     link = query_selector("a[href]").href

   Result: JobPosting(
     title="Senior Systems Engineer",
     location="Seattle, WA",
     url="https://boeing.wd1.myworkdayjobs.com/en-US/job/...",
     ...
   )
   ```

### Why Emotion CSS Classes?

Workday (and similar platforms) use dynamically generated CSS classes:
- **Primary class** `css-1q2dra3` — Applied to most job cards
- **Secondary class** `css-h2nt8k` — Applied to alternate layouts
- **Dynamic** — Classes regenerate on page refresh

**Solution**: Use stable data attributes instead
- ✅ Use: `[data-automation-id="jobResults"]` (stable ID)
- ❌ Avoid: `.css-1q2dra3` (regenerates)

---

## Selector Discovery & Validation

### How to Find Selectors

1. **Open Browser DevTools** (F12)
2. **Inspect job card element** (right-click → Inspect)
3. **Look for**:
   - `data-*` attributes (stable, preferred)
   - Unique class combinations (less stable)
   - Avoid: Auto-generated classes like `.css-XXXXX`

4. **Test in DevTools Console**:
   ```javascript
   // Find all job cards
   document.querySelectorAll("[data-automation-id='jobResults'] [role='list'] li")

   // Find all titles
   document.querySelectorAll("[data-automation-id='jobResults'] [role='list'] li div.css-qiqmbt")

   // Verify count matches expected
   ```

### Validation Metadata

The config includes evaluation results:

```json
"metadata": {
  "platform": "workday",
  "total_jobs_found": 40,
  "validation_rate": 100,
  "valid_cards": 40,
  "last_evaluated": "2026-06-15T17:42:18Z"
}
```

- **validation_rate** — % of cards with required fields (title)
- **last_evaluated** — When selectors were last tested
- **Stale configs** — If evaluation date > 30 days, re-validate selectors

---

## Error Handling & Recovery

### Crawler-Level

| Scenario | Handling |
|----------|----------|
| **Selector not found** | Log warning, wait fails gracefully, continue with available jobs |
| **Job extraction fails** | Log warning, skip job, continue with next |
| **Page load timeout** | Return empty list after timeout |
| **Container query returns 0** | Log info (may be empty careers page), return empty list |

```python
try:
    await page.wait_for_selector(wait_selector, timeout=10000)
except Exception as e:
    logger.warning(f"Selector {wait_selector} not found: {e}")
    # Continue without waiting
```

### Extraction-Level

```python
try:
    job = await self._extract_job_from_container(page, container, company_name, selectors)
    if job:
        jobs.append(job)
except Exception as e:
    logger.warning(f"Failed to extract job {i}: {e}")
    # Skip this job, continue with next
```

### HTML Cleaning-Level

```python
# Try MarkItDown first
if self.prefer_markitdown and self.markitdown_available:
    try:
        return self._clean_with_markitdown(html)
    except Exception:
        # Fall back to BeautifulSoup
        return self._clean_with_beautifulsoup(html)
```

---

## Performance Considerations

### Parallelization

```python
tasks = []
for company_name, company_config in companies.items():
    task = self.crawl_company(...)
    tasks.append((company_name, task))

# Execute concurrently
for company_name, task in tasks:
    results[company_name] = await task
```

**Async benefits**:
- Multiple companies crawled in parallel
- Single company: Job extraction is sequential (per-job processing in loop)
- Overall throughput: ~5-10 companies concurrently (limited by browser resources)

### Browser Resource Management

```python
# One page per job extraction loop iteration
for i, container in enumerate(job_containers):
    # Queries within same page (no new context)
    job = await self._extract_job_from_container(page, container, ...)

# Close after all jobs extracted
await page.close()
```

- **Context reuse** — Single page object for all jobs on listing
- **No redundant navigation** — Single page load per company
- **Cleanup** — Pages explicitly closed to free resources

---

## Data Model

### JobPosting Object

Created by crawler at listing page extraction:

```python
JobPosting(
    id=None,                              # Auto-generated in DB
    title="Senior Software Engineer",     # From listing page
    company="Boeing",                      # Config
    location="Seattle, WA",               # From listing page selector
    url="https://...",                    # From listing page selector
    description="",                       # Empty (filled from detail page later)
    requirements=None,                    # Not extracted yet
    salary_min=None,                      # Not extracted
    salary_max=None,                      # Not extracted
    posted_date=None,                     # Not extracted
    status="pending_review",              # Default status
    crawled_date=datetime.utcnow(),      # Extraction timestamp
)
```

### Status Lifecycle

```
pending_review  →  confirmed / rejected  →  (if confirmed) assessed
                                        ↓
                            Assessment results + match scores
```

---

## Future Enhancements

### Phase 3: Detail Page Extraction (Planned)

Currently extracted URLs can be used to:

1. **Navigate to each job detail page**
   ```python
   async def crawl_job_detail(url: str) -> Optional[str]:
       page = await context.new_page()
       await page.goto(url)
       # Extract full description, requirements, salary
       description = await page.query_selector(selector_description).text_content()
       return description
   ```

2. **Extract full job description** (currently blank)
   ```python
   job.description = HTMLCleaner().clean(detail_html)
   ```

3. **Parse requirements** (currently None)
   ```python
   job.requirements = parse_requirements_from_description(job.description)
   ```

### Multi-Page Listing Support

For sites with pagination:

```python
# In crawler config
"pagination": {
    "next_button_selector": "a.next-page",
    "max_pages": 5
}

# Loop through pages
while has_next_page:
    page = await page.click(selector_next)
    jobs.extend(await extract_jobs(page))
```

### Dynamic Site Support

For JavaScript-heavy sites:

```python
# In crawler config
"wait_strategies": {
    "network_idle": true,           # Wait for network
    "wait_for_selector": "[data-loaded]",
    "wait_ms": 5000                 # Extra buffer
}
```

---

## Debugging Guide

### Verify Selectors

```bash
# Open Chrome DevTools in target career page
# Run in console:
document.querySelectorAll('[data-automation-id="jobResults"]')
document.querySelectorAll('[data-automation-id="jobResults"] [role="list"] li')

# Should return NodeList with expected count
```

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("src.browser.crawler")
# Now you'll see detailed extraction logs
```

### Test Single Company

```python
from src.browser.crawler import Crawler
import asyncio

async def test():
    crawler = Crawler(headless=False)  # Visual mode for debugging
    jobs = await crawler.crawl_company(
        "Boeing",
        "https://boeing.wd1.myworkdayjobs.com/en-US/EXTERNAL_CAREERS",
        {
            "job_container": "[data-automation-id='jobResults']",
            "title": "div.css-qiqmbt",
            "location": "span.location",
            "link": "a[href]",
        }
    )
    for job in jobs:
        print(f"{job.title} @ {job.company}")
    await crawler.close()

asyncio.run(test())
```

### Inspect Network Requests

In Playwright:

```python
page.on("response", lambda response: print(f"{response.url}: {response.status}"))
```

---

## Summary

The job parsing pipeline provides a modular, extensible system for extracting job postings:

1. **Crawler** handles navigation, page loading, and job card extraction
2. **Selector Manager** centralizes multi-site configuration and validation
3. **HTML Cleaner** converts raw HTML to clean, processable text
4. **Configuration files** (JSON) enable site-specific selector definition

**Current Capabilities**:
- ✅ Multi-site crawling (Workday, generic platforms)
- ✅ Async/parallel execution
- ✅ Graceful error handling
- ✅ HTML cleaning with MarkItDown/BeautifulSoup

**Next Steps**:
- 🚧 Detail page extraction (job descriptions, requirements, salary)
- 🚧 Pagination support
- 🚧 Multi-step job application flow crawling
