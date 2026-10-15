"""Integration tests for SectionClassifierComponent spaCy pipeline integration.

Tests verify Phase C of Issue #293: spaCy component registration, pipeline
execution, doc extension population, and end-to-end section classification.

Coverage:
- Component factory registration and creation
- Component properties and naming
- Pipeline integration and chaining
- doc._.sections and doc._.classified_sections extensions
- Edge cases (None sections, empty pipeline, fixtures)
- End-to-end workflow from Doc to classifications

Run with:
    uv run pytest tests/poc/tweak/spacy_pipeline/test_section_classifier_integration.py -v
    uv run pytest tests/poc/tweak/spacy_pipeline/ -v --cov=src/poc/tweak
"""

import json
from pathlib import Path
from typing import Any, List, Tuple

import pytest

from src.parsers.html_to_markdown import html_to_markdown
from src.poc.tweak.markdown_section_classifier import SectionClassifier, SectionType
from src.poc.tweak.multi_line_paragraph import MarkdownSection, MarkdownSpanRuler

# Import to trigger factory registration
from src.poc.tweak.spacy_pipeline import SectionClassifierComponent, registry  # noqa: F401
from src.poc.tweak.spacy_pipeline.heading_promoter import HeadingPromoter

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
        # Ensure extensions are registered
        from src.poc.tweak.multi_line_paragraph import MarkdownSpanRuler

        MarkdownSpanRuler(nlp)  # Initializes Doc extensions
        return nlp
    except OSError:
        pytest.skip("en_core_web_md model not installed")


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to fixtures directory."""
    return Path(__file__).parent.parent.parent / "fixtures"


@pytest.fixture
def simple_sections() -> List[MarkdownSection]:
    """Load markdown_sections_simple.json as MarkdownSection objects."""
    fixtures_dir = Path(__file__).parent.parent.parent / "fixtures"
    fixture_file = fixtures_dir / "markdown_sections_simple.json"

    with open(fixture_file) as f:
        data = json.load(f)

    sections = []
    for section_data in data["sections"]:
        section = MarkdownSection(
            title=section_data.get("title"),
            content=section_data.get("content", ""),
            level=section_data.get("level", -2),
            start_line=section_data.get("start_line", 0),
            end_line=section_data.get("end_line", 0),
            word_count=section_data.get("word_count", 0),
            line_count=section_data.get("line_count", 0),
            has_list=section_data.get("has_list", False),
            metadata=section_data.get("metadata", {}),
        )
        sections.append(section)

    return sections


@pytest.fixture
def complex_sections() -> List[MarkdownSection]:
    """Load markdown_sections_complex.json as MarkdownSection objects."""
    fixtures_dir = Path(__file__).parent.parent.parent / "fixtures"
    fixture_file = fixtures_dir / "markdown_sections_complex.json"

    with open(fixture_file) as f:
        data = json.load(f)

    sections = []
    for section_data in data["sections"]:
        section = MarkdownSection(
            title=section_data.get("title"),
            content=section_data.get("content", ""),
            level=section_data.get("level", -2),
            start_line=section_data.get("start_line", 0),
            end_line=section_data.get("end_line", 0),
            word_count=section_data.get("word_count", 0),
            line_count=section_data.get("line_count", 0),
            has_list=section_data.get("has_list", False),
            metadata=section_data.get("metadata", {}),
        )
        sections.append(section)

    return sections


@pytest.fixture
def edge_case_sections() -> List[MarkdownSection]:
    """Load markdown_sections_edge_cases.json as MarkdownSection objects."""
    fixtures_dir = Path(__file__).parent.parent.parent / "fixtures"
    fixture_file = fixtures_dir / "markdown_sections_edge_cases.json"

    with open(fixture_file) as f:
        data = json.load(f)

    sections = []
    for section_data in data["sections"]:
        section = MarkdownSection(
            title=section_data.get("title"),
            content=section_data.get("content", ""),
            level=section_data.get("level", -2),
            start_line=section_data.get("start_line", 0),
            end_line=section_data.get("end_line", 0),
            word_count=section_data.get("word_count", 0),
            line_count=section_data.get("line_count", 0),
            has_list=section_data.get("has_list", False),
            metadata=section_data.get("metadata", {}),
        )
        sections.append(section)

    return sections


# ============================================================================
# Phase 1: Factory Registration Tests
# ============================================================================


class TestSectionClassifierFactoryRegistration:
    """Test spaCy factory registration of SectionClassifierComponent."""

    def test_component_can_be_created_via_factory(self, nlp) -> None:
        """Verify component can be created via nlp.create_pipe()."""
        classifier = nlp.create_pipe("section_classifier")
        assert isinstance(classifier, SectionClassifierComponent)

    def test_component_can_be_added_to_pipeline(self, nlp) -> None:
        """Verify component can be added to pipeline."""
        nlp.add_pipe("section_classifier", last=True)
        assert "section_classifier" in nlp.pipe_names

    def test_component_appears_in_pipeline_names(self, nlp) -> None:
        """Verify component appears in nlp.pipe_names after addition."""
        nlp.add_pipe("section_classifier", last=True)
        assert nlp.pipe_names[-1] == "section_classifier"


# ============================================================================
# Phase 2: Component Properties and Naming
# ============================================================================


class TestSectionClassifierComponentProperties:
    """Test component properties and behavior."""

    def test_component_name_property(self, nlp) -> None:
        """Verify component.name returns correct identifier."""
        classifier = nlp.create_pipe("section_classifier")
        assert classifier.name == "section_classifier"

    def test_component_has_classifier_instance(self, nlp) -> None:
        """Verify component has internal SectionClassifier instance."""
        classifier = nlp.create_pipe("section_classifier")
        assert hasattr(classifier, "classifier")

        assert isinstance(classifier.classifier, SectionClassifier)

    def test_component_raises_on_empty_name(self, nlp) -> None:
        """Verify component raises ValueError for empty/None name."""
        with pytest.raises(ValueError, match="Component name cannot be None or empty"):
            SectionClassifierComponent(nlp, "")

    def test_component_raises_on_none_name(self, nlp) -> None:
        """Verify component raises ValueError for None name."""
        with pytest.raises(ValueError, match="Component name cannot be None or empty"):
            SectionClassifierComponent(nlp, None)  # type: ignore


# ============================================================================
# Phase 3: Pipeline Execution and Doc Extension
# ============================================================================


class TestSectionClassifierDocExtensions:
    """Test doc._ extensions and pipeline execution."""

    def test_doc_classified_sections_extension_created(self, nlp) -> None:
        """Verify doc._.classified_sections extension is created."""
        from spacy.tokens import Doc

        nlp.create_pipe("section_classifier")
        assert Doc.has_extension("classified_sections")

    def test_doc_classified_sections_populated_after_processing(self, nlp) -> None:
        """Verify doc._.classified_sections is populated after processing."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test document")

        # Pre-populate sections
        section = MarkdownSection(
            title="Requirements",
            content="5+ years experience",
            level=2,
            start_line=0,
            end_line=0,
            word_count=3,
            line_count=1,
            has_list=False,
        )
        doc._.sections = [section]

        # Process
        doc = classifier(doc)

        # Verify classified_sections is populated
        assert len(doc._.classified_sections) == 1
        classified_section, classification = doc._.classified_sections[0]
        assert classified_section.title == "Requirements"
        assert classification.all_types[0].section_type == SectionType.QUALIFICATIONS

    def test_doc_classified_sections_empty_when_no_sections(self, nlp) -> None:
        """Verify doc._.classified_sections is empty when no sections."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test document")
        doc._.sections = []

        doc = classifier(doc)

        assert doc._.classified_sections == []

    def test_doc_classified_sections_handles_none_sections(self, nlp) -> None:
        """Verify component gracefully handles doc._.sections = None."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test document")
        doc._.sections = None

        doc = classifier(doc)

        assert doc._.classified_sections == []


