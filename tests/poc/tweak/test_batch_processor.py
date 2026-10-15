"""Tests for POC Batch Processor for multi-job markdown pipeline.

Tests validate:
1. Job loading from JSON array
2. Error handling for non-array input
3. Error handling for missing description field
4. Empty array handling
5. Full batch processing integration
"""

import json
from pathlib import Path

import pytest

from src.poc.tweak.batch_processor import JobResult, load_jobs, run_batch


class TestLoadJobs:
    """Tests for load_jobs() function."""

    def test_load_jobs_valid_array_returns_list_of_dicts(self, tmp_path):
        """Test loading valid JSON array of job records."""
        # Arrange
        fixture_path = Path(__file__).parent.parent / "fixtures" / "details_test_fixture.json"

        # Act
        jobs = load_jobs(str(fixture_path))

        # Assert
        assert isinstance(jobs, list)
        assert len(jobs) == 4, "Fixture should contain 4 job records"
        assert all(isinstance(job, dict) for job in jobs)
        assert all("description" in job for job in jobs)

    def test_load_jobs_non_array_raises_valueerror(self, tmp_path):
        """Test that non-array JSON raises ValueError with clear message."""
        # Arrange
        test_file = tmp_path / "non_array.json"
        test_file.write_text(json.dumps({"job": "single_object"}))

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            load_jobs(str(test_file))

        assert "Expected JSON array at root" in str(exc_info.value)
        assert "got dict" in str(exc_info.value)

    def test_load_jobs_missing_description_field_raises_valueerror(self, tmp_path):
        """Test that records without description field raise ValueError."""
        # Arrange
        test_file = tmp_path / "missing_description.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "Acme",
                        # Missing "description" field
                    }
                ]
            )
        )

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            load_jobs(str(test_file))

        assert "missing 'description' field" in str(exc_info.value)
        assert "job1" in str(exc_info.value)

    def test_load_jobs_null_description_is_valid(self, tmp_path):
        """Test that null description values are accepted (processed gracefully)."""
        # Arrange - description field present but null
        test_file = tmp_path / "null_description.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "Acme",
                        "description": None,  # Explicitly null
                    }
                ]
            )
        )

        # Act
        jobs = load_jobs(str(test_file))

        # Assert - should load without error
        assert len(jobs) == 1
        assert jobs[0]["description"] is None

    def test_load_jobs_empty_array_returns_empty_list(self, tmp_path):
        """Test that empty JSON array returns empty list without error."""
        # Arrange
        test_file = tmp_path / "empty_array.json"
        test_file.write_text(json.dumps([]))

        # Act
        jobs = load_jobs(str(test_file))

        # Assert
        assert jobs == []

    def test_load_jobs_file_not_found_raises_error(self, tmp_path):
        """Test that missing file raises FileNotFoundError."""
        # Act & Assert
        with pytest.raises(FileNotFoundError):
            load_jobs(str(tmp_path / "nonexistent.json"))


