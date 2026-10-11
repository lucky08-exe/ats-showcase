# Pattern Gap Analysis (Issue #430)

## Scope & disclaimer

- Advisory only. This document is NOT a patch to `src/poc/skills/patterns.py` or `src/poc/technologies/patterns.py`. No source file was edited.
- Candidates below were checked by reading the current lists. No runtime extraction was run, so no hit rates or coverage numbers are given.
- Any term adoption is a human decision. Machine-readable candidates live in `docs/dev-note/poc/pattern_candidates.json`.

## Current inventory

Counted by reading the files on 2026-10-11.

| File | Structure | Count |
|------|-----------|-------|
| `src/poc/skills/patterns.py` | `SKILL_VERBS` list | 24 |
| `src/poc/technologies/patterns.py` | `TECH_TERMS` set, `# ---` category comments | 42 |

Note: the text of issue #430 (and #268) cites 27 skill verbs and 51 tech terms. The files contain 24 and 42, verified by importing both lists. The issue figures are stale.

Tech term breakdown by existing category comment:

| Category comment | Count |
|------------------|-------|
| Carbon Robotics / AI / Robotics Specific | 13 |
| Languages | 8 |
| Frameworks & Libraries | 8 |
| Cloud & Infrastructure | 5 |
| Databases & Search | 4 |
| Tools & Collaboration | 4 |
| **Total** | **42** |

## Skill verb candidates

Each candidate was checked against `SKILL_VERBS`. None is present.

- `automate`: common JD verb for scripting and pipeline work.
- `collaborate`: frequent in soft-skill bullets; complements `partner` and `communicate`.
- `migrate`: common in platform and cloud job descriptions.
- `analyze`: common in data and research roles.
- `debug`: common in engineering bullets; the lemma is `debug`.
- `maintain`: common in ownership bullets; complements `own`.
- `refactor`: common in code-quality bullets.
- `monitor`: common in ops and reliability bullets.
- `coordinate`: common in cross-team and project bullets.
- `troubleshoot`: common in support and infrastructure bullets; lemma is `troubleshoot`.

## Tech term candidates

Each candidate was checked against `TECH_TERMS`. None is present. Grouped by existing category comment.

**Carbon Robotics / AI / Robotics Specific**
- `opencv`: computer vision library; sits next to `computer vision`.
- `ros`: robotics middleware; relevant to the robotics group.
- `lidar`: sensor type; sits next to `sensor fusion`.
- `slam`: localization and mapping; robotics domain term.
- `deep learning`: multi-word; ML umbrella term.

**Languages**
- `sql`: near-universal in data and backend JDs.
- `kotlin`: common JVM and mobile language.
- `scala`: common JVM and data-engineering language.
- `ruby`: common web language.
- `php`: common web language.

**Frameworks & Libraries**
- `fastapi`: common Python API framework; complements `flask` and `django`.
- `pandas`: common data library.
- `numpy`: common numeric library.
- `node.js`: common JavaScript runtime. Contains a dot; see maintainability notes.
- `graphql`: common API query language.

**Cloud & Infrastructure**
- `terraform`: common infrastructure-as-code tool.
- `ansible`: common configuration-management tool.
- `helm`: common Kubernetes package manager.
- `prometheus`: common metrics and monitoring tool.
- `kafka`: common event-streaming platform.

**Databases & Search**
- `mysql`: relational database; complements `postgresql`.
- `sqlite`: embedded database; relevant to this project's own stack.
- `cassandra`: wide-column database.
- `dynamodb`: AWS key-value database.

**Tools & Collaboration**
- `jenkins`: CI server.
- `bitbucket`: git hosting; sits next to `github` and `gitlab`.
- `confluence`: wiki tool; sits next to `jira`.
- `github actions`: multi-word; sits next to `github`.

## Maintainability notes

- **Flat lists, no metadata.** `SKILL_VERBS` is a list and `TECH_TERMS` is a set. Neither records category, source, version, or date added. Category is only a comment, so a comment drift or a misplaced term is not detected.
- **No alias handling.** Aliases must be listed manually as separate entries. Existing examples: `go` and `golang`; `LPM` and `Large Plant Model`. Missing examples a reviewer may want to decide on: `k8s` for `kubernetes`, `postgres` for `postgresql`, `js` for `javascript`, `ts` for `typescript`, `scikit-learn` for `sklearn`, `tf` for `tensorflow`. None are added here.
- **Case handling differs between the two extractors.**
  - Skills: `SKILL_VERBS` entries are lowercase lemmas matched through spaCy `LEMMA`. The extractor assumes lowercase lemmas. Entries are not lowercased in code.
  - Technologies: `_generate_patterns` lowercases each term and matches on `LOWER`. Case in `TECH_TERMS` is cosmetic, but the set mixes forms (`PyTorch`, `python`), so duplicates in different case would not be caught by the set.
- **Multi-word terms.** Technology multi-word terms are split on whitespace and emitted as a sequence of `LOWER` token patterns. Hyphenated terms such as `anchor-free detectors` and `real-time inference` are split only on spaces, so `anchor-free` and `real-time` remain single entries that spaCy may tokenize into several tokens. Whether these match is unverified because code was not run. Dotted and symbol terms such as `c#`, `c++`, and `node.js` depend on spaCy tokenization and are also unverified.
- **Overlaps and ambiguity found by reading.**
  - `go` is a common English word and may produce noise in tech matches.
  - `spring` is a framework name and a common English word.
  - `vue` (tech) is a plain word in French. In skill verbs, `scope`, `own`, `lead`, `drive`, `scale`, `model` and `partner` are also common nouns. Skill extraction requires `POS == VERB`, which reduces noise but depends on the tagger.
  - `go` and `golang` are aliases; `LPM` and `Large Plant Model` are aliases. Both are handled by listing them separately.
  - `computer vision` and `vision transformers` share the token `vision` but are distinct entries. No true duplicate was found in the `TECH_TERMS` literal. A set literal would silently absorb an exact duplicate, so a duplicate check is not available from the file alone.
- **No versioning.** Changes to either list are not recorded anywhere in the file, and downstream outputs are not tied to a list version.

## Suggested next step

Human decision. Options:
1. Review the candidates in `pattern_candidates.json` and select any to adopt. Adopt in a separate, reviewed change, not as part of this doc.
2. Decide on alias policy (manual entries vs. an alias map) before adding terms like `k8s` or `postgres`.
3. Decide whether to run extraction on sample JDs to measure the multi-word, hyphen, and dotted-term behaviour noted above. This was not done here.
