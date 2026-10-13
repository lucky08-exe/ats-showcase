# POC Extraction Accuracy Report (Issue #431)

## Purpose

Measure `SkillExtractor` (`src/poc/skills/extract_skills_a.py`) and `TechExtractor` (`src/poc/technologies/extract_technologies_a.py`) against a hand-labeled set of 8 JD snippets (`tests/poc/fixtures/accuracy_eval_set.json`).

The previously reported 78% / 82% figures were computed on only 2 fixtures (`raw_jd_what_you_ll_do.md`, `raw_jd_knowledge_skills_abilities.md`). They are not representative and are not reproduced here.

## Methodology

Ground truth labeling rules:
- Lowercased, sorted, deduplicated.
- Skill labels are surface spans exactly as written in the text, including any determiner inside the span (matcher outputs surface form, not lemma). Labels are the full phrase an ideal extractor would take.
- Technology labels are the terms a perfect extractor should return, including terms outside `TECH_TERMS`.

Run both extractors over the JSON. Both extractors return sorted lists of lowercased strings. The harness is `scripts/eval_poc_accuracy.py`, which runs the same logic as the snippet below.

```python
import json

import spacy

from src.poc.skills.extract_skills_a import SkillExtractor
from src.poc.technologies.extract_technologies_a import TechExtractor

with open("tests/poc/fixtures/accuracy_eval_set.json", encoding="utf-8") as f:
    snippets = json.load(f)

skill_extractor = SkillExtractor(model_name="en_core_web_md")
nlp = spacy.load("en_core_web_md")
tech_extractor = TechExtractor(nlp)

for s in snippets:
    skills = skill_extractor.extract(s["text"])
    techs = tech_extractor.extract(nlp(s["text"]))
    print(s["id"], skills, techs)
```

Note: `SkillExtractor` loads its own spaCy pipeline. `TechExtractor` adds an `entity_ruler` to the `nlp` passed in, so use a separate `nlp` for tech.

### Snippet set

| id | Edge case targeted |
|----|--------------------|
| s1 | In-vocabulary verb (`deploy`) and in-vocabulary terms (`computer vision`, `aws`, `kubernetes`) |
| s2 | Out-of-vocabulary verbs (`manage`, `ship`); out-of-vocabulary terms (`kafka`, `terraform`) |
| s3 | In-vocabulary verbs (`mentor`, `define`) with `for` as span boundary |
| s4 | Negation: "No experience with Kubernetes required" |
| s5 | Hyphenated tech term (`anchor-free detectors`) |
| s6 | Truncated-phrase risk: coordinated objects split at `and`; inflected verb (`building`) |
| s7 | Determiner inside span (`the roadmap`); common word matching a tech term (`Go`) |
| s8 | Out-of-vocabulary tech term (`lightning`) as multi-word tail of an in-vocabulary term |

The snippet set was not extended in the 2026-10-12 runs (see Run record). No labeled real JD text was available in the repo; the `raw_jd_*.md` fixtures have no ground-truth labels.

## Metrics

For each snippet, with E = expected set and X = extracted set:

- **Hit rate** = |E ∩ X| / |E|. Undefined (N/A) when E is empty.
- **Precision** = |E ∩ X| / |X|. Undefined (N/A) when X is empty.
- **Exact match** = true iff E == X (after sort/dedupe). Reported per snippet, not in the results table.

Matching is exact string equality on lowercased strings. Aggregation across snippets is micro (sum of hits over sum of expected / sum of extracted).

## Known false positives / false negatives

Source of each item: **[run]** = reproduced by a run (see Results and Run record); **[code]** = from reading `patterns.py` and the matcher code only, not exercised by the snippet set; **[issue]** = tracked in the named issue, listed here from the issue queue and not re-verified by this run. **[fixed]** = no longer reproduces on current main (`201d156`), with the run that shows it.

### Fixed on current main (`201d156`)

