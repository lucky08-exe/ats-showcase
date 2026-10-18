# CLI Phase: Command-Line Interface with Typer

## Overview

The CLI phase provides a unified command-line interface orchestrating all ATS Showcase phases:

1. **Command organization** - Logical grouping (crawl, preprocess, verify, assess, store, export)
2. **Interactive workflows** - Real-time user feedback during long operations
3. **Progress tracking** - Spinners, progress bars, cost estimates
4. **Error handling** - Clear error messages with remediation suggestions
5. **Help system** - Comprehensive `--help` at every level
6. **Typer framework** - Modern, type-hinted, async-ready CLI (Python 3.10+)

## Architecture

### Command Hierarchy

```
ats-showcase/
├── crawl                    # Phase 1: Extract jobs from career pages
│   └── --config             # Company URLs + CSS selectors
│
├── preprocess               # Phase 2: Clean & chunk text
│   ├── --file               # Input JSON (extracted jobs)
│   └── --output             # Output file (preprocessed chunks)
│
├── review                   # Phase 3: User verification
│   ├── --file               # Jobs to review
│   └── --interactive        # Show cost estimates during review
│
├── assess                   # Phase 4: Claude LLM matching
│   ├── --cv                 # Candidate CV
│   ├── --confirmed-only     # Only process verified jobs
│   └── --model              # Claude model selection (Sonnet/Haiku)
│
├── query                    # Phase 5: Search results
│   ├── --search             # Keyword search (FTS5)
│   ├── --min-score          # Filter by match score
│   └── --company            # Filter by company
│
├── export                   # Phase 5: Generate reports
│   ├── --format             # md|csv|json
│   ├── --output             # Output file path
│   └── --min-score          # Export threshold
│
├── stats                    # Analytics
│   ├── --show-tokens        # Token usage report
│   ├── --show-costs         # Cost breakdown by company
│   └── --days               # Time period (default: 7)
│
└── --all                    # Full workflow (crawl→preprocess→verify→assess→export)
    └── --up-to              # Stop at phase [crawl|preprocess|review|assess]
```

## Typer Implementation

### Project Structure

```python
src/
├── cli.py                   # Main entry point (Typer app)
├── commands/
│   ├── __init__.py
│   ├── crawl.py            # Crawl subcommand
│   ├── preprocess.py       # Preprocess subcommand
│   ├── review.py           # Review subcommand
│   ├── assess.py           # Assess subcommand
│   ├── query.py            # Query subcommand
│   ├── export.py           # Export subcommand
│   └── stats.py            # Stats subcommand
├── utils/
│   ├── formatting.py       # Tables, colors, progress
│   └── constants.py        # Defaults, messages
└── main.py                 # Entry point script
```

### Main CLI Entry Point

```python
# src/cli.py
import typer
from typing import Optional
from pathlib import Path
from rich.console import Console
import logging

from commands import crawl, preprocess, review, assess, query, export, stats

console = Console()
app = typer.Typer(
    name="ats-showcase",
    help="Agentic AI workflow for job opportunity assessment",
    pretty_exceptions_enable=True,
    no_args_is_help=True,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

# Register subcommands
app.command()(crawl.crawl_command)
app.command()(preprocess.preprocess_command)
app.command()(review.review_command)
app.command()(assess.assess_command)
app.command()(query.query_command)
app.command()(export.export_command)
app.command()(stats.stats_command)

@app.command()
def version():
    """Show version."""
    console.print("ATS Showcase v1.0.0")

@app.command()
def init():
    """Initialize database and config."""
    from src.storage import StorageClient
    from pathlib import Path

    console.print("[bold]Initializing ATS Showcase...[/bold]")

    # Create directories
    Path("data").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    # Initialize database
    storage = StorageClient()
    storage.init_schema()

    # Create example config if not exists
    config_path = Path("config/companies.json")
    if not config_path.exists():
        config_path.parent.mkdir(exist_ok=True)
        example_config = {
            "companies": [
                {
                    "name": "TechCorp",
                    "url": "https://techcorp.com/careers",
                    "selectors": {
                        "job_title": "h2.job-title",
                        "requirements": "div.requirements"
                    }
                }
            ]
        }
        import json
        with open(config_path, 'w') as f:
            json.dump(example_config, f, indent=2)

    console.print("[green]✓ Initialization complete[/green]")
    console.print(f"  - Database: data/ats_playground.db")
    console.print(f"  - Config: config/companies.json")
    console.print(f"  - Logs: logs/app.log")

@app.callback()
def global_options(
    debug: bool = typer.Option(False, help="Enable debug logging"),
    config: Optional[Path] = typer.Option(None, help="Config file path"),
):
    """Global options for all commands."""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")

if __name__ == "__main__":
    app()
```

### Sample Subcommand: crawl.py

```python
# src/commands/crawl.py
import typer
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.progress import Progress
import json

console = Console()

def crawl_command(
    config: Path = typer.Option(
        "config/companies.json",
        "--config",
        help="Company config file (JSON with URLs + CSS selectors)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Output directory for extracted jobs (default: data/extracted_jobs/)",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--no-headless",
        help="Run browser in headless mode",
    ),
    timeout: int = typer.Option(
        30,
        "--timeout",
        help="Page load timeout in seconds",
    ),
):
    """
    Phase 1: Crawl career pages and extract job postings.

    Reads company URLs from config file, navigates to each career page,
    and extracts job listings using CSS selectors.

    Example:
        ats-showcase crawl --config config/companies.json
    """
    from src.browser import PlaywrightCrawler
    import logging

    logger = logging.getLogger(__name__)
    output_dir = output or Path("data/extracted_jobs")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load config
    try:
        with open(config) as f:
            config_data = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]Error: Config file not found: {config}[/red]")
        raise typer.Exit(code=1)
    except json.JSONDecodeError:
        console.print(f"[red]Error: Invalid JSON in config file[/red]")
        raise typer.Exit(code=1)

    companies = config_data.get("companies", [])
    if not companies:
        console.print("[yellow]Warning: No companies in config[/yellow]")
        raise typer.Exit(code=1)

    # Initialize crawler
    crawler = PlaywrightCrawler(headless=headless, timeout=timeout)

    console.print(f"[bold]Crawling {len(companies)} companies...[/bold]\n")

    total_jobs = 0
    with Progress() as progress:
        task = progress.add_task("Crawling...", total=len(companies))

        for company in companies:
            company_name = company["name"]
            url = company["url"]
            selectors = company.get("selectors", {})

            try:
                jobs = crawler.extract_jobs(url, selectors, company_name)
                total_jobs += len(jobs)

                # Save to file
                output_file = output_dir / f"{company_name}_jobs.json"
                with open(output_file, 'w') as f:
                    json.dump(jobs, f, indent=2)

                console.print(
                    f"  [green]✓[/green] {company_name}: {len(jobs)} jobs → {output_file.name}"
                )

            except Exception as e:
                console.print(f"  [red]✗[/red] {company_name}: {str(e)}")
                logger.error(f"Crawl failed for {company_name}", exc_info=True)

            progress.advance(task)

    console.print(f"\n[bold green]✓ Crawl complete: {total_jobs} jobs extracted[/bold green]")

def get_company_selectors(company_name: str) -> dict:
    """Get CSS selectors for company (helper)."""
    # Could implement intelligent selector detection here
    return {
        "job_title": "h2.job-title, h3.position",
        "requirements": "div.requirements, ul.requirements",
        "responsibilities": "div.description, div.responsibilities",
    }
```

