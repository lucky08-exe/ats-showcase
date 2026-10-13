# POC Extractor Test Coverage Report

Issue #429. Covers the skills and technologies POC extractor tests.

## Overview

"Test functions" counts `def test_` definitions. "Collected items" is pytest's collection count, which expands parametrized cases.

| File under test | Test file | Test functions | Collected items |
|-----------------|-----------|----------------|-----------------|
| `src/poc/skills/extract_skills_a.py` (`SkillExtractor`) | `tests/poc/test_skills_extractor.py` | 40 | 42 |
| `src/poc/technologies/extract_technologies_a.py` (`TechExtractor`) | `tests/poc/test_technologies_extractor.py` | 47 | 79 |
| **Total** | | **87** | **121** |

- Requires spaCy model `en_core_web_md` (`uv run python -m spacy download en_core_web_md`). Installed version 3.8.0 (spaCy 3.8.14) in the shared `.venv`; `spacy.load` verified.
- Counts re-measured 2026-10-13 on `docs/issue-517-negation-reports` (source identical to main `d0938ae`) with `.venv/bin/python -m pytest --collect-only`.
- Runtime (run 2026-10-13, worktree `docs/issue-517-negation-reports`, source identical to `d0938ae`, `.venv/bin/python -m pytest tests/poc/ -v -p no:cacheprovider`): **1025 passed, 32 skipped, 0 failed, 0 errors, 7 warnings in 610.18 s (0:10:10)** for the whole `tests/poc/` directory. Exit 0. Python 3.12.12, pytest 9.1.1, spaCy 3.8.14, `en_core_web_md` 3.8.0.
- The two extractor files: `test_skills_extractor.py` 42 passed (42/42, 0 skipped); `test_technologies_extractor.py` 79 passed (79/79, 0 skipped). Total for the two files: 121 of 121 passed.
- The 32 skips are outside this report's scope: 29 in `tests/poc/test_extract_requirements_b.py` and 3 in `tests/poc/tweak/spacy_pipeline/test_pipeline_integration.py`. Their reasons were not investigated here.
- Fixture paths are relative (`tests/poc/fixtures/...`). Run from the repository root.

Note: this document replaces the missing `tests/poc/TEST_SUMMARY.md` referenced in issue #268 comments. No such file exists under `tests/poc/`.

## Per-file Breakdown

### `tests/poc/test_skills_extractor.py` (40 functions, 42 collected)