# ============================================================================
# Phase 4: Fixture-Based Integration Tests
# ============================================================================


class TestSectionClassifierWithFixtures:
    """Test component with fixture data."""

    def test_classify_simple_fixture_sections(self, nlp, simple_sections) -> None:
        """Verify classification of simple fixture sections."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test")
        doc._.sections = simple_sections
        doc = classifier(doc)

        assert len(doc._.classified_sections) == 3

        # First section: "Introduction" -> DESCRIPTION
        _, clf1 = doc._.classified_sections[0]
        assert clf1.all_types[0].section_type == SectionType.DESCRIPTION

        # Second section: "Requirements" -> QUALIFICATIONS
        _, clf2 = doc._.classified_sections[1]
        assert clf2.all_types[0].section_type == SectionType.QUALIFICATIONS

        # Third section: "Details" -> OTHER (no keyword match)
        _, clf3 = doc._.classified_sections[2]
        assert clf3.all_types[0].section_type == SectionType.OTHER

    def test_classify_complex_fixture_sections(self, nlp, complex_sections) -> None:
        """Verify classification of complex fixture sections."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test")
        doc._.sections = complex_sections
        doc = classifier(doc)

        assert len(doc._.classified_sections) == 6

        # Find classifications by title
        classifications = {section.title: clf for section, clf in doc._.classified_sections}

        # "Senior Python Developer" -> OTHER (no keywords matched in title)
        assert classifications["Senior Python Developer"].all_types[0].section_type == SectionType.OTHER

        # "About Us" -> DESCRIPTION (company information/description, not job requirements)
        assert classifications["About Us"].all_types[0].section_type == SectionType.DESCRIPTION

        # "Qualifications" -> QUALIFICATIONS
        assert classifications["Qualifications"].all_types[0].section_type == SectionType.QUALIFICATIONS

        # "Preferred Skills" -> SKILLS
        assert classifications["Preferred Skills"].all_types[0].section_type == SectionType.SKILLS

        # "Benefits" -> SKIP
        assert classifications["Benefits"].all_types[0].section_type == SectionType.SKIP

        # "How to Apply" -> SKIP (contains "apply" in skip keywords)
        assert classifications["How to Apply"].all_types[0].section_type == SectionType.SKIP

    def test_classify_edge_case_fixture_sections(self, nlp, edge_case_sections) -> None:
        """Verify classification of edge case fixture sections."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test")
        doc._.sections = edge_case_sections
        doc = classifier(doc)

        # Should have classified all edge case sections without errors
        assert len(doc._.classified_sections) == len(edge_case_sections)


# ============================================================================
# Phase 5: Pipeline Integration Tests
# ============================================================================


class TestSectionClassifierPipelineIntegration:
    """Test component in full spaCy pipeline."""

    def test_component_works_in_pipeline_chain(self, nlp) -> None:
        """Verify component can be chained in pipeline."""
        # Add multiple components
        nlp.add_pipe("section_classifier", last=True)

        doc = nlp("Test document")
        section = MarkdownSection(
            title="Skills",
            content="Python, Java",
            level=2,
            start_line=0,
            end_line=0,
            word_count=2,
            line_count=1,
            has_list=False,
        )
        doc._.sections = [section]

        # Pipeline should process without error
        doc = nlp("Test document")
        doc._.sections = [section]

        # Manually get component and process
        classifier = nlp.get_pipe("section_classifier")
        doc = classifier(doc)

        assert len(doc._.classified_sections) > 0

    def test_component_idempotent(self, nlp) -> None:
        """Verify multiple passes produce same results."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Technical Skills",
            content="Python",
            level=2,
            start_line=0,
            end_line=0,
            word_count=1,
            line_count=1,
            has_list=False,
        )
        doc._.sections = [section]

        # Process twice
        doc = classifier(doc)
        result1 = doc._.classified_sections

        doc = classifier(doc)
        result2 = doc._.classified_sections

        # Results should be identical
        assert len(result1) == len(result2)
        for (s1, c1), (s2, c2) in zip(result1, result2, strict=False):
            assert s1.title == s2.title
            assert c1.all_types[0].section_type == c2.all_types[0].section_type
            assert c1.all_types[0].confidence == c2.all_types[0].confidence


