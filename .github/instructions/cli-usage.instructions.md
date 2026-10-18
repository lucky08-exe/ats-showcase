---
applyTo: 'src/cli.py'
---

# CLI Usage Instructions

CLI command reference for ATS Showcase. Use when working with `uv run python -m src.cli` commands.

---

## Command Categories

### Workflow Commands (Full Pipeline)

**Run entire pipeline in one command:**
```bash
uv run python -m src.cli --all \
  --cv data/cv.json \
  --config config/companies.json

# Or with directory of configs:
uv run python -m src.cli --all \
  --cv data/cv.json \
  --config-dir ./config
```

### Halt at Phase (Cost Control)

Stop workflow before expensive phases:

```bash
# Common: Stop before assess phase
uv run python -m src.cli all --cv data/cv.json --config config/companies.json --up-to review

# Other phases
uv run python -m src.cli all --cv data/cv.json --config config/companies.json --up-to crawl
uv run python -m src.cli all --cv data/cv.json --config config/companies.json --up-to preprocess
uv run python -m src.cli all --cv data/cv.json --config config/companies.json --up-to assess
```

**Valid phases:** `crawl`, `preprocess`, `review`, `assess`, `export`
**Default:** No `--up-to` runs all phases

### Phase Commands (Individual Steps)

**1. Crawl** – Extract jobs from company career pages:
```bash
uv run python -m src.cli crawl --config config/companies.json
uv run python -m src.cli crawl --config-dir ./config
```

**2. Preprocess** – Clean HTML, estimate tokens/cost:
```bash
uv run python -m src.cli preprocess --show-estimates
```

**3. Review** – Interactive user verification:
```bash
uv run python -m src.cli review --interactive
uv run python -m src.cli review --merge-all  # Review all jobs at once
uv run python -m src.cli review --mode all  # Re-review already-reviewed jobs
uv run python -m src.cli review --skip-rejected  # Skip previously rejected
```

**4. Assess** – Send to Claude API for scoring:
```bash
uv run python -m src.cli assess --cv data/cv.json
uv run python -m src.cli assess --cv data/cv.json --mode new-only  # Only unassessed
uv run python -m src.cli assess --cv data/cv.json --score-threshold 75  # Min prior score
```

**5. Export** – Generate markdown report:
```bash
uv run python -m src.cli export --output data/assessments/report.md
```

### Query Commands

**Search by keyword:**
```bash
uv run python -m src.cli query --keyword "python" --min-score 75
uv run python -m src.cli query --keyword "remote" --status confirmed
```

**View statistics:**
```bash
uv run python -m src.cli stats --show-token-usage
```

---

## Common Flags

### Review Mode Filtering (Issue #116)

Control which jobs are reviewed:

```bash
--mode new-only      # Only unreviewed jobs (default)
--mode all           # All jobs, including previously reviewed
```

### Status Filtering

Skip certain job statuses:

```bash
--skip-rejected      # Skip rejected jobs (default: True)
--skip-assessed      # Skip already assessed (default: True)
```

### Date Filtering

Selective re-processing by crawl date:

```bash
--skip-before-date 2026-07-01  # Only jobs crawled on/after date
--since 2026-07-05             # Alias for --skip-before-date
```

### Score Filtering

Filter by prior CV match score:

```bash
--score-threshold 75  # Only jobs with prior_match_score >= 75
```

### Re-Review Mode

Allow changing previously-made decisions:

```bash
--allow-re-review  # Shows prior decisions, allows status change
```

---

## Combined Examples

**Selective re-assessment:**
```bash
# Only assess jobs crawled after July 1, skip low scores
uv run python -m src.cli assess --cv data/cv.json \
  --mode new-only \
  --since 2026-07-01 \
  --score-threshold 60
```

**Re-review with filtering:**
```bash
# Re-review all jobs, skip rejected ones
uv run python -m src.cli review --merge-all --mode all --skip-rejected
```

**Full workflow with selective crawl:**
```bash
# Crawl new configs, skip previously rejected
uv run python -m src.cli --all \
  --cv data/cv.json \
  --config-dir ./config \
  --skip-rejected
```

---

## Configuration Files

### Company Configuration (companies.json)

```json
{
  "companies": [
    {
      "name": "Company Name",
      "url": "https://careers.company.com/jobs",
      "enabled": true,
      "selectors": {
        "job_title": ".job-title",
        "job_location": ".job-location",
        "job_description": ".job-description"
      },
      "crawl_delay": 2000,
      "max_retries": 3
    }
  ]
}
```

**Key Options:**
- `enabled`: Skip company if False (useful for config directories)
- `crawl_delay`: Milliseconds between requests (rate limiting)
- `max_retries`: Network error retry attempts

### CV File (cv.json)

```json
{
  "name": "Your Name",
  "email": "you@example.com",
  "skills": ["Python", "React", "PostgreSQL"],
  "years_experience": 5,
  "current_role": "Senior Engineer",
  "preferences": {
    "location": ["Remote", "San Francisco"],
    "min_salary": 150000
  }
}
```

---

## Exit Codes

- `0`: Success
- `1`: User error (invalid config, missing file)
- `2`: Internal error (API failure, database corruption)

---

## Environment Variables

Set before running CLI:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export LOG_LEVEL=debug              # default: info
export DATABASE_PATH=data/ats_playground.db
```

---

## Troubleshooting

**Config not found:**
```
Error: Config file not found: ./config/companies.json
→ Check path and permissions
```

**API rate limit (429):**
```
Retrying with backoff (attempt 2/3)...
→ CLI automatically retries; increase crawl_delay if persistent
```

**Database locked:**
```
Error: Database is locked
→ Only one assessment process at a time (SQLite single-writer)
```

See [docs/COMPATIBILITY.md](../../docs/COMPATIBILITY.md) for more troubleshooting.

---

**Last Updated**: 2026-07-10
**Related**: [CLAUDE.md](../../CLAUDE.md), [.claude/rules/cli.md](../../.claude/rules/cli.md)
