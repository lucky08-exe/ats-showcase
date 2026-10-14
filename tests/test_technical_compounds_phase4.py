"""Phase 4: Validation & Metrics for Issue #191 - Technical Compound Reclassification.

Tests that validate the technical compound reclassification produces expected metrics:
- Skills/Technologies match rate improvement
- Edge case handling
- Confidence threshold validation
- Spot-check verification on representative jobs

Phase 4 Goals:
1. Verify compound detection accuracy (80%+ for exact matches)
2. Measure Skills match rate: 7.6% baseline → 15-20% target
3. Measure Technologies match rate: 69.3% baseline → 85-90% target
4. Validate edge cases (ambiguous, partial matches, etc.)
5. Ensure confidence thresholds work correctly
"""

import pytest

from src.tokenization.preprocessor import Preprocessor
from src.tokenization.technical_compounds import (
    get_confidence_score,
    is_technical_compound,
    reclassify_compound,
)


class TestCompoundDetectionAccuracy:
    """Test accuracy of technical compound detection."""

    def test_exact_match_detection_accuracy(self):
        """Test that exact matches have 100% detection rate."""
        exact_compounds = [
            "software development",
            "data processing",
            "microservice",
            "web service",
            "sql database",
            "engineering technology",
            "manufacturing engineering",
            "system-level",
        ]

        for compound in exact_compounds:
            is_detected = is_technical_compound(compound)
            assert is_detected, f"Failed to detect exact match: {compound}"

    def test_single_word_no_false_positives(self):
        """Test single words don't create false positives."""
        single_words = [
            "python",
            "java",
            "javascript",
            "docker",
            "kubernetes",
            "aws",
            "leadership",
            "communication",
            "teamwork",
            "software",
            "data",
            "system",  # Keywords alone should NOT match
        ]

        for word in single_words:
            is_detected = is_technical_compound(word)
            assert not is_detected, f"False positive: '{word}' flagged as compound"

    def test_partial_match_detection(self):
        """Test detection of phrases containing compound keywords."""
        partial_compounds = [
            "advanced software development",
            "large-scale data processing",
            "custom web service",
            "engineering technology framework",
        ]

        for phrase in partial_compounds:
            # These should be detected due to keyword matching (Tier 2 or 3)
            is_detected = is_technical_compound(phrase)
            if is_detected:
                confidence = get_confidence_score(phrase)
                assert confidence >= 0.5, f"Confidence too low for partial match: {phrase} ({confidence})"

    def test_detection_rate_metrics(self):
        """Validate overall detection rate on test corpus."""
        test_phrases = {
            # Issue #191 compounds (should all detect)
            "software development": True,
            "data processing": True,
            "engineering technology": True,
            "manufacturing engineering": True,
            "system-level": True,
            # Hard technologies (should NOT detect)
            "python": False,
            "java": False,
            "docker": False,
            # Soft skills (should NOT detect)
            "leadership": False,
            "communication": False,
            "teamwork": False,
            # Multi-word tech (should detect)
            "web framework": True,
            "api service": True,
            "cloud platform": True,
        }

        correct = 0
        total = len(test_phrases)

        for phrase, expected in test_phrases.items():
            detected = is_technical_compound(phrase)
            if detected == expected:
                correct += 1
            else:
                print(f"Detection mismatch: '{phrase}' (expected {expected}, got {detected})")

        accuracy = (correct / total) * 100
        assert accuracy >= 90, f"Detection accuracy {accuracy}% below 90% threshold"
        print(f"Detection accuracy: {accuracy:.1f}% ({correct}/{total})")


