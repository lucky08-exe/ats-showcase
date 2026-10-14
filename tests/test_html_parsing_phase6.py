"""Phase 1: Baseline tests for HTML parsing improvement (Issue #193)."""

import pytest

from src.tokenization.preprocessor import Preprocessor


class TestHTMLParsingBaseline:
    """Baseline tests for HTML parsing quality before Phase 2 improvements."""

    @pytest.fixture(scope="session")
    def preprocessor(self):
        """Initialize Preprocessor with real spaCy model."""
        preprocessor = Preprocessor(model="en_core_web_md")
        return preprocessor

    # Test Data: Representative problematic fragments from real job descriptions
    TEST_DATA = [
        {
            "name": "Multi-word fragment with case transition",
            "text": "Requires 5+ years of experience may differCulture StatementDon't settle for less.",
            "expected_fragment": "may differCulture StatementDon't",
            "description": "Mixed case artifact from HTML parsing",
        },
        {
            "name": "Section header artifact",
            "text": "Core CompetenciesRequired QualificationsTo apply, send your resume.",
            "expected_fragment": "Required QualificationsTo",
            "description": "Section headers concatenated without spacing",
        },
        {
            "name": "Compound science keywords",
            "text": "Degree in computer science and years of data science , or science background.",
            "expected_fragments": ["computer science and years", "data science , or science"],
            "description": "Oddly split compound keywords",
        },
        {
            "name": "Article concatenation",
            "text": "the Hiring Manager wants experienced developers for team.",
            "expected_fragment": "the Hiring Manager",
            "description": "Article with proper noun concatenation",
        },
        {
            "name": "HTML entity artifacts",
            "text": "Requirements&nbsp;&nbsp;Position Details&nbsp;We are looking for professionals.",
            "expected_fragment": None,  # Should be removed during cleanup
            "description": "HTML non-breaking spaces in text",
        },
    ]

    def test_baseline_extraction_quality(self, preprocessor):
        """Extract entities from problematic text and measure baseline quality."""
        test_text = (
            "Requires 5+ years of experience may differCulture StatementDon't settle for less. "
            "Core CompetenciesRequired QualificationsTo apply, send your resume. "
            "Degree in computer science and years of data science , or science background. "
            "the Hiring Manager wants experienced developers for team."
        )

        skills, tech, reqs = preprocessor.extract_entities(test_text)

        # Baseline metrics
        metrics: dict[str, float] = {
            "total_entities": len(skills) + len(tech) + len(reqs),
            "skills_count": len(skills),
            "tech_count": len(tech),
            "reqs_count": len(reqs),
        }

        # Count multi-word fragments with suspicious characteristics
        suspicious_count = 0
        for entity_list in [skills, tech, reqs]:
            for entity in entity_list:
                # Check for problematic patterns: MixedCase, articles, etc.
                if self._has_suspicious_pattern(entity):
                    suspicious_count += 1

        metrics["suspicious_fragments"] = suspicious_count
        metrics["quality_score"] = self._calculate_quality_score(suspicious_count, len(skills) + len(tech) + len(reqs))

        # Store baseline metrics
        pytest.baseline_metrics = metrics  # type: ignore[attr-defined]
        assert metrics["quality_score"] >= 0  # Baseline can be any value

    def test_fragment_count_baseline(self, preprocessor):
        """Establish baseline fragment count before improvements."""
        test_cases = [
            ("Senior may differCulture StatementDeveloper wanted", "MixedCase fragment"),
            ("Core CompetenciesRequired QualificationsTo apply", "Section header artifact"),
            ("Computer science and years data science", "Oddly split compound"),
        ]

        total_fragments = 0
        for text, _ in test_cases:
            skills, tech, reqs = preprocessor.extract_entities(text)
            fragment_count = self._count_suspicious_fragments(skills + tech + reqs)
            total_fragments += fragment_count

        # Baseline measurement (no assertion yet - just measurement)
        baseline_fragment_count = total_fragments
        pytest.baseline_fragment_count = baseline_fragment_count  # type: ignore[attr-defined]

    def test_quality_score_calculation(self, preprocessor):
        """Test quality score calculation: (total_entities - suspicious) / total_entities * 100."""
        text = "Senior may differCulture StatementDeveloper with Core CompetenciesRequired Qualifications."

        skills, tech, reqs = preprocessor.extract_entities(text)
        all_entities = skills + tech + reqs

        quality_score = self._calculate_quality_score(self._count_suspicious_fragments(all_entities), len(all_entities))

        # Store for Phase 4 comparison
        pytest.quality_score_baseline = quality_score  # type: ignore[attr-defined]
        assert 0 <= quality_score <= 100

    def test_signal_to_noise_ratio_baseline(self, preprocessor):
        """Calculate baseline signal-to-noise ratio (good entities / total entities)."""
        text = (
            "Needs Python JavaScript React expertise. "
            "Experience with may differCulture StatementPostgreSQL and MongoDB. "
            "Required QualificationsTo include AWS cloud skills."
        )

        skills, tech, reqs = preprocessor.extract_entities(text)
        all_entities = skills + tech + reqs

        good_count = len([e for e in all_entities if not self._has_suspicious_pattern(e)])
        ratio = (good_count / len(all_entities) * 100) if all_entities else 0

        pytest.baseline_signal_to_noise_ratio = ratio  # type: ignore[attr-defined]
        # Baseline target: 45%+ (before Phase 2 improvements)
        assert ratio >= 0  # Baseline can be any value

    @staticmethod
    def _has_suspicious_pattern(entity: str) -> bool:
        """Check if entity has suspicious patterns indicating HTML parsing issues."""
        # MixedCase transitions (e.g., "differCulture")
        mixed_case = any(entity[i].isupper() and entity[i - 1].islower() for i in range(1, len(entity)))

        # Multiple case transitions (e.g., "may differCulture StatementDon't")
        case_transitions = sum(1 for i in range(1, len(entity)) if entity[i].isupper() != entity[i - 1].isupper())

        # Unclosed punctuation
        has_unclosed_punc = entity.count("(") != entity.count(")") or entity.count("[") != entity.count("]")

        # Very short multi-word with odd spacing
        words = entity.split()
        odd_spacing = len(words) > 1 and any(len(w) < 3 for w in words)

        return mixed_case or case_transitions > 2 or has_unclosed_punc or odd_spacing

    @staticmethod
    def _count_suspicious_fragments(entities: list) -> int:
        """Count entities with suspicious patterns."""
        return sum(1 for entity in entities if TestHTMLParsingBaseline._has_suspicious_pattern(entity))

    @staticmethod
    def _calculate_quality_score(suspicious_count: int, total_count: int) -> float:
        """Calculate quality score: (total - suspicious) / total * 100."""
        if total_count == 0:
            return 100.0
        return ((total_count - suspicious_count) / total_count) * 100


