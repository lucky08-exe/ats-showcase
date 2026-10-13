# POC Extraction Accuracy Report (Issue #431)

## Purpose

Measure `SkillExtractor` (`src/poc/skills/extract_skills_a.py`) and `TechExtractor` (`src/poc/technologies/extract_technologies_a.py`) against a hand-labeled set of 12 JD snippets (`tests/poc/fixtures/accuracy_eval_set.json`).

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
| s9 | Negated list: "No Java, Kubernetes, or Docker experience required." (no expected terms) |
| s10 | Positive control: "nice to have" is not a negation cue ("Kubernetes experience is nice to have.") |
| s11 | Contrast word ends negation: "No prior experience needed, but Kubernetes is required." |
| s12 | Contrast after a cue: "Not a Kubernetes shop, but we do use Docker and Python." |

s9 to s12 were added by #515 (PR #515, closes #497) to cover negation. No labeled real JD text was available in the repo; the `raw_jd_*.md` fixtures have no ground-truth labels. No sentence with an ambiguous term after a previous-cue (e.g. "Lightning") has been added yet (#514).

## Metrics

For each snippet, with E = expected set and X = extracted set:

- **Hit rate** = |E ∩ X| / |E|. Undefined (N/A) when E is empty.
- **Precision** = |E ∩ X| / |X|. Undefined (N/A) when X is empty.
- **Exact match** = true iff E == X (after sort/dedupe). Reported per snippet, not in the results table.

Matching is exact string equality on lowercased strings. Aggregation across snippets is micro (sum of hits over sum of expected / sum of extracted).

## Known false positives / false negatives

Source of each item: **[run]** = reproduced by a run (see Results and Run record); **[code]** = from reading `patterns.py` and the matcher code only, not exercised by the snippet set; **[issue]** = tracked in the named issue, listed here from the issue queue and not re-verified by this run. **[fixed]** = no longer reproduces on current main (`d0938ae`), with the run that shows it.

### Fixed on current main (`d0938ae`)