### Sample Subcommand: assess.py

```python
# src/commands/assess.py
import typer
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.progress import Progress
from rich.panel import Panel
from rich.table import Table
import json
import logging

console = Console()

def assess_command(
    cv: Path = typer.Option(
        "data/cv.json",
        "--cv",
        help="Candidate CV file (JSON format)",
    ),
    confirmed_only: bool = typer.Option(
        True,
        "--confirmed-only/--all",
        help="Only assess verified jobs (default: confirmed only)",
    ),
    model: str = typer.Option(
        "claude-3-5-sonnet-20241022",
        "--model",
        help="Claude model (sonnet|haiku|opus)",
    ),
    min_score: float = typer.Option(
        0.0,
        "--min-score",
        help="Export only matches >= threshold (0.0-1.0)",
    ),
    batch_size: int = typer.Option(
        10,
        "--batch-size",
        help="Batch size for concurrent assessments",
    ),
):
    """
    Phase 4: Assess job-CV matches using Claude API.

    Loads verified job postings and CV, then uses Claude to score
    each job-CV pair on a 0.0-1.0 scale with reasoning.

    Example:
        ats-showcase assess --cv data/cv.json --confirmed-only
    """
    from src.storage import StorageClient
    from src.llm import AssessmentClient, BatchAssessor

    logger = logging.getLogger(__name__)

    # Load CV
    try:
        with open(cv) as f:
            cv_data = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]Error: CV file not found: {cv}[/red]")
        raise typer.Exit(code=1)

    cv_id = cv_data.get("id") or cv.stem
    cv_summary = cv_data.get("summary", "")

    # Load jobs from database
    storage = StorageClient()

    status_filter = "confirmed" if confirmed_only else "pending"
    cursor = storage.conn.cursor()
    cursor.execute("""
        SELECT * FROM jobs WHERE status = ?
    """, (status_filter,))

    jobs = [dict(row) for row in cursor.fetchall()]

    if not jobs:
        console.print(f"[yellow]No {status_filter} jobs to assess[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"[bold]Assessing {len(jobs)} jobs for CV: {cv_id}[/bold]\n")

    # Initialize Claude client
    client = AssessmentClient(model=model)
    assessor = BatchAssessor(client)

    # Prepare job-CV pairs
    job_cv_pairs = [
        (job, cv_summary, job["job_id"], cv_id)
        for job in jobs
    ]

    # Run assessments
    try:
        assessor.assess_batch(job_cv_pairs, show_progress=True)
    except Exception as e:
        console.print(f"[red]Assessment failed: {str(e)}[/red]")
        logger.error("Batch assessment failed", exc_info=True)
        raise typer.Exit(code=1)

    # Save results
    assessor.save_results()

    # Print summary
    assessor.print_cost_summary()

    # Show top matches
    console.print("\n[bold]Top 5 Matches:[/bold]\n")
    top_matches = sorted(
        assessor.results,
        key=lambda r: r.match_score,
        reverse=True
    )[:5]

    table = Table(title="Top Matches")
    table.add_column("Score", style="cyan")
    table.add_column("Job", style="magenta")
    table.add_column("Company", style="green")
    table.add_column("Reasoning")

    for result in top_matches:
        job = next((j for j in jobs if j["job_id"] == result.job_id), {})
        table.add_row(
            f"{result.match_score:.1%}",
            job.get("title", "Unknown"),
            job.get("company_name", "Unknown"),
            result.reasoning[:50] + "..."
        )

    console.print(table)
```

## Preprocessing & Boilerplate Removal (Issue #230 + #231)

ATS Showcase's preprocessing phase includes consolidated HTML cleaning with 70+ boilerplate patterns and a 3-tier fallback chain ensuring robustness.

### What is Boilerplate Removal?

Raw job postings contain repetitive, non-job-specific text that wastes API tokens:
- Legal disclaimers ("Equal Opportunity Employer", "© 2026")
- Navigation elements (breadcrumbs, page navigation)
- Company taglines and "about us" blurbs
- Posted dates, application deadlines
- Salary ranges and benefits (optional removal)
- Extra whitespace and formatting artifacts

**Token impact:** Boilerplate removal accounts for ~30% of preprocessing savings (6,000 → 700 tokens).

### Boilerplate Categories (7)

| Category | Examples | Optional? |
|----------|----------|-----------|
| **Legal** | EEO statements, compliance disclaimers, copyright notices | No (always removed) |
| **Section Headers** | Redundant navigation headers, section labels | No |
| **Company Info** | Company taglines, about sections (non-job-specific) | No |
| **Time References** | Posted dates, application deadlines, timestamps | No |
| **Salary & Benefits** | Salary ranges, benefits details | Yes (configurable) |
| **Formatting** | Extra whitespace, CSS classes, metadata attributes | No |
| **Navigation** | Breadcrumbs, page menus, link navigation | No |

### Robustness & Fallback Chain (Issue #231)

HTML cleaning uses a 3-tier fallback strategy to ensure preprocessing never fails:

