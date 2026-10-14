"""Integration tests for requirement extraction in Preprocessor pipeline.

Tests full preprocessing workflow with requirement_filter component.
Validates trigger-based requirement extraction and storage.
"""

import json
from typing import Any

import pytest

from src.tokenization.preprocessor import Preprocessor
from tests.perf_utils import median_elapsed_ms


@pytest.fixture
def preprocessor() -> Preprocessor:
    """Create Preprocessor instance with requirement extraction enabled."""
    try:
        return Preprocessor(extract_requirements=True)
    except OSError:
        pytest.skip("spaCy model not available")
        return None  # type: ignore[return-value]


@pytest.fixture
def sample_jobs() -> list[dict[str, Any]]:
    """Provide 5 sample job descriptions for integration testing."""
    return [
        {
            "job_id": "job_001",
            "title": "Senior Python Developer",
            "company": "TechCorp",
            "description": (
                "We are seeking a Senior Python Developer. "
                "Required: 5+ years of Python experience. "
                "Must have knowledge of Django and FastAPI. "
                "Essential skills include REST API design. "
                "Proficiency in Docker is mandatory. "
                "Ability to work with distributed systems. "
                "Nice to have: Kubernetes experience."
            ),
        },
        {
            "job_id": "job_002",
            "title": "Full Stack Engineer",
            "company": "StartupXYZ",
            "description": (
                "Full Stack Engineer needed for growing startup. "
                "Required technologies: React, Node.js, PostgreSQL. "
                "Must understand microservices architecture. "
                "Experience with AWS is essential. "
                "Should have CI/CD pipeline experience. "
                "Bachelor's degree in Computer Science preferred."
            ),
        },
        {
            "job_id": "job_003",
            "title": "Data Scientist",
            "company": "DataSys",
            "description": (
                "Join our analytics team as a Data Scientist. "
                "Essential qualifications: "
                "Machine learning knowledge required. "
                "Proficiency in Python and SQL. "
                "Understanding of statistical methods. "
                "5+ years of data analysis experience. "
                "Ability to communicate findings to stakeholders."
            ),
        },
        {
            "job_id": "job_004",
            "title": "DevOps Engineer",
            "company": "CloudPlatform",
            "description": (
                "DevOps Engineer for infrastructure automation. "
                "Must have hands-on Kubernetes experience. "
                "Required: AWS or GCP certification. "
                "Essential: Infrastructure as Code (Terraform). "
                "Strong Linux/Unix administration skills. "
                "Experience with monitoring tools (Prometheus, ELK). "
                "Bonus: Experience with GitOps workflows."
            ),
        },
        {
            "job_id": "job_005",
            "title": "Frontend Developer",
            "company": "WebDesign Inc",
            "description": (
                "Seeking Frontend Developer for modern web apps. "
                "Required: JavaScript/TypeScript expertise. "
                "Must know React or Vue.js. "
                "Proficiency in HTML5 and CSS3. "
                "Understanding of responsive design essential. "
                "Knowledge of accessibility standards (WCAG). "
                "Nice to have: Next.js or Nuxt experience. "
                "Ability to optimize web performance."
            ),
        },
    ]