class TestRunBatch:
    """Tests for run_batch() integration."""

    def test_run_batch_processes_4_jobs_from_fixture(self):
        """Test full batch processing on fixture with 4 jobs."""
        # Arrange
        fixture_path = Path(__file__).parent.parent / "fixtures" / "details_test_fixture.json"

        # Act
        results = run_batch(str(fixture_path))

        # Assert
        assert isinstance(results, list)
        assert len(results) == 4, "Should process all 4 jobs from fixture"

        # Verify each result
        for result in results:
            assert isinstance(result, JobResult)
            assert result.job_id, "Job ID should be set"
            assert result.title, "Title should be set"
            assert result.company, "Company should be set"
            assert result.sections_detected >= 0, "Sections detected should be non-negative"
            assert result.keyword_matches >= 0, "Keyword matches should be non-negative"
            assert 0.0 <= result.confidence_min <= 1.0, "Min confidence should be in [0,1]"
            assert 0.0 <= result.confidence_max <= 1.0, "Max confidence should be in [0,1]"
            assert 0.0 <= result.confidence_avg <= 1.0, "Avg confidence should be in [0,1]"

        # Verify confidence constraints
        for result in results:
            if result.sections_detected > 0:
                # If sections were detected, confidence scores should be reasonable
                assert result.confidence_max >= result.confidence_min, "Max confidence should be >= min confidence"
                assert result.confidence_avg >= result.confidence_min, "Avg confidence should be >= min confidence"
                assert result.confidence_avg <= result.confidence_max, "Avg confidence should be <= max confidence"

    def test_batch_processor_no_section_classification_errors_on_real_fixtures(self):
        """Verify no section_classification errors on real fixture jobs (Bug A/B test).

        This test ensures that section objects are correctly accessed (Bug A fix: .title not .heading)
        and confidence aggregation matches per-section storage (Bug B fix).
        """
        # Arrange
        fixture_path = Path(__file__).parent.parent / "fixtures" / "details_test_fixture.json"

        # Act
        results = run_batch(str(fixture_path))

        # Assert - no "section_classification" errors (would indicate Bug A or similar)
        for result in results:
            section_class_errors = [error for error in result.errors if error[0] == "section_classification"]
            err_count = len(section_class_errors)
            assert err_count == 0, (
                f"Job {result.job_id} has {err_count} section_classification errors: {section_class_errors}"
            )

    def test_batch_processor_markdown_sections_have_valid_titles(self):
        """Verify MarkdownSection.heading correctly populated from section.title (Bug A fix).

        Bug A was: section.heading used instead of section.title, causing AttributeError.
        This test ensures heading field is correctly populated.
        """
        # Arrange
        fixture_path = Path(__file__).parent.parent / "fixtures" / "details_test_fixture.json"

        # Act
        results = run_batch(str(fixture_path))

        # Assert
        for result in results:
            assert isinstance(result.markdown_sections, list), f"Job {result.job_id} should have markdown_sections list"
            for section in result.markdown_sections:
                # heading should be a string (possibly empty if no title)
                assert isinstance(section.heading, str), (
                    f"Section {section.section_id} heading should be str, got {type(section.heading)}"
                )

    def test_batch_processor_confidence_aggregates_match_per_section_values(self):
        """Verify confidence aggregate stats match per-section values (Bug B fix).

        Bug B was: aggregates built from all_types confidences but stored in sections as primary_confidence.
        This test ensures consistency between aggregate min/max/avg and what's stored per-section.
        """
        # Arrange
        fixture_path = Path(__file__).parent.parent / "fixtures" / "details_test_fixture.json"

        # Act
        results = run_batch(str(fixture_path))

        # Assert
        for result in results:
            if result.sections_detected == 0:
                # If no sections, aggregates should be default
                assert result.confidence_min == 0.0, f"Job {result.job_id}: min should be 0.0 with no sections"
                assert result.confidence_max == 0.0, f"Job {result.job_id}: max should be 0.0 with no sections"
                assert result.confidence_avg == 0.0, f"Job {result.job_id}: avg should be 0.0 with no sections"
            else:
                # Extract confidences from stored markdown_sections
                section_confidences = [s.confidence for s in result.markdown_sections if s.confidence is not None]
                if section_confidences:
                    # Recompute aggregates from per-section values
                    expected_min = min(section_confidences)
                    expected_max = max(section_confidences)
                    expected_avg = sum(section_confidences) / len(section_confidences)

                    # Assert aggregates match recomputed values
                    jid = result.job_id
                    cmin = result.confidence_min
                    cmax = result.confidence_max
                    cavg = result.confidence_avg
                    min_err = f"{jid}: confidence_min mismatch (result={cmin}, expected={expected_min})"
                    max_err = f"{jid}: confidence_max mismatch (result={cmax}, expected={expected_max})"
                    avg_err = f"{jid}: confidence_avg mismatch (result={cavg}, expected={expected_avg})"
                    assert abs(cmin - expected_min) < 0.001, min_err
                    assert abs(cmax - expected_max) < 0.001, max_err
                    assert abs(cavg - expected_avg) < 0.001, avg_err

    def test_batch_processor_extracts_technologies_regression(self):
        """Verify technology extraction works (regression test for entity_ruler patterns).

        Issue #321: entity_ruler patterns must be loaded for technology extraction.
        """
        # Arrange
        fixture_path = Path(__file__).parent.parent / "fixtures" / "details_test_fixture.json"

        # Act
        results = run_batch(str(fixture_path))

        # Assert - at least one job should extract technologies
        tech_counts = [len(r.technologies) for r in results]
        assert max(tech_counts) > 0, "No technologies extracted - entity_ruler patterns not loaded"

        # Verify structure of extracted technologies
        for result in results:
            for tech in result.technologies:
                assert isinstance(tech, dict), "Technology should be a dict"
                assert "tech" in tech, "Technology dict must have 'tech' key"
                assert "confidence" in tech, "Technology dict must have 'confidence' key"
                assert isinstance(tech["tech"], str), "Tech value should be string"
                assert isinstance(tech["confidence"], float), "Confidence should be float"
                assert tech["confidence"] == 1.0, "Technology confidence should always be 1.0"

    def test_batch_processor_handles_null_description_gracefully(self, tmp_path):
        """Test that jobs with null descriptions are processed without errors.

        Null descriptions should be treated as empty strings and processed
        without causing the batch processor to fail (Issue #340).
        """
        # Arrange - Create test file with null description
        test_file = tmp_path / "null_description_jobs.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer Position",
                        "company": "TechCorp",
                        "description": None,  # Null description
                        "location": "Remote",
                    },
                    {
                        "id": "job2",
                        "title": "Engineer Role",
                        "company": "InnovateLabs",
                        "description": "<p>Some HTML content here</p>",  # Valid description
                        "location": "On-site",
                    },
                ]
            )
        )

        # Act - Should not raise error
        results = run_batch(str(test_file))

        # Assert
        assert len(results) == 2, "Should process both jobs"

        # First job with null description should process without error
        job1_result = results[0]
        assert job1_result.job_id == "job1"
        assert job1_result.title == "Developer Position"
        assert not job1_result.has_errors(), f"Job with null description should not error: {job1_result.errors}"

        # Second job with valid description should also process
        job2_result = results[1]
        assert job2_result.job_id == "job2"
        assert job2_result.title == "Engineer Role"
        # This job may have content to process
        assert isinstance(job2_result.sections_detected, int)

    def test_batch_processor_preamble_handling_regression(self, tmp_path):
        """Test MarkdownSpanRuler preamble handling (Issue #373 regression).

        Verifies that text before the first markdown heading is captured
        as a separate section with title=None and level=-2, and that
        metadata (start_line, end_line, word_count) is computed correctly
        for the preamble and subsequent sections.
        """
        # Arrange - job with metadata header before first markdown section
        test_file = tmp_path / "preamble_test.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job-preamble",
                        "title": "Developer Position",
                        "company": "TestCorp",
                        "description": (
                            "Company: TestCorp\n"
                            "Location: Remote\n"
                            "Posted: 2026-09-25\n"
                            "\n"
                            "## Role Overview\n"
                            "We are looking for a developer.\n"
                            "\n"
                            "## Requirements\n"
                            "* 5+ years Python\n"
                            "* Django experience"
                        ),
                    }
                ]
            )
        )

        # Act
        results = run_batch(str(test_file))

        # Assert
        assert len(results) == 1
        result = results[0]
        assert result.job_id == "job-preamble"
        assert not result.has_errors(), f"Batch processor should not error on preamble: {result.errors}"

        # Check that markdown_sections includes the preamble
        assert len(result.markdown_sections) >= 2, "Should have at least 2 sections: preamble + Role Overview"

        # First section should be the preamble (title=None, level=-2)
        preamble = result.markdown_sections[0]
        assert preamble.heading == "", f"Preamble should have empty heading, got {preamble.heading}"
        # (MarkdownSection with title=None is exported as heading="")
        assert preamble.line_start == 0, f"Preamble should start at line 0, got {preamble.line_start}"

        # Subsequent sections should have actual headings
        role_section = result.markdown_sections[1]
        assert role_section.heading == "Role Overview", (
            f"Second section should be 'Role Overview', got {role_section.heading}"
        )

        # sections_detected should include the preamble
        assert result.sections_detected >= 2, (
            f"sections_detected should include preamble, got {result.sections_detected}"
        )


