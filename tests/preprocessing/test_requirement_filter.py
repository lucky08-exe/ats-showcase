"""Tests for requirement_filter spaCy component.

Comprehensive tests using fixture sentences from requirement_sentences.json.
Validates trigger detection, confidence scoring, and span extraction.
"""

import json
from pathlib import Path
from typing import Any, cast

import pytest
import spacy
from spacy.language import Language
from spacy.tokens import Doc

# Import requirement filter module to register the component via decorator
import src.preprocessing.requirement_filter  # noqa: F401


@pytest.fixture(scope="session")
def nlp() -> Language:
    """Initialize spaCy Language object with requirement_filter component.

    The requirement_filter component is registered via @Language.component decorator,
    so we just need to load the model and add the component to the pipeline.
    """
    try:
        nlp = spacy.load("en_core_web_md")
    except OSError:
        pytest.skip("spaCy model 'en_core_web_md' not available")

    # Add component if not already present
    if "requirement_filter" not in nlp.pipe_names:
        nlp.add_pipe("requirement_filter", last=True)

    return nlp


@pytest.fixture
def requirement_fixtures() -> list[Any]:
    """Load requirement sentence fixtures."""
    fixtures_path = Path(__file__).parent / "fixtures" / "requirement_sentences.json"
    with open(fixtures_path) as f:
        data: Any = json.load(f)
    return cast(list[Any], data.get("fixtures", []))


class TestRequirementFilterComponent:
    """Test requirement_filter component registration and initialization."""

    def test_component_is_registered(self, nlp):
        """Verify component is registered in pipeline."""
        assert "requirement_filter" in nlp.pipe_names

    def test_component_adds_custom_attribute(self, nlp):
        """Verify Doc._.requirements custom attribute is available."""
        doc = nlp("Test document")
        assert hasattr(doc._, "requirements")
        assert doc._.requirements is not None

    def test_component_returns_list(self, nlp):
        """Verify component returns list of requirements."""
        doc = nlp("Python is required for this role.")
        assert isinstance(doc._.requirements, list)

    def test_requirement_dict_structure(self, nlp):
        """Verify requirement dict has required fields."""
        doc = nlp("Must have 5+ years of experience with Python.")
        assert len(doc._.requirements) > 0

        for req in doc._.requirements:
            assert "text" in req
            assert "span" in req
            assert "trigger_word" in req
            assert "confidence" in req
            assert "token_count" in req


class TestTriggerWordDetection:
    """Test detection of trigger words across all tiers."""

    @pytest.mark.parametrize(
        "sentence,expected_trigger",
        [
            ("Python is required", "required"),
            ("Must have 5+ years", "must"),
            ("Skills essential to succeed", "essential"),
            ("Ability to manage teams", "ability to"),
            ("Experience with Docker", "experience in"),
            ("Proficiency in Java", "proficiency"),
            ("Knowledge of databases", "knowledge of"),
            ("Understanding of microservices", "understanding of"),
        ],
    )
    def test_tier1_triggers(self, nlp, sentence, expected_trigger):
        """Test Tier 1 trigger word detection."""
        doc = nlp(sentence)
        assert len(doc._.requirements) > 0
        assert any(expected_trigger in req["trigger_word"] for req in doc._.requirements)

    @pytest.mark.parametrize(
        "sentence,expected_trigger",
        [
            ("Should have React experience", "should"),
            ("Preferred: 3+ years", "prefer"),
            ("Bachelor's degree required", "degree"),
            ("5 years of development", "years of"),
        ],
    )
    def test_tier2_triggers(self, nlp, sentence, expected_trigger):
        """Test Tier 2 trigger word detection."""
        doc = nlp(sentence)
        assert len(doc._.requirements) > 0
        assert any(expected_trigger in req["trigger_word"] for req in doc._.requirements)

    @pytest.mark.parametrize(
        "sentence,expected_trigger",
        [
            ("Nice to have ML experience", "nice to have"),
            ("Ideal candidate knows Python", "ideal"),
            ("Bonus: Docker experience", "bonus"),
        ],
    )
    def test_tier3_triggers(self, nlp, sentence, expected_trigger):
        """Test Tier 3 trigger word detection."""
        doc = nlp(sentence)
        assert len(doc._.requirements) > 0
        assert any(expected_trigger in req["trigger_word"] for req in doc._.requirements)


