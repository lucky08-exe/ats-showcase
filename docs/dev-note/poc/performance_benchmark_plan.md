# POC Extraction Performance Benchmark Plan (Issue #432)

Benchmark for the POC extractors: `SkillExtractor` (`src/poc/skills/extract_skills_a.py`) and `TechExtractor` (`src/poc/technologies/extract_technologies_a.py`).

Script: `scripts/benchmark_poc_extraction.py`

---

## What Is Measured

**(a) Model load time**
- `spacy.load("en_core_web_md")`: one cold call (first and only load in the process; reported as a single sample, min = median = max).
- `SkillExtractor(model_name="en_core_web_md")` construction with the shared pre-loaded `nlp`: `--repeats` calls (min/median/max). Measures Matcher setup only, not a model load.

**(b) Extraction latency** at three input sizes (min/median/max ms over `--repeats` calls, one untimed warm-up call first):
- Sizes (targets): small (~100), medium (~1000), large (~5000); actual counts differ, see caveats. Built by repeating the two POC fixtures (`tests/poc/fixtures/raw_jd_what_you_ll_do.md`, `tests/poc/fixtures/raw_jd_knowledge_skills_abilities.md`). Actual token counts are reported.
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
- Any `OSError` (including spaCy's missing-model error) exits with code 1 and the exception text on stderr.

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
- **"Cold" is per process, not per OS.** The cold load is the only `spacy.load` in the script. The OS file cache may still be warm.
- **Small size is not ~100 tokens.** Inputs are whole repeats of the fixtures, so the smallest input is one fixture pass, which is more than ~100. The `Tokens` column is authoritative.
- **Warm-up call excluded.** Each extraction measurement runs one untimed call before the timed repeats.
- **Timer.** `time.perf_counter()` for all latency values.
- **Single-machine numbers.** Results depend on CPU, Python build, and spaCy version. Compare runs on the same machine only.
- **Shared nlp.** `TechExtractor(nlp)` adds an `entity_ruler` to the `nlp` object used for parsing in the tech measurements. This happens once in the script.

## Known deviation

- **Model load count (resolved in #448).** The script now loads `en_core_web_md` once per run. The same `nlp` is passed to `SkillExtractor(model_name=..., nlp=nlp)` and `TechExtractor(nlp)`, so the SkillExtractor construction timings measure only Matcher setup, not a model load. `spacy_load_ms` is now the single cold-load sample (min = median = max), not warm repeats.

---

## Results

Values are from **Run 1** (JSON mode, the documented default invocation, 5 repeats). Run 2 (`--table`, 5 repeats) is listed in the Run record below as a repeat check. Raw outputs are kept outside the repo.

### Run record

- **Command:** `uv run python scripts/benchmark_poc_extraction.py` (Run 1, JSON, default `--repeats 5`). Executed as `.venv/bin/python scripts/benchmark_poc_extraction.py` from the worktree using the main repo venv.
- **Run 2 command:** `.venv/bin/python scripts/benchmark_poc_extraction.py --table` (default `--repeats 5`).
- **Date:** 2026-10-12
- **Branch / commit:** `fix/issue-450-docs-benchmark-run` based on `612626c` (includes the #448 single-load fix).
- **Machine:** Intel(R) Core(TM) i7-3820 CPU @ 3.60GHz; `nproc` = 8; RAM 65,777,220 kB (about 62.7 GiB). Single machine.
- **Software:** Python 3.12.12 (GCC 14.2.0 build); spaCy 3.8.14; `en_core_web_md` 3.8.0.
- **Other load:** Load average at start was 0.69 / 0.78 / 0.88 (1 / 5 / 15 min). Desktop applications were running (IDE, window manager, browser), each using low CPU at the time of the check. No other benchmark or heavy job was identified. Load average after Run 2 was 2.02 / 1.08 / 0.97. The machine was not otherwise idle.
- **Model load sample count:** `spacy.load` is one cold call per process, so min = median = max for it. `SkillExtractor` init repeats 5 times on the shared `nlp`.
- **Run 2 repeat check (table mode):** `spacy.load` cold 1346.592 ms. Medium skill median 167.409 ms (Run 1: 174.633). Medium tech parse median 164.486 ms (Run 1: 166.061). Large skill median 717.674 ms (Run 1: 728.291). Large tech parse median 717.965 ms (Run 1: 733.840). Only two runs were done, so no variance claim is made beyond these differences (about 1-5% on the medians shown).

### Model load

| Metric | min (ms) | median (ms) | max (ms) |
|--------|----------|-------------|----------|
| `spacy.load` cold (single call) | 1335.411 | 1335.411 | 1335.411 |
| `SkillExtractor` init | 0.135 | 0.141 | 0.362 |

### Extraction latency

| Size | Tokens | Metric | min (ms) | median (ms) | max (ms) |
|------|--------|--------|----------|-------------|----------|
| small (target ~100) | 379 | `SkillExtractor.extract` | 58.843 | 59.586 | 60.230 |
| small (target ~100) | 379 | Tech `nlp(text)` parse | 58.510 | 59.601 | 68.797 |
| small (target ~100) | 379 | Tech `extract(doc)` | 0.045 | 0.046 | 0.051 |
| medium (target ~1000) | 1137 | `SkillExtractor.extract` | 170.080 | 174.633 | 177.626 |
| medium (target ~1000) | 1137 | Tech `nlp(text)` parse | 165.251 | 166.061 | 167.008 |
| medium (target ~1000) | 1137 | Tech `extract(doc)` | 0.127 | 0.127 | 0.132 |
| large (target ~5000) | 4927 | `SkillExtractor.extract` | 727.897 | 728.291 | 741.298 |
| large (target ~5000) | 4927 | Tech `nlp(text)` parse | 718.925 | 733.840 | 743.493 |
| large (target ~5000) | 4927 | Tech `extract(doc)` | 0.539 | 0.540 | 0.589 |

### Peak memory (tracemalloc)

| Size | Tokens | Skill peak (bytes) | Tech parse + extract peak (bytes) |
|------|--------|--------------------|-----------------------------------|
| small (target ~100) | 379 | 6,921,374 | 6,921,938 |
| medium (target ~1000) | 1137 | 20,435,398 | 20,435,571 |
| large (target ~5000) | 4927 | 88,127,224 | 88,127,130 |

These are tracemalloc values, which undercount native (Cython/C and vector) memory. Treat them as lower bounds.

### Manual comparison against targets

No pass/fail is computed by the script. The comparison below is manual and uses Run 1.

- **Model load (< 2000 ms):** `spacy_load_cold_ms` = 1335.411 ms, below the target. This is a single cold sample. Run 2 gave 1346.592 ms.
- **Extraction per ~1000-token doc (< 100 ms):** the medium input is 1137 tokens. Skill median is 174.633 ms, which is above 100 ms. Tech path median is 166.061 ms (parse) + 0.127 ms (extract) = 166.188 ms, also above 100 ms. Run 2 medians were 167.409 ms (skill) and 164.486 + 0.133 ms (tech). Both paths were above the target in both runs.
