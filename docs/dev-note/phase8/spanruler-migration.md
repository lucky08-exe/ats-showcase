# POC to Production Migration: SpanRuler-Based Section Detection (Issue #281 S6)

Migration guide for transitioning v3 section-based requirement extraction from POC to production.

---

## Overview

**Goal:** Move SpanRuler-based section detection from `src/poc/` into production `src/preprocessing/` with frozen contracts and informational parity validation.

**Timeline:** Phase 5-7 completed (trigger-based); Phase 8a-b completed (span extraction); Issue #281 S5-S6 completes SpanRuler integration.

**Status:** v3 section-based extraction complete and testable. Legacy trigger-based extraction remains default (Phase 9 decision: switch assessor post-parity-review).

---

## What Moved from POC to Production

### Files Promoted

| POC Path | Production Path | Purpose |
|----------|-----------------|---------|
| `src/poc/section_patterns.py` | `src/preprocessing/section_patterns.py` | Section regex patterns + labels (frozen) |
| `src/poc/section_detector.py` | `src/preprocessing/section_detector.py` | SpanRuler-based detection API (frozen) |
| `src/poc/requirement_patterns.py` | `src/preprocessing/requirement_patterns.py` | Trigger-based classification (frozen) |
| `src/poc/extract_requirements_d.py` | `src/preprocessing/section_extractor.py` | Section-specific extraction (frozen) |

### Preprocessor API Changes

**New constructor arg (opt-in):**
```python
from src.preprocessing.section_detector import SectionDetector
from src.tokenization.preprocessor import Preprocessor

detector = SectionDetector()  # Blank pipeline + SpanRuler, no model required
preprocessor = Preprocessor(section_engine=detector)
result = preprocessor.extract_sectioned_requirements(text)
# Returns SectionedResult | None
```

**Legacy unchanged (default):**
```python
preprocessor = Preprocessor()  # No section_engine → legacy behavior
skills, tech, reqs = preprocessor.extract_entities(text)
```

### CLI Integration

**CLI flag (Phase 5-7):**
```bash
uv run python -m src.cli preprocess --preprocessing-version 3.0
```

**Storage tag (Phase 5-7):**
- `preprocessing_version = "v3.0"` in `job_reviews` table
- `VALID_PREPROCESSING_VERSIONS = ["v1.0", "v2.0", "v3.0"]` in storage.py

---

## Frozen Contracts

### SectionedResult (Immutable)

```python
@dataclass(frozen=True)
class SectionedResult:
    requirements: tuple[RequirementItem, ...]
    sections_detected: tuple[str, ...]  # Section label values in order
    requirements_by_section: dict[str, int]  # Section label → count
    schema_version: str = "3.0"  # Always "3.0"
    metadata: dict[str, Any] = field(default_factory=dict)
```

**Invariants (must hold):**
- `schema_version == "3.0"` (strictly enforced)
- All `requirement.final_confidence` ∈ [0.0, 1.0]
- `sum(requirements_by_section.values()) == len(requirements)`
- `requirements` sorted by `final_confidence` descending
- Transient output (never persisted to DB; stored as `v3.0` tag + clipped metrics only)

### RequirementItem (Immutable)

```python
@dataclass(frozen=True)
class RequirementItem:
    text: str
    trigger_word: str
    base_confidence: float  # From pattern classification
    section_boost: float   # From section context
    final_confidence: float  # base + boost, clamped [0.0, 1.0]
    source_section: SectionLabel  # Enum value
    section_display_name: str  # Human-readable name
```

**Method:**
- `to_legacy_tuple() -> (text, trigger_word, final_confidence)`

---

## Detection Design

### SectionDetector Architecture

**Input:** Plain text or markdown job description (≤200K chars)

**Processing:**
1. Create blank spaCy pipeline (no model download)
2. Add SpanRuler with 40+ regex patterns (section headers)
3. Run text through pipeline → extract spans
4. Filter non-heading-like spans (must be on line by itself)
5. Resolve overlaps (keep longest non-overlapping spans)
6. Return DetectedSection objects with content boundaries

