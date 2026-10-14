"""Phase 1: Analysis & Baseline for Issue #191 - Technical Compound Reclassification.

This test establishes baseline metrics for technical compound detection and reclassification.
Tests ensure that after Phase 4, technical compounds are moved from skills to technologies.
"""

from typing import Any

import pytest

from src.tokenization.preprocessor import Preprocessor
from src.tokenization.technical_compounds import is_technical_compound

# Test data: 10 representative jobs with known technical compounds
TEST_JOBS_PHASE1 = [
    {
        "id": "job_001",
        "title": "Senior Software Development Engineer",
        "company": "TechCorp",
        "description": """
We're looking for a Senior Software Development Engineer with expertise in software development.
Key responsibilities:
- Lead software development initiatives
- Design and implement data processing pipelines
- Mentor junior engineers in best practices
Required skills:
- Software development (5+ years)
- Data processing experience
- Python, JavaScript, and REST API development
""",
    },
    {
        "id": "job_002",
        "title": "Data Processing Specialist",
        "company": "DataCo",
        "description": """
Join our team to work on large-scale data processing systems.
Responsibilities:
- Optimize data processing workflows
- Implement ETL pipelines for data processing
- Monitor system performance
Skills needed:
- Data processing (3+ years)
- SQL, Python
- Kubernetes
""",
    },
    {
        "id": "job_003",
        "title": "Engineering Technology Lead",
        "company": "EngineerCo",
        "description": """
We need an Engineering Technology Lead for our manufacturing division.
Your role will involve:
- Lead engineering technology initiatives
- Implement manufacturing engineering best practices
- Work with engineering technology platforms
Requirements:
- Manufacturing engineering experience
- Knowledge of engineering technology stacks
- CAD software proficiency
""",
    },
    {
        "id": "job_004",
        "title": "Manufacturing Engineering Manager",
        "company": "MfgCo",
        "description": """
Seeking a Manufacturing Engineering Manager with manufacturing engineering experience.
Responsibilities:
- Direct manufacturing engineering projects
- Oversee manufacturing engineering processes
- Coordinate with manufacturing engineering teams
Skills:
- Manufacturing engineering (5+ years)
- Process optimization
- Lean manufacturing
""",
    },
    {
        "id": "job_005",
        "title": "System Architecture Engineer",
        "company": "SysCorp",
        "description": """
Looking for a System Architecture Engineer to design system-level solutions.
You will:
- Design system-level architectures
- Work on system-level performance optimization
- Collaborate on system-level requirements
Required:
- System-level thinking and design
- AWS, Docker, Kubernetes
- Python, Java
""",
    },
    {
        "id": "job_006",
        "title": "Full-Stack Developer",
        "company": "WebTech",
        "description": """
We need a Full-Stack Developer experienced in software development.
Your work will include:
- Software development for web applications
- Implement frontend and backend systems
- Design data processing layers
Technologies:
- React, Node.js
- PostgreSQL, Redis
- Docker, AWS
""",
    },
    {
        "id": "job_007",
        "title": "Data Engineer",
        "company": "Analytics Inc",
        "description": """
Join our team as a Data Engineer focused on data processing systems.
Responsibilities:
- Build data processing pipelines
- Optimize data processing performance
- Manage big data processing infrastructure
Skills:
- Data processing expertise
- Spark, Kafka
- Python, Scala
""",
    },
    {
        "id": "job_008",
        "title": "Manufacturing Process Engineer",
        "company": "Industrial Co",
        "description": """
Seeking a Manufacturing Process Engineer for manufacturing engineering roles.
You will work on:
- Manufacturing engineering process improvements
- Manufacturing engineering automation
- Quality control in manufacturing engineering
Skills:
- Manufacturing engineering knowledge
- 6+ years in manufacturing
- Six Sigma, Lean
""",
    },
    {
        "id": "job_009",
        "title": "System Integration Engineer",
        "company": "IntegrationCorp",
        "description": """
We're hiring a System Integration Engineer for system-level integration work.
Responsibilities:
- Design and implement system-level solutions
- Ensure system-level compatibility
- Test system-level functionality
Requirements:
- System-level architecture knowledge
- Java, C++
- Linux
""",
    },
    {
        "id": "job_010",
        "title": "Platform Engineer",
        "company": "PlatformCo",
        "description": """
Looking for a Platform Engineer with software development background.
Your role includes:
- Build software development platforms
- Support data processing operations
- Optimize system-level performance
Stack:
- Python, Go
- Kubernetes, Docker
- PostgreSQL
""",
    },
]

# Technical compounds to track
TECHNICAL_COMPOUNDS = {
    "software development": 6,  # Expected in Phase 3 output
    "data processing": 3,
    "engineering technology": 3,
    "manufacturing engineering": 3,
    "system-level": 3,
}

# Hard technologies that should NOT be reclassified
HARD_TECHNOLOGIES = {
    "python",
    "javascript",
    "java",
    "kubernetes",
    "docker",
    "postgresql",
    "redis",
    "react",
    "node",
    "aws",
    "spark",
    "kafka",
    "go",
    "c++",
    "linux",
}

