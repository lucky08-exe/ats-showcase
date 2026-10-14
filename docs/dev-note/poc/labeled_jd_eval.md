# Labeled-JD Eval Set (Issue #500)

Optional labeled job-description set for `scripts/eval_poc_accuracy.py`. It sits alongside the 27-snippet set (`tests/poc/fixtures/accuracy_eval_set.json`, see [extraction_accuracy_report.md](extraction_accuracy_report.md)) and reports precision and recall for skills and technologies against real, maintainer-labeled text.

Parent: #268. Corpus mode (`--corpus`, `--dump`, `--compare`, #552) is out of scope; it may build on this loader.

## Where the file goes

| Location | Use |
|----------|-----|
| `data/poc/labeled_jds.json` | Default. Loaded automatically when present. `data/` is gitignored, so real third-party text stays out of git. |
| any path via `--labeled-jds PATH` | Explicit. A missing path is an error (exit 2). |

When no labeled file is found, the script behaves exactly as before: the output is unchanged.

## Format

A JSON list of objects. Every object has exactly these five keys:

| Key | Type | Meaning |
|-----|------|---------|
| `id` | non-empty string | Unique within the file. Used as the row label. |
| `source_note` | non-empty string | Where the text came from, e.g. `"maintainer export, 2026-10, public careers page"`. For synthetic entries, start with `SYNTHETIC:`. |
| `text` | non-empty string | The JD text exactly as the extractors will see it. |
| `expected_skills` | list of non-empty strings | Ideal skill spans (see labeling rules). |
| `expected_technologies` | list of non-empty strings | Ideal technology terms, including terms outside `TECH_TERMS`. |

Validation (`load_labeled_jds`) rejects: a top level that is not a list, a non-object entry, missing or extra keys, empty or wrongly typed fields, and duplicate `id`s. An empty list is valid.

Template: `tests/poc/fixtures/synthetic_labeled_jd_TEMPLATE.json` (2 entries, both marked `SYNTHETIC:` and `SYNTHETIC EXAMPLE.` in the text). The name ends in `TEMPLATE` so it is not mistaken for data. Its numbers are a format demo, not a benchmark.

```json
[
  {
    "id": "synthetic-01",
    "source_note": "SYNTHETIC: invented sentence for format demonstration",
    "text": "SYNTHETIC EXAMPLE. Build internal reporting dashboards in Python and PostgreSQL.",
    "expected_skills": ["build internal reporting dashboards"],
    "expected_technologies": ["postgresql", "python"]
  }
]
```

## Labeling rules

Follow the same rules as the snippet set (see "Ground truth labeling rules" in `extraction_accuracy_report.md`):

- Lowercase, sorted, deduplicated. The loader and scorer normalize case and whitespace, but write labels in lowercase anyway.
- Skill labels are surface spans as written, including a determiner inside the span. Label the full phrase an ideal extractor would take.
- Technology labels are the terms a perfect extractor should return, whether or not they are in `TECH_TERMS`.
- Negated requirements ("No experience with X required") are not expected positives. Leave X out of both lists unless the JD also asks for it positively.

## Adding an entry

1. Copy the text from the source into `text`. Do not paraphrase; the extractors run on the exact string.
2. Fill `source_note` with where and when it came from. Do not include personal data or the company's private details.
3. Label `expected_skills` and `expected_technologies` by hand, following the rules above. Do not copy extractor output into the labels; that would measure nothing.
4. Give it a new unique `id`.
5. Validate and score:

```bash
uv run python scripts/eval_poc_accuracy.py                                   # uses data/poc/labeled_jds.json if present
uv run python scripts/eval_poc_accuracy.py --labeled-jds path/to/file.json   # explicit file
```

The labeled section prints `LABELED JD SET <path> entries=N`, a per-entry table (skills and tech recall and precision, `N/A` when a denominator is 0), and micro totals. Recall is hits / expected, precision is hits / extracted.

## Rules for committing

- Do not commit real third-party JD text unless the maintainer has explicitly approved it. Keep real files under `data/poc/` (gitignored).
- Do not invent realistic-looking postings. Synthetic entries must say so in `source_note` and in the text.
- Changes to the tracked template or this doc go through a normal PR.

## Tests

`tests/poc/test_labeled_jd_eval.py` covers the loader's validation, the template's synthetic marking, the flag and default-path behaviour, and the metric helpers. It does not load the spaCy model.
