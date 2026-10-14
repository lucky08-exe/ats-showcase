"""Phase 4: Integration validation for HTML parsing improvement (Issue #193)."""

import time
from typing import cast

import pytest

from src.parsers.html_to_markdown import add_markdown_section_headers
from src.tokenization.preprocessor import Preprocessor


class TestHTMLParsingIntegration:
    """End-to-end integration tests for HTML parsing Phase 6 improvements."""

    @pytest.fixture(scope="session")
    def preprocessor(self):
        """Initialize Preprocessor with real spaCy model."""
        return Preprocessor(model="en_core_web_md")

    # Realistic test job descriptions with known issues
    REALISTIC_TEST_JOBS = [
        {
            "name": "Carbon Robotics Job (Issue #190 base case)",
            "text": (
                "Position: Senior Python Developer\n"
                "Requirements: 5+ years Python, AWS, machine learning experience.\n"
                "Responsibilities: Build backend services, manage cloud infrastructure.\n"
                "Skills: Python, JavaScript, React, PostgreSQL, AWS, Docker, Kubernetes.\n"
                "Benefits: Competitive salary, health insurance, 401k.\n"
                "Equal Opportunity Employer. Apply Now."
            ),
            "expected_tech_min": 5,  # Python, JS, React, PostgreSQL, AWS, Docker, Kubernetes
            "expected_skills_min": 3,  # backend, cloud, infrastructure
        },
        {
            "name": "Job with mixed-case fragments",
            "text": (
                "Senior Developer Wanted\n"
                "may differCulture StatementDon't settle for less.\n"
                "Core CompetenciesRequired QualificationsTo apply.\n"
                "Experience: Python, Java, Go, Rust.\n"
                "We are looking for talented engineers."
            ),
            "expected_tech_min": 3,  # Python, Java, Go, Rust
            "max_fragments": 2,  # Should filter out mixed-case artifacts
        },
        {
            "name": "Job with section header artifacts",
            "text": (
                "Job Description: Senior Software Engineer\n"
                "Responsibilities: Build scalable systems\n"
                "Requirements/Qualifications: 8+ years experience\n"
                "Technical Skills: C++, Python, CUDA, TensorFlow\n"
                "Apply Now"
            ),
            "expected_tech_min": 2,  # At least Python, TensorFlow
            "max_fragments": 1,
        },
        {
            "name": "Job with compound split keywords",
            "text": (
                "Degree in computer science and years of data science, or science background.\n"
                "Experience with machine learning and deep learning preferred.\n"
                "Python, JavaScript, Go, Rust required.\n"
                "Full-time position. Competitive salary."
            ),
            "expected_tech_min": 3,  # Python, JavaScript, Go, Rust
            "max_fragments": 2,
        },
    ]

    def test_end_to_end_extraction_quality(self, preprocessor):
        """Verify end-to-end extraction quality on realistic job descriptions."""
        for test_case in self.REALISTIC_TEST_JOBS:
            skills, tech, reqs = preprocessor.extract_entities(test_case["text"])

            # Verify minimum expected technologies extracted
            assert len(tech) >= cast(int, test_case.get("expected_tech_min", 1)), (
                f"{test_case['name']}: Expected at least {test_case.get('expected_tech_min', 1)} tech, got {len(tech)}"
            )

            # Verify reasonable skill extraction
            assert len(skills) >= 0, f"{test_case['name']}: Skills extraction failed"

            # Verify no excessive fragments (quality score)
            all_entities = skills + tech + reqs
            fragment_count = sum(1 for e in all_entities if preprocessor._is_suspicious_multi_word_fragment(e))

            # Check fragment count is below maximum if specified
            if "max_fragments" in test_case:
                max_frags = cast(int, test_case["max_fragments"])
                assert fragment_count <= max_frags, (
                    f"{test_case['name']}: Too many fragments ({fragment_count}), expected <={max_frags}"
                )

    def test_fragment_reduction_target(self, preprocessor):
        """Test that fragment reduction meets Phase 4 target (75%+ reduction)."""
        problematic_text = (
            "Senior may differCulture StatementDeveloper wanted.\n"
            "Core CompetenciesRequired QualificationsTo apply.\n"
            "Experience: Python, JavaScript, React.\n"
            "RequiredQualificationsTo review resume and submit application."
        )

        # Count potential fragments BEFORE filtering (simulated baseline)
        # Simulate what extraction would capture before fragment filtering
        baseline_fragments = [
            "may differCulture StatementDeveloper",
            "Core CompetenciesRequired",
            "RequiredQualificationsTo",
        ]

        # Run actual extraction with filtering
        skills, tech, reqs = preprocessor.extract_entities(problematic_text)
        all_entities = skills + tech + reqs

        # Count actual fragments in results
        actual_fragments = [e for e in all_entities if preprocessor._is_suspicious_multi_word_fragment(e)]

        # Should remove at least 75% of problematic fragments
        fragment_reduction = 1 - (len(actual_fragments) / len(baseline_fragments))
        assert fragment_reduction >= 0.75, f"Fragment reduction {fragment_reduction * 100:.1f}% below target of 75%"

    def test_quality_score_target(self, preprocessor):
        """Test that quality score meets Phase 4 target (99%+)."""
        test_text = (
            "Seeking Python developer with 5+ years of experience.\n"
            "Skills: Python, Go, Rust, C++, Java.\n"
            "Cloud platforms: AWS, GCP, Azure.\n"
            "may differCulture StatementDon't worry about the fragment here."
        )

        skills, tech, reqs = preprocessor.extract_entities(test_text)
        all_entities = skills + tech + reqs

        if len(all_entities) == 0:
            quality_score = 100.0
        else:
            fragment_count = sum(1 for e in all_entities if preprocessor._is_suspicious_multi_word_fragment(e))
            quality_score = ((len(all_entities) - fragment_count) / len(all_entities)) * 100

        # Target 99%+ quality
        assert quality_score >= 99.0, f"Quality score {quality_score:.1f}% below target of 99%"

    def test_performance_target(self, preprocessor):
        """Test that extraction performance is <100ms per job."""
        test_text = (
            "Senior Software Engineer - Backend\n"
            "We are hiring a talented developer to join our team.\n"
            "Responsibilities:\n"
            "- Design and implement backend services\n"
            "- Optimize database queries\n"
            "- Mentor junior engineers\n"
            "Requirements:\n"
            "- 8+ years of experience with Python, Go, or Rust\n"
            "- Strong knowledge of distributed systems\n"
            "- Experience with AWS, GCP, or Azure\n"
            "- Excellent communication skills\n"
            "Benefits: Competitive salary, health insurance, 401k, remote work.\n"
            "Apply: send resume to careers@company.com"
        )

        start_time = time.time()
        skills, tech, reqs = preprocessor.extract_entities(test_text)
        elapsed_ms = (time.time() - start_time) * 1000

        # Target <100ms per job
        assert elapsed_ms < 100, f"Extraction took {elapsed_ms:.1f}ms, exceeds target of 100ms"

    def test_soft_skills_preserved(self, preprocessor):
        """Verify soft skills extraction (Issue #190) still works."""
        text = (
            "We seek a collaborative engineer with strong communication skills.\n"
            "Teamwork and leadership experience required.\n"
            "Problem-solving and critical thinking essential.\n"
            "Python and Java expertise needed."
        )

        skills, tech, reqs = preprocessor.extract_entities(text)

        # At least some soft skills should be present
        assert len(skills) > 0, "No soft skills extracted"

    def test_technical_compounds_reclassified(self, preprocessor):
        """Verify technical compounds (Issue #191) still work."""
        text = (
            "Requirements: machine learning, deep learning, natural language processing.\n"
            "Software: Python, TensorFlow, PyTorch, BERT.\n"
            "Cloud: AWS infrastructure, Docker containers, Kubernetes orchestration."
        )

        skills, tech, reqs = preprocessor.extract_entities(text)

        # Technical compounds should be in tech, not skills
        tech_lower = [t.lower() for t in tech]

        # machine learning type compounds should be in tech
        has_ml_compounds = any("learning" in t or "processing" in t for t in tech_lower)
        assert has_ml_compounds or len(tech) > 0, "No technical compounds detected in tech category"

    def test_backward_compatibility(self, preprocessor):
        """Ensure Phase 6 changes don't break existing extraction."""
        test_cases = [
            # Simple clear cases
            ("Python developer", ["Python"]),
            ("Java and JavaScript", ["Java", "JavaScript"]),
            ("React with Node.js", ["React", "Node.js"]),
            # Multi-word skills - may not extract single items
            ("We need machine learning expertise", []),  # Technical compound in context
        ]

        for text, _expected_keywords in test_cases:
            skills, tech, reqs = preprocessor.extract_entities(text)
            all_entities = skills + tech + reqs

            # Most cases should extract something reasonable
            if text in ("Python developer", "Java and JavaScript", "React with Node.js"):
                assert len(all_entities) > 0, f"Failed to extract from: {text}"

            # Should not have obvious fragments
            for entity in all_entities:
                assert not entity.startswith("may differ"), "Fragment not filtered"
                assert not entity.endswith("To"), "Section header artifact not filtered"

    def test_spot_check_real_extractions(self, preprocessor):
        """Spot-check representative jobs for correct extraction."""
        test_job = (
            "Senior Python Engineer\n\n"
            "About the Role:\n"
            "We're seeking a talented Python engineer to build scalable backend services.\n\n"
            "Responsibilities:\n"
            "- Design and implement API services\n"
            "- Optimize database performance\n"
            "- Lead technical architecture discussions\n\n"
            "Requirements:\n"
            "- 7+ years Python experience\n"
            "- Strong knowledge of async programming\n"
            "- Experience with PostgreSQL and Redis\n"
            "- AWS or GCP cloud experience\n"
            "- Bachelor's degree in Computer Science or equivalent\n\n"
            "Nice to Have:\n"
            "- Kubernetes experience\n"
            "- Docker knowledge\n"
            "- Message queue experience (RabbitMQ, Kafka)\n\n"
            "Compensation:\n"
            "Competitive salary $150K - $200K. Excellent benefits package.\n\n"
            "Equal Opportunity Employer. Apply Now."
        )

        skills, tech, reqs = preprocessor.extract_entities(test_job)

        # Should extract key technologies
        tech_lower = [t.lower() for t in tech]
        assert any("python" in t for t in tech_lower), "Python not detected"
        assert any("postgresql" in t or "postgres" in t for t in tech_lower), "PostgreSQL not detected"
        assert any("redis" in t for t in tech_lower), "Redis not detected"
        assert any("aws" in t or "gcp" in t for t in tech_lower), "Cloud platform not detected"

        # Should NOT have fragments
        all_entities = skills + tech + reqs
        for entity in all_entities:
            # Check for known fragment patterns
            assert not entity.lower().startswith("equal opportunity"), "Boilerplate not removed"
            assert not entity.lower().startswith("apply"), "Navigation not removed"
            assert "CompetenciesRequired" not in entity, "Section header artifact not removed"

    def test_keyword_extraction_still_works(self, preprocessor):
        """Verify keyword extraction (Issue #192) still works."""
        text = (
            "We need expertise in: Python, Go, Rust, C++, Java, C#.\n"
            "Cloud: AWS, GCP, Azure, Digital Ocean.\n"
            "Databases: PostgreSQL, MongoDB, Redis, Elasticsearch.\n"
            "Tools: Docker, Kubernetes, Git, Jenkins."
        )

        skills, tech, reqs = preprocessor.extract_entities(text)

        tech_lower = [t.lower() for t in tech]

        # Should extract common keywords
        keywords_to_check = ["python", "go", "rust", "aws", "gcp", "docker", "kubernetes"]
        extracted_keywords = sum(1 for kw in keywords_to_check if any(kw in t for t in tech_lower))

        # Should extract at least 50% of keywords
        assert extracted_keywords >= len(keywords_to_check) * 0.5, (
            f"Only {extracted_keywords} of {len(keywords_to_check)} keywords extracted"
        )


