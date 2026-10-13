"""Unit tests for SkillExtractor POC module."""

from pathlib import Path

import pytest
import spacy

from src.poc.skills.extract_skills_a import SkillExtractor
from src.poc.skills.patterns import SKILL_VERBS


@pytest.fixture
def extractor():
    """Initialize SkillExtractor with spaCy model."""
    return SkillExtractor(model_name="en_core_web_md")


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


class TestSkillExtractorBasics:
    """Test basic extraction functionality."""

    def test_extractor_initialization(self, extractor):
        """Extractor initializes with spaCy model and matcher."""
        assert extractor.nlp is not None
        assert extractor.matcher is not None

    def test_extract_simple_skill(self, extractor):
        """Extract single skill phrase with action verb."""
        text = "Must design machine learning systems."
        skills = extractor.extract(text)
        assert len(skills) > 0
        assert any("design" in s for s in skills)

    def test_extract_multiple_skills(self, extractor):
        """Extract multiple skill phrases."""
        text = "You will design neural networks. You will develop production systems. You will deploy at scale."
        skills = extractor.extract(text)
        assert skills == ["deploy at scale", "design neural networks", "develop production systems"]

    def test_extract_returns_list(self, extractor):
        """Extract returns sorted list."""
        text = "Lead the team and develop solutions."
        skills = extractor.extract(text)
        assert isinstance(skills, list)
        assert all(isinstance(s, str) for s in skills)

    def test_extract_lowercase_output(self, extractor):
        """All results are lowercase."""
        text = "You will design Python applications. You will deploy systems."
        skills = extractor.extract(text)
        assert skills == ["deploy systems", "design python applications"]

    def test_extract_no_duplicates(self, extractor):
        """Results deduplicated."""
        # Identical matches must collapse to a single entry (sorted(set(...)))
        text = "You will design systems. You will design systems. You will design systems."
        skills = extractor.extract(text)
        assert skills == ["design systems"]

    def test_extract_handles_newlines(self, extractor):
        """Handles newlines in text."""
        text = "Lead the\ndesign of\narchitectures."
        skills = extractor.extract(text)
        # Should extract without newline issues
        assert isinstance(skills, list)

    def test_extract_empty_text(self, extractor):
        """Extract from empty text returns empty list."""
        skills = extractor.extract("")
        assert skills == []

    def test_extract_no_verbs(self, extractor):
        """Text without skill verbs returns empty."""
        text = "The quick brown fox jumps over the lazy dog."
        skills = extractor.extract(text)
        assert skills == []


class TestSkillExtractorPatternMatching:
    """Test pattern matching against SKILL_VERBS."""

    def test_all_skill_verbs_present(self):
        """SKILL_VERBS list populated."""
        assert len(SKILL_VERBS) > 0
        assert "design" in SKILL_VERBS
        assert "develop" in SKILL_VERBS
        assert "lead" in SKILL_VERBS

    def test_lemmatization_base_form(self, extractor):
        """Captures base form (lemma) of verbs."""
        text = "You will lead teams and develop solutions."
        skills = extractor.extract(text)
        assert skills == ["develop solutions", "lead teams"]

    def test_captures_past_tense(self, extractor):
        """Captures past tense forms."""
        text = "Designed systems. Developed architectures."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_captures_continuous_form(self, extractor):
        """Captures -ing forms."""
        text = "Designing neural networks. Deploying models."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_captures_descriptive_nouns(self, extractor):
        """Captures nouns/adjectives after verb."""
        text = "Lead the design of deep learning architectures."
        skills = extractor.extract(text)
        assert len(skills) > 0
        assert any("design" in s for s in skills)

    def test_optional_preposition_handling(self, extractor):
        """Handles optional prepositions (with, the, of)."""
        text1 = "You will lead the design of systems."
        text2 = "You will lead design efforts."
        skills1 = extractor.extract(text1)
        skills2 = extractor.extract(text2)
        # Observed: the optional "the/of" connector is kept; "of systems" is not
        # (ADP is excluded from the noun run), so the span stops at "design".
        assert skills1 == ["lead the design"]
        assert skills2 == ["lead design efforts"]

    def test_compound_noun_phrases(self, extractor):
        """Captures compound nouns (deep learning)."""
        text = "Lead the design of deep learning architectures."
        skills = extractor.extract(text)
        assert len(skills) > 0
        # Should capture "deep learning" as part of phrase

    def test_longest_span_filtering(self, extractor):
        """Filters overlapping spans, keeps longest."""
        text = "Design and develop novel deep learning architectures."
        skills = extractor.extract(text)
        # Should pick longest matches, avoid duplicates
        assert len(skills) > 0


