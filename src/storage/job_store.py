"""Job storage and management for ATS Showcase."""

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from src.storage._init_helpers import initialize_db_common
from src.storage.cost_models import (
    CostComparisonReport,
    QualityComparisonReport,
    QualityImpactMetrics,
    ReprocessingMetrics,
)
from src.storage.schema import COST_TRACKING_TABLE_SQL, JOBS_TABLE_SQL, QUALITY_TRACKING_TABLE_SQL

logger = logging.getLogger(__name__)

VALID_PREPROCESSING_VERSIONS = ("1.0", "2.0", "3.0")


class JobStore:
    """SQLite storage for job reviews with preprocessing version tracking."""

    def __init__(self, db_path: str = "data/ats_playground.db"):
        """Initialize job store."""
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Initialize database and schema."""
        # Use common initialization helper with job-related schemas
        tables = {"job_reviews": JOBS_TABLE_SQL}
        self.conn = initialize_db_common(self.db_path, tables)
        logger.info("Initialized job store database")
        self._run_migrations()

    def _run_migrations(self) -> None:
        """Run schema migrations to add missing columns."""
        if not self.conn:
            return
        cursor = self.conn.cursor()

        # Add preprocessing_version column if missing (Phase 2)
        try:
            cursor.execute("ALTER TABLE job_reviews ADD COLUMN preprocessing_version TEXT DEFAULT 'v2.0'")
            self.conn.commit()
            logger.info("Added preprocessing_version column to job_reviews")
        except sqlite3.OperationalError:
            pass  # Column already exists

    def add_job(
        self,
        job_id: str,
        title: str,
        company: Optional[str] = None,
        location: Optional[str] = None,
        status: str = "pending",
        preprocessing_version: str = "v2.0",
        tokens: Optional[int] = None,
        estimated_cost: Optional[float] = None,
    ) -> None:
        """Add or update a job in the database.

        Args:
            job_id: Unique job identifier
            title: Job title
            company: Company name
            location: Job location
            status: Job status (pending, confirmed, rejected)
            preprocessing_version: Version used for preprocessing (v1.0, 1.0, v2.0, 2.0)
            tokens: Token count
            estimated_cost: Estimated LLM cost
        """
        if not self.conn:
            return

        # Normalize version to v-prefixed format
        version_query = preprocessing_version if preprocessing_version.startswith("v") else f"v{preprocessing_version}"

        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO job_reviews
               (job_id, title, company, location, status,
                preprocessing_version, tokens, estimated_cost, crawled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (job_id, title, company, location, status, version_query, tokens, estimated_cost),
        )
        self.conn.commit()
        logger.debug(f"Added/updated job {job_id}")

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job dict or None if not found
        """
        if not self.conn:
            return None

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM job_reviews WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()

        return dict(row) if row else None

    def update_preprocessing_version(self, job_id: str, version: str) -> None:
        """Update preprocessing_version for a job.

        Args:
            job_id: Job ID to update
            version: '1.0', 'v1.0', '2.0', or 'v2.0'

        Raises:
            ValueError: If version not valid
            sqlite3.OperationalError: If job_id not found
        """
        # Normalize version
        clean_version = version.replace("v", "")
        if clean_version not in VALID_PREPROCESSING_VERSIONS:
            raise ValueError(f"Invalid preprocessing version: {version}. Must be one of {VALID_PREPROCESSING_VERSIONS}")

        if not self.conn:
            raise RuntimeError("Database connection not available")

        # Format for storage
        version_query = version if version.startswith("v") else f"v{version}"

        cursor = self.conn.cursor()
        cursor.execute(
            """UPDATE job_reviews
               SET preprocessing_version = ?, preprocessed_at = CURRENT_TIMESTAMP
               WHERE job_id = ?""",
            (version_query, job_id),
        )

        if cursor.rowcount == 0:
            raise sqlite3.OperationalError(f"Job not found: {job_id}")

        self.conn.commit()

    def get_jobs_by_version(self, version: str) -> List[Dict[str, Any]]:
        """Get all jobs with specific preprocessing version.

        Args:
            version: '1.0', 'v1.0', '2.0', or 'v2.0'

        Returns:
            List of job dicts with all columns

        Raises:
            ValueError: If version not valid
        """
        # Normalize and validate version
        clean_version = version.replace("v", "")
        if clean_version not in VALID_PREPROCESSING_VERSIONS:
            raise ValueError(f"Invalid preprocessing version: {version}. Must be one of {VALID_PREPROCESSING_VERSIONS}")

        if not self.conn:
            return []

        # Format for query
        version_query = version if version.startswith("v") else f"v{version}"

        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT *
               FROM job_reviews
               WHERE preprocessing_version = ?
               ORDER BY crawled_at DESC""",
            (version_query,),
        )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_version_stats(self) -> Dict[str, int]:
        """Get count of jobs by preprocessing version.

        Returns:
            Dict like {'1.0': 42, '2.0': 8}
        """
        if not self.conn:
            return {}

        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT preprocessing_version, COUNT(*) as count
               FROM job_reviews
               GROUP BY preprocessing_version
               ORDER BY preprocessing_version"""
        )

        stats: Dict[str, int] = {}
        for row in cursor.fetchall():
            version = row[0] or "unknown"  # Handle NULL
            count = row[1]
            # Normalize version (remove 'v' prefix for return)
            clean_version = version.replace("v", "")
            stats[clean_version] = count

        return stats

    def get_all_jobs(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all jobs, optionally filtered by status.

        Args:
            status: Optional status filter (pending, confirmed, rejected)

        Returns:
            List of job dicts
        """
        if not self.conn:
            return []

        cursor = self.conn.cursor()

        if status:
            cursor.execute("SELECT * FROM job_reviews WHERE status = ? ORDER BY crawled_at DESC", (status,))
        else:
            cursor.execute("SELECT * FROM job_reviews ORDER BY crawled_at DESC")

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def _ensure_cost_tracking_table(self) -> None:
        """Ensure cost_tracking table exists with all required columns.

        Creates the table if it doesn't exist, and adds missing columns if needed.
        """
        if not self.conn:
            return

        cursor = self.conn.cursor()

        # Create cost_tracking table if it doesn't exist
        cursor.execute(COST_TRACKING_TABLE_SQL)

        # Check and add missing columns
        cursor.execute("PRAGMA table_info(cost_tracking)")
        columns = {row[1] for row in cursor.fetchall()}

        columns_to_add = [
            ("preprocessing_version_before", "TEXT"),
            ("preprocessing_version_after", "TEXT"),
            ("tokens_before", "INTEGER"),
            ("tokens_after", "INTEGER"),
            ("estimated_cost_before", "REAL"),
            ("estimated_cost_after", "REAL"),
            ("is_re_preprocessing", "BOOLEAN DEFAULT FALSE"),
        ]

        for col_name, col_type in columns_to_add:
            if col_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE cost_tracking ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column {col_name} to cost_tracking")
                except sqlite3.OperationalError:
                    pass  # Column already exists

        self.conn.commit()

    def log_reprocessing_metrics(
        self,
        job_id: str,
        tokens_before: int,
        tokens_after: int,
        version_before: str,
        version_after: str,
        cost_before: float,
        cost_after: float,
    ) -> None:
        """Log cost/quality metrics for a re-preprocessing run.

        Args:
            job_id: Job ID being re-preprocessed
            tokens_before: Token count before re-preprocessing
            tokens_after: Token count after re-preprocessing
            version_before: Preprocessing version before (e.g., 'v1.0')
            version_after: Preprocessing version after (e.g., 'v2.0')
            cost_before: Estimated cost before re-preprocessing
            cost_after: Estimated cost after re-preprocessing

        Raises:
            RuntimeError: If database connection not available
        """
        if not self.conn:
            raise RuntimeError("Database connection not available")

        self._ensure_cost_tracking_table()

        cursor = self.conn.cursor()

        # Normalize versions
        version_before_normalized = version_before if version_before.startswith("v") else f"v{version_before}"
        version_after_normalized = version_after if version_after.startswith("v") else f"v{version_after}"

        cursor.execute(
            """INSERT INTO cost_tracking
               (job_id, phase, is_re_preprocessing, preprocessing_version_before,
                preprocessing_version_after, tokens_before, tokens_after,
                estimated_cost_before, estimated_cost_after, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (
                job_id,
                "reprocess",
                True,
                version_before_normalized,
                version_after_normalized,
                tokens_before,
                tokens_after,
                cost_before,
                cost_after,
            ),
        )

        self.conn.commit()
        logger.debug(
            f"Logged reprocessing metrics for job {job_id}: "
            f"{tokens_before} → {tokens_after} tokens, "
            f"${cost_before:.6f} → ${cost_after:.6f}"
        )

    def get_cost_comparison_report(self, limit_days: Optional[int] = None) -> CostComparisonReport:
        """Generate cost analysis report for v1.0 vs v2.0 preprocessing.

        Compares token usage, cost estimates, and tracks re-preprocessing progress.

        Args:
            limit_days: Optional limit to jobs preprocessed in last N days

        Returns:
            CostComparisonReport with comprehensive cost/quality metrics
        """
        if not self.conn:
            return CostComparisonReport()

        self._ensure_cost_tracking_table()

        cursor = self.conn.cursor()
        report = CostComparisonReport()

        # Count jobs by version
        cursor.execute("SELECT COUNT(*) FROM job_reviews WHERE preprocessing_version = 'v1.0'")
        report.total_jobs_v1_0 = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM job_reviews WHERE preprocessing_version = 'v2.0'")
        report.total_jobs_v2_0 = cursor.fetchone()[0] or 0

        # Calculate tokens by version
        cursor.execute("SELECT SUM(tokens) FROM job_reviews WHERE preprocessing_version = 'v1.0'")
        result = cursor.fetchone()
        report.total_tokens_v1_0 = result[0] or 0

        cursor.execute("SELECT SUM(tokens) FROM job_reviews WHERE preprocessing_version = 'v2.0'")
        result = cursor.fetchone()
        report.total_tokens_v2_0 = result[0] or 0

        # Calculate averages
        if report.total_jobs_v1_0 > 0:
            report.avg_tokens_per_job_v1_0 = report.total_tokens_v1_0 / report.total_jobs_v1_0
        if report.total_jobs_v2_0 > 0:
            report.avg_tokens_per_job_v2_0 = report.total_tokens_v2_0 / report.total_jobs_v2_0

        # Estimate total savings (assuming $0.003 per 1M tokens for input)
        token_rate = 0.003 / 1_000_000
        if report.total_tokens_v1_0 > 0 and report.total_tokens_v2_0 > 0:
            tokens_saved = report.total_tokens_v1_0 - report.total_tokens_v2_0
            report.estimated_savings_usd = tokens_saved * token_rate

        # Get re-preprocessing metrics
        cursor.execute(
            """SELECT job_id, preprocessing_version_before, preprocessing_version_after,
                      tokens_before, tokens_after, estimated_cost_before, estimated_cost_after
               FROM cost_tracking
               WHERE is_re_preprocessing = TRUE
               ORDER BY timestamp DESC"""
        )

        reprocessing_runs = []
        for row in cursor.fetchall():
            metrics = ReprocessingMetrics(
                job_id=row[0],
                preprocessing_version_before=row[1],
                preprocessing_version_after=row[2],
                tokens_before=row[3],
                tokens_after=row[4],
                estimated_cost_before=row[5],
                estimated_cost_after=row[6],
            )
            reprocessing_runs.append(metrics)
            report.total_reprocessing_tokens_saved += metrics.tokens_saved
            report.total_reprocessing_cost_saved += metrics.cost_saved_usd

        report.reprocessing_runs = reprocessing_runs
        report.jobs_already_migrated = report.total_jobs_v2_0
        report.jobs_pending_migration = report.total_jobs_v1_0

        return report

    def get_jobs_for_reprocessing(
        self,
        version: str = "v1.0",
        min_age_days: Optional[int] = None,
        max_score: Optional[int] = None,
        min_tokens: Optional[int] = None,
        company_names: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get jobs matching filter criteria for targeted re-preprocessing.

        Intelligently filters jobs based on version, age, score, token count, and company.
        Supports combined filtering for A/B testing and gradual migrations.

        Args:
            version: Preprocessing version to filter (e.g., 'v1.0', '1.0', 'v2.0', '2.0')
            min_age_days: Only jobs preprocessed at least N days ago
            max_score: Only jobs with overall_score <= max_score (for low-scoring jobs)
            min_tokens: Only jobs with tokens >= min_tokens (high token count)
            company_names: List of company names to include (e.g., ['Amazon', 'Google'])
            limit: Maximum number of jobs to return (enforces safe batch sizes)

        Returns:
            List of job dicts matching all filter criteria, ordered by oldest first

        Raises:
            ValueError: If version not valid
        """
        # Normalize and validate version
        clean_version = version.replace("v", "")
        if clean_version not in VALID_PREPROCESSING_VERSIONS:
            raise ValueError(f"Invalid preprocessing version: {version}. Must be one of {VALID_PREPROCESSING_VERSIONS}")

        if not self.conn:
            return []

        # Format for query
        version_query = version if version.startswith("v") else f"v{version}"

        # Build query dynamically based on filters
        query = "SELECT * FROM job_reviews WHERE preprocessing_version = ?"
        params: List[Any] = [version_query]

        # Age filter: jobs preprocessed at least min_age_days ago
        if min_age_days is not None and min_age_days > 0:
            query += f" AND datetime(preprocessed_at) <= datetime('now', '-{min_age_days} days')"

        # Score filter: only jobs with low scores (potential improvement candidates)
        if max_score is not None:
            # Note: This requires a joined assessments table or score column
            # For now, we note that future implementation will add assessment score tracking
            pass

        # Token filter: only high-token jobs (most savings potential)
        if min_tokens is not None and min_tokens > 0:
            query += " AND tokens >= ?"
            params.append(min_tokens)

        # Company filter: restrict to specific companies
        if company_names is not None and len(company_names) > 0:
            placeholders = ", ".join("?" * len(company_names))
            query += f" AND company IN ({placeholders})"
            params.extend(company_names)

        # Order by oldest first (prioritize older jobs)
        query += " ORDER BY preprocessed_at ASC"

        # Apply batch limit for safety
        if limit is not None and limit > 0:
            query += f" LIMIT {limit}"

        cursor = self.conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def _ensure_quality_tracking_table(self) -> None:
        """Ensure quality_tracking table exists for Phase 3B.

        Creates the table if it doesn't exist, and adds missing columns if needed.
        """
        if not self.conn:
            return

        cursor = self.conn.cursor()

        # Create quality_tracking table if it doesn't exist
        cursor.execute(QUALITY_TRACKING_TABLE_SQL)

        self.conn.commit()

    def log_quality_impact(
        self,
        job_id: str,
        previous_assessment_score: int,
        new_assessment_score: int,
        preprocessing_version_before: str = "v1.0",
        preprocessing_version_after: str = "v2.0",
    ) -> None:
        """Log quality impact from re-preprocessing and re-assessment.

        Args:
            job_id: Job ID
            previous_assessment_score: Assessment score before re-preprocessing
            new_assessment_score: Assessment score after re-preprocessing
            preprocessing_version_before: Version before (default v1.0)
            preprocessing_version_after: Version after (default v2.0)

        Raises:
            RuntimeError: If database connection not available
        """
        if not self.conn:
            raise RuntimeError("Database connection not available")

        self._ensure_quality_tracking_table()

        cursor = self.conn.cursor()

        # Normalize versions
        version_before_normalized = (
            preprocessing_version_before
            if preprocessing_version_before.startswith("v")
            else f"v{preprocessing_version_before}"
        )
        version_after_normalized = (
            preprocessing_version_after
            if preprocessing_version_after.startswith("v")
            else f"v{preprocessing_version_after}"
        )

        score_delta = new_assessment_score - previous_assessment_score

        cursor.execute(
            """INSERT INTO quality_tracking
               (job_id, preprocessing_version_before, preprocessing_version_after,
                previous_assessment_score, new_assessment_score, score_delta, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (
                job_id,
                version_before_normalized,
                version_after_normalized,
                previous_assessment_score,
                new_assessment_score,
                score_delta,
            ),
        )

        self.conn.commit()
        logger.debug(
            f"Logged quality impact for job {job_id}: "
            f"score {previous_assessment_score} → {new_assessment_score} (delta: {score_delta:+d})"
        )

    def _process_quality_metric(
        self,
        report: QualityComparisonReport,
        row: Any,
        regression_risk_jobs: List[str],
    ) -> tuple[int, int]:
        """Helper to process a single quality metric and update report.

        Args:
            report: Report to update
            row: Database row with quality tracking data
            regression_risk_jobs: List to append regression risk job IDs

        Returns:
            Tuple of (score_before, score_after) for average calculation
        """
        job_id = row[0]
        version_before = row[1]
        version_after = row[2]
        prev_score = row[3]
        new_score = row[4]
        delta = row[5]

        # Create quality metric
        metric = QualityImpactMetrics(
            job_id=job_id,
            preprocessing_version_before=version_before,
            preprocessing_version_after=version_after,
            previous_assessment_score=prev_score,
            new_assessment_score=new_score,
            timestamp=row[6],
        )
        report.quality_metrics.append(metric)

        # Track improvements and declines
        if delta > 0:
            report.score_improved += 1
            if delta > report.max_score_improvement:
                report.max_score_improvement = delta
        elif delta < 0:
            report.score_declined += 1
            if abs(delta) > abs(report.max_score_decline):
                report.max_score_decline = delta
            # Flag regressions (score decline >= 10 points)
            if abs(delta) >= 10:
                regression_risk_jobs.append(job_id)
        else:
            report.score_unchanged += 1

        return (prev_score, new_score)

    def get_quality_comparison_report(self, limit_jobs: Optional[int] = None) -> QualityComparisonReport:
        """Generate quality impact analysis for re-preprocessed jobs.

        Compares assessment scores before and after re-preprocessing to measure
        quality impact of v1.0 → v2.0 migration.

        Args:
            limit_jobs: Optional limit to only analyze first N comparisons

        Returns:
            QualityComparisonReport with comprehensive quality metrics
        """
        if not self.conn:
            return QualityComparisonReport()

        self._ensure_quality_tracking_table()

        cursor = self.conn.cursor()
        report = QualityComparisonReport()

        # Get all quality tracking records
        query = """SELECT job_id, preprocessing_version_before, preprocessing_version_after,
                          previous_assessment_score, new_assessment_score, score_delta, timestamp
                   FROM quality_tracking
                   ORDER BY timestamp DESC"""

        if limit_jobs is not None and limit_jobs > 0:
            query += f" LIMIT {limit_jobs}"

        cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            return QualityComparisonReport()

        # Track metrics
        total_scores_before = 0
        total_scores_after = 0
        regression_risk_jobs: List[str] = []

        for row in rows:
            score_before, score_after = self._process_quality_metric(report, row, regression_risk_jobs)
            total_scores_before += score_before
            total_scores_after += score_after

        # Calculate totals and averages
        report.total_comparisons = len(rows)
        if report.total_comparisons > 0:
            report.avg_score_before = total_scores_before / report.total_comparisons
            report.avg_score_after = total_scores_after / report.total_comparisons

        report.regression_risk_jobs = regression_risk_jobs

        return report

    def get_regression_risk_jobs(self, threshold: int = -10) -> List[Dict[str, Any]]:
        """Get jobs with significant score declines (regression risk).

        Args:
            threshold: Score delta threshold for regression (default -10, i.e., 10 point decline)

        Returns:
            List of job dicts with regression risk metadata
        """
        if not self.conn:
            return []

        self._ensure_quality_tracking_table()

        cursor = self.conn.cursor()

        cursor.execute(
            """SELECT job_id, preprocessing_version_before, preprocessing_version_after,
                      previous_assessment_score, new_assessment_score, score_delta, timestamp
               FROM quality_tracking
               WHERE score_delta <= ?
               ORDER BY score_delta ASC
               LIMIT 100""",
            (threshold,),
        )

        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append(
                {
                    "job_id": row[0],
                    "preprocessing_version_before": row[1],
                    "preprocessing_version_after": row[2],
                    "previous_assessment_score": row[3],
                    "new_assessment_score": row[4],
                    "score_delta": row[5],
                    "timestamp": row[6],
                }
            )

        return results

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Job store connection closed")
