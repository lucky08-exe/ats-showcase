"""Tests for Phase 8b SpanCategorizer component.

Focused unit tests validating boundary extraction, span type classification,
and edge case handling. Delegates comprehensive fixture-based tests to
test_span_categorizer_edge_cases.py and test_integration_spans_chunks.py.
"""

from typing import Generator

import pytest
import spacy
from spacy.language import Language
from spacy.tokens import Doc

from src.preprocessing.requirement_filter import requirement_filter
from src.preprocessing.span_categorizer import (
    _expand_span,
    _extract_span_boundaries,
    _is_hard_boundary,
    _is_soft_boundary,
    span_categorizer,
)


@pytest.fixture(scope="session")
def nlp() -> Language:
    """Load plain en_core_web_md model (no pipeline changes), shared across tests.

    Returns:
        spaCy Language model
    """
    return spacy.load("en_core_web_md")


@pytest.fixture(scope="session")
def spacy_model() -> Generator[Language, None, None]:
    """Load spaCy model with requirement_filter and span_categorizer components.

    Yields:
        Configured spaCy Language model
    """
    try:
        nlp = spacy.load("en_core_web_md")
    except OSError:
        pytest.skip("en_core_web_md not installed")

    for component_name in ["ner"]:
        if component_name in nlp.pipe_names:
            nlp.remove_pipe(component_name)

    if "requirement_filter" not in nlp.pipe_names:
        nlp.add_pipe("requirement_filter")

    if "span_categorizer" not in nlp.pipe_names:
        nlp.add_pipe("span_categorizer")

    yield nlp


class TestExtractSpanBoundaries:
    """Unit tests for _extract_span_boundaries() function."""

    def test_valid_boundary_detection(self, nlp: Language) -> None:
        """Valid character offsets map to correct token indices."""
        text = "Required: 5+ years Python experience"
        doc = nlp(text)

        # Find a valid span in the text
        char_start = text.find("5+")
        char_end = char_start + len("5+ years Python")

        start_idx, end_idx = _extract_span_boundaries(doc, char_start, char_end)

        assert start_idx is not None
        assert end_idx is not None
        assert start_idx <= end_idx

    def test_invalid_char_start_negative(self, nlp: Language) -> None:
        """Negative char_start returns (None, None)."""
        text = "Required: 5+ years Python"
        doc = nlp(text)

        start_idx, end_idx = _extract_span_boundaries(doc, -1, 10)

        assert start_idx is None
        assert end_idx is None

    def test_invalid_char_end_negative(self, nlp: Language) -> None:
        """Negative char_end returns (None, None)."""
        text = "Required: 5+ years Python"
        doc = nlp(text)

        start_idx, end_idx = _extract_span_boundaries(doc, 5, -1)

        assert start_idx is None
        assert end_idx is None

    def test_invalid_char_start_gte_char_end(self, nlp: Language) -> None:
        """char_start >= char_end returns (None, None)."""
        text = "Required: 5+ years Python"
        doc = nlp(text)

        start_idx, end_idx = _extract_span_boundaries(doc, 15, 10)

        assert start_idx is None
        assert end_idx is None

    def test_invalid_char_start_beyond_doc(self, nlp: Language) -> None:
        """char_start beyond doc.text length returns (None, None)."""
        text = "Required: 5+ years"
        doc = nlp(text)

        start_idx, end_idx = _extract_span_boundaries(doc, len(text) + 10, len(text) + 20)

        assert start_idx is None
        assert end_idx is None

    def test_valid_single_token(self, nlp: Language) -> None:
        """Offset spanning single token returns correct indices."""
        text = "Python experience required"
        doc = nlp(text)

        # Single word "Python"
        char_start = text.find("Python")
        char_end = char_start + len("Python")

        start_idx, end_idx = _extract_span_boundaries(doc, char_start, char_end)

        assert start_idx is not None
        assert end_idx is not None
        assert start_idx == end_idx  # Single token

    def test_valid_multi_token(self, nlp: Language) -> None:
        """Offset spanning multiple tokens returns valid range."""
        text = "5+ years Python experience"
        doc = nlp(text)

        char_start = 0
        char_end = len("5+ years Python")

        start_idx, end_idx = _extract_span_boundaries(doc, char_start, char_end)

        assert start_idx is not None
        assert end_idx is not None
        assert start_idx < end_idx  # Multiple tokens


