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

## Metrics

For each snippet, with E = expected set and X = extracted set:

- **Hit rate** = |E ∩ X| / |E|. Undefined (N/A) when E is empty.
- **Precision** = |E ∩ X| / |X|. Undefined (N/A) when X is empty.
- **Exact match** = true iff E == X (after sort/dedupe). Reported per snippet, not in the results table.

Matching is exact string equality on lowercased strings. Aggregation across snippets is not defined here; it is for the run step to decide and document. The run step used micro aggregation (sum of hits over sum of expected / sum of extracted); see Run record below.

## Known false positives / false negatives

Source of each item: **[run]** = reproduced by the 2026-10-12 run (see Results and Run record); **[code]** = from reading `patterns.py` and the matcher code only, not exercised by the snippet set.

**Skills (`extract_skills_a.py`)**
- FN, truncation at conjunction **[run]**: the noun group is `ADJ/NOUN/PROPN` only, so the span stops at `and`. "lead data science and platform teams" yields "lead data science"; the second conjunct is never matched (s6). Reproduced: sentence-initial `Lead` is tagged `VERB` by `en_core_web_md`, and the extractor returns `lead data science`. The label is the full phrase "lead data science and platform teams".
- FN, truncation at punctuation or hyphen **[code]**: `-`, `,`, `.` are not in the noun group, so spans stop there. No snippet in the set exercises this.
- FN, verb not in `SKILL_VERBS` **[run]**: `manage` (s2) and `ship` (s2) are not in `SKILL_VERBS` and were not extracted. `evaluate` (s8) is also not in `SKILL_VERBS` and `research novel retrieval methods` was not extracted (see the NOUN item below for the cause on that snippet).
- Labeling convention, inflection **[run]**: output is surface form ("building services", not lemma form "build services"), and labels follow the same convention (s6). Reproduced: `building services` is extracted. Comparing against lemma-form labels would count a spurious miss.
- FN, sentence-initial imperative mis-tagged as NOUN **[run]**: matches require spaCy `POS == VERB`. `Mentor` (s3) and `Research` (s8) are tagged `NOUN` at sentence start by `en_core_web_md` (checked with a spaCy POS probe on 2026-10-12), so `mentor junior engineers` and `research novel retrieval methods` are not extracted, although both lemmas are in `SKILL_VERBS`. Gerunds (`building`, s6) did match.

**Technologies (`extract_technologies_a.py`)**
- FN, hyphenated term **[run]**: `anchor-free detectors` (s5) is in `TECH_TERMS` but is not extracted. spaCy tokenizes `anchor-free` into multiple tokens, but `_generate_patterns` emits a single `LOWER` token for it. Same mechanism expected for `real-time inference` in `TECH_TERMS` **[code]**; no snippet exercises it.
- FN, vocabulary gap **[run]**: `kafka`, `terraform`, `lightning` are not in `TECH_TERMS` and were not extracted (s2, s8). `pytorch lightning` (s8) is also not in `TECH_TERMS`; only `pytorch` is extracted.
- FP, common word **[run]**: `go` is in `TECH_TERMS` and matches the verb "Go" (s7). `spring` and `vue` carry the same risk **[code]**; no snippet exercises them.
- FP, negation not handled **[run]**: "No experience with Kubernetes required" yields `kubernetes` (s4).
- Not verified: whether `en_core_web_md` NER overrides `entity_ruler` spans (ruler is added `before="ner"`). Not tested by the 2026-10-12 run.

## Results

Filled from the run recorded below (2026-10-12). Format: value (numerator/denominator); N/A where the denominator is empty.

| id | skills hit rate | skills precision | tech hit rate | tech precision |
|----|-----------------|------------------|---------------|----------------|
| s1 | 1.00 (1/1) | 1.00 (1/1) | 1.00 (3/3) | 1.00 (3/3) |
| s2 | 0.00 (0/2) | N/A (X empty) | 0.33 (1/3) | 1.00 (1/1) |
| s3 | 0.50 (1/2) | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) |
| s4 | N/A (E empty) | N/A (X empty) | 1.00 (1/1) | 0.50 (1/2) |
| s5 | N/A (E empty) | N/A (X empty) | 0.50 (1/2) | 1.00 (1/1) |
| s6 | 0.50 (1/2) | 0.50 (1/2) | 1.00 (2/2) | 1.00 (2/2) |
| s7 | 1.00 (1/1) | 1.00 (1/1) | 1.00 (1/1) | 0.50 (1/2) |
| s8 | 0.00 (0/1) | N/A (X empty) | 0.50 (1/2) | 1.00 (1/1) |

Per-snippet exact match (E == X):

| id | skills exact | tech exact |
|----|--------------|------------|
| s1 | yes | yes |
| s2 | no | no |
| s3 | no | yes |
| s4 | yes (both empty) | no |
| s5 | yes (both empty) | no |
| s6 | no | yes |
| s7 | yes | no |
| s8 | no | no |

Aggregate (micro, across the 8 snippets; N/A snippets contribute to numerator/denominator sums only where defined):

| extractor | hits | expected (E) | extracted (X) | hit rate (recall) | precision |
|-----------|------|--------------|---------------|-------------------|-----------|
| SkillExtractor | 4 | 9 | 5 | 4/9 = 0.44 | 4/5 = 0.80 |
| TechExtractor | 11 | 15 | 13 | 11/15 = 0.73 | 11/13 = 0.85 |

Exact-match counts: skills 4/8, tech 3/8. With n = 8 snippets these figures are a small labeled sample, not a benchmark.

## Run record

- **Date:** 2026-10-12
- **Environment:** main repo venv `/home/pluto-atom-4/Documents/full-stack/ats-playground/.venv/bin/python`, spaCy 3.8.14, `en_core_web_md` 3.8.0, run from a git worktree of this branch.
- **Command:** `uv run python scripts/eval_poc_accuracy.py` (from repo root; run 2026-10-12 with the main repo venv, outputs identical).
- **Script:** `scripts/eval_poc_accuracy.py` (the Methodology snippet, extended to compute E/X, hit rate, precision, exact match, and micro totals). Committed with this report so the numbers are reproducible.
- **POS probe (for the NOUN-tag item):** ad-hoc `spacy.load("en_core_web_md")` over the s3/s6/s8 sentence openings, printing `tag_`/`pos_`, run 2026-10-12; the probe script is not committed (one-off `tag_`/`pos_` print).
- **Not run:** the `en_core_web_md` NER-vs-`entity_ruler` question; `real-time inference`, `spring`, `vue` (no snippet covers them).

## Next step

Run recorded above. Any extractor failure is a follow-up issue; extractor logic was not changed as part of this step. Candidate follow-ups from the run: sentence-initial verb tagging (s3, s6, s8), hyphenated `TECH_TERMS` matching (s5), negation handling (s4), and `go` as a common-word false positive (s7).