class TestEnhancedFragmentDetection:
    """Test enhanced fragment detection for Phase 3."""

    @pytest.fixture(scope="session")
    def preprocessor(self):
        """Initialize Preprocessor with real spaCy model."""
        preprocessor = Preprocessor(model="en_core_web_md")
        return preprocessor

    def test_excessive_case_transitions(self, preprocessor):
        """Detect multi-word with excessive MixedCase transitions."""
        # Should detect: 3+ transitions
        assert preprocessor._has_excessive_case_transitions("may differCulture StatementDon't")
        assert preprocessor._has_excessive_case_transitions("RequiredQualificationsTo")

        # Should not detect: <3 transitions
        assert not preprocessor._has_excessive_case_transitions("machine Learning")
        assert not preprocessor._has_excessive_case_transitions("Python")

    def test_unclosed_punctuation(self, preprocessor):
        """Detect entities with mismatched punctuation."""
        assert preprocessor._has_unclosed_punctuation("(incomplete")
        assert preprocessor._has_unclosed_punctuation("test [without closing")
        assert preprocessor._has_unclosed_punctuation("{brace mismatch")

        assert not preprocessor._has_unclosed_punctuation("test(content)")
        assert not preprocessor._has_unclosed_punctuation("normal text")

    def test_html_entity_artifacts(self, preprocessor):
        """Detect HTML entity artifacts in text."""
        assert preprocessor._has_html_entity_artifacts("Requirements&nbsp;Details")
        assert preprocessor._has_html_entity_artifacts("text&amp;more")
        assert preprocessor._has_html_entity_artifacts("&#36;100")

        assert not preprocessor._has_html_entity_artifacts("normal text")

    def test_suspicious_multi_word_fragment(self, preprocessor):
        """Detect suspicious multi-word fragments."""
        # Section header artifacts
        assert preprocessor._is_suspicious_multi_word_fragment("Required QualificationsTo")
        assert preprocessor._is_suspicious_multi_word_fragment("RequiredQualificationsTo")

        # Article + proper noun pattern
        assert preprocessor._is_suspicious_multi_word_fragment("the Hiring Manager")

        # Oddly spaced keywords
        assert preprocessor._is_suspicious_multi_word_fragment("computer science and years")

        # MixedCase patterns
        assert preprocessor._is_suspicious_multi_word_fragment("may differCulture Statement")

        # Single words should not be flagged
        assert not preprocessor._is_suspicious_multi_word_fragment("Python")
        assert not preprocessor._is_suspicious_multi_word_fragment("Developer")

        # Normal multi-word should not be flagged
        assert not preprocessor._is_suspicious_multi_word_fragment("machine learning engineer")
        assert not preprocessor._is_suspicious_multi_word_fragment("cloud computing")

    def test_fragment_filtering_integration(self, preprocessor):
        """Test that fragments are filtered during extraction."""
        # Text with problematic fragments
        text = (
            "Requires Python developer. "
            "may differCulture StatementDon't settle. "
            "Core CompetenciesRequired Qualifications"
        )

        skills, tech, reqs = preprocessor.extract_entities(text)

        # Fragments should be filtered out
        all_entities = skills + tech + reqs
        for entity in all_entities:
            # Verify no obvious fragments are in results
            assert not preprocessor._is_suspicious_multi_word_fragment(entity), (
                f"Fragment detected in results: {entity}"
            )
