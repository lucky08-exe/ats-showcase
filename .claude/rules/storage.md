---
paths:
  - "src/storage/**"
  - "tests/storage/**"
---

# Storage Phase Rules

SQLite schema, FTS5 full-text search, markdown export, query patterns.

## SQLite Schema

**Main tables:**

```sql
-- Jobs with extracted data
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  company TEXT,
  title TEXT,
  location TEXT,
  raw_html TEXT,
  clean_text TEXT,
  status TEXT, -- pending_review, confirmed, rejected
  preprocessing_version TEXT, -- Phase 2: v1.0 (legacy) or v2.0 (new)
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- Assessment results
CREATE TABLE assessments (
  assessment_id TEXT PRIMARY KEY,
  job_id TEXT FOREIGN KEY,
  cv_id TEXT,
  match_score INT,
  categories JSONB, -- {tech_skills: 85, seniority: 90, ...}
  reasoning TEXT,
  created_at TIMESTAMP,
  FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);

-- Cost tracking (for analytics)
CREATE TABLE cost_tracking (
  cost_id TEXT PRIMARY KEY,
  job_id TEXT,
  estimated_tokens INT,
  actual_tokens INT,
  estimated_cost FLOAT,
  actual_cost FLOAT,
  api_call_time_ms INT,
  created_at TIMESTAMP,
  FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);
```

**FTS5 index (full-text search):**
```sql
CREATE VIRTUAL TABLE jobs_fts USING fts5(
  title, location, clean_text
);
```

Queries complete in <100ms even with 1000+ jobs.

**Preprocessing Version Tracking (Issue #230 Phase 2 – IMPLEMENTED):**
- `v1.0` – Legacy pipeline (no boilerplate removal via clean_html)
- `v2.0` – New pipeline (70+ boilerplate patterns removed, 3-tier fallback chain for robustness)

Old jobs (v1.0): `clean_text` may contain legal disclaimers, navigation links, company taglines
New jobs (v2.0): `clean_text` cleaned with 7 boilerplate categories removed (legal, headers, company, time, salary, formatting, navigation); robust 3-tier fallback (MarkItDown → BeautifulSoup → Original) ensures preprocessing never fails

**Supported Workflows:**
1. **Selective re-preprocessing**: Query `WHERE preprocessing_version = 'v1.0'` and update to v2.0
2. **Cost analysis**: Compare token usage between pipeline versions
3. **Graceful fallback**: Revert to v1.0 if v2.0 causes quality issues
4. **Version stats**: Track job counts and cost by preprocessing version

## Database Access Pattern

<!-- @include ../.claude/rules/_common.md#database-access-pattern -->

See [_common.md](_common.md#database-access-pattern) for detailed pattern.

## Markdown Export

**Generate reports from assessments:**

```python
from src.storage.export import export_markdown

export_markdown(
  store=store,
  output_file="data/assessments/report.md",
  min_score=75
)
```

**Report includes:**
- Summary (total jobs, avg score)
- Jobs sorted by match_score descending
- Each job: title, company, score, reasoning excerpt

## Verification Commands

See [Database Commands](./_common.md#database) for init, export, query, and stats commands.

## Important Notes

- **SQLite is single-writer**: Don't run multiple assessment processes concurrently on same DB. Use a queue or single-process pattern.
- **FTS5 requires SQLite 3.9.0+**: Check version: `sqlite3 --version`
- **Backup before bulk operations**: `cp data/ats_playground.db data/ats_playground.db.bak`