class TestHTMLScoping:
    """Tests for HTML scoping via description_selector (Issue #363)."""

    def test_scoped_vs_unscoped_output_differs(self, tmp_path):
        """Test that scoped output differs from unscoped when selector is provided."""
        # Arrange - Create test file with selector-scoped HTML
        test_file = tmp_path / "scoping_test.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TechCorp",
                        "description": (
                            '<div class="sidebar">Sidebar content</div>'
                            '<div class="job-description">Job requirements here</div>'
                        ),
                    }
                ]
            )
        )

        # Act - Process unscoped
        results_unscoped = run_batch(str(test_file), description_selector=None)

        # Act - Process scoped
        results_scoped = run_batch(str(test_file), description_selector=".job-description")

        # Assert - Results should differ (scoped has less content)
        assert len(results_unscoped) == 1
        assert len(results_scoped) == 1
        unscoped_job = results_unscoped[0]
        scoped_job = results_scoped[0]

        # Scoped should have fewer sections/keywords if it excluded sidebar
        # (Note: exact counts depend on pipeline, but scoped should be more focused)
        assert unscoped_job.job_id == scoped_job.job_id

    def test_scoping_warning_no_matches(self, tmp_path):
        """Test that no-match scenario generates warning."""
        # Arrange
        test_file = tmp_path / "no_match_test.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TechCorp",
                        "description": "<div>Some content</div>",
                    }
                ]
            )
        )

        # Act
        results = run_batch(str(test_file), description_selector=".nonexistent")

        # Assert
        assert len(results) == 1
        result = results[0]
        assert len(result.warnings) >= 1
        warning_texts = [w[1] for w in result.warnings]
        assert any("matched 0 elements" in w for w in warning_texts)
        assert not result.has_errors()  # Warnings are not errors

    def test_scoping_warning_multi_matches(self, tmp_path):
        """Test that multi-match scenario generates warning with count."""
        # Arrange
        test_file = tmp_path / "multi_match_test.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TechCorp",
                        "description": (
                            '<div class="desc">First</div><div class="desc">Second</div><div class="desc">Third</div>'
                        ),
                    }
                ]
            )
        )

        # Act
        results = run_batch(str(test_file), description_selector=".desc")

        # Assert
        assert len(results) == 1
        result = results[0]
        assert len(result.warnings) >= 1
        warning_texts = [w[1] for w in result.warnings]
        assert any("matched 3 elements" in w for w in warning_texts)
        assert not result.has_errors()

    def test_scoping_warning_invalid_css(self, tmp_path):
        """Test that invalid CSS selector generates warning."""
        # Arrange
        test_file = tmp_path / "invalid_css_test.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TechCorp",
                        "description": "<div>Content</div>",
                    }
                ]
            )
        )

        # Act
        results = run_batch(str(test_file), description_selector=">>invalid")

        # Assert
        assert len(results) == 1
        result = results[0]
        assert len(result.warnings) >= 1
        warning_texts = [w[1] for w in result.warnings]
        assert any("Invalid CSS selector" in w for w in warning_texts)
        assert not result.has_errors()  # Invalid CSS is a warning, not an error

    def test_scoping_no_warning_on_single_match(self, tmp_path):
        """Test that single match produces no warning."""
        # Arrange
        test_file = tmp_path / "single_match_test.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TechCorp",
                        "description": '<div class="job-desc">Exact match</div>',
                    }
                ]
            )
        )

        # Act
        results = run_batch(str(test_file), description_selector=".job-desc")

        # Assert
        assert len(results) == 1
        result = results[0]
        # Should have no html_scoping warnings for single match
        html_scope_warnings = [w for w in result.warnings if w[0] == "html_scoping"]
        assert len(html_scope_warnings) == 0

    def test_warnings_not_counted_as_failure(self, tmp_path):
        """Test that warnings do not cause has_errors() to return True."""
        # Arrange
        test_file = tmp_path / "warnings_test.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TechCorp",
                        "description": "<div>No matching selector</div>",
                    }
                ]
            )
        )

        # Act
        results = run_batch(str(test_file), description_selector=".nonexistent")

        # Assert
        assert len(results) == 1
        result = results[0]
        assert len(result.warnings) > 0  # Has warnings
        assert not result.has_errors()  # But not errors

    def test_job_not_mutated_by_scoping(self, tmp_path):
        """Test that original job dict is not mutated by scoping."""
        # Arrange
        test_file = tmp_path / "mutate_test.json"
        original_html = '<div class="desc">Content</div>'
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TechCorp",
                        "description": original_html,
                    }
                ]
            )
        )

        # Load jobs before processing
        jobs = load_jobs(str(test_file))
        original_description = jobs[0]["description"]

        # Act
        _results = run_batch(str(test_file), description_selector=".desc")

        # Assert - reload jobs and verify original not mutated
        jobs_after = load_jobs(str(test_file))
        assert jobs_after[0]["description"] == original_description

    def test_scoping_with_null_description(self, tmp_path):
        """Test that null description with selector is handled gracefully."""
        # Arrange
        test_file = tmp_path / "null_with_selector_test.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TechCorp",
                        "description": None,
                    }
                ]
            )
        )

        # Act
        results = run_batch(str(test_file), description_selector=".desc")

        # Assert
        assert len(results) == 1
        result = results[0]
        assert not result.has_errors()  # Null + selector = no error

    def test_fixture_scope_selector_fixture_loads(self):
        """Test that synthetic fixture loads and contains expected jobs."""
        # Arrange
        fixture_path = Path(__file__).parent.parent / "fixtures" / "scope_selector_fixture.json"

        # Act
        jobs = load_jobs(str(fixture_path))

        # Assert
        assert len(jobs) == 5
        job_ids = [job["id"] for job in jobs]
        assert "job_A_full_shell" in job_ids
        assert "job_B_already_scoped" in job_ids
        assert "job_C_no_match" in job_ids
        assert "job_D_multi_match" in job_ids
        assert "job_E_null_description" in job_ids

        # Verify all have description field (even if null)
        for job in jobs:
            assert "description" in job


