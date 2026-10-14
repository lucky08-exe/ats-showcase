"""Run POC skill/tech extractors over the labeled eval set and print metrics.

Usage (from repo root, needs spaCy model en_core_web_md):
    uv run python scripts/eval_poc_accuracy.py
    uv run python scripts/eval_poc_accuracy.py --labeled-jds path/to/labeled_jds.json

Prints per-snippet hit rate / precision / exact match and micro totals.
Hit rate = |E & X| / |E|; precision = |E & X| / |X|; N/A when denominator is 0.

If a labeled-JD file is present (default data/poc/labeled_jds.json, or the path
given with --labeled-jds), its entries are scored the same way and printed after
the snippet output as recall / precision per entry and micro totals. When no
labeled file is present the output is unchanged.
Format and labeling guide: docs/dev-note/poc/labeled_jd_eval.md.
See docs/dev-note/poc/extraction_accuracy_report.md (Issue #431, #449, #500).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import spacy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.poc.skills.extract_skills_a import SkillExtractor  # noqa: E402
from src.poc.technologies.extract_technologies_a import TechExtractor  # noqa: E402

EVAL_SET = ROOT / "tests" / "poc" / "fixtures" / "accuracy_eval_set.json"
# data/ is gitignored, so a real (third-party) labeled set placed here is never committed.
DEFAULT_LABELED_JDS = ROOT / "data" / "poc" / "labeled_jds.json"
LABELED_KEYS = frozenset({"id", "source_note", "text", "expected_skills", "expected_technologies"})


class LabeledJDError(ValueError):
    """Raised when a labeled-JD file does not match the documented format."""


def _validate_entry(entry: Any, where: str, seen: set[str]) -> None:
    if not isinstance(entry, dict):
        raise LabeledJDError(f"{where}: entry must be a JSON object")
    keys = set(entry)
    if keys != LABELED_KEYS:
        missing = sorted(LABELED_KEYS - keys)
        extra = sorted(keys - LABELED_KEYS)
        raise LabeledJDError(f"{where}: missing keys {missing}, unexpected keys {extra}")
    for key in ("id", "source_note", "text"):
        if not isinstance(entry[key], str) or not entry[key].strip():
            raise LabeledJDError(f"{where}: '{key}' must be a non-empty string")
    for key in ("expected_skills", "expected_technologies"):
        values = entry[key]
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            raise LabeledJDError(f"{where}: '{key}' must be a list of non-empty strings")
    if entry["id"] in seen:
        raise LabeledJDError(f"{where}: duplicate id {entry['id']!r}")
    seen.add(entry["id"])


def load_labeled_jds(path: Path) -> list[dict[str, Any]]:
    """Load and validate a labeled-JD JSON file (see docs/dev-note/poc/labeled_jd_eval.md)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LabeledJDError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise LabeledJDError(f"{path}: top level must be a JSON list")
    seen: set[str] = set()
    for i, entry in enumerate(data):
        _validate_entry(entry, f"{path}[{i}]", seen)
    return data


def norm(xs: list[str]) -> list[str]:
    return sorted({str(x).strip().lower() for x in xs})


def rate(num: int, den: int) -> str:
    return "N/A" if den == 0 else f"{num}/{den}={num / den:.2f}"


