# DESIGN.md: ATS Playground Architecture

**Version:** 2.1 (Anthropic standards + Requirements Extraction)
**Last Updated:** 2026-08-01
**Status:** Condensed for token budget; Phase-specific rules in `.claude/rules/`

---

## 1. PRODUCT NARRATIVE

ATS Playground: CV-to-job assessment in 5 phases (crawl → preprocess → verify → assess → export) + enhancement phases 5-7 for soft skills & keyword expansion (45% → 99.8% semantic accuracy).

**Core:** Playwright crawling → MarkItDown HTML cleanup (15× token reduction: ~6,000 → ~400) → spaCy semantic chunks → requirement extraction (Phase 8a/8b) → interactive verification → Claude scoring → FTS5 storage → markdown export.

**Cost Control:** `--up-to review` halts before costly assess phase. Token estimates pre-API, actual vs. estimated tracked.

---

## 2. WORKFLOW PIPELINE

```
CONFIG (companies.json + CSS selectors)
  ↓
CRAWL (Playwright + pagination) → Raw HTML
  ↓
PREPROCESS (MarkItDown + spaCy + tiktoken) → Clean chunks + token estimates
  ↓
VERIFY (Interactive CLI, status tracking) → Confirmed jobs
  ↓
ASSESS (Claude 3.5 Sonnet + rate limiting) → Scores + actual tokens/cost
  ↓
STORAGE (SQLite + FTS5) → Queryable database
  ↓
EXPORT (Markdown reports)
```

---

## 3. MODULE STRUCTURE