**Output:** List of DetectedSection (label, display_name, header_text, content_text, offsets)

**No model dependency:** Blank pipeline only (spaCy.blank("en") + SpanRuler). No word vectors, NER, POS tagging.

### Pattern Library

**40+ patterns (SECTION_RULER_PATTERNS):**
- `Requirements`, `Qualifications`, `Required Skills`
- `What You'll Do`, `Responsibilities`, `Key Responsibilities`
- `Knowledge Skills & Abilities`, `Technical Skills`, `Must Have`, `Nice to Have`
- `Benefits`, `Compensation`, `Salary`, `About`, `Culture`, `Apply`, `Location`
- (See `src/preprocessing/section_patterns.py` for full list)

**Label enum (SectionLabel):**
```python
class SectionLabel(Enum):
    REQUIREMENTS = "requirements"
    QUALIFICATIONS = "qualifications"
    SKILLS_TECHNICAL = "skills_technical"
    RESPONSIBILITIES = "responsibilities"
    # ... 15+ more section types
```

**Confidence adjustments (per section):**
- `requirements` section: +0.15 boost (high signal)
- `qualifications` section: +0.10 boost (medium signal)
- `benefits` section: -1.0 boost (filtered out entirely)
- `compensation` section: -1.0 boost (filtered out entirely)

---

## Legacy vs v3 Differences

### Legacy (Phase 5-7, Current Default)

**Extraction:** Trigger-based patterns (REQUIREMENT_PATTERNS, 18 patterns)
- Matches keywords: "Required", "Must have", "Years of experience", "Knowledge of", etc.
- Returns tuple: (skills, technologies, requirements) as unique strings
- Requires spaCy model: `en_core_web_md` (word vectors, NER, POS/DEP tagging)
- **Filter:** Full-text `extract_entities()` with section-aware filtering

**Storage:** Preprocessed v1.0 or v2.0 (no v3.0 tag)

### v3 (Phase 8-9, Section-Aware)

**Extraction:** Section + trigger-based combined
- Detects section headers (SpanRuler, no model)
- Extracts bullets/sentences from each section
- Classifies each sentence with trigger patterns
- Applies section-specific confidence boosts
- Returns SectionedResult with full metadata

**Requires:** NO spaCy model (blank pipeline only)

**Advantages:**
- Model-free (works in CI without model download)
- Section awareness (requirements vs benefits handled explicitly)
- Confidence transparency (per-requirement base+boost)
- Deduplication (semantic fuzzy matching via `_find_matching_requirement`)

**Trade-offs:**
- ~20-30% more tokens vs legacy (due to section-based chunking)
- Markdown-only (section patterns rely on headers)
- Requires explicit section structure (plain paragraphs harder to detect)

---

## Parity Report Usage

**Purpose:** Informational validation of v3 vs legacy on sample fixtures.

**Run:**
```bash
# Generate report to stdout
uv run python scripts/parity_check.py

# Save to file
uv run python scripts/parity_check.py --output docs/dev-note/phase8/parity-report.md

# Custom fixtures
uv run python scripts/parity_check.py --fixtures \
  tests/preprocessing/fixtures/parity_no_headers.md \
  tests/preprocessing/fixtures/parity_benefits_heavy.md
```

**Example output (actual `uv run python scripts/parity_check.py` run):**

| Fixture | Status | v3 Count | v3 Sections | Avg Confidence | Legacy Count | Notes |
|---------|--------|----------|-------------|----------------|--------------|-------|
| raw_job_description.md | model-unavailable | 10 | SECTION_KNOWLEDGE_SKILLS, SECTION_REQUIREMENTS, SECTION_IN_OFFICE | 0.95 | 0 | spaCy model not available; legacy extraction skipped |
| parity_no_headers.md | model-unavailable | 0 | none | 0.00 | 0 | spaCy model not available; legacy extraction skipped |
| parity_benefits_heavy.md | model-unavailable | 5 | SECTION_REQUIREMENTS | 1.00 | 0 | spaCy model not available; legacy extraction skipped |

