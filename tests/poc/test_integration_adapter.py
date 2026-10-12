"""Tests for CombinedExtractor POC adapter (Issue #433)."""

import json
from pathlib import Path
from typing import Any

import pytest

from src.poc.integration_adapter import CombinedExtractor

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "docs" / "dev-note" / "poc" / "expected_output_schema.json"
# Verb is not sentence-initial: spaCy tags sentence-initial "Design" as NOUN, so the skill pattern would miss it.
JD_SENTENCE = "You will design deep learning architectures using PyTorch and TensorFlow."


@pytest.fixture(scope="module")
def adapter() -> CombinedExtractor:
    """Load CombinedExtractor once per module (spaCy load is slow)."""
    return CombinedExtractor()


def _boom(*args: Any, **kwargs: Any) -> Any:
    """Raise to simulate an extractor failure."""
    raise RuntimeError("simulated failure")


def test_both_keys_always_present(adapter: CombinedExtractor) -> None:
    """Result always contains exactly the skills and technologies keys."""
    for text in ["", "   ", JD_SENTENCE, "Nothing relevant here."]:
        result = adapter.extract(text)
        assert set(result.keys()) == {"skills", "technologies"}
        assert isinstance(result["skills"], list)
        assert isinstance(result["technologies"], list)


def test_real_jd_sentence_extracts_skills_and_technologies(adapter: CombinedExtractor) -> None:
    """A real JD sentence yields non-empty skills and PyTorch as a technology."""
    result = adapter.extract(JD_SENTENCE)
    assert result["skills"]
    assert result["technologies"]
    assert "pytorch" in result["technologies"]


def test_output_sorted_and_deduplicated(adapter: CombinedExtractor) -> None:
    """Each list is sorted ascending with no duplicates."""
    text = (
        f"{JD_SENTENCE} Design deep learning architectures and use PyTorch. "
        "Design deep learning architectures again. Use PyTorch daily."
    )
    result = adapter.extract(text)
    for key in ("skills", "technologies"):
        values = result[key]
        assert values == sorted(set(values))
        assert all(v == v.lower() for v in values)


def test_empty_string_returns_empty_lists(adapter: CombinedExtractor) -> None:
    """Empty and whitespace-only input yields both keys empty."""
    assert adapter.extract("") == {"skills": [], "technologies": []}
    assert adapter.extract("   \n\t ") == {"skills": [], "technologies": []}


def test_skill_failure_isolated(adapter: CombinedExtractor, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing SkillExtractor yields skills == [] and leaves technologies intact."""
    monkeypatch.setattr(adapter.skills, "extract", _boom)
    result = adapter.extract(JD_SENTENCE)
    assert result["skills"] == []
    assert "pytorch" in result["technologies"]


def test_tech_failure_isolated(adapter: CombinedExtractor, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing tech pipeline yields technologies == [] and leaves skills intact."""
    monkeypatch.setattr(adapter, "tech_nlp", _boom)
    result = adapter.extract(JD_SENTENCE)
    assert result["technologies"] == []
    assert result["skills"]


def test_output_matches_expected_schema_structure(adapter: CombinedExtractor) -> None:
    """Output structurally matches docs/dev-note/poc/expected_output_schema.json.

    Hand-rolled on purpose (Issue #447): the checks are driven by the schema file
    (required keys, additionalProperties, array type, uniqueItems). The schema only
    documents sorted/lowercase output in prose, and JSON Schema cannot express either,
    so those are asserted here. A jsonschema dev dependency would still need both
    hand-written asserts, so it is not used.
    """
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    result = adapter.extract(JD_SENTENCE)

    assert schema["additionalProperties"] is False
    assert set(result.keys()) == set(schema["required"]) == set(schema["properties"].keys())

    for key, prop in schema["properties"].items():
        assert prop["type"] == "array"
        values = result[key]
        assert isinstance(values, list)
        assert all(isinstance(v, str) for v in values)
        if prop.get("uniqueItems"):
            assert len(values) == len(set(values))
        assert values == sorted(values)
        assert all(v == v.lower() for v in values)