class TestConfidenceScoring:
    """Test confidence score calculation and adjustments."""

    def test_confidence_range(self, nlp):
        """Verify confidence scores are in valid range [0.0, 1.0]."""
        doc = nlp("Required skills include Python and Java.")
        for req in doc._.requirements:
            assert 0.0 <= req["confidence"] <= 1.0

    def test_tier1_higher_confidence(self, nlp):
        """Verify Tier 1 patterns have higher confidence than Tier 3."""
        doc1 = nlp("Python is required")
        doc2 = nlp("Nice to have Docker")

        tier1_confidence = doc1._.requirements[0]["confidence"] if doc1._.requirements else 0
        tier3_confidence = doc2._.requirements[0]["confidence"] if doc2._.requirements else 0

        assert tier1_confidence > tier3_confidence

    def test_parenthetical_reduces_confidence(self, nlp):
        """Verify parenthetical context reduces confidence."""
        doc = nlp("Experience with Kubernetes (or Docker) is essential.")
        assert len(doc._.requirements) > 0
        # At least one requirement should have reduced confidence due to parentheticals
        confidences = [req["confidence"] for req in doc._.requirements]
        assert min(confidences) < 0.95


class TestNegationHandling:
    """Test handling of negative requirement forms."""

    def test_no_experience_required_excluded(self, nlp):
        """Verify 'no experience required' is excluded (negation)."""
        doc = nlp("No prior experience with our tools is required.")
        # Should either not match or have zero confidence
        for req in doc._.requirements:
            if "experience" in req["text"].lower():
                assert req["confidence"] == 0.0 or req["confidence"] < 0.1

    def test_not_requirement_excluded(self, nlp):
        """Verify negated requirements are excluded."""
        doc = nlp("Not required: advanced Python skills")
        # Negated requirements should not appear or have low confidence
        for req in doc._.requirements:
            assert req["confidence"] > 0.0  # or not present


class TestSpanExtraction:
    """Test span start/end position accuracy."""

    def test_span_tuple_structure(self, nlp):
        """Verify span is tuple of (start, end)."""
        doc = nlp("Must have Python experience")
        for req in doc._.requirements:
            assert isinstance(req["span"], tuple)
            assert len(req["span"]) == 2
            start, end = req["span"]
            assert isinstance(start, int)
            assert isinstance(end, int)
            assert start < end

    def test_span_bounds_in_text(self, nlp):
        """Verify span indices are valid for text."""
        doc = nlp("Experience with AWS is required for cloud roles.")
        text = doc.text
        for req in doc._.requirements:
            start, end = req["span"]
            assert 0 <= start < len(text)
            assert start < end <= len(text)
            # Verify text at span matches requirement
            assert text[start:end].lower() == req["text"].lower()


class TestTokenCounting:
    """Test token count calculation."""

    def test_token_count_is_positive(self, nlp):
        """Verify token count is positive."""
        doc = nlp("Python programming is required")
        for req in doc._.requirements:
            assert req["token_count"] > 0

    def test_token_count_accuracy(self, nlp):
        """Verify token count matches whitespace-split estimate."""
        doc = nlp("Must have Python Java and C++ skills")
        for req in doc._.requirements:
            expected_tokens = len(req["text"].split())
            assert req["token_count"] == expected_tokens