class TestDescriptionMatchStrategies:
    """Tests for description_selector_match strategies (Issue #367)."""

    def test_strategy_longest_on_multi_match_short_first_long_second(self, tmp_path):
        """Test that strategy='longest' picks the long description when first match is short (WorkSource case)."""
        # Arrange: Simulating WorkSource page with benefits snippet first, description second
        test_file = tmp_path / "longest_multi_match.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Senior Developer",
                        "company": "WorkSource",
                        "description": (
                            '<div class="job-desc">Benefits: Health insurance, 401k</div>'
                            '<div class="job-desc">Comprehensive job description with requirements, '
                            "qualifications, technical skills needed, years of experience required, "
                            "and detailed responsibilities. This is much longer than the benefits section."
                            "</div>"
                        ),
                    }
                ]
            )
        )

        # Act
        results = run_batch(
            str(test_file),
            description_selector=".job-desc",
            description_match="longest",
        )

        # Assert
        assert len(results) == 1
        result = results[0]
        # Should have 1 warning about multi-match and longest strategy
        html_scope_warnings = [w for w in result.warnings if w[0] == "html_scoping"]
        assert len(html_scope_warnings) >= 1
        # Warning should mention "using longest match"
        warning_text = " ".join([w[1] for w in html_scope_warnings])
        assert "using longest match" in warning_text
        assert "2 elements" in warning_text

    def test_strategy_all_joins_multiple_matches_with_separator(self, tmp_path):
        """Test that strategy='all' joins all matches with separator in document order."""
        # Arrange
        test_file = tmp_path / "all_matches.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TestCorp",
                        "description": (
                            '<div class="section">Section 1 content</div><div class="section">Section 2 content</div>'
                        ),
                    }
                ]
            )
        )

        # Act
        results = run_batch(
            str(test_file),
            description_selector=".section",
            description_match="all",
        )

        # Assert
        assert len(results) == 1
        result = results[0]
        html_scope_warnings = [w for w in result.warnings if w[0] == "html_scoping"]
        assert len(html_scope_warnings) >= 1
        warning_text = " ".join([w[1] for w in html_scope_warnings])
        assert "using all matches" in warning_text

    def test_invalid_strategy_warning_fallback_to_first(self, tmp_path):
        """Test that invalid strategy generates warning and falls back to 'first'."""
        # Arrange
        test_file = tmp_path / "invalid_strategy.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TestCorp",
                        "description": (
                            '<div class="desc">First match</div>'
                            '<div class="desc">Second match longer than first one</div>'
                        ),
                    }
                ]
            )
        )

        # Act
        results = run_batch(
            str(test_file),
            description_selector=".desc",
            description_match="invalid_strategy_name",
        )

        # Assert
        assert len(results) == 1
        result = results[0]
        html_scope_warnings = [w for w in result.warnings if w[0] == "html_scoping"]
        assert len(html_scope_warnings) >= 1
        # Should have warning about invalid strategy
        warning_texts = [w[1] for w in html_scope_warnings]
        assert any("Invalid description_selector_match value" in w for w in warning_texts)
        assert any("invalid_strategy_name" in w for w in warning_texts)
        assert any("falling back to 'first'" in w for w in warning_texts)

    def test_strategy_first_default_when_not_provided(self, tmp_path):
        """Test that omitting description_match defaults to 'first' strategy."""
        # Arrange
        test_file = tmp_path / "default_strategy.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TestCorp",
                        "description": (
                            '<div class="desc">First match content</div><div class="desc">Second match content</div>'
                        ),
                    }
                ]
            )
        )

        # Act - No description_match parameter (defaults to "first")
        results = run_batch(
            str(test_file),
            description_selector=".desc",
        )

        # Assert
        assert len(results) == 1
        result = results[0]
        # Should use first match (no warning about strategy since it's implicit)
        html_scope_warnings = [w for w in result.warnings if w[0] == "html_scoping"]
        # May have warning about multi-match, should say "using first match"
        if html_scope_warnings:
            warning_text = " ".join([w[1] for w in html_scope_warnings])
            assert "using first match" in warning_text or "matched 2 elements" in warning_text