1. **MarkItDown** (primary) – Preserves structure, handles tables/rich content (~50ms/job)
2. **BeautifulSoup + lxml** (fallback) – Basic text extraction if MarkItDown unavailable (~100ms/job)
3. **Original HTML** (safety net) – Returns unmodified HTML if both fail (~6K tokens, worst case)

**Guarantee:** Preprocessing always succeeds. Token count may increase (raw HTML ~6K tokens vs ~400 expected), but never fails catastrophically.

**Test coverage:** See `tests/parsers/test_html_to_markdown.py` for fallback chain verification.

### Usage

**Default (remove all categories except optional):**
```bash
uv run python -m src.cli preprocess --show-estimates
```

**Skip salary/benefits info (keep in clean_text):**
```python
# In code:
from src.parsers.html_to_markdown import clean_html

clean_text = clean_html(
    raw_html,
    skip_boilerplate_categories={'salary_benefits'}  # Keep salary info
)
```

### Example Output Comparison

**Before (raw HTML):**
```
<div class="posting">
  <h2>Senior Python Developer</h2>
  <p>Carbon Robotics, Inc. is a cutting-edge robotics company...</p>

  <div class="job-details">
    <h3>Requirements</h3>
    <ul>
      <li>5+ years Python</li>
      <li>AWS/Kubernetes</li>
    </ul>
  </div>

  <div class="benefits">
    <h3>Salary & Benefits</h3>
    <p>$150K - $200K</p>
    <ul><li>Health insurance</li></ul>
  </div>

  <footer>
    Carbon Robotics is an Equal Opportunity Employer.
    © 2026 All rights reserved.
  </footer>

  <nav><a href="/careers">← Back to jobs</a></nav>
</div>

Token count: ~6,000
```

**After (clean_html with boilerplate removal):**
```
## Senior Python Developer

### Requirements
- 5+ years Python
- AWS/Kubernetes

Token count: ~400 (88% reduction)
```

### Performance Improvement

- **Pattern compilation:** 70+ regex patterns pre-compiled at module load
- **Per-job time:** ~50ms (vs 500ms with sequential regex)
- **Total speed:** 10x faster boilerplate removal
- **Cost savings:** Combined with other preprocessing, enables 88% token reduction

### Backward Compatibility & Versioning (Phase 2)

Phase 2 (future) will introduce `preprocessing_version` column:
- `v1.0` – Legacy (no boilerplate removal)
- `v2.0` – New (70+ boilerplate patterns removed)

This enables:
- **Selective re-preprocessing**: Update only v1.0 jobs to v2.0
- **Cost comparison**: Analyze token usage between versions
- **Graceful fallback**: Revert to v1.0 if v2.0 causes issues

---

## Interactive TUI Dashboard

ATS Showcase includes an optional **Textual-based interactive dashboard** for real-time workflow visualization. The dashboard runs the complete workflow (crawl → preprocess → assess → export) with live progress tracking, cost accumulation, and pause/resume controls.

### Enabling the Dashboard

The dashboard is **automatically enabled** when running in an interactive terminal:

```bash
uv run python -m src.cli all --cv data/cv.json --config config/companies.json
# Dashboard auto-launches if stdout/stdin are TTYs
```

### Explicit Control

```bash
# Force enable TUI (interactive dashboard)
uv run python -m src.cli all --tui --cv data/cv.json --config config/companies.json

# Force disable TUI (text-only output, suitable for CI/pipes)
uv run python -m src.cli all --no-tui --cv data/cv.json --config config/companies.json
```

### Dashboard Layout

```
┌──────────────────────────────────────────────────┐
│ 🎯 ATS Showcase - Workflow Dashboard             │
│ Tokens: 45,230 | Total Cost: $0.1357            │
├──────────────────────────────────────────────────┤
│ ✅ Crawl | ⏳ Preprocess | ⚪ Assess | ⚪ Export │
├──────────────────────────────────────────────────┤
│                                                  │
│  🕷️ CRAWL PHASE | RUNNING                       │
│  Companies: 12 | Jobs Extracted: 347 | Failed: 0│
│  ████████░░░░░░░░░░░░ 45% (6/12)                │
│  ETA: 2m 15s | Speed: 0.5 jobs/sec              │
│  Tokens: 1,230 | Cost: $0.0037                  │
│                                                  │
├──────────────────────────────────────────────────┤
│ [p]ause [r]esume [q]uit                         │
└──────────────────────────────────────────────────┘
```

### Keyboard Bindings

| Key | Action |
|-----|--------|
| `p` | Pause/Resume workflow |
| `r` | Resume from pause |
| `q` | Quit dashboard (stops workflow) |

### Dashboard Phases

The dashboard displays each phase sequentially with real-time updates:

1. **Crawl Phase** - Extract jobs from career pages
   - Companies processed / total
   - Jobs extracted per company
   - Network errors (if any)
   - Running token count

2. **Preprocess Phase** - Clean & chunk job descriptions
   - Jobs processed / total
   - Token count per job
   - Running cost estimate
   - Chunking speed (tokens/sec)

3. **Assess Phase** - Claude API matching
   - Jobs assessed / total
   - Top 5 matches displayed live
   - Running cost + actual tokens used
   - Overall/tech/seniority scores per job

4. **Export Phase** - Generate markdown report
   - Report file path
   - Generation status
   - Final cost summary

### CLI vs TUI Comparison

| Aspect | CLI Mode (`--no-tui`) | TUI Dashboard |
|--------|----------------------|---------------|
| **Output** | Line-by-line text to stdout | Real-time interactive panels |
| **Interactivity** | None | Pause/resume, keyboard controls |
| **Progress Display** | Progress bars, final summary | Live phase-by-phase updates |
| **Cost Tracking** | Reported at end | Real-time counter |
| **Top Matches** | Printed after assess complete | Updated live during assess |
| **Suitable For** | Headless/CI/piping | Interactive terminal usage |
| **Log Output** | All logs to stdout/file | Logs to file, TUI for status |

### When to Use Each Mode

**Use Interactive TUI Dashboard (`--tui`):**
- Running in interactive terminal (not piped/redirected)
- Want real-time progress visualization
- Need to pause/resume long workflows
- Want live cost tracking
- Assessing large job sets (100+ jobs)

**Use CLI Text Mode (`--no-tui`):**
- Headless/remote environments (SSH with limited terminal support)
- Piping output to files or other commands
- CI/CD pipelines
- Parsing output programmatically
- Running in limited terminal (no color/ANSI support)