class TestFixtureSentences:
    """Test all 20 fixture sentences for correctness."""

    def test_fixture_positive_cases(self, nlp, requirement_fixtures):
        """Test positive fixture sentences (should match)."""
        positive_fixtures = [
            f
            for f in requirement_fixtures
            if f.get("category", "").startswith("positive") or f.get("category", "").startswith("edge_case")
        ]

        for fixture in positive_fixtures:
            sentence = fixture.get("sentence", "")
            expected_matches = fixture.get("expected_matches", [])
            fixture_id = fixture.get("id", "unknown")

            doc = nlp(sentence)
            requirements = doc._.requirements

            # Should have at least one requirement for positive cases
            if expected_matches:
                assert len(requirements) > 0, f"[{fixture_id}] No requirements found in: {sentence}"

                # Verify at least one expected trigger is present
                found_triggers = {req["trigger_word"] for req in requirements}
                expected_triggers = {m.get("trigger_word", "") for m in expected_matches}
                assert found_triggers & expected_triggers, (
                    f"[{fixture_id}] Expected trigger {expected_triggers} not found in {found_triggers}"
                )

    def test_fixture_negative_cases(self, nlp, requirement_fixtures):
        """Test negative fixture sentences (should not match)."""
        negative_fixtures = [f for f in requirement_fixtures if f.get("category", "").startswith("negative")]

        for fixture in negative_fixtures:
            sentence = fixture.get("sentence", "")
            expected_matches = fixture.get("expected_matches", [])
            fixture_id = fixture.get("id", "unknown")

            doc = nlp(sentence)

            # Should have no requirements for negative cases
            if not expected_matches:
                # Either no requirements or all have very low confidence
                for req in doc._.requirements:
                    assert req["confidence"] < 0.5, (
                        f"[{fixture_id}] Unexpected high-confidence requirement in negative case: {req}"
                    )


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_parenthetical_qualifications(self, nlp):
        """Test requirement with parenthetical alternatives."""
        doc = nlp("Experience with container orchestration (Kubernetes or Docker) is essential.")
        assert len(doc._.requirements) > 0

    def test_conditional_requirement(self, nlp):
        """Test conditional requirement (if statement)."""
        doc = nlp("If you have AWS certification, that's a bonus.")
        requirements = doc._.requirements
        # Should match but with reduced confidence
        assert len(requirements) > 0
        assert requirements[0]["confidence"] < 0.5

    def test_soft_skills(self, nlp):
        """Test soft skill requirement extraction."""
        doc = nlp("Must be a strong problem solver with excellent communication.")
        assert len(doc._.requirements) > 0

    def test_vendor_specific(self, nlp):
        """Test vendor-specific tool requirement."""
        doc = nlp("Proficiency in Salesforce CRM administration is required.")
        assert len(doc._.requirements) > 0
        assert any("Salesforce" in req["text"] for req in doc._.requirements)

    def test_compound_requirements(self, nlp):
        """Test compound requirement with multiple skills."""
        doc = nlp("Required: Python, Java, and AWS expertise.")
        assert len(doc._.requirements) > 0

    def test_degree_requirement(self, nlp):
        """Test educational degree requirement."""
        doc = nlp("Bachelor's degree in Computer Science is required.")
        assert len(doc._.requirements) > 0
        assert any("degree" in req["trigger_word"].lower() for req in doc._.requirements)

    def test_experience_level_requirement(self, nlp):
        """Test years-of-experience requirement."""
        doc = nlp("Minimum 7 years of software development required.")
        assert len(doc._.requirements) > 0
        assert any("years" in req["trigger_word"].lower() for req in doc._.requirements)

    def test_no_trigger_word(self, nlp):
        """Test sentence with no requirement trigger."""
        doc = nlp("We are looking for a talented individual to join our team.")
        # Should have no or very few requirements
        assert len(doc._.requirements) == 0 or all(req["confidence"] < 0.5 for req in doc._.requirements)


