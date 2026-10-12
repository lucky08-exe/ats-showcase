# POC Extraction Accuracy Report (Issue #431)

## Purpose

Measure `SkillExtractor` (`src/poc/skills/extract_skills_a.py`) and `TechExtractor` (`src/poc/technologies/extract_technologies_a.py`) against a hand-labeled set of 8 JD snippets (`tests/poc/fixtures/accuracy_eval_set.json`).

The previously reported 78% / 82% figures were computed on only 2 fixtures (`raw_jd_what_you_ll_do.md`, `raw_jd_knowledge_skills_abilities.md`). They are not representative and are not reproduced here.

## Methodology

Ground truth labeling rules:
- Lowercased, sorted, deduplicated.
- Skill labels are surface spans exactly as written in the text, including any determiner inside the span (matcher outputs surface form, not lemma). Labels are the full phrase an ideal extractor would take.
- Technology labels are the terms a perfect extractor should return, including terms outside `TECH_TERMS`.

Run both extractors over the JSON. Both extractors return sorted lists of lowercased strings.

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

The snippet set was not extended in the 2026-10-12 re-run (see Run record). No labeled real JD text was available in the repo; the `raw_jd_*.md` fixtures have no ground-truth labels.

## Metrics

For each snippet, with E = expected set and X = extracted set:

- **Hit rate** = |E ∩ X| / |E|. Undefined (N/A) when E is empty.
- **Precision** = |E ∩ X| / |X|. Undefined (N/A) when X is empty.
- **Exact match** = true iff E == X (after sort/dedupe). Reported per snippet, not in the results table.

Matching is exact string equality on lowercased strings. Aggregation across snippets is not defined here; it is for the run step to decide and document. The run step used micro aggregation (sum of hits over sum of expected / sum of extracted); see Run record below.

## Known false positives / false negatives

Source of each item: **[run]** = reproduced by a run (see Results and Run record); **[code]** = from reading `patterns.py` and the matcher code only, not exercised by the snippet set. **[fixed]** = no longer reproduces after #475 / #476 (2026-10-12 re-run).

**Skills (`extract_skills_a.py`)**
- FN, truncation at conjunction **[run]**: the noun group is `ADJ/NOUN/PROPN` only, so the span stops at `and`. "lead data science and platform teams" yields "lead data science"; the second conjunct is never matched (s6). Reproduced: sentence-initial `Lead` is tagged `VERB` by `en_core_web_md`, and the extractor returns `lead data science`. The label is the full phrase "lead data science and platform teams". Unchanged by the re-run.
- FN, truncation at punctuation or hyphen **[code]**: `-`, `,`, `.` are not in the noun group, so spans stop there. No snippet in the set exercises this.
- FN, verb not in `SKILL_VERBS` **[run]**: `manage` (s2) and `ship` (s2) are not in `SKILL_VERBS` and were not extracted. `evaluate` (s8) is also not in `SKILL_VERBS`.
- Labeling convention, inflection **[run]**: output is surface form ("building services", not lemma form "build services"), and labels follow the same convention (s6). Reproduced: `building services` is extracted. Comparing against lemma-form labels would count a spurious miss.
- FN, sentence-initial imperative mis-tagged as NOUN **[run]**: matches require spaCy `POS == VERB`. `Mentor` (s3) and `Research` (s8) were tagged `NOUN` at sentence start by `en_core_web_md` in the earlier 2026-10-12 POS probe; that probe was not repeated in the re-run, so the tags are carried forward, not re-verified. Result is unchanged in the re-run: `mentor junior engineers` and `research novel retrieval methods` are not extracted. Gerunds (`building`, s6) did match.

**Technologies (`extract_technologies_a.py`)**
- FN, hyphenated term **[fixed]**: `anchor-free detectors` (s5) was not extracted before #476 (`_generate_patterns` emitted a single `LOWER` token for a hyphenated term). After #476 it is extracted (s5 tech hit 1/2 -> 2/2, exact match yes). Reproduced on the pre-fix snapshot and the post-fix tree. `real-time inference` (also hyphenated in `TECH_TERMS`) is covered by the same change **[code]**; no snippet exercises it, so it is not verified.
- FN, vocabulary gap **[run]**: `kafka`, `terraform`, `lightning` are not in `TECH_TERMS` and were not extracted (s2, s8). `pytorch lightning` (s8) is also not in `TECH_TERMS`; only `pytorch` is extracted. Unchanged.
- FP, common word **[fixed]**: `go` was in `TECH_TERMS` and matched the verb "Go" (s7, tech precision 1/2). After #475 (context gating of `go` / `spring` / `vue`) s7 returns only `redis` (tech precision 1/1). Verified on s7 only. `spring` and `vue` are gated by the same change **[code]**; no snippet exercises them, so they are not verified.
- FP, negation not handled **[run]**: "No experience with Kubernetes required" yields `kubernetes` (s4). Unchanged. Negation handling is step 6 of #452 and is architect-gated; not addressed here.
- Not verified: whether `en_core_web_md` NER overrides `entity_ruler` spans (ruler is added `before="ner"`). Not tested by any run.

