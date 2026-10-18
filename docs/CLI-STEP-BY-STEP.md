# ATS Showcase CLI - Step-by-Step Workflow Guide

Complete reference for using the ATS Showcase command-line interface to run the intelligent job assessment workflow.

---

## Quick Start (5 Minutes)

Run everything in one command:

```bash
uv run python -m src.cli all --cv data/cv.json --config config/companies.json
```

For multiple company config directories:

```bash
uv run python -m src.cli all --cv data/cv.json --config-dir ./config
```

---

## Quick Start with Interactive Dashboard

ATS Showcase includes an interactive Textual dashboard that shows real-time progress, live cost tracking, and top job matches as the workflow runs.

**Dashboard auto-launches in interactive terminals:**

```bash
uv run python -m src.cli all --cv data/cv.json --config config/companies.json
# Dashboard appears automatically (no --tui flag needed)
```

**Explicitly enable dashboard:**

```bash
uv run python -m src.cli all --tui --cv data/cv.json --config config/companies.json
```

**Force text-only mode (useful for CI/headless):**

```bash
uv run python -m src.cli all --no-tui --cv data/cv.json --config config/companies.json
```

**Dashboard shows:**
- Real-time crawl progress (companies, jobs extracted)
- Preprocessing tokens and cost
- Assessment scores and top 5 matches live
- Overall token usage and cost accumulation
- Phase status indicators (✅ running, ⏳ in progress, ⚪ pending)

**Keyboard controls:**
- `p` - Pause/resume workflow
- `r` - Resume from pause
- `q` - Quit dashboard

---

## Cost-Controlled Workflow (Stop Before Assess)

Use `--up-to` to halt before expensive assessment phase:

```bash
# Extract jobs, verify quality — STOP before paying for assessment
uv run python -m src.cli all --cv data/cv.json --config config/companies.json --up-to review

# Crawl + preprocess only
uv run python -m src.cli all --cv data/cv.json --config config/companies.json --up-to preprocess

# Crawl only
uv run python -m src.cli all --cv data/cv.json --config config/companies.json --up-to crawl

# Continue with assessment (after verification)
uv run python -m src.cli assess --cv data/cv.json
```

**Typical workflow:**
1. Extract jobs: `--up-to crawl`
2. Clean + verify: `--up-to review`
3. Review extraction quality interactively
4. If satisfied: continue with `assess` or full `--all` on next run

---

## Full Workflow (8 Commands)

> **Note:** The interactive TUI dashboard is available when running the complete workflow with the `all` command (see Quick Start above). Individual phase commands (crawl, preprocess, assess, export) use text-based output only. For step-by-step phases with TUI visualization, use `uv run python -m src.cli all --tui`.

### Phase 0: Prerequisites

Before running any commands, ensure:

```bash
# Setup environment
uv sync                                          # Install deps
uv run python -m spacy download en_core_web_md # NLP model
uv run playwright install                       # Browser
cp .env.example .env                            # Config
# Edit .env and add: export ANTHROPIC_API_KEY="..."
```

Verify dependencies:

```bash
# Check Python version (must be 3.12+)
python --version

# Check API key is set
echo $ANTHROPIC_API_KEY
```

---

## Phase 1: CRAWL - Extract Job Postings

### Command

```bash
uv run python -m src.cli crawl \
  --config config/companies.json \
  --headless true \
  --timeout 30000
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--config` | `config/companies.json` | Path to single JSON config file |
| `--config-dir` | None | Directory with multiple JSON config files |
| `--headless` | `true` | Run browser in headless mode (no UI) |
| `--timeout` | `30000` | Browser timeout in milliseconds |
| `--mock` | `false` | Mock crawling without launching browser (testing) |

### Config File Format

```json
{
  "companies": {
    "CompanyName": {
      "enabled": true,
      "name": "Company Name",
      "url": "https://example.com/careers",
      "job_selector": ".job-posting",
      "title_selector": ".job-title",
      "location_selector": ".job-location",
      "description_selector": ".job-description"
    }
  }
}
```

### Output

Saves job postings to: `data/extracted_jobs/{company_name}_jobs.json`

Example output:

```
🌐 Crawling in progress...

📋 Found 2 companies from file: config/companies.json
✅ Processing 2 enabled companies

✅ Crawl complete! Extracted 45 total jobs

   • CompanyA: 26 jobs
      Saved to: data/extracted_jobs/companya_jobs.json
   • CompanyB: 19 jobs
      Saved to: data/extracted_jobs/companyb_jobs.json

⏱️  Phase 1 took 42.15s
```

### Troubleshooting

**Browser crashes:**
```bash
uv run playwright install chromium
```

**Timeout errors:**
Increase `--timeout` (in milliseconds): `--timeout 60000` (60 seconds)

**No jobs found:**
- Check CSS selectors in config file
- Visit company careers page manually to verify structure
- Use browser DevTools to inspect HTML

---

## Phase 2: PREPROCESS - Clean, Chunk, Count Tokens (with Boilerplate Removal)

### What Happens