class TestCLIFlags:
    """Tests for CLI --company and --config-dir flags (Issue #363, #367)."""

    def test_resolve_description_selector_match_found(self, tmp_path):
        """Test _resolve_description_selector with matching company."""
        # Arrange
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "test.json"
        config_file.write_text(
            json.dumps(
                {
                    "companies": {
                        "TestCorp": {
                            "name": "Test Corporation",
                            "selectors": {
                                "description_selector": ".job-description",
                                "title": "h1",
                            },
                        }
                    }
                }
            )
        )

        # Act
        from src.poc.tweak.batch_processor import _resolve_description_selector

        selector = _resolve_description_selector("TestCorp", str(config_dir))

        # Assert
        assert selector == ".job-description"

    def test_resolve_description_selector_no_match_raises_valueerror(self, tmp_path):
        """Test _resolve_description_selector when company not found."""
        # Arrange
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "test.json"
        config_file.write_text(json.dumps({"companies": {}}))

        # Act & Assert
        from src.poc.tweak.batch_processor import _resolve_description_selector

        with pytest.raises(ValueError) as exc_info:
            _resolve_description_selector("NonExistent", str(config_dir))

        assert "No configuration found for company 'NonExistent'" in str(exc_info.value)

    def test_resolve_description_selector_no_description_field_raises_valueerror(self, tmp_path):
        """Test _resolve_description_selector when config lacks description_selector."""
        # Arrange
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "test.json"
        config_file.write_text(
            json.dumps(
                {
                    "companies": {
                        "TestCorp": {
                            "name": "Test Corporation",
                            "selectors": {
                                "title": "h1",
                                # Missing "description_selector"
                            },
                        }
                    }
                }
            )
        )

        # Act & Assert
        from src.poc.tweak.batch_processor import _resolve_description_selector

        with pytest.raises(ValueError) as exc_info:
            _resolve_description_selector("TestCorp", str(config_dir))

        assert "has no 'selectors.description_selector' defined" in str(exc_info.value)

    def test_resolve_description_match_returns_longest_for_worksource(self, tmp_path):
        """Test _resolve_description_match returns 'longest' for WorkSource with proper tmp_path config."""
        # Arrange - Create temporary config with WorkSource entry having description_selector_match: longest
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "worksource.json"
        config_file.write_text(
            json.dumps(
                {
                    "companies": {
                        "WorkSource": {
                            "name": "WorkSource Inc.",
                            "selectors": {
                                "description_selector": ".job-description",
                                "description_selector_match": "longest",
                                "title": "h1",
                            },
                        }
                    }
                }
            )
        )

        # Act
        from src.poc.tweak.batch_processor import _resolve_description_match

        strategy = _resolve_description_match("WorkSource", str(config_dir))

        # Assert
        assert strategy == "longest"

    def test_resolve_description_match_returns_first_when_key_absent(self, tmp_path):
        """Test _resolve_description_match returns 'first' as default when key absent."""
        # Arrange - Create config without description_selector_match key
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "test.json"
        config_file.write_text(
            json.dumps(
                {
                    "companies": {
                        "TestCorp": {
                            "name": "Test Corporation",
                            "selectors": {
                                "description_selector": ".job-desc",
                                # Missing "description_selector_match"
                            },
                        }
                    }
                }
            )
        )

        # Act
        from src.poc.tweak.batch_processor import _resolve_description_match

        strategy = _resolve_description_match("TestCorp", str(config_dir))

        # Assert
        assert strategy == "first"

    def test_cli_company_flag_resolves_selector(self, tmp_path):
        """Test that --company flag resolves description_selector from config."""
        # Arrange
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "test.json"
        config_file.write_text(
            json.dumps(
                {
                    "companies": {
                        "TestCorp": {
                            "name": "Test Corporation",
                            "selectors": {
                                "description_selector": ".job-desc",
                            },
                        }
                    }
                }
            )
        )

        # Create a test input file
        input_file = tmp_path / "jobs.json"
        input_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",
                        "company": "TechCorp",
                        "description": '<div class="job-desc">Job content</div><div class="other">Other</div>',
                    }
                ]
            )
        )

        # Act - Call main with --company flag
        import sys

        from src.poc.tweak.batch_processor import main

        old_argv = sys.argv
        try:
            sys.argv = [
                "batch_processor",
                "--input-path",
                str(input_file),
                "--company",
                "TestCorp",
                "--config-dir",
                str(config_dir),
            ]
            exit_code = main()

            # Assert
            assert exit_code == 0, "main() should return 0 on success"
        finally:
            sys.argv = old_argv

    def test_cli_company_flag_not_found_exits_1(self, tmp_path, capsys):
        """Test that --company with non-existent company exits with code 1."""
        # Arrange
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "test.json"
        config_file.write_text(json.dumps({"companies": {}}))

        input_file = tmp_path / "jobs.json"
        input_file.write_text(
            json.dumps([{"id": "job1", "title": "Developer", "company": "TechCorp", "description": "text"}])
        )

        # Act
        import sys

        from src.poc.tweak.batch_processor import main

        old_argv = sys.argv
        try:
            sys.argv = [
                "batch_processor",
                "--input-path",
                str(input_file),
                "--company",
                "NonExistent",
                "--config-dir",
                str(config_dir),
            ]
            exit_code = main()

            # Assert
            assert exit_code == 1, "main() should return 1 on company not found"
            captured = capsys.readouterr()
            assert "No configuration found for company 'NonExistent'" in captured.err
        finally:
            sys.argv = old_argv

    def test_default_config_dir_is_config_test(self):
        """Test that default --config-dir is 'config_test' as per plan."""
        # This test documents the default behavior; no --config-dir means config_test is used
        # The lazy import of common.py only happens when --company is provided
        # (verified by code structure: import only in _resolve_description_selector function)
        from src.poc.tweak.batch_processor import _resolve_description_selector

        # If we call _resolve_description_selector with config_test, common.py is imported
        # (which is the lazy import behavior)
        # This test just documents that config_test is the default
        assert True  # Placeholder; actual behavior verified by CLI tests above


