"""Tests for TechnologyProcessor confidence threshold gating (Issue #348).

Verifies confidence-aware gating logic added to TechnologyProcessor:
- Single-type (SKILLS-only or KNOWLEDGE-only) classification above threshold extracts.
- When both SKILLS and KNOWLEDGE are present in all_types, the higher-confidence
  type wins and gates extraction.
- Both types below threshold skips extraction.
- Missing/empty all_types falls back to labels-only check (no regression).

Run with:
    uv run pytest tests/poc/tweak/spacy_pipeline/test_technology_processor.py -v
"""

from typing import Any

import pytest
from spacy.tokens import Doc

from src.poc.tweak.markdown_section_classifier import SectionClassification, SectionType, TypeClassification
from src.poc.tweak.multi_line_paragraph import MarkdownSection

# Import to trigger factory registration
from src.poc.tweak.spacy_pipeline import TechnologyProcessor, registry  # noqa: F401

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def spacy_module():
    """Import spacy (skip test if not available)."""
    try:
        import spacy

        return spacy
    except ImportError:
        pytest.skip("spaCy not installed")


@pytest.fixture(scope="session")
def nlp(spacy_module: Any) -> Any:
    """Load spaCy model with entity_ruler + technology patterns registered."""
    try:
        loaded = spacy_module.load("en_core_web_md")
    except OSError:
        pytest.skip("en_core_web_md model not installed")

    # Ensure classified_sections/sections/technologies extensions are registered
    from src.poc.tweak.multi_line_paragraph import MarkdownSpanRuler

    MarkdownSpanRuler(loaded)

    if not Doc.has_extension("classified_sections"):
        Doc.set_extension("classified_sections", default=[])

    # Register entity_ruler with tech patterns (D5 decision, see batch_processor.py)
    if "entity_ruler" not in loaded.pipe_names:
        loaded.add_pipe("entity_ruler", before="ner")
    ruler = loaded.get_pipe("entity_ruler")
    tech_patterns = TechnologyProcessor.generate_tech_patterns()
    ruler.add_patterns(tech_patterns)

    return loaded


def _make_section(title: str = "Skills", content: str = "Experience with Python and Docker.") -> MarkdownSection:
    """Build a simple MarkdownSection for tests."""
    return MarkdownSection(
        title=title,
        content=content,
        level=2,
        start_line=0,
        end_line=0,
        word_count=len(content.split()),
        line_count=1,
        has_list=False,
    )


def _classification(all_types: tuple = (), labels: frozenset = frozenset()) -> SectionClassification:
    """Build a SectionClassification with given all_types/labels."""
    return SectionClassification(all_types=all_types, labels=labels, is_skip=False, keyword_matches=())


# ============================================================================
# Tests
# ============================================================================


class TestTechnologyProcessorConfidenceGate:
    """Test confidence-aware SKILLS/KNOWLEDGE gating (Issue #348)."""

    def test_skills_only_above_threshold_extracts(self, nlp) -> None:
        """SKILLS-only classification at 0.85 confidence extracts technologies."""
        processor = TechnologyProcessor(nlp, "technology_processor")

        doc = nlp("Test document")
        section = _make_section()
        classification = _classification(
            all_types=(TypeClassification(SectionType.SKILLS, 0.85),),
            labels=frozenset({SectionType.SKILLS}),
        )
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        assert len(doc._.technologies) > 0

    def test_knowledge_only_above_threshold_extracts(self, nlp) -> None:
        """KNOWLEDGE-only classification at 0.85 confidence extracts technologies."""
        processor = TechnologyProcessor(nlp, "technology_processor")

        doc = nlp("Test document")
        section = _make_section()
        classification = _classification(
            all_types=(TypeClassification(SectionType.KNOWLEDGE, 0.85),),
            labels=frozenset({SectionType.KNOWLEDGE}),
        )
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        assert len(doc._.technologies) > 0

    def test_both_present_higher_confidence_wins_and_logs(self, nlp, caplog) -> None:
        """Both SKILLS (0.60) and KNOWLEDGE (0.90) present: KNOWLEDGE wins, clears threshold."""
        processor = TechnologyProcessor(nlp, "technology_processor")

        doc = nlp("Test document")
        section = _make_section()
        classification = _classification(
            all_types=(
                TypeClassification(SectionType.KNOWLEDGE, 0.90),
                TypeClassification(SectionType.SKILLS, 0.60),
            ),
            labels=frozenset({SectionType.SKILLS, SectionType.KNOWLEDGE}),
        )
        doc._.classified_sections = [(section, classification)]

        with caplog.at_level("INFO"):
            doc = processor(doc)

        assert len(doc._.technologies) > 0
        assert any("knowledge" in message.lower() for message in caplog.messages)

    def test_both_below_threshold_skips(self, nlp) -> None:
        """Both SKILLS (0.40) and KNOWLEDGE (0.50) below 0.70 threshold: no extraction."""
        processor = TechnologyProcessor(nlp, "technology_processor")

        doc = nlp("Test document")
        section = _make_section()
        classification = _classification(
            all_types=(
                TypeClassification(SectionType.KNOWLEDGE, 0.50),
                TypeClassification(SectionType.SKILLS, 0.40),
            ),
            labels=frozenset({SectionType.SKILLS, SectionType.KNOWLEDGE}),
        )
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        assert doc._.technologies == []

    def test_all_types_empty_falls_back_to_labels_only(self, nlp) -> None:
        """Empty all_types with SKILLS in labels: falls back to labels-only check (no regression)."""
        processor = TechnologyProcessor(nlp, "technology_processor")

        doc = nlp("Test document")
        section = _make_section()
        classification = _classification(
            all_types=(),
            labels=frozenset({SectionType.SKILLS}),
        )
        doc._.classified_sections = [(section, classification)]

        doc = processor(doc)

        assert len(doc._.technologies) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
