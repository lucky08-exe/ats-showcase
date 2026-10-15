# Preprocessing Detail: Version Tracking & Span Strategy Examples

Moved from `.claude/rules/preprocess.md` (Issue #626, context budget trim). See that file for the current trimmed summary.

## Phase 2: Preprocessing Version Tracking (Issue #230 Phase 2)

**Purpose:** Track which preprocessing pipeline processed each job, enable selective re-preprocessing with new versions.

**Schema:** `preprocessing_version TEXT DEFAULT 'v2.0'` column in `job_reviews` table.

**Versions:**
- `v1.0` (legacy) – No boilerplate removal; raw HTML extraction
- `v2.0` (new) – 70+ boilerplate patterns removed; 3-tier fallback chain

### Selective Re-Preprocessing Workflow

Query jobs by version, re-process old jobs with new pipeline:

```bash
# Show preprocessing status
uv run python -m src.cli preprocess --show-version-stats

# Re-preprocess only v1.0 jobs to v2.0
uv run python -m src.cli preprocess \
  --cv data/cv.json \
  --re-preprocess-only-v1

# Force specific version
uv run python -m src.cli preprocess \
  --cv data/cv.json \
  --preprocessing-version 2.0
```

### API Usage (JobStore)

```python
from src.storage.job_store import JobStore

store = JobStore("data/ats_playground.db")

# Get version stats
stats = store.get_version_stats()
print(f"v1.0 jobs: {stats.get('1.0', 0)}, v2.0 jobs: {stats.get('2.0', 0)}")

# Get jobs by version
v1_jobs = store.get_jobs_by_version("v1.0")

# Update version after re-processing
for job in v1_jobs:
    # Re-process with new pipeline...
    store.update_preprocessing_version(job["job_id"], "v2.0")
```

### Cost Analysis

Compare token usage across versions:

```python
# Query cost_tracking table for version comparison
# SELECT preprocessing_version, AVG(actual_tokens), SUM(actual_cost)
# FROM jobs j
# JOIN cost_tracking c ON j.id = c.job_id
# GROUP BY preprocessing_version
```

Expected benefit: v2.0 produces ~30% fewer tokens vs v1.0 (boilerplate removed).

## Span Categorizer Strategy Code Sample (Issue #278)

```python
from src.preprocessing.span_categorizer import create_span_categorizer
from src.preprocessing.custom_span_categorizer import load_patterns
from src.preprocessing.span_types import BoundaryRules

nlp_cat = create_span_categorizer("nlp", rules=BoundaryRules())        # POS/DEP, callable on Doc
custom = create_span_categorizer("custom", patterns=load_patterns("patterns.json"))  # regex, writes doc._.custom_spans
```
