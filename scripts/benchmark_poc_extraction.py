"""Benchmark POC skill and technology extraction (Issue #432).

Measures:
(a) Model load time: spacy.load("en_core_web_md") and SkillExtractor construction.
(b) Extraction latency at target sizes ~100 / ~1000 / ~5000 tokens (actual counts reported) (min/median/max ms).
    Tech path is split into nlp(text) parse time and TechExtractor.extract(doc) time.
(c) Peak tracemalloc memory per input size.

Inputs are built by repeating the POC fixture text. Token counts are len(nlp(text)).

Usage:
    uv run python scripts/benchmark_poc_extraction.py [--table] [--repeats N]
"""

import argparse
import json
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

import spacy
from spacy.language import Language

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.poc.skills.extract_skills_a import SkillExtractor  # noqa: E402
from src.poc.technologies.extract_technologies_a import TechExtractor  # noqa: E402

FIXTURE_DIR = PROJECT_ROOT / "tests" / "poc" / "fixtures"
FIXTURE_NAMES = (
    "raw_jd_what_you_ll_do.md",
    "raw_jd_knowledge_skills_abilities.md",
)
MODEL_NAME = "en_core_web_md"
SIZE_TARGETS: dict[str, int] = {"small": 100, "medium": 1000, "large": 5000}


def load_fixture_text() -> str:
    """Read and join the POC fixture files.

    Raises:
        FileNotFoundError: If any fixture file is missing.
    """
    parts: list[str] = []
    for name in FIXTURE_NAMES:
        path = FIXTURE_DIR / name
        if not path.is_file():
            raise FileNotFoundError(f"fixture missing: {path}")
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def build_sized_text(base_text: str, base_tokens: int, target_tokens: int) -> str:
    """Repeat base_text so its token count is approximately target_tokens."""
    reps = max(1, round(target_tokens / max(base_tokens, 1)))
    return "\n".join([base_text] * reps)


def summarize(samples_ms: list[float]) -> dict[str, float]:
    """Return min/median/max of latency samples in milliseconds."""
    return {
        "min_ms": round(min(samples_ms), 3),
        "median_ms": round(statistics.median(samples_ms), 3),
        "max_ms": round(max(samples_ms), 3),
    }


def time_calls(fn: Callable[[], Any], repeats: int) -> list[float]:
    """Time fn() repeats times using time.perf_counter. Returns samples in ms."""
    samples_ms: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples_ms.append((time.perf_counter() - start) * 1000.0)
    return samples_ms


def warm_then_time(fn: Callable[[], Any], repeats: int) -> dict[str, float]:
    """Run fn once untimed (warm-up), then summarize repeats timed calls."""
    fn()
    return summarize(time_calls(fn, repeats))


def peak_bytes(fn: Callable[[], Any]) -> int:
    """Return tracemalloc peak bytes allocated while running fn once."""
    started_here = not tracemalloc.is_tracing()
    if started_here:
        tracemalloc.start()
    else:
        tracemalloc.reset_peak()
    try:
        fn()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        if started_here:
            tracemalloc.stop()
    return peak


def bench_size(
    text: str,
    target_tokens: int,
    nlp: Language,
    skill: SkillExtractor,
    tech: TechExtractor,
    repeats: int,
) -> dict[str, Any]:
    """Measure latency and peak memory for one input size."""
    doc = nlp(text)
    tokens = len(doc)

    skill_ms = warm_then_time(lambda: skill.extract(text), repeats)
    tech_parse_ms = warm_then_time(lambda: nlp(text), repeats)
    tech_extract_ms = warm_then_time(lambda: tech.extract(doc), repeats)

    skill_peak = peak_bytes(lambda: skill.extract(text))
    tech_peak = peak_bytes(lambda: tech.extract(nlp(text)))

    return {
        "target_tokens": target_tokens,
        "tokens": tokens,
        "chars": len(text),
        "skill_extract_ms": skill_ms,
        "tech_parse_ms": tech_parse_ms,
        "tech_extract_ms": tech_extract_ms,
        "skill_peak_bytes": skill_peak,
        "tech_parse_plus_extract_peak_bytes": tech_peak,
    }


def run_benchmark(repeats: int) -> dict[str, Any]:
    """Run all measurements and return a JSON-serializable result dict."""
    base_text = load_fixture_text()

    cold_start = time.perf_counter()
    nlp = spacy.load(MODEL_NAME)
    spacy_cold_ms = (time.perf_counter() - cold_start) * 1000.0

    spacy_load_samples = time_calls(lambda: spacy.load(MODEL_NAME), repeats)
    skill_init_samples = time_calls(lambda: SkillExtractor(model_name=MODEL_NAME), repeats)

    skill = SkillExtractor(model_name=MODEL_NAME)
    tech = TechExtractor(nlp)
    base_tokens = len(nlp(base_text))

    sizes: dict[str, Any] = {}
    for label, target in SIZE_TARGETS.items():
        text = build_sized_text(base_text, base_tokens, target)
        sizes[label] = bench_size(text, target, nlp, skill, tech, repeats)

    return {
        "model": MODEL_NAME,
        "repeats": repeats,
        "model_load": {
            "spacy_load_cold_ms": round(spacy_cold_ms, 3),
            "spacy_load_ms": summarize(spacy_load_samples),
            "skill_extractor_init_ms": summarize(skill_init_samples),
        },
        "sizes": sizes,
    }


def _fmt_row(name: str, stats: dict[str, float]) -> str:
    return f"{name:<36} {stats['min_ms']:>12.3f} {stats['median_ms']:>12.3f} {stats['max_ms']:>12.3f}"


def render_table(result: dict[str, Any]) -> str:
    """Render the benchmark result as a plain text table."""
    header = f"{'metric':<36} {'min_ms':>12} {'median_ms':>12} {'max_ms':>12}"
    lines = [header, "-" * len(header)]

    load = result["model_load"]
    lines.append(f"{'spacy.load cold (single call)':<36} {load['spacy_load_cold_ms']:>12.3f}")
    lines.append(_fmt_row("spacy.load", load["spacy_load_ms"]))
    lines.append(_fmt_row("SkillExtractor init", load["skill_extractor_init_ms"]))

    for label, size in result["sizes"].items():
        tokens = size["tokens"]
        lines.append(_fmt_row(f"skill extract {label} ({tokens} tok)", size["skill_extract_ms"]))
        lines.append(_fmt_row(f"tech nlp() parse {label} ({tokens} tok)", size["tech_parse_ms"]))
        lines.append(_fmt_row(f"tech extract(doc) {label} ({tokens} tok)", size["tech_extract_ms"]))

    lines.append("")
    lines.append(f"{'size':<10} {'tokens':>8} {'skill_peak_KiB':>16} {'tech_peak_KiB':>16}")
    for label, size in result["sizes"].items():
        skill_kib = size["skill_peak_bytes"] / 1024
        tech_kib = size["tech_parse_plus_extract_peak_bytes"] / 1024
        lines.append(f"{label:<10} {size['tokens']:>8} {skill_kib:>16.1f} {tech_kib:>16.1f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Parse args, run the benchmark, and print JSON (default) or a table."""
    parser = argparse.ArgumentParser(description="Benchmark POC skill and technology extraction.")
    parser.add_argument(
        "--table",
        action="store_true",
        help="Print a plain text table instead of JSON.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="Timed repeats per measurement (default: 5).",
    )
    args = parser.parse_args(argv)

    if args.repeats < 1:
        print("error: --repeats must be >= 1", file=sys.stderr)
        return 1

    try:
        result = run_benchmark(args.repeats)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.table:
        print(render_table(result))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