- **[fixed]** truncation at conjunction (#498, s6): the noun group was `ADJ/NOUN/PROPN` only, so "lead data science and platform teams" was cut to "lead data science". A coordinated pattern now yields the full span. s6 skills 1/2 -> 2/2, exact yes. [run]
- **[fixed]** verbs `manage` and `ship` not in `SKILL_VERBS` (#499). `manage` now matches: "manage kafka clusters" is extracted (s2 skills 0/2 -> 1/2). `ship` is in the list but still does not fire in s2 (see Remaining gaps). `evaluate` was added by #499; no snippet label targets it. [run]
- **[fixed]** vocabulary gaps `kafka` and `terraform` not in `TECH_TERMS` (#499). s2 tech 1/3 -> 3/3, exact yes. [run]
- **[fixed]** hyphenated tech term `anchor-free detectors` not extracted (#476, s5 tech 1/2 -> 2/2). `real-time inference` is also extracted now (probe, see below). [run]
- **[fixed]** `go` matched the verb "Go" as a tech term (#475, s7 tech precision 1/2 -> 1/1). `spring` and `vue` are gated by the same change **[code]**; no snippet exercises them.

### Remaining gaps on current main

- **FP, negation not handled (#497) [run]:** "No experience with Kubernetes required" yields `kubernetes` (s4 tech precision 1/2). Negation handling is step 6 of #452 and is architect-gated.
- **FN, sentence-initial verb tagged as NOUN or PROPN [run]:** matches require spaCy `POS == VERB`. In the s8 sentence "Research novel retrieval methods and evaluate them with PyTorch Lightning.", `Research` is tagged `NOUN`, so `research novel retrieval methods` is not extracted (s8 skills 0/1). A bare "Research novel retrieval methods." also returns `[]`. This was verified by a POS probe on 2026-10-12 (the earlier probe was carried forward, not re-run). The mechanism is the sentence-initial tag, not a pronoun object as the issue spec's wording suggests. The same tagging issue also affects s3 `Mentor` (not extracted, s3 skills 1/2) and "Design APIs, dashboards, and reports." (`Design` tagged `PROPN`, nothing extracted). Gerunds and verbs after a subject do match (`Build` is tagged `VERB` and "build data pipelines" is extracted).
- **FN, verb after a coordinating conjunction tagged as NOUN [run, new]:** in s2 "Manage Kafka clusters on GCP and ship Terraform modules for the platform team.", `ship` is tagged `NOUN` (dependency `conj`), so `ship terraform modules` is not extracted even though `ship` is in `SKILL_VERBS` (s2 skills still 1/2). This was not in the prior report; it is a POS-tagging gap of the same kind as the sentence-initial case.
- **FN, truncation at hyphen (#508) [run]:** "Build real-time inference pipelines." yields the skill `build real`, because `-` is PUNCT and ends the noun run. The tech term `real-time inference` is extracted correctly. `test_hyphenated_noun` pins the truncated output `["design high"]`, so a fix for #508 will need that test updated.
- **FN, truncation at "or" and serial lists (#509) [run]:** "Build data pipelines or streaming services." yields `build data pipelines` (the span stops at `or`). "Design APIs, dashboards, and reports." yields no skill (see sentence-initial tagging above). No snippet in the eval set contains "or" or a serial list.
- **FN, truncation at punctuation [code]:** `,` and `.` are not in the noun group, so spans stop there. No snippet exercises this beyond the list case above.
- **Labeling convention, inflection [run]:** output is surface form ("building services", not lemma form "build services"), and labels follow the same convention (s6). Reproduced: `building services` is extracted.
- **s8 label mismatch (#504) [run]:** the label is `pytorch lightning`, but the extractor returns `pytorch` and `lightning` as two separate terms. Under the current labels, the standalone `lightning` is a FP. This is new: `lightning` was added to `TECH_TERMS` by #499, and s8 tech precision moved from 1/1 to 1/2. Whether the label or the extractor is wrong is the subject of #504; this report does not resolve it.
- **"Lightning strikes" (#505) [issue]:** a probe on "Lightning strikes are rare in our data centers." returned no tech terms (no FP reproduced in this probe). The exact failing input in #505 was not confirmed, so this is not verified here.
- **Not verified [code]:** `spring` and `vue` context gating (#475) has no snippet; `pytorch lightning` as a single term is not in `TECH_TERMS`; whether `en_core_web_md` NER overrides `entity_ruler` spans (ruler is added `before="ner"`) is not tested by any run.

## Results

### Current run (HEAD `201d156`, 2026-10-12)

Includes #475 (`5ee416f`), #476 (`18aa412`), #498 (`0fbc28d`), #499 (`006e237`). Format: value (numerator/denominator); N/A where the denominator is empty. Three runs of `scripts/eval_poc_accuracy.py` produced byte-identical output.

| id | skills hit rate | skills precision | tech hit rate | tech precision |
|----|-----------------|------------------|---------------|----------------|
| s1 | 1.00 (1/1) | 1.00 (1/1) | 1.00 (3/3) | 1.00 (3/3) |
| s2 | 0.50 (1/2) | 1.00 (1/1) | 1.00 (3/3) | 1.00 (3/3) |
| s3 | 0.50 (1/2) | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) |
| s4 | N/A (E empty) | N/A (X empty) | 1.00 (1/1) | 0.50 (1/2) |
| s5 | N/A (E empty) | N/A (X empty) | 1.00 (2/2) | 1.00 (2/2) |
| s6 | 1.00 (2/2) | 1.00 (2/2) | 1.00 (2/2) | 1.00 (2/2) |
| s7 | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) |
| s8 | 0.00 (0/1) | N/A (X empty) | 0.50 (1/2) | 0.50 (1/2) |

Per-snippet exact match (E == X):

| id | skills exact | tech exact |
|----|--------------|------------|
| s1 | yes | yes |
| s2 | no | yes |
| s3 | no | yes |
| s4 | yes (both empty) | no |
| s5 | yes (both empty) | yes |
| s6 | yes | yes |
| s7 | yes | yes |
| s8 | no | no |

Aggregate (micro, across the 8 snippets):

| extractor | hits | expected (E) | extracted (X) | hit rate (recall) | precision |
|-----------|------|--------------|---------------|-------------------|-----------|
| SkillExtractor | 6 | 9 | 6 | 6/9 = 0.67 | 6/6 = 1.00 |
| TechExtractor | 14 | 15 | 16 | 14/15 = 0.93 | 14/16 = 0.88 |

Exact-match counts: skills 5/8, tech 6/8. With n = 8 snippets these figures are a small labeled sample, not a benchmark.

### Pre-fix record (HEAD `2d93802`, 2026-10-12)

Kept as the record of the state before #498 and #499. Includes #475 and #476. Values are as originally recorded.

| id | skills hit rate | skills precision | tech hit rate | tech precision |
|----|-----------------|------------------|---------------|----------------|
| s1 | 1.00 (1/1) | 1.00 (1/1) | 1.00 (3/3) | 1.00 (3/3) |
| s2 | 0.00 (0/2) | N/A (X empty) | 0.33 (1/3) | 1.00 (1/1) |
| s3 | 0.50 (1/2) | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) |
| s4 | N/A (E empty) | N/A (X empty) | 1.00 (1/1) | 0.50 (1/2) |
| s5 | N/A (E empty) | N/A (X empty) | 1.00 (2/2) | 1.00 (2/2) |
| s6 | 0.50 (1/2) | 0.50 (1/2) | 1.00 (2/2) | 1.00 (2/2) |
| s7 | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) |
| s8 | 0.00 (0/1) | N/A (X empty) | 0.50 (1/2) | 1.00 (1/1) |

Pre-fix exact match: skills s1, s4, s5, s7 yes (4/8); tech s1, s3, s5, s6, s7 yes (5/8).

Pre-fix aggregate: SkillExtractor 4 hits / 9 expected / 5 extracted (recall 0.44, precision 0.80); TechExtractor 12 hits / 15 expected / 13 extracted (recall 0.80, precision 0.92).

### Change summary: pre-fix (`2d93802`) -> current (`201d156`)

| metric | pre-fix (2d93802) | current (201d156) | change |
|--------|-------------------|-------------------|--------|
| Skills hit / E / X | 4 / 9 / 5 | 6 / 9 / 6 | +2 hits (s2 `manage kafka clusters`, s6 `lead data science and platform teams`), +1 extracted |
| Skills recall / precision | 0.44 / 0.80 | 0.67 / 1.00 | recall +0.23, precision +0.20 |
| Skills exact-match snippets | 4 / 8 | 5 / 8 | +1 (s6) |
| Tech hit / E / X | 12 / 15 / 13 | 14 / 15 / 16 | +2 hits (s2 `kafka`, `terraform`), +3 extracted (s2 kafka, terraform; s8 lightning) |
| Tech recall / precision | 0.80 / 0.92 | 0.93 / 0.88 | recall +0.13, precision -0.04 |
| Tech exact-match snippets | 5 / 8 | 6 / 8 | +1 (s2) |

Per-snippet changes:
- s2 skills: 0/2 -> 1/2 (`manage kafka clusters`; `ship terraform modules` still missing).
- s2 tech: 1/3 -> 3/3 (`kafka`, `terraform`), exact no -> yes.
- s6 skills: 1/2 -> 2/2 (`lead data science and platform teams`), exact no -> yes.
- s8 tech: precision 1/1 -> 1/2 (`lightning` added as a standalone term; label expects `pytorch lightning`). This is a regression under the current labels, tracked in #504.
- All other rows and columns are unchanged.

### Earlier before/after (#475, #476)

Baseline = pre-fix `src/` at `612626c`, same `scripts/eval_poc_accuracy.py` and same fixture, run 2026-10-12. Kept as the historical record.

| metric | before (612626c) | after (2d93802) | change |
|--------|------------------|-----------------|--------|
| Skills hit / E / X | 4 / 9 / 5 | 4 / 9 / 5 | none |
| Skills precision / recall | 0.80 / 0.44 | 0.80 / 0.44 | none |
| Skills exact-match snippets | 4 / 8 | 4 / 8 | none |
| Tech hit / E / X | 11 / 15 / 13 | 12 / 15 / 13 | +1 hit (s5) |
| Tech recall | 0.73 | 0.80 | +0.07 |
| Tech precision | 0.85 | 0.92 | +0.07 (s7 `go` FP removed) |
| Tech exact-match snippets | 3 / 8 | 5 / 8 | +2 (s5, s7) |

## Benchmark (current main, `201d156`)

Source: `scripts/benchmark_poc_extraction.py --table --repeats 5`, run 3 times on 2026-10-12. Each cell is the range across the 3 runs of that run's median (5 timed repeats after one warm-up). Inputs are the two `raw_jd_*.md` fixtures repeated to target sizes; actual token counts were 379 (small), 1137 (medium), 4927 (large) in all 3 runs.

| measurement | median range (ms) across 3 runs |
|-------------|----------------------------------|
| `spacy.load` (cold, single call) | 1353.3 – 1402.5 |
| `SkillExtractor` init | 0.29 – 0.40 |
| skill extract, small (379 tok) | 59.8 – 61.3 |
| skill extract, medium (1137 tok) | 169.5 – 174.1 |
| skill extract, large (4927 tok) | 729.8 – 740.5 |
| tech `nlp()` parse, small | 59.4 – 62.5 |
| tech `nlp()` parse, medium | 168.3 – 171.2 |
| tech `nlp()` parse, large | 708.2 – 719.9 |
| tech `extract(doc)`, small | 0.103 – 0.109 |
| tech `extract(doc)`, medium | 0.293 – 0.327 |
| tech `extract(doc)`, large | 1.258 – 1.353 |

Peak tracemalloc memory (KiB, same in all 3 runs to within about 2 KiB):

| size | tokens | skill peak | tech (parse + extract) peak |
|------|--------|------------|------------------------------|
| small | 379 | 6759.4 – 6759.8 | 6759.3 – 6759.7 |
| medium | 1137 | 19955.1 – 19956.2 | 19956.5 – 19956.7 |
| large | 4927 | 86061.8 – 86062.2 | 86061.6 – 86061.9 |

Spread of the medians across the 3 runs was at most about 4% (large skill extract). The ~18% run-to-run variance noted previously was not seen in these 3 runs; the timing noise is not claimed to be smaller in general.

Pre-fix benchmark: the report has no recorded pre-fix benchmark baseline, and none was run for this update. PENDING-RUN if a before/after timing comparison is wanted. Tech `nlp()` parse dominates the tech path; `TechExtractor.extract(doc)` is about 1 ms at large size. Skill extraction re-parses the text internally, so its cost is similar to a full `nlp()` call.

## Run record

- **Date:** 2026-10-12.
- **Commit context:** current run on HEAD `201d156` (main; worktree branch `docs/issue-506-accuracy-report`, no `src/`, `tests/`, or `scripts/` changes). Pre-fix run on `2d93802` (#477 re-run, recorded above).
- **Environment:** `/home/pluto-atom-4/Documents/full-stack/ats-playground/.venv/bin/python` (Python 3.12.12), spaCy 3.8.14, `en_core_web_md` 3.8.0. `uv run` was not used; the output is the same interpreter.
- **Accuracy command:** `.venv/bin/python scripts/eval_poc_accuracy.py` from the worktree root, 3 runs. Output identical across runs.
- **Benchmark command:** `.venv/bin/python scripts/benchmark_poc_extraction.py --table --repeats 5`, 3 runs (ranges above).
- **Targeted tests:** `tests/poc/test_skills_extractor.py -k "lemmatization_base_form or hyphenated_noun"`: 2 passed.
- **Probes (not in the harness):** a short POS and extractor probe on the sentences quoted in Remaining gaps, run with the same interpreter, to check the mechanisms named there. Results are cited inline as [run].
- **Fixture:** `tests/poc/fixtures/accuracy_eval_set.json` (unchanged; 8 snippets). No labeled real JD text is available.
- **Not run:** `spring` / `vue` / `real-time inference` on a labeled snippet (no snippet covers them); the `en_core_web_md` NER-vs-`entity_ruler` question; any labeled set beyond the 8 snippets; a pre-fix benchmark baseline; the exact input of #505.

## Next step

No extractor logic was changed in this update. Open gaps, still gated per #452 (step 4 go/no-go before steps 5 and 6):
- Sentence-initial and post-conjunction verb tagging (s3, s8 `Research`, s2 `ship`, "Design APIs" in the probe).
- Negation (#497; s4).
- Hyphen truncation (#508) and "or" / serial-list truncation (#509).
- s8 label versus extractor mismatch for `lightning` / `pytorch lightning` (#504), and the "Lightning strikes" case (#505).
- Verification of `spring` / `vue` on a snippet that exercises them.
