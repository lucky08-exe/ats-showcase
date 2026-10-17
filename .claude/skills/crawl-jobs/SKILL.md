---
name: crawl-jobs
description: Fetch job listings via Playwright and prepare for assessment (crawl + preprocess)
dependencies:
  - "playwright >= 1.40"
  - "spacy >= 3.0"
  - "markitdown >= 0.0.1"
phases:
  - crawl
  - preprocess
cost_estimate: "$0.00 (local processing only)"
triggers:
  - "crawl jobs"
  - "browse careers pages"
  - "fetch job listings"
  - "scrape companies"
execution: atomic
allowed_tools:
  - Read
  - Bash(uv run *)
  - Bash(python *)
  - Bash(ls *)
  - Bash(find *)
  - Bash(grep *)
---

# Crawl + Preprocess Workflow

## Workflow: Crawl → Preprocess → Estimate Costs

Fetch raw HTML from career pages, clean text, chunk by sentences, estimate tokens before assessment.

### Prerequisites

```bash
# Install dependencies
uv sync

# Download NLP model
uv run python -m spacy download en_core_web_md

# Download Chromium
uv run playwright install chromium

# Create config file
cat > config/companies.json << 'EOF'
{
  "companies": [
    {
      "name": "Company Name",
      "url": "https://careers.company.com/jobs",
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
EOF
```

### Step 1: Crawl & Extract HTML

```bash
uv run python -m src.cli crawl --config config/companies.json
```

**Output:** Jobs stored in SQLite with `status: pending_review`, `raw_html` populated.

**Troubleshooting:**
- Playwright timeout? Increase timeout in config + check selectors in browser DevTools
- Rate limited? Check crawl_delay, add exponential backoff in config
- No jobs found? Verify CSS selectors match current website HTML

### Step 2: Preprocess & Estimate Costs

```bash
uv run python -m src.cli preprocess --show-estimates
```

**Output:** Jobs enriched with `clean_text`, `chunks`, `estimated_tokens`, `estimated_cost`.

Shows estimated cost before assessment:
```
Job 1: Senior Python Developer
  Estimated tokens: 650
  Estimated cost: $0.002
Job 2: ...
Total: 5 jobs, 3,250 tokens, $0.010
```

**Key decisions:**
- Chunks split at sentence boundaries (spaCy), not token-aligned
- Target ~400 tokens per chunk
- Cost estimates use Claude 3.5 Sonnet input rate ($0.003 / 1M tokens)

### Step 3: Review Costs & Proceed

Before assessment, review total estimated cost. If within budget, proceed to [[assess-jobs]].

If cost too high:
- Reduce crawl scope (fewer companies)
- Increase min_score threshold (only assess promising jobs)
- Batch assessment across multiple runs

---

## Verification

```bash
# Check crawled jobs
uv run python -m src.cli query --keyword "python" --status pending_review

# Estimate costs for review
uv run python -m src.cli preprocess --show-estimates

# Watch for errors
tail -f logs/app.log
```

## Related Skill

→ [[assess-jobs]] for assessment workflow
