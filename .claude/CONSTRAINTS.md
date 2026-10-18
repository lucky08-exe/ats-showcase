# ATS Showcase: Core Constraints

Single source of truth for NEVER and ALWAYS rules. Extract from CLAUDE.md + phase rules.

---

## NEVER Rules (Critical)

1. **Don't assess unconfirmed jobs** – Use `--confirmed-only` (default) to filter status
2. **Don't run multiple assessment processes concurrently** – SQLite single-writer; use queue/single-process
3. **Don't send raw HTML to Claude** – Always preprocess (clean + chunk). Raw HTML ~6,000 tokens
4. **Don't skip verification** – Always show user cost estimate before API calls
5. **Don't force uniform token counts in chunks** – Splits at sentence boundaries. Chunks vary 100–600 tokens intentionally
6. **Don't re-assess already reviewed jobs** – Use `--skip-assessed`, `--skip-rejected` flags
7. **Don't commit directly to main** – All changes via feature branches. Pre-commit hook enforces
8. **Don't hardcode API calls** – Use LLMProvider abstraction for Claude integration

---

## ALWAYS Rules (Mandatory)

1. **Always show cost estimate before LLM calls** – Interactive verification, token count + USD cost
2. **Always count tokens before API calls** – Use tiktoken, track estimated vs actual
3. **Always use async context manager for browser** – `async with BrowserManager() as browser` ensures cleanup

---

**Last Updated:** 2026-08-09 (Issue #245 Phase A)
