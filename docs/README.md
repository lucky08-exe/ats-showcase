# Documentation Index

Welcome to ATS Showcase documentation. Start with the quick-start guide or explore phase-specific details below.

## Getting Started

👉 **[.github/copilot-instructions.md](./.github/copilot-instructions.md)** - Quick start (5 min read)

If you hit issues: **[docs/COMPATIBILITY.md](./docs/COMPATIBILITY.md)** - Troubleshooting & version matrix

## Pipeline Overview

ATS Showcase follows a 6-phase pipeline for job assessment:

```
CRAWL (Playwright)
  ↓
PREPROCESS (spaCy, tiktoken)
  ↓
VERIFY (Interactive CLI)
  ↓
ASSESS (Claude API)
  ↓
STORE / RETRIEVE / EXPORT (SQLite)
```

## Phase Documentation

| Phase | Document | Status | Description |
|-------|----------|--------|-------------|
| **1. CRAWL** 🌐 | [docs/CRAWL.md](./docs/CRAWL.md) | ✅ Done | Playwright multi-site crawling, CSS selector maintenance |
| **2. PREPROCESS** 🔄 | [docs/PREPROCESS.md](./docs/PREPROCESS.md) | ✅ Done | MarkItDown/BeautifulSoup HTML cleaning, NLP preprocessing, semantic chunking, token counting |
| **3. VERIFY** 👀 | [docs/VERIFY.md](./docs/VERIFY.md) | ✅ Done | Interactive CLI verification, user confirmation, cost transparency |
| **4. ASSESS** 🤖 | [docs/ASSESS.md](./docs/ASSESS.md) | ✅ Done | Claude API integration, prompts, cost optimization, error handling |
| **5. STORAGE** 💾 | [docs/STORAGE.md](./docs/STORAGE.md) | ✅ Done | SQLite schema, queries, export, data purge |
| **6. CLI** 📝 | [docs/CLI.md](./docs/CLI.md) | ✅ Done | Command structure, Typer framework, error handling, full workflow |

## Technical References

- **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** - System architecture & data flow
- **[docs/CONVENTIONS.md](./docs/CONVENTIONS.md)** - Code style, testing strategy, deployment
- **[docs/COMPATIBILITY.md](./docs/COMPATIBILITY.md)** - Python module compatibility, known issues, environment setup

## Directory Map

```
ats-showcase/
├── .github/
│   ├── copilot-instructions.md      ⭐ START HERE (5-min quick start)
│   └── COMPATIBILITY.md              (troubleshooting, versions)
│
├── docs/                            📚 DETAILED DOCS
│   ├── README.md                    (this file - navigation)
│   ├── ARCHITECTURE.md              (system overview & data flow)
│   ├── CLI.md                       (command reference, Typer design)
│   ├── CRAWL.md                     (Playwright, CSS selectors, multi-site)
│   ├── PREPROCESS.md               (NLP, chunking, token counting)
│   ├── VERIFY.md                    (user verification workflow)
│   ├── ASSESS.md                    (LLM integration & prompts)
│   ├── STORAGE.md                  (SQLite schema, queries, export)
│   └── CONVENTIONS.md               (code style, testing, deployment)
│
├── src/                             💻 IMPLEMENTATION
│   ├── cli.py                       (see: docs/CLI.md)
│   ├── browser/                     (see: docs/CRAWL.md)
│   ├── tokenization/                (see: docs/PREPROCESS.md)
│   ├── verification/                (see: docs/VERIFY.md)
│   ├── llm/                         (see: docs/ASSESS.md)
│   └── storage/                     (see: docs/STORAGE.md)
│
├── config/
│   └── companies.json               (company URLs + CSS selectors)
│
└── data/
    ├── cv.json                      (user CV input)
    ├── extracted_jobs/              (pending review)
    ├── ats_playground.db            (SQLite database)
    └── assessments/                 (markdown exports)
```

## How to Use This Documentation

### I'm new, where do I start?
1. Read `.github/copilot-instructions.md` (quick overview)
2. Run setup: `uv sync`, `uv run python -m spacy download en_core_web_md`
3. Pick a phase to learn: [docs/CRAWL.md](./docs/CRAWL.md), [docs/PREPROCESS.md](./docs/PREPROCESS.md), etc.

### I want to understand the architecture
- Read [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) for data flow overview
- Then dive into phase-specific docs (CRAWL.md, ASSESS.md, etc.)

### I'm debugging an issue
1. Check `docs/COMPATIBILITY.md` for known issues
2. Check relevant phase doc (e.g., CRAWL.md if Playwright issue)
3. Run tests: `uv run pytest tests/ -v`
4. Check logs: `tail -f logs/app.log`

### I want to add a new feature
1. Check which phase it affects (or add new doc if cross-cutting)
2. Update relevant phase doc (CRAWL.md, ASSESS.md, etc.)
3. Update [docs/CONVENTIONS.md](./docs/CONVENTIONS.md) if changing code style
4. Add tests in `tests/`
5. Update `.github/copilot-instructions.md` if new top-level command

### I'm deploying to production
- Follow checklist in each phase doc
- Review `docs/COMPATIBILITY.md` for environment setup (Docker, CI/CD, etc.)
- Check [docs/CONVENTIONS.md](./docs/CONVENTIONS.md) deployment section

## Quick Links

| Task | Link |
|------|------|
| Install & run | [.github/copilot-instructions.md](./.github/copilot-instructions.md#quick-start) |
| Add new company | [docs/CRAWL.md](./docs/CRAWL.md#adding-new-companies) |
| Customize LLM | [docs/ASSESS.md](./docs/ASSESS.md#customizing-assessment-prompts) |
| Query results | [docs/STORAGE.md](./docs/STORAGE.md#querying-results) |
| Fix Playwright issue | [docs/COMPATIBILITY.md](./docs/COMPATIBILITY.md#playwright--browser-installation) |
| Upgrade Python | [docs/COMPATIBILITY.md](./docs/COMPATIBILITY.md#version-upgrade-paths) |

## Performance & Costs

- **Token cost**: 80-90% reduction vs raw HTML → LLM
- **Speed**: Crawl (100 jobs/min) → Assess (2-5 jobs/min)
- **LLM cost**: ~$0.003 per job (Claude Haiku, optimized)

See [docs/PREPROCESS.md](./docs/PREPROCESS.md#token-cost-savings) for detailed breakdown.

## Contributing & Feedback

- Documentation issues: Update relevant doc in `docs/` or `.github/`
- Code issues: Open issue with stack trace
- Feature requests: Describe use case + which phase it affects

## Questions?

1. **How do I...?** → Check relevant phase doc (or search docs/)
2. **Why does...?** → Check [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)
3. **Getting error...?** → Check [docs/COMPATIBILITY.md](./docs/COMPATIBILITY.md)
4. **Best practice for...?** → Check [docs/CONVENTIONS.md](./docs/CONVENTIONS.md)

---

**Last updated**: 2026-05-18
**Version**: 2.4
**Status**: Active & Maintained
**Completed**: All 8 docs ✅ (CRAWL, PREPROCESS, VERIFY, ASSESS, STORAGE, CLI, ARCHITECTURE, CONVENTIONS) — **165 KB total**
