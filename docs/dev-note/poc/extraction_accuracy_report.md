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

Matching is exact string equality on lowercased strings. Aggregation across snippets is not defined here; it is for the run step to decide and document.

## Known false positives / false negatives

Justified from reading `patterns.py` and the matcher code. Not verified by running.

**Skills (`extract_skills_a.py`)**
- FN, truncation at conjunction: the noun group is `ADJ/NOUN/PROPN` only, so the span stops at `and`. "lead data science and platform teams" yields "lead data science"; the second conjunct is never matched (s6). Observed with `en_core_web_md`: sentence-initial `Lead` is tagged `VERB`, so the truncation is reproducible; the label is the full phrase "lead data science and platform teams".
- FN, truncation at punctuation or hyphen: `-`, `,`, `.` are not in the noun group, so spans stop there.
- FN, verb not in `SKILL_VERBS`: `manage`, `ship`, `evaluate`, `collaborate` never match (s2, s8).
- Labeling convention, inflection: output is surface form ("building services", not lemma form "build services"), and labels follow the same convention (s6). Comparing against lemma-form labels would count a spurious miss.
- FN, sentence-initial imperative mis-tagged as NOUN: matches require spaCy `POS == VERB`. Observed with `en_core_web_md` during review of this PR: `Mentor` (s3) and `Research` (s8) are tagged `NOUN` at sentence start, so `mentor junior engineers` and `research novel retrieval methods` are not extracted although both lemmas are in `SKILL_VERBS`. Gerunds (`building`, s6) did match. Observation from one ad-hoc run; it is not a recorded result in the table below.

**Technologies (`extract_technologies_a.py`)**
- FN, hyphenated term: spaCy tokenizes `anchor-free` into multiple tokens, but `_generate_patterns` emits a single `LOWER` token for it. Same for `real-time inference` in `TECH_TERMS` (s5).
- FN, vocabulary gap: `kafka`, `terraform`, `lightning` are not in `TECH_TERMS` (s2, s8).
- FP, common word: `go` is in `TECH_TERMS` and matches the verb "Go" (s7). `spring` and `vue` carry the same risk.
- FP, negation not handled: "No experience with Kubernetes required" yields `kubernetes` (s4).
- Not verified by reading: whether `en_core_web_md` NER overrides `entity_ruler` spans (ruler is added `before="ner"`).

## Results

Cells are filled by the run step. Do not fill from prediction.

| id | skills hit rate | skills precision | tech hit rate | tech precision |
|----|-----------------|------------------|---------------|----------------|
| s1 | PENDING-RUN | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| s2 | PENDING-RUN | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| s3 | PENDING-RUN | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| s4 | PENDING-RUN | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| s5 | PENDING-RUN | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| s6 | PENDING-RUN | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| s7 | PENDING-RUN | PENDING-RUN | PENDING-RUN | PENDING-RUN |
| s8 | PENDING-RUN | PENDING-RUN | PENDING-RUN | PENDING-RUN |

## Next step

A human or Sonnet run runs the snippet in Methodology with `en_core_web_md` installed, then fills each `PENDING-RUN` cell with the computed value. Record per-snippet exact-match alongside the table. Do not change extractor logic as part of this step; any failure found is a follow-up issue.