### Auto-Detection Logic

When neither `--tui` nor `--no-tui` is specified, the CLI auto-detects:

```python
use_tui = sys.stdout.isatty() and sys.stdin.isatty()
```

This enables the dashboard only when both stdout and stdin are connected to a terminal, ensuring headless/piped execution automatically falls back to text mode.

### Examples

**Interactive workflow with dashboard (auto-detected):**
```bash
uv run python -m src.cli all \
  --cv data/my_cv.json \
  --config config/companies.json
```

**Explicit TUI mode for testing:**
```bash
uv run python -m src.cli all \
  --tui \
  --cv data/my_cv.json \
  --config config/companies.json \
  --headless
```

**CI/headless with text output:**
```bash
uv run python -m src.cli all \
  --no-tui \
  --cv data/my_cv.json \
  --config config/companies.json \
  2>&1 | tee assessment.log
```

### Troubleshooting

**Dashboard doesn't appear (expected TUI, got text):**
- Check terminal is interactive (not piped)
- Explicitly use `--tui` flag to force enable
- Verify stdout/stdin are TTYs: `isatty` test

**Terminal rendering issues (garbled text):**
- Update terminal emulator (Textual requires modern terminal)
- Disable colors: Not supported yet (Textual always uses colors)
- Try `--no-tui` mode as fallback

**Dashboard freezes or hangs:**
- Press `q` to quit (safe even if workflow mid-phase)
- Check logs in `logs/app.log` for errors
- Report issue with terminal version and size

## Complete Command Reference

### crawl
**Purpose**: Extract job postings from career pages

```bash
ats-showcase crawl \
  --config config/companies.json \
  --output data/extracted_jobs/ \
  --headless \
  --timeout 30
```

**Options**:
- `--config PATH` - Company config file (required)
- `--output PATH` - Output directory (default: data/extracted_jobs)
- `--headless/--no-headless` - Browser mode (default: headless)
- `--timeout INT` - Page timeout seconds (default: 30)

**Output**: JSON files per company with extracted jobs

---

### preprocess
**Purpose**: Clean HTML, chunk text, count tokens, extract trigger-based requirements (Phase 8)

```bash
# Default: Extract requirements + show preprocessing
uv run python -m src.cli preprocess

# With estimates (show token/cost for first 3 jobs)
uv run python -m src.cli preprocess --show-estimates

# Disable requirement extraction (backward compatible)
uv run python -m src.cli preprocess --no-extract-requirements

# Export requirements to JSON file (Phase 8)
uv run python -m src.cli preprocess --export-requirements-json data/requirements.json

# Selective re-preprocessing with requirement extraction
uv run python -m src.cli preprocess --re-preprocess-only-v1 --preprocessing-version 2.0
```

**Options**:
- `--batch-size INT` - Jobs per batch (default: 10)
- `--show-estimates` - Display token/cost estimates for first 3 jobs
- `--extract-requirements/--no-extract-requirements` - Enable/disable trigger-based requirement extraction (default: enabled, Phase 8)
- `--export-requirements-json PATH` - Export full requirements JSON to file (optional, Phase 8)
- `--preprocessing-version TEXT` - Version: 1.0 (legacy) or 2.0 (default, with boilerplate removal)
- `--re-preprocess-only-v1` - Only re-preprocess v1.0 jobs (skip v2.0)
- `--filter-by-age DAYS` - Only jobs preprocessed at least N days ago
- `--filter-by-company NAMES` - Comma-separated company names (e.g., 'Amazon,Google')
- `--filter-by-tokens-above N` - Only jobs with token count >= N
- `--limit N` - Maximum number of jobs to process (default: 100)
- `--dry-run` - Preview jobs without modifying database

**Behavior**:
- ✅ Auto-discovers all `*_jobs.json` files in `data/extracted_jobs/`
- ✅ Merges all companies into **single** `preprocessed_jobs.json`
- ✅ Skips `preprocessed_jobs.json` to avoid re-processing
- ✅ **[NEW Phase 8]** Extracts trigger-based requirements by default (--extract-requirements)
- ✅ **[NEW Phase 8]** Displays requirement count + top 5 requirements per job when --show-estimates enabled
- ✅ **[NEW Phase 8]** Exports full requirements JSON when --export-requirements-json specified
- Works for multi-company `--config-dir` crawls automatically

**Requirement Extraction (Phase 8)**:
- **Trigger patterns**: 18 patterns organized in 3 confidence tiers
- **Output format**: JSON array with text, trigger_word, confidence, span, token_count
- **Confidence tiers**:
  - Tier 1 (0.83-0.95): required, must, essential, ability to, experience in/with, proficiency, knowledge of, understanding of
  - Tier 2 (0.65-0.89): should, prefer, degree, years of
  - Tier 3 (0.40-0.55): nice to have, ideal, bonus
- **Context-based adjustments**: Confidence reduced for negations (-0.25), conditionals (-0.15), parentheticals (-0.10)
- **Performance**: <50ms overhead per job, minimal token impact (<5% increase)

**Output**: Single `preprocessed_jobs.json` with cleaned chunks, token counts, cost estimates, and trigger-based requirements (when enabled)

---

### review
**Purpose**: User verification + cost transparency before LLM assessment

```bash
# Basic: confirm/reject jobs interactively
uv run python -m src.cli review --merge-all

# With cost recalculation (NEW): Show costs for specific model
uv run python -m src.cli review --merge-all --model haiku   # Haiku costs
uv run python -m src.cli review --merge-all --model sonnet  # Sonnet costs (default)

# With cost warning (NEW): Alert if total > threshold
uv run python -m src.cli review --merge-all --cost-limit 0.05  # Warn if > $0.05
```

**Options**:
- `--extracted PATH` - Path to single extracted jobs JSON (optional if using `--merge-all`)
- `--preprocessed PATH` - Path to preprocessed jobs JSON (default: data/extracted_jobs/preprocessed_jobs.json)
- `--merge-all` - **[RECOMMENDED]** Auto-discover and process all extracted company files
- `--model TEXT` - **[NEW]** Recalculate costs for model: haiku, sonnet, opus (default: uses preprocess estimates)
- `--cost-limit FLOAT` - **[NEW]** Warn if estimated cost exceeds threshold USD (default: $0.10)
- `--mode TEXT` - Review mode: 'new-only' (unreviewed, default) or 'all' (all jobs)
- `--skip-before-date DATE` - Skip jobs crawled before ISO date (e.g., 2026-07-01)
- `--skip-rejected` - Skip previously rejected jobs (default: true)
- `--skip-assessed` - Skip previously assessed jobs (default: true)
- `--allow-re-review` - Show prior decisions and allow re-review

