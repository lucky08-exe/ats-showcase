---
paths:
  - "src/verification/**"
---

# Verify Phase Rules

Interactive CLI for user confirmation, cost transparency, rejection flow.

## User Verification Flow

**Before assessment, always show:**
1. Extracted job (title, location, company)
2. Clean text preview (first 500 chars)
3. Estimated tokens + USD cost
4. User choice: [Confirm] / [Edit] / [Reject]

```bash
uv run python -m src.cli review --interactive
```

## Status Tracking

Job status transitions:
```
pending_review (default after crawl)
  ↓ User confirms or rejects
├→ confirmed (assessed by default)
├→ rejected (skipped in assess)
└→ pending_edit (user wants to modify)
```

**Assessment only runs on "confirmed" jobs by default.**

Use `--confirmed-only` flag to enforce (default: true). Omit for testing:
```bash
uv run python -m src.cli assess --cv data/cv.json
# Only assesses status == "confirmed"
```

## Cost Transparency

See [Core Constraints](../../.claude/CONSTRAINTS.md#always-rules-mandatory) (constraint: always show cost estimate before LLM calls). Example format:
```
Title: Senior Python Developer
Location: Remote
Estimated tokens: 650
Estimated cost: $0.002
Proceed? [y/n]
```

Track actual cost after assessment. Compare in cost_tracking table.

## Verification Commands

See [Verification Commands](./_common.md#verification-interactive) for interactive review, cost estimates, and status query commands.

## Important Notes

- **Don't skip verification in production**: Low-quality extractions waste API quota.
- **Rejections are permanent**: Once rejected, job won't appear in assess. Update status manually in DB if needed.
- **Edit flow incomplete**: Future work. Currently, edits done via SQL directly.