# ============================================================================
# Phase 6: End-to-End Workflow Tests
# ============================================================================


class TestSectionClassifierEndToEnd:
    """Test end-to-end workflow from Doc to classifications."""

    def test_full_workflow_single_section(self, nlp) -> None:
        """Test complete workflow with single section."""
        classifier = nlp.create_pipe("section_classifier")

        # Create doc
        doc = nlp("Job description document")

        # Create and set sections
        section = MarkdownSection(
            title="Requirements",
            content="5+ years Python experience",
            level=2,
            start_line=0,
            end_line=0,
            word_count=4,
            line_count=1,
            has_list=False,
        )
        doc._.sections = [section]

        # Process
        doc = classifier(doc)

        # Verify result
        assert len(doc._.classified_sections) == 1
        section_out, classification = doc._.classified_sections[0]

        assert section_out.title == "Requirements"
        assert classification.all_types[0].section_type == SectionType.QUALIFICATIONS
        assert "requirement" in classification.all_types[0].matched_keywords
        assert classification.all_types[0].confidence > 0.5
        assert classification.is_skip is False

    def test_full_workflow_multiple_sections(self, nlp) -> None:
        """Test complete workflow with multiple sections."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test")

        sections = [
            MarkdownSection(
                title="Technical Skills",
                content="Python, Java",
                level=2,
                start_line=0,
                end_line=0,
                word_count=2,
                line_count=1,
                has_list=False,
            ),
            MarkdownSection(
                title="Responsibilities",
                content="Lead projects",
                level=2,
                start_line=1,
                end_line=1,
                word_count=2,
                line_count=1,
                has_list=False,
            ),
            MarkdownSection(
                title="Benefits",
                content="Competitive salary",
                level=2,
                start_line=2,
                end_line=2,
                word_count=2,
                line_count=1,
                has_list=False,
            ),
        ]
        doc._.sections = sections

        doc = classifier(doc)

        assert len(doc._.classified_sections) == 3

        types = [clf.all_types[0].section_type for _, clf in doc._.classified_sections]
        assert types[0] == SectionType.SKILLS
        assert types[1] == SectionType.RESPONSIBILITIES
        assert types[2] == SectionType.SKIP


# ============================================================================
# Phase 7: Return Value and Type Tests
# ============================================================================


class TestSectionClassifierReturnValues:
    """Test return values and types."""

    def test_call_returns_doc(self, nlp) -> None:
        """Verify __call__ returns Doc object."""
        classifier = nlp.create_pipe("section_classifier")
        doc = nlp("Test")
        doc._.sections = []

        result = classifier(doc)

        from spacy.tokens import Doc

        assert isinstance(result, Doc)

    def test_classified_sections_is_list_of_tuples(self, nlp) -> None:
        """Verify classified_sections contains (section, classification) tuples."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Skills",
            content="Python",
            level=2,
            start_line=0,
            end_line=0,
            word_count=1,
            line_count=1,
            has_list=False,
        )
        doc._.sections = [section]

        doc = classifier(doc)

        assert isinstance(doc._.classified_sections, list)
        for item in doc._.classified_sections:
            assert isinstance(item, tuple)
            assert len(item) == 2
            section_out, classification = item
            assert isinstance(section_out, MarkdownSection)
            from src.poc.tweak.markdown_section_classifier import SectionClassification

            assert isinstance(classification, SectionClassification)


