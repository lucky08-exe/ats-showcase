# Database Integrity & Repair Guide

Comprehensive guide to detecting, inspecting, and safely repairing database anomalies in the ATS Showcase assessment database.

---

## Overview

The integrity module performs **12 automated checks** to detect:
- Orphaned records (assessments/preprocessed data without matching jobs)
- Invalid scores (outside 0-100 range)
- Malformed JSON in recommendations field
- Missing preprocessing data for assessments
- Orphaned FTS (full-text search) index entries
- FTS data consistency issues (NULL job_ids in FTS)
- NULL job_ids in assessments (should be auto-generated)
- Status inconsistencies between tables
- Dangling cost tracking entries
- Duplicate assessments for same job_id

**Safety first**: All destructive operations use dry-run mode by default. Requires explicit `--force` flag for actual deletion.

---

## Command: `integrity check`

Run comprehensive database integrity checks and generate report.

### Basic Usage

```bash
# Display report to stdout (markdown format)
uv run python -m src.cli integrity check

# Save to file
uv run python -m src.cli integrity check --output report.md

# JSON format (machine-readable)
uv run python -m src.cli integrity check --format json

# CSV format (spreadsheet-friendly)
uv run python -m src.cli integrity check --format csv
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output` | TEXT | None | Save report to file (default: stdout) |
| `--format` | TEXT | markdown | Report format: `markdown`, `json`, `csv` |
| `--db` | TEXT | `data/ats_playground.db` | Path to assessment database |

### Output Example (Markdown)

```markdown
# Database Integrity Report
Generated: 2026-06-28 14:23:00 UTC

## Summary
- **Total Issues Found**: 12
- **Total Checks Run**: 11
- **Records Affected**: 8
- **Errors**: 5
- **Warnings**: 7
- **Info**: 0

## Issues by Type
| Type | Count |
|------|-------|
| orphaned_assessment | 3 |
| invalid_score | 2 |
| malformed_json | 5 |
| fts_orphan | 2 |

## Recommended Actions
1. purge_orphaned_assessments (high priority)
2. purge_invalid_scores (high priority)
3. purge_malformed_recommendations (soft delete)

## Detailed Issues

### ERROR
- **orphaned_job_id_001** (job_assessments)
  - Type: orphaned_assessment
  - Details: Assessment exists but job_id 'orphaned_job_id_001' not in jobs table
  - Action: Delete orphaned assessment record
```

### 12 Checks Explained

1. **Orphaned Assessments**: assessments without matching job_id in jobs table
2. **Orphaned Preprocessed**: preprocessed_jobs without matching job_id
3. **Invalid Scores**: scores outside [0, 100] range
4. **Malformed JSON**: recommendations field fails JSON parsing
5. **Duplicate Assessments**: multiple assessments for same job_id (UNIQUE constraint prevents, but check validates)
6. **Missing Preprocessing**: assessments without corresponding preprocessed_jobs record
7. **FTS Orphans**: full-text search index entries without matching assessment (by rowid)
8. **FTS Data Consistency**: FTS entries with NULL job_id (out of sync with main table)
9. **NULL Job IDs**: assessments with NULL job_id (should be auto-generated from title/company/location)
10. **Status Inconsistencies**: jobs.status ≠ job_reviews.status
11. **Missing Cost Tracking**: cost_tracking entries without matching job_id
12. **Orphaned Job Reviews**: job_reviews with NULL or invalid job_id (should reference job_assessments)

---

## Command: `integrity purge`

Safely delete invalid data with transactional guarantees and backup support.

### Basic Usage

```bash
# Dry-run (preview what would be deleted)
uv run python -m src.cli integrity purge --type orphaned_assessments

# Actual deletion (requires --force)
uv run python -m src.cli integrity purge --type orphaned_assessments \
  --no-dry-run --force --backup-dir ./backups
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--type` | TEXT | Required | Issue type to purge: `orphaned_assessments`, `orphaned_preprocessed`, `invalid_scores`, `malformed_recommendations`, `fts_orphans`, `fts_data_mismatch`, `null_job_ids`, `orphaned_job_reviews` |
| `--backup-dir` | TEXT | `./backups/{timestamp}` | Directory for backup files before deletion |
| `--dry-run` | FLAG | True | Preview deletions without modifying database |
| `--no-dry-run` | FLAG | False | Actually perform deletions (requires --force) |
| `--force` | FLAG | False | Required for non-dry-run operations |
| `--db` | TEXT | `data/ats_playground.db` | Path to assessment database |

### Workflow: Safe Deletion

**Step 1: Check for issues**
```bash
uv run python -m src.cli integrity check --output before.md
```

**Step 2: Dry-run purge (preview)**
```bash
uv run python -m src.cli integrity purge --type orphaned_assessments
# Output: "[DRY RUN] Would delete 5 orphaned assessment records (IDs: job_123, job_124, ...)"
```

**Step 3: Create backup**
```bash
uv run python -m src.cli integrity purge --type orphaned_assessments \
  --backup-dir ./backups --no-dry-run --force
# Output: "Backed up 5 records to ./backups/2026-06-28-001/orphaned_assessments.csv"
# Output: "Deleted 5 orphaned assessment records"
```

