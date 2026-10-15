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


def _newline_split_calls(tree: ast.Module) -> list[str]:
    """Find all .split() calls that use newline patterns (positional, keyword, or regex escape).

    Detects:
    - Positional args: s.split("\\n"), re.split("\\n", s)
    - Keyword args: s.split(sep="\\n"), re.split(pattern="\\n", s)
    - Regex escapes: r"\\n" passed to split (the two-char sequence backslash-n)
    """
    offending: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Check if this is a split() call
        is_split_call = False
        if isinstance(node.func, ast.Attribute) and node.func.attr == "split":
            is_split_call = True
        elif isinstance(node.func, ast.Name) and node.func.id == "split":
            is_split_call = True

        if not is_split_call:
            continue

        # Check positional arguments for newline patterns
        for i, arg in enumerate(node.args):
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                # Check for literal newline
                if "\n" in arg.value or "\r\n" in arg.value:
                    offending.append(f"line {node.lineno}: .split({arg.value!r})")
                # Check for regex escape backslash-n (r"\n")
                elif arg.value == "\\n":
                    offending.append(f"line {node.lineno}: .split(r\"\\n\")")

        # Check keyword arguments sep= or pattern=
        for keyword in node.keywords:
            if keyword.arg in ("sep", "pattern"):
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    val = keyword.value.value
                    if "\n" in val or "\r\n" in val:
                        offending.append(f"line {node.lineno}: .split({keyword.arg}={val!r})")
                    elif val == "\\n":
                        offending.append(f"line {node.lineno}: .split({keyword.arg}=r\"\\n\")")

    return offending


def _split(text: str) -> list[str]:
    nlp = spacy.blank("en")
    nlp.add_pipe("poc_sentence_splitter")
    doc = nlp(text)
    result: list[str] = doc._.poc_sentences
    return result


def test_multi_sentence_single_line_splits_into_three() -> None:
    assert _split("A. B! C?") == ["A.", "B!", "C?"]


def test_embedded_newline_inside_sentence_is_not_split() -> None:
    assert _split("Must know\nPython.") == ["Must know\nPython."]


def test_markdown_line_with_multiple_sentences_splits_correctly() -> None:
    # Known/intended POC limitation: the heading has no terminator, so it glues onto
    # the following sentence. The assertion pins this behavior; do not "fix" it here.
    text = "## Requirements\n\nYou must know Python. Experience with SQL is a plus!"
    assert _split(text) == [
        "## Requirements\n\nYou must know Python.",
        "Experience with SQL is a plus!",
    ]


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
    tree = _module_ast()
    offending = _newline_split_calls(tree)
    assert offending == [], f"newline-based .split() forbidden in sentence_splitter: {offending}"


def test_newline_split_calls_detects_positional_newline() -> None:
    """Verify _newline_split_calls detects positional args with literal newline."""
    code = 's.split("\\n")'
    tree = ast.parse(code)
    offending = _newline_split_calls(tree)
    assert len(offending) == 1
    assert 'split(' in offending[0]


def test_newline_split_calls_detects_keyword_sep_newline() -> None:
    """Verify _newline_split_calls detects sep= keyword with literal newline."""
    code = 's.split(sep="\\n")'
    tree = ast.parse(code)
    offending = _newline_split_calls(tree)
    assert len(offending) == 1
    assert 'sep=' in offending[0]


def test_newline_split_calls_detects_keyword_pattern_newline() -> None:
    """Verify _newline_split_calls detects pattern= keyword with literal newline."""
    code = 're.split(pattern="\\n", string=s)'
    tree = ast.parse(code)
    offending = _newline_split_calls(tree)
    assert len(offending) == 1
    assert 'pattern=' in offending[0]


def test_newline_split_calls_detects_regex_backslash_n() -> None:
    """Verify _newline_split_calls detects regex escape r\"\\n\" passed to split."""
    code = 's.split(r"\\n")'
    tree = ast.parse(code)
    offending = _newline_split_calls(tree)
    assert len(offending) == 1
    assert 'r"\\n"' in offending[0]


def test_newline_split_calls_detects_from_import_split() -> None:
    """Verify _newline_split_calls detects 'from re import split' form."""
    code = 'split("\\n", s)'
    tree = ast.parse(code)
    offending = _newline_split_calls(tree)
    assert len(offending) == 1


def test_newline_split_calls_ignores_clean_code() -> None:
    """Verify _newline_split_calls does not flag clean split calls."""
    code = 's.split(" ")'
    tree = ast.parse(code)
    offending = _newline_split_calls(tree)
    assert offending == []
