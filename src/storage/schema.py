"""Consolidated database schema definitions for ATS Showcase.

This module centralizes all table schema definitions to avoid duplication
across JobStore, AssessmentStore, and other storage modules.
"""

# Job Reviews Table
JOBS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS job_reviews (
    job_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    location TEXT,
    company TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reason TEXT,
    tokens INTEGER,
    estimated_cost REAL,
    crawled_at TIMESTAMP,
    preprocessed_at TIMESTAMP,
    reviewed_at TIMESTAMP,
    preprocessing_version TEXT DEFAULT 'v2.0'
)
"""

# Job Assessments Table
ASSESSMENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS job_assessments (
    job_id TEXT PRIMARY KEY,
    title TEXT,
    company TEXT,
    location TEXT,
    overall_score REAL,
    tech_score REAL,
    seniority_score REAL,
    location_score REAL,
    recommendations TEXT,
    summary TEXT,
    tokens_used INTEGER,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    actual_cost REAL,
    assessed_date TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES job_reviews(job_id)
)
"""

# Job Assessments Full-Text Search Index
ASSESSMENT_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS job_assessments_fts USING fts5(
    job_id, title, company, summary, recommendations
)
"""

# Cost Tracking Table
COST_TRACKING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cost_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    phase TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    preprocessing_version_before TEXT,
    preprocessing_version_after TEXT,
    tokens_before INTEGER,
    tokens_after INTEGER,
    estimated_cost_before REAL,
    estimated_cost_after REAL,
    is_re_preprocessing BOOLEAN DEFAULT FALSE,
    FOREIGN KEY(job_id) REFERENCES job_reviews(job_id)
)
"""

# Quality Tracking Table (Phase 3B)
QUALITY_TRACKING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS quality_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    preprocessing_version_before TEXT,
    preprocessing_version_after TEXT,
    previous_assessment_score INTEGER,
    new_assessment_score INTEGER,
    score_delta INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(job_id) REFERENCES job_reviews(job_id)
)
"""