**Status meanings:**
- `equivalent` — v3 count >= legacy count (good parity)
- `review` — v3 count < legacy count OR legacy extraction error (investigate)
- `model-unavailable` — spaCy model not installed (expected in CI; no error, legacy skipped)

**Exit codes:**
- `0` — Report generated successfully, no schema invariant violations detected
- `1` — Schema invariant violation detected (confidence out of range [0.0, 1.0], count mismatch, or schema_version != "3.0")
- `2` — Fatal error (missing fixture file, bad argument, write error)

**Note on extraction exceptions:** If v3 extraction fails (e.g., bad regex pattern), the status is set to "error" but exit code remains 0. Only actual schema invariant violations (real SectionedResult with invalid data) set exit code to 1.

---

## Assessor Integration

**Current state (as of S6):** Assessor remains legacy (Phase 5-7 trigger-based).

**Why:** v3 is informational for now. Assessor depends on inline requirement extraction at assess time; switching requires separate Phase 9 slice.

**When to switch:** After human reviews parity report and approves v3 quality. Assessor switch (Phase 9) will:
1. Update `Assessor` class to accept optional `section_engine`
2. Call `preprocessor.extract_sectioned_requirements()` when `--use-v3` flag set
3. Store requirement metadata in assessment output
4. Track v3 assessor performance separately in cost_tracking

**CLI preview (Phase 9):**
```bash
# Legacy (current, default)
uv run python -m src.cli assess --cv data/cv.json

# v3 (future, opt-in)
uv run python -m src.cli assess --cv data/cv.json --use-v3-requirements
```

---

## Known Gaps & Limitations

### Issue #380: CLI Flag for Span Strategies
**Status:** Resolved (closed 2026-10-15)

CLI exposes `--categorizer-strategy nlp|custom` and `--span-patterns <json>` on the
`preprocess` command (`src/cli.py` ~L1619-1627).

### Issue #381: Span Categorizer Not Registered as Pipeline Factory
**Status:** Resolved in code (PR #618); GitHub issue still open pending closure

`custom_span_categorizer` is registered via `@Language.factory` in
`src/preprocessing/custom_span_categorizer.py` (~L466), backing the
`--categorizer-strategy custom` CLI path. The default NLP-strategy pipeline still
hard-registers `span_categorizer` directly in `Preprocessor._load_model()`
(`src/tokenization/preprocessor.py` L160-197) — that is separate, intentional
behavior, not a remaining gap.

### Issue #383: Model-Required Tests for SpaCy Spans
**Status:** Open

11 older tests in test_span_categorizer.py require `en_core_web_md` model.

**Workaround:** Tests skip gracefully if model unavailable; run locally with model installed.

---

## Production Readiness Checklist

- ✓ SectionDetector model-free, no external I/O
- ✓ SectionedResult frozen dataclass, schema pinned to "3.0"
- ✓ Preprocessor accepts optional section_engine parameter (backward compatible)
- ✓ CLI supports `--preprocessing-version 3.0` flag (Phase 5-7 slice S5)
- ✓ Parity report script (`scripts/parity_check.py`) tested with real extraction (S6)
- ✓ Schema validation on real SectionedResult objects (not dummy dicts)
- ✓ Exit codes semantics: 0 = success/no violations, 1 = schema break, 2 = fatal
- ✓ Transient output (not persisted, only v3.0 storage tag + clipped metrics)
- ✓ Assessor remains legacy (Phase 9 planned switch after parity review)

---

## Integration Timeline

| Phase | Slice | Feature | Status |
|-------|-------|---------|--------|
| 5-7 | S1-S4 | Trigger-based requirements | ✓ Production |
| 8a | S5 | Section detection + CLI flag | ✓ Production |
| 8b | S6 | Parity report + migration doc | ✓ Production (informational) |
| 9 | S7 | Assessor v3 switch (opt-in) | Planned |

---

**Last Updated:** 2026-09-25 (Issue #281 S6 Round 3)
**Status:** v3 section-based extraction complete with real SectionedResult validation, parity validation complete, ready for Phase 9 assessor integration
