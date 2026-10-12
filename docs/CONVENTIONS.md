# CONVENTIONS.md – Code Style, Testing & Deployment

**Table of Contents**
- [Code Style Guide](#code-style-guide)
- [Testing Strategy](#testing-strategy)
- [Git & Commit Workflow](#git--commit-workflow)
- [Documentation Standards](#documentation-standards)
- [Deployment Checklist](#deployment-checklist)
- [Troubleshooting & Common Errors](#troubleshooting--common-errors)

---

## Code Style Guide

### Python Version & Tools

**Target**: Python 3.11+
**Package manager**: `uv` (faster than pip)
**Type checking**: `mypy` (non-strict by default; `run-local-ci.sh --strict` available)
**Linting**: `ruff` (Rust-based, faster than flake8)
**Formatting**: `black` (opinionated, uncompromising)
**Testing**: `pytest` with `pytest-cov` + `pytest-asyncio`

### Project Structure

```
src/
├── __init__.py              (empty or version string)
├── cli.py                   (main entry point, 50-100 lines max)
├── config.py                (env vars, defaults, validation)
├── browser/
│   ├── __init__.py
│   ├── crawler.py           (20–30 functions, 300–500 lines)
│   └── selectors.py         (configuration, no logic)
├── tokenization/
│   ├── __init__.py
│   ├── markitdown.py        (wrapper around MarkItDown)
│   ├── cleaner.py           (BeautifulSoup post-processing)
│   ├── nld_processor.py      (spaCy NER entity extraction)
│   └── counter.py           (tiktoken integration)
├── verification/
│   ├── __init__.py
│   ├── interactive_cli.py    (Typer UI, <200 lines)
│   └── reviewer.py          (business logic)
├── llm/
│   ├── __init__.py
│   ├── claude_client.py      (Anthropic API wrapper)
│   ├── prompts.py           (templates, no API calls)
│   └── batch_processor.py    (queueing, cost tracking)
└── storage/
    ├── __init__.py
    ├── db_client.py         (connection pool, transactions)
    ├── schema.py            (table definitions)
    ├── queries.py           (common patterns)
    └── export.py            (markdown + JSON output)

tests/
├── __init__.py
├── test_browser.py          (mock Playwright, assert selectors)
├── test_tokenization.py     (mock spaCy, assert token counts)
├── test_verification.py     (mock CLI input, assert output)
├── test_llm.py             (mock Claude, assert prompts)
├── test_storage.py         (in-memory SQLite, assert queries)
└── conftest.py             (pytest fixtures, mocks)

.github/
├── workflows/
│   ├── test.yml             (run tests + lint on PR)
│   ├── deploy.yml           (build Docker on merge to main)
│   └── codeql.yml           (security scan)
├── copilot-instructions.md  (quick-start)
└── PULL_REQUEST_TEMPLATE.md (standard PR format)
```

### Naming Conventions

**Modules**: `snake_case` (crawler.py, llm_client.py)
**Classes**: `PascalCase` (JobCrawler, CLaudeClient, StorageClient)
**Functions**: `snake_case` (extract_job_title, validate_selector)
**Constants**: `UPPER_SNAKE_CASE` (MAX_RETRIES, DEFAULT_TIMEOUT)
**Private**: `_leading_underscore` (_internal_helper, _parse_html)
**Dataclasses**: `PascalCase` (RawJob, PreprocessedJob, Assessment)
**Type hints**: Always required (mypy; strict via `run-local-ci.sh --strict`)

```python
# GOOD
class JobCrawler:
    MAX_RETRIES = 5
    DEFAULT_TIMEOUT = 30

    def __init__(self, config: CrawlerConfig) -> None:
        self._browser_pool: list[Browser] = []

    async def extract_jobs(self, url: str) -> list[RawJob]:
        pass

# BAD
class job_crawler:  # lowercase class
    def extractJobs(self, url):  # camelCase method
        MAX_TIMEOUT = 30  # constant in method
        pass
```

### Type Hints & Dataclasses

Use `dataclasses` for models (avoids boilerplate):

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class RawJob:
    """Extracted job from crawl phase."""
    url: str
    title: str
    company: str
    html: str
    timestamp: datetime

    def __post_init__(self) -> None:
        # Validation after init
        if not self.url.startswith("http"):
            raise ValueError(f"Invalid URL: {self.url}")

# Use
job = RawJob(
    url="https://...",
    title="Engineer",
    company="Acme",
    html="<html>...",
    timestamp=datetime.now()
)
```

### Error Handling

**Prefer specific exceptions**:

```python
# GOOD
class JobCrawlerError(Exception):
    """Base class for crawler errors."""
    pass

class SelectorNotFoundError(JobCrawlerError):
    """CSS selector did not match any elements."""
    pass

class BrowserTimeoutError(JobCrawlerError):
    """Browser operation exceeded timeout."""
    pass

# Usage
try:
    job = await crawler.extract_job(url)
except SelectorNotFoundError as e:
    logger.warning(f"Selector failed for {url}: {e}")
    # fallback or retry
except BrowserTimeoutError as e:
    logger.error(f"Browser timeout for {url}: {e}")
    # increase timeout or skip
except JobCrawlerError as e:
    logger.error(f"Unexpected crawler error: {e}", exc_info=True)
    raise

# BAD
except Exception:  # too broad
    pass
```

### Logging

Use `structlog` or standard `logging` module:

```python
import logging

logger = logging.getLogger(__name__)

# Info: normal flow
logger.info("Starting crawl for company", extra={"company": "acme"})

# Warning: recoverable issue
logger.warning("Selector mismatch, retrying", extra={"attempt": 2})

# Error: failure, but process continues
logger.error("Claude API error", extra={"status": 429, "retry_after": 60})

# Critical: process cannot continue
logger.critical("Database corrupted, cannot continue", exc_info=True)
```

### Async/Await Patterns

Use `asyncio` for I/O-bound operations (crawl, API calls):

```python
import asyncio
from typing import Coroutine

# Good: concurrent requests
async def crawl_companies(companies: list[str]) -> list[RawJob]:
    tasks = [crawl_company(company) for company in companies]
    return await asyncio.gather(*tasks, return_exceptions=True)

# Good: resource pooling
async with BrowserPool(max_size=5) as pool:
    tasks = [pool.get().extract_job(url) for url in urls]
    results = await asyncio.gather(*tasks)

# Good: timeout protection
try:
    result = await asyncio.wait_for(api_call(), timeout=30)
except asyncio.TimeoutError:
    logger.error("API call exceeded 30s timeout")
    raise
```

---

## Testing Strategy

### Test Structure

```
tests/
├── unit/              # No I/O, no external calls
│   ├── test_tokenizer.py
│   └── test_db_queries.py
├── integration/        # Multiple modules, real I/O
│   ├── test_crawl_and_preprocess.py
│   └── test_assess_and_store.py
├── e2e/               # Full workflow, real services
│   └── test_full_pipeline.py
└── fixtures/          # Shared mocks and test data
    ├── raw_jobs.json
    ├── mock_claude_responses.json
    └── conftest.py
```

### Unit Testing

**Principle**: Test business logic, mock I/O

```python
import pytest
from unittest.mock import patch, MagicMock
from src.tokenization.counter import TokenCounter

class TestTokenCounter:
    def test_count_tokens_basic(self):
        counter = TokenCounter()
        text = "Hello world"
        count = counter.count(text)
        assert count > 0
        assert isinstance(count, int)

    def test_count_tokens_empty(self):
        counter = TokenCounter()
        count = counter.count("")
        assert count == 0

    @patch("tiktoken.encoding_for_model")
    def test_uses_correct_model(self, mock_encoding):
        counter = TokenCounter(model="gpt-4")
        counter.count("test")
        mock_encoding.assert_called_with("gpt-4")
```

### Integration Testing

**Principle**: Test phase boundaries with real data

```python
import pytest
import asyncio
from src.browser.crawler import JobCrawler
from src.tokenization.cleaner import Cleaner

@pytest.mark.asyncio
async def test_crawl_and_preprocess():
    """Test crawl output feeds into preprocess input."""
    crawler = JobCrawler(config=CrawlerConfig(headless=True))
    raw_job = await crawler.extract_job("https://acme.com/jobs/123")

    cleaner = Cleaner()
    cleaned = cleaner.clean(raw_job.html)

    assert cleaned.token_count < raw_job.html_token_estimate
    assert len(cleaned.text) > 0
    assert "<script>" not in cleaned.text  # tags removed
```

### E2E Testing

**Principle**: Test full workflow with real services (staging)

```python
import pytest
import tempfile
import json
from pathlib import Path
from src.cli import app
from typer.testing import CliRunner

def test_full_workflow_e2e():
    """Test crawl → preprocess → review → assess → export."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock company config
        config_path = Path(tmpdir) / "companies.json"
        config_path.write_text(json.dumps({
            "acme": {"url": "https://acme.com/jobs", "selector": "..."}
        }))

        # Crawl
        result = runner.invoke(app, ["crawl", "--company", "acme", "--dry-run"])
        assert result.exit_code == 0

        # Preprocess
        result = runner.invoke(app, ["preprocess", "--batch", "10"])
        assert result.exit_code == 0

        # Review (non-interactive, auto-approve all)
        result = runner.invoke(app, ["review", "--auto-approve"])
        assert result.exit_code == 0

        # Assess (mock Claude responses)
        result = runner.invoke(app, ["assess", "--mock"])
        assert result.exit_code == 0

        # Export
        result = runner.invoke(app, ["export", "--output", f"{tmpdir}/out.md"])
        assert result.exit_code == 0
        assert Path(f"{tmpdir}/out.md").exists()
```

### Mocking & Fixtures

Use `conftest.py` for shared fixtures:

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.browser.crawler import JobCrawler

@pytest.fixture
def mock_browser():
    """Mock Playwright browser."""
    browser = AsyncMock()
    context = AsyncMock()
    page = AsyncMock()

    browser.new_context.return_value = context
    context.new_page.return_value = page
    page.goto.return_value = None
    page.query_selector.return_value = MagicMock(inner_html="<div>Job Title</div>")

    return browser

@pytest.fixture
def mock_claude_response():
    """Mock Claude API response."""
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "match_score": 85,
                    "strengths": ["Python", "SQL"],
                    "gaps": ["Kubernetes"],
                    "recommendation": "STRONG_MATCH"
                })
            }
        ],
        "usage": {
            "input_tokens": 1400,
            "output_tokens": 350
        }
    }

@pytest.fixture
def raw_job_sample():
    """Sample raw job from crawl phase."""
    return RawJob(
        url="https://acme.com/jobs/123",
        title="Senior Python Engineer",
        company="Acme",
        html="<html>...</html>",
        timestamp=datetime.now()
    )
```

### Coverage Requirements

**Target**: 80%+ line coverage, 70%+ branch coverage

```bash
# Run tests with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Generate HTML report
pytest tests/ --cov=src --cov-report=html
# Open htmlcov/index.html
```

---

## Git & Commit Workflow

### Branch Naming

```
feature/add-slack-integration    # New feature
bugfix/fix-rate-limit-crash      # Bug fix
docs/update-architecture         # Documentation
refactor/simplify-tokenizer      # Code improvement
chore/upgrade-dependencies       # Dependency updates
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
**Scope**: Module name (optional but recommended)
**Subject**: Imperative, 50 chars max, lowercase
**Body**: Why, not what (optional, 72 chars wrap)
**Footer**: References (e.g., Fixes #123)

```bash
# Good commits
git commit -m "feat(cli): add --mock flag to assess command"
git commit -m "fix(llm): handle 429 rate limit with exponential backoff

The assess command would crash on rate limit errors.
Now queues jobs and retries with jitter."
git commit -m "docs(architecture): update scaling considerations

Fixes #45"

# Bad commits
git commit -m "updated stuff"
git commit -m "WIP"
git commit -m "asdasdasd"
```

### Pull Request Process

1. **Create branch**: `git checkout -b feature/my-feature`
2. **Make changes** & test locally:
   ```bash
   uv sync
   pytest tests/ -v
   black src/ tests/
   ruff check src/ tests/
   mypy src/ tests/
   ```
3. **Push & create PR**:
   ```bash
   git push origin feature/my-feature
   # Open PR on GitHub with template
   ```
4. **Automated checks** (CI/CD):
   - Tests pass ✅
   - Linting passes ✅
   - Coverage maintained ✅
   - No secrets detected ✅
5. **Code review** (require 1+ approval)
6. **Squash & merge** to main

### PR Template

```markdown
## Description
Brief explanation of changes.

## Related Issue
Fixes #123

## Type of Change
- [ ] Feature
- [ ] Bug fix
- [ ] Documentation

## Testing
How did you test? Provide commands or screenshots.

## Checklist
- [ ] Lint passes: `ruff check src/`
- [ ] Type check: `mypy src/ tests/`
- [ ] Tests pass: `pytest tests/ -v`
- [ ] Coverage maintained: `--cov-report=term`
- [ ] Docs updated (if applicable)
```

---

## Documentation Standards

### Doc Format

All docs in `docs/` use **GitHub-flavored Markdown**:

```markdown
# Heading 1 (title only, once per file)

## Heading 2 (major sections)

### Heading 3 (subsections)

**Bold** for emphasis
`code` for inline code
```code block``` for multi-line

- Bullet lists
  - Nested bullets

1. Numbered lists
2. For procedures
```

### Code Examples

Always include:
- Function signature (with type hints)
- Brief explanation
- Expected output or side effects

```python
# Example: Extracting jobs from a company
from src.browser.crawler import JobCrawler

crawler = JobCrawler(config=CrawlerConfig(headless=True))
jobs = await crawler.crawl_company("acme")
# Output: list[RawJob] with 50–200 jobs
```

### Table Format

Use pipe-delimited tables with alignment:

```markdown
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Left     | Center   | Right    |
| aligned  | aligned  | aligned  |
```

### Cross-References

Link to other docs:

```markdown
See [CRAWL.md](./CRAWL.md#adding-new-companies) for CSS selector help.
See [docs/STORAGE.md](./STORAGE.md#querying-results) for query examples.
```

### Updating Docs

When code changes:
1. Update relevant phase doc (CRAWL.md, ASSESS.md, etc.)
2. Update examples & code blocks
3. Update `.github/copilot-instructions.md` if top-level command changed
4. Commit with message: `docs: update <module> for <change>`

---

## Deployment Checklist

### Pre-Deployment

- [ ] All tests pass: `pytest tests/ -v --cov=src`
- [ ] Linting passes: `ruff check src/ tests/`
- [ ] Type check passes: `mypy src/ tests/`
- [ ] No secrets in commits: `git log --oneline | grep -i "key\|secret\|password"`
- [ ] All PRs merged to main
- [ ] Bump version in `src/__init__.py` (semantic versioning)
- [ ] Update CHANGELOG.md with new features/fixes

### Staging Deployment

```bash
# Build Docker image
docker build -t ats-showcase:staging .

# Test in container
docker run --env-file .env.staging ats-showcase:staging \
  python -m pytest tests/ -v

# Push to registry
docker tag aats-showcasestaging myregistry/ats-showcase:staging
docker push myregistry/ats-showcase:staging
```

### Production Deployment

```bash
# Tag release
git tag v1.2.0
git push origin v1.2.0

# GitHub Action auto-triggers:
# 1. Build Docker image
# 2. Push to registry: myregistry/ats-showcase:v1.2.0
# 3. Deploy to production (if configured)
# 4. Run smoke tests

# Monitor
docker logs -f ats-showcase-prod
# Check: logs/app.log for errors
# Check: Database health (query count, response time)
# Check: Cost tracking (compare actual vs estimate)
```

### Post-Deployment

- [ ] Verify health check endpoint: `curl http://localhost:8000/health`
- [ ] Test core workflows: `crawl` → `assess` → `export`
- [ ] Check logs for errors: `tail -f logs/app.log`
- [ ] Monitor cost tracking: Compare actual vs estimated cost
- [ ] Set up alerts for: Rate limit errors, database size, API latency

### Rollback

```bash
# If deployment fails:
git revert <commit_hash>
git push origin main
# GitHub Action re-deploys previous version
```

---

## Troubleshooting & Common Errors

### Playwright Browser Issues

**Error**: `BrowserTypeError: Chromium is not installed`

**Solution**:
```bash
# Install system dependencies
sudo apt-get install -y chromium  # Ubuntu/Debian
brew install chromium             # macOS

# Or use Playwright's installer
python -m playwright install chromium
```

### spaCy Model Issues

**Error**: `OSError: [E050] Can't find model 'en_core_web_md'`

**Solution**:
```bash
# Download model
python -m spacy download en_core_web_md

# Or specify in config
export SPACY_MODEL="en_core_web_sm"  # lighter model
python -m src.cli crawl
```

### Claude API Rate Limits

**Error**: `RateLimitError: 429 Too Many Requests`

**Solution**:
- Already handled in batch_processor.py with exponential backoff
- Monitor cost tracking: `cli stats`
- Reduce batch size: `cli assess --batch 5` (instead of 20)

### Database Lock

**Error**: `sqlite3.OperationalError: database is locked`

**Solution**:
```bash
# Check if another process is using DB
lsof | grep ats_playground.db

# Close process or wait
# Or increase timeout
export SQLITE_TIMEOUT=10  # seconds
```

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'src.llm'`

**Solution**:
```bash
# Ensure PYTHONPATH is set
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Or run via module
python -m src.cli --help
# (not python src/cli.py)
```

### Type Check Failures

**Error**: `error: Argument 1 to "extract_job" has incompatible type "str"; expected "URL"`

**Solution**:
- Use proper types for all function arguments
- Run type check locally before committing: `mypy src/ tests/`
- Update function signature or cast value

### Test Failures

**Error**: `AssertionError: assert 0.95 == 0.96`

**Solution**:
- Use `pytest.approx()` for floating-point comparisons
- Use `assert result == expected` for exact matches
- Run `pytest -vv` for detailed output
- Check fixture data in `tests/fixtures/`

---

## Quick Reference: Common Commands

```bash
# Setup
uv sync
python -m spacy download en_core_web_md

# Development
python -m src.cli crawl --help
python -m src.cli assess --mock

# Testing
pytest tests/ -v
pytest tests/ -v --cov=src
pytest tests/test_llm.py -v

# Linting
black src/ tests/
ruff check src/ tests/
mypy src/ tests/

# Git
git checkout -b feature/my-feature
git commit -m "feat(cli): add new command"
git push origin feature/my-feature

# Docker
docker build -t ats-showcase .
docker run -e CLAUDE_API_KEY="sk-..." ats-showcase
```
