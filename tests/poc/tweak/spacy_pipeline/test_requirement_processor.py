"""Tests for RequirementProcessor confidence threshold gating (Issue #346).

Verifies min_confidence gating on classification.all_types[0] for QUALIFICATIONS
sections, with backward-compatible fallback to labels-only filtering when
all_types is empty/absent.

Coverage:
- High-confidence QUALIFICATIONS section (all_types[0].confidence >= threshold)
  -> requirements extracted
- Low-confidence QUALIFICATIONS section (all_types[0].confidence < threshold)
  -> extraction skipped
- min_confidence=0 -> extracts everything (regression guard)
- all_types empty/absent -> falls back to labels-only behavior (no regression)

Run with:
    uv run pytest tests/poc/tweak/spacy_pipeline/test_requirement_processor.py -v
"""

import logging
from typing import Any

import pytest

from src.poc.tweak.markdown_section_classifier import SectionClassification, SectionType, TypeClassification
from src.poc.tweak.multi_line_paragraph import MarkdownSection

# Import to trigger factory registration
from src.poc.tweak.spacy_pipeline import RequirementProcessor, registry  # noqa: F401

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def spacy_module():
    """Import spacy (skip test if not available)."""
    try:
        import spacy

        return spacy
    except ImportError:
        pytest.skip("spaCy not installed")


@pytest.fixture
def nlp(spacy_module: Any) -> Any:
    """Load spaCy model (skip if not available)."""
    try:
        nlp = spacy_module.load("en_core_web_md")
        # Ensure classified_sections extension exists (normally registered by
        # SectionClassifierComponent.__init__, not instantiated in these tests).
        from spacy.tokens import Doc

        if not Doc.has_extension("classified_sections"):
            Doc.set_extension("classified_sections", default=[])
        return nlp
    except OSError:
        pytest.skip("en_core_web_md model not installed")


@pytest.fixture
def qualifications_section() -> MarkdownSection:
    """Section title/content that trigger requirement pattern matching."""
    return MarkdownSection(
        title="Requirements",
        content="Must have Python experience.",
        level=2,
        start_line=0,
        end_line=0,
        word_count=4,
        line_count=1,
        has_list=False,
    )


def _make_classification(confidence: float) -> SectionClassification:
    """Build SectionClassification with QUALIFICATIONS as top-ranked all_types entry."""
    return SectionClassification.from_type_classifications(
        [TypeClassification(SectionType.QUALIFICATIONS, confidence, ("required",))],
    )


# ============================================================================
# Confidence Threshold Tests (Issue #346)
# ============================================================================


class TestRequirementProcessorConfidenceThreshold:
    """Test min_confidence gating against classification.all_types[0]."""

    def test_high_confidence_qualifications_extracts_requirements(self, nlp, qualifications_section) -> None:
        """High-confidence QUALIFICATIONS (all_types[0] >= 0.70) extracts requirements."""
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        classification = _make_classification(confidence=0.85)
        doc._.classified_sections = [(qualifications_section, classification)]

        doc = processor(doc)

        assert len(doc._.requirements) >= 1

    def test_low_confidence_qualifications_skips_extraction(self, nlp, qualifications_section, caplog) -> None:
        """Low-confidence QUALIFICATIONS (all_types[0] < 0.70) skips extraction and logs reason."""
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        classification = _make_classification(confidence=0.42)
        doc._.classified_sections = [(qualifications_section, classification)]

        with caplog.at_level(logging.INFO):
            doc = processor(doc)

        assert doc._.requirements == []
        assert "Skipping QUALIFICATIONS extraction: confidence 0.42 < threshold 0.70" in caplog.text

    def test_min_confidence_zero_extracts_everything(self, nlp, qualifications_section) -> None:
        """min_confidence=0 extracts even very low-confidence QUALIFICATIONS sections (regression guard)."""
        processor = RequirementProcessor(nlp, "requirement_processor", min_confidence=0.0)

        doc = nlp("Test")
        classification = _make_classification(confidence=0.01)
        doc._.classified_sections = [(qualifications_section, classification)]

        doc = processor(doc)

        assert len(doc._.requirements) >= 1

    def test_missing_all_types_falls_back_to_labels_only(self, nlp, qualifications_section) -> None:
        """Empty/absent all_types falls back to labels-only filtering (no regression)."""
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        # all_types intentionally empty/absent (default); labels-only behavior applies.
        classification = SectionClassification(all_types=(), labels=frozenset({SectionType.QUALIFICATIONS}))
        doc._.classified_sections = [(qualifications_section, classification)]

        doc = processor(doc)

        assert len(doc._.requirements) >= 1


# ============================================================================
# Multi-Line Sentence Splitting Tests (Issue #353)
# ============================================================================


