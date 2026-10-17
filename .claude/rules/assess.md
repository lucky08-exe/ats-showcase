---
paths:
  - "src/assessment/**"
  - "src/llm/**"
  - "tests/assessment/**"
---

# Assess Phase Rules

Claude API integration, prompt design, rate limiting, error handling, cost tracking.

## Claude API Client Pattern

**Provider interface:**
- `assess_job(cv, job)` → `Assessment` object
- Includes rate limiting, retries, token tracking
- Returns assessment + metadata (tokens used, cost)

## Prompt Design

**Assessment prompt structure:**
1. System: "You are an expert recruiter. Assess CV fit for this job."
2. Context: CV text + job description
3. Output format: JSON with match_score, categories, reasoning

**Example categories:**
- Technical skills match (0–100)
- Seniority alignment (0–100)
- Location preferences (yes/no)
- Overall fit (0–100)

**Always validate JSON output** before storing.

## Rate Limiting & Retries

**Claude limits:**
- ~10 RPM (requests per minute)
- ~50k TPM (tokens per minute)

**Catch transient errors:**
- 429 (rate limit): Backoff → retry
- 500, 502, 503 (server error): Backoff → retry
- 401 (auth): Fail immediately, check API key

## Cost Tracking

**Always log:**
```python
{
  "job_id": "...",
  "estimated_tokens": 650,
  "actual_tokens": 673,
  "estimated_cost": 0.00195,
  "actual_cost": 0.00202,
  "api_call_time_ms": 1250
}
```

Compare actual vs estimated. Use for future token prediction refinement.

## Verification Commands

See [Assessment Commands](./_common.md#assessment-api) for assess, token usage, and single-job test commands.

## Important Notes

- See [Core Constraints](../../.claude/CONSTRAINTS.md#never-rules-critical) (constraint: don't assess unconfirmed jobs). Use `--confirmed-only` (default) to filter.
- **API key required**: Set `ANTHROPIC_API_KEY` in `.env`. Loaded automatically.
- **Cost estimates may differ**: tiktoken vs Claude's actual token count. Logged in cost_tracking.