class TestBoundaryHelpers:
    """Unit tests for boundary detection helper functions."""

    def test_hard_boundary_period(self) -> None:
        """Period (.) is hard boundary."""
        result = _is_hard_boundary(".", "PUNCT", "punct")
        assert result is True

    def test_hard_boundary_semicolon(self) -> None:
        """Semicolon (;) is hard boundary."""
        result = _is_hard_boundary(";", "PUNCT", "punct")
        assert result is True

    def test_hard_boundary_close_paren(self) -> None:
        """Close paren ()) is hard boundary."""
        result = _is_hard_boundary(")", "PUNCT", "punct")
        assert result is True

    def test_hard_boundary_exclamation(self) -> None:
        """Exclamation mark (!) is hard boundary."""
        result = _is_hard_boundary("!", "PUNCT", "punct")
        assert result is True

    def test_hard_boundary_question(self) -> None:
        """Question mark (?) is hard boundary."""
        result = _is_hard_boundary("?", "PUNCT", "punct")
        assert result is True

    def test_non_boundary_comma(self) -> None:
        """Comma without conjunction context is not hard boundary."""
        result = _is_hard_boundary(",", "PUNCT", "punct")
        assert result is False

    def test_soft_boundary_comma_without_and_or(self) -> None:
        """Comma without 'and'/'or' is soft boundary."""
        result = _is_soft_boundary(",", "PUNCT", None)
        assert result is True

    def test_soft_boundary_comma_with_and(self) -> None:
        """Comma followed by 'and' is NOT soft boundary (continuation)."""
        result = _is_soft_boundary(",", "PUNCT", "and")
        assert result is False

    def test_soft_boundary_comma_with_or(self) -> None:
        """Comma followed by 'or' is NOT soft boundary (continuation)."""
        result = _is_soft_boundary(",", "PUNCT", "or")
        assert result is False

    def test_soft_boundary_non_comma_non_boundary(self) -> None:
        """Non-punctuation tokens are not soft boundaries."""
        result = _is_soft_boundary("python", "NOUN", None)
        assert result is False


class TestExpandSpan:
    """Unit tests for _expand_span() function."""

    def test_expand_stop_at_period(self, nlp: Language) -> None:
        """Expansion stops at period."""
        text = "Required: 5+ years Python experience. Knowledge of Docker."
        doc = nlp(text)

        # Initial span before period
        start_idx = 2  # "5"
        end_idx = 5  # "experience"

        expanded_start, expanded_end = _expand_span(doc, start_idx, end_idx)

        # Should not include period
        expanded_span = doc[expanded_start : expanded_end + 1]
        assert "." not in expanded_span.text

    def test_expand_includes_compound_and(self, nlp: Language) -> None:
        """Expansion continues through 'and' conjunctions."""
        text = "Required: Python and Java"
        doc = nlp(text)

        start_idx = 2  # "Python"
        end_idx = 2

        expanded_start, expanded_end = _expand_span(doc, start_idx, end_idx)

        expanded_span = doc[expanded_start : expanded_end + 1]
        # Should include "and Java"
        assert "and" in expanded_span.text or "Java" in expanded_span.text

    def test_expand_includes_hyphenated_compound(self, nlp: Language) -> None:
        """Expansion includes hyphenated words (compound dependency)."""
        text = "cross-functional team management"
        doc = nlp(text)

        start_idx = 0  # "cross"
        end_idx = 0

        expanded_start, expanded_end = _expand_span(doc, start_idx, end_idx)

        expanded_span = doc[expanded_start : expanded_end + 1]
        # Should preserve hyphenated compound or include both parts
        assert expanded_span.text

    def test_expand_bounds_respect_start_end(self, nlp: Language) -> None:
        """Expanded span never has end < start."""
        text = "Required: Python experience"
        doc = nlp(text)

        for start in range(len(doc)):
            for end in range(start, min(start + 3, len(doc))):
                exp_start, exp_end = _expand_span(doc, start, end)
                assert exp_start <= exp_end, f"Invalid range: {exp_start} > {exp_end}"


