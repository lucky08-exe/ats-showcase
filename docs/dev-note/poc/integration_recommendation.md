# POC Skills/Technologies Extractors: Integration Recommendation (Issue #452)

Gate 1 draft for human review. Parent: #268. Covers `src/poc/skills/extract_skills_a.py`
(`SkillExtractor`) and `src/poc/technologies/extract_technologies_a.py` (`TechExtractor`).

## Recommendation: No-Go (as-is). Conditional go for a narrow, additive slice.

Do not replace or merge the existing Phase 8 extraction pipeline
(`src/tokenization/preprocessor.py`, `src/preprocessing/*`) with the POC extractors.
Do not route `src/cli.py` preprocess through them in their current form. The measured
evidence (small sample) shows real gaps, the POC has no persistence or CLI integration
yet, and the production pipeline already does a superset of what the POC attempts, with
far more edge-case handling. If the team wants to pursue this, the smallest defensible
move is a narrow follow-on: fix 1-2 of the known weaknesses, add proper fixtures/tests,
and re-run the benchmark/accuracy harness before any CLI wiring is discussed again. That
is a "maybe later", not a "yes now".

## Evidence (as recorded; small sample, do not over-read)

Source: `docs/dev-note/poc/extraction_accuracy_report.md` (8 hand-labeled snippets,
2026-10-12 run).

- `SkillExtractor` micro recall 0.44 (4/9), precision 0.80 (4/5). Exact match 4/8 snippets.
- `TechExtractor` micro recall 0.73 (11/15), precision 0.85 (11/13). Exact match 3/8 snippets.
- n = 8 is explicitly called out in the source report as "a small labeled sample, not a
  benchmark." Nothing here should be read as a general accuracy figure.

Known weaknesses from that run (all `[run]`-tagged, i.e., reproduced, not just
theorized from reading the code):
- **Sentence-initial verb tagging**: `en_core_web_md` tags sentence-initial imperatives
  (`Mentor`, `Research`) as `NOUN`, not `VERB`, so `SkillExtractor`'s `POS == VERB`
  match requirement misses them even though the lemma is in `SKILL_VERBS` (s3, s8).
- **Truncation at conjunction**: the skill noun-group pattern stops at `and`, so
  "lead data science and platform teams" only yields "lead data science" (s6).
- **Hyphenated `TECH_TERMS`**: `anchor-free detectors` is in `TECH_TERMS` but spaCy
  tokenizes `anchor-free` into multiple tokens while the generated pattern emits a
  single `LOWER` token, so it never matches (s5). Same risk flagged (not reproduced)
  for `real-time inference`.
- **Negation not handled**: "No experience with Kubernetes required" still yields
  `kubernetes` as a tech false positive (s4).
- **`go` false positive**: `TECH_TERMS` includes `go`, which matches the common verb
  "Go" in running text (s7). `spring`, `vue` are flagged as the same risk class but
  not exercised by the snippet set.
- Vocabulary gaps: `kafka`, `terraform`, `lightning`, `pytorch lightning` are not in
  `TECH_TERMS` (s2, s8); `manage`, `ship`, `evaluate` are not in `SKILL_VERBS` (s2, s8).

Performance: `docs/dev-note/poc/performance_benchmark_plan.md` (single machine,
2026-10-12, Run 1, 5 repeats).

- Model load cold: 1335.411 ms — under the <2000 ms target.
- Medium input (1137 tokens, target ~1000): `SkillExtractor.extract` median
  174.633 ms; tech path (`nlp(text)` parse 166.061 ms + `extract(doc)` 0.127 ms)
  166.188 ms. **Both miss the <100 ms target** (manual comparison in the source doc;
  the benchmark script itself computes no pass/fail).