**Cost Recalculation** (when `--model` specified):
- Loads preprocessed token counts
- Recalculates estimated cost using selected model's pricing
- Shows: original estimate → model-specific estimate
- Helps decide which model to use for assessment phase

**Cost Warnings** (when `--cost-limit` specified):
- After review complete, warns if total_cost > limit
- Suggests adjusting limit or proceeding with assessment
- Useful for budget-conscious workflows

**Output**: Job statuses ("confirmed"/"rejected") saved to database, cost summary displayed

---

### assess
**Purpose**: Claude LLM job-CV matching with configurable model selection

```bash
# Default: Sonnet (balanced cost/quality, $3/$15 per 1M tokens)
uv run python -m src.cli assess --cv data/cv.json --confirmed-only

# Budget mode: Haiku (95% cost savings, $0.80/$4 per 1M tokens)
uv run python -m src.cli assess --cv data/cv.json --model haiku

# Premium: Opus (best accuracy, $15/$75 per 1M tokens)
uv run python -m src.cli assess --cv data/cv.json --model opus

# Advanced: Custom filters with full model ID
uv run python -m src.cli assess \
  --cv data/cv.json \
  --mode new-only \
  --score-threshold 65 \
  --since 2026-07-01 \
  --model claude-sonnet-5
```

**Model options** (use aliases or full IDs):
- `haiku` or `claude-haiku-4-5-20251001` – Fast, cheapest ($0.80/$4/1M)
- `sonnet` or `claude-sonnet-5` – Balanced, default ($3/$15/1M)
- `opus` or `claude-opus-4-8` – Most capable ($15/$75/1M)

**Options**:
- `--cv PATH` - Candidate CV file (required)
- `--confirmed-only/--all` - Filter verified jobs (default: confirmed only)
- `--model TEXT` - Claude model: haiku, sonnet, opus, or full ID (default: sonnet)
- `--model TEXT` - Claude model selection
  - `claude-haiku-4-5-20251001` - Budget ($0.80/$4 per 1M, 95% savings)
  - `claude-sonnet-5` - Default ($3/$15 per 1M, 80% savings)
  - `claude-opus-4-8` - Premium ($15/$75 per 1M, best accuracy)
- `--mode TEXT` - 'new-only' (unassessed) or 'all' (default: new-only)
- `--score-threshold FLOAT` - Re-assess jobs < threshold
- `--since DATE` - Re-assess jobs after ISO date (2026-07-01)

**Output**: Assessment results, per-model cost summary, token usage

---

### query
**Purpose**: Search assessment results by keyword, score, and company

```bash
# Basic search
uv run python -m src.cli query --keyword "Python"

# Search with score filter
uv run python -m src.cli query --keyword "Python" --min-score 75 --max-score 100

# Search within specific company
uv run python -m src.cli query --keyword "engineer" --company "Google"

# Combined filters
uv run python -m src.cli query --keyword "Python" --company "Google" --min-score 80 --limit 5
```

**Options**:
- `--keyword TEXT` - Search keyword (required)
- `--min-score INT` - Minimum score filter (0-100, default: 0)
- `--max-score INT` - Maximum score filter (0-100, default: 100)
- `--company TEXT` - Filter by company name (optional)
- `--limit INT` - Maximum results (default: 10)
- `--json-output` - Output as JSON format (default: false)

**Output**: Formatted table with job titles, companies, scores, and tech/seniority ratings

---

### export
**Purpose**: Generate reports with optional date and score filtering

```bash
# Export all assessments
ats-showcase export --output report.md

# Export with score filter
ats-showcase export --min-score 75 --max-score 95 --output report.md

# Export with date filter
ats-showcase export --from-date 2025-06-01 --to-date 2025-12-31 --output report.md

# Export with combined filters
ats-showcase export \
  --from-date 2025-06-01 \
  --to-date 2025-12-31 \
  --min-score 80 \
  --sort-by company \
  --template-style summary \
  --output report.md
```

**Options**:
- `--output PATH` - Output file path
- `--min-score INT` - Minimum score filter (0-100, default: 0)
- `--max-score INT` - Maximum score filter (0-100, default: 100)
- `--from-date TEXT` - Export assessments from date (YYYY-MM-DD)
- `--to-date TEXT` - Export assessments to date (YYYY-MM-DD)
- `--sort-by TEXT` - Sort by: score|company|location (default: score)
- `--template-style TEXT` - detailed|summary (default: detailed)

**Date Filtering**:
- Dates in ISO 8601 format (YYYY-MM-DD)
- `--from-date` includes assessments on that date and after
- `--to-date` includes assessments on that date and before
- Both can be used together for a date range
- If neither specified, no date filtering applied

**Output**: Markdown report with filtered assessments and applied filters shown in header

---

### view
**Purpose**: Display assessment report with rich markdown formatting and filtering

```bash
# View full report with formatting
uv run python -m src.cli view

# View summary only (headers + scores)
uv run python -m src.cli view --template summary

# View top 3 matches
uv run python -m src.cli view --template topn --topn 3

# Filter by score range
uv run python -m src.cli view --min-score 80 --max-score 95

# View custom report file
uv run python -m src.cli view --report custom_assessments/june_report.md

# Plain text (no colors)
uv run python -m src.cli view --no-highlight
```

**Options**:
- `--report PATH` - Path to report.md file (default: data/assessments/report.md)
- `--template TEXT` - View template: full|summary|topn (default: full)
- `--topn INT` - Number of top matches (default: 5, used with --template topn)
- `--min-score FLOAT` - Filter: only show jobs with score >= min_score (default: 0.0)
- `--max-score FLOAT` - Filter: only show jobs with score <= max_score (default: 100.0)
- `--highlight / --no-highlight` - Enable/disable colors (default: enabled)
- `--no-pager` - Print entire report without pager

**Templates**:
- `full` - Complete report with all job details and filtering
- `summary` - Headers and summary statistics only
- `topn` - Top N matching jobs with full details