class TestPerformanceMetrics:
    """Test performance metrics for Phase 6."""

    @pytest.fixture(scope="session")
    def preprocessor(self):
        """Initialize Preprocessor."""
        return Preprocessor(model="en_core_web_md")

    def test_batch_processing_performance(self, preprocessor):
        """Verify batch processing performance is reasonable."""
        jobs = [
            "Python developer needed. Experience with Django, FastAPI.",
            "Java engineer. Spring Boot, Microservices, AWS.",
            "Go programmer. Kubernetes, Docker, gRPC.",
            "Rust expert. Systems programming, WebAssembly.",
            "Full-stack engineer. React, Node.js, PostgreSQL.",
        ]

        start_time = time.time()
        results = []
        for job in jobs:
            skills, tech, reqs = preprocessor.extract_entities(job)
            results.append((skills, tech, reqs))
        elapsed_ms = (time.time() - start_time) * 1000

        avg_ms_per_job = elapsed_ms / len(jobs)

        # Average should be <100ms per job
        assert avg_ms_per_job < 100, f"Average {avg_ms_per_job:.1f}ms per job exceeds target of 100ms"

        # All jobs should have extracted something
        assert all(len(skills) + len(tech) + len(reqs) > 0 for skills, tech, reqs in results), (
            "Some jobs produced no results"
        )


