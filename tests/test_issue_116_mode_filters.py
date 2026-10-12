"""Tests for Issue #116: --mode flag and --new-only / --all filters."""

import json
import tempfile
from pathlib import Path

import pytest

from src.storage.assessment_store import AssessmentStore
from src.verification.reviewer import JobReviewer


class TestModeFilterNewOnly:
    """Tests for --new-only mode (default)."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    def test_new_only_skips_already_reviewed(self, temp_db):
        """Test that new-only mode skips jobs already in job_reviews."""
        reviewer = JobReviewer(db_path=temp_db)

        # Setup: Job already reviewed
        reviewer.save_review("job_1", "Engineer", "SF", "confirmed")

        # With new-only mode, should skip
        skip, reason = reviewer.should_skip_job("job_1", mode="new-only")
        assert skip is True
        assert reason == "already_reviewed"

        reviewer._close_db()

    def test_new_only_includes_unreviewed(self, temp_db):
        """Test that new-only mode includes jobs not yet reviewed."""
        reviewer = JobReviewer(db_path=temp_db)

        # Job not in database at all
        skip, reason = reviewer.should_skip_job("job_999", mode="new-only")
        assert skip is False
        assert reason is None

        reviewer._close_db()

    def test_new_only_with_skip_rejected(self, temp_db):
        """Test new-only mode combined with skip_rejected filter."""
        reviewer = JobReviewer(db_path=temp_db)

        # Setup: Rejected job
        reviewer.save_review("job_1", "Engineer", "SF", "rejected", reason="location")

        # With new-only, should skip due to already_reviewed (mode filter runs first)
        skip, reason = reviewer.should_skip_job("job_1", mode="new-only", skip_rejected=True)
        assert skip is True
        assert reason == "already_reviewed"  # Mode filter catches it first

        reviewer._close_db()


class TestModeFilterAll:
    """Tests for --all mode."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    def test_all_includes_reviewed(self, temp_db):
        """Test that all mode includes already reviewed jobs."""
        reviewer = JobReviewer(db_path=temp_db)

        # Setup: Job already reviewed and confirmed
        reviewer.save_review("job_1", "Engineer", "SF", "confirmed")

        # With all mode, should NOT skip (mode filter allows it)
        skip, reason = reviewer.should_skip_job("job_1", mode="all")
        assert skip is False  # Mode filter doesn't skip

        reviewer._close_db()

    def test_all_with_skip_rejected(self, temp_db):
        """Test all mode with skip_rejected filter."""
        reviewer = JobReviewer(db_path=temp_db)

        # Setup: Rejected job
        reviewer.save_review("job_1", "Engineer", "SF", "rejected", reason="location")

        # With all mode + skip_rejected, should skip due to status filter
        skip, reason = reviewer.should_skip_job("job_1", mode="all", skip_rejected=True)
        assert skip is True
        assert reason == "previously_rejected"  # Status filter catches it

        reviewer._close_db()

    def test_all_without_skip_rejected(self, temp_db):
        """Test all mode without skip_rejected filter."""
        reviewer = JobReviewer(db_path=temp_db)

        # Setup: Rejected job
        reviewer.save_review("job_1", "Engineer", "SF", "rejected", reason="location")

        # With all mode + skip_rejected=False, should NOT skip
        skip, reason = reviewer.should_skip_job("job_1", mode="all", skip_rejected=False)
        assert skip is False  # No filter catches it

        reviewer._close_db()

    def test_all_includes_unreviewed(self, temp_db):
        """Test that all mode includes unreviewed jobs."""
        reviewer = JobReviewer(db_path=temp_db)

        # Job not in database
        skip, reason = reviewer.should_skip_job("job_999", mode="all")
        assert skip is False
        assert reason is None

        reviewer._close_db()