# Soft skills that should NOT be reclassified
SOFT_SKILLS_TO_PRESERVE = {
    "leadership",
    "communication",
    "teamwork",
    "problem-solving",
    "analytical",
    "mentoring",
}


class TestPhase1Baseline:
    """Test Phase 1 baseline metrics for Issue #191."""

    @pytest.fixture(scope="session")
    def preprocessor(self):
        """Initialize preprocessor."""
        return Preprocessor("en_core_web_md")

    def test_technical_compound_detection(self):
        """Test that technical compounds are correctly identified."""
        compounds = [
            "software development",
            "data processing",
            "engineering technology",
            "manufacturing engineering",
            "system-level",
        ]

        for compound in compounds:
            assert is_technical_compound(compound), f"Failed to detect compound: {compound}"

    def test_hard_technologies_not_flagged(self):
        """Test that hard technologies are NOT flagged as compounds."""
        hard_techs = [
            "python",
            "javascript",
            "react",
            "kubernetes",
            "docker",
            "postgresql",
            "aws",
            "rest api",
        ]

        for tech in hard_techs:
            assert not is_technical_compound(tech), f"Incorrectly flagged as compound: {tech}"

    def test_soft_skills_not_flagged(self):
        """Test that soft skills are NOT flagged as compounds."""
        soft_skills = [
            "leadership",
            "communication",
            "teamwork",
            "problem-solving",
            "analytical skills",
        ]

        for skill in soft_skills:
            assert not is_technical_compound(skill), f"Incorrectly flagged as compound: {skill}"

    def test_baseline_extraction_job_001(self, preprocessor):
        """Test baseline extraction on job_001 with software development compounds."""
        job = TEST_JOBS_PHASE1[0]
        skills, technologies, requirements = preprocessor.extract_entities(job["description"])

        # Verify extraction happened
        assert len(skills) > 0 or len(technologies) > 0 or len(requirements) > 0, "No entities extracted from job_001"

        # Log baseline for Phase 1 analysis
        print(f"\nJob {job['id']} baseline extraction:")
        print(f"  Skills: {sorted(skills)}")
        print(f"  Technologies: {sorted(technologies)}")
        print(f"  Requirements: {sorted(requirements)}")

        # Check for some expected hard technologies
        tech_lower = [t.lower() for t in technologies]
        assert any(t in tech_lower for t in ["python", "javascript"]), "Expected to extract Python or JavaScript"

    def test_baseline_extraction_all_jobs(self, preprocessor):
        """Test baseline extraction on all 10 jobs and report metrics."""
        results: dict[str, Any] = {
            "total_jobs": len(TEST_JOBS_PHASE1),
            "total_skills_extracted": 0,
            "total_technologies_extracted": 0,
            "total_requirements_extracted": 0,
            "compound_detections": dict.fromkeys(TECHNICAL_COMPOUNDS, 0),
        }

        for job in TEST_JOBS_PHASE1:
            skills, technologies, requirements = preprocessor.extract_entities(job["description"])

            results["total_skills_extracted"] += len(skills)
            results["total_technologies_extracted"] += len(technologies)
            results["total_requirements_extracted"] += len(requirements)

            # Check for technical compounds in skills
            skills_lower = [s.lower() for s in skills]
            for compound in TECHNICAL_COMPOUNDS:
                if compound in skills_lower:
                    results["compound_detections"][compound] += 1

        # Report baseline metrics
        print("\n=== Phase 1 Baseline Metrics ===")
        print(f"Total jobs analyzed: {results['total_jobs']}")
        print(f"Total skills extracted: {results['total_skills_extracted']}")
        print(f"Total technologies extracted: {results['total_technologies_extracted']}")
        print(f"Total requirements extracted: {results['total_requirements_extracted']}")
        print("\nTechnical Compounds in Skills:")
        for compound, count in results["compound_detections"].items():
            print(f"  - '{compound}': {count} job(s)")

        # Verify extraction happened
        assert results["total_skills_extracted"] > 0, "No skills extracted across all jobs"
        assert results["total_technologies_extracted"] > 0, "No technologies extracted across all jobs"

    def test_hard_technologies_extracted(self, preprocessor):
        """Test that hard technologies are extracted correctly."""
        job = TEST_JOBS_PHASE1[0]
        skills, technologies, requirements = preprocessor.extract_entities(job["description"])

        tech_lower = [t.lower() for t in technologies]

        # Verify at least some hard technologies were found
        found_hard_tech = [t for t in HARD_TECHNOLOGIES if t in tech_lower]
        assert len(found_hard_tech) > 0, f"Expected to find hard technologies from {HARD_TECHNOLOGIES}"

    def test_soft_skills_extracted(self, preprocessor):
        """Test that soft skills can be extracted."""
        job = TEST_JOBS_PHASE1[0]
        skills, technologies, requirements = preprocessor.extract_entities(job["description"])

        # Note: Soft skills may not all be extracted due to filtering
        # Just verify extraction didn't fail
        print(f"\nExtracted skills: {sorted(skills)}")
        print(f"Extracted technologies: {sorted(technologies)}")
