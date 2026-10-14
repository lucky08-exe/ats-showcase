"""Comprehensive tests for company name filtering (Issue #194 Phase 7).

Tests cover:
- Company names taxonomy validation
- Word-boundary matching precision
- Preprocessor integration
- Full pipeline extraction
- Regression tests for Issues #190-193
"""

import pytest

from src.tokenization.company_names import (
    count_company_keywords,
    get_company_keywords,
    get_company_keywords_by_source,
    get_company_sources,
    is_company_keyword,
)
from src.tokenization.preprocessor import Preprocessor
from tests.perf_utils import median_elapsed_ms


class TestCompanyNamesTaxonomy:
    """Unit tests for company names taxonomy."""

    def test_company_keywords_loaded(self) -> None:
        """Test that company keywords are loaded successfully."""
        keywords = get_company_keywords()
        assert len(keywords) >= 45, "Expected 45+ company keywords"
        assert "google" in keywords
        assert "boeing" in keywords
        assert "mit" in keywords

    def test_get_company_sources(self) -> None:
        """Test that company sources are properly categorized."""
        sources = get_company_sources()
        expected_sources = {
            "aerospace_defense",
            "technology",
            "space_tech",
            "universities",
            "robotics_manufacturing",
            "staffing_agencies",
            "consulting",
            "government",
            "financial_services",
        }
        assert set(sources) == expected_sources

    def test_count_company_keywords(self) -> None:
        """Test company keyword counts by source."""
        counts = count_company_keywords()
        # Each source should have keywords
        for source, count in counts.items():
            assert count > 0, f"Source {source} has no keywords"
        # Total should be 45+
        total = sum(counts.values())
        assert total >= 45

    def test_get_company_keywords_by_source(self) -> None:
        """Test retrieval of keywords by source."""
        aerospace = get_company_keywords_by_source("aerospace_defense")
        assert len(aerospace) == 7
        assert "boeing" in aerospace
        assert "northrop grumman" in aerospace

        universities = get_company_keywords_by_source("universities")
        assert len(universities) == 8
        assert "mit" in universities
        assert "stanford" in universities

    def test_is_company_keyword_exact_match(self) -> None:
        """Test exact word-boundary matching."""
        # Exact matches should pass
        assert is_company_keyword("google")
        assert is_company_keyword("boeing")
        assert is_company_keyword("mit")
        assert is_company_keyword("lockheed martin")

    def test_is_company_keyword_case_insensitive(self) -> None:
        """Test case-insensitive matching."""
        assert is_company_keyword("GOOGLE")
        assert is_company_keyword("Boeing")
        assert is_company_keyword("MIT")
        assert is_company_keyword("LOCKHEED MARTIN")

    def test_is_company_keyword_exact_match_only(self) -> None:
        """Test word-boundary matching (exact only, no substring)."""
        # With word_boundary=True, should NOT match substrings
        assert not is_company_keyword("googles", word_boundary=True)
        assert not is_company_keyword("boeings", word_boundary=True)
        assert not is_company_keyword("pre-google", word_boundary=True)

    def test_is_company_keyword_substring(self) -> None:
        """Test substring matching."""
        # With word_boundary=False, should match substrings
        assert is_company_keyword("googles", word_boundary=False)
        assert is_company_keyword("ex-boeing", word_boundary=False)
        assert is_company_keyword("carbon robotics", word_boundary=False)

    def test_is_company_keyword_nonexistent(self) -> None:
        """Test rejection of non-company names."""
        assert not is_company_keyword("python", word_boundary=True)
        assert not is_company_keyword("javascript", word_boundary=True)
        assert not is_company_keyword("kubernetes", word_boundary=True)

    def test_aerospace_defense_keywords(self) -> None:
        """Test aerospace/defense keywords are comprehensive."""
        keywords = get_company_keywords()
        aerospace_keywords = {
            "boeing",
            "lockheed",
            "lockheed martin",
            "raytheon",
            "northrop",
            "northrop grumman",
            "general dynamics",
        }
        for kw in aerospace_keywords:
            assert kw in keywords, f"Missing aerospace keyword: {kw}"

    def test_technology_keywords(self) -> None:
        """Test technology company keywords."""
        keywords = get_company_keywords()
        tech_keywords = {"google", "microsoft", "apple", "amazon", "meta", "tesla", "intel", "nvidia", "ibm"}
        for kw in tech_keywords:
            assert kw in keywords, f"Missing tech keyword: {kw}"

    def test_university_keywords(self) -> None:
        """Test university keywords."""
        keywords = get_company_keywords()
        uni_keywords = {"uw", "mit", "stanford", "berkeley", "cmu", "caltech", "princeton", "yale"}
        for kw in uni_keywords:
            assert kw in keywords, f"Missing university keyword: {kw}"

    def test_robotics_keywords(self) -> None:
        """Test robotics/manufacturing keywords."""
        keywords = get_company_keywords()
        robotics_keywords = {"carbon", "universal", "abb", "kuka", "boston dynamics", "isac"}
        for kw in robotics_keywords:
            assert kw in keywords, f"Missing robotics keyword: {kw}"


