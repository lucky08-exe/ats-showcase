# Hyphen-Compound Suffix Decision (Issue #553)

## Scope

- Records the decision on how broad the hyphen-compound rule for ambiguous tech terms should be.
- Follow-up to #513 (rule introduced) and PR #549 (suffix allow-list added). Tracked under #268.
- Advisory. No real job-description text was available when this was written.

## The rule

- `AMBIGUOUS_TERMS` in `src/poc/technologies/extract_technologies_a.py`: `go`, `spring`, `vue`, `lightning`.
- If an ambiguous term is followed by `-`, the hyphen is read as an English compound (e.g. `Go-live`, `Go-to-market`) unless the next word is in `HYPHEN_TECH_SUFFIXES`.
- `HYPHEN_TECH_SUFFIXES` = `based`, `native`, `lang`, `like`. Lives in `src/poc/technologies/patterns.py` (moved there by #553, behavior unchanged).
- Enforced in `_is_tech_context`. A hyphen after an ambiguous term with a non-suffix next word returns "not tech" immediately. It does not fall through to the cue or adjacency checks.

## Known trade-off

- Rejecting `Go-live` and `Go-to-market` is intentional. These are common non-tech compounds.
- The cost: a real tech hyphen compound whose second word is not in the list loses its evidence. Example shape: `<ambiguous>-<unlisted word>` used as a technology. Such cases are currently unseen, so their frequency is unknown.

## Decision

- The suffix list is **not widened and not narrowed**. There is no evidence either way.
- The maintainer confirmed on 2026-10-14 that no real JD examples exist yet. The decision is therefore **deferred**, not closed.

## Alternatives considered and deferred

- **Stoplist of non-tech compound heads** (e.g. `market`, `live`). Deferred. It needs an enumeration of every plausible non-tech head, which is more data-hungry than the current allow-list. Adopting it now would be speculative.
- **Keying on the following word's POS or dependency role.** Deferred. It needs parser-dependent tuning and labeled data to validate. Not justified without real examples.

## Test coverage status

- `TestTechExtractorHyphenSuffix553` in `tests/poc/test_technologies_extractor.py` covers the mechanism.
- All sentences in that class are **synthetic mechanics tests**; the cases added with the #553 data-driven refactor carry an inline `# SYNTHETIC:` comment. They prove the code follows the rule. They are not real-world coverage and say nothing about precision or recall on real postings.

## Extension point (when real examples exist)

1. Collect real sentences containing `<ambiguous>-<word>` with a technology meaning. Keep the raw text in gitignored `data/`. Never commit it.
2. Record only counts and provenance (e.g. `"maintainer export, 2026-10, public careers page"`) in docs or commit messages.
3. If a word qualifies, add it to `HYPHEN_TECH_SUFFIXES` in `src/poc/technologies/patterns.py`.
4. Add a parametrized entry to `TestTechExtractorHyphenSuffix553`. Any synthetic fixture must start its `source_note` or inline comment with `SYNTHETIC:`, per the #500 convention in `docs/dev-note/poc/labeled_jd_eval.md`.
5. Check for non-tech compounds that the wider list would now accept. Add a rejection test for each.

Do not add a suffix without real evidence. Do not present synthetic tests as validation.