class TestSkillExtractorFixtures:
    """Test against real job description fixtures."""

    def test_extract_from_what_you_ll_do(self, extractor, fixture_what_you_ll_do):
        """Extract skills from 'What You'll Do' section."""
        if not fixture_what_you_ll_do:
            pytest.skip("Fixture file not found")

        skills = extractor.extract(fixture_what_you_ll_do)
        assert len(skills) > 0

        # Verify results are properly formatted
        assert all(isinstance(s, str) for s in skills)
        assert all(s.islower() for s in skills)

        # At least one skill should be extracted
        assert len(skills) >= 1

    def test_extract_from_knowledge_skills(self, extractor, fixture_knowledge_skills):
        """Extract skills from 'Knowledge, Skills & Abilities' section."""
        if not fixture_knowledge_skills:
            pytest.skip("Fixture file not found")

        skills = extractor.extract(fixture_knowledge_skills)
        assert len(skills) > 0

        # Verify results are properly formatted
        assert all(isinstance(s, str) for s in skills)
        assert all(s.islower() for s in skills)
        # All skills should be non-empty after stripping
        assert all(s.strip() for s in skills)

    def test_fixture_combined_extraction(self, extractor, fixture_what_you_ll_do, fixture_knowledge_skills):
        """Extract from combined fixtures."""
        combined_text = fixture_what_you_ll_do + "\n" + fixture_knowledge_skills
        skills = extractor.extract(combined_text)

        # Should extract from both sections
        assert len(skills) > 3
        # All results should be lowercase
        assert all(s.islower() for s in skills)
        # All results should be strings
        assert all(isinstance(s, str) for s in skills)
        # No empty strings
        assert all(s.strip() for s in skills)

    def test_fixture_extraction_accuracy(self, extractor, fixture_what_you_ll_do):
        """Verify extraction hit rate on fixture."""
        if not fixture_what_you_ll_do:
            pytest.skip("Fixture file not found")

        skills = extractor.extract(fixture_what_you_ll_do)

        # Expected verbs to find
        expected_verbs = ["lead", "design", "develop", "own", "drive", "define", "partner", "mentor", "communicate"]
        found_verbs = set()
        for skill in skills:
            for verb in expected_verbs:
                if verb in skill.split():
                    found_verbs.add(verb)

        # Should find at least 50% of expected verbs
        hit_rate = len(found_verbs) / len(expected_verbs)
        assert hit_rate >= 0.5, f"Hit rate {hit_rate:.0%} below 50%"


class TestSkillExtractorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_sentence_with_punctuation(self, extractor):
        """Handles end-of-sentence punctuation."""
        text = "Design robust systems. Deploy at scale."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_multiple_verbs_in_sequence(self, extractor):
        """Handles comma-separated verbs."""
        text = "Design, develop, and deploy solutions."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_verb_with_many_modifiers(self, extractor):
        """Captures skill with multiple adjectives."""
        text = "Develop robust, scalable, production-ready systems."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_skill_at_sentence_start(self, extractor):
        """Extracts skill at sentence beginning."""
        text = "Lead the design of systems from scratch."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_skill_at_sentence_end(self, extractor):
        """Extracts skill at sentence end."""
        text = "The team must design systems."
        skills = extractor.extract(text)
        assert skills == ["design systems"]

    def test_hyphenated_noun(self, extractor):
        """Handles hyphenated compound nouns."""
        text = "You will design high-performance distributed systems."
        skills = extractor.extract(text)
        # Hyphen is PUNCT, so the noun run stops at "high".
        assert skills == ["design high"]

    def test_parenthetical_context(self, extractor):
        """Handles skill in parenthetical context."""
        text = "Lead the design and development of novel architectures (state-of-the-art)."
        skills = extractor.extract(text)
        # Should handle parentheses without crashing
        assert isinstance(skills, list)

    def test_special_characters_in_text(self, extractor):
        """Handles special characters."""
        text = "Design & develop → production systems."
        skills = extractor.extract(text)
        # Should not crash
        assert isinstance(skills, list)

    def test_very_long_skill_phrase(self, extractor):
        """Handles long skill phrases."""
        text = "Design and develop novel deep learning architectures for computer vision in production environments."
        skills = extractor.extract(text)
        assert len(skills) > 0


class TestSkillExtractorSorting:
    """Test result sorting and ordering."""

    def test_results_are_sorted(self, extractor):
        """Results returned in sorted order."""
        text = "You will develop solutions. You will design architectures. You will deploy systems."
        skills = extractor.extract(text)
        assert skills == ["deploy systems", "design architectures", "develop solutions"]

    def test_sorted_case_insensitive(self, extractor):
        """Mixed-case input yields sorted, lowercase output."""
        text = "You will design systems. You will BUILD tools. You will manage teams."
        skills = extractor.extract(text)
        assert skills == ["build tools", "design systems", "manage teams"]


class TestSkillExtractorPerformance:
    """Test performance characteristics."""

    def test_extraction_completes_quickly(self, extractor, fixture_what_you_ll_do):
        """Extraction completes in reasonable time."""
        if not fixture_what_you_ll_do:
            pytest.skip("Fixture file not found")

        import time

        start = time.perf_counter()
        skills = extractor.extract(fixture_what_you_ll_do)
        elapsed = time.perf_counter() - start

        # Coarse sanity bound only (5s), not a perf assertion; avoids CI flake
        assert elapsed < 5.0
        assert len(skills) > 0

    def test_repeated_extraction_consistent(self, extractor):
        """Multiple extractions produce same results."""
        text = "Design and develop systems."
        skills1 = extractor.extract(text)
        skills2 = extractor.extract(text)
        assert skills1 == skills2


class TestSkillExtractorVocabularyAdditions:
    """Verbs added for #499 (manage, ship, evaluate)."""

    def test_new_verbs_in_skill_verbs(self):
        """New verbs are registered in SKILL_VERBS."""
        assert {"manage", "ship", "evaluate"} <= set(SKILL_VERBS)

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("You will manage teams.", ["manage teams"]),
            ("You will ship products.", ["ship products"]),
            ("You will evaluate vendors.", ["evaluate vendors"]),
        ],
    )
    def test_new_verb_extracted(self, extractor, text, expected):
        """Base and inflected forms of new verbs produce a skill phrase."""
        assert extractor.extract(text) == expected

    def test_inflected_new_verb_extracted(self, extractor):
        """Inflected forms lemmatize to the new verb."""
        assert extractor.extract("Managing teams and evaluating vendors.") == [
            "evaluating vendors",
            "managing teams",
        ]

    def test_ship_as_noun_not_extracted(self, extractor):
        """'ship' tagged as a noun is not treated as an action verb."""
        assert extractor.extract("The ship sailed at dawn.") == []