1. **HTML Cleaning (Issue #230)**: Consolidated `clean_html()` removes 70+ boilerplate patterns across 7 categories
2. **Markdown Conversion (Issue #231)**: 3-tier fallback (MarkItDown → BeautifulSoup → Original HTML) ensures robustness
3. **Section Headers**: Synthesized `##`/`###` headers + `---` dividers (Issue #228)
4. **Text Chunking**: Semantic chunks at sentence boundaries using spaCy
5. **Token Counting**: tiktoken estimates Claude API usage
6. **Cost Estimation**: Calculates USD cost per job

### Command

```bash
# Single or multi-company (auto-detects all extracted files)
uv run python -m src.cli preprocess --show-estimates
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--batch-size` | `10` | Number of jobs per batch (for memory management) |
| `--show-estimates` | `false` | Display token/cost estimates for first 3 jobs per file |
| `--extract-requirements` | `true` | Enable trigger-based requirement extraction (Phase 8) |
| `--no-extract-requirements` | N/A | Disable requirement extraction (backward compatible) |
| `--export-requirements-json` | N/A | Export full requirements JSON to file path (optional, Phase 8) |
| `--preprocessing-version` | `2.0` | Version: 1.0 (legacy, no boilerplate) or 2.0 (with boilerplate, default) |
| `--re-preprocess-only-v1` | `false` | Only re-preprocess v1.0 jobs (skip v2.0) |
| `--filter-by-age` | N/A | Only jobs preprocessed at least N days ago |
| `--filter-by-company` | N/A | Comma-separated company names (e.g., 'Amazon,Google') |
| `--filter-by-tokens-above` | N/A | Only jobs with token count >= N |
| `--limit` | `100` | Maximum number of jobs to process |
| `--dry-run` | `false` | Preview jobs without modifying database |

### Multi-Company Auto-Merge ✓

When using `crawl --config-dir` for multiple companies:
- ✅ Auto-discovers **all** `*_jobs.json` files in `data/extracted_jobs/`
- ✅ Processes each company file automatically
- ✅ **Merges all into single** `preprocessed_jobs.json` (no manual steps)
- Zero additional configuration needed

### What It Does

1. **Scans directory** - Finds all `*_jobs.json` files (skips `preprocessed_jobs.json`)
2. **Cleans HTML (Issue #230)** - Uses consolidated `clean_html()` with 70+ boilerplate patterns (legal, headers, company info, time refs, salary, formatting, navigation)
3. **Converts to Markdown** - MarkItDown (primary) or BeautifulSoup (fallback) HTML→Markdown
4. **Chunks text** - Splits into semantic chunks (sentence-based)
5. **Counts tokens** - Estimates Claude API tokens using tiktoken
6. **Estimates costs** - Calculates API cost per job
7. **Extracts requirements (NEW - Phase 8, Issue #252)** - Trigger-based requirement extraction with 18 patterns across 3 confidence tiers
8. **Merges all** - Combines all companies into single output file

### Output

Saves **merged** preprocessed jobs to: `data/extracted_jobs/preprocessed_jobs.json`
- Contains jobs from all crawled companies
- Single file (automatic merge from all sources)

Example output:

```
🔄 Preprocessing jobs...

📂 Processing companya_jobs.json...
   Job 1: Software Engineer - San Francisco...
      Tokens: 342 | Cost: $0.0021
   Job 2: Senior DevOps Engineer - Austin...
      Tokens: 456 | Cost: $0.0028

✅ Preprocessing complete!

📊 Summary:
   Total jobs: 45
   Processed: 45
   Failed: 0
   Total tokens: 15,420
   Total cost: $0.0924
   Avg tokens/job: 343

💾 Saving preprocessed jobs...
   ✓ Saved to: data/extracted_jobs/preprocessed_jobs.json
```

### Key Metrics

- **Token reduction**: ~88% vs raw HTML (saves API costs)
  - Boilerplate removal: ~30% of savings
  - Markdown cleaning: ~40% of savings
  - Semantic chunking: ~18% of savings
- **Time**: <2 seconds for typical crawls (70+ patterns pre-compiled for 10x speed)
- **Cost accuracy**: ±5% vs actual Claude API usage

### Token Reduction Breakdown (Example)

```
Raw HTML job posting:     ~6,000 tokens
  ├─ Boilerplate (removed): ~1,800 tokens  (legal, nav, company info, etc.)
  ├─ Markdown cleaning:     ~2,400 tokens  (markup, formatting)
  ├─ Semantic chunking:     ~1,080 tokens  (whitespace, redundancy)
  └─ Final cleaned text:      ~700 tokens ✅

Per-job cost:
  Raw approach:           $0.018
  ATS Showcase (v2.0):    $0.002
  Savings:                89% per job

Example: Assessing 100 jobs
  Raw (no preprocessing):  $1.80
  ATS Showcase (v2.0):     $0.20
  Total savings:           $1.60 (89%)
```

### Trigger-Based Requirement Extraction (Phase 8, NEW)

Automatic requirement extraction using 18 trigger patterns across 3 confidence tiers. Disabled by default in text mode; enable with `--extract-requirements`.

**Usage**:
```bash
# Enable extraction (default for new pipelines)
uv run python -m src.cli preprocess --extract-requirements

# Disable extraction (backward compatible)
uv run python -m src.cli preprocess --no-extract-requirements

# Export requirements to JSON (optional)
uv run python -m src.cli preprocess --export-requirements-json data/requirements.json

# With estimates (shows requirement count + top 5 per job)
uv run python -m src.cli preprocess --show-estimates --extract-requirements
```

**Output with `--show-estimates`**:
```
📂 Processing test_jobs.json...
   Job 1: Senior Python Developer...
      Tokens: 342 | Cost: $0.0021
      Requirements: 8 extracted
         1. 5+ years of Python experience... (confidence: 0.89)
         2. knowledge of Django and FastAPI... (confidence: 0.87)
         3. REST API design... (confidence: 0.85)
         4. Proficiency in Docker... (confidence: 0.88)
         5. ability to work with distributed systems... (confidence: 0.84)

✅ Preprocessing complete!

📊 Summary:
   ...
   Trigger-based requirements: 42 extracted
```

**Requirement Extraction Features**:
- **18 trigger patterns** organized by confidence tier (Tier 1: 0.83-0.95, Tier 2: 0.65-0.89, Tier 3: 0.40-0.55)
- **Tier 1 patterns**: required, must, essential, ability to, experience in/with, proficiency, knowledge of, understanding of
- **Tier 2 patterns**: should, prefer, degree, years of
- **Tier 3 patterns**: nice to have, ideal, bonus
- **Context-based adjustments**: Confidence adjusted for negations, conditionals, parentheticals, soft skills mentions
- **Performance**: <50ms overhead per job, minimal token impact (<5% increase)
- **JSON output format**: `{text, trigger_word, confidence, span, token_count}`

**When to use**:
- `--extract-requirements` (default): Enable pattern-based requirement extraction
- `--no-extract-requirements`: Skip extraction for faster processing
- `--export-requirements-json <file>`: Save all requirements to JSON for downstream analysis (e.g., skills gap analysis, curriculum building)
```

### Boilerplate Categories Removed

| Category | Example Removed | Preserved |
|----------|-----------------|-----------|
| Legal | "Equal Opportunity Employer. © 2026 All rights reserved." | — |
| Navigation | Breadcrumbs, page menus, links back to careers | — |
| Company Info | "TechCorp is a cutting-edge robotics company..." | "Senior Python Developer" |
| Time Refs | "Posted 2 days ago • Apply by July 31" | — |
| Salary/Benefits | "$150K–$200K, health insurance, 401k" | (optional removal) |
| Formatting | Extra whitespace, `<br/>` tags, CSS classes | Semantic structure |
| Section Headers | Duplicate "Requirements", "Description" headers | Synthesized `##` headers |

---

## Phase 3: REVIEW - Interactive Job Filtering

### Command

**Single company (legacy):**

```bash
uv run python -m src.cli review \
  --extracted data/extracted_jobs/companya_jobs.json
```

**Multiple companies (RECOMMENDED):**

```bash
uv run python -m src.cli review --merge-all
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--extracted` | None | Path to single extracted jobs JSON (only if NOT using `--merge-all`) |
| `--preprocessed` | `data/extracted_jobs/preprocessed_jobs.json` | Path to preprocessed jobs JSON (auto-discovered) |
| `--merge-all` | `false` | **[RECOMMENDED for multi-company]** Auto-discover and process all extracted company files together |
| `--model` | None | **[NEW]** Recalculate costs for model (haiku/sonnet/opus). Shows model-specific cost estimate |
| `--cost-limit` | $0.10 | **[NEW]** Warn if total estimated cost exceeds this USD amount |
| `--mode` | new-only | Review mode: 'new-only' (unreviewed) or 'all' (all jobs) |
| `--skip-before-date` | None | Skip jobs crawled before ISO date (e.g., 2026-07-01) |
| `--skip-rejected` | true | Skip previously rejected jobs |
| `--skip-assessed` | true | Skip previously assessed jobs |
| `--allow-re-review` | false | Show prior decisions and allow changing them |

### Multi-Company Workflow ✓

Complete end-to-end pipeline for multiple companies:

```bash
# Step 1: Crawl all companies → separate extracted_*.json files
uv run python -m src.cli crawl --config-dir ./config

# Step 2: Preprocess → auto-merges all into single preprocessed_jobs.json
uv run python -m src.cli preprocess

# Step 3: Review --merge-all → processes all jobs from all companies
uv run python -m src.cli review --merge-all

# Step 4: Assess → evaluates all confirmed jobs
uv run python -m src.cli assess --cv data/cv.json
```

**How `--merge-all` works:**
- ✅ Auto-discovers all `*_jobs.json` files in `data/extracted_jobs/`
- ✅ Skips `preprocessed_jobs.json` automatically
- ✅ Reviews all jobs from all companies in one interactive session
- ✅ No manual file selection needed

### Interactive Flow

For each job, you'll see:

```
[1/26] Software Engineer - San Francisco
  Company: Carbon Robotics
  Location: San Francisco, CA
  Token count: 342
  Estimated cost: $0.0021

Confirm? (y/n/skip):
```

### Actions

- **y** (yes) - Confirm job, will be assessed by Claude
- **n** (no) - Reject job, skip LLM assessment
- **skip** - Skip for now (can review later)

### Output

Updates job status in preprocessed JSON:

```json
{
  "job_id": "companya_1",
  "title": "Software Engineer",
  "status": "confirmed",  // or "rejected"
  "chunks": [...],
  "token_count": 342
}
```

Example output:

```
👀 Reviewing extracted jobs...

[1/26] Software Engineer - San Francisco
  Company: Carbon Robotics
  Location: San Francisco, CA
  Tokens: 342 | Cost: $0.0021
Confirm? (y/n/skip): y

[2/26] Product Manager - Austin
  Company: Carbon Robotics
  Location: Austin, TX
  Tokens: 398 | Cost: $0.0024
Confirm? (y/n/skip): n

...

✅ Review complete: 22 confirmed, 4 rejected
```

### Why Review Jobs?

- **Save money** - Skip irrelevant jobs before LLM assessment
- **Save time** - Skip positions you're not interested in
- **Improve results** - Assess only relevant opportunities

### Cost Recalculation (NEW)

By default, cost estimates are based on the model used during preprocessing (typically Sonnet). Use `--model` to recalculate for a different model:

```bash
# See costs for Haiku (cheapest)
uv run python -m src.cli review --merge-all --model haiku

# Output includes recalculated cost estimates
💰 Recalculating costs for Haiku model...
✅ Recalculated costs using Haiku:
   Original estimate: $0.0234
   Haiku estimate:    $0.0031  (87% savings!)
```

**Use case**: "Before reviewing, show me how much Haiku would cost vs Sonnet"

### Cost Warnings (NEW)

Set a budget threshold to warn if review total exceeds it:

```bash
# Warn if total estimated cost > $0.05
uv run python -m src.cli review --merge-all --cost-limit 0.05

# Output at end of review:
⚠️  WARNING: Estimated LLM cost ($0.0847) exceeds threshold ($0.05)
   To proceed with assessment, use: assess --model <model> --cv <cv_file>
   To adjust threshold: review --cost-limit 0.10
```

**Use case**: "Alert me if review total would exceed my budget"

---

## Phase 4: ASSESS - AI Evaluation with Claude

### Command

```bash
# Default: Sonnet (balanced cost/quality, $3/$15 per 1M tokens)
uv run python -m src.cli assess --cv data/cv.json

# Budget mode: Haiku (95% cost savings, $0.80/$4 per 1M tokens)
uv run python -m src.cli assess --cv data/cv.json --model haiku

# Premium: Opus (best accuracy, $15/$75 per 1M tokens)
uv run python -m src.cli assess --cv data/cv.json --model opus

# Advanced: Filters + model selection with full model ID
uv run python -m src.cli assess \
  --cv data/cv.json \
  --mode new-only \
  --score-threshold 65 \
  --since 2026-07-01 \
  --model claude-sonnet-5
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--cv` | *required* | Path to CV file (JSON or TXT) |
| `--confirmed-only` | `true` | Only assess jobs with status="confirmed" |
| `--model` | `sonnet` | Claude model: haiku, sonnet, opus (or full ID like claude-sonnet-5) |
| `--mode` | `new-only` | 'new-only' (unassessed) or 'all' (all confirmed) |
| `--score-threshold` | None | Re-assess jobs below threshold |
| `--since` | None | Re-assess jobs after ISO date (2026-07-01) |

### Model Comparison

| Model | Alias | Cost (input/output per 1M) | Speed | Accuracy | Use Case |
|-------|-------|---------------------------|-------|----------|----------|
| Haiku | `haiku` | $0.80 / $4.0 | Fast | 🟡 Good | Budget, prototyping, volume testing |
| Sonnet | `sonnet` | $3.0 / $15.0 | Medium | 🟢 Great | **Default choice** |
| Opus | `opus` | $15.0 / $75.0 | Slower | 🟢 Excellent | High accuracy needed |

**Using aliases:**
```bash
# Haiku with alias
uv run python -m src.cli assess --cv data/cv.json --model haiku

# Opus with alias (case-insensitive)
uv run python -m src.cli assess --cv data/cv.json --model OPUS

# Full model ID (also works)
uv run python -m src.cli assess --cv data/cv.json --model claude-haiku-4-5-20251001
```

### CV File Format

**JSON format:**

```json
{
  "text": "Your complete CV text here...",
  "name": "John Doe",
  "email": "john@example.com",
  "phone": "+1-555-0000",
  "summary": "5 years of software engineering experience...",
  "skills": ["Python", "Go", "Kubernetes", "ML"],
  "experience": [...]
}
```

**Plain text format:** Just use a `.txt` file with your CV content

### What It Does

For each confirmed job, Claude evaluates:

1. **Overall CV Match** (0-100) - How well does your CV fit?
2. **Technical Skills** (0-100) - Do you have required skills?
3. **Seniority Level** (0-100) - Does your experience level match?
4. **Location Preference** (0-100) - Is location acceptable?
5. **Recommendations** (text) - Should you apply?

### Output

Saves assessments to: `data/ats_playground.db` (SQLite)

Example output:

```
📄 Loaded CV from: data/cv.json

🤖 Starting CV assessment for 22 confirmed jobs

✅ Job 1/22: Software Engineer - San Francisco
   Tech: 85/100 | Seniority: 75/100 | Location: 80/100 | Overall: 80/100
   Cost: $0.0006 | Tokens: 1,247

✅ Job 2/22: Senior Backend Engineer - New York
   Tech: 92/100 | Seniority: 88/100 | Location: 60/100 | Overall: 80/100
   Cost: $0.0007 | Tokens: 1,356

✅ Job 3/22: DevOps Engineer - Austin
   Tech: 78/100 | Seniority: 72/100 | Location: 90/100 | Overall: 80/100
   Cost: $0.0006 | Tokens: 1,198

...

════════════════════════════════════════════════════════════════════════════════
📊 Assessment Summary:
   Total assessed: 22/22
   Avg overall score: 76.3/100
   Total cost: $0.0147
   Total tokens: 26,534

🏆 Top Matches:
   1. Senior Backend Engineer - Overall: 92/100
   2. ML Engineer - Overall: 88/100
   3. Software Engineer (Python) - Overall: 85/100

✅ Assessment complete!
```

### Scoring Interpretation

| Score | Interpretation | Action |
|-------|-----------------|--------|
| 90-100 | Excellent match | Definitely apply |
| 75-89 | Good fit | Apply |
| 60-74 | Moderate fit | Consider applying |
| 0-59 | Poor fit | Skip |

### Rate Limiting

Claude API has built-in rate limits:

- **Max requests**: 10 per minute
- **Max tokens**: 50,000 per minute
- **Backoff**: Auto-retry with exponential backoff

For 100 jobs: ~10 minutes

### Troubleshooting

**"ANTHROPIC_API_KEY not set"**
```bash
export ANTHROPIC_API_KEY="..."
```

**API rate limit exceeded:**
CLI auto-retries. Wait 1 minute and rerun the command (restarts from where it failed).

**No confirmed jobs found:**
Run `review` command first to confirm jobs.

---

## Phase 5: EXPORT - Generate Markdown Report

### Command

```bash
uv run python -m src.cli export \
  --output data/assessments/report.md \
  --min-score 75 \
  --max-score 100 \
  --sort-by score \
  --template detailed \
  --include-recommendations true \
  --include-stats true
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--output` | `data/assessments/report.md` | Output file path |
| `--min-score` | `0` | Minimum score filter (0-100) |
| `--max-score` | `100` | Maximum score filter (0-100) |
| `--sort-by` | `score` | Sort by: `score`, `company`, or `location` |
| `--template` | `detailed` | Template: `detailed` or `summary` |
| `--include-recommendations` | `true` | Include Claude recommendations |
| `--include-stats` | `true` | Include analytics section |

### Filter Examples

Show only top matches (80+):

```bash
uv run python -m src.cli export --min-score 80
```

Show only poor fits (<60):

```bash
uv run python -m src.cli export --max-score 59
```

Sort by location:

```bash
uv run python -m src.cli export --sort-by location
```

### Output

Generates Markdown file: `data/assessments/report.md`

Example output:

```
📊 Generating report (score 75-100)...
✅ Exported 18/22 jobs to data/assessments/report.md
   File size: 42.3 KB
   Template: detailed
```

### Report Structure

```markdown
# ATS Assessment Report

**Generated:** 2026-06-16
**Total jobs:** 22
**Filtered:** 18 (75-100)

---

## Top Matches

1. **Senior Backend Engineer** (92/100)
   - Company: TechCorp
   - Location: New York, NY
   - Tech: 92/100 | Seniority: 88/100 | Overall: 92/100

...

---

## Job Details

### 1. Senior Backend Engineer
- **Company:** TechCorp
- **Location:** New York, NY
- **Score:** 92/100
- **Tech Skills:** 92/100
- **Seniority:** 88/100
- **Location Fit:** 60/100
- **Recommendation:** Excellent match - Python + 5 years experience aligns well

...

---

## Analytics

**Total Jobs:** 22
**Assessed:** 22
**Average Score:** 76.3/100
**Total Cost:** $0.0147
**Token Usage:** 26,534 tokens

**Score Distribution:**
- 90-100 (Excellent): 3 jobs
- 75-89 (Good): 12 jobs
- 60-74 (Moderate): 7 jobs
- 0-59 (Poor): 0 jobs
```

---

## Utility Commands

### Search Assessments by Keyword

```bash
# Basic search
uv run python -m src.cli query --keyword "python"

# Search with score filter
uv run python -m src.cli query --keyword "python" --min-score 75 --limit 5

# Search by company
uv run python -m src.cli query --keyword "engineer" --company "Google"

# Combined filters
uv run python -m src.cli query --keyword "python" --company "TechCorp" --min-score 80

# JSON output
uv run python -m src.cli query --keyword "kubernetes" --json-output
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--keyword` | TEXT | *required* | Search keyword (FTS5) |
| `--min-score` | INT | 0 | Minimum score (0-100) |
| `--max-score` | INT | 100 | Maximum score (0-100) |
| `--company` | TEXT | None | Filter by company name |
| `--limit` | INT | 10 | Maximum results |
| `--json-output` | BOOL | false | JSON format output |

### Example Usage

Search for Python jobs:

```bash
uv run python -m src.cli query --keyword "python"
```

Search for high-scoring ML jobs:

```bash
uv run python -m src.cli query --keyword "machine learning" --min-score 85
```

Get JSON output:

```bash
uv run python -m src.cli query --keyword "kubernetes" --json-output true
```

### Output

```
🔍 Searching for 'python' (score 0-100, limit 10)...

Found 8 results:

Rank │ Company          │ Title                    │ Score │ Tech │ Senior
─────┼──────────────────┼──────────────────────────┼───────┼──────┼───────
  1  │ TechCorp         │ Senior Python Engineer   │  92   │  95  │  88
  2  │ DataInc          │ ML Engineer (Python)     │  88   │  90  │  85
  3  │ CloudSys         │ Backend Engineer (Py)    │  80   │  85  │  75

📊 Average score: 86.7
💡 Tip: Use 'export --min-score 85' to get a full report
```

### Display Statistics

```bash
uv run python -m src.cli stats \
  --show-token-usage false
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--show-token-usage` | `false` | Include token usage breakdown |

---

## Advanced Workflows

### Workflow 1: Quick POC (15 minutes)

```bash
# 1. Crawl
uv run python -m src.cli crawl --config config/companies.json
# Output: 26 jobs extracted

# 2. Preprocess (check token savings)
uv run python -m src.cli preprocess --show-estimates
# Output: 88% token reduction

# 3. Assess (auto-confirm in 'all' command)
# (covered by next step)

# 4. Run everything
uv run python -m src.cli all --cv data/cv.json --config config/companies.json
```

Expected time: 10-15 minutes

### Workflow 2: Incremental Assessment

```bash
# Crawl many companies
uv run python -m src.cli crawl --config-dir ./config

# Preprocess
uv run python -m src.cli preprocess --show-estimates

# Review jobs (manual filtering)
uv run python -m src.cli review

# Assess only confirmed
uv run python -m src.cli assess --cv data/cv.json

# Export top matches
uv run python -m src.cli export --min-score 80
```

### Workflow 3: Repeated Assessment

```bash
# Update CV
vim data/cv.json

# Re-assess (skips jobs already assessed, assesses new ones)
uv run python -m src.cli assess --cv data/cv.json

# Export new report
uv run python -m src.cli export --output data/assessments/report_v2.md
```

### Workflow 4: Search and Filter

```bash
# Export full report
uv run python -m src.cli export

# Search for specific skills
uv run python -m src.cli query --keyword "kubernetes"
uv run python -m src.cli query --keyword "python"
uv run python -m src.cli query --keyword "remote"

# Export filtered report
uv run python -m src.cli export --min-score 85 --sort-by location
```

---

## POC: Interactive Job Selector TUI

Interactive Textual-based TUI for browsing and selecting extracted jobs before assessment.

**Purpose**: Visual job review and selection with filtering, before assessment.

### Quick Start

```bash
# Default: Load from data/extracted_jobs, save to data/work/selected.json
python -m src.poc.ui.job_selector

# Custom input directory
python -m src.poc.ui.job_selector --input-dir /path/to/jobs --output-path /path/to/output.json

# Validate input before launching TUI
python -m src.poc.ui.job_selector --input-dir /does/not/exist
# Output: Error: Input directory does not exist: /does/not/exist
# Exit code: 1
```

### Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--input-dir` | `data/extracted_jobs` | Directory containing extracted job JSON files |
| `--output-path` | `data/work/selected.json` | Path where to save selected jobs JSON |

### Features

**Real-time Filtering:**
- Type to filter jobs by title, company, or location
- Case-insensitive search
- Instant results as you type

**Job Selection:**
- Space bar to toggle individual job selection
- `[a]` Select All visible jobs (in current filter)
- `[c]` Clear All selections
- `[e]` Export selected jobs to JSON
- `[q]` Quit TUI

**Status Bar:**
- Shows count of visible jobs vs total
- Shows number of selected jobs
- Real-time updates as you filter and select

**Warning Banner:**
- Displays warnings from loading (missing files, validation errors)
- Non-blocking (warnings don't prevent TUI from launching)

### Usage Examples

**Basic usage (defaults):**
```bash
python -m src.poc.ui.job_selector
# Loads from: data/extracted_jobs/
# Saves to: data/work/selected.json
```

**Custom input directory:**
```bash
python -m src.poc.ui.job_selector --input-dir data/my_jobs
```

**Custom output path:**
```bash
python -m src.poc.ui.job_selector --output-path data/my_selection.json
```

**Both custom:**
```bash
python -m src.poc.ui.job_selector \
  --input-dir data/extracted_jobs \
  --output-path results/selected.json
```

### Workflow Integration

**Typical workflow:**

```bash
# Step 1: Crawl jobs
uv run python -m src.cli crawl --config config/companies.json
# Output: data/extracted_jobs/{company}_jobs.json

# Step 2: Preprocess
uv run python -m src.cli preprocess --show-estimates

# Step 3: Visual selection (with TUI)
python -m src.poc.ui.job_selector
# Manually select jobs of interest

# Step 4: Assess only selected jobs
uv run python -m src.cli assess --cv data/cv.json \
  --input-file results/selected.json

# Step 5: Export report
uv run python -m src.cli export --min-score 75
```

### Error Handling

**Input directory doesn't exist:**
```bash
python -m src.poc.ui.job_selector --input-dir /does/not/exist
# Error: Input directory does not exist: /does/not/exist
# Exit code: 1
```

**Input path is not a directory:**
```bash
python -m src.poc.ui.job_selector --input-dir data/extracted_jobs/company_jobs.json
# Error: Input path is not a directory: data/extracted_jobs/company_jobs.json
# Exit code: 1
```

**Output path is a directory (warning, doesn't fail):**
```bash
python -m src.poc.ui.job_selector --output-path /existing/directory/
# Warning: Output path is a directory, not a file: /existing/directory/
# (TUI still launches - user can export)
```

**Empty input directory (warning shown in TUI):**
```bash
python -m src.poc.ui.job_selector --input-dir /empty/dir
# TUI launches with warning:
# ⚠ 1 warning(s): /empty/dir: Directory not found
```

### Keyboard Commands

| Key | Action |
|-----|--------|
| Space | Toggle selection for current job |
| `a` | Select all visible jobs |
| `c` | Clear all selections |
| `e` | Export selected jobs |
| `q` | Quit TUI |
| ↑/↓ | Navigate job list |
| Type | Filter jobs (real-time) |

### JSON Output Format

Selected jobs are exported as JSON array:

```json
[
  {
    "id": "job_1",
    "title": "Senior Python Developer",
    "company": "TechCorp",
    "location": "Remote",
    "status": "confirmed",
    "description": "5+ years Python...",
    "url": "https://careers.techcorp.com/job/123"
  },
  ...
]
```

---

## Issue #102: Pipeline Control & Visibility Features

Advanced pipeline management with four phases: visibility, filtering, re-review, and timeline tracking.

### Phase 1: Show Pipeline Status Before Review

Display job distribution before interactive review starts:

```bash
uv run python -m src.cli review --merge-all --show-stats
```

**Output example:**

```
================================================================================
📊 PIPELINE STATUS
================================================================================

Total jobs:          127
  • Pending review:  8      ← Ready for review
  • Confirmed:       92     ← Ready for assessment
  • Rejected:        23     ← Will be skipped
  • Assessed:        4      ← Already processed

Applying filters: --skip-rejected=True --skip-assessed=True
  → Will process:  8 jobs
  → Will skip:     119 jobs

Skip breakdown:
    • Rejected:       23
    • Already assessed: 4
```

**Use case:** "Before I start reviewing, show me how many jobs to expect"

---

### Phase 2: Filter Assessment by Score Threshold

Only assess jobs with high confidence matches (by prior CV score):

```bash
# Assess only jobs with 75%+ prior match score
uv run python -m src.cli assess --cv data/cv.json --score-threshold 75

# Query with score filter
uv run python -m src.cli query --keyword "python" --score-threshold 80
```

**How it works:**

1. Jobs without prior assessment → assessed normally
2. Jobs with prior_match_score < threshold → skipped
3. Jobs with prior_match_score >= threshold → assessed

**Output:**

```
📄 Loaded CV from: data/cv.json

🤖 Starting assessment (score threshold: 75%)

ℹ️  Filtering jobs by prior match score...
  Total confirmed: 92
  Skipped (score < 75): 18
  Will process: 74

✅ Processing...
✅ Job 1/74: Senior Python Developer
   Tech: 85/100 | Seniority: 75/100 | Overall: 82/100
   Cost: $0.0006
```

**Use case:** "Don't waste API calls on low-confidence jobs"

---

### Phase 3: Interactive Re-Review with Prior Decisions

Show what you decided before and allow changes:

```bash
# Review with prior decision tracking
uv run python -m src.cli review --interactive --allow-re-review
```

**Interactive flow:**

```
[1/8] Software Engineer - San Francisco
  Company: TechCorp
  Location: San Francisco, CA
  Prior decision: confirmed on 2026-07-01 14:22

  Tokens: 342 | Cost: $0.0021
  ──────────────────────────────────────────
  [Confirm] [Reject] [Skip] [Re-review]: _
```

**What happens:**

- Shows your prior decision with timestamp
- Allows you to keep it or change it
- Audit trail records all changes
- `re_review_audit` table tracks history

**Use case:** "Review decisions are never locked - revisit anytime"

---

### Phase 4: Job Timeline Visibility

Track full job lifecycle from crawl to assessment:

**Timeline shown during review:**

```bash
uv run python -m src.cli review --interactive
```

**Display:**

```
[1/8] Machine Learning Engineer @ TechCorp
────────────────────────────────────────────────────

📅 Timeline:
  Crawled:      2026-07-01 10:00   ← Extracted from career page
  Preprocessed: 2026-07-01 10:05   ← Cleaned & chunked
  Reviewed:     2026-07-01 14:22   ← Status confirmed
  Assessed:     not processed       ← Waiting for Claude

Tokens: 742 (estimated $0.002)
────────────────────────────────────────────────────
[Confirm] [Reject] [Skip]: _
```

**Timestamps recorded at:**

1. **Crawled** - When job extracted from career page
2. **Preprocessed** - When HTML cleaned and text chunked
3. **Reviewed** - When you confirm/reject status
4. **Assessed** - When Claude scores the job

**Automatic recording:**

- `preprocess` command auto-sets preprocessed_at
- Timeline persists across multiple reviews
- Timestamps stored as ISO 8601 (UTC)

**Use case:** "Understand the journey of each job through the pipeline"

---

### Combined Workflow: All Issue #102 Features

Complete end-to-end with all four phases:

```bash
# Step 1: Crawl multiple companies
uv run python -m src.cli crawl --config-dir ./config

# Step 2: Preprocess (auto-records preprocessed_at for all jobs)
uv run python -m src.cli preprocess --show-estimates

# Step 3: Review with stats + timeline + re-review
uv run python -m src.cli review \
  --merge-all \
  --show-stats \
  --skip-rejected \
  --skip-assessed \
  --allow-re-review \
  --interactive

# Step 4: Assess with score threshold filtering
uv run python -m src.cli assess \
  --cv data/cv.json \
  --score-threshold 75

# Step 5: Export results
uv run python -m src.cli export --min-score 80
```

**What you see at each step:**

```
Phase 1 - Show Stats:
  → "Total jobs: 127, Pending: 8, Will process: 8"

Phase 3 - Review with Timeline:
  → Each job shows its crawled/preprocessed/reviewed timestamps
  → Prior decisions shown with option to re-review

Phase 2 - Score Filtering:
  → "Skipped 18 jobs with score < 75%"
  → "Processing 74 high-confidence jobs"

Result:
  → Only high-quality matches in final report
```

---

### Selective Re-Assessment Workflow

Re-crawl some companies and reassess selectively:

```bash
# Step 1: Re-crawl specific company (updates crawled_at)
uv run python -m src.cli crawl --config config/techcorp.json

# Step 2: Preprocess new jobs
uv run python -m src.cli preprocess --show-estimates

# Step 3: Review only newly crawled jobs (by date)
uv run python -m src.cli review \
  --merge-all \
  --skip-before-date 2026-07-05 \
  --skip-assessed \
  --interactive

# Step 4: Assess
uv run python -m src.cli assess --cv data/cv.json
```

**Timeline tracking enables this:**

- New jobs have fresh crawled_at timestamps
- `--skip-before-date` filters to only new ones
- Old assessments preserved in database

---

### Common Issue #102 Patterns

**Pattern 1: High-Confidence Workflow (Minimal API Cost)**

```bash
uv run python -m src.cli review --merge-all --show-stats
# Review jobs, focus on high-quality ones

uv run python -m src.cli assess --cv data/cv.json --score-threshold 80
# Only assess jobs with 80%+ prior match

uv run python -m src.cli export --min-score 75
# Show only top matches
```

**Cost:** ~$0.01 for 100 jobs (vs $0.30 without filtering)

---

**Pattern 2: Iterative Refinement (Multi-Review)**

```bash
# First pass: Quick review
uv run python -m src.cli review --merge-all --interactive

# Assess
uv run python -m src.cli assess --cv data/cv.json

# Second pass: Re-review with prior decisions visible
uv run python -m src.cli review --merge-all --allow-re-review --interactive

# Final assess (only new jobs)
uv run python -m src.cli assess --cv data/cv.json
```

**Benefit:** Change decisions without losing history

---

**Pattern 3: Quality Gate (No Low Scores)**

```bash
# Review all jobs
uv run python -m src.cli review --merge-all --show-stats --interactive

# Assess with confidence threshold
uv run python -m src.cli assess --cv data/cv.json --score-threshold 70

# Export only 80+ matches
uv run python -m src.cli export --min-score 80
```

**Result:** Only highest-quality opportunities in report

---

## Common Patterns

### Pattern 1: Single Command (Easiest)

```bash
uv run python -m src.cli all --cv data/cv.json --config config/companies.json
```

**Pros:** One command, automatic workflow
**Cons:** Less control, must confirm all jobs

### Pattern 2: Phase-by-Phase (Recommended)

```bash
uv run python -m src.cli crawl --config config/companies.json
uv run python -m src.cli preprocess --show-estimates
uv run python -m src.cli review
uv run python -m src.cli assess --cv data/cv.json
uv run python -m src.cli export --min-score 75
```

**Pros:** Full control, can inspect outputs
**Cons:** More commands to run

### Pattern 3: Batch Processing

```bash
# Process multiple company directories
uv run python -m src.cli crawl --config-dir ./config/tech-companies
uv run python -m src.cli crawl --config-dir ./config/finance-companies

# Preprocess all at once
uv run python -m src.cli preprocess

# Review and assess
uv run python -m src.cli review
uv run python -m src.cli assess --cv data/cv.json

# Generate separate reports
uv run python -m src.cli export --output data/assessments/tech_report.md
uv run python -m src.cli export --output data/assessments/finance_report.md
```

---

## Data Flow & Files

```
CONFIG FILES:
  config/companies.json ─────┐
  config/other.json ─────────┤
                             ↓
PHASE 1 (CRAWL):
  ┌──────────────────────────────────┐
  │ Browser Automation               │
  │ (Playwright)                     │
  └──────────────────────────────────┘
                             ↓
  data/extracted_jobs/
  ├── companya_jobs.json ◄── 26 raw jobs
  ├── companyb_jobs.json ◄── 19 raw jobs
  └── ...

PHASE 2 (PREPROCESS):
  ┌──────────────────────────────────┐
  │ Clean HTML                       │
  │ Chunk Text (semantic)            │
  │ Count Tokens (tiktoken)          │
  └──────────────────────────────────┘
                             ↓
  data/extracted_jobs/
  └── preprocessed_jobs.json ◄── 45 chunked jobs

PHASE 3 (REVIEW):
  ┌──────────────────────────────────┐
  │ Interactive CLI Review           │
  │ User confirms/rejects            │
  └──────────────────────────────────┘
                             ↓
  data/extracted_jobs/
  └── preprocessed_jobs.json ◄── status=confirmed/rejected

CV INPUT:
  data/cv.json ──────────────┐
  data/cv.txt ───────────────┤
                             ↓
PHASE 4 (ASSESS):
  ┌──────────────────────────────────┐
  │ Claude 3.5 Sonnet API            │
  │ Multi-category scoring           │
  │ Cost tracking                    │
  └──────────────────────────────────┘
                             ↓
  data/ats_playground.db ◄── SQLite assessments

PHASE 5 (EXPORT):
  ┌──────────────────────────────────┐
  │ Generate Markdown Report         │
  │ Filter, sort, analytics          │
  └──────────────────────────────────┘
                             ↓
  data/assessments/
  ├── report.md ◄── Full report
  ├── report_summary.md
  └── ...

SEARCH:
  data/ats_playground.db ──┐
                           ↓
                    ┌──────────────────┐
                    │ Keyword search   │
                    │ Score filtering  │
                    └──────────────────┘
                           ↓
                      Table output
                      JSON output
```

---

## Cost & Performance

### Typical Costs

| Phase | Cost | Time |
|-------|------|------|
| Crawl 26 jobs | Free | 30-60s |
| Preprocess 26 | Free | <2s |
| Review 26 | Free | 2-3m |
| Assess 26 | $0.02 | 5-10m |
| Export | Free | <1s |
| **TOTAL** | **$0.02** | **10-15m** |

vs. Traditional approach: **$0.47** (89% savings)

### Token Usage

```
Per job:
  Raw HTML:          6,000 tokens
  Preprocessed:      700 tokens
  Assessment:        1,200 tokens
  Total:             1,900 tokens

26 jobs:
  Total tokens:      49,400
  Cost at $0.003/1K: $0.15
  (Claude 3.5 Sonnet pricing)
```

---

## Environment Variables

```bash
# Required
ANTHROPIC_API_KEY="..."

# Optional (defaults shown)
LOG_LEVEL="INFO"
DB_PATH="data/ats_playground.db"
```

Set in `.env` file:

```bash
cp .env.example .env
# Edit and add:
# export ANTHROPIC_API_KEY="..."
```

---

## Error Handling

### Common Errors & Fixes

**Error: "Config file not found"**
```bash
# Fix: Use correct path
uv run python -m src.cli crawl --config config/companies.json
```

**Error: "No companies found"**
```bash
# Fix: Check config file format
cat config/companies.json | grep "companies"
```

**Error: "SQLite locked"**
```bash
# Fix: Only one assess process at a time
# Wait for other processes to finish
```

**Error: "Rate limit exceeded"**
```bash
# Fix: Auto-retries. Wait 1 minute and re-run
# (Restarts from where it failed)
```

**Error: "spaCy model not found"**
```bash
uv run python -m spacy download en_core_web_md
```

---

## Testing Commands

Verify setup without using API:

```bash
# Test crawl (mock mode)
uv run python -m src.cli crawl --mock true

# Test preprocessing
uv run python -m src.cli preprocess --show-estimates

# Test export (with existing data)
uv run python -m src.cli export --min-score 80
```

---

## Tips & Best Practices

1. **Use `--config-dir`** for multiple companies (easier to manage)
2. **Always review jobs** before assessment (saves money)
3. **Use `--min-score`** when exporting (focus on good matches)
4. **Check token estimates** with `--show-estimates` (predict costs)
5. **Save API key in `.env`** (don't pass on command line)
6. **Monitor `.db` file size** (deletes old data if >100MB)

---

## Phase 6: INTEGRITY - Database Health Check & Repair

Detect and fix corrupted data: orphaned records, invalid scores, malformed JSON.

**See [INTEGRITY.md](./INTEGRITY.md) for comprehensive guide.**

### Quick Start

```bash
# Health check
uv run python -m src.cli integrity check

# Auto-repair (safe operations)
uv run python -m src.cli integrity repair --no-dry-run --force

# Purge invalid assessments (with backup)
uv run python -m src.cli integrity purge --type invalid_scores \
  --backup-dir ./backups --no-dry-run --force
```

### When to Run

- **After crawl**: Verify no duplicates
- **After assess**: Verify no invalid scores or malformed JSON
- **Before export**: Ensure clean data in report

---

## Document Version

- **Version:** 1.2
- **Last Updated:** 2026-09-02
- **Status:** Complete
- **Coverage:** Phases 1-6 (crawl, preprocess, review, assess, export, integrity) + POC job selector with options, examples, workflows
