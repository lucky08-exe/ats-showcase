---
name: assess-jobs
description: Verify extracted jobs and run Claude assessment for CV fit scoring
dependencies:
  - "anthropic >= 0.20"
  - "tiktoken >= 0.5.0"
  - "pydantic >= 2.5"
phases:
  - verify
  - assess
cost_estimate: "$0.50-5.00 per 100 jobs (Claude API)"
triggers:
  - "review jobs"
  - "assess candidates"
  - "score jobs"
  - "evaluate cv fit"
execution: streaming
allowed_tools:
  - Read
  - Bash(uv run *)
  - Bash(python *)
  - Bash(pytest *)
  - Bash(tail *)
---

# Review + Assess Workflow

## Workflow: Verify → Assess → Export Results

Confirm extracted jobs interactively, then send to Claude for assessment. Export results to markdown.

### Prerequisites

Completed [[crawl-jobs]] workflow. Jobs in SQLite with `clean_text` and estimated costs.

Set `ANTHROPIC_API_KEY` in `.env`:
```bash
# Create .env if not exists
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-...
```

### Step 1: Interactive Verification

```bash
uv run python -m src.cli review --interactive
```

**Interactive flow for each job:**
```
Title: Senior Python Developer
Location: Remote
Estimated tokens: 650
Estimated cost: $0.002

[C]onfirm  [E]dit  [R]eject  [Q]uit?
```

Job status transitions:
- `[C]onfirm` → `status: confirmed` (will be assessed)
- `[R]eject` → `status: rejected` (skipped in assess)
- `[E]dit` → `status: pending_edit` (manual SQL edit if needed)

**Cost transparency:** Total show at end:
```
Confirmed: 8 jobs
Estimated total cost: $0.016
Proceed with assessment? [y/n]
```

### Step 2: Run Assessment

```bash
uv run python -m src.cli assess --cv data/cv.json
```

**Output:** Each job gets assessment with:
- `match_score` (0–100)
- `categories` (tech_skills, seniority, location_fit, etc.)
- `reasoning` (why this score)
- Actual tokens used + actual cost

Tracks cost_tracking table: `estimated_tokens` vs `actual_tokens`.

**Key behavior:**
- Only assesses jobs with `status: confirmed` (default)
- Respects Claude rate limits (10 RPM, 50k TPM)
- Retries transient errors (429, 5xx) with exponential backoff

### Step 3: Export Report

```bash
uv run python -m src.cli export --output data/assessments/report.md
```

**Report includes:**
- Summary: total jobs, avg score, total cost
- Jobs sorted by match_score descending
- Each job: title, company, score, reasoning excerpt

Example:
```markdown
# Assessment Report

Total: 8 jobs assessed
Average match score: 78
Total cost: $0.016

## High Match (≥80)
### Senior Python Developer (Company A)
Score: 88
Reasoning: Strong technical match, 5+ years experience...
```

---

## Verification

```bash
# Check confirmed jobs before assess
uv run python -m src.cli query --keyword "python" --status confirmed

# Show token usage stats
uv run python -m src.cli stats --show-token-usage

# View final report
cat data/assessments/report.md

# Watch logs for errors
tail -f logs/app.log
```

## Error Handling

- **API key missing?** Set `ANTHROPIC_API_KEY` in `.env`
- **Rate limited (429)?** Built-in backoff handles it. Check logs.
- **SQLite locked?** Only one assess process at a time. Wait for other to finish.
- **Assessment JSON invalid?** Logged as error. Check logs for details.

## Related Skill

← [[crawl-jobs]] for crawl + preprocess workflow