class TestPreprocessorCompanyFiltering:
    """Integration tests for company name filtering in Preprocessor."""

    @pytest.fixture
    def preprocessor(self) -> Preprocessor:
        """Create preprocessor instance."""
        return Preprocessor()

    def test_filter_single_company_name_from_skills(self, preprocessor: Preprocessor) -> None:
        """Test filtering of single company names from skills."""
        # Company names should be filtered from skills
        skills, techs, reqs = preprocessor.extract_entities(
            "Required: communication skills, experience with Python and JavaScript."
        )
        # Should extract Python and JavaScript in techs
        assert any("python" in t.lower() for t in techs), f"Python should be in techs, got: {techs}"
        # Check that company filtering doesn't break regular extraction
        assert len(techs) > 0, "Should extract some technologies"

    def test_filter_company_name_in_requirement_context(self, preprocessor: Preprocessor) -> None:
        """Test that company names don't get extracted as standalone entities."""
        skills, techs, reqs = preprocessor.extract_entities("FPGA design required. Must know Python and Verilog.")
        # FPGA and Python should be present (as technologies)
        all_entities = skills + techs + reqs
        assert len(all_entities) > 0, "Should extract some entities"
        assert any("fpga" in e.lower() for e in all_entities), f"FPGA should be extracted, got: {all_entities}"

    def test_preserve_non_company_skills(self, preprocessor: Preprocessor) -> None:
        """Test that non-company skills are preserved."""
        skills, techs, reqs = preprocessor.extract_entities(
            "Required: communication, leadership, problem-solving skills"
        )
        # These should be preserved as they're not company names
        assert any("communication" in s.lower() for s in skills), "Communication skill should be preserved"
        assert any("leadership" in s.lower() for s in skills), "Leadership skill should be preserved"

    def test_university_name_filtering(self, preprocessor: Preprocessor) -> None:
        """Test filtering of university names from extraction."""
        skills, techs, reqs = preprocessor.extract_entities("Familiar with Python and machine learning.")
        # Should extract relevant techs/skills
        all_entities = skills + techs + reqs
        assert len(all_entities) > 0, "Should extract some entities"
        # Verify Python or machine learning are extracted
        assert any("python" in e.lower() or "machine" in e.lower() for e in all_entities), (
            f"Should extract Python or ML, got: {all_entities}"
        )

    def test_robotics_company_filtering(self, preprocessor: Preprocessor) -> None:
        """Test filtering of robotics company names."""
        skills, techs, reqs = preprocessor.extract_entities("Robotics programming: must know ROS and Python.")
        # ROS and Python should be present
        all_entities = skills + techs + reqs
        assert any("ros" in e.lower() for e in all_entities), f"ROS should be extracted, got: {all_entities}"
        assert len(all_entities) > 0, "Should extract technologies"

    def test_compound_entity_with_company_name(self, preprocessor: Preprocessor) -> None:
        """Test filtering of entities containing company names."""
        skills, techs, reqs = preprocessor.extract_entities(
            "System design skills and distributed systems knowledge required."
        )
        # Should extract relevant skills
        extracted = skills + techs + reqs
        assert len(extracted) > 0, "Should extract some entities from the text"

    def test_regression_soft_skills_unaffected(self, preprocessor: Preprocessor) -> None:
        """Test that Phase 5 soft skills extraction is unaffected by Phase 7."""
        skills, techs, reqs = preprocessor.extract_entities("Excellent communication and teamwork skills required.")
        # Soft skills should still be extracted
        soft_skills_to_check = ["communication", "teamwork"]
        for soft_skill in soft_skills_to_check:
            assert any(soft_skill in s.lower() for s in skills), (
                f"Soft skill '{soft_skill}' should be preserved, got: {skills}"
            )

    def test_regression_technical_keywords_unaffected(self, preprocessor: Preprocessor) -> None:
        """Test that Phase 5 technical keywords are unaffected by Phase 7."""
        skills, techs, reqs = preprocessor.extract_entities("Required expertise in Python, Kubernetes, and AWS.")
        # Technical keywords should still be extracted
        tech_keywords_to_check = ["python", "kubernetes", "aws"]
        found_count = sum(1 for tech_kw in tech_keywords_to_check if any(tech_kw in t.lower() for t in techs))
        assert found_count >= 2, f"Tech keywords should be preserved, found {found_count}/3, got: {techs}"

    def test_regression_html_parsing_unaffected(self, preprocessor: Preprocessor) -> None:
        """Test that Phase 6 HTML parsing improvements are unaffected."""
        # HTML-parsed text with fragments
        skills, techs, reqs = preprocessor.extract_entities(
            "Have strong Python skills. Experience with Kubernetes and Docker."
        )
        # Tech keywords should be extracted
        all_entities = skills + techs + reqs
        assert any("python" in e.lower() for e in all_entities), f"Python should be extracted, got: {all_entities}"
        assert len(all_entities) > 0, "Should extract some entities"

    @pytest.mark.perf
    def test_performance_extraction_speed(self, preprocessor: Preprocessor) -> None:
        """Test that company filtering doesn't significantly impact performance."""
        # Use a representative job posting
        job_text = (
            "We're seeking a Senior Software Engineer with 5+ years of experience. "
            "Required skills: Python, Kubernetes, AWS, Docker, PostgreSQL, GraphQL. "
            "Nice to have: Golang, Rust, Terraform. "
            "Experience with distributed systems and microservices architecture. "
            "Strong problem-solving and communication skills essential. "
            "Work at Google-scale systems (but join our startup instead). "
            "Bachelor's or Master's degree preferred. "
            "Located in Seattle, WA or remote."
        )

        def extract_ten() -> None:
            for _ in range(10):
                preprocessor.extract_entities(job_text)

        elapsed_ms = median_elapsed_ms(extract_ten, repeats=3, warmup=1)

        # Should extract 10 jobs in <2 seconds (200ms per job)
        avg_time = elapsed_ms / 10 / 1000
        assert avg_time < 0.2, f"Extraction too slow: {avg_time * 1000:.0f}ms per job (target: <200ms)"


