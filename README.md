# ATS Showcase

[![GitHub](https://img.shields.io/badge/github-pluto--atom--4%2Fats--playground-blue?logo=github)](https://github.com/pluto-atom-4/ats-showcase)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status: Active](https://img.shields.io/badge/status-active-success)]()

Agentic AI workflow for intelligent job assessment. Extract job postings from company websites, preprocess with NLP, verify with users, assess CV fit using Claude (Haiku/Sonnet/Opus), and store results in a queryable SQLite database.

**Cost optimized**: 88% token reduction through local preprocessing with consolidated `clean_html()` function removing 70+ boilerplate patterns. Configurable LLM model (default Sonnet). ~$0.0001–0.0008 per assessment depending on model.

## 🚀 Quick Start

```bash
# 1. Clone & setup (with Python 3.12)
git clone https://github.com/pluto-atom-4/ats-showcase.git
cd ats-showcase
uv python pin 3.12                    # Recommended: Python 3.12.x
uv sync
python -m spacy download en_core_web_md

# 2. Validate NLP setup
python -m src.setup.validate_nlp_setup  # Check all components

# 3. Create .env and set API key
cp .env.example .env
export ANTHROPIC_API_KEY="sk-ant-..."

# 4. Run the full workflow
python -m src.cli all --cv data/cv.json --config config/companies.json

# Or with directory of configs (NEW - enables selective company processing):
python -m src.cli all --cv data/cv.json --config-dir ./config

# Or run individually:
python -m src.cli crawl --config config/companies.json
python -m src.cli preprocess
python -m src.cli review
python -m src.cli assess --cv data/cv.json
python -m src.cli export --output data/assessments/report.md
```

**Stop before billing (cost verification):**
```bash
# Crawl + preprocess + review — STOP before assess
python -m src.cli all --cv data/cv.json --config config/companies.json --up-to review

# Crawl + preprocess only
python -m src.cli all --cv data/cv.json --config config/companies.json --up-to preprocess
```

**Config Options**:
- `--config <file>` - Single JSON config file (backward compatible)
- `--config-dir <dir>` - Directory of JSON config files (NEW - enables `enabled` flag for selective processing)

See [docs/CLI.md](./docs/CLI.md#configuration-management) for detailed config examples and the `enabled` flag.

**Setup Troubleshooting?** See [docs/SETUP.md](./docs/SETUP.md) for detailed Python 3.12 configuration, system dependencies, and troubleshooting.

## 📊 Interactive Dashboard (TUI)

Run the workflow with an interactive text-based dashboard for real-time progress tracking:

```bash
# Auto-detect TUI from terminal (runs in TUI if interactive)
python -m src.cli all --cv data/cv.json --config config/companies.json

# Force TUI mode
python -m src.cli all --cv data/cv.json --config config/companies.json --tui

# Force text-only mode
python -m src.cli all --cv data/cv.json --config config/companies.json --no-tui
```

**Dashboard Features**:
- 🕷️ **Real-time progress bars** for crawl, preprocess, assess, and export phases
- 💰 **Live cost tracking** - tokens used and USD spent per phase
- 🏆 **Top matches display** - see top 5 job matches as they're assessed
- ⏸️ **Pause/resume** - control workflow with `[p]` to pause, `[r]` to resume
- 🎯 **Phase status** - visual indicators for each workflow phase
- ⌨️ **Keyboard shortcuts**: `[q]` to quit, `[p]` to pause/resume

**When TUI is disabled**: Falls back to traditional text output (useful for CI/CD or piped output).

## 🌍 Environment Configuration

ATS Showcase requires environment variables for API keys and configuration. Set them in `.env` (created during quick start).

### Required Variables

```bash
# Copy template
cp .env.example .env

# Edit .env with your values
```

| Variable | Example | Required? | Purpose |
|----------|---------|-----------|---------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | ✅ Yes | Claude API authentication. Get from [console.anthropic.com](https://console.anthropic.com) |
| `SPACY_MODEL` | `en_core_web_md` | ✅ Yes | NLP model for sentence segmentation (downloaded in quick start) |
| `DATABASE_PATH` | `data/ats_playground.db` | ❌ No | SQLite database file (default: shown) |
| `LOG_LEVEL` | `INFO` | ❌ No | Logging verbosity: DEBUG, INFO, WARNING, ERROR (default: INFO) |
| `PLAYWRIGHT_HEADLESS` | `true` | ❌ No | Browser headless mode: true (default), false (see browser) |

### Getting an API Key

1. Visit [console.anthropic.com](https://console.anthropic.com)
2. Sign up or log in
3. Navigate to API Keys
4. Click "Create Key"
5. Copy the key (starts with `sk-ant-`)
6. Paste into `.env`: `ANTHROPIC_API_KEY=sk-ant-...`

### Verification

```bash
# Verify all environment variables are set
python -m src.setup.validate_nlp_setup

# Should show:
# ✅ ANTHROPIC_API_KEY loaded
# ✅ SPACY_MODEL loaded
# ✅ DATABASE_PATH ready
```

## 🔍 Code Quality Assurance (Issue #6)

Optional: Automatically catch code quality issues before committing:

```bash
# Install pre-commit hooks (1 minute)
python -m src.setup.setup_precommit

# Hooks run automatically on git commit:
# • trailing-whitespace & end-of-file-fixer (auto-fix)
# • black & ruff (auto-fix formatting)
# • mypy (type checking)
# • pytest (unit tests)
```

**Details**: See [docs/QUALITY-ASSURANCE.md](./docs/QUALITY-ASSURANCE.md) for hook explanations, troubleshooting, and performance tips.

## 🧠 NLP Setup Validation (Issue #7)

After setup, validate the NLP environment:

```bash
# Comprehensive validation of all NLP components
python -m src.setup.validate_nlp_setup

# Output shows status of:
# ✅ Python version (3.12+ required)
# ✅ spaCy installation & model
# ✅ Pydantic v2 compatibility
# ✅ tiktoken token counting
# ✅ MarkItDown HTML cleaning
# ✅ lxml C bindings (optional)
# ✅ System dependencies (libxml2, libxslt)
```

**Result**: Should show `✅ ALL CRITICAL COMPONENTS OK`

**Python Version Strategy**:
- **Recommended**: Python 3.12.x (production-ready, EOL 2028-10)
- **Alternative**: Python 3.13+ (security-only, newer features)
- **Not Recommended**: Python 3.11 (legacy, slower)

**If validation fails**: See [docs/SETUP.md](./docs/SETUP.md) for platform-specific system dependency installation (Ubuntu/Debian, macOS, Windows) and [docs/COMPATIBILITY.md](./docs/COMPATIBILITY.md) for known issues and workarounds.

**New here?** Start with:
- 👉 **[.github/copilot-instructions.md](./.github/copilot-instructions.md)** (5 min quick overview)
- 📖 **[docs/README.md](./docs/README.md)** (complete documentation index with all guides)

**Phase-specific guides** (in `docs/`):
| Phase | Guide | Focus |
|-------|-------|-------|
| 🌐 **CRAWL** | [CRAWL.md](./docs/CRAWL.md) | Playwright multi-site crawling, CSS selectors |
| 🔄 **PREPROCESS** | [PREPROCESS.md](./docs/PREPROCESS.md) | HTML cleaning, NLP, semantic chunking, token counting |
| 👀 **VERIFY** | [VERIFY.md](./docs/VERIFY.md) | Interactive CLI, user confirmation, cost transparency |
| 🤖 **ASSESS** | [ASSESS.md](./docs/ASSESS.md) | Claude API, prompts, rate limiting, cost tracking |
| 💾 **STORAGE** | [STORAGE.md](./docs/STORAGE.md) | SQLite schema, FTS5 search, markdown export |
| 🔧 **INTEGRITY** | [INTEGRITY.md](./docs/INTEGRITY.md) | Database health check, repair orphaned data, safe purge |
| 📝 **CLI** | [CLI.md](./docs/CLI.md) | Command reference, Typer framework, workflows |

**System design**:
- [ARCHITECTURE.md](./docs/ARCHITECTURE.md) – System architecture, data flow, modules, scaling
- [CONVENTIONS.md](./docs/CONVENTIONS.md) – Code style, testing, deployment, best practices
- [COMPATIBILITY.md](./docs/COMPATIBILITY.md) – Troubleshooting, version matrix, setup issues

## ✨ Features

- **🌐 Multi-site crawling** – Playwright with JavaScript rendering, CSS selector pooling, rate limiting
- **🔄 Smart preprocessing (Issue #230 + #231)** – Consolidated `clean_html()` with 70+ boilerplate patterns; 3-tier fallback (MarkItDown → BeautifulSoup → Original HTML) ensures robustness; semantic chunking; 88% token reduction
- **👀 User verification** – Interactive CLI review with cost estimates before expensive LLM calls
- **🤖 LLM assessment** – Claude 3.5 Sonnet with batch processing, rate limiting, detailed scoring
- **💾 Data persistence** – SQLite with FTS5 full-text search, structured export to Markdown
- **📊 Cost analytics** – Real-time token tracking, per-job cost breakdown, total spend accounting
- **📅 Date-range filtering** – Filter exports by assessment date, purge old records with safety confirmations
- **⚡ Performance** – Crawl 100+ jobs/min; preprocess 10x faster with pre-compiled patterns; assess 2–5 jobs/min (Claude limit); query <100ms (indexed)

## 💻 Tech Stack

| Layer | Technologies |
|-------|--------------|
| **Browser** | Playwright (Chromium), async/await |
| **NLP** | spaCy (en_core_web_md), tiktoken for token counting |
| **Text Processing** | MarkItDown (primary), BeautifulSoup4 + lxml (fallback), `clean_html()` with 70+ boilerplate patterns (Issue #230) |
| **CLI** | Typer (modern, async-ready), interactive prompts |
| **LLM** | Claude (configurable: Haiku/Sonnet/Opus, Anthropic SDK) |
| **Database** | SQLite with FTS5 (full-text search) |
| **Formatting** | Markdown, JSON |

### HTML Preprocessing & Boilerplate Removal (Issue #230)

The preprocessing phase uses consolidated `clean_html()` function with 70+ pre-compiled boilerplate patterns across 7 categories:

**Boilerplate removed:**
- ✂️ Legal disclaimers (EEO statements, © copyright)
- ✂️ Navigation elements (breadcrumbs, page menus)
- ✂️ Company taglines (non-job-specific "about us")
- ✂️ Timestamps (posted dates, application deadlines)
- ✂️ Extra formatting (whitespace, CSS, metadata)

**Preserved:**
- ✅ Job title and description
- ✅ Requirements and responsibilities
- ✅ Salary/benefits (configurable removal)
- ✅ Location and job type

**Performance benefit:** 10x faster boilerplate removal via pre-compiled patterns; accounts for ~30% of 88% total token reduction.

**Deprecation Notice:** `HTMLCleaner` class deprecated (v2.0 removal planned); use `clean_html()` instead.

**See also:** [docs/CLI.md#preprocessing--boilerplate-removal](./docs/CLI.md#preprocessing--boilerplate-removal) for configuration examples.

## 📋 Requirements

- **Python**: 3.11+ (3.13 recommended)
- **Package manager**: `uv` ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **Browser**: Chromium or Chrome (Playwright handles download)
- **API key**: Anthropic Claude API key ([get one](https://console.anthropic.com))
- **Disk**: ~100 MB for dependencies, ~5 MB per 500 assessments

## 🛠️ Installation

See [.github/copilot-instructions.md](./.github/copilot-instructions.md#quick-start) for detailed setup with environment config.

```bash
# Install dependencies
uv sync

# Download spaCy NLP model (~40 MB)
python -m spacy download en_core_web_md

# Install Playwright browsers
uv run playwright install

# Create environment file with your API key
cp .env.example .env
# Edit .env and add: ANTHROPIC_API_KEY=sk-ant-...
```

Verify installation:
```bash
uv run pytest tests/ -v  # All tests should pass
uv run python -c "import spacy; print(spacy.load('en_core_web_md'))"
```

## 🎯 Usage Examples

### Full Workflow (One Command)
```bash
# Process all companies in config, assess against your CV
uv run python -m src.cli all --cv data/cv.json --config config/companies.json
```

### Step-by-Step

**1. Crawl** job postings from company websites:
```bash
uv run python -m src.cli crawl --config config/companies.json --headless
```

**2. Preprocess** (clean HTML, chunk by sentences, count tokens):
```bash
uv run python -m src.cli preprocess --batch 50 --show-estimates
```

**3. Review** extracted jobs interactively before LLM calls:
```bash
# Basic: review and confirm/reject jobs
uv run python -m src.cli review --interactive

# With cost recalculation for specific model (NEW)
uv run python -m src.cli review --interactive --model haiku  # Show Haiku costs
uv run python -m src.cli review --interactive --model sonnet # Show Sonnet costs

# With cost warning threshold (default: $0.10)
uv run python -m src.cli review --interactive --cost-limit 0.05  # Warn if > $0.05
```

**4. Assess** CV fit with Claude (choose model by cost/accuracy tradeoff):
```bash
# Default: Claude Sonnet (balanced cost/quality, $3/$15 per 1M tokens)
uv run python -m src.cli assess --cv data/cv.json --confirmed-only

# Or: Haiku (cheapest, 95% savings vs Opus, $0.80/$4 per 1M)
uv run python -m src.cli assess --cv data/cv.json --model haiku

# Or: Opus (most capable, $15/$75 per 1M)
uv run python -m src.cli assess --cv data/cv.json --model opus

# Or use full model IDs (equivalent to aliases above)
uv run python -m src.cli assess --cv data/cv.json --model claude-sonnet-5
uv run python -m src.cli assess --cv data/cv.json --model claude-haiku-4-5-20251001
uv run python -m src.cli assess --cv data/cv.json --model claude-opus-4-8
```

**5. Query & Export** results:
```bash
# Search by keyword
uv run python -m src.cli query --keyword "python" --min-score 75

# Export to Markdown (all assessments)
uv run python -m src.cli export --output data/assessments/report.md

# Export with date filtering (new feature)
uv run python -m src.cli export \
  --from-date 2025-06-01 \
  --to-date 2025-12-31 \
  --min-score 80 \
  --output data/assessments/recent_high_matches.md

# Purge old assessments (with safety features - dry-run by default)
uv run python -m src.cli purge --before-date 2025-04-01

# Actually delete old assessments (requires --no-dry-run AND --confirm)
uv run python -m src.cli purge --before-date 2025-04-01 --no-dry-run --confirm
```

**6. View Statistics** and token usage:
```bash
uv run python -m src.cli stats --show-token-usage
```

### Testing & Debugging
```bash
# Run all tests
uv run pytest tests/ -v

# Test crawling without browser (mock mode)
uv run python -m src.cli crawl --mock

# Test LLM assessment without API calls
uv run python -m src.cli assess --mock

# Check logs
tail -f logs/app.log
```

See [docs/CLI.md](./docs/CLI.md) for full command reference.

## 💰 Cost Optimization

ATS Showcase cuts LLM costs **80–90%** through local preprocessing.

### Example: Assess 100 Jobs

| Approach | Tokens/Job | Total Tokens | Cost (Claude 3.5) | Savings |
|----------|-----------|--------------|-------------------|---------|
| **Raw HTML → LLM** | ~6,000 | 600,000 | ~$0.60 | — |
| **ATS Showcase** | ~700 | 70,000 | ~$0.07 | **88%** ✅ |

**Breakdown:**
- Crawl locally (0 tokens)
- Preprocess locally with spaCy (0 tokens)
- Chunk semantically by sentences (not random token breaks)
- Count tokens with tiktoken before LLM
- Show cost estimate to user
- Send only clean chunks → LLM

**Detailed analysis**: [docs/PREPROCESS.md](./docs/PREPROCESS.md#token-cost-savings) and [docs/ASSESS.md](./docs/ASSESS.md#cost-tracking)

## 🧪 Testing

```bash
# Run all tests with coverage
uv run pytest tests/ -v --cov=src --cov-report=term-missing

# Run specific test suite
uv run pytest tests/test_llm.py -v
uv run pytest tests/test_storage.py::test_query_results -v

# Run with detailed output
uv run pytest tests/ -vv -s
```

Tests cover:
- ✅ Crawling & HTML extraction
- ✅ Preprocessing & token counting
- ✅ User verification workflows
- ✅ LLM assessment & error handling
- ✅ SQLite queries & exports
- ✅ CLI commands & arguments

## 📑 Configuration File Map

**For new developers**: Read these files in order to understand the project structure and development workflow.

| File | Purpose | Read When |
|------|---------|-----------|
| [CLAUDE.md](./CLAUDE.md) | Core rules, quick commands, never-do-this guardrails | Setting up your environment |
| [AGENTS.md](./AGENTS.md) | Agent roles, handover protocol, escalation rules | Understanding multi-agent coordination |
| [DESIGN.md](./DESIGN.md) | Architecture, module structure, design decisions | Learning project design patterns |
| [.claude/settings.json](./.claude/settings.json) | Model tier pinning, permissions, orchestration layer | Configuring Claude Code behavior |
| [.claude/rules/](./claude/rules/) | Phase-specific guidance (crawl, preprocess, assess, etc.) | Working on a specific phase |
| [.github/instructions/](./github/instructions/) | CLI usage, code patterns, topic-scoped rules | Writing code or using CLI commands |
| [docs/COMPATIBILITY.md](./docs/COMPATIBILITY.md) | Troubleshooting, version matrix, environment setup | Debugging issues |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Contributing guidelines, PR process | Ready to contribute |

**Quick Navigation:**
- **I want to run the code** → [CLAUDE.md](./CLAUDE.md) § Quick Workflow
- **I want to understand the design** → [DESIGN.md](./DESIGN.md)
- **I want to write code** → [.github/instructions/code-patterns.instructions.md](./.github/instructions/code-patterns.instructions.md)
- **I need a CLI command** → [.github/instructions/cli-usage.instructions.md](./.github/instructions/cli-usage.instructions.md)
- **I need to troubleshoot** → [docs/COMPATIBILITY.md](./docs/COMPATIBILITY.md)

## 🤝 Contributing

1. **Read code standards**: [CONVENTIONS.md](./docs/CONVENTIONS.md)
2. **Create feature branch**: `git checkout -b feature/my-feature`
3. **Make changes** & write tests (coverage: 80%+)
4. **Test**: `uv run pytest tests/ -v`
5. **Lint**:
   ```bash
   uv run black src/ tests/
   uv run ruff check src/ tests/ --fix
   ```
6. **Commit** with clear message:
   ```bash
   git commit -m "feat(cli): add new command"
   # Include Co-authored-by if pair programming
   ```
7. **Push & open PR**: Include description of changes & testing

See [CONVENTIONS.md](./docs/CONVENTIONS.md) for code style, error handling, and deployment checklist.

## 🐛 Debugging

**Playwright crashes?**
```bash
uv run playwright install chromium
# See detailed troubleshooting: docs/COMPATIBILITY.md#playwright--browser-installation
```

**spaCy model not found?**
```bash
uv run python -m spacy download en_core_web_md
# See: docs/COMPATIBILITY.md#spacy-model-issues
```

**Claude API errors?**
```bash
# Check logs
tail -f logs/app.log

# Verify API key
echo $ANTHROPIC_API_KEY

# Test connection
uv run python -c "from anthropic import Anthropic; print(Anthropic().models.list())"

# See: docs/ASSESS.md#error-handling
```

**Database locked?**
```bash
# Check for running processes
lsof | grep ats_playground.db

# Clear database if corrupted
rm data/ats_playground.db
uv run python src/storage/db.py --init
```

**More troubleshooting**: [COMPATIBILITY.md](./docs/COMPATIBILITY.md) — version matrix, environment setup, known issues

## 📊 Performance Benchmarks

| Metric | Speed | Notes |
|--------|-------|-------|
| **Crawl** | 100–200 jobs/min | Depends on site complexity & network |
| **Preprocess** | 50–100 jobs/min | Local NLP with spaCy |
| **Token counting** | 1000+ jobs/sec | tiktoken on preprocessed text |
| **Assess (LLM)** | 2–5 jobs/min | Claude rate limit (~10 RPM, ~50k TPM) |
| **Query** | <100 ms | SQLite FTS5 indexed search |
| **Export** | <1 sec | Markdown generation |
| **Database size** | ~5 MB | Per 500 assessments |
| **LLM cost** | $0.00009–$0.00115/job | Haiku (cheapest) to Opus (best accuracy) |

See [ARCHITECTURE.md](./docs/ARCHITECTURE.md#performance) for scaling strategies.

## 🏗️ Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ INPUT: Company URLs + CSS Selectors (config/companies.json) │
└────────┬────────────────────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────┐
    │ 1️⃣  CRAWL (Playwright)                   │
    │     • Render JavaScript                  │
    │     • Extract via CSS selectors          │
    │     • Rate limiting & retries            │
    └────┬─────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────┐
    │ 2️⃣  PREPROCESS (MarkItDown + spaCy)     │
    │     • Convert HTML → clean text          │
    │     • Split by sentences                 │
    │     • Count tokens with tiktoken         │
    │     • Remove boilerplate                 │
    └────┬─────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────┐
    │ 3️⃣  VERIFY (Interactive CLI)            │
    │     • User confirms/edits/rejects        │
    │     • Show cost estimate                 │
    │     • Mark approved for LLM              │
    └────┬─────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────┐
    │ 4️⃣  ASSESS (Claude API)                 │
    │     • Match CV skills vs job             │
    │     • Rate by category (tech, seniority) │
    │     • Generate recommendations           │
    │     • Track actual tokens & cost         │
    └────┬─────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────┐
    │ 5️⃣  STORE (SQLite)                      │
    │     • Save job + assessment              │
    │     • Index for FTS5 search              │
    │     • Track cost & tokens                │
    └────┬─────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────┐
    │ 6️⃣  QUERY / EXPORT                      │
    │     • Search by keyword/score            │
    │     • Export to Markdown report          │
    │     • View statistics & costs            │
    └────▼─────────────────────────────────────┘
         │
    OUTPUT: Markdown assessment report + SQLite database
```

**Full architecture**: [ARCHITECTURE.md](./docs/ARCHITECTURE.md)

## 📄 License

MIT — Use freely in commercial or personal projects. See [LICENSE](LICENSE) for details.

## ❓ Help & Support

**Quick Answers**:
| Question | Resource |
|----------|----------|
| How do I...? | Check the relevant phase doc (CRAWL, ASSESS, etc.) |
| Why does...? | Read [ARCHITECTURE.md](./docs/ARCHITECTURE.md) |
| Getting error...? | See [COMPATIBILITY.md](./docs/COMPATIBILITY.md) |
| Best practice for...? | Read [CONVENTIONS.md](./docs/CONVENTIONS.md) |

**Resources**:
- 📖 **Full Documentation**: [docs/README.md](./docs/README.md)
- 🚀 **Quick Start**: [.github/copilot-instructions.md](./.github/copilot-instructions.md)
- 🏗️ **Architecture & Design**: [DESIGN.md](./DESIGN.md) (semantic tokens, system design, core principles)
- 🎯 **Design Decisions**: [docs/ARCHITECTURE-DECISIONS.md](./docs/ARCHITECTURE-DECISIONS.md) (framework selection, why we chose X over Y)
- 🐛 **Troubleshooting**: [COMPATIBILITY.md](./docs/COMPATIBILITY.md)
- 📝 **All Commands**: [CLI.md](./docs/CLI.md)

**Report Issues**:
- 🐛 Bugs: [Open an issue](https://github.com/pluto-atom-4/ats-showcase/issues/new?template=bug_report.md)
- ✨ Features: [Request a feature](https://github.com/pluto-atom-4/ats-showcase/issues/new?template=feature_request.md)
- 💬 Discussion: [Start a discussion](https://github.com/pluto-atom-4/ats-showcase/discussions)

---

**Last updated**: 2026-05-19
**Status**: Active & Maintained ✅
**Documentation**: [8 comprehensive guides](./docs/README.md) — **165+ KB total**
**Repository**: [pluto-atom-4/ats-showcase](https://github.com/pluto-atom-4/ats-showcase)