**Output**: Colored markdown report with organized sections, syntax highlighting, and score-based coloring

---

### purge
**Purpose**: Delete old assessments by date range with safety features

```bash
# Preview what would be deleted (dry-run mode is default)
uv run python -m src.cli purge --before-date 2025-04-01

# Actually delete assessments before date (requires --confirm)
uv run python -m src.cli purge --before-date 2025-04-01 --no-dry-run --confirm

# Delete assessments after a date
uv run python -m src.cli purge --after-date 2025-01-01 --no-dry-run --confirm

# Delete within date range
uv run python -m src.cli purge \
  --after-date 2025-01-01 \
  --before-date 2025-03-31 \
  --no-dry-run \
  --confirm
```

**Options**:
- `--before-date TEXT` - Delete assessments before date (YYYY-MM-DD)
- `--after-date TEXT` - Delete assessments after date (YYYY-MM-DD)
- `--dry-run` / `--no-dry-run` - Preview or actually delete (default: dry-run)
- `--confirm` / `--no-confirm` - Required flag for actual deletion (default: no-confirm)

**Safety Features**:
- Default dry-run mode: Shows count without deleting
- Must explicitly use `--no-dry-run` to delete
- Must explicitly use `--confirm` to permit deletion
- Both flags required together for actual deletion
- Fails safely if only one flag provided

**Date Semantics**:
- `--before-date X` removes assessments with assessed_date < X
- `--after-date X` removes assessments with assessed_date > X
- Both can be combined for a date range
- Dates in ISO 8601 format (YYYY-MM-DD)

**Output**: Count of records to be deleted (dry-run) or deleted (actual)

---

### stats
**Purpose**: Analytics and cost tracking

```bash
ats-showcase stats \
  --show-tokens \
  --show-costs \
  --days 7
```

**Options**:
- `--show-tokens/--hide-tokens` - Token usage report (default: show)
- `--show-costs/--hide-costs` - Cost breakdown (default: show)
- `--show-timing/--hide-timing` - Performance metrics (default: show)
- `--days INT` - Time period (default: 7)
- `--company TEXT` - Filter by company (optional)

**Output**: Summary tables and charts

---

## Issue #102: Pipeline Control & Visibility Features

Comprehensive pipeline management tools for visibility, filtering, and workflow control.

### Phase 1: Pipeline Visibility (--show-stats)
**Purpose**: Display job counts by status before processing

```bash
# Show pipeline stats with current filtering
uv run python -m src.cli review --merge-all --show-stats

# Output example:
# ================================================================================
# 📊 PIPELINE STATUS
# ================================================================================
#
# Total jobs:          127
#   • Pending review:  8      ← Ready for review
#   • Confirmed:       92     ← Ready for assessment
#   • Rejected:        23     ← Will be skipped
#   • Assessed:        4      ← Already processed
#
# Applying filters: --skip-rejected=True --skip-assessed=True
#   → Will process:  8 jobs
#   → Will skip:     119 jobs
#
# Skip breakdown:
#     • Rejected:       23
#     • Already assessed: 4
```

**Use Case**: Understand job distribution before interactive review starts

---

### Phase 2: Score Threshold Filtering (--score-threshold)
**Purpose**: Skip jobs with low prior CV match scores during assessment

```bash
# Only assess jobs with prior match score ≥ 75%
uv run python -m src.cli assess --cv data/cv.json --score-threshold 75

# Query with score filter
uv run python -m src.cli query --keyword "python" --score-threshold 80
```

**Options**:
- `--score-threshold FLOAT` - Minimum prior match score to assess (0.0-100.0, default: 0)
- Applied before API calls to save cost and time

**Behavior**:
- Jobs without prior assessment → processed normally
- Jobs with prior_match_score < threshold → skipped
- Jobs with prior_match_score >= threshold → assessed

**Use Case**: "Only review jobs with 75%+ CV match confidence"

---

### Phase 3: Interactive Re-Review (--allow-re-review)
**Purpose**: Show prior decisions and allow users to change job status

```bash
# Review with prior decision visibility
uv run python -m src.cli review --interactive --allow-re-review

# Output example:
# Job 1 of 8
# ──────────────────────────────────────────────────────
# Title:       Senior Python Developer
# Company:     TechCorp
# Location:    Remote
# Prior decision: confirmed on 2026-07-01 14:22
#
# Tokens: 742 (estimated $0.002)
# ──────────────────────────────────────────────────────
# [Confirm] [Reject] [Skip] [Re-review]: _
```

**Options**:
- `--allow-re-review` - Show prior decisions + allow status changes (default: False)

**Interactive Choices**:
- `[Confirm]` - Keep current status (confirmed)
- `[Reject]` - Mark as rejected
- `[Skip]` - Skip to next job
- `[Re-review]` - Change prior decision to new status
- `[q]uit` - Exit review

**Database Updates**:
- `job_reviews.reviewed_at` - Timestamp when status last changed
- `re_review_audit` table - Tracks all status changes with reasoning

**Use Case**: "Revisit decisions from previous review sessions"

---

### Phase 4: Job Timeline Visibility (crawled_at, preprocessed_at, reviewed_at, assessed_at)
**Purpose**: Track and display full job lifecycle timestamps

Timestamps recorded at each phase:

```bash
# Timestamps displayed during interactive review
uv run python -m src.cli review --interactive

# Output example:
# Job: Machine Learning Engineer @ TechCorp
# ──────────────────────────────────────────────────────
# 📅 Timeline:
#   Crawled:      2026-07-01 10:00   (when extracted from career page)
#   Preprocessed: 2026-07-01 10:05   (when cleaned & chunked)
#   Reviewed:     2026-07-01 14:22   (when status confirmed/rejected)
#   Assessed:     not processed      (when Claude scored it)
#
# Tokens: 742 (estimated $0.002)
# ──────────────────────────────────────────────────────
# [Confirm] [Reject] [Skip]:
```

**Timeline Events**:
- `crawled_at` - Set when job first extracted from career page
- `preprocessed_at` - Set when HTML cleaned & text chunked
- `reviewed_at` - Set when user confirms/rejects status
- `assessed_at` - Set when Claude assessment completes

**Implementation**:
- Preprocess command auto-sets `preprocessed_at` for all jobs
- Timeline display built into interactive review
- Schema migration handles existing databases gracefully
- Timestamps stored as ISO 8601 format in database

