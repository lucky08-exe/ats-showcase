# POC Extractor Test Coverage Report

Issue #429. Covers the skills and technologies POC extractor tests.

## Overview

| File under test | Test file | Test functions |
|-----------------|-----------|----------------|
| `src/poc/skills/extract_skills_a.py` (`SkillExtractor`) | `tests/poc/test_skills_extractor.py` | 34 |
| `src/poc/technologies/extract_technologies_a.py` (`TechExtractor`) | `tests/poc/test_technologies_extractor.py` | 36 |
| **Total** | | **70** |

- Requires spaCy model `en_core_web_md` (`uv run python -m spacy download en_core_web_md`). Installed version 3.8.0 (spaCy 3.8.14) in the shared `.venv`; `spacy.load` verified.
- Runtime (recorded 2026-10-12, worktree `docs/issue-451-test-coverage-run`, `.venv/bin/python -m pytest tests/poc/ -v -p no:cacheprovider`): **959 passed, 37 skipped, 0 failed, 0 errors in 533.21 s (0:08:53)** for the whole `tests/poc/` directory. Exit 0. Python 3.12.12, pytest 9.1.1, spaCy 3.8.14, `en_core_web_md` 3.8.0.
- The two extractor files: `test_skills_extractor.py` 34 passed, 0 failed, 0 skipped (34/34); `test_technologies_extractor.py` 36 passed, 0 failed, 0 skipped (36/36). Total for the two files: 70 of 70 passed.
- The 37 skips are outside this report's scope: 34 in `tests/poc/test_extract_requirements_b.py` and 3 in `tests/poc/tweak/spacy_pipeline/test_pipeline_integration.py`. Their reasons were not investigated here.
- Fixture paths are relative (`tests/poc/fixtures/...`). Run from the repository root.

Note: this document replaces the missing `tests/poc/TEST_SUMMARY.md` referenced in issue #268 comments. No such file exists under `tests/poc/`.

## Per-file Breakdown

### `tests/poc/test_skills_extractor.py` (34)

| Group (class) | Count | What it covers |
|---------------|-------|----------------|
| `TestSkillExtractorBasics` | 9 | Initialization; simple and multiple skill extraction; return type is list; lowercase output; no duplicates; newline handling; empty text; text with no verbs |
| `TestSkillExtractorPatternMatching` | 8 | `SKILL_VERBS` presence; lemmatization to base form (weak assert, see gaps); past tense; continuous form; descriptive nouns; optional preposition/determiner (exact expected lists); compound noun phrases; longest-span filtering |
| `TestSkillExtractorFixtures` | 4 | Extraction from `raw_jd_what_you_ll_do.md` and `raw_jd_knowledge_skills_abilities.md`; combined extraction; accuracy check on one fixture |
| `TestSkillExtractorEdgeCases` | 9 | Punctuation; verb sequences; many modifiers; skill at sentence start/end; hyphenated noun (weak assert, see gaps); parenthetical context; special characters; very long phrase |
| `TestSkillExtractorSorting` | 2 | `test_results_are_sorted` (exact sorted list); `test_sorted_case_insensitive` (mixed-case input, exact lowercase sorted list) |
| `TestSkillExtractorPerformance` | 2 | Fixture extraction under a 5.0 s coarse bound; repeated extraction gives consistent results |

### `tests/poc/test_technologies_extractor.py` (36)

| Group (class) | Count | What it covers |
|---------------|-------|----------------|
| `TestTechExtractorBasics` | 9 | Initialization; `TECH_TERMS` populated; simple and multiple tech extraction; sorted list return; case-insensitive matching; no duplicates; empty text; text with no techs |
| `TestTechExtractorMultiWordPhrases` | 4 | Two-word phrases; `vision transformers`; case-insensitive phrase match; partial phrase not extracted |
| `TestTechExtractorFixtures` | 4 | Extraction from both fixture files; combined extraction; coverage check on knowledge/skills fixture |
| `TestTechExtractorEdgeCases` | 9 | Punctuation; term in parentheses; term in list; hyphenated phrase; terms with numbers; acronym expansion; vendor-specific terms; overlapping term names; `test_negation_not_handled_known_limitation` (not a negation test, see gaps) |
| `TestTechExtractorSorting` | 2 | Results sorted; alphabetical order |
| `TestTechExtractorWithPreprocessing` | 2 | Extraction after document processing; entity info preserved |
| `TestTechExtractorPerformance` | 3 | Timing on knowledge/skills fixture and on a 3x repeated fixture (both under a 5.0 s coarse bound); repeated extraction consistency |
| `TestTechExtractorPatternGeneration` | 3 | Inspects `TECH_TERMS` directly (non-empty set/list/tuple; single-word terms include a Python/Java entry; multi-word terms include one containing "vision"). Does not call `_generate_patterns()`. |

