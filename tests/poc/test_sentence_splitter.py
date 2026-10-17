"""Model-free tests for the POC regex-only sentence splitter (Issue #638 / #639)."""

from __future__ import annotations

import ast
from pathlib import Path

import spacy

from src.poc.sentence_splitter import PocSentenceSplitterComponent, create_poc_sentence_splitter

MODULE_PATH = Path(__file__).resolve().parents[2] / "src" / "poc" / "sentence_splitter.py"


def _module_ast() -> ast.Module:
    """Parse the sentence_splitter module once, reusable across tests."""
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def _split(text: str) -> list[str]:
    nlp = spacy.blank("en")
    nlp.add_pipe("poc_sentence_splitter")
    doc = nlp(text)
    result: list[str] = doc._.poc_sentences
    return result


def test_multi_sentence_single_line_splits_into_three() -> None:
    assert _split("A. B! C?") == ["A.", "B!", "C?"]


def test_embedded_newline_is_split_into_two_sentences() -> None:
    assert _split("Must know\nPython.") == ["Must know", "Python."]


def test_markdown_line_with_multiple_sentences_splits_correctly() -> None:
    text = "## Requirements\n\nYou must know Python. Experience with SQL is a plus!"
    assert _split(text) == [
        "## Requirements",
        "You must know Python.",
        "Experience with SQL is a plus!",
    ]


def test_definition_list_line_is_split_on_newline() -> None:
    assert _split("locations\n:   Seattle, WA") == ["locations", ":   Seattle, WA"]


def test_bullet_lines_split_into_separate_sentences() -> None:
    assert _split("* Item one\n* Item two") == ["* Item one", "* Item two"]


def test_no_output_sentence_contains_newline() -> None:
    text = "## Requirements\n\n* Must know Python.\n\nlocations\n:   Seattle, WA\n\nYou must know SQL. Also Go!"
    sentences = _split(text)
    assert sentences == [
        "## Requirements",
        "* Must know Python.",
        "locations",
        ":   Seattle, WA",
        "You must know SQL.",
        "Also Go!",
    ]
    assert all("\n" not in s and "\r" not in s for s in sentences)


def test_crlf_line_endings_are_split_without_carriage_returns() -> None:
    sentences = _split("Must know\r\nPython.\r\nSQL is good.\r\n")
    assert sentences == ["Must know", "Python.", "SQL is good."]
    assert all("\r" not in s and "\n" not in s for s in sentences)


def test_empty_string_returns_empty_list() -> None:
    assert _split("") == []


def test_whitespace_only_string_returns_empty_list() -> None:
    assert _split("   \n\t  ") == []


def test_sentences_are_list_of_non_empty_stripped_strings() -> None:
    sentences = _split("  First one.   Second one.  ")
    assert sentences == ["First one.", "Second one."]
    assert all(isinstance(s, str) and s and s == s.strip() for s in sentences)


def test_factory_registers_on_bare_blank_pipeline() -> None:
    nlp = spacy.blank("en")
    assert nlp.pipe_names == []
    nlp.add_pipe("poc_sentence_splitter")
    assert nlp.pipe_names == ["poc_sentence_splitter"]
    component = create_poc_sentence_splitter(nlp, "poc_sentence_splitter")
    assert isinstance(component, PocSentenceSplitterComponent)


def test_module_has_no_src_imports() -> None:
    tree = _module_ast()
    offending: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offending.extend(alias.name for alias in node.names if alias.name.split(".")[0] == "src")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level > 0 or module.split(".")[0] == "src":
                offending.append("." * node.level + module)
    assert offending == [], f"src.* imports forbidden in sentence_splitter: {offending}"


def test_module_does_not_split_on_newline() -> None:
    """Ensure sentence_splitter doesn't call .split() on strings."""
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "split":
                # Skip if called on a regex pattern (e.g., _SENTENCE_BOUNDARY_RE.split)
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id.startswith("_"):
                        continue
                msg = f"Line {node.lineno}: string .split() forbidden"
                raise AssertionError(msg)