# ============================================================================
# Phase 8: Error Handling Tests
# ============================================================================


class TestSectionClassifierErrorHandling:
    """Test error handling and edge cases."""

    def test_component_handles_malformed_sections(self, nlp) -> None:
        """Verify component handles sections with missing fields gracefully."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test")
        # Create section with minimal data
        section = MarkdownSection(
            title="Test",
            content="",
            level=-2,
            start_line=0,
            end_line=0,
            word_count=0,
            line_count=0,
            has_list=False,
        )
        doc._.sections = [section]

        # Should process without error
        doc = classifier(doc)
        assert len(doc._.classified_sections) == 1

    def test_component_handles_unicode_sections(self, nlp) -> None:
        """Verify component handles unicode content."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Français - 中文",
            content="International content with émojis 🎉",
            level=2,
            start_line=0,
            end_line=0,
            word_count=4,
            line_count=1,
            has_list=False,
        )
        doc._.sections = [section]

        # Should process without error
        doc = classifier(doc)
        assert len(doc._.classified_sections) == 1

    def test_component_handles_very_long_content(self, nlp) -> None:
        """Verify component handles very long sections."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test")
        long_content = "This is a long section. " * 1000  # ~4000 words
        section = MarkdownSection(
            title="Long Section",
            content=long_content,
            level=2,
            start_line=0,
            end_line=100,
            word_count=4000,
            line_count=100,
            has_list=False,
        )
        doc._.sections = [section]

        # Should process without error
        doc = classifier(doc)
        assert len(doc._.classified_sections) == 1


# ============================================================================
# Phase 9: Consistency Tests
# ============================================================================


class TestSectionClassifierConsistency:
    """Test consistency and reproducibility."""

    def test_same_input_produces_same_classification(self, nlp) -> None:
        """Verify same input always produces same classification."""
        classifier = nlp.create_pipe("section_classifier")

        doc = nlp("Test")
        section = MarkdownSection(
            title="Technical Skills",
            content="Python, Java",
            level=2,
            start_line=0,
            end_line=0,
            word_count=2,
            line_count=1,
            has_list=False,
        )

        # Process multiple times
        results = []
        for _ in range(3):
            doc._.sections = [section]
            doc = classifier(doc)
            _, clf = doc._.classified_sections[0]
            results.append(
                (clf.all_types[0].section_type, clf.all_types[0].confidence, clf.all_types[0].matched_keywords)
            )

        # All results should be identical
        assert results[0] == results[1] == results[2]


# ============================================================================
# Phase 10: HeadingPromoter -> SectionClassifier EEO Integration (Issue #520)
# ============================================================================


class TestHeadingPromoterSectionClassifierEEOIntegration:
    """EEO isolation (Issue #520) carried through MarkdownSpanRuler and SectionClassifier.

    All text is synthetic and hand-written. Covers an end-to-end WorkSource-shaped document,
    the #482 first-sentence window boundary (heading_promoter.py `first_sentence[:200]`; the
    #482 outcome is not yet decided, so these cases pin current behaviour only), a heading
    glued to its body, and a local-only structural check against gitignored data/work.
    """

    @pytest.fixture
    def blank_nlp(self) -> Any:
        """Blank English pipeline: MarkdownSpanRuler.parse needs a tokenizer, not en_core_web_md."""
        spacy = pytest.importorskip("spacy")
        return spacy.blank("en")

    @staticmethod
    def _classify_sections(text: str, nlp: Any) -> List[Tuple[MarkdownSection, Any]]:
        """Run HeadingPromoter, split with MarkdownSpanRuler, classify each section."""
        promoted = HeadingPromoter().process(text)
        sections = MarkdownSpanRuler(nlp).parse(promoted)
        classifier = SectionClassifier()
        return [(section, classifier.classify(section)) for section in sections]

    def test_end_to_end_trailing_eeo_isolated_from_preceding_section(self, blank_nlp: Any) -> None:
        """Trailing EEO paragraph becomes its own SKIP section; preceding section is unchanged."""
        text = (
            "Job Description\n\n"
            "Build and operate internal developer platforms for a regional logistics network.\n\n"
            "Technical Skills\n\n"
            "* Python\n"
            "* Terraform\n\n"
            "Northwind Logistics is an equal opportunity employer and welcomes applicants of all backgrounds.\n\n"
            "Please contact HR with any questions."
        )
        pairs = self._classify_sections(text, blank_nlp)
        assert [section.title for section, _ in pairs] == [
            "Job Description",
            "Technical Skills",
            "Equal Opportunity Employer",
        ]

        skills_section, skills_clf = pairs[1]
        assert skills_section.content.strip() == "## Technical Skills\n\n* Python\n* Terraform"
        assert skills_clf.all_types[0].section_type is SectionType.SKILLS
        assert skills_clf.is_skip is False

        eeo_section, eeo_clf = pairs[2]
        assert eeo_section.content.strip() == (
            "## Equal Opportunity Employer\n\n"
            "Northwind Logistics is an equal opportunity employer and welcomes applicants of all backgrounds.\n\n"
            "Please contact HR with any questions."
        )
        assert eeo_clf.is_skip is True

    @pytest.mark.parametrize(
        ("offset", "expect_isolated"),
        [
            # Added control (not requested): trigger ends at index 199, the last index inside [:200].
            (174, True),
            # Trigger starts at 190: only "equal oppo" falls inside first_sentence[:200].
            (190, False),
            # Only "e" falls inside first_sentence[:200].
            (199, False),
            # Trigger starts beyond the 200-char window.
            (210, False),
        ],
    )
    def test_trigger_window_boundary_current_behaviour(self, offset: int, expect_isolated: bool) -> None:
        """EEO trigger must end within the first 200 chars of the first sentence to isolate.

        The #482 outcome (widen, keep or move the window) is not yet decided; this pins current
        behaviour only and should be revisited when #482 is decided.
        """
        body = "x" * offset + "equal opportunity employer for all applicants."
        text = f"{body}\n\nPlease contact HR."
        result = HeadingPromoter().process(text)
        if expect_isolated:
            assert result == f"## Equal Opportunity Employer\n\n{text}"
        else:
            assert result == text

    def test_heading_glued_to_eeo_body_isolated_current_behaviour(self, blank_nlp: Any) -> None:
        """Heading glued to body: the EEO sentence isolates as a whole line, glued text kept verbatim.

        Probe-by-reading: the trigger "equal employment opportunity" matches the casefolded
        substring of "Equal Employment OpportunityBlue", so the paragraph is isolated. Not xfail.
        """
        glued = "Equal Employment OpportunityBlue Origin is proud to be an equal opportunity employer."
        text = (
            "Job Description\n\n"
            "Maintain build tooling for the warehouse team.\n\n"
            f"{glued}\n\n"
            "Please contact HR with any questions."
        )
        pairs = self._classify_sections(text, blank_nlp)
        assert HeadingPromoter().process(text) == (
            "## Job Description\n\n"
            "Maintain build tooling for the warehouse team.\n\n"
            "## Equal Opportunity Employer\n\n"
            f"{glued}\n\n"
            "Please contact HR with any questions."
        )
        eeo_section, eeo_clf = pairs[-1]
        assert eeo_section.title == "Equal Opportunity Employer"
        assert glued in eeo_section.content
        assert eeo_clf.is_skip is True

    def test_local_my_details_eeo_section_structure(self, blank_nlp: Any) -> None:
        """Local-only structural check against gitignored data/work/my_details.json.

        Skipped when the file is absent or unreadable. Asserts structure only: some section is
        SKIP and mentions equal opportunity/employment. No job text is asserted or printed.
        """
        repo_root = Path(__file__).resolve().parents[4]
        details_path = repo_root / "data" / "work" / "my_details.json"
        if not details_path.is_file():
            pytest.skip("data/work/my_details.json not present (local-only, gitignored)")
        try:
            jobs = json.loads(details_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pytest.skip("data/work/my_details.json unreadable or not valid JSON")
        if not isinstance(jobs, list):
            pytest.skip("data/work/my_details.json is not a JSON list")

        eeo_markers = ("equal opportunity", "equal employment")
        description = next(
            (
                job["description"]
                for job in jobs
                if isinstance(job, dict)
                and isinstance(job.get("description"), str)
                and any(marker in job["description"].casefold() for marker in eeo_markers)
            ),
            None,
        )
        if description is None:
            pytest.skip("no local description contains an EEO marker")

        # clean_html strips legal boilerplate (incl. EEO) before the promoter ever runs, so use the
        # raw conversion to exercise promoter -> classifier on real EEO text.
        text = html_to_markdown(description) or ""
        pairs = self._classify_sections(text, blank_nlp)
        skipped = [section for section, clf in pairs if clf.is_skip]
        assert any(any(marker in section.content.casefold() for marker in eeo_markers) for section in skipped)


# ============================================================================
# Run with: uv run pytest tests/poc/tweak/spacy_pipeline/test_section_classifier_integration.py -v
# ============================================================================
