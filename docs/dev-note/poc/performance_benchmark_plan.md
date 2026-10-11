# POC Extraction Performance Benchmark Plan (Issue #432)

Benchmark for the POC extractors: `SkillExtractor` (`src/poc/skills/extract_skills_a.py`) and `TechExtractor` (`src/poc/technologies/extract_technologies_a.py`).

Script: `scripts/benchmark_poc_extraction.py`

---

## What Is Measured

**(a) Model load time**
- `spacy.load("en_core_web_md")`: one cold call (first load in the process), then `--repeats` warm in-process loads (min/median/max).
- `SkillExtractor(model_name="en_core_web_md")` construction: `--repeats` calls (min/median/max). Each construction loads its own spaCy pipeline.

**(b) Extraction latency** at three input sizes (min/median/max ms over `--repeats` calls, one untimed warm-up call first):
- Sizes: small (~100 tokens), medium (~1000), large (~5000). Built by repeating the two POC fixtures (`tests/poc/fixtures/raw_jd_what_you_ll_do.md`, `tests/poc/fixtures/raw_jd_knowledge_skills_abilities.md`). Actual token counts are reported.
- Skill: `SkillExtractor.extract(text)`. Includes its internal spaCy parse.
- Tech: `nlp(text)` parse time and `TechExtractor.extract(doc)` time, reported separately.

**(c) Peak memory** per size, via `tracemalloc` (one run per extractor per size, not timed):
- Skill: `skill_peak_bytes` for `extract(text)`.
- Tech: `tech_parse_plus_extract_peak_bytes` for `extract(nlp(text))`.

**Token counts** are `len(nlp(text))`.

---

## How To Run

```bash
# JSON to stdout (default)
uv run python scripts/benchmark_poc_extraction.py

# Plain text table
uv run python scripts/benchmark_poc_extraction.py --table

# Custom repeat count (default 5, must be >= 1)
uv run python scripts/benchmark_poc_extraction.py [--table] [--repeats N]
```

Requirements:
- `en_core_web_md` installed: `uv run python -m spacy download en_core_web_md`
- Both fixture files present under `tests/poc/fixtures/`. Missing fixtures exit with code 1 and a message on stderr.
- Missing spaCy model exits with code 1 and a message on stderr.

Output JSON keys: `model`, `repeats`, `model_load` (`spacy_load_cold_ms`, `spacy_load_ms` {min_ms, median_ms, max_ms}, `skill_extractor_init_ms` {min_ms, median_ms, max_ms}), `sizes` (per label: `target_tokens`, `tokens`, `chars`, `skill_extract_ms`, `tech_parse_ms`, `tech_extract_ms`, `skill_peak_bytes`, `tech_parse_plus_extract_peak_bytes`).

---

## Target Thresholds (from Issue #432)

| Metric | Target |
|--------|--------|
| Model load (`spacy.load("en_core_web_md")`), cold | < 2 s (2000 ms) |
| Extraction per ~1000-token doc | < 100 ms |

Compare the `spacy_load_cold_ms` value against the load target. Compare the medium-size median against the extraction target, using the measured token count in the `Tokens` column (medium is not exactly 1000 tokens). Skill path: `skill_extract_ms`. Tech path: sum of the `tech_parse_ms` and `tech_extract_ms` medians (they are timed separately). No pass/fail is computed; the comparison is manual.

---

## Caveats

- **spaCy parse dominates.** Both extractors spend most time in `nlp(text)`. `TechExtractor.extract(doc)` is a loop over `doc.ents`, so the tech extraction row is small by comparison. Read the `tech_parse_ms` row as the main cost.
- **tracemalloc undercounts native memory.** It only traces Python-level allocations routed through the Python allocator. Memory allocated directly by Cython/C code inside spaCy (and vector data) may be missing from the peak. Treat peak values as lower bounds.
- **"Cold" is per process, not per OS.** The cold load is the first `spacy.load` in the script. The OS file cache may still be warm. Warm repeats are in-process only.
- **Small size is not ~100 tokens.** Inputs are whole repeats of the fixtures, so the smallest input is one fixture pass, which is more than ~100. The `Tokens` column is authoritative.
- **Warm-up call excluded.** Each extraction measurement runs one untimed call before the timed repeats.
- **Timer.** `time.perf_counter()` for all latency values.
- **Single-machine numbers.** Results depend on CPU, Python build, and spaCy version. Compare runs on the same machine only.
- **Shared nlp.** `TechExtractor(nlp)` adds an `entity_ruler` to the `nlp` object used for parsing in the tech measurements. This happens once in the script.

---

## Results

All result cells are placeholders until the benchmark is run. No values have been recorded.

### Model load

| Metric | min (ms) | median (ms) | max (ms) |
|--------|----------|-------------|----------|
| `spacy.load` cold (single call) | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| `spacy.load` warm repeats | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| `SkillExtractor` init | PENDING-RUN | PENDING-RUN | PENDING-RUN |

### Extraction latency

| Size | Tokens | Metric | min (ms) | median (ms) | max (ms) |
|------|--------|--------|----------|-------------|----------|
| small (target ~100) | PENDING-RUN | `SkillExtractor.extract` | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| small (target ~100) | PENDING-RUN | Tech `nlp(text)` parse | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| small (target ~100) | PENDING-RUN | Tech `extract(doc)` | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| medium (target ~1000) | PENDING-RUN | `SkillExtractor.extract` | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| medium (target ~1000) | PENDING-RUN | Tech `nlp(text)` parse | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| medium (target ~1000) | PENDING-RUN | Tech `extract(doc)` | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| large (target ~5000) | PENDING-RUN | `SkillExtractor.extract` | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| large (target ~5000) | PENDING-RUN | Tech `nlp(text)` parse | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| large (target ~5000) | PENDING-RUN | Tech `extract(doc)` | PENDING-RUN | PENDING-RUN | PENDING-RUN |

### Peak memory (tracemalloc)

| Size | Tokens | Skill peak (bytes) | Tech parse + extract peak (bytes) |
|------|--------|--------------------|-----------------------------------|
| small (target ~100) | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| medium (target ~1000) | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| large (target ~5000) | PENDING-RUN | PENDING-RUN | PENDING-RUN |