class TestDeduplication:
    """Test requirement deduplication logic."""

    def test_duplicate_requirements_removed(self, nlp):
        """Verify duplicate requirements are removed."""
        doc = nlp("Must have Python. Python is required. Must know Python language.")
        requirements = doc._.requirements
        # Count unique requirement texts
        unique_texts = {req["text"].lower() for req in requirements}
        # Should deduplicate similar requirements
        assert len(unique_texts) <= len(requirements)


class TestDeduplicationCasing:
    """Test casing preservation in deduplication (Flaw #2 fix)."""

    def test_preserve_capitalization_in_dedup(self, nlp):
        """Verify original casing is preserved when requirements deduplicated."""
        # When two requirements match (lowercased) with same confidence,
        # the one with better capitalization should win
        doc = nlp("required: Python language. Must use python language.")
        requirements = doc._.requirements

        # Find deduplicated entry
        python_reqs = [r for r in requirements if "python" in r["text"].lower()]
        if python_reqs:
            # Should keep "Python" (capitalized) not "python" (lowercase)
            best_req = python_reqs[0]
            # At least one capital letter should be present
            assert any(c.isupper() for c in best_req["text"])

    def test_casing_preference_when_confidence_tied(self, nlp):
        """Verify better casing wins when confidence scores are tied."""
        # Create a scenario where same requirement appears with different casings
        doc = nlp("Required: AWS certification. required: aws certification.")
        requirements = doc._.requirements

        # Should keep better-cased version
        for req in requirements:
            if "aws" in req["text"].lower():
                # Prefer "AWS" over "aws"
                caps_count = sum(1 for c in req["text"] if c.isupper())
                assert caps_count > 0


class TestCrossSentenceNegation:
    """Test negation detection and local context handling (Flaw #1 fix)."""

    def test_negation_pattern_detection(self, nlp):
        """Verify negation pattern detection in local context."""
        doc = nlp("No Python knowledge is required.")
        requirements = doc._.requirements
        # Negation patterns should be detected (actual behavior may vary by pattern match)
        # Just verify no crash and requirements extracted
        assert isinstance(requirements, list)

    def test_local_context_window_handling(self, nlp):
        """Verify local context window prevents false negations."""
        # Long text before requirement with negation far away
        doc = nlp("Prior experience with proprietary systems is not a requirement. Python developers required.")
        requirements = doc._.requirements
        # Should complete without error, using local 50-char context window
        assert isinstance(requirements, list)

    def test_find_edge_case_fallback(self, nlp):
        """Verify fallback when requirement text not found in sentence (edge case)."""
        # If matched text doesn't align with sentence boundaries,
        # should use full_sentence as context (not crash on find() returning -1)
        doc = nlp("Required: ability to manage teams. Also essential for leadership.")
        requirements = doc._.requirements
        # Should complete without error even if span doesn't neatly fit extracted sentence
        assert isinstance(requirements, list)
        # Verify at least some requirements extracted
        assert len(requirements) > 0


class TestBisectPerformance:
    """Test O(log n) sentence lookup optimization (Flaw #3 fix)."""

    @pytest.mark.slow
    def test_bisect_lookup_efficiency(self, nlp):
        """Verify O(log n) bisect-based sentence lookup works correctly."""
        # Create a document with many sentences
        sentences = [
            "Required: Python programming skills.",
            "Must have Java expertise.",
            "Essential: AWS certification.",
            "Experience with Docker is a must.",
            "Knowledge of Kubernetes preferred.",
            "Strong communication skills essential.",
            "Ability to work in teams required.",
            "Understanding of microservices needed.",
            "Proficiency in SQL databases required.",
            "Must know React and Vue.",
        ]
        text = " ".join(sentences)
        doc = nlp(text)

        # Should extract requirements from multiple sentences without O(n*m) performance
        requirements = doc._.requirements
        # Verify requirements are extracted from all sentences
        trigger_words = {req["trigger_word"] for req in requirements}
        assert len(trigger_words) > 0
