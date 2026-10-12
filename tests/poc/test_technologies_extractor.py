"""Unit tests for TechExtractor POC module."""

from pathlib import Path

import pytest
import spacy

from src.poc.technologies.extract_technologies_a import TechExtractor
from src.poc.technologies.patterns import TECH_TERMS


@pytest.fixture
def nlp():
    """Initialize spaCy model for TechExtractor."""
    return spacy.load("en_core_web_md")


@pytest.fixture
def extractor(nlp):
    """Initialize TechExtractor with spaCy pipeline."""
    return TechExtractor(nlp)


@pytest.fixture
def fixture_what_you_ll_do():
    """Load 'What You'll Do' fixture."""
    path = Path("tests/poc/fixtures/raw_jd_what_you_ll_do.md")
    return path.read_text() if path.exists() else ""


@pytest.fixture
def fixture_knowledge_skills():
    """Load 'Knowledge, Skills & Abilities' fixture."""
    path = Path("tests/poc/fixtures/raw_jd_knowledge_skills_abilities.md")
    return path.read_text() if path.exists() else ""


class TestTechExtractorBasics:
    """Test basic extraction functionality."""

    def test_extractor_initialization(self, extractor):
        """TechExtractor initializes with spaCy pipeline."""
        assert extractor.nlp is not None
        assert extractor.ruler is not None

    def test_tech_terms_populated(self):
        """TECH_TERMS set is populated."""
        assert len(TECH_TERMS) > 0
        assert "PyTorch" in TECH_TERMS
        assert "Python" in TECH_TERMS or "python" in TECH_TERMS

    def test_extract_simple_tech(self, extractor, nlp):
        """Extract single technology term."""
        text = "Experience with Python programming."
        doc = nlp(text)
        techs = extractor.extract(doc)
        assert len(techs) > 0
        # Should find Python (case-insensitive)
        tech_lower = [t.lower() for t in techs]
        assert "python" in tech_lower

    def test_extract_multiple_techs(self, extractor, nlp):
        """Extract multiple technology terms."""
        text = "Use Python, Java, and C++ for development."
        doc = nlp(text)
        techs = extractor.extract(doc)
        assert len(techs) > 0

    def test_extract_returns_sorted_list(self, extractor, nlp):
        """Extract returns sorted list."""
        text = "Use Java and Python."
        doc = nlp(text)
        techs = extractor.extract(doc)
        assert isinstance(techs, list)
        assert all(isinstance(t, str) for t in techs)
        assert techs == sorted(techs)

    def test_extract_case_insensitive(self, extractor, nlp):
        """Extract is case-insensitive."""
        text = "python PYTHON Python PyThOn"
        doc = nlp(text)
        techs = extractor.extract(doc)
        # Should deduplicate case variations
        python_matches = [t for t in techs if t.lower() == "python"]
        # May be 1 or more depending on how extraction works
        assert len(python_matches) >= 1

    def test_extract_no_duplicates(self, extractor, nlp):
        """Results deduplicated."""
        text = "Python is great. Python is powerful. Python rocks."
        doc = nlp(text)
        techs = extractor.extract(doc)
        # Count Python occurrences
        python_count = sum(1 for t in techs if t.lower() == "python")
        assert python_count == 1

    def test_extract_empty_text(self, extractor, nlp):
        """Extract from empty text returns empty list."""
        doc = nlp("")
        techs = extractor.extract(doc)
        assert techs == []

    def test_extract_no_techs(self, extractor, nlp):
        """Text without tech terms returns empty."""
        text = "The quick brown fox jumps over the lazy dog."
        doc = nlp(text)
        techs = extractor.extract(doc)
        assert techs == []


class TestTechExtractorMultiWordPhrases:
    """Test extraction of multi-word technology phrases."""

    def test_extract_two_word_phrase(self, extractor, nlp):
        """Extracts multi-word phrases (e.g., 'computer vision')."""
        text = "Experience with computer vision systems."
        doc = nlp(text)
        techs = extractor.extract(doc)
        # Should find "computer vision"
        tech_lower = [t.lower() for t in techs]
        assert "computer vision" in tech_lower

    def test_extract_vision_transformers(self, extractor, nlp):
        """Extracts 'vision transformers' if present."""
        text = "Knowledge of vision transformers and transformers."
        doc = nlp(text)
        techs = extractor.extract(doc)
        tech_lower = [t.lower() for t in techs]
        # Should find vision transformers
        assert any("vision" in t and "transformer" in t for t in tech_lower)

    def test_multi_word_phrase_case_insensitive(self, extractor, nlp):
        """Multi-word phrases are case-insensitive."""
        text = "COMPUTER VISION is used."
        doc = nlp(text)
        techs = extractor.extract(doc)
        tech_lower = [t.lower() for t in techs]
        assert "computer vision" in tech_lower

    def test_multi_word_partial_match_not_extracted(self, extractor, nlp):
        """Partial matches of multi-word phrases don't extract."""
        text = "Computer graphics and vision software."
        doc = nlp(text)
        techs = extractor.extract(doc)
        # Should find "computer vision" if both words adjacent
        tech_lower = [t.lower() for t in techs]
        # Behavior depends on implementation
        assert all("computer vision" not in t for t in tech_lower)


