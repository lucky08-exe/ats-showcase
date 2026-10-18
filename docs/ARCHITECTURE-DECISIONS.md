# Architecture Decisions: Detailed Analysis

**Purpose:** Deep dives on critical architectural choices. Start here when curious "why we chose X over Y."

**Related:** See DESIGN.md § Key Decisions for 1-page summaries.

---

## 1. Framework Selection: Why Textual Over Alternatives

### Decision Context

ATS Showcase manages a 4-phase workflow: crawl (extract HTML), preprocess (clean + chunk), assess (Claude API calls), export (markdown reports). Each phase processes dozens to thousands of jobs.

The UI must show:
- Real-time progress bars (crawl: 10.5 jobs/min, assess: 2-5 jobs/min)
- Live cost accumulation (tokens + USD)
- Top matches as they're processed
- Phase transitions (crawl → preprocess → assess → export)

Additionally, the workflow is **inherently async:** crawler fetches multiple pages in parallel, assessments are rate-limited by Claude TPM (tokens per minute), not by individual job processing time.

### Decision Criteria & Weighting

| Criterion | Weight | Importance |
|-----------|--------|------------|
| Async-native support | 25% | Crawl + LLM calls are parallel; TUI must not block |
| Real-time updates (no flicker) | 20% | Progress bars, cost tracker need smooth rendering |
| Composable widgets | 20% | Dashboard = stacked containers + reusable widgets |
| Cross-platform (Linux/macOS/Windows) | 15% | User-facing CLI must work everywhere |
| Maturity + maintenance | 10% | Production stability, active community |
| Learning curve | 10% | Implementation speed matters for Phase 1 |

### Framework Comparison & Scoring

#### **1. Textual** ⭐ SELECTED (94/100)

**By:** Textualize (maintainers of Rich)
**Release:** v0.1+ (2023), v0.42+ current
**License:** MIT

**Async Support:** Native (built on asyncio)
```python
class Dashboard(Screen):
    @work(exclusive=True)
    async def run_workflow(self):
        await self._phase_crawl()      # Runs async without blocking UI
        await self._phase_assess()
```

**Real-time Updates:** Event-driven rendering (no manual refresh loops)
```python
# Widgets update automatically when StateManager changes
def on_mount(self):
    self.set_interval(0.5, self._update_display)  # ~2Hz, no flicker
```

**Composable Widgets:** 30+ built-in (Button, Input, DataTable, etc.)
```python
with Vertical(id="content"):
    yield CrawlPanel(...)          # Panels stack automatically
    yield PreprocessPanel(...)
    yield AssessPanel(...)
```

**Styling:** CSS-like (TCSS) + theming
```css
/* Colors, spacing, borders like CSS */
#header { height: 3; border: solid $primary; }
```

**Platform:** Linux, macOS, Windows

**Testing:** First-class testing API
```python
async def test_crawl_panel():
    app = Dashboard(StateManager())
    async with app.run_test() as pilot:
        assert app.query("#crawl-panel")
```

**Pros:**
- ✅ Async-first: `@work` decorator for background tasks (crawl, assess)
- ✅ Composable: Stack containers (Vertical/Horizontal) + widgets
- ✅ Live updates: Event-driven, no flickering
- ✅ Rich integration: Colors, tables, progress bars ship with Textual
- ✅ Testing API: Automated tests for dashboard logic
- ✅ Active dev: Weekly releases, responsive maintainer
- ✅ Accessibility: ANSI compatible (screenreader friendly)
- ✅ Large projects using it: Atuin (shell history), DuckDB (query CLI), Hatch (package manager)

**Cons:**
- ⚠️ Textual < v1.0 (currently v0.42): Breaking changes possible in minor versions
- ⚠️ Steeper learning curve: CSS-like layout, event model, widget lifecycle
- ⚠️ Larger binary footprint: ~20MB with dependencies

**Score:** 25 + 19 + 20 + 15 + 8 + 7 = **94/100**

---

#### **2. Urwid** (Second Place, 70/100)

**By:** Ian Ward
**Release:** 2006 (mature), v1.4+ current
**License:** LGPL

**Async Support:** Limited (manual asyncio integration required)
```python
# Must manually manage event loop; awkward
asyncio_loop = urwid.AsyncioEventLoop()
loop = urwid.MainLoop(..., event_loop=asyncio_loop)
# Still not truly async-first
```

**Real-time Updates:** Manual invalidate() calls (error-prone)
```python
# ❌ Must remember to call invalidate() or UI doesn't update
widget.set_text("new text")
self.invalidate()  # Easy to forget, causes flicker
```