## Fixtures

| Fixture | File(s) | Scope | Behavior |
|---------|---------|-------|----------|
| `extractor` | `test_skills_extractor.py` | function (default) | Returns `SkillExtractor(model_name="en_core_web_md")` |
| `nlp` | `test_technologies_extractor.py` | function (default) | Returns `spacy.load("en_core_web_md")` |
| `extractor` | `test_technologies_extractor.py` | function (default) | Returns `TechExtractor(nlp)` |
| `fixture_what_you_ll_do` | both | function (default) | Reads `tests/poc/fixtures/raw_jd_what_you_ll_do.md`; returns `""` if missing |
| `fixture_knowledge_skills` | both | function (default) | Reads `tests/poc/fixtures/raw_jd_knowledge_skills_abilities.md`; returns `""` if missing |

Both fixture files exist (verified by glob). Most fixture-dependent tests guard with `if not fixture: pytest.skip(...)`, so a missing file produces a skip, not a failure. Exceptions with no guard: `test_fixture_combined_extraction` in both files, which run on empty strings if the files are missing.

## Coverage Gaps

Verified by reading the two test files and their imports (current state, as of this run).

1. **No production integration.** Both files import only `src/poc/skills/*` and `src/poc/technologies/*`. Nothing from `src/cli.py`, `src/storage/`, or `src/poc/tweak/` is exercised here.
2. **Negation is not tested.** `TestTechExtractorEdgeCases::test_negation_not_handled_known_limitation` (formerly listed as `test_negated_technology`) states in its docstring that negation handling is NOT implemented. It asserts only that `COBOL` is absent, which holds because `COBOL` is not in `TECH_TERMS`. Per its docstring, a negated known term such as "No experience with Python" would still be extracted; this was not run here. `test_skills_extractor.py` has no negation test (no test name or body references negation).
3. **No adversarial input tests.** No test name or docstring in either file targets prompt-injection-style text, confusable Unicode, or malformed input beyond the special-character and punctuation cases (`test_special_characters_in_text` in the skills file; `test_sentence_with_punctuation` in both).
4. **Constructor error paths untested.** No test covers the `OSError` branch in `SkillExtractor.__init__` (invalid model name), or the `"entity_ruler" in nlp.pipe_names` reuse branch in `TechExtractor.__init__`.
5. **Sorting test name resolved.** `TestSkillExtractorSorting::test_sorted_case_insensitive` now feeds mixed-case input (`design`, `BUILD`, `manage`) and asserts the exact result `["build tools", "design systems"]`. Its lowercase, sorted output matches its name. (The earlier report said its input was all lowercase; that is no longer true.)
6. **Silent fixture skips.** Fixture helpers return `""` on a missing file, and the tests then skip. A rename of a fixture file would convert those tests into skips, not failures.
7. **Wall-clock assertions relaxed, still present.** `TestSkillExtractorPerformance::test_extraction_completes_quickly` and `TestTechExtractorPerformance::test_extraction_completes_quickly` / `test_large_text_handling` now assert `elapsed < 5.0`, with a comment calling it a "coarse sanity bound only, not a perf assertion". The earlier 1.0 s and 0.1 s bounds no longer exist. The 5.0 s bound is much less flaky-prone than before, but it is still a wall-clock check.
8. **Weak asserts (resolved).** `test_skills_extractor.py::test_lemmatization_base_form` now asserts the exact list `["develop solutions", "lead teams"]`, so the lemma-like output is checked. `test_skills_extractor.py::test_hyphenated_noun` now asserts the exact list `["design high"]`. This pins the known hyphen truncation (#508, "Hyphen is PUNCT, so the noun run stops at 'high'"), so the assert will need updating when #508 is fixed. Both tests pass on current main (`201d156`): 2 passed.

## Verification

```bash
uv run pytest tests/poc/test_skills_extractor.py tests/poc/test_technologies_extractor.py -v
```

Expected: 70 tests collected from the two files (34 + 36), all passing with `en_core_web_md` 3.8.0 installed.