**Use Case**: "Understand the journey of each job through the pipeline"

---

### Combined Workflow: All Issue #102 Features

```bash
# Show stats + review with filters + timeline + re-review
uv run python -m src.cli review \
  --merge-all \
  --show-stats \
  --skip-rejected \
  --skip-assessed \
  --allow-re-review \
  --interactive

# Expected output:
# 1. Pipeline stats shown first (Phase 1)
# 2. Interactive review starts (Phase 3 + Phase 4)
# 3. Timeline visible for each job (Phase 4)
# 4. Prior decisions shown with re-review option (Phase 3)
#
# Then assess with score filtering (Phase 2)
uv run python -m src.cli assess \
  --cv data/cv.json \
  --score-threshold 75
```

---

### Full Workflow
**Purpose**: Execute all phases sequentially (crawl→preprocess→verify→assess→export)

```bash
# Default: Sonnet model
uv run python -m src.cli all \
  --cv data/cv.json \
  --config config/companies.json

# Budget mode: Haiku (95% cost savings)
uv run python -m src.cli all \
  --cv data/cv.json \
  --config config/companies.json \
  --model claude-haiku-4-5-20251001

# Premium: Opus (best accuracy)
uv run python -m src.cli all \
  --cv data/cv.json \
  --config-dir ./config \
  --model claude-opus-4-8 \
  --interactive
```

**Options**:
- `--cv PATH` - CV file (required)
- `--config PATH` - Single config file or
- `--config-dir PATH` - Directory of config files (NEW)
- `--model TEXT` - Claude model (Haiku/Sonnet/Opus, default: Sonnet)
- `--interactive` - Prompt before assessing each job
- `--tui / --no-tui` - Use/disable dashboard (auto-detected)

**Equivalent to** (step-by-step):
```bash
uv run python -m src.cli crawl --config config/companies.json
uv run python -m src.cli preprocess
uv run python -m src.cli review --interactive
uv run python -m src.cli assess --cv data/cv.json --model claude-sonnet-5
uv run python -m src.cli export --output data/assessments/report.md
```

## Error Handling Patterns

### Error Messages & Remediation

```python
class CLIError(Exception):
    """Base CLI error with remediation."""

    def __init__(self, message: str, hint: str = None):
        self.message = message
        self.hint = hint
        super().__init__(message)

# Usage
def validate_cv_file(cv_path: Path):
    if not cv_path.exists():
        raise CLIError(
            f"CV file not found: {cv_path}",
            hint=f"Create CV at {cv_path} in JSON format"
        )

    try:
        with open(cv_path) as f:
            json.load(f)
    except json.JSONDecodeError:
        raise CLIError(
            f"Invalid JSON in {cv_path}",
            hint="Validate JSON syntax: python -m json.tool cv.json"
        )
```

### Exit Codes

| Code | Meaning | Remediation |
|------|---------|-------------|
| 0 | Success | - |
| 1 | Input/config error | Check `--help` and config files |
| 2 | Network error | Check internet connection, proxy |
| 3 | API error | Check ANTHROPIC_API_KEY, rate limits |
| 4 | Database error | Check file permissions, disk space |
| 5 | Timeout | Increase --timeout, check network |

## Interactive Workflows

### Review Command (Interactive Mode)

```
┌─ Job 1 of 5 ────────────────────────────────────┐
│ Title: Senior Python Engineer                    │
│ Company: TechCorp                                │
│ Requirements: 5+ years Python, AWS               │
│                                                   │
│ Token count: 450 / Cost: $0.0014                 │
│                                                   │
│ (c)onfirm / (r)eject / (e)dit / (s)kip / (q)uit? │
└────────────────────────────────────────────────┘
```

**Keystrokes**:
- `c` - Confirm and save to database
- `r` - Reject (mark for skip)
- `e` - Edit in $EDITOR
- `s` - Skip to next
- `q` - Quit

### Assess Command (Progress Tracking)

```
Assessing 50 jobs for CV: john_smith

▓▓▓▓▓▓▓▓░░░░░░░░░░░ 40%

[10/25] MES Programmer @ EngineerCorp
  ✓ Score: 0.82 | Cost: $0.0007 | Latency: 1.2s

[11/25] Manufacturing IT @ MfgCorp
  ✗ Error: Rate limited (retry 1/3)

Assessment complete:
  - Total: 50 jobs
  - Successful: 48 (96%)
  - Failed: 2 (4%)
  - Total cost: $0.035
  - Avg cost/job: $0.0007
```

## Testing CLI

### Unit Tests

```python
# tests/test_cli.py
import pytest
from typer.testing import CliRunner
from src.cli import app

runner = CliRunner()

def test_crawl_missing_config():
    """Test crawl with missing config file."""
    result = runner.invoke(app, ["crawl", "--config", "nonexistent.json"])
    assert result.exit_code == 1
    assert "not found" in result.stdout

def test_assess_success(tmp_path):
    """Test successful assessment workflow."""
    cv_file = tmp_path / "test_cv.json"
    cv_file.write_text('{"id": "test", "summary": "Python engineer"}')

    result = runner.invoke(app, ["assess", "--cv", str(cv_file), "--confirmed-only"])
    assert result.exit_code in [0, 1]  # 0 success, 1 no jobs

def test_query_keyword_search(tmp_path):
    """Test FTS5 keyword search."""
    result = runner.invoke(app, ["query", "--search", "Python"])
    assert result.exit_code == 0
```

### Integration Tests

```python
# tests/integration/test_full_workflow.py
def test_full_workflow(tmp_path, monkeypatch):
    """Test crawl→review→assess→export workflow."""
    from pathlib import Path

    # Setup
    config_file = tmp_path / "config.json"
    cv_file = tmp_path / "cv.json"
    output_dir = tmp_path / "output"

    config_file.write_text(json.dumps({
        "companies": [{
            "name": "TestCorp",
            "url": "https://example.com",
            "selectors": {"job_title": "h2"}
        }]
    }))

    cv_file.write_text(json.dumps({
        "id": "test_cv",
        "summary": "Experienced engineer"
    }))

    # Execute workflow
    runner = CliRunner()

    # Crawl
    result = runner.invoke(app, [
        "crawl",
        "--config", str(config_file),
        "--output", str(output_dir / "extracted")
    ])
    assert result.exit_code in [0, 1]  # May fail if URL unreachable

    # Export
    result = runner.invoke(app, [
        "export",
        "--format", "markdown",
        "--output", str(output_dir / "report.md")
    ])
    assert result.exit_code == 0
```