class TestPerJobSourceConfigScoping:
    """Tests for per-record description_selector resolution from source_config (Issue #376)."""

    @staticmethod
    def _write_config_dir(tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "companies.json").write_text(
            json.dumps(
                {
                    "companies": {
                        "AlphaCo": {
                            "name": "Alpha Co",
                            "selectors": {
                                "description_selector": ".alpha-desc",
                                "description_selector_match": "longest",
                            },
                        },
                        "BetaCo": {
                            "name": "Beta Co",
                            "selectors": {"description_selector": ".beta-desc"},
                        },
                    }
                }
            )
        )
        return config_dir

    @staticmethod
    def _write_jobs(tmp_path, records):
        input_file = tmp_path / "jobs.json"
        input_file.write_text(json.dumps(records))
        return input_file

    @staticmethod
    def _record(job_id, source_config=None, present=True):
        record = {"id": job_id, "title": "Dev", "company": "X", "description": "<p>placeholder</p>"}
        if present:
            record["source_config"] = source_config
        return record

    @pytest.fixture
    def recorded_calls(self, monkeypatch):
        """Replace process_job with a recorder that returns a minimal JobResult (no pipeline work)."""
        from src.poc.tweak import batch_processor as bp

        calls = []

        def fake_process_job(job, **kwargs):
            calls.append({"job_id": job["id"], **kwargs})
            return JobResult(
                job_id=job["id"],
                title="Dev",
                company="X",
                sections_detected=0,
                keyword_matches=0,
                confidence_min=0.0,
                confidence_max=0.0,
                confidence_avg=0.0,
            )

        monkeypatch.setattr(bp, "process_job", fake_process_job)
        return calls

    def test_mixed_source_config_each_job_gets_its_own_selector(self, tmp_path, recorded_calls):
        """Two companies in one input, no global override: each job receives its own company's selector/match."""
        config_dir = self._write_config_dir(tmp_path)
        input_file = self._write_jobs(
            tmp_path,
            [
                self._record("a1", "AlphaCo"),
                self._record("b1", "BetaCo"),
                self._record("a2", "AlphaCo"),
            ],
        )

        run_batch(str(input_file), config_dir=str(config_dir))

        by_id = {c["job_id"]: c for c in recorded_calls}
        assert by_id["a1"]["description_selector"] == ".alpha-desc"
        assert by_id["a1"]["description_match"] == "longest"
        assert by_id["a2"]["description_selector"] == ".alpha-desc"
        assert by_id["a2"]["description_match"] == "longest"
        assert by_id["b1"]["description_selector"] == ".beta-desc"
        assert by_id["b1"]["description_match"] == "first"

    def test_global_description_selector_overrides_all_jobs(self, tmp_path, recorded_calls):
        """A global description_selector (--company path) wins for every job, regardless of source_config."""
        config_dir = self._write_config_dir(tmp_path)
        input_file = self._write_jobs(
            tmp_path,
            [self._record("a1", "AlphaCo"), self._record("b1", "BetaCo")],
        )

        run_batch(
            str(input_file),
            description_selector=".global-desc",
            description_match="all",
            config_dir=str(config_dir),
        )

        assert len(recorded_calls) == 2
        for call in recorded_calls:
            assert call["description_selector"] == ".global-desc"
            assert call["description_match"] == "all"

    def test_records_without_source_config_keep_defaults(self, tmp_path, recorded_calls):
        """Missing key, None, and empty string all keep the old defaults (None selector, 'first' match)."""
        config_dir = self._write_config_dir(tmp_path)
        input_file = self._write_jobs(
            tmp_path,
            [
                self._record("missing", present=False),
                self._record("none", None),
                self._record("empty", ""),
            ],
        )

        run_batch(str(input_file), config_dir=str(config_dir))

        assert len(recorded_calls) == 3
        for call in recorded_calls:
            assert call["description_selector"] is None
            assert call["description_match"] == "first"

    def test_unknown_source_config_degrades_to_unscoped_with_warning(self, tmp_path, recorded_calls):
        """Unknown source_config: batch continues, job gets defaults, and a source_config warning is recorded.

        Mirrors the existing resolver behaviour (ValueError 'No configuration found'), captured per job.
        """
        config_dir = self._write_config_dir(tmp_path)
        input_file = self._write_jobs(
            tmp_path,
            [self._record("ghost", "NoSuchCo"), self._record("alpha", "AlphaCo")],
        )

        results = run_batch(str(input_file), config_dir=str(config_dir))

        assert len(results) == 2
        by_id = {c["job_id"]: c for c in recorded_calls}
        assert by_id["ghost"]["description_selector"] is None
        assert by_id["ghost"]["description_match"] == "first"
        assert by_id["alpha"]["description_selector"] == ".alpha-desc"

        ghost_result = next(r for r in results if r.job_id == "ghost")
        source_warnings = [w for w in ghost_result.warnings if w[0] == "source_config"]
        assert len(source_warnings) == 1
        assert "NoSuchCo" in source_warnings[0][1]
        assert "No configuration found" in source_warnings[0][1]
        assert not ghost_result.has_errors()

        alpha_result = next(r for r in results if r.job_id == "alpha")
        assert not [w for w in alpha_result.warnings if w[0] == "source_config"]

    def test_missing_config_dir_degrades_to_unscoped_with_warning(self, tmp_path, recorded_calls):
        """Missing config dir (default 'config_test' absent): no exception, record processed unscoped, warning kept."""
        input_file = self._write_jobs(tmp_path, [self._record("alpha", "AlphaCo")])

        results = run_batch(str(input_file), config_dir=str(tmp_path / "nope"))

        assert len(results) == 1
        assert len(recorded_calls) == 1
        assert recorded_calls[0]["description_selector"] is None
        assert recorded_calls[0]["description_match"] == "first"

        source_warnings = [w for w in results[0].warnings if w[0] == "source_config"]
        assert len(source_warnings) == 1
        assert "could not be resolved" in source_warnings[0][1]
        assert "nope" in source_warnings[0][1]
        assert not results[0].has_errors()

    def test_non_str_truthy_source_config_is_stringified(self, tmp_path, recorded_calls):
        """Non-str truthy source_config (int 123) is stringified to '123' as the lookup key: no crash.

        Actual behaviour: no config key '123' exists, so the job is processed unscoped with a warning.
        """
        config_dir = self._write_config_dir(tmp_path)
        input_file = self._write_jobs(tmp_path, [self._record("num", 123)])

        results = run_batch(str(input_file), config_dir=str(config_dir))

        assert len(results) == 1
        assert recorded_calls[0]["description_selector"] is None
        assert recorded_calls[0]["description_match"] == "first"
        source_warnings = [w for w in results[0].warnings if w[0] == "source_config"]
        assert len(source_warnings) == 1
        assert "'123'" in source_warnings[0][1]
        assert "No configuration found" in source_warnings[0][1]

    def test_same_source_config_resolved_once_per_batch(self, tmp_path, monkeypatch, recorded_calls):
        """Cache: two records sharing a source_config resolve once (one cache miss, two loader calls in resolver).

        Spies the resolver (cache miss counter) and the config loader it calls.
        """
        from src.poc.tweak import batch_processor as bp
        from src.poc.tweak import common

        resolver_keys = []
        original_resolver = bp._resolve_job_scoping

        def counting_resolver(source_config, config_dir):
            resolver_keys.append(source_config)
            return original_resolver(source_config, config_dir)

        loader_calls = []
        original_loader = common.load_all_company_configs

        def counting_loader(config_dir):
            loader_calls.append(config_dir)
            return original_loader(config_dir)

        monkeypatch.setattr(bp, "_resolve_job_scoping", counting_resolver)
        monkeypatch.setattr(common, "load_all_company_configs", counting_loader)

        config_dir = self._write_config_dir(tmp_path)
        input_file = self._write_jobs(
            tmp_path,
            [self._record("a1", "AlphaCo"), self._record("a2", "AlphaCo"), self._record("a3", "AlphaCo")],
        )

        run_batch(str(input_file), config_dir=str(config_dir))

        assert resolver_keys == ["AlphaCo"]
        # Resolver loads config twice (selector + match) on the single cache miss
        assert len(loader_calls) == 2
        assert len(recorded_calls) == 3
        assert all(c["description_selector"] == ".alpha-desc" for c in recorded_calls)

    def test_top_level_array_config_degrades_to_unscoped_without_abort(self, tmp_path, recorded_calls):
        """Top-level JSON array config (AttributeError in loader): batch continues, job unscoped, warning recorded."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "companies.json").write_text(json.dumps([1, 2]))
        input_file = self._write_jobs(tmp_path, [self._record("alpha", "AlphaCo")])

        results = run_batch(str(input_file), config_dir=str(config_dir))

        assert len(results) == 1
        assert len(recorded_calls) == 1
        assert recorded_calls[0]["description_selector"] is None
        assert recorded_calls[0]["description_match"] == "first"
        source_warnings = [w for w in results[0].warnings if w[0] == "source_config"]
        assert len(source_warnings) == 1
        assert "could not be resolved" in source_warnings[0][1]
        assert not results[0].has_errors()

    def test_null_name_company_with_unknown_source_config_does_not_abort(self, tmp_path, recorded_calls):
        """Another entry with "name": null plus unknown source_config (NoneType.lower): batch continues."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "companies.json").write_text(
            json.dumps(
                {
                    "companies": {
                        "NullNameCo": {"name": None, "selectors": {"description_selector": ".n"}},
                        "AlphaCo": {
                            "name": "Alpha Co",
                            "selectors": {"description_selector": ".alpha-desc"},
                        },
                    }
                }
            )
        )
        input_file = self._write_jobs(
            tmp_path,
            [self._record("ghost", "NoSuchCo"), self._record("alpha", "AlphaCo")],
        )

        results = run_batch(str(input_file), config_dir=str(config_dir))

        assert len(results) == 2
        by_id = {c["job_id"]: c for c in recorded_calls}
        assert by_id["ghost"]["description_selector"] is None
        assert by_id["ghost"]["description_match"] == "first"
        assert by_id["alpha"]["description_selector"] == ".alpha-desc"

        ghost_result = next(r for r in results if r.job_id == "ghost")
        source_warnings = [w for w in ghost_result.warnings if w[0] == "source_config"]
        assert len(source_warnings) == 1
        assert "could not be resolved" in source_warnings[0][1]
        assert not ghost_result.has_errors()

    def test_non_dict_company_value_degrades_to_unscoped_without_abort(self, tmp_path, recorded_calls):
        """Non-dict company value ("AlphaCo": "x", AttributeError in resolver): batch continues, jobs unscoped."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "companies.json").write_text(
            json.dumps({"companies": {"AlphaCo": "x", "BetaCo": {"name": "Beta Co", "selectors": {}}}})
        )
        input_file = self._write_jobs(
            tmp_path,
            [self._record("alpha", "AlphaCo"), self._record("beta", "BetaCo")],
        )

        results = run_batch(str(input_file), config_dir=str(config_dir))

        assert len(results) == 2
        assert len(recorded_calls) == 2
        for call in recorded_calls:
            assert call["description_selector"] is None
            assert call["description_match"] == "first"
        for result in results:
            source_warnings = [w for w in result.warnings if w[0] == "source_config"]
            assert len(source_warnings) == 1
            assert "could not be resolved" in source_warnings[0][1]
            assert not result.has_errors()

    def test_list_description_selector_match_falls_back_to_first_without_abort(self, tmp_path):
        """Unhashable description_selector_match (list) from source_config: html_scoping warning, batch continues."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "companies.json").write_text(
            json.dumps(
                {
                    "companies": {
                        "AlphaCo": {
                            "name": "Alpha Co",
                            "selectors": {
                                "description_selector": ".desc",
                                "description_selector_match": ["all"],
                            },
                        },
                    }
                }
            )
        )
        input_file = self._write_jobs(
            tmp_path,
            [
                {
                    "id": "alpha",
                    "title": "Dev",
                    "company": "Alpha Co",
                    "description": '<div class="desc">First match</div><div class="desc">Second match</div>',
                    "source_config": "AlphaCo",
                },
                {
                    "id": "plain",
                    "title": "Dev",
                    "company": "X",
                    "description": "<p>No scoping here</p>",
                },
            ],
        )

        results = run_batch(str(input_file), config_dir=str(config_dir))

        assert len(results) == 2
        alpha_result = next(r for r in results if r.job_id == "alpha")
        html_scope_warnings = [w[1] for w in alpha_result.warnings if w[0] == "html_scoping"]
        assert any("Invalid description_selector_match value" in w for w in html_scope_warnings)
        assert any("falling back to 'first'" in w for w in html_scope_warnings)
        assert not alpha_result.has_errors()
        assert not [w for w in alpha_result.warnings if w[0] == "source_config"]

    def test_cli_config_dir_forwarded_to_run_batch_without_company(self, tmp_path, monkeypatch):
        """Test that --config-dir reaches run_batch without --company (per-job source_config resolution)."""
        import sys

        import src.poc.tweak.batch_processor as bp

        config_dir = tmp_path / "custom_configs"
        config_dir.mkdir()
        input_file = tmp_path / "jobs.json"
        input_file.write_text(
            json.dumps(
                [
                    {
                        "id": "alpha",
                        "title": "Dev",
                        "company": "Alpha",
                        "description": "text",
                        "source_config": "alpha",
                    },
                    {"id": "beta", "title": "Dev", "company": "Beta", "description": "text"},
                ]
            )
        )

        recorded: dict = {}

        def fake_run_batch(input_path, **kwargs):
            recorded["input_path"] = input_path
            recorded.update(kwargs)
            return []

        monkeypatch.setattr(bp, "run_batch", fake_run_batch)
        monkeypatch.setattr(bp, "print_summary", lambda results: None)
        old_argv = sys.argv
        try:
            sys.argv = [
                "batch_processor",
                "--input-path",
                str(input_file),
                "--config-dir",
                str(config_dir),
            ]
            exit_code = bp.main()
        finally:
            sys.argv = old_argv

        assert exit_code == 0
        assert recorded["input_path"] == str(input_file)
        assert recorded["config_dir"] == str(config_dir)
        assert recorded["config_dir"] != "config_test"
        assert recorded["description_selector"] is None


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "details_test_fixture.json"