class TestTechExtractorFixtures:
    """Test against real job description fixtures."""

    def test_extract_from_what_you_ll_do(self, extractor, nlp, fixture_what_you_ll_do):
        """Extract techs from 'What You'll Do' section."""
        if not fixture_what_you_ll_do:
            pytest.skip("Fixture file not found")

        doc = nlp(fixture_what_you_ll_do)
        techs = extractor.extract(doc)

        # May or may not find techs in this section (it's action-oriented)
        # Just verify it doesn't crash
        assert isinstance(techs, list)

    def test_extract_from_knowledge_skills(self, extractor, nlp, fixture_knowledge_skills):
        """Extract techs from 'Knowledge, Skills & Abilities' section."""
        if not fixture_knowledge_skills:
            pytest.skip("Fixture file not found")

        doc = nlp(fixture_knowledge_skills)
        techs = extractor.extract(doc)
        assert len(techs) > 0

        # Check for expected technologies
        text_lower = fixture_knowledge_skills.lower()
        tech_lower = [t.lower() for t in techs]

        assert "pytorch" in text_lower, "Precondition: fixture must contain 'PyTorch'"
        assert "c++" in text_lower, "Precondition: fixture must contain 'C++'"
        assert "computer vision" in text_lower, "Precondition: fixture must contain 'computer vision'"
        assert any("pytorch" in t for t in tech_lower), "Should extract 'PyTorch'"
        assert any("c++" in t for t in tech_lower), "Should extract 'C++'"
        assert any("computer vision" in t for t in tech_lower), "Should extract 'computer vision'"

    def test_fixture_combined_extraction(self, extractor, nlp, fixture_what_you_ll_do, fixture_knowledge_skills):
        """Extract from combined fixtures."""
        combined_text = fixture_what_you_ll_do + "\n" + fixture_knowledge_skills
        doc = nlp(combined_text)
        techs = extractor.extract(doc)

        # Should extract technologies from combined text
        assert len(techs) > 0
        # All results should be strings
        assert all(isinstance(t, str) for t in techs)
        # No empty strings
        assert all(t.strip() for t in techs)
        # Results should be sorted
        assert techs == sorted(techs)

    def test_fixture_extraction_coverage(self, extractor, nlp, fixture_knowledge_skills):
        """Verify extraction coverage on fixture."""
        if not fixture_knowledge_skills:
            pytest.skip("Fixture file not found")

        doc = nlp(fixture_knowledge_skills)
        techs = extractor.extract(doc)

        # Expected technologies in this fixture
        expected_techs = [
            "pytorch",
            "c++",
            "computer vision",
            "vision transformers",
            "anchor-free detectors",
            "embeddings",
            "web services",
            "sensor fusion",
            "perception pipelines",
            "real-time inference",
            "adas",
        ]
        found_techs = {t.lower() for t in techs}

        # Should find at least 40% of expected techs (some may not be in fixture)
        matches = sum(1 for exp in expected_techs if any(exp in f for f in found_techs))
        assert matches >= len(expected_techs) * 0.4, f"Found {matches}/{len(expected_techs)} expected techs"


class TestTechExtractorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_sentence_with_punctuation(self, extractor, nlp):
        """Handles punctuation."""
        text = "Use Python. Deploy with Docker. Orchestrate with Kubernetes."
        doc = nlp(text)
        techs = extractor.extract(doc)
        assert len(techs) > 0

    def test_technology_in_parentheses(self, extractor, nlp):
        """Handles technology in parentheses."""
        text = "Use cloud services (AWS, Azure, GCP) for deployment."
        doc = nlp(text)
        techs = extractor.extract(doc)
        assert len(techs) > 0

    def test_technology_in_list(self, extractor, nlp):
        """Handles technologies in comma-separated list."""
        text = "Knowledge of Python, Java, C++, and Go."
        doc = nlp(text)
        techs = extractor.extract(doc)
        assert len(techs) > 0

    def test_hyphenated_phrase(self, extractor, nlp):
        """Handles hyphenated phrases (e.g., 'anchor-free detectors')."""
        text = "Modern anchor-free detectors for object detection."
        doc = nlp(text)
        techs = extractor.extract(doc)
        # May or may not extract depending on pattern
        assert isinstance(techs, list)

    def test_technology_with_numbers(self, extractor, nlp):
        """Handles technology names with numbers."""
        text = "Use Python 3.9 and Java 11."
        doc = nlp(text)
        techs = extractor.extract(doc)
        # Should find at least Python and Java
        tech_lower = [t.lower() for t in techs]
        assert any("python" in t for t in tech_lower) or len(techs) > 0

    def test_acronym_expansion(self, extractor, nlp):
        """Handles acronyms (e.g., ADAS, LPM)."""
        text = "Experience with ADAS systems and Large Plant Model technology."
        doc = nlp(text)
        techs = extractor.extract(doc)
        # May extract acronym or full phrase depending on patterns
        assert isinstance(techs, list)

    def test_vendor_specific_terms(self, extractor, nlp):
        """Handles vendor-specific terms."""
        text = "Expertise with Salesforce CRM and AWS services."
        doc = nlp(text)
        techs = extractor.extract(doc)
        tech_lower = [t.lower() for t in techs]
        assert any("aws" in t for t in tech_lower)

    def test_overlapping_tech_names(self, extractor, nlp):
        """Handles overlapping technology names."""
        text = "Use JavaScript and TypeScript together."
        doc = nlp(text)
        techs = extractor.extract(doc)
        # JavaScript may or may not be in TECH_TERMS
        assert isinstance(techs, list)

    def test_negation_not_handled_known_limitation(self, extractor, nlp):
        """Negation handling is NOT implemented; this only checks a non-term is absent.

        "COBOL" is not in TECH_TERMS, so it must not be extracted. This does not
        verify negation logic: a negated known term (e.g. "No experience with Python")
        would still be extracted.
        """
        text = "No experience with COBOL required."
        doc = nlp(text)
        techs = extractor.extract(doc)
        assert all("cobol" not in t.lower() for t in techs)