## Results

Run on 2026-10-12 against HEAD `2d93802` (includes #475 `5ee416f` and #476 `18aa412`). Format: value (numerator/denominator); N/A where the denominator is empty.

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

Per-snippet exact match (E == X):

| id | skills exact | tech exact |
|----|--------------|------------|
| s1 | yes | yes |
| s2 | no | no |
| s3 | no | yes |
| s4 | yes (both empty) | no |
| s5 | yes (both empty) | yes |
| s6 | no | yes |
| s7 | yes | yes |
| s8 | no | no |

Aggregate (micro, across the 8 snippets; N/A snippets contribute to numerator/denominator sums only where defined):

| extractor | hits | expected (E) | extracted (X) | hit rate (recall) | precision |
|-----------|------|--------------|---------------|-------------------|-----------|
| SkillExtractor | 4 | 9 | 5 | 4/9 = 0.44 | 4/5 = 0.80 |
| TechExtractor | 12 | 15 | 13 | 12/15 = 0.80 | 12/13 = 0.92 |

Exact-match counts: skills 4/8, tech 5/8. With n = 8 snippets these figures are a small labeled sample, not a benchmark.

### Before / after (#475, #476)

Baseline = pre-fix `src/` at `612626c`, same `scripts/eval_poc_accuracy.py` and same fixture, run 2026-10-12. The baseline run reproduces the previously recorded numbers exactly (skills 4/9, 5 extracted; tech 11/15, 13 extracted; exact 4/8 and 3/8), so the harness is stable across the two commits.

| metric | before (612626c) | after (2d93802) | change |
|--------|------------------|-----------------|--------|
| Skills hit / E / X | 4 / 9 / 5 | 4 / 9 / 5 | none |
| Skills precision / recall | 0.80 / 0.44 | 0.80 / 0.44 | none |
| Skills exact-match snippets | 4 / 8 | 4 / 8 | none |
| Tech hit / E / X | 11 / 15 / 13 | 12 / 15 / 13 | +1 hit (s5) |
| Tech recall | 0.73 | 0.80 | +0.07 |
| Tech precision | 0.85 | 0.92 | +0.07 (s7 `go` FP removed) |
| Tech exact-match snippets | 3 / 8 | 5 / 8 | +2 (s5, s7) |

Per-snippet tech changes (only these two; all other rows and all skills columns are identical between runs):
- s5: tech hit 1/2 -> 2/2, precision 1/1 -> 2/2. Caused by #476 (hyphenated `TECH_TERMS` now generate token patterns). `vision transformers` was already extracted; `anchor-free detectors` is the new hit.
- s7: tech extracted `['go', 'redis']` -> `['redis']`, precision 1/2 -> 1/1. Caused by #475 (context gating of `go`).

So the two fixes changed tech accuracy on this set and did not change skills accuracy. Neither fix addresses the open FNs (s2, s8 vocabulary; s3, s6, s8 skill tagging/truncation) or the s4 negation FP.

## Run record

- **Date:** 2026-10-12 (re-run for #477, after #475 and #476 merged).
- **Commit context:** post-fix run on HEAD `2d93802` (worktree branch `docs/issue-477-benchmark-rerun`, no uncommitted src changes). `src/poc/` last changed by `5ee416f` (#475) and `18aa412` (#476). Baseline run on `612626c` (`src/` exported with `git archive`; eval script and fixture copied from HEAD, identical in both runs).
- **Environment:** `/home/pluto-atom-4/Documents/full-stack/ats-playground/.venv/bin/python` (Python 3.12.12), spaCy 3.8.14, `en_core_web_md` 3.8.0.
- **Command (post-fix):** `.venv/bin/python scripts/eval_poc_accuracy.py` from the worktree root. `uv run` was not used (per task instructions, no `uv sync`); the output is the same interpreter.
- **Command (baseline):** same script run from a `src/`-only snapshot of `612626c`.
- **Script:** `scripts/eval_poc_accuracy.py` (unchanged in this re-run). Prints per-snippet E/X, hit/precision, summary table, micro totals, exact-match counts.
- **Fixture:** `tests/poc/fixtures/accuracy_eval_set.json` (unchanged; 8 snippets). Extension with real JD text was not done: no labeled real JD text is available in the repo, and the unlabeled `raw_jd_*.md` fixtures would need hand labels to be used.
- **POS probe (NOUN-tag item):** not repeated in this re-run; carried from the earlier 2026-10-12 run.
- **Not run:** the `en_core_web_md` NER-vs-`entity_ruler` question; `real-time inference`, `spring`, `vue` (no snippet covers them); any labeled set beyond the 8 snippets.

## Next step

The re-run is recorded above. No extractor logic was changed in this step. Candidate follow-ups, still gated per #452 (step 4 go/no-go before steps 5 and 6): sentence-initial verb tagging (s3, s6, s8), conjunction truncation (s6), negation handling (s4), vocabulary gaps (`kafka`, `terraform`, `lightning`, `pytorch lightning`), and verification of `real-time inference` / `spring` / `vue` on snippets that exercise them.
