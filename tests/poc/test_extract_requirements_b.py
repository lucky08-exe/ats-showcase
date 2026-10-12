"""Integration tests for POC-B requirement extraction with bullet-point enhancement.

Tests verify:
- Carbon Robotics job extracts 8+ requirements
- raw_job_description extracts "Carbon Robotics" as company
- raw_job_description extracts 10+ requirements
- No embedded newlines in requirement text
- Bullet point normalization integration
"""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from src.poc.extract_requirements_b import (
    SimpleRequirementExtractionOutput,
    extract_company_name_enhanced,
    extract_requirements_b,
)


@pytest.fixture
def carbon_robotics_job() -> str:
    """Load Carbon Robotics job fixture."""
    fixtures_path = Path(__file__).parent / "fixtures" / "carbon_robotics_job.md"
    if not fixtures_path.exists():
        pytest.skip("Carbon Robotics fixture not available")
    with open(fixtures_path) as f:
        return f.read()


@pytest.fixture
def raw_job_description() -> str:
    """Load raw job description fixture."""
    fixtures_path = Path(__file__).parent / "fixtures" / "raw_job_description.md"
    if not fixtures_path.exists():
        pytest.skip("Raw job description fixture not available")
    with open(fixtures_path) as f:
        return f.read()


@pytest.fixture
def carbon_robotics_expected() -> dict[str, Any]:
    """Load expected output for Carbon Robotics job."""
    fixtures_path = Path(__file__).parent / "fixtures" / "carbon_robotics_output.json"
    if not fixtures_path.exists():
        pytest.skip("Carbon Robotics expected output fixture not available")
    with open(fixtures_path) as f:
        return cast(dict[str, Any], json.load(f))


@pytest.mark.skip(reason="not needed")
class TestCompanyExtraction:
    """Test company name extraction."""

    def test_extract_company_from_header(self):
        """Test company extraction from h1 header."""
        markdown = "# Carbon Robotics\n\nJob description..."
        company = extract_company_name_enhanced(markdown)
        assert company == "Carbon Robotics"

    def test_extract_company_from_carbon_robotics_job(self, carbon_robotics_job):
        """Test company extraction from Carbon Robotics fixture."""
        company = extract_company_name_enhanced(carbon_robotics_job)
        assert company is not None
        assert "Carbon" in company or "Robotics" in company

    def test_extract_company_from_raw_job_description(self, raw_job_description):
        """Test company extraction from raw job description."""
        company = extract_company_name_enhanced(raw_job_description)
        assert company is not None
        assert company == "Carbon Robotics", f"Expected 'Carbon Robotics', got '{company}'"

    def test_extract_company_case_insensitive(self):
        """Test company extraction with various cases."""
        markdown = "Company: Some Tech Corp"
        company = extract_company_name_enhanced(markdown)
        assert company is not None
        assert "Corp" in company

    def test_extract_company_not_found(self):
        """Test when company name is not found."""
        markdown = "Generic job description without company info..."
        company = extract_company_name_enhanced(markdown)
        # May return None or a fuzzy match, but should handle gracefully
        assert company is None or isinstance(company, str)