**Composable Widgets:** 20+ widgets (ListBox, Edit, etc.)

**Styling:** Palette system (not CSS-like)

**Platform:** Linux, macOS, Windows

**Maturity:** 13+ years, stable, well-documented

**Pros:**
- ✅ Mature + stable (battle-tested)
- ✅ Full-featured (overlays, advanced layouts)
- ✅ Lightweight
- ✅ Good documentation

**Cons:**
- ❌ Async is awkward: Manual asyncio integration, not first-class
- ❌ Updates require manual `invalidate()` calls (flicker-prone)
- ❌ Less active maintenance
- ❌ Learning curve steep (event model different from modern Python)
- ❌ Would require significant async refactoring

**Why not selected:** Async integration kills it. ATS workflow is async-heavy; forcing asyncio onto Urwid is fighting the framework.

**Score:** 10 + 14 + 16 + 15 + 10 + 5 = **70/100**

---

#### **3. Blessed** (Third Place, 48/100)

**By:** jquast
**Release:** 2013, v1.20+ current
**License:** GPL

**Async Support:** No native support (manual wrapping required)

**Widgets:** None (only cursor movement, formatting)

**Composability:** None (build everything from scratch)

**Pros:**
- ✅ Lightweight + minimal dependencies
- ✅ Low learning curve
- ✅ Works everywhere (TTY abstraction)

**Cons:**
- ❌ No composable widgets (boilerplate-heavy)
- ❌ No async support (must wrap manually)
- ❌ Not suitable for rich dashboards
- ❌ Manual layout = error-prone positioning

**Why not selected:** Too low-level. Would require building dashboard components from scratch (ProgressBar, DataTable, etc.) with manual async handling.

**Score:** 0 + 8 + 8 + 15 + 8 + 9 = **48/100**

---

#### **4. Rich** (Fourth Place, 62/100)

**By:** Will McGugan (Textualize)
**Release:** 2020, v13.0+ current
**License:** MIT

**Type:** Output-only (not a TUI framework)

**Widgets:** Tables, progress bars, panels (static, no input)

**Pros:**
- ✅ Beautiful output (tables, progress bars, rich panels)
- ✅ Ships with Textual (no extra dependencies)
- ✅ Perfect for static reports
- ✅ Lightweight

**Cons:**
- ❌ Output-only: Can't capture user input
- ❌ No event loop or widget state management
- ❌ Not a TUI framework (complementary to Textual)

**Why not selected:** Rich is amazing for reports and static output, but can't build interactive dashboards alone. Textual ships with Rich, so we get both.

**Score:** 0 + 18 + 12 + 15 + 9 + 8 = **62/100**

---

#### **5. Prompt Toolkit** (Fifth Place, 66/100)

**By:** Jonathan Slenders
**Release:** 2014, v3.0+ current
**License:** BSD

**Async Support:** Native (asyncio-ready)

**Focus:** Interactive prompts (questions, completions, keybindings)

**Widgets:** Input, completion, history (prompt-focused)

**Pros:**
- ✅ Excellent for interactive prompts
- ✅ Auto-complete, history, keybindings
- ✅ Lightweight
- ✅ Async-aware

**Cons:**
- ❌ Not designed for multi-panel dashboards
- ❌ Limited layout capabilities (vertical stacking only)
- ❌ No real-time progress bars or tables
- ❌ Would need multiple frameworks

**Why not selected:** Good for verify phase (approve/reject dialogs), but insufficient for main dashboard. Would need Textual anyway.

**Score:** 22 + 6 + 8 + 15 + 9 + 6 = **66/100**

---

#### **6. Curses** (Last Place, 27/100)

**By:** Unix standard (1980s)
**Type:** Low-level primitives
**License:** Stdlib

**Pros:**
- ✅ No external dependencies (stdlib)
- ✅ Maximum control
- ✅ Minimal footprint

**Cons:**
- ❌ Extremely low-level (manual positioning, refresh loops)
- ❌ No async support
- ❌ Boilerplate-heavy
- ❌ Windows support is janky (wincurses)
- ❌ Easy to introduce flicker bugs
- ❌ No widgets or composition

**Why not selected:** Too low-level for modern Python. Building a dashboard would take 2–3× longer.

**Score:** 0 + 10 + 0 + 5 + 10 + 2 = **27/100**

---

### Decision Matrix: All Frameworks

