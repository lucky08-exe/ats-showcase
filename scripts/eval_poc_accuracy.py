"""Run POC skill/tech extractors over the labeled eval set and print metrics.

Usage (from repo root, needs spaCy model en_core_web_md):
    uv run python scripts/eval_poc_accuracy.py

Prints per-snippet hit rate / precision / exact match and micro totals.
Hit rate = |E & X| / |E|; precision = |E & X| / |X|; N/A when denominator is 0.
See docs/dev-note/poc/extraction_accuracy_report.md (Issue #431, #449).
"""

import json
import sys
from pathlib import Path

import spacy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.poc.skills.extract_skills_a import SkillExtractor  # noqa: E402
from src.poc.technologies.extract_technologies_a import TechExtractor  # noqa: E402

EVAL_SET = ROOT / "tests" / "poc" / "fixtures" / "accuracy_eval_set.json"


def norm(xs: list[str]) -> list[str]:
    return sorted({str(x).strip().lower() for x in xs})


def rate(num: int, den: int) -> str:
    return "N/A" if den == 0 else f"{num}/{den}={num / den:.2f}"


def main() -> None:
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


if __name__ == "__main__":
    main()