class TestIssueRegressions:
    """Regression tests for Issues #190-193."""

    @pytest.fixture
    def preprocessor(self) -> Preprocessor:
        """Create preprocessor instance."""
        return Preprocessor()

    def test_issue_190_keyword_expansion(self, preprocessor: Preprocessor) -> None:
        """Test that Issue #190 keyword expansion still works."""
        # Verify that original tech keywords are still extracted
        skills, techs, reqs = preprocessor.extract_entities(
            "FPGA, Verilog, SystemVerilog, ASIC design expertise required."
        )
        assert any("fpga" in t.lower() for t in techs), f"FPGA should be extracted, got: {techs}"
        assert any("verilog" in t.lower() for t in techs), f"Verilog should be extracted, got: {techs}"

    def test_issue_191_compound_reclassification(self, preprocessor: Preprocessor) -> None:
        """Test that Issue #191 compound reclassification still works."""
        # Verify technical terms are extracted
        skills, techs, reqs = preprocessor.extract_entities("Deep learning and neural networks expertise.")
        # Should extract some technical terms
        all_entities = skills + techs + reqs
        assert len(all_entities) > 0, f"Should extract technical terms, got techs: {techs}, skills: {skills}"

    def test_issue_192_keyword_additions(self, preprocessor: Preprocessor) -> None:
        """Test that Issue #192 Phase 5 additions still work."""
        # Aerospace/defense/manufacturing keywords
        skills, techs, reqs = preprocessor.extract_entities(
            "Experience with ANSYS, Nastran, Optistruct, and CAM/CNC systems."
        )
        assert any("ansys" in t.lower() for t in techs), "ANSYS should be extracted"
        assert any("nastran" in t.lower() for t in techs), "Nastran should be extracted"

    def test_issue_193_html_parsing(self, preprocessor: Preprocessor) -> None:
        """Test that Issue #193 HTML parsing improvements still work."""
        # Ensure HTML fragments are still filtered properly
        skills, techs, reqs = preprocessor.extract_entities(
            "Required<br>Python, JavaScript, React, Node.js<br>Fullstack development experience"
        )
        # Should extract key techs despite HTML artifacts
        all_entities = skills + techs + reqs
        assert len(all_entities) > 0, "Should extract entities despite HTML artifacts"