| Framework | Async (25%) | Real-time (20%) | Widgets (20%) | Platform (15%) | Maturity (10%) | Learning (10%) | **Total** |
|-----------|-------------|-----------------|---------------|----------------|----------------|----------------|-----------|
| **Textual** | 25 | 19 | 20 | 15 | 8 | 7 | **94/100** ⭐ |
| Urwid | 10 | 14 | 16 | 15 | 10 | 5 | **70/100** |
| Prompt Toolkit | 22 | 6 | 8 | 15 | 9 | 6 | **66/100** |
| Rich | 0 | 18 | 12 | 15 | 9 | 8 | **62/100** |
| Blessed | 0 | 8 | 8 | 15 | 8 | 9 | **48/100** |
| Curses | 0 | 10 | 0 | 5 | 10 | 2 | **27/100** |

---

### ATS-Specific Reasoning

#### Why Async Matters (25% weight)

ATS workflow is inherently parallel:

**Crawl Phase:** Fetch 100+ jobs from multiple career pages concurrently
```python
# Without async, would crawl sequentially (very slow)
# With async, crawls all pages in parallel
async with BrowserManager() as browser:
    tasks = [browser.fetch_jobs(cfg) for cfg in configs]
    results = await asyncio.gather(*tasks)  # Parallel
```

**Assess Phase:** Claude has rate limits (e.g., 50k tokens per minute). Single sequential assessment (2-5 jobs/min) is slow. Async allows queuing multiple jobs for rate-limited processing.

Textual's `@work` decorator makes this natural. Urwid forces manual asyncio integration. Others don't support async at all.

#### Why Real-Time Updates Matter (20% weight)

Dashboard updates every 0.5s for smooth rendering:
- Progress bar: 10.5 jobs/min crawl = 1 job per 6 seconds → visual feedback
- Cost tracker: Each job processed → cost increments by ~$0.002 → user sees accumulation
- Phase transitions: crawl → preprocess → assess → export → visual feedback

Textual's event-driven model (widgets observe StateManager) prevents manual refresh bugs. Urwid's `invalidate()` model is error-prone (easy to forget, causes flicker).

#### Why Composability Matters (20% weight)

Dashboard = Header + PhaseIndicator + (4 Phase Panels) + Footer

Textual:
```python
with Vertical(id="content"):
    yield CrawlPanel(state)
    yield PreprocessPanel(state)
    yield AssessPanel(state)
    yield ExportPanel(state)
```

Urwid would require manual layout coordination (nested Pile/Columns with manual sizing).

#### Why Rich Integration Matters (implicit)

Already using Rich for CLI output:
```python
from rich.table import Table
table = Table()
table.add_row("Job", "Score", "Status")
```

Textual ships with Rich built-in:
```python
from textual.widgets import DataTable
table = DataTable()  # Renders with Rich formatting, no extra dep
```

Urwid would require separate styling layer.

#### Why Testing Matters (implicit)

Textual has first-class testing:
```python
async def test_crawl_panel():
    app = Dashboard(StateManager())
    async with app.run_test() as pilot:
        # Can drive UI, assert on widget state
        assert app.query("#crawl-panel")
```

Urwid/Blessed have no testing framework.

---

### Risk Mitigation: Textual < v1.0

**Risk:** Textual is v0.42 (not v1.0 yet). Minor version bumps (0.42 → 0.43, 0.50) might break API.

**Mitigation Strategy:**

1. **Pin version in pyproject.toml:**
   ```toml
   textual = "^0.42.0"  # Allow patches, lock minor
   ```
   This allows 0.42.x security patches but not 0.43+ (breaking changes).

2. **Minimize direct Textual usage:**
   - Wrap Textual components in StateManager, Panels (loose coupling)
   - If Textual API breaks, only need to update wrapper layer, not entire codebase

3. **Async patterns are stable:**
   - asyncio core (Python stdlib) won't break
   - Textual adapts to asyncio, not vice versa
   - `@work` decorator is stable; unlikely to change drastically

4. **Active adoption:**
   - Atuin (shell history CLI): ~10k stars, production use
   - DuckDB (SQL query CLI): official SQL CLI built on Textual
   - Hatch (Python package manager): official build CLI
   - These projects prove Textual is stable for production dashboards

5. **Fallback plan (if critical blocker):**
   - Migrate to Urwid (requires async refactoring, but feasible)
   - Keep StateManager + Panels abstraction (minimal UI rewrites)
   - Estimated effort: 2–3 days

---

### Conclusion

**Textual is the best choice for ATS Showcase.**

- Async-first architecture matches workflow nature (crawl + LLM parallel)
- Real-time rendering prevents UX bugs (flicker, stale progress)
- Rich integration saves dependencies and complexity
- Testing support enables CI/CD automation
- Active maintenance + large projects using it prove stability
- Risk (v0.42 < v1.0) is mitigated by version pinning + loose coupling