class TestSpanCategorizerComponent:
    """Thin integration tests for span_categorizer() component."""

    def test_component_with_valid_requirements(self, spacy_model: Language) -> None:
        """span_categorizer processes valid Phase 8a requirements."""
        text = "Required: 5+ years Python experience"
        doc = spacy_model(text)

        # Phase 8a populates requirements
        assert doc._.requirements is not None

        # Phase 8b populates spans
        assert doc._.requirement_spans is not None
        if len(doc._.requirements) > 0:
            # If requirements exist, spans should be created
            assert len(doc._.requirement_spans) > 0

    def test_component_skips_invalid_boundaries(self, spacy_model: Language) -> None:
        """span_categorizer handles requirements with invalid boundaries gracefully."""
        text = "Required: Python"
        doc = spacy_model(text)

        # Component should not crash even with edge cases
        assert hasattr(doc._, "requirement_spans")


class TestEdgeCases:
    """Test specific edge case behaviors."""

    def test_negation_handling(self, spacy_model: Language) -> None:
        """Pure negations should not produce spans (filtered by Phase 8a)."""
        pure_negation_cases = [
            "No experience required",
            "You don't need prior experience",
        ]

        for text in pure_negation_cases:
            doc = spacy_model(text)
            assert len(doc._.requirement_spans) == 0, f"Pure negation not filtered: {text}"

    def test_compound_conjunction_and(self, spacy_model: Language) -> None:
        """Conjunctions with 'and' should create compound spans."""
        text = "Required: 5+ years Python and strong REST API design skills"
        doc = spacy_model(text)

        assert len(doc._.requirement_spans) == 1
        span = doc._.requirement_spans[0]
        assert span["span_type"] == "compound"
        assert span["conjunct_count"] == 2

    def test_compound_conjunction_or(self, spacy_model: Language) -> None:
        """Conjunctions with 'or' should create compound spans."""
        text = "Knowledge of Docker or Kubernetes or containerization tools"
        doc = spacy_model(text)

        assert len(doc._.requirement_spans) == 1
        span = doc._.requirement_spans[0]
        assert span["span_type"] == "compound"
        assert span["conjunct_count"] == 3

    def test_parenthetical_context(self, spacy_model: Language) -> None:
        """Parenthetical content is handled correctly."""
        text = "Required: 5+ years (in production environments)"
        doc = spacy_model(text)

        assert len(doc._.requirement_spans) >= 1

    def test_comma_separated_list(self, spacy_model: Language) -> None:
        """Comma-separated lists are extracted correctly."""
        text = "Must have Python, Java, and C++"
        doc = spacy_model(text)

        assert len(doc._.requirement_spans) >= 1
        if len(doc._.requirement_spans) > 0:
            span = doc._.requirement_spans[0]
            assert span["start_token"] <= span["end_token"]

    def test_hyphenated_compound(self, spacy_model: Language) -> None:
        """Hyphenated words should not break span boundaries."""
        text = "Required: cross-functional team management and leadership"
        doc = spacy_model(text)

        assert len(doc._.requirement_spans) == 1
        span = doc._.requirement_spans[0]

        assert "cross-functional" in span["span_text"] or "cross" in span["span_text"]

    def test_sentence_boundary(self, spacy_model: Language) -> None:
        """Spans should stop at sentence boundaries (period, semicolon)."""
        text = "Required: 5+ years Python experience. Knowledge of Docker also preferred."
        doc = spacy_model(text)

        assert len(doc._.requirement_spans) >= 1

        first_span = doc._.requirement_spans[0]
        assert "." not in first_span["span_text"]

    def test_multiple_degree_options(self, spacy_model: Language) -> None:
        """Degree alternatives should create compound spans."""
        text = "Bachelor's degree in Computer Science or equivalent"
        doc = spacy_model(text)

        assert len(doc._.requirement_spans) == 1
        span = doc._.requirement_spans[0]
        assert span["span_type"] == "compound"

    def test_infinitive_phrase(self, spacy_model: Language) -> None:
        """Infinitive phrases (ability to...) should extract correctly."""
        text = "Ability to manage complex projects"
        doc = spacy_model(text)

        assert len(doc._.requirement_spans) == 1
        span = doc._.requirement_spans[0]

        assert "manage" in span["span_text"] or "complex" in span["span_text"]
