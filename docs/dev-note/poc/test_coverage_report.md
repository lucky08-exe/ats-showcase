# POC Extractor Test Coverage Report

Issue #429. Covers the skills and technologies POC extractor tests.

## Overview

| File under test | Test file | Test functions |
|-----------------|-----------|----------------|
| `src/poc/skills/extract_skills_a.py` (`SkillExtractor`) | `tests/poc/test_skills_extractor.py` | 34 |
| `src/poc/technologies/extract_technologies_a.py` (`TechExtractor`) | `tests/poc/test_technologies_extractor.py` | 36 |
| **Total** | | **70** |

- Requires spaCy model `en_core_web_md` (`uv run python -m spacy download en_core_web_md`).
- Measured runtime: 70 passed in 98.21s (single local run, `uv run pytest ... -q`).
- Fixture paths are relative (`tests/poc/fixtures/...`). Run from the repository root.

Note: this document replaces the missing `tests/poc/TEST_SUMMARY.md` referenced in issue #268 comments. No such file exists under `tests/poc/`.

## Per-file Breakdown

### `tests/poc/test_skills_extractor.py` (34)

| Group (class) | Count | What it covers |
|---------------|-------|----------------|
| `TestSkillExtractorBasics` | 9 | Initialization; simple and multiple skill extraction; return type is list; lowercase output; no duplicates; newline handling; empty text; text with no verbs |
| `TestSkillExtractorPatternMatching` | 8 | `SKILL_VERBS` presence; lemmatization to base form; past tense; continuous form; descriptive nouns; optional preposition/determiner; compound noun phrases; longest-span filtering |
| `TestSkillExtractorFixtures` | 4 | Extraction from `raw_jd_what_you_ll_do.md` and `raw_jd_knowledge_skills_abilities.md`; combined extraction; accuracy check on one fixture |
| `TestSkillExtractorEdgeCases` | 9 | Punctuation; verb sequences; many modifiers; skill at sentence start/end; hyphenated noun; parenthetical context; special characters; very long phrase |
| `TestSkillExtractorSorting` | 2 | Output equals `sorted(output)`; second test (`test_sorted_case_insensitive`) uses all-lowercase input only |
| `TestSkillExtractorPerformance` | 2 | Fixture extraction under 1.0s wall clock; repeated extraction gives consistent results |

### `tests/poc/test_technologies_extractor.py` (36)

| Group (class) | Count | What it covers |
|---------------|-------|----------------|
| `TestTechExtractorBasics` | 9 | Initialization; `TECH_TERMS` populated; simple and multiple tech extraction; sorted list return; case-insensitive matching; no duplicates; empty text; text with no techs |
| `TestTechExtractorMultiWordPhrases` | 4 | Two-word phrases; `vision transformers`; case-insensitive phrase match; partial phrase not extracted |
| `TestTechExtractorFixtures` | 4 | Extraction from both fixture files; combined extraction; coverage check on knowledge/skills fixture |
| `TestTechExtractorEdgeCases` | 9 | Punctuation; term in parentheses; term in list; hyphenated phrase; terms with numbers; acronym expansion; vendor-specific terms; overlapping term names; negated technology (see gaps) |
| `TestTechExtractorSorting` | 2 | Results sorted; alphabetical order |
| `TestTechExtractorWithPreprocessing` | 2 | Extraction after document processing; entity info preserved |
| `TestTechExtractorPerformance` | 3 | Timing on knowledge/skills fixture; repeated extraction consistency; large text handling |
| `TestTechExtractorPatternGeneration` | 3 | `_generate_patterns()` output for all terms, single-word terms, and multi-word terms |

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

Verified by reading the two test files and their imports.

1. **No combined-pipeline test.** Neither file imports the other extractor or any code that builds a combined output. No test asserts the `{"skills": [...], "technologies": [...]}` shape.
2. **No production integration.** Both files import only `src/poc/skills/*` and `src/poc/technologies/*`. Nothing from `src/cli.py`, `src/storage/`, or `src/poc/tweak/` is exercised here.
3. **Negation is not tested.** `TestTechExtractorEdgeCases::test_negated_technology` (docstring: "Handles negation") asserts only that `COBOL` is absent, and its own comment says it is absent because it is not in `TECH_TERMS`. It does not test negation handling. `test_skills_extractor.py` has no negation test.
4. **No adversarial input tests.** No test name or docstring in either file targets prompt-injection-style text, confusable Unicode, or malformed input beyond the special-character and punctuation cases (`test_special_characters_in_text` in the skills file; `test_sentence_with_punctuation` in both).
5. **Constructor error paths untested.** No test covers the `OSError` branch in `SkillExtractor.__init__` (invalid model name), or the `"entity_ruler" in nlp.pipe_names` reuse branch in `TechExtractor.__init__`.
6. **Misnamed sorting test.** `TestSkillExtractorSorting::test_sorted_case_insensitive` does not test case-insensitive ordering. Its input is all lowercase.
7. **Silent fixture skips.** Fixture helpers return `""` on a missing file, and the tests then skip. A rename of a fixture file would convert those tests into skips, not failures.
8. **Wall-clock assertions.** `TestSkillExtractorPerformance::test_extraction_completes_quickly` asserts `elapsed < 1.0`; `TestTechExtractorPerformance::test_extraction_completes_quickly` asserts `elapsed < 0.1` (100 ms). Both can be flaky on slow hosts.

## Verification

```bash
uv run pytest tests/poc/test_skills_extractor.py tests/poc/test_technologies_extractor.py -v
```

Expected: 70 tests collected from the two files (34 + 36).