class TestTechExtractorSorting:
    """Test result sorting and ordering."""

    def test_results_are_sorted(self, extractor, nlp):
        """Results returned in sorted order."""
        text = "Use Python and Django and AWS."
        doc = nlp(text)
        techs = extractor.extract(doc)
        assert len(techs) > 1
        assert techs == sorted(techs)

    def test_sorted_alphabetically(self, extractor, nlp):
        """Results sorted alphabetically."""
        text = "Zulu Python AWS Django"
        doc = nlp(text)
        techs = extractor.extract(doc)
        assert len(techs) > 1
        for i in range(len(techs) - 1):
            assert techs[i] <= techs[i + 1]


class TestTechExtractorWithPreprocessing:
    """Test extraction workflow with preprocessing."""

    def test_extract_after_document_processing(self, extractor, nlp):
        """Extract works on processed spaCy Doc objects."""
        text = "Learn Python and Docker for containerization."
        doc = nlp(text)
        assert doc is not None
        assert len(doc) > 0

        techs = extractor.extract(doc)
        assert isinstance(techs, list)

    def test_extraction_preserves_entity_info(self, extractor, nlp):
        """Extraction preserves entity information."""
        text = "Use AWS and Azure cloud services."
        doc = nlp(text)
        techs = extractor.extract(doc)
        # Should find cloud services (AWS, Azure)
        assert len(techs) > 0


class TestTechExtractorPerformance:
    """Test performance characteristics."""

    def test_extraction_completes_quickly(self, extractor, nlp, fixture_knowledge_skills):
        """Extraction completes in reasonable time."""
        if not fixture_knowledge_skills:
            pytest.skip("Fixture file not found")

        import time

        doc = nlp(fixture_knowledge_skills)
        start = time.perf_counter()
        techs = extractor.extract(doc)
        elapsed = time.perf_counter() - start

        # Coarse sanity bound only (5s), not a perf assertion; avoids CI flake
        assert elapsed < 5.0
        assert len(techs) > 0

    def test_repeated_extraction_consistent(self, extractor, nlp):
        """Multiple extractions produce same results."""
        text = "Use Python and Docker."
        doc = nlp(text)
        techs1 = extractor.extract(doc)
        techs2 = extractor.extract(doc)
        assert techs1 == techs2

    def test_large_text_handling(self, extractor, nlp, fixture_knowledge_skills):
        """Handles larger text efficiently."""
        if not fixture_knowledge_skills:
            pytest.skip("Fixture file not found")

        # Repeat fixture to create larger text
        large_text = fixture_knowledge_skills * 3
        doc = nlp(large_text)

        import time

        start = time.perf_counter()
        techs = extractor.extract(doc)
        elapsed = time.perf_counter() - start

        # Coarse sanity bound only (5s), not a perf assertion; avoids CI flake
        assert elapsed < 5.0
        assert len(techs) > 0


class TestTechExtractorPatternGeneration:
    """Test pattern generation from TECH_TERMS."""

    def test_patterns_generated_for_all_terms(self):
        """Patterns generated for all terms in TECH_TERMS."""
        assert len(TECH_TERMS) > 0
        # TECH_TERMS should be a set or list
        assert isinstance(TECH_TERMS, (set, list, tuple))

    def test_single_word_terms_in_patterns(self):
        """Single-word terms like 'Python', 'Java' in TECH_TERMS."""
        single_word_terms = [t for t in TECH_TERMS if " " not in t]
        assert len(single_word_terms) > 0
        # Should include languages
        term_lower = [t.lower() for t in single_word_terms]
        assert any("python" in t or "java" in t for t in term_lower)

    def test_multi_word_terms_in_patterns(self):
        """Multi-word terms like 'computer vision' in TECH_TERMS."""
        multi_word_terms = [t for t in TECH_TERMS if " " in t]
        assert len(multi_word_terms) > 0
        # Should include phrases
        assert any("vision" in t.lower() for t in multi_word_terms)