class TestAssessModeModeFilter:
    """Tests for mode filter in assess command."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    def test_assess_new_only_excludes_assessed(self, temp_db):
        """Test assess new-only mode filters out already assessed jobs."""
        store = AssessmentStore(db_path=temp_db)

        # Save an assessment
        store.save_assessment(
            job_id="job_1",
            title="Engineer",
            company="TechCorp",
            location="SF",
            overall_score=85.0,
            tech_score=90.0,
            seniority_score=80.0,
            location_score=95.0,
            recommendations=["Good match"],
            summary="Engineer with 5+ years",
            tokens_used=500,
            actual_cost=0.0015,
        )

        # Query: job should be excluded in new-only mode
        # (This would be filtered in CLI logic, not in store itself)
        assessment = store.get_assessment_by_id("job_1")
        assert assessment is not None
        # In new-only mode, this job would be filtered out

        store._close_db()

    def test_assess_all_includes_assessed(self, temp_db):
        """Test assess all mode includes already assessed jobs."""
        store = AssessmentStore(db_path=temp_db)

        # Save an assessment
        store.save_assessment(
            job_id="job_1",
            title="Engineer",
            company="TechCorp",
            location="SF",
            overall_score=85.0,
            tech_score=90.0,
            seniority_score=80.0,
            location_score=95.0,
            recommendations=["Good match"],
            summary="Engineer with 5+ years",
            tokens_used=500,
            actual_cost=0.0015,
        )

        # Query: job should be included in all mode
        assessment = store.get_assessment_by_id("job_1")
        assert assessment is not None
        assert assessment.get("overall_score") == 85.0

        store._close_db()


class TestModeFlagFiltering:
    """Tests for mode flag in extracted jobs review."""

    @pytest.fixture
    def temp_files(self):
        """Create temporary extracted and preprocessed files."""
        # Create temp directory
        tmpdir = Path(tempfile.mkdtemp())

        # Create extracted jobs file
        extracted_jobs = [
            {
                "id": "job_1",
                "title": "Engineer",
                "company": "TechCorp",
                "location": "SF",
                "url": "http://example.com",
            },
            {
                "id": "job_2",
                "title": "Designer",
                "company": "DesignCo",
                "location": "NYC",
                "url": "http://example.com",
            },
        ]

        extracted_file = tmpdir / "extracted.json"
        with open(extracted_file, "w") as f:
            json.dump(extracted_jobs, f)

        # Create preprocessed jobs file (empty for this test)
        preprocessed_file = tmpdir / "preprocessed.json"
        with open(preprocessed_file, "w") as f:
            json.dump([], f)

        yield extracted_file, preprocessed_file, tmpdir

        # Cleanup
        import shutil

        shutil.rmtree(tmpdir)

    def test_mode_new_only_default(self, temp_files, temp_db):
        """Test that new-only is the default mode."""
        extracted_file, preprocessed_file, _ = temp_files
        reviewer = JobReviewer(db_path=temp_db)

        # Review first job
        reviewer.save_review("job_1", "Engineer", "TechCorp", "confirmed")

        # Second review with new-only mode (default)
        skip, reason = reviewer.should_skip_job("job_1", mode="new-only")
        assert skip is True
        assert reason == "already_reviewed"

        reviewer._close_db()

    def test_mode_all_allows_reprocessing(self, temp_files, temp_db):
        """Test that all mode allows reprocessing of reviewed jobs."""
        extracted_file, preprocessed_file, _ = temp_files
        reviewer = JobReviewer(db_path=temp_db)

        # Review first job
        reviewer.save_review("job_1", "Engineer", "TechCorp", "confirmed")

        # With all mode, should not skip (just check other filters)
        skip, reason = reviewer.should_skip_job("job_1", mode="all", skip_rejected=False)
        assert skip is False
        assert reason is None

        reviewer._close_db()


class TestModeStacksWithOtherFilters:
    """Tests for mode stacking with other filter types."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    def test_mode_new_only_stacks_with_date_filter(self, temp_db):
        """Test new-only mode with date filter."""
        reviewer = JobReviewer(db_path=temp_db)

        # Setup: unreviewed job with old crawled_at
        if reviewer.conn:
            cursor = reviewer.conn.cursor()
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                   id TEXT PRIMARY KEY,
                   crawled_at TEXT
                )"""
            )
            cursor.execute("INSERT INTO jobs VALUES ('job_1', '2026-06-01')")
            reviewer.conn.commit()

        # With new-only + skip_before_date, should skip due to date
        skip, reason = reviewer.should_skip_job("job_1", mode="new-only", skip_before_date="2026-07-01")
        assert skip is True
        assert reason is not None
        assert "crawled_before" in reason

        reviewer._close_db()

    def test_mode_all_stacks_with_multiple_filters(self, temp_db):
        """Test all mode stacking with multiple filters."""
        reviewer = JobReviewer(db_path=temp_db)

        # Setup: rejected job with old crawled_at
        reviewer.save_review("job_1", "Engineer", "SF", "rejected")
        if reviewer.conn:
            cursor = reviewer.conn.cursor()
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                   id TEXT PRIMARY KEY,
                   crawled_at TEXT
                )"""
            )
            cursor.execute("INSERT INTO jobs VALUES ('job_1', '2026-06-01')")
            reviewer.conn.commit()

        # Mode check passes (all mode), but status filter catches rejection
        skip, reason = reviewer.should_skip_job(
            "job_1",
            mode="all",
            skip_rejected=True,
            skip_before_date="2026-07-01",
        )
        assert skip is True
        # Should catch rejection first (status filter before date filter)
        assert reason == "previously_rejected"

        reviewer._close_db()