class TestRequirementProcessorMultiLineSplitting:
    """Test multi-line sentence splitting on newlines and periods."""

    def test_multiline_no_periods_splits_on_newlines(self, nlp) -> None:
        """Multi-line content without periods splits correctly on newlines."""
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Requirements",
            content="Must have Python experience\nMust know Django\nMust have REST API skills",
            level=2,
            start_line=0,
            end_line=0,
            word_count=12,
            line_count=3,
            has_list=False,
        )
        classification = _make_classification(confidence=0.85)
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        # Should extract 3 separate requirements, one per line
        assert len(doc._.requirements) >= 3

    def test_mixed_line_endings_carriage_return_linefeed(self, nlp) -> None:
        """Mixed line endings (\\r\\n and \\n) split correctly."""
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Requirements",
            content="Must have Python\r\nMust know SQL\nMust understand testing",
            level=2,
            start_line=0,
            end_line=0,
            word_count=10,
            line_count=3,
            has_list=False,
        )
        classification = _make_classification(confidence=0.85)
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        # Should extract at least 3 requirements despite mixed line endings
        assert len(doc._.requirements) >= 3

    def test_periods_and_newlines_both_split(self, nlp) -> None:
        """Text with both periods and newlines splits on both."""
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Requirements",
            content="Must have Python. Must know Django\nMust have REST API skills. Must understand testing",
            level=2,
            start_line=0,
            end_line=0,
            word_count=16,
            line_count=2,
            has_list=False,
        )
        classification = _make_classification(confidence=0.85)
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        # Should extract at least 4 requirements: split on both . and \n
        assert len(doc._.requirements) >= 4

    def test_multiline_content_also_splits(self, nlp) -> None:
        """Multi-line section content is split into separate requirement lines.

        Issue #375: section titles are no longer classified, so this test
        exercises line splitting through section content (two trigger-bearing
        lines) instead of the title.
        """
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Qualifications",
            content="Must have experience with Django\nMust know frameworks",
            level=2,
            start_line=0,
            end_line=0,
            word_count=8,
            line_count=2,
            has_list=False,
        )
        classification = _make_classification(confidence=0.85)
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        # Each content line is classified separately
        assert len(doc._.requirements) >= 2


# ============================================================================
# Heading Exclusion Tests (Issue #375)
# ============================================================================


class TestRequirementProcessorHeadingExclusion:
    """Test that markdown headings never become requirements (Issue #375)."""

    def test_heading_title_not_emitted_as_requirement(self, nlp) -> None:
        """Issue #375: a QUALIFICATIONS section title is never emitted as a requirement."""
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Essential Qualifications",
            content="Bachelor degree in Computer Science or equivalent experience.",
            level=2,
            start_line=0,
            end_line=0,
            word_count=10,
            line_count=1,
            has_list=False,
        )
        classification = _make_classification(confidence=0.85)
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        assert all(req["text"] != "Essential Qualifications" for req in doc._.requirements)

    def test_heading_marker_content_line_not_emitted_as_requirement(self, nlp) -> None:
        """Issue #375: a literal '## ' heading line inside content is not emitted as a requirement."""
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Qualifications",
            content=(
                "## Essential Qualifications\n\n"
                "Bachelor degree in Computer Science or equivalent experience.\n"
                "5+ years of software engineering experience."
            ),
            level=2,
            start_line=0,
            end_line=0,
            word_count=18,
            line_count=4,
            has_list=False,
        )
        classification = _make_classification(confidence=0.85)
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        assert all(not req["text"].startswith("#") for req in doc._.requirements)

    def test_real_requirements_still_extracted_alongside_heading(self, nlp) -> None:
        """Issue #375 regression guard: real body sentences are still extracted next to a heading line."""
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Qualifications",
            content=(
                "## Essential Qualifications\n\n"
                "Bachelor degree in Computer Science or equivalent experience.\n"
                "5+ years of software engineering experience."
            ),
            level=2,
            start_line=0,
            end_line=0,
            word_count=18,
            line_count=4,
            has_list=False,
        )
        classification = _make_classification(confidence=0.85)
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        texts = [req["text"] for req in doc._.requirements]
        assert any("Bachelor degree in Computer Science or equivalent experience" in t for t in texts)
        assert any("5+ years of software engineering experience" in t for t in texts)
        assert len(doc._.requirements) >= 2

    def test_non_promoted_native_heading_also_excluded(self, nlp) -> None:
        """Issue #375: a native markdown heading used as a section title is not emitted, even with real content."""
        processor = RequirementProcessor(nlp, "requirement_processor")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Required Skills",
            content="Python experience with Django and REST APIs.",
            level=2,
            start_line=0,
            end_line=0,
            word_count=9,
            line_count=1,
            has_list=False,
        )
        classification = _make_classification(confidence=0.85)
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        assert all(req["text"] != "Required Skills" for req in doc._.requirements)


# ============================================================================
# Run with: uv run pytest tests/poc/tweak/spacy_pipeline/test_requirement_processor.py -v
# ============================================================================