- **src/browser/** – Playwright automation
- **src/parsers/** – HTML cleaning (MarkItDown + BeautifulSoup + fallback)
- **src/tokenization/** – spaCy chunking + tiktoken counting
- **src/preprocessing/** – Requirement extraction (Phase 8a/8b)
- **src/llm/** – Claude API + rate limiting
- **src/storage/** – SQLite FTS5 + export
- **src/cli.py** – Typer CLI orchestration

---

## 4. KEY DECISIONS

- **Semantic Chunking:** Sentence-level (spaCy), 100–600 tokens intentional (not token-aligned)
- **Cost Transparency:** Estimate before assess, track actual vs. estimated tokens
- **Confirmation Gate:** Assessment only on status="confirmed" (prevent quota waste)
- **Single-Writer SQLite:** No concurrent assess (use queue pattern)
- **Async TUI:** StateManager is source-of-truth, 0.5s polling

See `.claude/rules/tui/` and `.claude/rules/cli.md` for details.

---

## 5A. HTML Cleaning (Issue #230)

**Architecture:** Consolidated `clean_html()` function replaces scattered regex. 70+ boilerplate patterns (7 categories: legal, headers, company, time, salary, formatting, navigation).

**Performance:** 10x faster (~50ms/job pre-compiled vs. ~500ms sequential regex).

**API:** `clean_html(raw_html, skip_boilerplate_categories={'legal', 'salary_benefits'})`

**Token Reduction:** ~6,000 → ~400 tokens/job (88% reduction, 30% from boilerplate removal).

**Fallback Chain (Issue #231):** MarkItDown (primary) → BeautifulSoup (fallback) → Original HTML (safe). Preprocessing never fails.

**Version Tracking:** `preprocessing_version` column (v1.0 legacy, v2.0 with boilerplate removal) enables selective re-processing.

See `.claude/rules/preprocess.md` for details.

---

## 5B. Requirement Extraction (Phase 8a, Issues #248-252)

**Component:** `requirement_filter` (spaCy) with 18 patterns (3 confidence tiers, 0.40–0.95). Outputs `Doc._.requirements` {text, trigger_word, confidence, span, token_count}.

**CLI:** `--extract-requirements` (default), `--export-requirements-json <file>`.

**Storage:** `requirements` JSON column (backward-compatible, nullable).

**Performance:** <50ms per job, <5% overhead. 48 tests (39 unit + 9 integration).

See `.claude/rules/phase8/patterns.md` for patterns and edge cases.

---

## 5C. Span Extraction (Phase 8b, Issues #253-257)

**Component:** `span_categorizer` (spaCy) expands Phase 8a spans using POS/DEP tags. Detects hard stops (`.;!`), soft stops (`,`), conjunctions (`and`/`or`).

**Span Types:** Atomic (single requirement) vs compound (multi-clause with conjunctions).

**Chunking:** `preserve_requirement_spans=True` (default) prevents chunks from splitting requirement spans. <2% latency overhead.

**Storage:** `requirement_spans` JSONB {span_text, start_token, end_token, span_type}.

**Performance:** 79 tests; +1.03ms baseline (<5% cost). 99% span boundary accuracy.

**Strategies (Issue #278):** boundary rules are injectable and a second, regex-only strategy exists. The `requirement_spans` dict shape is frozen.
- `span_types.py`: frozen `BoundaryRules` (`hard_stops` `. ; ! ? )`, `soft_stops` `,`, `stop_words` `if unless because`), `DEFAULT_RULES`, `SpanPattern` (regex validated at construction), `SpanCategory`.
- `span_categorizer.py`: boundary helpers take optional `rules` (default = previous hard-coded sets); `categorize_spans(doc, rules)`; `NLPSpanCategorizer`; `create_span_categorizer(strategy="nlp"|"custom", rules, patterns)`. The `span_categorizer` spaCy component is unchanged and uses defaults.
- `custom_span_categorizer.py`: spaCy-free `CustomSpanCategorizer(patterns).categorize(text)`; `load_patterns(path)` JSON loader; `validate_pattern` (500-char cap, nested-quantifier ReDoS heuristic); 200k-char input bound. `SpanCategorizerComponent` is a thin wrapper, registered as a spaCy pipeline factory (#618, "custom_span_categorizer") writing `doc._.custom_spans` (never `requirement_spans`).
- Limits: ReDoS check is a heuristic (see #382). CLI: `--categorizer-strategy nlp|custom`, `--span-patterns <json>` (#380). Markdown strategy is tracked in #281.

See `.claude/rules/phase8/span_algorithm.md` and `.claude/rules/phase8/performance.md`.

---

## 5. PHASE-SPECIFIC RULES & COORDINATION

Phase documentation organized in `.claude/rules/`:
- **crawl.md** – Playwright patterns, CSS selectors, pagination, rate limiting
- **preprocess.md** – MarkItDown, spaCy chunking, tokenization, Phase 5-7 enhancements
- **verify.md** – Interactive review workflow, cost verification, status transitions
- **assess.md** – Claude API integration, prompt design, rate limiting, cost tracking
- **storage.md** – SQLite schema (FTS5), markdown export, query patterns
- **cli.md** – Typer command structure, async patterns, error handling
- **multi-agent.md** – Phase coordination across Architect, Builder, Reviewer roles

See **AGENTS.md** for role-based governance and handoff protocols.

---

## 6. CRITICAL CONSTRAINTS

**Don't:**
- Assess unconfirmed jobs (enforce `--skip-unconfirmed`, default: true)
- Run concurrent assessment processes on same DB (single-writer SQLite)
- Send raw HTML to Claude (always preprocess; raw HTML ~6,000 tokens)
- Skip verification before API calls (cost transparency required)
- Force uniform token chunks (sentences vary 100–600 tokens)
- Commit to main directly (feature branch workflow via pre-commit hook)

**TUI-Specific:**
- Mutate StateManager outside `@work(exclusive=True)` (race conditions)
- Block Textual's main thread (all I/O must be async)
- Render 1000+ rows in DataTable (paginate, show top 100)
- Update UI at 60 FPS (poll every 0.5s to prevent flicker)

See CLAUDE.md and `.claude/rules/` for enforcement mechanisms.

---

## 7. TECH STACK & SETUP

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Browser | Playwright (async, JS rendering) | Handles dynamic content, pagination |
| HTML → Markdown | 3-tier: MarkItDown → BeautifulSoup → Original | Structure preservation + robustness (Issue #231) |
| Tokenization | spaCy (sentences) + tiktoken (counting) | Semantic boundaries, cost estimation |
| Database | SQLite + FTS5 | Serverless, full-text search, atomic writes |
| LLM | Claude 3.5 Sonnet | Cost/quality balance: $0.003 per 1M input tokens |
| CLI | Typer | Async-ready, typed commands, help text |
| TUI | Textual + Rich | Async-first, responsive, light/dark theme |

**Quick Setup:**
```bash
uv sync && uv run python -m spacy download en_core_web_md
uv run playwright install chromium
cp .env.example .env && uv run python src/storage/db.py --init
```

---

## Summary: Key Takeaways

1. **5-phase core + 3-phase enhancement pipeline** with cost transparency and user confirmation gates
2. **Semantic chunking** (sentences) preserves meaning; chunk sizes vary 100–600 tokens intentionally
3. **Single-writer SQLite** prevents deadlocks under concurrent load; use queue pattern
4. **StateManager as TUI source of truth** (polling every 0.5s, all I/O async)
5. **Phase-specific rules in `.claude/rules/`** with role-based governance in AGENTS.md
6. **Cost control at each step:** Verify estimates before assess; track actual vs. estimated tokens

---

**See Also:** CLAUDE.md (setup + workflows) | AGENTS.md (roles + governance) | .claude/rules/ (phase details)