- **[fixed]** negation of technologies (#497, PR #515 merged, commit `316bfe0`): "No experience with Kubernetes required." returns `[]`. s4 tech precision 1/2 -> 1/1, exact no -> yes. The new snippets s9 to s12 pass exact. [run] Remaining negation problems are in the next section (#516).
- **[fixed]** `lightning` after a previous-cue (#505, PR #512 merged, commit `5529447`): the issue input "Experience with Lightning strikes." returns `[]` on current main and on the pre-negation baseline `136ee36`. The fix was not re-verified against the pre-#512 commit in this run. Remaining lightning false positives are tracked in #513 (open) [issue].
- **[fixed]** truncation at conjunction (#498, s6): the noun group was `ADJ/NOUN/PROPN` only, so "lead data science and platform teams" was cut to "lead data science". A coordinated pattern now yields the full span. s6 skills 1/2 -> 2/2, exact yes. [run]
- **[fixed]** verbs `manage` and `ship` not in `SKILL_VERBS` (#499). `manage` now matches: "manage kafka clusters" is extracted (s2 skills 0/2 -> 1/2). `ship` is in the list but still does not fire in s2 (see Remaining gaps). `evaluate` was added by #499; no snippet label targets it. [run]
- **[fixed]** vocabulary gaps `kafka` and `terraform` not in `TECH_TERMS` (#499). s2 tech 1/3 -> 3/3, exact yes. [run]
- **[fixed]** hyphenated tech term `anchor-free detectors` not extracted (#476, s5 tech 1/2 -> 2/2). `real-time inference` is also extracted. [run]
- **[fixed]** `go` matched the verb "Go" as a tech term (#475, s7 tech precision 1/2 -> 1/1). `spring` and `vue` are gated by the same change **[code]**; no snippet exercises them.

### Remaining gaps on current main

- **Regression, "not only X but also Y" (#516) [run]:** `not` is a negation cue with no idiom exclusion, so affirmed items in the idiom are dropped. "We run Kubernetes not only in prod but also in staging." returns `[]` on main (`136ee36` returned `['kubernetes']`). "Not only Kubernetes but also Docker is needed." returns `['docker']` on main (`136ee36`: `['docker', 'kubernetes']`). Not covered by any snippet or test.
- **Over-propagation across list joiners (#516) [run]:** negation spreads across `,` / `and` / `or` joins, so affirmed neighbours are dropped. "Python, Kubernetes is not required." returns `[]` on main (`136ee36`: `['kubernetes', 'python']`); the drop of `python` is likely wrong, though the wording is ambiguous. "We need Docker, no Kubernetes, and Redis experience." returns `['docker']` on main (`136ee36`: `['docker', 'kubernetes', 'redis']`); `redis` is dropped through the ", and" join. The same mechanism correctly removes `python` in "No Python, but Java and Kubernetes are required." (main `['java', 'kubernetes']`; `136ee36` also kept `python`). Not covered by any snippet or test.
- **FN, sentence-initial verb tagged as NOUN or PROPN [run, re-verified 2026-10-13]:** matches require spaCy `POS == VERB`. In the s8 sentence "Research novel retrieval methods and evaluate them with PyTorch Lightning.", `Research` is tagged `NOUN` (dep `compound`), so `research novel retrieval methods` is not extracted (s8 skills 0/1). The same tagging issue affects s3 `Mentor` (tagged `NOUN`, dep `nmod`; s3 skills 1/2) and "Design APIs, dashboards, and reports." (`Design` tagged `PROPN`; no skill and no tech extracted). Gerunds and verbs after a subject do match (`Build` is tagged `VERB` and "build data pipelines" is extracted).
- **FN, verb after a coordinating conjunction tagged as NOUN [run]:** in s2 "Manage Kafka clusters on GCP and ship Terraform modules for the platform team.", `ship` is tagged `NOUN` (dependency `conj`), so `ship terraform modules` is not extracted even though `ship` is in `SKILL_VERBS` (s2 skills 1/2).
- **FN, truncation at hyphen (#508) [run]:** "Build real-time inference pipelines." yields the skill `build real`, because `-` is PUNCT and ends the noun run. The tech term `real-time inference` is extracted correctly. `test_hyphenated_noun` pins the truncated output `["design high"]`, so a fix for #508 will need that test updated.
- **FN, truncation at "or" and serial lists (#509) [run]:** "Build data pipelines or streaming services." yields `build data pipelines` (the span stops at `or`). "Design APIs, dashboards, and reports." yields no skill (see sentence-initial tagging above). No snippet in the eval set contains "or" or a serial list.
- **FN, truncation at punctuation [code]:** `,` and `.` are not in the noun group, so spans stop there. No snippet exercises this beyond the list case above.
- **Labeling convention, inflection [run]:** output is surface form ("building services", not lemma form "build services"), and labels follow the same convention (s6). Reproduced: `building services` is extracted.
- **s8 label mismatch (#504, open) [run]:** the label is `pytorch lightning`, but the extractor returns `pytorch` and `lightning` as two separate terms. Under the current labels, the standalone `lightning` is a FP. `lightning` was added to `TECH_TERMS` by #499, and s8 tech precision is 1/2. Whether the label or the extractor is wrong is the subject of #504; this report does not resolve it.
- **Not verified [code]:** `spring` and `vue` context gating (#475) has no snippet; `pytorch lightning` as a single term is not in `TECH_TERMS`; whether `en_core_web_md` NER overrides `entity_ruler` spans (ruler is added `before="ner"`) is not tested by any run.

## Results

### Current run (HEAD `d0938ae`, 2026-10-13, 12 snippets)

Includes #475 (`5ee416f`), #476 (`18aa412`), #498 (`0fbc28d`), #499 (`006e237`), #505 (PR #512, `5529447`), #497 (PR #515, `316bfe0`). Format: value (numerator/denominator); N/A where the denominator is empty. Three runs of `scripts/eval_poc_accuracy.py` produced byte-identical output.

| id | skills hit rate | skills precision | tech hit rate | tech precision |
|----|-----------------|------------------|---------------|----------------|
| s1 | 1.00 (1/1) | 1.00 (1/1) | 1.00 (3/3) | 1.00 (3/3) |
| s2 | 0.50 (1/2) | 1.00 (1/1) | 1.00 (3/3) | 1.00 (3/3) |
| s3 | 0.50 (1/2) | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) |
| s4 | N/A (E empty) | N/A (X empty) | 1.00 (1/1) | 1.00 (1/1) |
| s5 | N/A (E empty) | N/A (X empty) | 1.00 (2/2) | 1.00 (2/2) |
| s6 | 1.00 (2/2) | 1.00 (2/2) | 1.00 (2/2) | 1.00 (2/2) |
| s7 | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) |
| s8 | 0.00 (0/1) | N/A (X empty) | 0.50 (1/2) | 0.50 (1/2) |
| s9 | N/A (E empty) | N/A (X empty) | N/A (E empty) | N/A (X empty) |
| s10 | N/A (E empty) | N/A (X empty) | 1.00 (1/1) | 1.00 (1/1) |
| s11 | N/A (E empty) | N/A (X empty) | 1.00 (1/1) | 1.00 (1/1) |
| s12 | N/A (E empty) | N/A (X empty) | 1.00 (2/2) | 1.00 (2/2) |

Per-snippet exact match (E == X):

| id | skills exact | tech exact |
|----|--------------|------------|
| s1 | yes | yes |
| s2 | no | yes |
| s3 | no | yes |
| s4 | yes (both empty) | yes |
| s5 | yes (both empty) | yes |
| s6 | yes | yes |
| s7 | yes | yes |
| s8 | no | no |
| s9 | yes (both empty) | yes (both empty) |
| s10 | yes (both empty) | yes |
| s11 | yes (both empty) | yes |
| s12 | yes (both empty) | yes |

Aggregate (micro, across all 12 snippets):

| extractor | hits | expected (E) | extracted (X) | hit rate (recall) | precision |
|-----------|------|--------------|---------------|-------------------|-----------|
| SkillExtractor | 6 | 9 | 6 | 6/9 = 0.67 | 6/6 = 1.00 |
| TechExtractor | 18 | 19 | 19 | 18/19 = 0.95 | 18/19 = 0.95 |

Aggregate over the original 8 snippets only (s1 to s8, same labels as before):

| extractor | hits | expected (E) | extracted (X) | recall | precision |
|-----------|------|--------------|---------------|--------|-----------|
| SkillExtractor | 6 | 9 | 6 | 0.67 | 1.00 |
| TechExtractor | 14 | 15 | 15 | 0.93 | 0.93 |

Exact-match counts over 12 snippets: skills 9/12, tech 11/12. The original 8: skills 5/8, tech 7/8. With n = 12 snippets these figures are a small labeled sample, not a benchmark.

### Effect of #515 on the 12-snippet set (same labels, pre-negation baseline `136ee36`)

Run 2026-10-13 with the same fixture and the same harness logic, against `src/` extracted from `136ee36` into a temporary directory (the main checkout was not modified). Skills are unaffected by #515 and are not repeated.

| metric | 136ee36 (before #515) | d0938ae (after #515) | change |
|--------|-----------------------|----------------------|--------|
| Tech hit / E / X | 18 / 19 / 24 | 18 / 19 / 19 | 5 fewer false positives |
| Tech precision | 18/24 = 0.75 | 18/19 = 0.95 | +0.20 |
| Tech recall | 18/19 = 0.95 | 18/19 = 0.95 | none |
| Tech exact-match snippets | 8 / 12 | 11 / 12 | +3 (s4, s9, s12) |

Per-snippet changes (tech): s4 `kubernetes` FP removed (exact no -> yes); s9 `docker`, `java`, `kubernetes` FPs removed (exact no -> yes); s12 `kubernetes` FP removed (exact no -> yes). s8 unchanged (#504). s10 and s11 were exact on both.

The "5 fewer false positives" count is the difference in X (24 - 19). The regressions listed above under "not only" and list over-propagation are not in this fixture, so they do not appear in these numbers.

### Previous run (HEAD `201d156`, 2026-10-12, 8 snippets)

Kept as the record of the state before #497 and #515. Includes #475, #476, #498, #499. Format as above.

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

Aggregate (8 snippets): SkillExtractor 6 / 9 / 6 (recall 0.67, precision 1.00); TechExtractor 14 / 15 / 16 (recall 0.93, precision 0.88). Exact-match: skills 5/8, tech 6/8.

Change summary, 201d156 -> d0938ae on the original 8 snippets: tech X 16 -> 15 (s4 `kubernetes` FP removed), tech precision 14/16 = 0.88 -> 14/15 = 0.93, tech exact 6/8 -> 7/8. Skills unchanged.

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

### Change summary: pre-fix (`2d93802`) -> `201d156`

| metric | pre-fix (2d93802) | 201d156 | change |
|--------|-------------------|---------|--------|
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

## Benchmark (current main, `d0938ae`)

Source: `scripts/benchmark_poc_extraction.py --table` (the script default is `--repeats 5`, the same setting as the previous run), run 3 times on 2026-10-13. Each cell is the range across the 3 runs of that run's median (5 timed repeats after one warm-up). Inputs are the two `raw_jd_*.md` fixtures repeated to target sizes; actual token counts were 379 (small), 1137 (medium), 4927 (large) in all 3 runs.

| measurement | median range (ms) across 3 runs | previous (201d156, 2026-10-12) |
|-------------|----------------------------------|--------------------------------|
| `spacy.load` (cold, single call) | 1360.2 – 1435.3 | 1353.3 – 1402.5 |
| `SkillExtractor` init | 0.317 – 0.486 | 0.29 – 0.40 |
| skill extract, small (379 tok) | 59.0 – 59.4 | 59.8 – 61.3 |
| skill extract, medium (1137 tok) | 167.4 – 183.8 | 169.5 – 174.1 |
| skill extract, large (4927 tok) | 716.7 – 782.5 | 729.8 – 740.5 |
| tech `nlp()` parse, small | 58.7 – 60.5 | 59.4 – 62.5 |
| tech `nlp()` parse, medium | 165.7 – 179.0 | 168.3 – 171.2 |
| tech `nlp()` parse, large | 710.7 – 738.4 | 708.2 – 719.9 |
| tech `extract(doc)`, small | 0.277 – 0.281 | 0.103 – 0.109 |
| tech `extract(doc)`, medium | 0.859 – 0.957 | 0.293 – 0.327 |
| tech `extract(doc)`, large | 4.715 – 5.005 | 1.258 – 1.353 |

`extract(doc)` is now above the previously recorded 0.1 to 1.3 ms range. Re-measurement confirms the rise: about 2.6x at small size, 2.9x at medium, and 3.7x at large, using the midpoints of the ranges above. The cause was not profiled. The suspects are the per-entity `ent.sent` lookup and the quadratic list-propagation pass added by #515 (named as suspects in #516; not measured here). By the medians, `extract(doc)` is still roughly 0.5% to 0.7% of the matching `nlp()` parse median, so the overhead is small relative to parsing.

Peak tracemalloc memory (KiB, 3 runs):

| size | tokens | skill peak | tech (parse + extract) peak |
|------|--------|------------|------------------------------|
| small | 379 | 6759.5 – 6761.0 | 6760.0 – 6760.2 |
| medium | 1137 | 19955.2 – 19956.3 | 19956.4 – 19956.5 |
| large | 4927 | 86061.8 – 86063.0 | 86061.6 – 86061.8 |

Spread of the medians across the 3 runs was up to about 10% (skill extract medium and large; run 1 was the slowest on those rows) and about 6% for tech `extract(doc)` large. The previous run's ~4% spread is not claimed to hold in general.

Pre-#515 benchmark: no before-timing for `136ee36` was run for this update, so the rise is compared against the 2026-10-12 `201d156` run only. PENDING-RUN if a same-machine before/after timing comparison is wanted. Tech `nlp()` parse dominates the tech path. Skill extraction re-parses the text internally, so its cost is similar to a full `nlp()` call.

## Run record

- **Date:** 2026-10-13.
- **Commit context:** current run on HEAD `d0938ae` (main; worktree branch `docs/issue-517-negation-reports`, docs-only change on top of `d0938ae`; no `src/`, `tests/`, or `scripts/` changes). Previous run on `201d156` (2026-10-12, recorded above). Pre-fix run on `2d93802` (#477 re-run, recorded above).
- **Environment:** `/home/pluto-atom-4/Documents/full-stack/ats-playground/.venv/bin/python` (Python 3.12.12), spaCy 3.8.14, `en_core_web_md` 3.8.0. The worktree's own venv was not used because it lacks the model.
- **Accuracy command:** `scripts/eval_poc_accuracy.py` from the worktree root, 3 runs. Output identical across runs (same MD5 for all three captured outputs).
- **Benchmark command:** `scripts/benchmark_poc_extraction.py --table` (default `--repeats 5`), 3 runs (ranges above).
- **Baseline comparison:** `136ee36` source extracted with `git archive` to a temporary directory; the 12-snippet tech comparison and the #516 example probes were run against it and against the worktree `src/`. Probe scripts were kept outside the repository and are not committed.
- **Probes (not in the harness):** POS tags for `Research`, `ship`, `Mentor`, `Design`, and the extractor outputs for the sentences quoted in Remaining gaps, run with the same interpreter. Results are cited inline as [run].
- **Fixture:** `tests/poc/fixtures/accuracy_eval_set.json` (12 snippets, s1 to s12; the 4 new snippets were added by #515). No labeled real JD text is available.
- **Not run:** a pre-#512 probe of the #505 input (the command was refused by the permission system and was not retried), so the #505 fix is verified only at post-fix commits; any labeled set beyond the 12 snippets; a pre-fix benchmark baseline; `spring` / `vue` / `real-time inference` on a labeled snippet (no snippet covers them); the `en_core_web_md` NER-vs-`entity_ruler` question.

## Next step

No extractor logic was changed in this update. Open gaps:
- Negation follow-up (#516): "not only X but also Y" regression and list over-propagation (both [run]); no snippet or test covers them yet. Add cases and before/after numbers with the fix.
- Sentence-initial and post-conjunction verb tagging (s3, s8 `Research`, s2 `ship`, "Design APIs" in the probe). Gated per #452.
- Hyphen truncation (#508) and "or" / serial-list truncation (#509).
- s8 label versus extractor mismatch for `lightning` / `pytorch lightning` (#504).
- Remaining lightning false positives after #505/#512 (#513).
- Ambiguous-term-with-previous-cue sentences in the eval set (#514).
- Verification of `spring` / `vue` on a snippet that exercises them.
- Profiling of the `extract(doc)` increase from #515 (not profiled; suspects listed above).