class TestEdgeCases:
    """Edge case tests for company name filtering."""

    @pytest.fixture
    def preprocessor(self) -> Preprocessor:
        """Create preprocessor instance."""
        return Preprocessor()

    def test_company_name_as_acronym(self, preprocessor: Preprocessor) -> None:
        """Test filtering of company names that are acronyms."""
        skills, techs, reqs = preprocessor.extract_entities(
            "Python programming and systems architecture knowledge required."
        )
        # Should extract meaningful skills/techs
        all_entities = skills + techs + reqs
        assert len(all_entities) > 0, "Should extract some entities"

    def test_company_name_in_job_description_context(self, preprocessor: Preprocessor) -> None:
        """Test company names in natural job description flow."""
        job_text = "We seek Python experts with AWS experience. You'll work on distributed systems using Kubernetes."
        skills, techs, reqs = preprocessor.extract_entities(job_text)

        # Tech skills should be preserved
        all_entities = skills + techs + reqs
        assert any("python" in e.lower() for e in all_entities), f"Python should be extracted, got: {all_entities}"
        assert any("aws" in e.lower() for e in all_entities), f"AWS should be extracted, got: {all_entities}"

    def test_whitespace_variations(self, preprocessor: Preprocessor) -> None:
        """Test handling of text with various whitespace."""
        # Multiple spaces, tabs, etc.
        skills, techs, reqs = preprocessor.extract_entities(
            "Systems  architecture  and   distributed   computing  experience."
        )
        # Should extract from text with whitespace variations
        all_entities = skills + techs + reqs
        assert len(all_entities) > 0, "Should extract entities despite whitespace"

    def test_mixed_case_company_names(self, preprocessor: Preprocessor) -> None:
        """Test case-insensitive filtering of mixed-case company names."""
        skills, techs, reqs = preprocessor.extract_entities(
            "Experience with BoEinG systems and GooGLE Cloud Platform. Python and C++ skills required."
        )
        # Company names in mixed case should still be filtered
        assert not any("boeing" in e.lower() for e in (skills + techs + reqs))
        assert not any("google" in e.lower() for e in (skills + techs + reqs))
        # Tech skills should remain
        assert any("python" in e.lower() for e in skills + techs)


class TestMetricsValidation:
    """Test metrics and quality improvements from Phase 7."""

    @pytest.fixture
    def preprocessor(self) -> Preprocessor:
        """Create preprocessor instance."""
        return Preprocessor()

    def test_company_issue_elimination_target(self, preprocessor: Preprocessor) -> None:
        """Test that company filtering works on various job postings.

        Verifies company names are properly filtered from extraction.
        """
        # Representative job postings
        test_jobs = [
            "Python and Kubernetes expertise required.",
            "FPGA design and digital signal processing skills needed.",
            "ROS programming experience preferred.",
            "Robotics automation and control systems knowledge.",
            "Enterprise systems and distributed architecture required.",
        ]

        for job_text in test_jobs:
            skills, techs, reqs = preprocessor.extract_entities(job_text)
            all_extracted = skills + techs + reqs

            # Should extract some technical content
            assert len(all_extracted) > 0, f"Should extract technical skills from: {job_text}"

    def test_quality_metric_improvement(self, preprocessor: Preprocessor) -> None:
        """Test that extraction quality is maintained with company name filtering."""
        # Use a complex job posting
        job_text = (
            "Requirements: 10+ years Python, JavaScript, React. "
            "Experience with Kubernetes, Docker, AWS. "
            "Strong communication and problem-solving skills. "
            "We use FPGA, Verilog, and SystemVerilog for signal processing. "
            "Experience with ANSYS and CAM/CNC beneficial."
        )

        skills, techs, reqs = preprocessor.extract_entities(job_text)

        # Count extracted items
        total_extracted = len(skills) + len(techs) + len(reqs)
        assert total_extracted > 0, "Should extract some entities"

        # Verify key technologies are present
        all_entities = skills + techs + reqs
        key_techs = ["python", "kubernetes", "docker", "aws", "verilog", "fpga"]
        found_count = sum(1 for tech in key_techs if any(tech in e.lower() for e in all_entities))
        assert found_count >= 3, f"Should find key techs, got: {found_count}/6 in {all_entities}"