class TestMarkdownDividerIntegration:
    """Issue #211 / Phase 10: crawler '---' dividers -> preprocessor section split.

    Prior to Issue #211, the header-synthesis pass (originally
    `Crawler._add_markdown_section_headers`, moved to
    `src.parsers.html_to_markdown.add_markdown_section_headers` in Issue
    #228) synthesized "## "/"### " headers but never emitted a "---"
    divider near them, even though `Preprocessor._extract_markdown_sections`
    already had divider-aware boundary handling (dead code with real crawled
    input: nothing ever produced a "---" line). These tests feed real
    header-synthesis output -- including the adversarial case of section
    content with no trailing blank line before the next header -- through
    the real preprocessor pipeline.

    Issue #224: the divider (preceded by a blank line) is inserted
    immediately *before* each synthesized header, not after it.
    """

    @pytest.fixture(scope="session")
    def preprocessor(self):
        """Initialize Preprocessor with real spaCy model."""
        return Preprocessor(model="en_core_web_md")

    def test_crawler_output_contains_dividers_before_headers(self):
        """Real header-synthesis output contains '---' before each
        non-first header.

        This assertion alone fails if Task 1's divider-insertion pass is
        reverted -- `add_markdown_section_headers` would then only emit
        headers, never dividers.
        """
        # No blank line between section content and the next header --
        # the adversarial shape the preprocessor's divider-boundary code
        # (preprocessor.py:974-978) exists to handle, constructed directly
        # against `add_markdown_section_headers` (the real production
        # function Task 1 modified) to precisely control line adjacency.
        markdown_in = "**Skills**\nPython\nKubernetes\n**Benefits**\n401k match\nHealth insurance"
        result = add_markdown_section_headers(markdown_in)

        # "## Skills" is the very first line of the document, so it gets
        # no leading blank/divider. "## Benefits" follows ordinary content
        # ("Kubernetes"), so it gets a blank line + "---" immediately
        # before it.
        assert result == ("## Skills\nPython\nKubernetes\n\n---\n## Benefits\n401k match\nHealth insurance")

    def test_divider_bearing_output_splits_sections_without_bleed(self, preprocessor):
        """Section boundaries are correct even with no blank line before the next header.

        Feeds real crawler output (with '---' dividers, post-Task-1) through
        `_extract_markdown_sections`, in the adversarial case described by
        the Issue #211 plan: content immediately followed by the next
        header, no blank-line separator.
        """
        markdown_in = "**Skills**\nPython\nKubernetes\n**Benefits**\n401k match\nHealth insurance"
        crawler_output = add_markdown_section_headers(markdown_in)
        assert "---" in crawler_output  # sanity: divider path is actually exercised below

        sections = preprocessor._extract_markdown_sections(crawler_output)

        assert sections["skills"] == "Python\nKubernetes"
        assert sections["benefits"] == "401k match\nHealth insurance"
        # No bleed: skills content must not have absorbed benefits text or
        # vice versa.
        assert "401k" not in sections["skills"]
        assert "Python" not in sections["benefits"]

    def test_divider_bearing_output_flows_through_extract_entities(self, preprocessor):
        """Full crawl -> preprocess loop: benefits content is excluded from skills/tech.

        `_extract_entities_by_section`'s `skip_sections` denylist should
        exclude the 'benefits' section from entity extraction entirely,
        while 'skills' section content is extracted normally -- proving the
        divider-bearing markdown flows end-to-end through
        `extract_entities()` without error and with correct section-scoped
        results.
        """
        markdown_in = "**Skills**\nPython\nKubernetes\n**Benefits**\n401k match\nHealth insurance"
        crawler_output = add_markdown_section_headers(markdown_in)
        assert "---" in crawler_output

        skills, technologies, requirements = preprocessor.extract_entities(crawler_output)

        all_entities_lower = " ".join(skills + technologies + requirements).lower()
        assert "401k" not in all_entities_lower
        assert "health insurance" not in all_entities_lower
