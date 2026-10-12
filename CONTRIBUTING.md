# Contributing to ATS Playground

We appreciate your interest in contributing to the ATS Playground project! This guide explains how to set up your development environment, submit contributions, and maintain our high standards for code quality and security.

## Table of Contents

- [Getting Started](#getting-started)
- [Understanding Agent Roles](#understanding-agent-roles)
- [GitHub Copilot CLI Setup](#github-copilot-cli-setup)
- [Development Workflow](#development-workflow)
- [Code Quality Standards](#code-quality-standards)
- [Security Guidelines](#security-guidelines)
- [Testing Requirements](#testing-requirements)
- [Commit and PR Guidelines](#commit-and-pr-guidelines)
- [Code Review Process](#code-review-process)

## Getting Started

### Prerequisites

- Python 3.11 or later
- Git and GitHub CLI (`gh`)
- `uv` package manager (recommended) or pip/venv

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/pluto-atom-4/ats-showcase.git
cd ats-showcase

# Install dependencies
uv sync

# Download spaCy model
uv run python -m spacy download en_core_web_md

# Install Playwright browsers
uv run playwright install

# Create .env from template
cp .env.example .env
# Edit .env and add ANTHROPIC_API_KEY

# Initialize database
uv run python src/storage/db.py --init

# Run tests to verify setup
uv run pytest tests/ -v
```

### Verify Your Setup

```bash
# Check Python version
python --version  # Should be 3.11+

# Verify dependencies
uv pip list

# Run quick test
uv run pytest tests/test_storage.py::test_database_initialization -v

# Check code quality tools
black --version
ruff --version
mypy --version
```

## Understanding Agent Roles

ATS Playground uses a **multi-agent coordination model** to organize development work. Read [AGENTS.md](./AGENTS.md) to understand:

- **Architect/Planner**: Designs features, writes tasks.md, reads DESIGN.md
- **Builder/Implementer**: Writes production code, implements features from tasks.md
- **Reviewer/Tester**: Runs tests, verifies code quality, validates against tests

**Key Concept**: Work flows through handovers: Architect → tasks.md → Builder → Pull Request → Reviewer → Merge

See [AGENTS.md](./AGENTS.md) for:
- Detailed role responsibilities and boundaries
- Handover protocol and escalation rules (Three-Strike Rule)
- Permission matrix (what each agent can access)
- State locking for sub-agent recovery

This structure keeps work organized and prevents bottlenecks when multiple agents collaborate.

## GitHub Copilot CLI Setup

### What is the Plugin?

ATS Playground provides a GitHub Copilot CLI plugin with 3 reusable skills for automating job assessment workflows. These skills extend GitHub Copilot CLI sessions with ATS-specific capabilities.

**Available Skills:**
- `/ats-nlp-setup` — Configure NLP models and spaCy environment
- `/ats-preprocessing` — Preprocess job postings locally with cost estimation (80–90% savings)
- `/ats-assessment` — Assess job-to-CV matches using Claude 3.5 Sonnet

### Prerequisites

- GitHub Copilot CLI (v1.0.51+) — Download from [GitHub Copilot CLI releases](https://github.com/github/copilot-cli/releases)
- Python 3.11+ with ATS Playground installed (see [Getting Started](#setup-development-environment))
- GitHub authentication: `gh auth status`

### Install the Plugin

```bash
# Install the ATS Playground plugin
gh copilot -- plugin install pluto-atom-4/copilot-plugin-ats-playground

# Verify installation
gh copilot -- plugin list
# Output: ats-showcase (v1.0.0)
```

### Using the Plugin

Start an interactive Copilot CLI session and invoke the skills:

```bash
# Start a session
gh copilot

# In the interactive prompt, use skills:
> /ats-nlp-setup --validate
# Output: ✅ spaCy model 'en_core_web_md' is installed and valid

> /ats-preprocessing --show-estimates
# Output: Processing jobs... 650 tokens → $0.002 (89% savings)

> /ats-assessment --cv cv.json --jobs jobs.json --min-score 75
# Output: Assessing 10 jobs... [results with scores and recommendations]
```

### Skill Details

#### `/ats-nlp-setup` — NLP Configuration

Configure and validate spaCy models used for preprocessing.

**Options:**
- `--validate` — Validate installed model
- `--model MODEL` — Specify model (default: en_core_web_md)
- `--list-models` — Show available models

**Example:**
```bash
> /ats-nlp-setup --validate
✅ spaCy model 'en_core_web_md' is installed
  Path: /usr/local/lib/python3.11/site-packages/en_core_web_md
  Components: tokenizer, tagger, parser, lemmatizer
```

---

#### `/ats-preprocessing` — Local Job Preprocessing

Clean and chunk job postings locally before assessment. Estimates cost and saves 80–90% vs raw HTML.

**Options:**
- `--source FILE` — Input jobs JSON file (default: jobs.json)
- `--show-estimates` — Display token counts and cost estimates
- `--interactive` — Prompt for review before processing
- `--save-clean` — Save cleaned text to files

**Example:**
```bash
> /ats-preprocessing --show-estimates
Processing 10 jobs...

Job 1: Senior Software Engineer
  Raw HTML: 6,000 tokens
  Clean text: 650 tokens
  Estimated cost: $0.002

Summary:
  Total tokens: 6,500
  Estimated cost: $0.02
  💾 Savings: 89% ($0.18 saved per 100 jobs)
```

---

#### `/ats-assessment` — Job-to-CV Assessment

Evaluate job matches using Claude 3.5 Sonnet with local preprocessing. Scores jobs by technical skills, seniority, location, and recommendations.

**Options:**
- `--cv FILE` — CV file (JSON or markdown)
- `--jobs FILE` — Jobs JSON file
- `--min-score NUM` — Filter by minimum score (0-100)
- `--show-reasoning` — Show detailed scoring reasoning
- `--output-dir DIR` — Output directory for reports

**Example:**
```bash
> /ats-assessment --cv my-cv.json --jobs jobs.json --min-score 75
Assessing 10 jobs...

Job 1: Senior Software Engineer @ Google
  Overall match: 85/100 ✅ GOOD FIT
  Technical skills: 90/100 (Python, Go, AWS match)
  Seniority: 80/100 (8 years vs 10+ required)
  Location: 75/100 (Relocation available)

  Recommendation: ✅ APPLY NOW - Good fit
  Cost: $0.002 (estimated: $0.002) ✅

Report saved: assessments/assessment-20260526.md
```

### Troubleshooting

**Plugin not found after installation?**
```bash
# Verify installation
gh copilot -- plugin list

# Try uninstalling and reinstalling
gh copilot -- plugin uninstall ats-showcase
gh copilot -- plugin install pluto-atom-4/copilot-plugin-ats-playground
```

**Skill commands not working in session?**
```bash
# Ensure you're in an interactive Copilot CLI session
gh copilot

# Try asking Copilot for help
> /ats-preprocessing --help
```

**Model not found error?**
```bash
# Install the NLP model
> /ats-nlp-setup --validate
# This will auto-install if missing

# Or install manually
python -m spacy download en_core_web_md
```

### Related Resources

- **Plugin Repository**: https://github.com/pluto-atom-4/copilot-plugin-ats-playground
- **CLAUDE.md**: Detailed developer guide with skill examples
- **docs/PREPROCESS.md**: Technical preprocessing details
- **docs/ASSESS.md**: Assessment algorithm documentation

---

## Development Workflow

### Create a Feature Branch

```bash
# Update main branch
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

**Branch naming conventions**:
- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation changes
- `refactor/description` - Code refactoring
- `test/description` - Test improvements

### Local Development

```bash
# Make your changes in the appropriate module
# Example: src/browser/crawler.py for crawling features

# Keep code formatted while developing
black src/ tests/

# Check for linting issues
ruff check src/ tests/

# Run type checking
mypy src/ tests/

# Run tests for your changes
uv run pytest tests/test_crawler.py -v
```

### Run Full Quality Checks

```bash
# Format all code
black src/ tests/

# Lint all code
ruff check src/ tests/ --fix

# Type check all code
mypy src/ tests/

# Run all tests with coverage
uv run pytest tests/ -v --cov=src --cov-report=term-missing

# Run security scan
uv run bandit -r src/
```

## Code Quality Standards

### Pre-commit Hooks (Recommended)

Automatically enforce code quality on every commit:

```bash
# Install pre-commit hooks (1 minute)
python -m src.setup.setup_precommit

# Hooks will run automatically on git commit:
# ✅ trailing-whitespace - Removes trailing spaces
# ✅ end-of-file-fixer - Ensures single final newline
# ✅ black - Auto-formats code (line-length: 100)
# ✅ ruff - Auto-fixes imports & safe linting issues
# ❌ mypy - Type checking (requires manual fixes)
# ❌ pytest - Unit tests (requires manual fixes)
```

**Performance**: Full pre-commit run completes in <60 seconds

**Skip hooks when needed**:
```bash
SKIP=mypy,pytest git commit -m "WIP: feature in progress"
git commit --no-verify -m "Emergency hotfix" # (use sparingly)
```

**Details**: See [docs/QUALITY-ASSURANCE.md](./docs/QUALITY-ASSURANCE.md) for complete hook reference, troubleshooting, and performance tips.

### Type Hints (Required)

All functions and methods must have complete type hints:

```python
from typing import Optional, List, Dict
from pydantic import BaseModel

def process_jobs(jobs: List[Dict[str, str]]) -> Optional[str]:
    """Process a list of job postings.

    Args:
        jobs: List of job posting dictionaries

    Returns:
        Processed result or None if empty
    """
    if not jobs:
        return None
    return f"Processed {len(jobs)} jobs"
```

### Docstrings (Required)

All modules, classes, and functions must have docstrings:

```python
"""Module for processing job postings with Playwright.

This module handles:
- Browser automation using Playwright
- CSS selector management
- Job data extraction
"""

class JobCrawler:
    """Crawl job postings from career pages.

    Attributes:
        browser: Playwright browser instance
        timeout: Request timeout in seconds
    """

    async def crawl(self, url: str) -> List[Dict]:
        """Crawl jobs from a single URL.

        Args:
            url: Career page URL to crawl

        Returns:
            List of extracted job dictionaries

        Raises:
            TimeoutError: If request exceeds timeout
            ValueError: If URL is invalid
        """
        pass
```

### Code Style

- **Formatter**: Black (100-character line length)
- **Linter**: Ruff (flake8-compatible)
- **Type Checker**: Mypy (non-strict by default; `run-local-ci.sh --strict` available)
- **Sort Imports**: isort

```bash
# Auto-format code
black src/ tests/

# Auto-fix linting issues
ruff check src/ tests/ --fix

# Check (don't fix) type issues
mypy src/ tests/
```

### Naming Conventions

- **Functions**: `snake_case` - `extract_jobs()`, `process_job_data()`
- **Classes**: `PascalCase` - `JobCrawler`, `PreprocessedJob`
- **Constants**: `UPPER_SNAKE_CASE` - `MAX_RETRIES`, `DEFAULT_TIMEOUT`
- **Private members**: `_leading_underscore` - `_validate_input()`, `_internal_cache`

## Security Guidelines

### Never Commit Secrets

❌ **DO NOT**:
```python
# Never hardcode API keys
api_key = "sk-ant-abc123xyz"

# Never hardcode database credentials
password = "super_secret_password"

# Never commit .env files
```

✅ **DO**:
```python
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")
# Handle missing key gracefully
if not api_key:
    raise ValueError("ANTHROPIC_API_KEY not set in .env")
```

### Input Validation

Always validate user input using Pydantic models:

```python
from pydantic import BaseModel, Field

class JobPosting(BaseModel):
    """Validated job posting data."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=10)
    company: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., pattern=r"^https?://")
```

### SQL Injection Prevention

Always use parameterized queries with SQLite:

```python
# ✅ Safe: Parameterized query
cursor.execute(
    "SELECT * FROM jobs WHERE title = ? AND status = ?",
    (job_title, "active")
)

# ❌ Unsafe: String concatenation
query = f"SELECT * FROM jobs WHERE title = '{job_title}'"
cursor.execute(query)  # Vulnerable to SQL injection!
```

### Error Messages

Don't expose sensitive information in error messages:

```python
# ❌ Too detailed, exposes system info
except Exception as e:
    print(f"Database error: {e}")  # User might see SQL, credentials, etc.

# ✅ User-friendly message
except Exception as e:
    logger.error(f"Database error: {e}")  # Log full error internally
    raise ValueError("Failed to retrieve jobs. Please try again.")
```

### Security Review Checklist

Before submitting a PR, verify:

- [ ] No secrets committed (API keys, passwords, tokens)
- [ ] No hardcoded credentials in code
- [ ] All user input validated with Pydantic models
- [ ] Database queries use parameterized statements
- [ ] Error messages don't expose sensitive information
- [ ] Dependencies have no known vulnerabilities
- [ ] No new dangerous imports (e.g., `eval`, `exec`)

## Testing Requirements

### Minimum Coverage

All new code must have tests with minimum 80% coverage:

```bash
# Run tests with coverage report
uv run pytest tests/ -v --cov=src --cov-report=term-missing

# Generate HTML coverage report
uv run pytest tests/ --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

### Test Structure

Tests are organized by module:

```
tests/
├── conftest.py              # Shared fixtures
├── test_browser.py          # browser/ module tests
├── test_parsers.py          # parsers/ module tests
├── test_tokenization.py     # tokenization/ module tests
├── test_models.py           # models/ module tests
├── test_llm.py              # llm/ module tests
├── test_verification.py     # verification/ module tests
└── test_storage.py          # storage/ module tests
```

### Writing Tests

```python
import pytest
from src.models import JobPosting

@pytest.fixture
def sample_job(sample_job_data):
    """Fixture providing a valid JobPosting."""
    return JobPosting(**sample_job_data)

def test_job_posting_validation(sample_job):
    """Test JobPosting model validation."""
    assert sample_job.title
    assert sample_job.url.startswith("http")

def test_job_posting_invalid_url():
    """Test that invalid URLs are rejected."""
    with pytest.raises(ValueError):
        JobPosting(
            title="Test Job",
            description="Test description",
            company="Test Co",
            url="not-a-url"
        )

@pytest.mark.asyncio
async def test_async_crawler(temp_db):
    """Test async crawler function."""
    result = await crawler.crawl("https://example.com")
    assert isinstance(result, list)
```

## Commit and PR Guidelines

### Commit Messages

Use clear, descriptive commit messages following conventional commits:

```
<type>: <description>

<optional longer explanation>

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

**Types**:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `style:` - Formatting (no logic change)
- `refactor:` - Code restructuring (no logic change)
- `test:` - Test changes
- `chore:` - Build, config, dependencies

**Examples**:

```
feat: add semantic chunking for job descriptions

- Implement sentence-boundary chunk splitting
- Add configurable chunk size (default 400 tokens)
- Add tests for edge cases (empty text, single sentence)
- Update PREPROCESS.md documentation

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

```
fix: prevent SQL injection in job search query

- Replace string concatenation with parameterized queries
- Add tests for special characters in search terms
- Document secure query pattern in STORAGE.md

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

### Pull Request Process

1. **Create PR from feature branch**:
   ```bash
   # Push your branch
   git push origin feature/your-feature-name

   # Create PR (automatically opens in browser)
   gh pr create --web
   ```

2. **Fill out PR template**:
   - Clear description of changes
   - Link to related issue
   - List of changes made
   - Security checklist items verified
   - Screenshot/examples if applicable

3. **Ensure all checks pass**:
   - Tests pass (100% coverage for new code)
   - Linting passes (ruff, black)
   - Type checking passes (mypy)
   - Security scan passes (bandit, CodeQL)

4. **Respond to review comments**:
   - Address all feedback
   - Commit additional changes (don't force-push)
   - Request re-review when ready

5. **Merge when approved**:
   - Requires 2 approvals
   - All checks must pass
   - Branch must be up-to-date with main

## Code Review Process

### What Reviewers Look For

- ✅ **Business Logic**: Does it solve the problem correctly?
- ✅ **Code Quality**: Does it follow our standards?
- ✅ **Testing**: Is it well-tested?
- ✅ **Security**: Are secrets protected? Are inputs validated?
- ✅ **Performance**: Are there any efficiency concerns?
- ✅ **Documentation**: Are docstrings and type hints present?

### Code Review Checklist (For Reviewers)

- [ ] Code follows style guide (black, ruff, mypy)
- [ ] Tests present and >80% coverage
- [ ] No security issues (secrets, injection, validation)
- [ ] Type hints complete
- [ ] Docstrings present and clear
- [ ] Related documentation updated
- [ ] Commit messages clear and conventional

## Questions?

- Check [README.md](README.md) for project overview
- Check [docs/](docs/) for phase-specific guides
- Check [SECURITY.md](SECURITY.md) for security policies
- Open an issue for questions or suggestions

---

**Thank you for contributing to ATS Playground!** 🚀

Your contributions help make this project better for everyone.