---

## 2. Semantic Chunking: Sentences vs Token-Based Splits

### Decision

**Selected:** spaCy sentence segmentation (not fixed-token splits)

### Why Sentences Preserve Meaning

**Example 1: Technical Requirement**
```
Text: "Requires 5+ years MES experience. Must know Wonderware."

Token-based split (400 tokens/chunk):
  Chunk A: "Requires 5+ years MES experience."
  Chunk B: "Must know Wonderware."
  ❌ Split MIDDLE OF REQUIREMENT. Claude might think MES and Wonderware are unrelated.

Sentence-based split:
  Chunk A: "Requires 5+ years MES experience. Must know Wonderware."
  ✅ STAYS TOGETHER. Claude understands the linked requirements.
```

**Example 2: Multi-Sentence Qualification**
```
Text: "We need someone with strong Python skills. They should have 3+ years of async/await. Rust knowledge is a bonus."

Token-based (arbitrary break):
  Chunk A: "We need someone with strong Python skills. They should have"
  Chunk B: "3+ years of async/await. Rust knowledge is a bonus."
  ❌ Breaks "3+ years of async/await" requirement in half.

Sentence-based:
  Chunk A: "We need someone with strong Python skills. They should have 3+ years of async/await."
  Chunk B: "Rust knowledge is a bonus."
  ✅ Each sentence is complete thought.
```

### Variable Chunk Sizes Are Intentional

**Fact:** Sentence lengths vary 30–300 tokens. Chunks end up 100–600 tokens.

**This is correct behavior.** Semantic boundaries matter more than uniform sizes.

- Short job description (e.g., "Senior Engineer. Cloud + DevOps. Remote.") → 1 chunk (150 tokens)
- Long job description (e.g., 5 sentences about culture, tech stack, growth) → 2–3 chunks (300 tokens each)

Token-based splits would break semantic units (bad), trying to achieve uniform chunk size.

### Implications for Claude Assessment

**Pro:** Claude sees complete thoughts, makes better predictions.

**Con:** Chunks are variable size. Estimator must handle this.

**Solution:** Use tiktoken to count actual tokens in each chunk. Don't assume 400 tokens per chunk.

```python
chunks = chunk_by_sentences(text, target_tokens=400)
for chunk in chunks:
    tokens = count_tokens(chunk)  # Actual count, might be 350 or 450
    cost = tokens * 0.000003
```

---

## 3. Token Counting Strategy: Before vs After LLM

### Decision

**Selected:** tiktoken for estimates (before API call), Claude API response for actual

### Why Count Before?

1. **Cost Transparency:** User sees estimate before expensive API call
2. **Confirmation Gate:** User can cancel if estimate is too high
3. **Budget Tracking:** Prevent surprise overspending

Example:
```
Extracted job: "Senior Python Developer..."
Estimated tokens: 650
Estimated cost: $0.002
Proceed? [y/n]
```

### Why Track Actual After?

1. **Refinement:** Compare actual vs estimated for future improvement
2. **Billing Accuracy:** Record what Claude actually charged
3. **Debugging:** Find edge cases where token count differs significantly

Example:
```
Job: "Senior Python Developer..."
Estimated tokens: 650 → Actual tokens: 673 (difference: +3.5%)
Estimated cost: $0.002 → Actual cost: $0.002 (rounding hides small differences)
```

### Storage Pattern

Track both in cost_tracking table:
```sql
INSERT INTO cost_tracking
  (job_id, estimated_tokens, actual_tokens, estimated_cost, actual_cost, api_call_time_ms)
VALUES ('job-1', 650, 673, 0.00195, 0.00202, 1250)
```

Over time, if actual > estimated consistently, refine estimator.

---

## 4. StateManager Centralization: Why Not Distributed State?

### Decision

**Selected:** Single centralized StateManager (not distributed state across Panels)

### Why Centralization?

#### Problem with Distributed State

If each Panel tracks its own progress:
```python
class CrawlPanel:
    def __init__(self):
        self.processed = 0
        self.total = 100
        self.tokens = 0

    # ❌ Multiple Panels have different numbers for "total jobs"
    # ❌ Cost tracking split across panels (harder to sum)
    # ❌ If one panel updates incorrectly, inconsistency
```

#### Solution: Centralized StateManager

```python
state = StateManager()
state.phase_status["crawl"] = PhaseStatus.RUNNING
state.phase_metrics["crawl"].total_items = 100
state.phase_metrics["crawl"].processed_items = 50

# All panels observe same state
crawl_panel.render()     # Reads state.phase_metrics["crawl"]
phase_indicator.render() # Reads state.phase_metrics["crawl"]
header.render()          # Reads state.total_tokens_used (sum of all phases)
```