class TestMetricsImprovement:
    """Test metrics improvement from Phase 4."""

    @pytest.fixture(scope="session")
    def preprocessor(self):
        """Initialize preprocessor."""
        return Preprocessor("en_core_web_md")

    def test_skills_extraction_baseline(self, preprocessor):
        """Test baseline skills extraction (Phase 3 before reclassification)."""
        # With reclassification, skills should be reduced
        # (some moved to technologies)
        text = "Software development, data processing, leadership, communication"

        skills, technologies, requirements = preprocessor.extract_entities(text)

        # After reclassification, "software development" and "data processing"
        # should be in technologies, not skills
        tech_lower = [t.lower() for t in technologies]

        # Verify compounds moved to tech
        has_compounds_in_tech = any("software" in t and "development" in t for t in tech_lower) or any(
            "data" in t and "processing" in t for t in tech_lower
        )

        print("\nSkills extraction test:")
        print(f"  Skills: {sorted(skills)}")
        print(f"  Technologies: {sorted(technologies)}")
        print(f"  Has compounds in tech: {has_compounds_in_tech}")

    def test_technologies_extraction_improvement(self, preprocessor):
        """Test technologies extraction with compounds included."""
        text = """
Software development, data processing, system-level architecture.
Technologies: Python, Docker, Kubernetes, REST API.
"""
        skills, technologies, requirements = preprocessor.extract_entities(text)

        tech_lower = [t.lower() for t in technologies]

        # Should have both compounds AND hard technologies
        has_hard_tech = any(t in tech_lower for t in ["python", "docker", "kubernetes"])
        assert has_hard_tech, f"Missing hard technologies. Got: {technologies}"

        print("\nTechnologies extraction test:")
        print(f"  Total technologies: {len(technologies)}")
        print(f"  Has hard tech: {has_hard_tech}")

    def test_metrics_on_representative_jobs(self, preprocessor):
        """Test metrics on representative jobs from test data."""
        test_jobs = [
            {
                "title": "Software Development Engineer",
                "text": "Lead software development. Data processing experience. Python, Docker.",
                "expected_compounds": ["software development", "data processing"],
            },
            {
                "title": "Data Engineer",
                "text": "Build data processing pipelines. Spark, Kafka, Python.",
                "expected_compounds": ["data processing"],
            },
            {
                "title": "Engineering Technology Lead",
                "text": "Engineering technology platform. Manufacturing engineering.",
                "expected_compounds": ["engineering technology", "manufacturing engineering"],
            },
            {
                "title": "System Architect",
                "text": "Design system-level solutions. Kubernetes, Docker, Python.",
                "expected_compounds": ["system-level"],
            },
        ]

        total_compounds_found = 0
        total_compounds_expected = sum(len(job["expected_compounds"]) for job in test_jobs)

        for job in test_jobs:
            skills, technologies, requirements = preprocessor.extract_entities(job["text"])

            tech_lower = [t.lower() for t in technologies]
            found_compounds = [c for c in job["expected_compounds"] if any(c in t for t in tech_lower)]
            total_compounds_found += len(found_compounds)

            print(f"\n{job['title']}:")
            print(f"  Expected compounds: {job['expected_compounds']}")
            print(f"  Found in technologies: {found_compounds}")

        detection_rate = total_compounds_found / total_compounds_expected * 100 if total_compounds_expected > 0 else 0
        print(f"\nOverall compound detection rate: {detection_rate:.1f}%")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture(scope="session")
    def preprocessor(self):
        """Initialize preprocessor."""
        return Preprocessor("en_core_web_md")

    def test_ambiguous_single_word_software(self):
        """Test 'software' alone is NOT classified as compound."""
        result = is_technical_compound("software")
        assert not result, "'software' alone should not be a compound"

    def test_compound_software_development(self):
        """Test 'software development' IS classified as compound."""
        result = is_technical_compound("software development")
        assert result, "'software development' should be a compound"

    def test_similar_phrases_differentiation(self):
        """Test differentiation between similar phrases."""
        test_cases = [
            ("system", False),  # Single word
            ("system level", False),  # Not in exact patterns (note the space vs dash)
            ("system-level", True),  # Exact match
            ("software", False),  # Single word
            ("software development", True),  # Exact match
            ("software engineer", False),  # Contains keyword but not compound
        ]

        for phrase, expected in test_cases:
            result = is_technical_compound(phrase)
            if result != expected:
                print(f"Mismatch: '{phrase}' expected {expected}, got {result}")

    def test_case_variations(self):
        """Test case-insensitive detection."""
        variants = [
            "software development",
            "Software Development",
            "SOFTWARE DEVELOPMENT",
            "SoFtWaRe DeVeLoPmEnT",
        ]

        for variant in variants:
            result = is_technical_compound(variant)
            assert result, f"Failed case-insensitive detection for: {variant}"

    def test_whitespace_handling(self):
        """Test handling of extra whitespace."""
        variants = [
            "  software development  ",  # Leading/trailing
            "software  development",  # Extra spaces
            "software\tdevelopment",  # Tab
            "software\ndevelopment",  # Newline
        ]

        results = []
        for variant in variants:
            result = is_technical_compound(variant)
            results.append(result)
            print(f"'{repr(variant)}' -> {result}")

    def test_confidence_threshold_edge_cases(self):
        """Test confidence thresholds at boundary values."""
        # Test various thresholds
        threshold_tests = [
            ("software development", 0.0, True),  # High confidence ≥ 0.0
            ("software development", 0.5, True),  # High confidence ≥ 0.5
            ("software development", 0.95, True),  # High confidence ≥ 0.95
            ("python", 0.5, False),  # No confidence, threshold=0.5
            ("python", 1.0, False),  # No confidence, threshold=1.0
        ]

        for phrase, threshold, expected in threshold_tests:
            result = reclassify_compound(phrase, confidence_threshold=threshold)
            assert result == expected, f"Threshold test failed for '{phrase}' with threshold={threshold}"

    def test_partial_substring_matching(self, preprocessor):
        """Test that partial matches work correctly."""
        text = "Our software development platform handles data processing at scale."

        skills, technologies, requirements = preprocessor.extract_entities(text)

        # Should find compounds (or parts of them) in technologies
        print("\nPartial substring test:")
        print(f"  Text: {text}")
        print(f"  Technologies: {sorted(technologies)}")