**Step 4: Verify cleanup**
```bash
uv run python -m src.cli integrity check --output after.md
# Compare before.md and after.md
```

### Safety Mechanisms

**Dry-run enabled by default**:
- Shows what would be deleted (record count + IDs)
- No database modifications
- Requires explicit `--no-dry-run --force` for actual deletion

**Transactional safety**:
- All deletions wrapped in SQLite transaction
- Rollback on any error (all-or-nothing semantics)
- No partial deletes possible

**Mandatory backup before purge**:
- Auto-creates `./backups/{timestamp}/` directory
- Exports records to CSV before deletion
- Log shows exact backup location

### Purge Types

**orphaned_assessments**
- Deletes assessments with job_id not in jobs table
- Risk: None (orphaned data has no parent)
- Example: `uv run python -m src.cli integrity purge --type orphaned_assessments --no-dry-run --force`

**orphaned_preprocessed**
- Deletes preprocessed_jobs with job_id not in jobs table
- Risk: None (orphaned data has no parent)

**invalid_scores**
- Deletes assessments with scores outside [0, 100]
- Risk: **HIGH** — may contain otherwise valid assessments
- Recommendation: Review before purge

**malformed_recommendations**
- Sets recommendations field to NULL (soft-delete, no row deletion)
- Risk: Low (only nullifies data)
- Recommendation: Safe to run automatically

**fts_orphans**
- Rebuilds FTS5 full-text search index, removes orphaned rowid entries
- Risk: None (structural cleanup only)

**fts_data_mismatch**
- Rebuilds FTS5 index to refresh indexed content from main table
- Fixes out-of-sync entries (e.g., NULL job_ids in FTS)
- Risk: None (refreshes data from source)

**null_job_ids**
- Regenerates missing job_ids for assessments using title/company/location
- Deduplicates assessments with identical title/company/location (keeps first)
- Risk: None (generates deterministic IDs, removes duplicates)

**orphaned_job_reviews**
- Deletes job_reviews with NULL or non-existent job_id
- Detects orphaned records (job_reviews.job_id not in job_assessments)
- Background: job_reviews table has FK to jobs(id), but assessments are stored in job_assessments
- Risk: None (orphaned records are disconnected from assessment workflow)

---

## Command: `integrity repair`

Auto-repair safe integrity issues without manual intervention.

### Basic Usage

```bash
# Preview repairs
uv run python -m src.cli integrity repair

# Apply repairs
uv run python -m src.cli integrity repair --no-dry-run --force
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run` | FLAG | True | Preview repairs without modifying database |
| `--no-dry-run` | FLAG | False | Apply repairs (requires --force) |
| `--force` | FLAG | False | Required for non-dry-run operations |
| `--db` | TEXT | `data/ats_playground.db` | Path to assessment database |

### What Repair Does

1. **Soft-delete malformed JSON**: Sets recommendations to NULL (preserves assessment record)
2. **Rebuild FTS index**: Runs VACUUM and REINDEX (fixes orphaned search entries)

Both operations are safe and reversible via backup.

### Example

```bash
# Preview
uv run python -m src.cli integrity repair
# Output: "[DRY RUN] Would soft-delete 3 malformed recommendations"
# Output: "[DRY RUN] Would rebuild FTS index (VACUUM + REINDEX)"

# Apply
uv run python -m src.cli integrity repair --no-dry-run --force
# Output: "Soft-deleted 3 malformed recommendations"
# Output: "Rebuilt FTS index"
```

---

## Common Workflows

### Workflow 1: Periodic Health Check

Monitor database without making changes:

```bash
# Weekly integrity check
uv run python -m src.cli integrity check --output logs/integrity_$(date +%Y%m%d).md

# Compare reports
diff logs/integrity_20260621.md logs/integrity_20260628.md
```

### Workflow 2: Clean Invalid Assessments

Remove low-quality assessments that defaulted to score 50:

```bash
# 1. Check what invalid scores exist
uv run python -m src.cli integrity check --format json | jq '.invalid_score'

# 2. Dry-run purge
uv run python -m src.cli integrity purge --type invalid_scores

# 3. Backup and delete
uv run python -m src.cli integrity purge --type invalid_scores \
  --backup-dir ./backups/invalid_scores \
  --no-dry-run --force

# 4. Verify
uv run python -m src.cli integrity check --format json | jq '.invalid_score // empty'
# (Should be empty)
```

### Workflow 3: Auto-Repair Corrupted Data

Fix common issues without manual review:

```bash
# Preview what repair will do
uv run python -m src.cli integrity repair

# Auto-repair if output is acceptable
uv run python -m src.cli integrity repair --no-dry-run --force

# Verify
uv run python -m src.cli integrity check
```

### Workflow 4: Archive Old Assessments

Backup assessments older than 90 days, then archive:

```bash
# 1. Check assessments by date
uv run python -m src.cli query --keyword "%" --min-score 0

# 2. Backup database before bulk operations
cp data/ats_playground.db data/ats_playground.db.bak

# 3. Export old assessments
uv run python -m src.cli export --output backups/old_assessments_2026Q1.md

# 4. Manual cleanup (update status, or use custom SQL)
# sqlite3 data/ats_playground.db "DELETE FROM job_assessments WHERE assessed_date < '2026-04-01';"
```