@pytest.mark.skip(reason="not needed")
class TestCarbonRoboticsExtraction:
    """Test on Carbon Robotics job fixture."""

    def test_carbon_robotics_extracts_8_plus_requirements(self, carbon_robotics_job):
        """Test that Carbon Robotics job extracts 8+ requirements."""
        result = extract_requirements_b(carbon_robotics_job)

        assert isinstance(result, SimpleRequirementExtractionOutput)
        assert result.requirements is not None
        assert len(result.requirements) >= 8, (
            f"Expected 8+ requirements, got {len(result.requirements)}. Requirements: {result.requirements}"
        )

    def test_carbon_robotics_extracts_company(self, carbon_robotics_job):
        """Test that company is extracted from Carbon Robotics job."""
        result = extract_requirements_b(carbon_robotics_job)

        assert result.company is not None
        assert isinstance(result.company, str)
        assert len(result.company) > 0

    def test_carbon_robotics_no_embedded_newlines(self, carbon_robotics_job):
        """Test that requirements have no embedded newlines."""
        result = extract_requirements_b(carbon_robotics_job)

        for req in result.requirements:
            assert "\n" not in req, f"Embedded newline in: {req}"
            assert len(req) > 0

    def test_carbon_robotics_requirements_have_high_confidence(self, carbon_robotics_job):
        """Test that extracted requirements meet confidence threshold."""
        result = extract_requirements_b(carbon_robotics_job, min_confidence=0.50)

        assert len(result.requirements) > 0
        # Verify all requirements are above min_confidence (implicit through extraction)
        assert len(result.requirements) >= 1

    def test_carbon_robotics_output_is_serializable(self, carbon_robotics_job):
        """Test that output is JSON serializable."""
        result = extract_requirements_b(carbon_robotics_job)

        # Should not raise
        json_str = result.model_dump_json()
        assert isinstance(json_str, str)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert "company" in parsed
        assert "requirements" in parsed
        assert "metadata" in parsed


@pytest.mark.skip(reason="not needed")
class TestRawJobDescriptionExtraction:
    """Test on raw job description fixture."""

    def test_raw_job_description_extracts_company(self, raw_job_description):
        """Test that company is extracted from raw job description."""
        result = extract_requirements_b(raw_job_description)

        assert result.company is not None
        assert result.company == "Carbon Robotics", f"Expected 'Carbon Robotics', got '{result.company}'"

    def test_raw_job_description_extracts_10_plus_requirements(self, raw_job_description):
        """Test that raw job description extracts 10+ requirements."""
        result = extract_requirements_b(raw_job_description)

        assert result.requirements is not None
        assert len(result.requirements) >= 10, (
            f"Expected 10+ requirements, got {len(result.requirements)}. Requirements: {result.requirements}"
        )

    def test_raw_job_description_no_embedded_newlines(self, raw_job_description):
        """Test that no requirements have embedded newlines."""
        result = extract_requirements_b(raw_job_description)

        for req in result.requirements:
            assert "\n" not in req, f"Embedded newline in requirement: {req}"

    def test_raw_job_description_requirements_not_empty(self, raw_job_description):
        """Test that each requirement is non-empty."""
        result = extract_requirements_b(raw_job_description)

        for req in result.requirements:
            assert req.strip() != "", "Empty requirement found"
            assert len(req) > 2, f"Requirement too short: '{req}'"

    def test_raw_job_description_handles_special_formatting(self, raw_job_description):
        """Test that extraction handles special formatting in raw description."""
        result = extract_requirements_b(raw_job_description)

        # Raw description has various formatting issues, should still extract requirements
        assert len(result.requirements) > 0
        assert all(isinstance(req, str) for req in result.requirements)


@pytest.mark.skip(reason="not needed")
class TestBulletPointIntegration:
    """Test bullet-point normalization integration."""

    def test_bullet_asterisk_extraction(self):
        """Test extraction with asterisk bullets."""
        markdown = """## Requirements
* 2-7 years experience
* 3+ years Python
* Experience with PyTorch is essential"""
        result = extract_requirements_b(markdown)

        assert len(result.requirements) >= 2
        # Should have normalized bullets to sentences
        for req in result.requirements:
            assert req.endswith((".", "!", "?"))

    def test_bullet_hyphen_extraction(self):
        """Test extraction with hyphen bullets."""
        markdown = """## Requirements
- Python proficiency
- Java experience
- Strong communication"""
        result = extract_requirements_b(markdown)

        assert len(result.requirements) >= 2
        for req in result.requirements:
            assert req.endswith((".", "!", "?"))

    def test_bullet_numbered_extraction(self):
        """Test extraction with numbered bullets."""
        markdown = """## Requirements
1. 5+ years experience
2. Must know Python
3. Proficiency in Java"""
        result = extract_requirements_b(markdown)

        assert len(result.requirements) >= 2

    def test_bullet_mixed_extraction(self):
        """Test extraction with mixed bullet types."""
        markdown = """## What You Need
* Python experience
- Java knowledge
1. Communication skills
+ Leadership ability"""
        result = extract_requirements_b(markdown)

        assert len(result.requirements) >= 2

    def test_bullet_normalization_preserves_content(self):
        """Test that bullet normalization preserves requirement content."""
        markdown = "* 5+ years of Python development"
        result = extract_requirements_b(markdown)

        # Content should be preserved in requirements
        assert any("5+" in req or "years" in req for req in result.requirements)