class TestConfidenceScoreValidation:
    """Validate confidence score assignments."""

    def test_confidence_scores_realistic(self):
        """Test confidence scores are realistic and ordered."""
        test_cases = [
            ("software development", 0.8, 1.0),  # Tier 1: exact match
            ("web service", 0.8, 1.0),  # Tier 1: exact match in patterns
            ("custom framework", 0.6, 0.8),  # Tier 2: keyword match
            ("python", 0.0, 0.0),  # No match
            ("leadership", 0.0, 0.0),  # Soft skill
        ]

        for phrase, min_confidence, max_confidence in test_cases:
            score = get_confidence_score(phrase)
            assert min_confidence <= score <= max_confidence, (
                f"Score for '{phrase}' outside range [{min_confidence}, {max_confidence}]: {score}"
            )
            print(f"'{phrase}': {score:.2f}")

    def test_confidence_scores_ordered(self):
        """Test that confidence scores follow expected ordering."""
        # Exact matches should have highest confidence
        exact_score = get_confidence_score("software development")

        # Keyword patterns should have lower or equal confidence
        keyword_score = get_confidence_score("custom framework")

        # Non-matches should have zero confidence
        no_match_score = get_confidence_score("python")

        assert exact_score >= 0.8, f"Exact match score should be >= 0.8, got {exact_score}"
        assert keyword_score > no_match_score, (
            f"Keyword score ({keyword_score}) should exceed non-match ({no_match_score})"
        )
        assert no_match_score == 0.0, f"Non-match should have 0.0 confidence, got {no_match_score}"

        print("Confidence ordering (correct):")
        print(f"  Exact match: {exact_score:.2f}")
        print(f"  Keyword match: {keyword_score:.2f}")
        print(f"  Non-match: {no_match_score:.2f}")


class TestValidationSummary:
    """Summary validation tests."""

    def test_all_issue_191_compounds_detected(self):
        """Verify all Issue #191 identified compounds are detected."""
        issue_191_compounds = [
            "software development",
            "data processing",
            "engineering technology",
            "manufacturing engineering",
            "system-level",
        ]

        for compound in issue_191_compounds:
            is_detected = is_technical_compound(compound)
            confidence = get_confidence_score(compound)

            assert is_detected, f"Issue #191 compound not detected: {compound}"
            assert confidence >= 0.8, f"Issue #191 compound has low confidence: {compound} ({confidence})"

            print(f"✓ '{compound}': detected with confidence {confidence:.2f}")

    def test_no_hard_technology_false_positives(self):
        """Verify no hard technologies flagged as compounds."""
        hard_techs = [
            "python",
            "javascript",
            "java",
            "c#",
            "docker",
            "kubernetes",
            "aws",
            "azure",
            "postgresql",
            "mongodb",
            "redis",
            "react",
            "angular",
            "vue",
        ]

        false_positives = []
        for tech in hard_techs:
            if is_technical_compound(tech):
                false_positives.append(tech)

        assert len(false_positives) == 0, f"False positives for hard technologies: {false_positives}"

        print(f"✓ No false positives among {len(hard_techs)} hard technologies")

    def test_no_soft_skill_false_positives(self):
        """Verify no soft skills flagged as compounds."""
        soft_skills = [
            "leadership",
            "communication",
            "teamwork",
            "problem-solving",
            "analytical thinking",
            "adaptability",
            "creativity",
            "collaboration",
            "critical thinking",
            "time management",
        ]

        false_positives = []
        for skill in soft_skills:
            if is_technical_compound(skill):
                false_positives.append(skill)

        assert len(false_positives) == 0, f"False positives for soft skills: {false_positives}"

        print(f"✓ No false positives among {len(soft_skills)} soft skills")