---

## Troubleshooting

### Error: "Specify --type" (purge command)

**Problem**: Ran `integrity purge` without `--type` option.

**Solution**:
```bash
# Invalid
uv run python -m src.cli integrity purge

# Valid
uv run python -m src.cli integrity purge --type orphaned_assessments
```

### Error: "--force required" (purge/repair)

**Problem**: Tried to run non-dry-run without `--force` flag.

**Solution**:
```bash
# Invalid
uv run python -m src.cli integrity purge --type invalid_scores --no-dry-run

# Valid
uv run python -m src.cli integrity purge --type invalid_scores --no-dry-run --force
```

### Error: "SQLite locked"

**Problem**: Another process is accessing the database.

**Solution**:
```bash
# Check for other processes
lsof | grep ats_playground.db

# Kill assessment process if stuck
pkill -f "python -m src.cli assess"

# Retry after 30s
sleep 30
uv run python -m src.cli integrity check
```

### Backups not created

**Problem**: Purge completed but backups directory is empty.

**Reason**: Dry-run doesn't create backups (no deletion = no need to backup).

**Solution**:
```bash
# Run with --no-dry-run to trigger actual backup
uv run python -m src.cli integrity purge --type orphaned_assessments \
  --backup-dir ./backups \
  --no-dry-run --force
```

### Report shows "No safe repairs"

**Problem**: `integrity repair` says no repairs needed.

**Meaning**: Database is clean (no malformed JSON or FTS orphans).

**Next step**:
```bash
# Run full check to see other issue types
uv run python -m src.cli integrity check
```

---

## Examples by Use Case

### Use Case: Cleanup After LLM Parsing Failures

Some assessments defaulted to score 50 due to Claude API failures. Clean them:

```bash
# 1. Identify invalid scores
uv run python -m src.cli integrity check --format json > report.json
jq '.summary_by_type.invalid_score' report.json

# 2. Backup and purge
mkdir -p backups/invalid_$(date +%Y%m%d)
uv run python -m src.cli integrity purge --type invalid_scores \
  --backup-dir backups/invalid_$(date +%Y%m%d) \
  --no-dry-run --force

# 3. Verify count decreased
uv run python -m src.cli integrity check --format json | jq '.total_issues'
```

### Use Case: Investigate Orphaned Records

Job was deleted but assessment remains. Audit before cleanup:

```bash
# 1. Export orphaned records for review
uv run python -m src.cli integrity check --output orphaned_report.md

# 2. Manual SQL query to inspect
sqlite3 data/ats_playground.db <<EOF
SELECT a.job_id, a.overall_score, a.created_at
FROM job_assessments a
LEFT JOIN jobs j ON a.job_id = j.id
WHERE j.id IS NULL
ORDER BY a.created_at DESC;
EOF

# 3. If safe to delete
uv run python -m src.cli integrity purge --type orphaned_assessments \
  --backup-dir ./backups/orphaned_audit \
  --no-dry-run --force
```

### Use Case: Rebuild Search Index

FTS entries are out of sync with assessment table:

```bash
# 1. Check FTS health
uv run python -m src.cli integrity check | grep -A 2 "fts_orphan"

# 2. Auto-repair (rebuilds index)
uv run python -m src.cli integrity repair --no-dry-run --force

# 3. Verify search works
uv run python -m src.cli query --keyword "python" --min-score 0
```

---

## Performance Notes

| Operation | Time | Database Lock |
|-----------|------|---------------|
| check (100 jobs) | <1s | Read-only |
| purge orphaned (50 records) | <2s | Exclusive (during transaction) |
| repair FTS rebuild | <5s | Exclusive (VACUUM) |
| export to markdown | <1s | Read-only |

**Best practice**: Run `check` and `purge` during low-activity windows (e.g., end of business day).

---

## Integration with Crawl/Assess Pipeline

**When to run integrity checks**:

1. **After crawl** — Verify no duplicate jobs
2. **After preprocessing** — Verify all preprocessed_jobs have matching jobs
3. **After assess** — Verify no invalid scores, malformed JSON
4. **Before export** — Ensure clean data in report

**Example automated workflow**:

```bash
# Crawl phase
uv run python -m src.cli crawl --config config/companies.json

# Quick integrity check
uv run python -m src.cli integrity check | grep "Total Issues"

# Preprocess
uv run python -m src.cli preprocess --show-estimates

# Assess
uv run python -m src.cli assess --cv data/cv.json

# Auto-repair (safe operations only)
uv run python -m src.cli integrity repair --no-dry-run --force

# Export clean report
uv run python -m src.cli export --output data/assessments/report.md
```

---

## Document Version

- **Version**: 1.2
- **Last Updated**: 2026-06-28
- **Coverage**: All 3 integrity commands (check, purge, repair) with workflows, safety mechanisms, troubleshooting
- **Changes**: Added orphaned job_reviews detection/purge and FTS consistency repair (12 checks total)
