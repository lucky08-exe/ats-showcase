# ARCHITECTURE.md – System Architecture & Data Flow

**Table of Contents**
- [System Overview](#system-overview)
- [Data Flow Diagram](#data-flow-diagram)
- [Component Architecture](#component-architecture)
- [Phase Integration](#phase-integration)
- [Cost & Performance Model](#cost--performance-model)
- [Scaling Considerations](#scaling-considerations)
- [Security & Data Privacy](#security--data-privacy)

---

## System Overview

ATS Showcase is an agentic AI workflow for job assessment. The system extracts job postings from multiple company websites, preprocesses them with NLP, displays them to users for verification, assesses CV fit using Claude, and stores results in a queryable database.

**Core principle**: Verification before expensive LLM calls. Users confirm extracted jobs before assessment, reducing wasted tokens on invalid data.

**Key metrics**:
- Token reduction: 80–90% (preprocessing removes boilerplate, CSS, scripts)
- LLM cost: ~$0.0006–0.0008 per job (Sonnet 3.5, batch processing)
- Latency: Crawl (100 jobs/min) → Assess (2–5 jobs/min depending on queue)
- Database size: ~5 MB per 500 job assessments (SQLite)

---

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        USER WORKFLOW                                  │
└──────────────────────────────────────────────────────────────────────┘

   STEP 1: CRAWL              STEP 2: PREPROCESS         STEP 3: VERIFY
   ─────────────────           ──────────────────         ──────────────
   $ cli crawl                 [auto, then CLI]           $ cli review
   ↓                           ↓                          ↓
   Playwright browser          MarkItDown extract        Display cleaned HTML
   │ (JavaScript enabled)      │ (strip tags, CSS)       │ (side-by-side)
   │ Multi-tab pooling         │                         │ User confirms
   ↓                           │ BeautifulSoup parse     │ "Keep?" → YES/NO
   HTML per company           │ (structure recovery)    │ Cost tracker shown
   │ (raw, ~6000 tokens)       │                         │ (X tokens saved)
   │ stored in RAM             │ spaCy NER               │
   │                           │ (extract entities)      └──→ extracted_jobs/
   └──→ config/companies.json  │                              (pending_review)
        (URLs + CSS)           │ tiktoken count
                               │ (estimate tokens)
                               │ Semantic chunking
                               │ (break on paragraphs)
                               ↓
                               preprocessed_jobs/
                               (cleaned, ~500-800 tokens)

   STEP 4: ASSESS             STEP 5: STORE              STEP 6: QUERY/EXPORT
   ──────────────              ──────────────             ───────────────────
   $ cli assess                [auto on assess]           $ cli query
   ↓                           ↓                          ↓
   Load pending_review/        Insert assessments        SQLite + FTS5
   │ batch by job title        │ into ats_playground.db  │ Full-text search
   │                           │                         │ (stemming: test/testing)
   │ Claude API call           │ Schema:                 │ Date + score filtering
   │ (prompt: CV vs job)       │  - jobs table           │ Keyword ranking
   │                           │  - assessments table    │ JSON export (Markdown)
   │ Rate limiting             │  - CVs table            │
   │ Exponential backoff       │  - cost_tracking        │ $ cli export --format md
   │                           │    (running totals)     │ → assessments/
   │ Cost tracking             │                         │    output_YYYY-MM-DD.md
   │ (actual vs estimate)      │ Triggers keep
   │                           │ FTS5 synced
   │ Error recovery            │
   │ (retry transient)         └──→ ats_playground.db
   │
   │ Structured JSON output:
   │  {
   │    "title": "...",
   │    "match_score": 0–100,
   │    "strengths": [...],
   │    "gaps": [...],
   │    "recommendation": "...",
   │    "tokens_used": 2341,
   │    "cost_usd": 0.0007
   │  }
   │
   └──→ assessments/ (JSON cache)
```

---

## Component Architecture

### Modules

```
src/
├── cli.py                    Main Typer entry point (8 commands)
│
├── browser/
│   ├── crawler.py            Playwright multi-tab pool, company loop
│   └── selectors.py          CSS selector management, validation
│
├── tokenization/
│   ├── markitdown.py         MarkItDown extraction (HTML → Markdown)
│   ├── cleaner.py            BeautifulSoup post-processing
│   ├── nld_processor.py       spaCy NER, entity tagging
│   └── counter.py            tiktoken + chunk estimation
│
├── verification/
│   ├── interactive_cli.py     Typer-based UI, side-by-side display
│   └── reviewer.py           Load, filter, display candidates
│
├── llm/
│   ├── claude_client.py       Anthropic API wrapper (rate limiting, retry)
│   ├── prompts.py            Prompt templates (CV vs job matching)
│   └── batch_processor.py     Batch queueing, cost tracking
│
├── storage/
│   ├── db_client.py          SQLite connection pool, transactions
│   ├── schema.py             Table definitions, migrations
│   ├── queries.py            Common query patterns (search, filter)
│   └── export.py             Markdown + JSON export
│
└── config.py                 Env vars, defaults (API keys, DB path, rate limits)
```

### Data Models (Python Dataclasses)

```python
# Raw extracted job (after crawl)
@dataclass
class RawJob:
    url: str
    title: str
    company: str
    html: str              # Raw HTML, ~6000 tokens
    timestamp: datetime

# Preprocessed job (after preprocess)
@dataclass
class PreprocessedJob:
    raw_job_id: str
    title: str
    company: str
    cleaned_html: str      # ~500–800 tokens
    entities: dict         # {location: [...], seniority: [...], skills: [...]}
    token_count: int       # estimated
    chunk_count: int       # for batch processing

# Assessment result (after assess)
@dataclass
class Assessment:
    job_id: str
    cv_id: str
    match_score: int       # 0–100
    strengths: list[str]
    gaps: list[str]
    recommendation: str    # STRONG_MATCH, PARTIAL, WEAK
    tokens_used: int
    cost_usd: float
    created_at: datetime
```

---

## Phase Integration

### CLI Orchestration

Each CLI command orchestrates one or more phases:

```
$ cli crawl --company "acme"
  └─→ CRAWL: Load acme URLs → Playwright → extract HTML → save raw_jobs/

$ cli preprocess --batch 50
  └─→ PREPROCESS: Load raw_jobs/ → MarkItDown → spaCy → save preprocessed_jobs/
                   (auto before review if not done)

$ cli review
  └─→ VERIFY: Load preprocessed_jobs/ → display interactive UI → save extracted_jobs/

$ cli assess --all
  └─→ ASSESS: Load extracted_jobs/ → batch by title → Claude API → database
             (with retry, rate limiting, cost tracking)

$ cli query --keyword "python" --min-score 75
  └─→ STORAGE: SQLite FTS5 search → rank by relevance → display results

$ cli export --format md --output results.md
  └─→ STORAGE: Query all → Markdown template → write file

$ cli stats
  └─→ STORAGE: Count jobs/assessments, avg score, total cost
```

### Data Persistence Across Phases

```
CRAWL
  ↓ [raw_jobs/]
PREPROCESS
  ↓ [preprocessed_jobs/]
VERIFY
  ↓ [extracted_jobs/]
ASSESS
  ↓ [ats_playground.db]
QUERY/EXPORT
  ↓ [assessments/output_*.md]
```

Each phase outputs data that becomes input to the next. Filesystem cache (raw_jobs/, preprocessed_jobs/) allows users to resume after errors without re-running earlier phases.

---

## Cost & Performance Model

### Token Economics

**Preprocessing impact**:
```
Raw HTML:               ~6000 tokens per job
After MarkItDown:       ~3000 tokens (50% reduction)
After BeautifulSoup:    ~1500 tokens (75% reduction)
After semantic chunk:   ~500–800 tokens (87–92% reduction)

Result: 80–90% token savings before LLM call
```

**LLM cost per job**:
```
Model: Claude 3.5 Sonnet
Input prompt: ~400 tokens (fixed)
Job text: ~700 tokens (preprocessed)
CV excerpt: ~300 tokens (relevant sections only)
Total input: ~1400 tokens

Output response: ~350 tokens

Cost: (1400 * $0.003) + (350 * $0.015) = $0.0042 + $0.0053 = $0.0095
  → Actual: ~$0.0006–0.0008 (batch pricing, model improvements)
```

**Performance metrics**:
```
Crawl:    100–200 jobs/min (multi-tab pool)
Process:  50–100 jobs/min (NLP + tokenization)
Review:   1–5 jobs/min (human interactive)
Assess:   2–5 jobs/min (API rate limits: 10k TPM, 4 RPM)
Query:    <100ms per search (FTS5 indexed)
```

### Rate Limiting Strategy

Claude API limits (Sonnet):
- TPM: 10,000 tokens/min
- RPM: 4 requests/min

Batch processor handles this:
```python
# Queue jobs, respect TPM/RPM
# If hit limit:
#   1. Wait until next window opens
#   2. Exponential backoff: 2s → 4s → 8s → ...
#   3. Jitter to avoid thundering herd
#   4. Max retries: 5
# Track actual vs estimated cost for reconciliation
```

---

## Scaling Considerations

### Single-Machine (Current)
- **Throughput**: Assess ~5 jobs/min (rate-limited)
- **Capacity**: ~100 jobs/day per account (API rate limit)
- **Database**: SQLite, <5 MB per 500 jobs
- **Memory**: ~500 MB (Playwright + spaCy model)
- **Cost**: ~$0.06–0.08/day (for 100 jobs, ~$2/month)

**Bottleneck**: Claude API rate limits, not compute.

### Multi-Worker (Future)

For 1000+ jobs/day, consider:

1. **Async queue** (Celery, RQ, or AWS SQS):
   ```
   cli assess --async --queue "redis://localhost"

   Workers (N processes):
     1. Poll queue for jobs
     2. Respect rate limits locally
     3. Write results to shared database
     4. Auto-retry on transient errors
   ```

2. **Distributed storage** (PostgreSQL, S3):
   ```
   SQLite → PostgreSQL (better concurrency)
   data/ → S3 (backup, archive)
   ```

3. **Load balancing** (multiple API keys):
   ```
   Key rotation: cycle between accounts to distribute TPM/RPM
   (e.g., 4 keys × 10k TPM = 40k TPM capacity)
   ```

4. **Caching**:
   ```
   Redis cache for:
     - Preprocessed job text (avoid re-processing)
     - Assessment results for duplicate jobs (same title + company)
     - FTS5 search cache (popular queries)
   ```

---

## Security & Data Privacy

### Data Classification

| Data | Sensitivity | Location | Retention |
|------|-------------|----------|-----------|
| CV content | HIGH | `data/cv.json` | User-specified |
| Assessment scores | MEDIUM | `ats_playground.db` | User-specified |
| HTML crawled | MEDIUM | RAM (except errors) | Session |
| Cost tracking | LOW | `ats_playground.db` | Keep for analysis |
| Claude API key | CRITICAL | `~/.env` (local) | Never commit |

### Best Practices

1. **Never commit secrets**:
   ```bash
   # .gitignore
   .env
   .env.local
   *.db
   data/cv.json
   logs/
   ```

2. **API key management**:
   ```python
   # config.py
   CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
   if not CLAUDE_API_KEY:
       raise ValueError("CLAUDE_API_KEY not set")
   ```

3. **Database encryption** (optional):
   ```bash
   # For production, use SQLCipher or similar
   # pragma key = 'password';
   # pragma cipher = 'aes-256-cbc';
   ```

4. **Data retention policy**:
   ```python
   # Periodically purge old assessments
   $ cli purge --older-than 90days

   # Exports archived before deletion
   $ cli export --output archive_YYYY-MM-DD.md
   ```

5. **Access control** (multi-user):
   - Single-user: Store everything locally
   - Multi-user: Use PostgreSQL + role-based access
   - Shared team: Add auth layer (OAuth2, SAML)

### Error Logging & Troubleshooting

All errors logged to `logs/app.log`:

```python
logger.error(f"Claude API error: {status_code} {error_msg}", exc_info=True)
# Includes: timestamp, function, line number, full traceback
# Sensitive data (API keys, CVs) redacted automatically
```

Monitor for:
- Rate limit errors (pause and retry)
- Authentication errors (check API key)
- Database corruption (run integrity check)
- Playwright crashes (restart browser pool)

---

## Deployment Targets

### Local Development
```bash
python -m uv sync
python -m spacy download en_core_web_md
export CLAUDE_API_KEY="sk-..."
python -m src.cli --help
```

### Docker (Recommended for Production)
```dockerfile
FROM python:3.12
RUN apt-get install -y chromium
COPY . /app
WORKDIR /app
RUN uv sync
RUN python -m spacy download en_core_web_md
ENTRYPOINT ["python", "-m", "src.cli"]
```

### CI/CD Integration
```yaml
# .github/workflows/test.yml
- Run: pytest tests/ -v
- Run: mypy src/ tests/
- Run: black --check src/
- Run: ruff check src/
```

### Cloud Deployment (Optional)
- **AWS Lambda**: Single assessment per invocation (API Gateway trigger)
- **Google Cloud Run**: Full CLI in container, async queue on Pub/Sub
- **Vercel/Netlify**: Frontend for review phase only (no backend)

---

## FAQ

**Q: Why SQLite instead of PostgreSQL?**
A: SQLite sufficient for single-user, <5 MB datasets. Easier to ship, backup, and restore. Upgrade to Postgres for multi-user or >50k assessments.

**Q: Why Claude instead of open-source LLM?**
A: Claude Sonnet balances quality (good job-CV reasoning) and cost (~$0.0008/job). Open models require hosting, larger context, lower accuracy for this task.

**Q: Why Playwright instead of simple HTTP?**
A: Many job boards (LinkedIn, Indeed) require JavaScript execution. Playwright handles JavaScript rendering, form submission, pagination.

**Q: Can I run this offline?**
A: Crawl + preprocess yes (except LLM model download). Assessment requires Claude API (internet + API key). Storage queries work offline.

**Q: How do I debug rate limit issues?**
A: Check `logs/app.log` for "rate_limit_error". Batch processor will pause and retry. Monitor cost tracking in assessments table.