| Group (class) | Functions | Collected | What it covers |
|---------------|-----------|-----------|----------------|
| `TestSkillExtractorBasics` | 9 | 9 | Initialization; simple and multiple skill extraction; return type is list; lowercase output; no duplicates; newline handling; empty text; text with no verbs |
| `TestSkillExtractorPatternMatching` | 10 | 10 | `SKILL_VERBS` presence; lemmatization to base form (exact list); past tense; continuous form; descriptive nouns; optional preposition/determiner (exact expected lists); compound noun phrases; coordinated nouns kept whole at "and" (#498); "and" before a verb not merged (#498); longest-span filtering |
| `TestSkillExtractorFixtures` | 4 | 4 | Extraction from `raw_jd_what_you_ll_do.md` and `raw_jd_knowledge_skills_abilities.md`; combined extraction; accuracy check on one fixture |
| `TestSkillExtractorEdgeCases` | 9 | 9 | Punctuation; verb sequences; many modifiers; skill at sentence start/end; hyphenated noun (exact, pins #508 truncation); parenthetical context; special characters; very long phrase |
| `TestSkillExtractorSorting` | 2 | 2 | `test_results_are_sorted` (exact sorted list); `test_sorted_case_insensitive` (mixed-case input, exact lowercase sorted list) |
| `TestSkillExtractorPerformance` | 2 | 2 | Fixture extraction under a 5.0 s coarse bound; repeated extraction gives consistent results |
| `TestSkillExtractorVocabularyAdditions` | 4 | 6 | New verbs registered in `SKILL_VERBS` (#499, `manage`, `ship`, `evaluate`); base forms extracted (parametrized); inflected forms (`managing`, `evaluating`) lemmatize to the new verb; `ship` tagged as a noun is not extracted (`test_ship_as_noun_not_extracted`) |

### `tests/poc/test_technologies_extractor.py` (47 functions, 79 collected)

| Group (class) | Functions | Collected | What it covers |
|---------------|-----------|-----------|----------------|
| `TestTechExtractorBasics` | 9 | 9 | Initialization; `TECH_TERMS` populated; simple and multiple tech extraction; sorted list return; case-insensitive matching; no duplicates; empty text; text with no techs |
| `TestTechExtractorMultiWordPhrases` | 4 | 4 | Two-word phrases; `vision transformers`; case-insensitive phrase match; partial phrase not extracted |
| `TestTechExtractorFixtures` | 4 | 4 | Extraction from both fixture files; combined extraction; coverage check on knowledge/skills fixture |
| `TestTechExtractorEdgeCases` | 9 | 9 | Punctuation; term in parentheses; term in list; hyphenated phrase; terms with numbers; acronym expansion; vendor-specific terms; overlapping term names; `test_negated_known_term_not_extracted` (negated `kubernetes` is dropped, #497) |
| `TestTechExtractorNegation` | 2 | 17 | Negation scope (#497, PR #515): 16 parametrized sentences covering cues (`no`, `not`, `without`, `never`, `lacking`, `n't`), list propagation, `nice to have` as a positive control, contrast words (`but`, etc.), clause separators, and multi-sentence scope; plus a no-parser (`spacy.blank`) fallback test that asserts the whole doc is scanned |
| `TestTechExtractorSorting` | 2 | 2 | Results sorted; alphabetical order |
| `TestTechExtractorWithPreprocessing` | 2 | 2 | Extraction after document processing; entity info preserved |
| `TestTechExtractorPerformance` | 3 | 3 | Timing on knowledge/skills fixture and on a 3x repeated fixture (both under a 5.0 s coarse bound); repeated extraction consistency |
| `TestTechExtractorAmbiguousTerms` | 2 | 6 | Common-word uses of `go`, `spring`, `vue` are not extracted (#475); technology uses ("Built with Go", "Spring Boot", "Vue.js") are extracted (parametrized) |
| `TestTechExtractorHyphenatedTerms` | 1 | 3 | Hyphenated terms extracted (`anchor-free detectors`, `real-time inference`; parametrized) |
| `TestTechExtractorPatternGeneration` | 3 | 3 | Inspects `TECH_TERMS` directly (non-empty set/list/tuple; single-word terms include a Python/Java entry; multi-word terms include one containing "vision"). Does not call `_generate_patterns()`. |
| `TestTechExtractorVocabularyAdditions` | 6 | 17 | New terms (#499, `kafka`, `terraform`, `lightning`) extracted (parametrized); `lightning` as a common word not extracted; `lightning` with an adjacent tech term extracted; other ambiguous terms keep the previous-cue rule (#505 / #512) |

## Fixtures

| Fixture | File(s) | Scope | Behavior |
|---------|---------|-------|----------|
| `extractor` | `test_skills_extractor.py` | function (default) | Returns `SkillExtractor(model_name="en_core_web_md")` |
| `nlp` | `test_technologies_extractor.py` | function (default) | Returns `spacy.load("en_core_web_md")` |
| `extractor` | `test_technologies_extractor.py` | function (default) | Returns `TechExtractor(nlp)` |
| `fixture_what_you_ll_do` | both | function (default) | Reads `tests/poc/fixtures/raw_jd_what_you_ll_do.md`; returns `""` if missing |
| `fixture_knowledge_skills` | both | function (default) | Reads `tests/poc/fixtures/raw_jd_knowledge_skills_abilities.md`; returns `""` if missing |

Both fixture files exist (checked 2026-10-13). Most fixture-dependent tests guard with `if not fixture: pytest.skip(...)`, so a missing file produces a skip, not a failure. Exceptions with no guard: `test_fixture_combined_extraction` in both files, which run on empty strings if the files are missing.

## Coverage Gaps

Verified by reading the two test files and their imports (current state, as of 2026-10-13).

1. **No production integration.** Both files import only `src/poc/skills/*` and `src/poc/technologies/*` (including their `patterns` modules). Nothing from `src/cli.py`, `src/storage/`, or `src/poc/tweak/` is exercised here.
2. **Negation: covered for the #497 cases, not for the #516 regressions.** `TestTechExtractorNegation` (2 functions, 17 collected cases) and `TestTechExtractorEdgeCases::test_negated_known_term_not_extracted` cover negated known terms in `TechExtractor`. The old placeholder `test_negation_not_handled_known_limitation` no longer exists. Still not covered: the "not only X but also Y" idiom, which regresses after #515 (`We run Kubernetes not only in prod but also in staging.` returns `[]`), and list over-propagation (`Python, Kubernetes is not required.` drops `python`; `We need Docker, no Kubernetes, and Redis experience.` drops `redis`) (#516). `test_skills_extractor.py` has no negation test (no test name or body references negation; verified by grep).
3. **No adversarial input tests.** No test name or docstring in either file targets prompt-injection-style text, confusable Unicode, or malformed input beyond the special-character and punctuation cases (`test_special_characters_in_text` in the skills file; `test_sentence_with_punctuation` in both).
4. **Constructor error paths untested.** No test covers the `OSError` branch in `SkillExtractor.__init__` (invalid model name). For `TechExtractor.__init__`, both branches run (`entity_ruler` added on the `en_core_web_md` fixture; reused in `test_negation_without_parser_sentences_scans_whole_doc`, which pre-adds the ruler), but no test asserts which branch was taken or that a reused ruler is not duplicated.
5. **Sorting test name resolved.** `TestSkillExtractorSorting::test_sorted_case_insensitive` feeds mixed-case input (`design`, `BUILD`, `manage`) and asserts the exact result `["build tools", "design systems", "manage teams"]`. Its lowercase, sorted output matches its name.
6. **Silent fixture skips.** Fixture helpers return `""` on a missing file, and the tests then skip. A rename of a fixture file would convert those tests into skips, not failures.
7. **Wall-clock assertions relaxed, still present.** `TestSkillExtractorPerformance::test_extraction_completes_quickly` and `TestTechExtractorPerformance::test_extraction_completes_quickly` / `test_large_text_handling` assert `elapsed < 5.0`, with a comment calling it a "coarse sanity bound only, not a perf assertion". The 5.0 s bound is much less flaky-prone than the earlier 1.0 s and 0.1 s bounds, but it is still a wall-clock check.
8. **Weak asserts (resolved, with one pinned known bug).** `test_skills_extractor.py::test_lemmatization_base_form` asserts the exact list `["develop solutions", "lead teams"]`. `test_skills_extractor.py::test_hyphenated_noun` asserts the exact list `["design high"]`. This pins the known hyphen truncation (#508: "Hyphen is PUNCT, so the noun run stops at 'high'"), so the assert will need updating when #508 is fixed.
9. **Accuracy eval set is not asserted by pytest.** `tests/poc/fixtures/accuracy_eval_set.json` (12 snippets) is read only by `scripts/eval_poc_accuracy.py`. No test checks its expected labels, so a change in exact-match results is visible only when the script is run by hand (see `extraction_accuracy_report.md`).

## Verification

```bash
uv run pytest tests/poc/test_skills_extractor.py tests/poc/test_technologies_extractor.py -v
```

Expected: 121 items collected from the two files (42 skills + 79 technologies), from 87 test functions (40 + 47), all passing with `en_core_web_md` 3.8.0 installed.