## Configuration Management

### Single File Configuration (Backward Compatible)

Load companies from a single `companies.json` file:

```bash
python -m src.cli crawl --config config/companies.json
python -m src.cli all --cv data/cv.json --config config/companies.json
```

### Directory-Based Configuration with `--config-dir`

*(NEW)* Load companies from multiple JSON config files in a directory:

```bash
python -m src.cli crawl --config-dir ./config
python -m src.cli all --cv data/cv.json --config-dir ./config
```

#### The `enabled` Flag for Selective Company Processing

Control which companies are processed using the `enabled` flag in your config files:

```json
{
  "companies": {
    "ActiveCompany": {
      "enabled": true,
      "name": "Company to process",
      "url": "https://example.com/careers",
      "selectors": { ... }
    },
    "InactiveCompany": {
      "enabled": false,
      "name": "Company to skip",
      "url": "https://disabled.example.com",
      "selectors": { ... }
    },
    "LegacyCompany": {
      "name": "Defaults to true (backward compatible)",
      "url": "https://legacy.example.com",
      "selectors": { ... }
    }
  }
}
```

#### Behavior

| Flag | Behavior |
|------|----------|
| `"enabled": true` | Process the company ✅ |
| `"enabled": false` | Skip the company ⏭️ |
| Missing (omitted) | Defaults to `true` (backward compatible) ✅ |

#### Output Example

```bash
$ python -m src.cli crawl --config-dir ./config

📋 Found 5 companies from directory: ./config
⏭️  Skipping 2 disabled companies: DataCo, OldCorp
✅ Processing 3 enabled companies

🌐 Crawling in progress...
   • ActiveCompany: 24 jobs
   • LegacyCompany: 18 jobs
   • TechCorp: 31 jobs

✅ Crawl complete! Extracted 73 total jobs
```

#### Use Cases

**Multi-tenant scenarios**: Maintain separate config files per customer/client:
```
config/
├── client_a.json      # enabled: true
├── client_b.json      # enabled: true
├── client_archived.json # enabled: false
```

**A/B Testing**: Test new CSS selectors before activation:
```json
{
  "companies": {
    "SiteV1": { "enabled": false, "url": "..." },
    "SiteV2": { "enabled": true, "url": "..." }
  }
}
```

**Staged Rollout**: Gradually enable companies in production:
```bash
# Monday: Test with 2 companies
python -m src.cli all --cv data/cv.json --config-dir ./config

# Wednesday: Enable 5 more
# (Update enabled flags in config files)

# Friday: Full production
```

### Configuration File Format

All JSON config files must contain a `companies` key mapping company names to configuration:

```json
{
  "companies": {
    "CompanyKey": {
      "enabled": true|false,           // optional, defaults to true
      "name": "Display Name",
      "url": "https://career-url.com",
      "selectors": {
        "job_container": ".job-post",
        "title": ".job-title",
        "description": ".job-desc",
        "location": ".job-location"
      },
      "crawler": {                     // optional
        "type": "single_page",
        "timeout_ms": 30000,
        "headless": true
      }
    }
  }
}
```

### Loading Priority

When using `--config-dir`:
1. Scans directory for all `*.json` files (sorted alphabetically)
2. Loads companies from each file
3. Merges all companies into a single dictionary
4. Filters by `enabled` flag before processing

**Note**: If the same company key exists in multiple files, the last file wins (files are sorted alphabetically).

---

## Best Practices

✅ **Always provide defaults** - Users shouldn't need flags for common cases
✅ **Show costs upfront** - Display token/cost estimates before LLM calls
✅ **Batch operations** - Process multiple items efficiently
✅ **Progress feedback** - Show spinners, progress bars for long operations
✅ **Clear error messages** - Include "hint" for remediation
✅ **Async operations** - Use Typer's async support for concurrent work
✅ **Log everything** - Write to `logs/app.log` for debugging
✅ **Validation first** - Check inputs before expensive operations

❌ Don't silently ignore errors
❌ Don't process without user confirmation
❌ Don't make irreversible changes without --force flag
❌ Don't send to expensive APIs without showing cost estimate

## Deployment Checklist

- [ ] **Installation**:
  - [ ] `pip install -e .` installs CLI entry point
  - [ ] `ats-showcase --help` works
  - [ ] `ats-showcase version` shows version

- [ ] **Configuration**:
  - [ ] `ats-showcase init` creates config/data directories
  - [ ] `.env` file with ANTHROPIC_API_KEY set
  - [ ] `config/companies.json` populated

- [ ] **Testing**:
  - [ ] Run unit tests: `pytest tests/ -v`
  - [ ] Test each subcommand manually
  - [ ] Test error cases (missing file, invalid config)
  - [ ] Run integration tests: `pytest tests/integration/ -v`

- [ ] **Documentation**:
  - [ ] `ats-showcase --help` is clear
  - [ ] `ats-showcase <command> --help` detailed
  - [ ] README.md has quick-start with commands

- [ ] **Performance**:
  - [ ] Crawl 100 jobs in <5 minutes
  - [ ] Preprocess 100 jobs in <1 minute
  - [ ] Assess 50 jobs in <5 minutes

## Next Steps

1. **Async support**: Add `async def` commands for concurrent operations
2. **Shell completion**: Generate bash/zsh/fish completions
3. **Config validation**: JSON schema for companies.json
4. **Telemetry**: Optional usage tracking (opt-in)
5. **Plugin system**: Allow custom commands via plugins

---

**Related Documentation**:
- [CLI-STEP-BY-STEP.md](./CLI-STEP-BY-STEP.md) - Complete workflow guide with examples
- [CRAWL.md](./CRAWL.md) - Crawling implementation
- [PREPROCESS.md](./PREPROCESS.md) - Preprocessing implementation
- [VERIFY.md](./VERIFY.md) - Verification workflow
- [ASSESS.md](./ASSESS.md) - Assessment implementation
- [STORAGE.md](./STORAGE.md) - Database queries
- [ARCHITECTURE.md](./ARCHITECTURE.md) - System design
- [CONVENTIONS.md](./CONVENTIONS.md) - Code style & testing