def print_labeled(
    path: Path, entries: list[dict[str, Any]], skill_extractor: SkillExtractor, tech_extractor: TechExtractor, nlp: Any
) -> None:
    """Score labeled entries (recall = hit rate, precision) and print a per-entry table plus micro totals."""
    print(f"\nLABELED JD SET {path} entries={len(entries)}")
    print("| id | skills recall | skills precision | tech recall | tech precision |")
    tot = {"skills": [0, 0, 0], "tech": [0, 0, 0]}  # hits, expected, extracted
    for s in entries:
        e_s = norm(s["expected_skills"])
        x_s = norm(skill_extractor.extract(s["text"]))
        e_t = norm(s["expected_technologies"])
        x_t = norm(tech_extractor.extract(nlp(s["text"])))
        hs = len(set(e_s) & set(x_s))
        ht = len(set(e_t) & set(x_t))
        for key, hits, e, x in (("skills", hs, e_s, x_s), ("tech", ht, e_t, x_t)):
            tot[key][0] += hits
            tot[key][1] += len(e)
            tot[key][2] += len(x)
        print(
            f"| {s['id']} | {rate(hs, len(e_s))} | {rate(hs, len(x_s))} | {rate(ht, len(e_t))} | {rate(ht, len(x_t))} |"
        )
    print("LABELED MICRO TOTALS")
    for key, (hits, exp, ext) in tot.items():
        print(
            key,
            "hits",
            hits,
            "expected",
            exp,
            "extracted",
            ext,
            "recall",
            rate(hits, exp),
            "precision",
            rate(hits, ext),
        )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate POC extractors on the snippet set and an optional labeled-JD set."
    )
    parser.add_argument(
        "--labeled-jds",
        type=Path,
        default=None,
        help=f"Labeled-JD JSON file. Default: {DEFAULT_LABELED_JDS.relative_to(ROOT)} if it exists, otherwise skipped.",
    )
    args = parser.parse_args(argv)
    if args.labeled_jds is not None and not args.labeled_jds.is_file():
        parser.error(f"--labeled-jds file not found: {args.labeled_jds}")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    labeled_path: Path | None = args.labeled_jds
    if labeled_path is None and DEFAULT_LABELED_JDS.is_file():
        labeled_path = DEFAULT_LABELED_JDS
    labeled_entries: list[dict[str, Any]] | None = None
    if labeled_path is not None:
        try:
            labeled_entries = load_labeled_jds(labeled_path)
        except LabeledJDError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    nlp = spacy.load("en_core_web_md")
    print("spacy", spacy.__version__, "model", nlp.meta["version"])
    snippets = json.loads(EVAL_SET.read_text(encoding="utf-8"))

    skill_extractor = SkillExtractor(model_name="en_core_web_md")
    tech_extractor = TechExtractor(nlp)

    rows = []
    tot = {"skills": [0, 0, 0], "tech": [0, 0, 0]}  # hits, expected, extracted
    for s in snippets:
        e_s = norm(s["expected_skills"])
        x_s = norm(skill_extractor.extract(s["text"]))
        e_t = norm(s["expected_technologies"])
        x_t = norm(tech_extractor.extract(nlp(s["text"])))
        hs = len(set(e_s) & set(x_s))
        ht = len(set(e_t) & set(x_t))
        rows.append((s["id"], e_s, x_s, e_t, x_t, hs, ht))
        for key, hits, e, x in (("skills", hs, e_s, x_s), ("tech", ht, e_t, x_t)):
            tot[key][0] += hits
            tot[key][1] += len(e)
            tot[key][2] += len(x)
        print(f"\n{s['id']} TEXT: {s['text']}")
        for label, e, x, hits in (("skills", e_s, x_s, hs), ("tech  ", e_t, x_t, ht)):
            print(f"  {label} E={e}\n         X={x}")
            print(f"         exact={e == x} hit={rate(hits, len(e))} prec={rate(hits, len(x))}")

    print("\nSUMMARY TABLE")
    print("| id | skills hit rate | skills precision | tech hit rate | tech precision | skills exact | tech exact |")
    for sid, e_s, x_s, e_t, x_t, hs, ht in rows:
        print(
            f"| {sid} | {rate(hs, len(e_s))} | {rate(hs, len(x_s))} | "
            f"{rate(ht, len(e_t))} | {rate(ht, len(x_t))} | {e_s == x_s} | {e_t == x_t} |"
        )
    print("\nMICRO TOTALS")
    for key, (hits, exp, ext) in tot.items():
        print(key, "hits", hits, "expected", exp, "extracted", ext, "hit", rate(hits, exp), "prec", rate(hits, ext))
    print("skills exact-match snippets:", sum(1 for r in rows if r[1] == r[2]), "/", len(rows))
    print("tech exact-match snippets:", sum(1 for r in rows if r[3] == r[4]), "/", len(rows))

    if labeled_path is not None and labeled_entries is not None:
        print_labeled(labeled_path, labeled_entries, skill_extractor, tech_extractor, nlp)


if __name__ == "__main__":
    main()