- Large input (4927 tokens): skill 728.291 ms, tech parse 733.840 ms + 0.540 ms extract.
- The source doc's own caveat: "spaCy parse dominates" — `SkillExtractor.extract` and
  `TechExtractor`'s `nlp(text)` parse are each a full spaCy pipeline run; the
  extraction step itself (`Matcher`/`entity_ruler` lookup) is <1 ms in all three sizes.
  So the latency miss is a parse-cost problem, not an extractor-logic problem — and
  that matters for the integration design below, because the production pipeline
  already pays exactly one such parse per job.
- Peak memory via `tracemalloc` only (explicitly a lower bound; native/C allocations
  undercounted): medium ~20.4 MB, large ~88.1 MB, for skill or tech path alike.
- Single-machine numbers; not meant to generalize across hardware (stated in the
  source doc).

Unmeasured / not claimed here: no comparison run of the POC extractors against the
production `Preprocessor.extract_entities` pipeline on the same inputs; no measurement
of combined (skill+tech+Phase-8) latency in one pass; no measurement on realistic full
job postings (only the two `tests/poc/fixtures/raw_jd_*.md` repeated to hit size
targets, per the benchmark plan's own caveat that "small size is not ~100 tokens").

## Overlap with existing Phase 8 pipeline (why "no-go as a replacement")

`src/tokenization/preprocessor.py` (`Preprocessor`) already does, in production, a
superset of what the two POC modules attempt, with substantially more edge-case
handling built up over multiple issues (#190-194, #211, #230, #241, Phase 1-12 markers
in the module's own docstrings):

- Technology extraction: NER (`PRODUCT`/`ORG` labels) + token-level keyword/lemma
  matching against `get_all_keywords()` (86+ keywords, `src/tokenization/keywords.py`),
  plus section-aware routing (`_extract_entities_by_section`) for markdown jobs. Compare
  to `TechExtractor`'s single mechanism: an `entity_ruler` over a flat `TECH_TERMS` list
  with the known common-word (`go`) and hyphenation weaknesses above.
- Skill extraction: POS/dependency-based noun-compound and adjective extraction, soft
  skills vocabulary (`src/tokenization/soft_skills.py`), technical-compound
  reclassification (`src/tokenization/technical_compounds.py`), and roughly a dozen
  `_should_skip_*`/`_is_*` filters removing numbers, possessives, company names, job
  titles, policy/benefit boilerplate, generic words, and HTML-artifact fragments.
  `SkillExtractor` has none of this: a single `Matcher` pattern
  (`VERB(lemma in SKILL_VERBS) + ADP/DET/PART? + (ADJ|NOUN|PROPN)+`), no filtering, no
  section awareness, and the sentence-initial-verb and conjunction-truncation gaps
  above.
- Section skip-list: `Preprocessor.SKIP_SECTIONS` (benefits, legal, hiring-process,
  etc.) is the single source of truth per the module's own comment; the POC extractors
  have no section concept at all, so they would need either the same skip-list wired
  in or would reintroduce the boilerplate contamination Phase 8 was built to remove.
- Company-name filtering (`is_company_keyword`, Issue #194 Phase 7) has no analog in
  the POC. Given `TechExtractor`'s `go`-style false-positive pattern, running it
  unfiltered on real JD text risks reintroducing noise the production pipeline already
  suppresses.
- Separately, Phase 8a/8b (`src/preprocessing/requirement_filter.py`,
  `src/preprocessing/span_categorizer.py`) extract *requirements* (not skills/tech) via
  trigger patterns and expand them to boundary-aware spans for chunk preservation. This
  is a different entity class from what the POC extractors target, so it is not
  directly duplicative, but any merge plan needs to make clear these are three separate
  entity concerns (skills, technologies, requirements) that should not be collapsed into
  one extractor without a design pass.

Net: merging the POC extractors as a replacement would be a regression against the
current filtering quality, on a smaller measured sample, with a `<2x` to `<5x` latency
cost over target. The more defensible frame, if there is interest in the POC's approach
at all, is "does `TechExtractor`'s `entity_ruler` term-list approach add recall that
`Preprocessor`'s keyword/lemma matching misses on *specific* in-vocabulary terms?" — that
is a much narrower question than "merge the POC".

## Integration points (for if/when a narrower slice is pursued)

Even for a narrow slice, these are the touch points, named precisely so a future
Builder knows what NOT to improvise:

1. **`src/cli.py` preprocess step** — `_build_preprocess_clean_text` (around line 304)
   builds `clean_text` via `clean_html()`; `_preprocess_job_for_phase` (around line 329)
   runs `preprocessor.nlp(clean_text)` once to get `doc`, then calls `chunker.chunk(...,
   doc=doc)` and reads `doc._.requirements` for `trigger_requirements_json`. Any POC
   extractor call would need to reuse this *same* `doc` (the extractors can share an
   `nlp` instance via their constructors — `SkillExtractor(nlp=...)`,
   `TechExtractor(nlp)` — but note `TechExtractor.__init__` mutates the shared `nlp` by
   adding an `entity_ruler` pipe, so it cannot be constructed per-job; it must be set up
   once, the same way `Preprocessor._load_model` adds `requirement_filter` and
   `span_categorizer` once). Running a second, independent `spacy.load()` /
   `nlp(text)` call per job, as the POC scripts do standalone, would double the parse
   cost identified as the latency bottleneck in the benchmark — a second full parse
   per job, not merely a second extractor call.
2. **Storage** — there is currently no column for POC-style skills/technologies lists.
   `src/storage/db.py`'s `jobs`/`preprocessed_jobs` tables have a `requirements TEXT`
   column (free-text, pre-dates Phase 8); `src/storage/schema.py`'s `job_reviews` table
   (the one actually used by `JobStore`, per `.claude/rules/storage.md`) has no
   `requirements` or `skills`/`technologies` column at all — Phase 8a's trigger
   requirements live in the `preprocessed_jobs.json` file's `trigger_requirements` key
   (see `_preprocess_job_for_phase` above), not in `job_reviews`. Adding POC output would
   need either (a) a new nullable column on `job_reviews` following the
   `preprocessing_version`-style additive-migration pattern already in place, or (b) a
   new sibling table keyed on `job_id`, mirroring `quality_tracking`/`cost_tracking`.
   `JobStore` (`src/storage/job_store.py`) would need new read/write methods; no
   existing method handles this shape. This is schema/CLI-surface territory, so per
   AGENTS.md it needs Gate 1 (Architect plan + tasks.md) before any Builder touches
   `src/storage/` or `src/cli.py`.
3. **`requirement_spans` (frozen shape)** — `requirement_spans` is a `Doc._.`
   extension (`Doc.set_extension("requirement_spans", ...)` in
   `src/preprocessing/span_categorizer.py`), populated by the `span_categorizer` pipe and
   consumed only by `src/tokenization/chunker.py` (`SemanticChunker`) to avoid splitting
   a span across chunk boundaries. **It is never persisted** — not to the preprocessed
   JSON, not to any DB column (confirmed: `_preprocess_job_for_phase` reads
   `doc._.requirements`, never `doc._.requirement_spans`, into the output dict). Per
   CLAUDE.md's preprocess rules, "`requirement_spans` dict shape stays frozen" across
   categorizer strategies (`nlp`/`custom`, Issue #278). The POC extractors do not
   produce or consume this shape at all — there is no overlap risk here, but it does
   mean POC output (skills/tech spans) and Phase 8b spans are two independent
   span-tracking mechanisms today. If a future design wants one unified "entity spans in
   this doc" representation, that is a real design question, not a one-line fix, and
   should not be smuggled into a narrow accuracy-fix issue.

## Risks

- **Quality regression risk**: on the measured sample, skill recall (0.44) is
  materially below what a user of the existing, heavily-filtered Phase 8 skills
  extraction would expect. Shipping this to the `assess` phase's LLM input without
  matching the existing filter depth risks both missed skills and reintroduced noise
  (company names, policy boilerplate, the `go`/common-word class of false positive).
- **Latency risk**: medium-doc latency misses the <100 ms target by ~65-75 ms on this
  one run, on a non-idle single machine (load average 0.69-2.02 during the two runs,
  per the benchmark doc's own note — not a clean idle baseline). If a second, separate
  `nlp()` parse is added on top of the existing `Preprocessor.nlp(clean_text)` parse in
  `_preprocess_job_for_phase`, the user-visible preprocess-phase cost could roughly
  double per job rather than add the ~175 ms once.
- **Sample-size risk**: both the accuracy (n=8) and performance (single machine, 2 runs)
  numbers are explicitly flagged as small/limited in their source docs. Any go/no-go
  based on these numbers alone is provisional; the source reports' own framing should be
  preserved when this doc is cited elsewhere — do not round these into general claims.
  Precision (0.80 skills / 0.85 tech) looks more usable than recall in isolation, but
  with n=5 and n=13 extracted items respectively, a couple of snippet-count changes would
  move these substantially.
- **Memory**: `tracemalloc`-only peak figures (medium ~20 MB, large ~88 MB) are stated
  as undercounting native/C allocations; real peak (including spaCy's C-level vector
  data) is unmeasured and could be materially higher. Not evaluated against any existing
  memory budget for the preprocess phase (no such budget found in CLAUDE.md/rules).
- **Duplication risk**: without an explicit decision to either replace specific pieces
  of `Preprocessor` or scope the POC to genuinely novel vocabulary, merging both systems
  side by side means two independently-maintained skill/tech taxonomies
  (`SKILL_VERBS`/`TECH_TERMS` vs. `keywords.py`/`soft_skills.py`/`technical_compounds.py`)
  drifting out of sync over time.
- **No test coverage for the integration surface**: `tests/poc/test_skills_extractor.py`
  and `tests/poc/test_technologies_extractor.py` exist (not read in detail for this doc)
  but there is, as far as this review found, no test exercising the extractors against
  `src/cli.py`'s preprocess flow, storage, or the `job_reviews` schema, because that
  wiring does not exist yet.

## Step plan (if a narrow slice is approved)

Each step sized to fit a single-issue PR; Architect still owns Gate 1 for 2 and 4 per
AGENTS.md (schema/CLI surface changes).

1. **(S) Fix `go`/common-word false positive** — add a minimal denylist or
   require a capitalization/context check for single-token `TECH_TERMS` entries known to
   collide with common English words (`go`, `spring`, `vue`); add regression fixtures
   for all three. Scope: `src/poc/technologies/` only, plus tests. No CLI/storage
   touch.
2. **(S) Fix hyphenated `TECH_TERMS` pattern generation** — update
   `_generate_patterns()` to emit a token sequence (or a single-token match on the
   hyphen-joined form, whichever spaCy's tokenizer actually produces for the existing
   hyphenated entries) so `anchor-free detectors` / `real-time inference` match; add
   regression fixtures for both. Scope: `src/poc/technologies/` only, plus tests.
3. **(S) Re-run the accuracy and benchmark harnesses** after 1-2, on a larger labeled
   set (the 8-snippet set plus, ideally, real JD text rather than only the two POC
   fixtures used for size scaling) — purely a measurement step, no code change beyond
   extending fixtures. Needed before any further step, since the current n=8/n=2-fixture
   numbers are too small to justify more investment.
4. **(M, Architect-owned Gate 1 required)** Only if 1-3 show the POC extractors now add
   measurable recall/precision value over `Preprocessor`'s existing skill/tech
   extraction on the same inputs: draft a tasks.md proposing *where* the POC logic would
   plug in (e.g., as an additional signal merged into `Preprocessor.extract_entities`'s
   output, not a parallel pipeline) and what schema change (if any) is needed. This is
   the point at which the `job_reviews` schema / `JobStore` question from Integration
   point 2 gets decided, not before.
5. **(M) Address sentence-initial-verb and conjunction-truncation skill gaps** — these
   require a `Matcher` pattern or POS-tag-correction fix; sized separately from 1-2
   because they affect the skills path (lower measured precision/recall than tech) and
   are more involved (the sentence-initial NOUN mistagging is a spaCy POS-tagger
   limitation on this model, not simply a pattern bug, so the fix approach itself needs
   a short design note). Do this only after step 4's go decision, since it is wasted
   effort if the extractor is not going to be integrated.
6. **(S) Negation handling** — lowest priority of the known weaknesses; affects tech
   precision only (one snippet in the eval set) and typically needs a small window-based
   check (e.g., inspect preceding tokens for negation cues) rather than a structural
   change. Candidate for a "good first issue" once/if step 4 is a go.

Steps 1-3 are useful regardless of the go/no-go decision on full integration (they
improve the POC's own correctness and give a less small-sample-caveated basis for a
later decision). Steps 4-6 should not start before a human/Architect reviews the
re-run numbers from step 3.

## Open questions for the human

1. Is there a product/business need driving this (e.g., CV-matching quality complaints
   tied specifically to missed skills/tech), or is this exploratory POC cleanup? That
   changes whether steps 4-6 are worth prioritizing over other queued issues.
2. If integration is eventually approved, should the goal be **augmenting**
   `Preprocessor.extract_entities` (merge POC signal into existing output) or
   **replacing** parts of it? This doc assumes augmentation is the only defensible
   option given the overlap/regression risk above, but that is a product/architecture
   call, not something this draft should decide.
3. Who owns reconciling `TECH_TERMS`/`SKILL_VERBS` vocabulary against
   `keywords.py`/`soft_skills.py`/`technical_compounds.py` if both systems end up
   coexisting even temporarily? Risk of drift was flagged above but not resolved.
4. Is a larger (>8 snippet) hand-labeled accuracy set already planned elsewhere (e.g.,
   as part of issue #268's broader scope), or does step 3 above need to build one from
   scratch?
5. Benchmark Run 1/Run 2 were on one non-idle machine with no idle baseline captured.
   Is a clean/idle re-run worth doing before any latency-sensitive decision, given the
   medium-doc numbers are ~65-75% over target?
6. The `tracemalloc`-based memory figures are a known lower bound. Does the team have
   an existing memory ceiling for the preprocess phase (e.g., for CI runners or
   production hosts) that these numbers should be checked against, or is memory not a
   current concern?

## Sources read for this recommendation

- `docs/dev-note/poc/extraction_accuracy_report.md`
- `docs/dev-note/poc/performance_benchmark_plan.md`
- `src/poc/skills/extract_skills_a.py`, `src/poc/skills/patterns.py` (not read in
  detail — `SKILL_VERBS` content not reproduced here)
- `src/poc/technologies/extract_technologies_a.py`, `src/poc/technologies/patterns.py`
  (not read in detail — `TECH_TERMS` content not reproduced here)
- `tests/poc/` directory listing (full extractor test files identified:
  `test_skills_extractor.py`, `test_technologies_extractor.py`; not read line-by-line)
- `src/cli.py` (`_build_preprocess_clean_text`, `_preprocess_job_for_phase`,
  `_preprocess_jobs_file`, `_run_phase_preprocess`)
- `src/storage/db.py`, `src/storage/schema.py` (table definitions)
- `src/tokenization/preprocessor.py` (`Preprocessor`, full file)
- `src/tokenization/chunker.py` (`requirement_spans` consumption, partial — grep-located
  lines, not full read)
- `src/preprocessing/span_types.py` (full file), `src/preprocessing/span_categorizer.py`
  (partial read, extension registration and boundary-rule helpers)
- `AGENTS.md`, `CLAUDE.md`, `.claude/rules/preprocess.md`, `.claude/rules/storage.md`,
  `.claude/rules/cli.md` (process/role constraints, `requirement_spans` frozen-shape
  note)

Note: `code-review-graph` (MCP) was unavailable in this worktree (no
`graphify-out/graph.json` here, no `.code-review-graph/graph.db` queried) — this
review fell back to direct file reads/grep per the tool's documented no-hard-dependency
fallback.