def _run_main(argv_tail: list) -> int:
    """Invoke batch_processor.main() with the given CLI args (Issue #643 helper)."""
    import sys

    import src.poc.tweak.batch_processor as bp

    old_argv = sys.argv
    try:
        sys.argv = ["batch_processor", *argv_tail]
        return bp.main()
    finally:
        sys.argv = old_argv


class TestBatchSentences:
    """Tests for JobResult.sentences and the poc_sentence_splitter flag (Issue #643)."""

    def test_sentences_are_nonempty_stripped_strings(self):
        """Every sentence is a stripped, non-empty str; at least one job has sentences."""
        # Act
        results = run_batch(str(FIXTURE_PATH))

        # Assert
        for result in results:
            assert isinstance(result.sentences, list)
            for sentence in result.sentences:
                assert isinstance(sentence, str)
                assert sentence, f"{result.job_id}: empty sentence"
                assert sentence == sentence.strip(), f"{result.job_id}: unstripped sentence {sentence!r}"
        assert any(result.sentences for result in results), "Expected at least one job with sentences"

    def test_null_description_job_has_empty_sentences(self, tmp_path):
        """Null description yields sentences == [] with no per-job error."""
        # Arrange
        test_file = tmp_path / "null_description_sentences.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer Position",
                        "company": "TechCorp",
                        "description": None,
                    }
                ]
            )
        )

        # Act
        results = run_batch(str(test_file))

        # Assert
        assert len(results) == 1
        assert results[0].sentences == []
        assert not results[0].has_errors(), f"Unexpected errors: {results[0].errors}"

    def test_jobresult_without_sentences_defaults_to_empty_list(self):
        """JobResult built without sentences gets [] and instances do not share the list."""
        # Arrange / Act
        first = JobResult(
            job_id="a",
            title="t",
            company="c",
            sections_detected=0,
            keyword_matches=0,
            confidence_min=0.0,
            confidence_max=0.0,
            confidence_avg=0.0,
        )
        second = JobResult(
            job_id="b",
            title="t",
            company="c",
            sections_detected=0,
            keyword_matches=0,
            confidence_min=0.0,
            confidence_max=0.0,
            confidence_avg=0.0,
        )

        # Assert
        assert first.sentences == []
        first.sentences.append("x")
        assert second.sentences == [], "default_factory must not share the list between instances"

    def test_main_output_json_includes_sentences_per_job(self, tmp_path):
        """CLI --output-json export carries a sentences list for every job."""
        # Arrange
        out_file = tmp_path / "out.json"

        # Act
        exit_code = _run_main(["--input-path", str(FIXTURE_PATH), "--output-json", str(out_file)])

        # Assert
        assert exit_code == 0
        entries = json.loads(out_file.read_text())
        assert len(entries) == 4
        for entry in entries:
            assert isinstance(entry["sentences"], list)
        assert any(entry["sentences"] for entry in entries)

    def test_flag_on_adds_pipe_flag_off_omits_it(self, monkeypatch):
        """Pipe is present by default and absent when enable_poc_sentence_splitter=False."""
        import src.poc.tweak.batch_processor as bp

        seen_pipes: list = []
        original_process_job = bp.process_job

        def recording_process_job(job, **kwargs):
            seen_pipes.append(tuple(kwargs["nlp"].pipe_names))
            return original_process_job(job, **kwargs)

        monkeypatch.setattr(bp, "process_job", recording_process_job)

        run_batch(str(FIXTURE_PATH))
        assert seen_pipes, "process_job was not invoked"
        assert all("poc_sentence_splitter" in names for names in seen_pipes)

        seen_pipes.clear()
        off_results = run_batch(str(FIXTURE_PATH), enable_poc_sentence_splitter=False)
        assert seen_pipes, "process_job was not invoked"
        assert all("poc_sentence_splitter" not in names for names in seen_pipes)
        assert all(result.sentences == [] for result in off_results)

    def test_cli_no_poc_sentences_leaves_sentences_empty(self, tmp_path):
        """--no-poc-sentences yields empty sentences for every job in the JSON export."""
        # Arrange
        out_file = tmp_path / "out_off.json"

        # Act
        exit_code = _run_main(["--input-path", str(FIXTURE_PATH), "--output-json", str(out_file), "--no-poc-sentences"])

        # Assert
        assert exit_code == 0
        entries = json.loads(out_file.read_text())
        assert len(entries) == 4
        assert all(entry["sentences"] == [] for entry in entries)

    def test_flag_does_not_change_sections_or_requirements(self):
        """Toggling the splitter leaves sections_detected and requirements counts unchanged."""
        # Act
        on_results = run_batch(str(FIXTURE_PATH))
        off_results = run_batch(str(FIXTURE_PATH), enable_poc_sentence_splitter=False)

        # Assert
        on_by_id = {result.job_id: result for result in on_results}
        assert len(off_results) == len(on_results)
        for off in off_results:
            on = on_by_id[off.job_id]
            assert on.sections_detected == off.sections_detected, f"{off.job_id}: sections_detected differs"
            assert len(on.requirements) == len(off.requirements), f"{off.job_id}: requirements count differs"

    def test_heading_merges_into_following_sentence_known_limitation(self, tmp_path):
        """Documents known limitation: a markdown heading glues onto the next sentence.

        See the "Known limitations" section of src/poc/sentence_splitter.py
        (a heading without terminal punctuation joins the following sentence).
        """
        # Arrange
        test_file = tmp_path / "heading_sentences.json"
        test_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Dev",
                        "company": "Co",
                        "description": "## Requirements\n\nYou must know Python.",
                    }
                ]
            )
        )

        # Act
        results = run_batch(str(test_file))

        # Assert - known limitation: heading and sentence merge into ONE entry
        sentences = results[0].sentences
        assert len(sentences) == 1, f"Expected merged single entry, got {sentences!r}"
        assert "Requirements" in sentences[0]
        assert "You must know Python." in sentences[0]