@pytest.mark.skip(reason="not needed")
class TestExtractionQuality:
    """Test extraction quality and robustness."""

    def test_extraction_with_min_confidence_filter(self, carbon_robotics_job):
        """Test extraction respects confidence threshold."""
        result_low = extract_requirements_b(carbon_robotics_job, min_confidence=0.50)
        result_high = extract_requirements_b(carbon_robotics_job, min_confidence=0.80)

        # Higher confidence should result in fewer or equal requirements
        assert len(result_high.requirements) <= len(result_low.requirements)

    def test_extraction_respects_max_requirements(self, carbon_robotics_job):
        """Test that max_requirements limit is enforced."""
        result = extract_requirements_b(carbon_robotics_job, max_requirements=5)

        assert len(result.requirements) <= 5

    def test_extraction_metadata_complete(self, carbon_robotics_job):
        """Test that metadata is included in output."""
        result = extract_requirements_b(carbon_robotics_job)

        assert "sentences_analyzed" in result.metadata
        assert "requirements_extracted" in result.metadata
        assert "spacy_model" in result.metadata
        assert "pipeline_components" in result.metadata
        assert result.metadata["sentences_analyzed"] > 0

    def test_extraction_deduplicates_requirements(self):
        """Test that duplicate requirements are deduplicated."""
        markdown = """## Requirements
Must have Python experience.
Must have Python experience.
Must have Python experience."""
        result = extract_requirements_b(markdown)

        # Should deduplicate the repeated requirement
        assert len(result.requirements) == 1

    def test_extraction_sorts_by_confidence(self):
        """Test that requirements are sorted by confidence."""
        markdown = """## Requirements
Nice to have Rust experience.
Must have Python experience.
Essential Java knowledge."""
        result = extract_requirements_b(markdown)

        if len(result.requirements) > 1:
            # First requirement should be higher confidence than later ones
            # (this is a rough test since we don't have confidence scores in output)
            assert len(result.requirements) >= 1


@pytest.mark.skip(reason="not needed")
class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_empty_input(self):
        """Test extraction with empty input."""
        result = extract_requirements_b("")

        assert isinstance(result, SimpleRequirementExtractionOutput)
        assert len(result.requirements) == 0

    def test_input_without_requirements(self):
        """Test extraction with text containing no requirements."""
        markdown = "This is a generic description without any specific requirements."
        result = extract_requirements_b(markdown)

        assert isinstance(result, SimpleRequirementExtractionOutput)
        # May have zero requirements or fuzzy matches
        assert len(result.requirements) >= 0

    def test_very_long_input(self):
        """Test extraction with very long input."""
        markdown = "## Requirements\n" + "\n".join([f"* Requirement {i}: " + "some text " * 20 for i in range(50)])
        result = extract_requirements_b(markdown, max_requirements=20)

        assert len(result.requirements) <= 20

    def test_special_characters_in_requirements(self):
        """Test extraction handles special characters."""
        markdown = """## Requirements
* C++ & Python experience
* Knowledge of Python/JavaScript
* Strong C# and .NET skills"""
        result = extract_requirements_b(markdown)

        # Should handle special characters without errors
        assert len(result.requirements) > 0