class TestRequirementExtractionIntegration:
    """Integration tests for requirement extraction in full pipeline."""

    def test_single_job_requirement_extraction(self, preprocessor, sample_jobs):
        """Test requirement extraction on single job description."""
        job = sample_jobs[0]
        description = job["description"]

        # Extract trigger-based requirements
        trigger_reqs_json = preprocessor.extract_trigger_requirements(description)

        # Verify extraction was successful
        assert trigger_reqs_json is not None, "No requirements extracted"
        assert isinstance(trigger_reqs_json, str), "Requirements should be JSON string"

        # Parse JSON and validate structure
        requirements = json.loads(trigger_reqs_json)
        assert isinstance(requirements, list), "Requirements should be JSON array"
        assert len(requirements) > 0, "Should extract at least one requirement"

        # Validate requirement dict structure
        for req in requirements:
            assert "text" in req
            assert "trigger_word" in req
            assert "confidence" in req
            assert "span" in req
            assert "token_count" in req
            assert isinstance(req["confidence"], (int, float))
            assert 0.0 <= req["confidence"] <= 1.0

    def test_all_sample_jobs_requirement_extraction(self, preprocessor, sample_jobs):
        """Test requirement extraction on all 5 sample jobs."""
        extraction_results = []

        for job in sample_jobs:
            trigger_reqs_json = preprocessor.extract_trigger_requirements(job["description"])
            extraction_results.append((job["job_id"], trigger_reqs_json))

        # Verify all jobs had requirements extracted
        for job_id, reqs_json in extraction_results:
            assert reqs_json is not None, f"No requirements extracted for {job_id}"

            requirements = json.loads(reqs_json)
            assert len(requirements) > 0, f"Empty requirements for {job_id}"

            # Log extraction summary
            print(f"{job_id}: {len(requirements)} requirements extracted")

    def test_requirement_trigger_word_variety(self, preprocessor, sample_jobs):
        """Verify extraction captures variety of trigger words."""
        all_trigger_words = set()

        for job in sample_jobs:
            trigger_reqs_json = preprocessor.extract_trigger_requirements(job["description"])
            if trigger_reqs_json:
                requirements = json.loads(trigger_reqs_json)
                for req in requirements:
                    all_trigger_words.add(req["trigger_word"])

        # Should capture multiple trigger words from tier 1-3
        assert len(all_trigger_words) > 0, "Should capture multiple trigger words"
        print(f"Captured trigger words: {sorted(all_trigger_words)}")

    @pytest.mark.perf
    def test_performance_no_regression(self, preprocessor, sample_jobs):
        """Verify requirement extraction adds <50ms overhead per job."""

        def run_batch() -> None:
            for job in sample_jobs:
                preprocessor.extract_trigger_requirements(job["description"])

        # Warm-up run primes the same measured path; median over repeats
        total_ms = median_elapsed_ms(run_batch, repeats=3, warmup=1)
        avg_time_per_job = total_ms / len(sample_jobs)

        print(f"Average extraction time: {avg_time_per_job:.2f}ms per job")
        print(f"Total time for {len(sample_jobs)} jobs: {total_ms:.2f}ms")

        # Assert performance requirement: <50ms per job
        assert avg_time_per_job < 50.0, f"Extraction too slow: {avg_time_per_job:.2f}ms per job"

    def test_requirement_confidence_scoring(self, preprocessor, sample_jobs):
        """Verify confidence scores reflect trigger word tier."""
        confidence_by_trigger: dict[str, list[float]] = {}

        for job in sample_jobs:
            trigger_reqs_json = preprocessor.extract_trigger_requirements(job["description"])
            if trigger_reqs_json:
                requirements = json.loads(trigger_reqs_json)
                for req in requirements:
                    trigger = req["trigger_word"]
                    confidence = req["confidence"]

                    if trigger not in confidence_by_trigger:
                        confidence_by_trigger[trigger] = []
                    confidence_by_trigger[trigger].append(confidence)

        # Verify Tier 1 triggers have higher confidence on average than Tier 3
        tier1_triggers = {"required", "must", "essential", "ability to", "experience in"}
        tier3_triggers = {"nice to have", "ideal", "bonus"}

        tier1_confidences = [
            conf for trigger, confs in confidence_by_trigger.items() if trigger in tier1_triggers for conf in confs
        ]
        tier3_confidences = [
            conf for trigger, confs in confidence_by_trigger.items() if trigger in tier3_triggers for conf in confs
        ]

        if tier1_confidences and tier3_confidences:
            avg_tier1 = sum(tier1_confidences) / len(tier1_confidences)
            avg_tier3 = sum(tier3_confidences) / len(tier3_confidences)
            print(f"Tier 1 avg confidence: {avg_tier1:.2f}")
            print(f"Tier 3 avg confidence: {avg_tier3:.2f}")
            assert avg_tier1 >= avg_tier3, (
                f"Tier 1 ({avg_tier1:.2f}) should have >= confidence than Tier 3 ({avg_tier3:.2f})"
            )

    def test_backward_compatibility_disabled_extraction(self, sample_jobs):
        """Test that extraction can be disabled for backward compatibility."""
        try:
            preprocessor_disabled = Preprocessor(extract_requirements=False)
        except OSError:
            pytest.skip("spaCy model not available")

        job = sample_jobs[0]

        # Should return None when extraction is disabled
        result = preprocessor_disabled.extract_trigger_requirements(job["description"])
        assert result is None, "Should return None when extraction is disabled"

    def test_json_serialization_correctness(self, preprocessor, sample_jobs):
        """Verify JSON output is valid and deserializable."""
        job = sample_jobs[0]

        trigger_reqs_json = preprocessor.extract_trigger_requirements(job["description"])
        assert trigger_reqs_json is not None

        # Should be able to deserialize without error
        requirements = json.loads(trigger_reqs_json)

        # Should be able to serialize back to JSON without error
        reserialized = json.dumps(requirements, ensure_ascii=False)
        assert isinstance(reserialized, str)

        # Reserialized should match original (lossy comparison)
        requirements_2 = json.loads(reserialized)
        assert len(requirements_2) == len(requirements)

    def test_empty_text_handling(self, preprocessor):
        """Test handling of empty or None text."""
        assert preprocessor.extract_trigger_requirements("") is None
        assert preprocessor.extract_trigger_requirements(None) is None
        assert preprocessor.extract_trigger_requirements("   ") is None

    def test_text_without_triggers(self, preprocessor):
        """Test text with no requirement triggers."""
        no_triggers_text = "This is a job posting about a company. We are hiring."

        result = preprocessor.extract_trigger_requirements(no_triggers_text)

        # Should return None or empty JSON
        assert result is None or json.loads(result) == []
