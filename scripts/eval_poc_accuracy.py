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

Corpus mode (Issue #552) runs the same extractors over every sentence of a
wider corpus instead of the labeled sets, so output can be diffed before and
after a change:
    uv run python scripts/eval_poc_accuracy.py --corpus tests/poc/fixtures --dump before.json
    # ... make the change ...
    uv run python scripts/eval_poc_accuracy.py --corpus tests/poc/fixtures --compare before.json
--corpus takes a directory (searched recursively) or a glob; only *.md and *.json
files are read. --dump writes the per-sentence output as sorted, indented JSON;
--compare prints only sentences whose text, skill output or tech output differs
from the dump, with before/after values. Corpus mode skips the snippet and
labeled-JD evals. Sentence splitting is documented in split_sentences().
"""

import argparse
import glob
import json
import re
import sys
from collections.abc import Iterator
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

CORPUS_SUFFIXES = (".md", ".json")
DUMP_SCHEMA = "eval_poc_corpus_dump"
DUMP_VERSION = 1
# Break after sentence-final punctuation followed by whitespace (no lookbehind on abbreviations).
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
# Leading Markdown markers: headings, bullets, numbered items, blockquotes.
_LINE_MARKER = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)")


class LabeledJDError(ValueError):
    """Raised when a labeled-JD file does not match the documented format."""


class CorpusError(ValueError):
    """Raised when a corpus, or a dump file used with --compare, cannot be used."""


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


def split_sentences(text: str) -> list[str]:
    """Split text into sentences for corpus mode (Issue #552). Regex only, no spaCy, deterministic.

    1. Each line is a candidate block; blank lines are dropped.
    2. Leading Markdown markers (``#`` headings, ``-``/``*``/``+`` bullets, ``1.`` items, ``>`` quotes) are stripped.
    3. Each block is broken after ``.``, ``!`` or ``?`` followed by whitespace.
    4. Pieces with no letter or digit (e.g. ``---`` dividers) are dropped.
    Known limit: abbreviations followed by a space ("e.g. ", "etc. ") also split.
    """
    sentences: list[str] = []
    for line in text.splitlines():
        block = _LINE_MARKER.sub("", line).strip()
        for piece in _SENTENCE_BREAK.split(block):
            piece = piece.strip()
            if any(ch.isalnum() for ch in piece):
                sentences.append(piece)
    return sentences


def _has_magic(text: str) -> bool:
    return any(ch in text for ch in "*?[")


def _literal_prefix(pattern: str) -> Path:
    """Leading path components of a glob pattern that contain no wildcard characters."""
    parts: list[str] = []
    for part in Path(pattern).parts:
        if _has_magic(part):
            break
        parts.append(part)
    return Path(*parts) if parts else Path(".")


def collect_corpus(spec: str) -> list[tuple[str, Path]]:
    """Return (stable id prefix, file) pairs for a corpus directory, file or glob, sorted by prefix.

    The id prefix is the path relative to the directory (or to the glob's literal prefix), in POSIX form,
    so dumps do not embed machine-specific absolute paths.
    """
    path = Path(spec)
    if path.is_dir():
        found = [p for p in path.rglob("*") if p.is_file() and p.suffix in CORPUS_SUFFIXES]
        pairs = [(p.relative_to(path).as_posix(), p) for p in found]
    elif path.is_file():
        pairs = [(path.name, path)]
    elif _has_magic(spec):
        root = _literal_prefix(spec)
        pairs = []
        for match in sorted(glob.glob(spec, recursive=True)):
            candidate = Path(match)
            if candidate.is_file() and candidate.suffix in CORPUS_SUFFIXES:
                pairs.append((candidate.relative_to(root).as_posix(), candidate))
    else:
        raise CorpusError(f"corpus path not found: {spec}")
    if not pairs:
        raise CorpusError(f"no {' or '.join(CORPUS_SUFFIXES)} files found for corpus {spec!r}")
    return sorted(pairs, key=lambda pair: pair[0])


def _json_strings(node: Any) -> Iterator[str]:
    """String values of a parsed JSON document, in document order (keys are skipped)."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _json_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _json_strings(value)


def _file_texts(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CorpusError(f"{path}: cannot read as UTF-8 text: {exc}") from exc
    if path.suffix != ".json":
        return [raw]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{path}: invalid JSON: {exc}") from exc
    return list(_json_strings(data))


def build_records(files: list[tuple[str, Path]]) -> list[tuple[str, str]]:
    """Return (sentence id, sentence) pairs. Id is ``<prefix>:<5-digit index within file>``."""
    records: list[tuple[str, str]] = []
    for prefix, path in files:
        sentences = [s for text in _file_texts(path) for s in split_sentences(text)]
        records.extend((f"{prefix}:{i:05d}", sentence) for i, sentence in enumerate(sentences))
    if not records:
        raise CorpusError("corpus contains no sentences")
    return records


def build_dump(records: list[tuple[str, str]], skill_fn: Any, tech_fn: Any) -> dict[str, Any]:
    """Run both extractors on every sentence. Keys are sorted; skill and tech lists are normalised."""
    sentences = {
        sid: {"text": text, "skills": norm(skill_fn(text)), "tech": norm(tech_fn(text))} for sid, text in records
    }
    return {"schema": DUMP_SCHEMA, "version": DUMP_VERSION, "sentences": dict(sorted(sentences.items()))}


def write_dump(path: Path, dump: dict[str, Any]) -> None:
    text = json.dumps(dump, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise CorpusError(f"cannot write dump {path}: {exc}") from exc


def load_dump(path: Path) -> dict[str, Any]:
    """Load and validate a dump written by write_dump()."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise CorpusError(f"cannot read dump {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != DUMP_SCHEMA or data.get("version") != DUMP_VERSION:
        raise CorpusError(f"{path}: not a {DUMP_SCHEMA} v{DUMP_VERSION} dump (create one with --dump)")
    sentences = data.get("sentences")
    if not isinstance(sentences, dict):
        raise CorpusError(f"{path}: 'sentences' must be an object")
    for sid, entry in sentences.items():
        ok = (
            isinstance(entry, dict)
            and isinstance(entry.get("text"), str)
            and isinstance(entry.get("skills"), list)
            and isinstance(entry.get("tech"), list)
        )
        if not ok:
            raise CorpusError(f"{path}: sentence {sid!r} must have text, skills and tech")
    return data


def compare_dumps(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Diff two dumps by sentence id. Changed = text, skills or tech differs for an id present in both."""
    b_sent: dict[str, Any] = before["sentences"]
    a_sent: dict[str, Any] = after["sentences"]
    common = sorted(set(b_sent) & set(a_sent))
    changed = [
        (sid, b_sent[sid], a_sent[sid])
        for sid in common
        if (b_sent[sid]["text"], b_sent[sid]["skills"], b_sent[sid]["tech"])
        != (a_sent[sid]["text"], a_sent[sid]["skills"], a_sent[sid]["tech"])
    ]
    added = [(sid, a_sent[sid]) for sid in sorted(set(a_sent) - set(b_sent))]
    removed = [(sid, b_sent[sid]) for sid in sorted(set(b_sent) - set(a_sent))]
    return {"common": len(common), "changed": changed, "added": added, "removed": removed}


def format_compare(result: dict[str, Any], dump_name: str) -> list[str]:
    lines = [f"COMPARE against {dump_name}: sentences in both={result['common']}"]
    for sid, before, after in result["changed"]:
        lines.append(f"\nCHANGED {sid}")
        if before["text"] != after["text"]:
            lines.append(f"  TEXT before: {before['text']}")
            lines.append(f"  TEXT after:  {after['text']}")
        else:
            lines.append(f"  TEXT: {after['text']}")
        if before["skills"] != after["skills"]:
            lines.append(f"  SKILLS before={before['skills']}")
            lines.append(f"         after ={after['skills']}")
        if before["tech"] != after["tech"]:
            lines.append(f"  TECH   before={before['tech']}")
            lines.append(f"         after ={after['tech']}")
    for sid, entry in result["added"]:
        lines.append(f"\nADDED {sid}: {entry['text']}")
    for sid, entry in result["removed"]:
        lines.append(f"\nREMOVED {sid}: {entry['text']}")
    lines.append(
        f"\nSUMMARY compared={result['common']} changed={len(result['changed'])} "
        f"added={len(result['added'])} removed={len(result['removed'])}"
    )
    return lines


def print_sentence_listing(dump: dict[str, Any]) -> None:
    for sid, entry in dump["sentences"].items():
        print(f"{sid}\tskills={entry['skills']}\ttech={entry['tech']}")


def run_corpus_mode(args: argparse.Namespace) -> None:
    try:
        files = collect_corpus(args.corpus)
        records = build_records(files)
        before = load_dump(args.compare) if args.compare is not None else None
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    nlp = spacy.load("en_core_web_md")
    print("spacy", spacy.__version__, "model", nlp.meta["version"])
    skill_extractor = SkillExtractor(model_name="en_core_web_md")
    tech_extractor = TechExtractor(nlp)
    dump = build_dump(records, skill_extractor.extract, lambda text: tech_extractor.extract(nlp(text)))
    print(f"CORPUS files={len(files)} sentences={len(records)}")

    try:
        if args.dump is not None:
            write_dump(args.dump, dump)
            print(f"DUMP written: {args.dump} sentences={len(dump['sentences'])}")
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if before is not None:
        # Informational diff: exit status is 0 whether or not sentences changed (see PR for rationale).
        for line in format_compare(compare_dumps(before, dump), str(args.compare)):
            print(line)
    elif args.dump is None:
        print_sentence_listing(dump)


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
    parser.add_argument(
        "--corpus",
        default=None,
        help="Corpus mode: directory (searched recursively) or glob of .md/.json files whose sentences are "
        "run through the extractors. Skips the snippet and labeled-JD evals.",
    )
    parser.add_argument(
        "--dump",
        type=Path,
        default=None,
        help="With --corpus: write per-sentence skill/tech output to this JSON file (sorted, deterministic).",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        default=None,
        help="With --corpus: diff current output against a file written by --dump; print only changed sentences.",
    )
    args = parser.parse_args(argv)
    if args.labeled_jds is not None and not args.labeled_jds.is_file():
        parser.error(f"--labeled-jds file not found: {args.labeled_jds}")
    if args.corpus is None:
        if args.dump is not None or args.compare is not None:
            parser.error("--dump and --compare require --corpus")
    else:
        if args.labeled_jds is not None:
            parser.error("--corpus cannot be combined with --labeled-jds")
        if not Path(args.corpus).exists() and not _has_magic(args.corpus):
            parser.error(f"--corpus path not found: {args.corpus}")
        if args.compare is not None and not args.compare.is_file():
            parser.error(f"--compare file not found: {args.compare}")
    return args


def run_eval(args: argparse.Namespace) -> None:
    """Default mode: snippet eval plus the optional labeled-JD eval."""
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


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.corpus is not None:
        run_corpus_mode(args)
    else:
        run_eval(args)


if __name__ == "__main__":
    main()
