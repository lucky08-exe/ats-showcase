# CLAUDE.md

@AGENTS.md

ATS Showcase: CV-to-jobs assessment system. Crawls career pages, preprocesses HTML, sends to Claude for scoring.

**See [Core Constraints](.claude/CONSTRAINTS.md) for NEVER/ALWAYS rules.**

---

## Git Workflow & CI

Feature branches enforced. Pre-commit runs ruff, mypy, secrets.

```bash
git checkout -b feat/issue-XXX-description
bash .claude/scripts/run-local-ci.sh          # Pre-commit checks
bash .claude/scripts/run-local-ci.sh --tests  # Include tests
```

Setup: `bash .claude/skills/pre-commit-enforce/setup.sh`.

---

## Setup

```bash
uv sync
uv run python -m spacy download en_core_web_md
uv run playwright install chromium
cp .env.example .env  # Set ANTHROPIC_API_KEY
uv run python src/storage/db.py --init
```

---

## Quick Workflow

```bash
# Full pipeline (Sonnet, $3/$15 per 1M)
uv run python -m src.cli all --cv data/cv.json --config config/companies.json

# Cheaper version (Haiku, $0.80/$4 per 1M)
uv run python -m src.cli all --cv data/cv.json --config config/companies.json --model haiku

# Stop before assess (cost verify)
uv run python -m src.cli all --cv data/cv.json --config config/companies.json --up-to review
```

**HTML Preprocessing:** Phases 1-4 complete (Issue #230). See [DESIGN.md](DESIGN.md) for details. [CLI reference](.github/instructions/cli-usage.instructions.md).

---

## Verification Commands

```bash
bash .claude/scripts/run-local-ci.sh              # Pre-commit checks + mypy
uv run pytest tests/ -v                          # All tests
uv run pytest tests/ -v --cov=src               # With coverage
uv run python -m src.cli query --keyword "python" --min-score 75  # Query DB
uv run python -m src.cli stats --show-token-usage              # Cost breakdown
tail -f logs/app.log                             # Watch logs
```

---

## Session State Preservation

**Caveman Mode Hook**: Session insights auto-append to CLAUDE.md on termination (if enabled).
- `stop caveman` or `normal mode`: Reverts Caveman Mode (terse output).
- Enabled via `.claude/hooks/post-session-state.sh` (auto-triggers on exit).

**Manual State Save**: Run `/remember` or append directly to CLAUDE.md with session learnings.

---

## Reference

**Docs**: [Constraints](.claude/CONSTRAINTS.md) • [Architecture](DESIGN.md) • [Rules](.claude/rules/) • [CLI](.github/instructions/cli-usage.instructions.md) • [Agents](AGENTS.md)

**Effort Tuning:** [Local Overrides](docs/dev-note/ai-config-maintenance.md#local-overrides-claudesettingslocaljson) – set `CLAUDE_CODE_EFFORT_LEVEL`, `MAX_THINKING_TOKENS` per session

**Updated**: 2026-08-30 (Issue #305: AI config optimization)

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