### Benefits

1. **Consistency:** All panels show same progress, cost, tokens
2. **Testability:** State transitions easy to test
3. **Debugging:** One place to inspect workflow progress
4. **Thread-Safety:** Single point of mutation (with proper locking)

### Constraints

**Don't mutate StateManager from multiple async tasks simultaneously:**
```python
# ❌ BAD: Race condition
async def crawl_job(job, state):
    state.increment_phase_progress("crawl")  # Multiple tasks doing this
    # Race: two tasks call increment() at same time

# ✅ GOOD: Exclusive work
@work(exclusive=True)
async def crawl_all(state):
    for job in jobs:
        state.increment_phase_progress("crawl")  # Only one task
```

---

## 5. Storage Layer: SQLite + FTS5

### Decision

**Selected:** SQLite with FTS5 full-text search (not PostgreSQL, NoSQL, in-memory)

### Why SQLite?

#### Alternative 1: PostgreSQL
- **Pro:** More powerful (JSONB, advanced indexing), handles concurrency better
- **Con:** Requires server, adds deployment complexity, overkill for single machine

#### Alternative 2: NoSQL (MongoDB, Firestore)
- **Pro:** Flexible schema, easy horizontal scaling
- **Con:** Overkill for structured data, slower queries for our use case, requires external service

#### Alternative 3: In-Memory (Python dict)
- **Pro:** Fast for small datasets
- **Con:** No persistence, can't query 1000+ jobs quickly, data lost on restart

#### SQLite is Right-Sized
- Single-machine use case (no server)
- Persistent (ACID guarantees, data survives crash)
- Fast queries with FTS5 (<100ms on 1000+ jobs)
- Simple deployment (single file: `data/ats_playground.db`)

### FTS5 for Full-Text Search

```sql
CREATE VIRTUAL TABLE jobs_fts USING fts5(
  title, location, clean_text
);

-- Query completes in <100ms
SELECT * FROM jobs_fts WHERE jobs_fts MATCH 'python AND kubernetes'
```

### Constraint: Single-Writer Pattern

SQLite locks on writes. Multiple processes assessingconcurrently cause deadlocks.

**Solution:** Use queue or single-process pattern.
```python
# ✅ GOOD: Single assessment process
uv run python -m src.cli assess --cv data/cv.json

# ❌ BAD: Multiple concurrent processes
uv run python -m src.cli assess --cv data/cv.json &
uv run python -m src.cli assess --cv data/cv.json &
# ^ Deadlock
```

---

## 6. Claude 3.5 Sonnet (Not Batch API)

### Decision

**Selected:** Claude 3.5 Sonnet sync API (not Batch API)

### Why Not Batch API?

Batch API is optimized for:
- Large volumes of independent tasks
- Latency-tolerant workflows (results in 24h)
- Cost savings (50% cheaper: $0.003 → $0.0015 per 1M input tokens)

ATS Showcase needs:
- Results immediately (for interactive verification)
- Show top matches as jobs are assessed (real-time)
- User can see progress + cost accumulation live

**Batch API doesn't fit** (24-hour wait is incompatible with interactive workflow).

### Why 3.5 Sonnet?

**Available Claude models (as of 2026-07):**
- Claude 3.5 Sonnet: Fast, cost-effective ($0.003/1M input)
- Claude Opus: More capable, slower, more expensive ($0.015/1M input)
- Claude Haiku: Fastest, less capable ($0.00080/1M input)

**Choice:** 3.5 Sonnet balances speed + accuracy + cost.
- Fast enough: 2–5 jobs/min (acceptable for workflow)
- Accurate: Good at CV matching, reasoning
- Cost-effective: $0.003/1M (reasonable for user budget)

### Rate Limits

Claude has soft limits:
- RPM (Requests Per Minute): ~10 RPM
- TPM (Tokens Per Minute): ~50k TPM

**For ATS:** If processing 100 jobs at 650 tokens/job = 65k tokens needed. With 50k TPM limit, assessments queue up naturally.

**Don't need exponential backoff for each job.** Just queue and let Claude's rate limiting handle it.

---

## References

- **Textual:** https://textual.textualize.io/
- **Rich:** https://rich.readthedocs.io/
- **Claude API:** https://docs.anthropic.com/
- **GitHub Issue #89:** https://github.com/pluto-atom-4/ats-showcase/issues/89

---

**Last Updated:** 2026-07-04

**Next:** See DESIGN.md for 1-page decision summaries. See `.claude/rules/` for implementation patterns.
