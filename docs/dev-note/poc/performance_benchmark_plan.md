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
- **Run-to-run noise is larger than the fix effects.** Two post-fix runs on the same code differ by about 18% on the medium tech parse median (202.2 ms JSON vs 171.4 ms table). Differences of this size between runs are not attributable to code changes.

## Known deviation

- **Model load count (resolved in #448).** The script now loads `en_core_web_md` once per run. The same `nlp` is passed to `SkillExtractor(model_name=..., nlp=nlp)` and `TechExtractor(nlp)`, so the SkillExtractor construction timings measure only Matcher setup, not a model load. `spacy_load_ms` is now the single cold-load sample (min = median = max), not warm repeats.

---

## Results

Re-run on 2026-10-12 after the go-fix (#475) and hyphenation-fix (#476). Values are from **Post Run 1** (JSON mode, the documented default invocation, 5 repeats). **Post Run 2** (`--table`, 5 repeats) is a repeat check. **Baseline** is the pre-fix code (`612626c`, `--table`, 5 repeats, same script and fixtures). The earlier 2026-10-12 pre-fix run (recorded in the previous version of this doc) is shown as "Prior" in the comparison table.

### Run record

- **Command (Post Run 1):** `.venv/bin/python scripts/benchmark_poc_extraction.py` (JSON, default `--repeats 5`), from the worktree root.
- **Command (Post Run 2):** `.venv/bin/python scripts/benchmark_poc_extraction.py --table` (default `--repeats 5`), from the worktree root.
- **Command (Baseline):** `.venv/bin/python scripts/benchmark_poc_extraction.py --table` from a snapshot directory containing only `src/` exported from `612626c` (`git archive`), plus this script and the two raw JD fixtures copied from HEAD.
- **Date:** 2026-10-12.
- **Commit context:** post-fix runs on HEAD `2d93802` (`src/poc/` last changed by `5ee416f` #475 and `18aa412` #476). Baseline on `612626c`. Worktree branch `docs/issue-477-benchmark-rerun`.
- **Venv:** `/home/pluto-atom-4/Documents/full-stack/ats-playground/.venv/bin/python`, Python 3.12.12 (GCC 14.2.0 build); spaCy 3.8.14; `en_core_web_md` 3.8.0. `uv sync` was not run.
- **Machine:** Intel(R) Core(TM) i7-3820 CPU @ 3.60GHz; `nproc` = 8; RAM about 62.7 GiB. Single machine.
- **Other load:** load average after the three runs was 2.17 / 1.44 / 1.05 (1 / 5 / 15 min). The machine was not idle (desktop applications running). No load average was recorded at the start of this re-run.
- **Model load sample count:** `spacy.load` is one cold call per process, so min = median = max for it. `SkillExtractor` init repeats 5 times on the shared `nlp`.
- **Noise note:** the cold `spacy.load` ranged from 1483 to 1581 ms across the three runs on the same machine.

### Model load

| Metric | Post Run 1 (JSON) ms | Post Run 2 (table) ms | Baseline (table) ms | Prior (pre-fix, earlier 2026-10-12 run) ms |
|--------|----------------------|------------------------|---------------------|---------------------------------------------|
| `spacy.load` cold (single call) | 1482.697 | 1580.614 | 1537.389 | 1335.411 |
| `SkillExtractor` init (median) | 0.161 (min 0.139, max 0.354) | 0.163 (min 0.145, max 0.354) | 0.156 (min 0.139, max 0.363) | 0.141 (min 0.135, max 0.362) |

### Extraction latency (median ms; min-max in brackets)

| Size | Tokens | Metric | Post Run 1 (JSON) | Post Run 2 (table) | Baseline (table, pre-fix) | Prior (pre-fix, earlier run) |
|------|--------|--------|-------------------|--------------------|---------------------------|------------------------------|
| small (target ~100) | 379 | `SkillExtractor.extract` | 63.887 [60.182, 83.260] | 60.280 [59.469, 61.722] | 83.794 [76.247, 109.674] | 59.586 [58.843, 60.230] |
| small (target ~100) | 379 | Tech `nlp(text)` parse | 61.498 [60.954, 66.957] | 62.938 [59.483, 78.955] | 70.821 [65.709, 102.921] | 59.601 [58.510, 68.797] |
| small (target ~100) | 379 | Tech `extract(doc)` | 0.110 [0.106, 0.136] | 0.106 [0.104, 0.111] | 0.101 [0.100, 0.103] | 0.046 [0.045, 0.051] |
| medium (target ~1000) | 1137 | `SkillExtractor.extract` | 170.010 [166.809, 199.520] | 185.412 [170.790, 229.170] | 180.534 [172.522, 190.856] | 174.633 [170.080, 177.626] |
| medium (target ~1000) | 1137 | Tech `nlp(text)` parse | 202.217 [185.717, 233.271] | 171.371 [167.929, 172.873] | 181.035 [171.982, 218.217] | 166.061 [165.251, 167.008] |
| medium (target ~1000) | 1137 | Tech `extract(doc)` | 0.317 [0.315, 0.358] | 0.304 [0.303, 0.307] | 0.134 [0.134, 0.138] | 0.127 [0.127, 0.132] |
| large (target ~5000) | 4927 | `SkillExtractor.extract` | 719.662 [717.783, 931.452] | 734.508 [733.872, 742.292] | 774.085 [768.246, 808.407] | 728.291 [727.897, 741.298] |
| large (target ~5000) | 4927 | Tech `nlp(text)` parse | 723.988 [720.390, 745.525] | 748.784 [740.857, 1684.234] | 761.062 [742.916, 807.901] | 733.840 [718.925, 743.493] |
| large (target ~5000) | 4927 | Tech `extract(doc)` | 1.346 [1.320, 1.931] | 1.288 [1.281, 1.322] | 0.690 [0.602, 0.754] | 0.540 [0.539, 0.589] |

Notes on the table:
- The Post Run 2 large tech parse max (1684 ms) is a single outlier sample; it does not change the median.
- `Tech extract(doc)` medium/large is about 0.17 ms (medium) and 0.6 ms (large) higher post-fix than in the baseline run, consistently in both post-fix runs. This row is small relative to parse time. The increase is plausibly from the #475 context gating or the #476 hyphenated patterns, but it was not isolated by a per-commit run.

### Peak memory (tracemalloc)

| Size | Tokens | Post Run 1 skill peak (bytes) | Post Run 1 tech peak (bytes) | Baseline skill peak (KiB) | Baseline tech peak (KiB) | Post Run 2 skill peak (KiB) | Post Run 2 tech peak (KiB) |
|------|--------|-------------------------------|------------------------------|---------------------------|--------------------------|-----------------------------|----------------------------|
| small (target ~100) | 379 | 6,921,609 | 6,922,079 | 6759.5 | 6760.3 | 6759.8 | 6759.4 |
| medium (target ~1000) | 1137 | 20,434,031 | 20,435,520 | 19956.3 | 19956.7 | 19955.7 | 19956.7 |
| large (target ~5000) | 4927 | 88,128,646 | 88,127,193 | 86062.0 | 86062.0 | 86062.4 | 86061.6 |

Peak memory is unchanged by the fixes within a few KiB. These are tracemalloc values, which undercount native (Cython/C and vector) memory. Treat them as lower bounds.

### Manual comparison against targets

No pass/fail is computed by the script. The comparison below is manual.

- **Model load (< 2000 ms):** cold load was 1483 ms (Post Run 1), 1581 ms (Post Run 2), 1537 ms (baseline). All below the target. Single cold samples per run.
- **Extraction per ~1000-token doc (< 100 ms):** the medium input is 1137 tokens. Skill median is 170.0 ms (Post Run 1) and 185.4 ms (Post Run 2). Tech path median is 202.2 + 0.3 ms (Post Run 1) and 171.4 + 0.3 ms (Post Run 2). Baseline medians were 180.5 ms (skill) and 181.0 + 0.1 ms (tech). Both paths are above the target in every run, before and after the fixes. The target is not met.

### Before / after summary

- Model load: no meaningful change; all runs are in the 1.3-1.6 s range.
- Skill extraction latency: no meaningful change. Post-fix and baseline medians overlap within run-to-run noise. Skill code path is not changed by #475 or #476.
- Tech parse latency: no meaningful change. The parse is `nlp(text)` and is independent of the extractor fixes; differences are within noise.
- Tech `extract(doc)` latency: slightly higher post-fix (about 0.2 ms at medium, about 0.6 ms at large). Small in absolute terms.
- Peak memory: no change beyond a few KiB.
- Accuracy effects of the same two fixes are in `docs/dev-note/poc/extraction_accuracy_report.md`.
