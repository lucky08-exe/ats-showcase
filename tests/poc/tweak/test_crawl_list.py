"""Tests for crawl_list.py job extraction and company crawling."""

from datetime import datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.poc.tweak.crawl_list import (
    crawl_company_jobs,
    extract_detail_page_fields,
    extract_job_from_container,
    extract_url_param,
    parse_field,
    parse_posted_date,
)


class TestExtractUrlParam:
    """Test suite for extract_url_param helper function."""

    def test_extract_url_param_single_param(self):
        """Test extracting a single parameter from URL."""
        url = "https://example.com/jobs?jobId=abc123xyz789"
        result = extract_url_param(url, "jobId")
        assert result == "abc123xyz789"

    def test_extract_url_param_multiple_params(self):
        """Test extracting one parameter when multiple exist."""
        url = "https://example.com/jobs?page=1&jobId=abc123xyz789&company=acme"
        result = extract_url_param(url, "jobId")
        assert result == "abc123xyz789"

    def test_extract_url_param_not_found(self):
        """Test that None is returned when parameter not found."""
        url = "https://example.com/jobs?page=1&company=acme"
        result = extract_url_param(url, "jobId")
        assert result is None

    def test_extract_url_param_no_query_string(self):
        """Test that None is returned when no query string exists."""
        url = "https://example.com/jobs"
        result = extract_url_param(url, "jobId")
        assert result is None

    def test_extract_url_param_malformed_url(self):
        """Test that None is returned for malformed URLs."""
        result = extract_url_param("not a url", "jobId")
        assert result is None

    def test_extract_url_param_empty_url(self):
        """Test that None is returned for empty URL."""
        result = extract_url_param("", "jobId")
        assert result is None

    def test_extract_url_param_workday_format(self):
        """Test extracting 18-char jobId from Workday-style URL."""
        # Real Workday jobId format is typically 18 characters
        url = "https://mycompany.myworkdayjobs.com/en-US/mycompany-jobs/job/abc123xyz789123456/Senior-Developer"
        result = extract_url_param(url, "jobId")
        # This URL doesn't have jobId as query param, but test the extraction logic anyway
        assert result is None

    def test_extract_url_param_with_fragment(self):
        """Test extracting parameter when URL has fragment identifier."""
        url = "https://example.com/jobs?jobId=test123#section"
        result = extract_url_param(url, "jobId")
        assert result == "test123"


class TestParsePostedDate:
    """Test suite for parse_posted_date function."""

    def test_parse_posted_date_none_input(self):
        """Test that None input returns None."""
        result = parse_posted_date(None, datetime(2026, 9, 8, 10, 30))
        assert result is None

    def test_parse_posted_date_empty_string(self):
        """Test that empty string returns None."""
        result = parse_posted_date("", datetime(2026, 9, 8, 10, 30))
        assert result is None

    def test_parse_posted_date_today(self):
        """Test 'Posted Today' returns reference date."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("Posted Today", reference)
        assert result == "2026-09-08"

    def test_parse_posted_date_today_case_insensitive(self):
        """Test 'Posted Today' is case-insensitive."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("POSTED TODAY", reference)
        assert result == "2026-09-08"

    def test_parse_posted_date_yesterday(self):
        """Test 'Posted Yesterday' returns reference - 1 day."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("Posted Yesterday", reference)
        assert result == "2026-09-07"

    def test_parse_posted_date_yesterday_case_insensitive(self):
        """Test 'Posted Yesterday' is case-insensitive."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("posted yesterday", reference)
        assert result == "2026-09-07"

    def test_parse_posted_date_n_days_ago(self):
        """Test 'Posted N Days Ago' returns reference - N days."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("Posted 8 Days Ago", reference)
        assert result == "2026-08-31"

    def test_parse_posted_date_n_days_ago_single_day(self):
        """Test 'Posted 1 Days Ago' (singular 'day' variant)."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("Posted 1 Day Ago", reference)
        assert result == "2026-09-07"

    def test_parse_posted_date_n_days_ago_case_insensitive(self):
        """Test 'Posted N Days Ago' is case-insensitive."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("POSTED 5 DAYS AGO", reference)
        assert result == "2026-09-03"

    def test_parse_posted_date_30_plus_days_ago(self):
        """Test 'Posted 30+ Days Ago' returns reference - 30 days."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("Posted 30+ Days Ago", reference)
        assert result == "2026-08-09"

    def test_parse_posted_date_30_plus_days_ago_case_insensitive(self):
        """Test 'Posted 30+ Days Ago' is case-insensitive."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("posted 30+ days ago", reference)
        assert result == "2026-08-09"

    def test_parse_posted_date_garbage_text(self):
        """Test that garbage text returns None."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("Some random text", reference)
        assert result is None

    def test_parse_posted_date_whitespace_trimmed(self):
        """Test that leading/trailing whitespace is handled."""
        reference = datetime(2026, 9, 8, 10, 30)
        result = parse_posted_date("  Posted 3 Days Ago  ", reference)
        assert result == "2026-09-05"

    def test_parse_posted_date_month_boundary(self):
        """Test date calculation across month boundary."""
        reference = datetime(2026, 9, 5, 10, 30)
        result = parse_posted_date("Posted 10 Days Ago", reference)
        assert result == "2026-08-26"

    def test_parse_posted_date_year_boundary(self):
        """Test date calculation across year boundary."""
        reference = datetime(2026, 1, 5, 10, 30)
        result = parse_posted_date("Posted 10 Days Ago", reference)
        assert result == "2025-12-26"


class TestParseField:
    """Test suite for parse_field helper function."""

    def test_parse_field_basic_extraction(self):
        """Test extracting a field value after a label."""
        text = "Job types: Contract\nLocation type: Hybrid\nSkills: Python"
        result = parse_field(text, "Job types:", "Location type:")
        assert result == "Contract"

    def test_parse_field_with_next_field(self):
        """Test extracting between two labels."""
        text = "Job types: Full-Time\nLocation type: Hybrid\nSkills: Python, Java"
        result = parse_field(text, "Location type:", "Skills:")
        assert result == "Hybrid"

    def test_parse_field_without_next_field(self):
        """Test extracting to end of text when no next_field provided."""
        text = "Job types: Contract\nLocation type: Hybrid"
        result = parse_field(text, "Location type:")
        assert result is not None
        assert result.startswith("Hybrid")

    def test_parse_field_none_input(self):
        """Test that None input returns None."""
        result = parse_field(None, "Job types:", "Location type:")
        assert result is None

    def test_parse_field_label_not_found(self):
        """Test that None is returned when label not found."""
        text = "Job types: Contract\nLocation type: Hybrid"
        result = parse_field(text, "Compensation:", "Skills:")
        assert result is None

    def test_parse_field_empty_text(self):
        """Test that empty text returns None."""
        result = parse_field("", "Job types:", "Location type:")
        assert result is None

    def test_parse_field_with_whitespace(self):
        """Test that whitespace is stripped from extracted value."""
        text = "Job types:   Full-Time  \nLocation type: Hybrid"
        result = parse_field(text, "Job types:", "Location type:")
        assert result == "Full-Time"

    def test_parse_field_length_limit(self):
        """Test that extracted value is limited to 100 characters."""
        long_value = "a" * 150
        text = f"Job types: {long_value}\nLocation type: Hybrid"
        result = parse_field(text, "Job types:", "Location type:")
        assert result == "a" * 100

    def test_parse_field_multiline_value(self):
        """Test extracting multiline field values."""
        text = "Description: Senior role\nwith benefits\nLocation: Remote"
        result = parse_field(text, "Description:", "Location:")
        assert result is not None
        assert "Senior role" in result
        assert "with benefits" in result

    def test_parse_field_special_chars(self):
        """Test parsing fields with special characters."""
        text = "Salary: $120k - $150k/year\nBenefits: Healthcare, 401k"
        result = parse_field(text, "Salary:", "Benefits:")
        assert result is not None
        assert "$120k - $150k/year" in result


class TestExtractDetailPageFields:
    """Test suite for extract_detail_page_fields async function."""

    @pytest.mark.asyncio
    async def test_extract_detail_page_fields_successful(self):
        """Test successful extraction of all detail page fields."""
        page = AsyncMock()

        # Mock successful navigation
        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True

            # Mock description extraction
            description_elem = AsyncMock()
            description_elem.text_content = AsyncMock(return_value="Senior Python role with 5+ years experience")

            # Mock details container
            details_container = AsyncMock()
            details_container.text_content = AsyncMock(
                return_value="Job types: Contract\nLocation type: Hybrid\nSkills: Python"
            )

            # Mock compensation extraction
            compensation_elem = AsyncMock()
            compensation_elem.text_content = AsyncMock(return_value="$120k - $150k")

            async def query_selector_side_effect(sel):
                if sel == ".job-description":
                    return description_elem
                elif sel == "div.job-details":
                    return details_container
                elif sel == ".compensation":
                    return compensation_elem
                return None

            page.query_selector = AsyncMock(side_effect=query_selector_side_effect)
            page.wait_for_timeout = AsyncMock()

            selectors = {
                "detail_page_description": ".job-description",
                "detail_page_details_container": "div.job-details",
                "detail_page_compensation": ".compensation",
            }

            result = await extract_detail_page_fields(page, "https://example.com/jobs?jobId=abc123", selectors)

        # Verify all fields extracted
        assert result["description"] == "Senior Python role with 5+ years experience"
        assert result["job_id"] == "abc123"
        assert result["job_type"] == "Contract"
        assert result["location_type"] == "Hybrid"
        assert result["compensation"] == "$120k - $150k"

    @pytest.mark.asyncio
    async def test_extract_detail_page_fields_navigation_failure(self):
        """Test graceful fallback when detail page navigation fails."""
        page = AsyncMock()

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = False  # Navigation fails

            selectors: dict[str, str] = {}
            result = await extract_detail_page_fields(page, "https://example.com/jobs?jobId=abc123", selectors)

        # Should return all None values on navigation failure
        assert result["description"] is None
        assert result["job_id"] == "abc123"  # Should still extract from URL
        assert result["job_type"] is None
        assert result["location_type"] is None
        assert result["compensation"] is None

    @pytest.mark.asyncio
    async def test_extract_detail_page_fields_partial_extraction(self):
        """Test extraction when only some fields are available."""
        page = AsyncMock()

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True

            # Mock only description selector (others not provided)
            description_elem = AsyncMock()
            description_elem.text_content = AsyncMock(return_value="Job description text")

            page.query_selector = AsyncMock(return_value=description_elem)
            page.wait_for_timeout = AsyncMock()

            selectors = {
                "detail_page_description": ".description",
                # No details_container, compensation, or job_id selectors
            }

            result = await extract_detail_page_fields(page, "https://example.com/jobs?jobId=xyz789", selectors)

        # Should have description from selector and job_id from URL
        assert result["description"] == "Job description text"
        assert result["job_id"] == "xyz789"
        # Others should be None
        assert result["job_type"] is None
        assert result["location_type"] is None
        assert result["compensation"] is None

    @pytest.mark.asyncio
    async def test_extract_detail_page_fields_no_job_id_in_url(self):
        """Test extraction when jobId is not in URL."""
        page = AsyncMock()

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True

            page.query_selector = AsyncMock(return_value=None)
            page.wait_for_timeout = AsyncMock()

            selectors: dict[str, str] = {}

            result = await extract_detail_page_fields(
                page,
                "https://example.com/jobs/senior-role",
                selectors,  # No jobId param
            )

        # job_id should be None when not in URL and no selector provided
        assert result["job_id"] is None

    @pytest.mark.asyncio
    async def test_extract_detail_page_fields_job_id_from_selector(self):
        """Test extraction of job_id from selector when URL param missing."""
        page = AsyncMock()

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True

            # Mock job_id selector
            job_id_elem = AsyncMock()
            job_id_elem.text_content = AsyncMock(return_value="job-abc-123")

            page.query_selector = AsyncMock(return_value=job_id_elem)
            page.wait_for_timeout = AsyncMock()

            selectors = {
                "detail_page_job_id": ".job-id-field",
            }

            result = await extract_detail_page_fields(page, "https://example.com/jobs/senior-role", selectors)

        # Should extract job_id from selector
        assert result["job_id"] == "job-abc-123"

    @pytest.mark.asyncio
    async def test_extract_detail_page_fields_exception_handling(self):
        """Test graceful exception handling during extraction."""
        page = AsyncMock()

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.side_effect = Exception("Navigation error")

            selectors: dict[str, str] = {}
            result = await extract_detail_page_fields(page, "https://example.com/jobs?jobId=abc123", selectors)

        # Should handle exception gracefully and return default dict
        assert result["description"] is None
        assert result["job_type"] is None
        assert result["location_type"] is None
        assert result["compensation"] is None


class TestExtractJobFromContainer:
    """Test suite for extract_job_from_container function."""

    @pytest.mark.asyncio
    async def test_extract_job_from_container_full_schema(self):
        """Test that extract_job_from_container returns all 13 required fields."""
        # Mock page and container
        page = AsyncMock()
        container = AsyncMock()

        # Mock element queries
        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Senior Python Developer")

        location_elem = AsyncMock()
        location_elem.text_content = AsyncMock(return_value="San Francisco, CA")

        link_elem = AsyncMock()
        link_elem.get_attribute = AsyncMock(return_value="https://example.com/jobs/123")

        # Setup container.query_selector to return mocked elements
        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "location":
                return location_elem
            elif selector == "link":
                return link_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)  # No shadow DOM

        # Call function
        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="Carbon Robotics",
            selectors={"title": "title", "location": "location", "link": "link"},
            base_url="https://example.com/",
        )

        # Verify all 13 fields are present
        assert result is not None
        expected_fields = {
            "id",
            "title",
            "company",
            "location",
            "url",
            "description",
            "requirements",
            "salary_min",
            "salary_max",
            "posted_date",
            "crawled_at",
            "status",
            "source_config",
        }
        assert set(result.keys()) == expected_fields

    @pytest.mark.asyncio
    async def test_extract_job_from_container_id_deterministic(self):
        """Test that same inputs produce identical job IDs (deterministic hashing)."""
        # Mock page and container
        page = AsyncMock()
        container = AsyncMock()

        # Mock element queries
        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Python Engineer")

        location_elem = AsyncMock()
        location_elem.text_content = AsyncMock(return_value="Remote")

        link_elem = AsyncMock()
        link_elem.get_attribute = AsyncMock(return_value="https://example.com/jobs/456")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "location":
                return location_elem
            elif selector == "link":
                return link_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)  # No shadow DOM

        # Call function twice with same inputs
        result1 = await extract_job_from_container(
            page=page,
            container=container,
            company_name="TechCorp",
            selectors={"title": "title", "location": "location", "link": "link"},
            base_url="https://example.com/",
        )

        result2 = await extract_job_from_container(
            page=page,
            container=container,
            company_name="TechCorp",
            selectors={"title": "title", "location": "location", "link": "link"},
            base_url="https://example.com/",
        )

        # IDs should be identical
        assert result1 is not None
        assert result2 is not None
        assert result1["id"] == result2["id"]
        assert result1["id"].startswith("workday:") or ":" in result1["id"]  # Should have portal:hash format

    @pytest.mark.asyncio
    async def test_extract_job_from_container_no_title_returns_none(self):
        """Test that missing title returns None (existing behavior preserved)."""
        page = AsyncMock()
        container = AsyncMock()

        # No title element
        container.query_selector = AsyncMock(return_value=None)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="TechCorp",
            selectors={"title": "title", "location": "location", "link": "link"},
            base_url="",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_job_from_container_no_url_still_generates_id(self):
        """Test that missing URL doesn't prevent ID generation (fallback path works)."""
        page = AsyncMock()
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Data Scientist")

        location_elem = AsyncMock()
        location_elem.text_content = AsyncMock(return_value="New York")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "location":
                return location_elem
            elif selector == "link":
                return None  # No URL
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="DataCorp",
            selectors={"title": "title", "location": "location", "link": "link"},
            base_url="",
        )

        # Should still have an ID
        assert result is not None
        assert result["id"] is not None
        assert ":" in result["id"]  # Should have portal:hash format
        assert result["url"] == ""  # URL should be empty string

    @pytest.mark.asyncio
    async def test_extract_job_from_container_defaults(self):
        """Test that description, requirements, salary_* default to None."""
        page = AsyncMock()
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Frontend Developer")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            return None  # All other fields None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="WebCorp",
            selectors={"title": "title"},
            base_url="",
        )

        assert result is not None
        assert result["description"] is None
        assert result["requirements"] is None
        assert result["salary_min"] is None
        assert result["salary_max"] is None
        assert result["posted_date"] is None

    @pytest.mark.asyncio
    async def test_extract_job_from_container_posted_date_extraction(self):
        """Test that posted_date is extracted and parsed from posted_on selector."""
        page = AsyncMock()
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Backend Developer")

        posted_on_elem = AsyncMock()
        posted_on_elem.text_content = AsyncMock(return_value="Posted 5 Days Ago")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "posted_on":
                return posted_on_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="TechCorp",
            selectors={"title": "title", "posted_on": "posted_on"},
            base_url="",
        )

        assert result is not None
        assert result["posted_date"] is not None
        # Verify it's a valid ISO date string
        assert len(result["posted_date"]) == 10  # YYYY-MM-DD format
        assert result["posted_date"].count("-") == 2

    @pytest.mark.asyncio
    async def test_extract_job_from_container_posted_date_none_when_no_selector(self):
        """Test that posted_date is None when posted_on selector is not provided."""
        page = AsyncMock()
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="DevOps Engineer")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="CloudCorp",
            selectors={"title": "title"},  # No posted_on selector
            base_url="",
        )

        assert result is not None
        assert result["posted_date"] is None

    @pytest.mark.asyncio
    async def test_extract_job_from_container_posted_date_unparseable_text(self):
        """Test that posted_date is None for unparseable posted_on text."""
        page = AsyncMock()
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="QA Engineer")

        posted_on_elem = AsyncMock()
        posted_on_elem.text_content = AsyncMock(return_value="Some random text")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "posted_on":
                return posted_on_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="TestCorp",
            selectors={"title": "title", "posted_on": "posted_on"},
            base_url="",
        )

        assert result is not None
        assert result["posted_date"] is None

    @pytest.mark.asyncio
    async def test_extract_job_from_container_status_default(self):
        """Test that status defaults to 'pending_review'."""
        page = AsyncMock()
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="DevOps Engineer")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="CloudCorp",
            selectors={"title": "title"},
            base_url="",
        )

        assert result is not None
        assert result["status"] == "pending_review"

    @pytest.mark.asyncio
    async def test_extract_job_from_container_crawled_at_format(self):
        """Test that crawled_at is in ISO 8601 format with aware UTC timezone."""
        page = AsyncMock()
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="QA Engineer")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="TestCorp",
            selectors={"title": "title"},
            base_url="",
        )

        assert result is not None
        crawled_at = result["crawled_at"]
        # Should be parseable as ISO format
        dt = datetime.fromisoformat(crawled_at)
        assert dt is not None
        # Should have timezone suffix (aware UTC with +00:00)
        assert crawled_at.endswith("+00:00")
        assert not crawled_at.endswith("Z")

    @pytest.mark.asyncio
    async def test_extract_job_from_container_field_types(self):
        """Test that returned fields have correct types."""
        page = AsyncMock()
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="ML Engineer")

        location_elem = AsyncMock()
        location_elem.text_content = AsyncMock(return_value="Boston")

        link_elem = AsyncMock()
        link_elem.get_attribute = AsyncMock(return_value="/jobs/789")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "location":
                return location_elem
            elif selector == "link":
                return link_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="AILabs",
            selectors={"title": "title", "location": "location", "link": "link"},
            base_url="https://careers.ai.com/",
        )

        assert result is not None
        assert isinstance(result["id"], str)
        assert isinstance(result["title"], str)
        assert isinstance(result["company"], str)
        assert isinstance(result["location"], str)
        assert isinstance(result["url"], str)
        assert result["description"] is None
        assert result["requirements"] is None
        assert isinstance(result["crawled_at"], str)
        assert isinstance(result["status"], str)

    @pytest.mark.asyncio
    async def test_extract_company_from_card(self):
        """Test that company is extracted from card when selector present, falling back to config name."""
        page = AsyncMock()
        container = AsyncMock()

        # Mock title element
        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Senior Engineer")

        # Mock company element
        company_elem = AsyncMock()
        company_elem.text_content = AsyncMock(return_value="Microsoft")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == ".company":  # company selector
                return company_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="WorkSource for Jobs",
            selectors=cast(dict[str, str], {"title": "title", "company": ".company", "location": None, "link": None}),
            base_url="",
        )

        assert result is not None
        # Should use extracted company name, not fallback
        assert result["company"] == "Microsoft"

    @pytest.mark.asyncio
    async def test_extract_company_from_card_shadow_dom(self):
        """Test that company is extracted from shadow DOM when direct selector fails."""
        page = AsyncMock()
        container = AsyncMock()

        # Mock title element
        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Senior Engineer")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "p.company-name":
                return None  # Direct selector fails
            return None

        # Mock evaluate to return company from shadow DOM
        async def evaluate_side_effect(js_code, *args):
            # args[0] is the selector passed as parameter
            if args and args[0] == "p.company-name":
                return "Apple"
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(side_effect=evaluate_side_effect)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="WorkSource for Jobs",
            selectors=cast(
                dict[str, str], {"title": "title", "company": "p.company-name", "location": None, "link": None}
            ),
            base_url="",
        )

        assert result is not None
        # Should use extracted company from shadow DOM
        assert result["company"] == "Apple"

    @pytest.mark.asyncio
    async def test_extract_company_fallback_to_config_name(self):
        """Test that company falls back to config display name when per-card extraction unavailable."""
        page = AsyncMock()
        container = AsyncMock()

        # Mock title element
        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Senior Engineer")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            # No company selector provided
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="Google",
            selectors=cast(dict[str, str], {"title": "title", "location": None, "link": None}),
            base_url="",
        )

        assert result is not None
        # Should use config display name as fallback
        assert result["company"] == "Google"

    @pytest.mark.asyncio
    async def test_extract_description_from_container(self):
        """Test that description is extracted when selector is configured (not None)."""
        page = AsyncMock()
        container = AsyncMock()

        # Mock title element (required)
        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Senior Python Developer")

        # Mock description element
        desc_elem = AsyncMock()
        desc_elem.text_content = AsyncMock(
            return_value="We are looking for an experienced Python developer with 5+ years of experience."
        )

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == ".job-description":
                return desc_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="TechCorp",
            selectors={"title": "title", "description": ".job-description"},
            base_url="",
        )

        assert result is not None
        assert result["description"] is not None
        assert (
            result["description"] == "We are looking for an experienced Python developer with 5+ years of experience."
        )

    @pytest.mark.asyncio
    async def test_extract_description_shadow_dom(self):
        """Test that description is extracted from shadow DOM when direct selector fails."""
        page = AsyncMock()
        container = AsyncMock()

        # Mock title element
        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Senior Engineer")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "div.description":
                return None  # Direct selector fails
            return None

        # Mock evaluate to return description from shadow DOM
        async def evaluate_side_effect(js_code, *args):
            # args[0] is the selector passed as parameter
            if args and args[0] == "div.description":
                return "This is a job description from shadow DOM"
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(side_effect=evaluate_side_effect)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="TechCorp",
            selectors={"title": "title", "description": "div.description"},
            base_url="",
        )

        assert result is not None
        assert result["description"] == "This is a job description from shadow DOM"

    @pytest.mark.asyncio
    async def test_extract_job_worksource_click_and_extract_jobid(self):
        """Test that WorkSource jobs click link and extract jobId from detail page URL."""
        page = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.go_back = AsyncMock()
        # Simulate page.url changing after click
        page.url = "https://careers.worksource.com/en-US/jobs/job/abc123xyz789/?jobId=abc123xyz789"
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Senior Developer")

        link_elem = AsyncMock()
        # Link without jobId parameter
        link_elem.get_attribute = AsyncMock(return_value="/en-US/jobs/job/abc123xyz789/")
        # Mock click to simulate navigation
        link_elem.click = AsyncMock()

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "a.job-link":
                return link_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="WorkSource",
            company_key="WorkSource",
            selectors={"title": "title", "link": "a.job-link"},
            base_url="https://careers.worksource.com/",
        )

        assert result is not None
        # Should have extracted jobId from page.url after click
        assert "jobId=abc123xyz789" in result["url"]
        # Link SHOULD have been clicked (WorkSource behavior)
        link_elem.click.assert_called()

    @pytest.mark.asyncio
    async def test_extract_job_non_worksource_skips_jobid_extraction(self):
        """Test that non-WorkSource companies skip jobId extraction logic."""
        page = AsyncMock()
        page.url = "https://careers.boeing.com/jobs/search"
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Aircraft Systems Engineer")

        link_elem = AsyncMock()
        link_elem.get_attribute = AsyncMock(return_value="/jobs/aircraft-systems-engineer")
        # Should NOT be called for non-WorkSource companies
        link_elem.click = AsyncMock()

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "a.job-link":
                return link_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        page.wait_for_timeout = AsyncMock()
        page.go_back = AsyncMock()

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="Boeing",  # Not WorkSource
            selectors={"title": "title", "link": "a.job-link"},
            base_url="https://careers.boeing.com/jobs/search",
        )

        assert result is not None
        # Should use simple URL join, not jobId extraction
        assert result["url"] == "https://careers.boeing.com/jobs/aircraft-systems-engineer"
        # Link should NOT have been clicked (no jobId extraction for non-WorkSource)
        link_elem.click.assert_not_called()
        # page.wait_for_timeout should NOT have been called
        page.wait_for_timeout.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_job_records_source_config_key_not_extracted_company(self):
        """source_config is the config key even when the card's company differs from it."""
        page = AsyncMock()
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Platform Engineer")

        company_elem = AsyncMock()
        company_elem.text_content = AsyncMock(return_value="Acme Robotics Ltd")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            if selector == ".company":
                return company_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="Carbon Robotics",
            selectors={"title": "title", "company": ".company", "location": None, "link": None},
            base_url="",
            company_key="CarbonRobotics",
        )

        assert result is not None
        assert result["company"] == "Acme Robotics Ltd"
        assert result["source_config"] == "CarbonRobotics"

    @pytest.mark.asyncio
    async def test_extract_job_source_config_defaults_to_empty_key(self):
        """Without company_key, source_config is the empty default, not the display name."""
        page = AsyncMock()
        container = AsyncMock()

        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="QA Analyst")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        result = await extract_job_from_container(
            page=page,
            container=container,
            company_name="Carbon Robotics",
            selectors={"title": "title", "location": None, "link": None},
            base_url="",
        )

        assert result is not None
        assert result["company"] == "Carbon Robotics"
        assert result["source_config"] == ""

    @pytest.mark.asyncio
    async def test_crawl_company_jobs_source_config_is_config_key(self):
        """crawl output records carry the config key in source_config, independent of extracted company."""
        browser = AsyncMock()
        page = MagicMock()
        browser.new_page = AsyncMock(return_value=page)

        container = AsyncMock()
        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Backend Developer")
        company_elem = AsyncMock()
        company_elem.text_content = AsyncMock(return_value="Acme Robotics Ltd")

        async def query_selector_side_effect(selector):
            if selector == ".job-title":
                return title_elem
            if selector == ".job-company":
                return company_elem
            return None

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        page.query_selector_all = AsyncMock(return_value=[container])
        page.wait_for_selector = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.close = AsyncMock()
        page.set_default_timeout = MagicMock()

        company_config = {
            "enabled": True,
            "name": "Carbon Robotics",
            "url": "https://example.com/careers",
            "selectors": {
                "job_container": ".job-card",
                "job_card": ".job-card",
                "title": ".job-title",
                "company": ".job-company",
                "location": None,
                "link": None,
            },
            "crawler": {"delay_ms": 0, "max_jobs_debug": None},
        }

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True
            jobs = await crawl_company_jobs(
                browser=browser,
                company_key="CarbonRobotics",
                company_config=company_config,
                timeout_ms=30000,
            )

        assert len(jobs) == 1
        assert jobs[0]["company"] == "Acme Robotics Ltd"
        assert jobs[0]["source_config"] == "CarbonRobotics"


class TestCrawlCompanyJobs:
    """Test suite for crawl_company_jobs function."""

    @pytest.mark.asyncio
    async def test_crawl_company_jobs_uses_display_name(self):
        """Test that company display name from config is used in extracted jobs (fallback path)."""
        browser = AsyncMock()
        page = MagicMock()  # Use MagicMock for sync methods like set_default_timeout
        browser.new_page = AsyncMock(return_value=page)

        # Mock container
        container = AsyncMock()
        title_elem = AsyncMock()
        title_elem.text_content = AsyncMock(return_value="Backend Developer")

        location_elem = AsyncMock()
        location_elem.text_content = AsyncMock(return_value="Remote")

        async def query_selector_side_effect(selector):
            if selector == "title":
                return title_elem
            elif selector == "location":
                return location_elem
            elif selector == "job_container":
                return [container]
            return None

        page.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        page.query_selector_all = AsyncMock(return_value=[container])
        page.wait_for_selector = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.close = AsyncMock()

        container.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        container.evaluate = AsyncMock(return_value=None)

        company_config = {
            "enabled": True,
            "name": "Carbon Robotics",  # Display name
            "url": "https://example.com/careers",
            "selectors": {
                "job_container": "job_container",
                "title": "title",
                "location": "location",
                "link": None,
            },
            "crawler": {},
        }

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True
            jobs = await crawl_company_jobs(
                browser=browser,
                company_key="CarbonRobotics",  # Key
                company_config=company_config,
                timeout_ms=30000,
            )

        assert len(jobs) > 0
        # Company field should be display name (fallback), not key
        assert jobs[0]["company"] == "Carbon Robotics"

    @pytest.mark.asyncio
    async def test_crawl_company_jobs_skip_disabled(self):
        """Test that disabled companies are skipped."""
        browser = AsyncMock()

        company_config = {
            "enabled": False,  # Disabled
            "name": "Test Company",
            "url": "https://example.com/careers",
        }

        jobs = await crawl_company_jobs(
            browser=browser,
            company_key="TestCompany",
            company_config=company_config,
            timeout_ms=30000,
        )

        assert jobs == []
        browser.new_page.assert_not_called()

    @pytest.mark.asyncio
    async def test_crawl_company_jobs_no_url(self):
        """Test that companies without URL are skipped."""
        browser = AsyncMock()

        company_config = {
            "enabled": True,
            "name": "Test Company",
            # No URL
        }

        jobs = await crawl_company_jobs(
            browser=browser,
            company_key="TestCompany",
            company_config=company_config,
            timeout_ms=30000,
        )

        assert jobs == []
        browser.new_page.assert_not_called()

    @pytest.mark.asyncio
    async def test_crawl_worksource_integration(self):
        """Test WorkSource config integration: mocked browser with multiple job containers.

        Validates that crawl_company_jobs:
        - Extracts 3 job containers with distinct titles and locations
        - Returns full 12-field schema per job
        - Preserves company name from config
        - Properly parses selector-based field extraction
        """
        browser = AsyncMock()
        page = MagicMock()  # Use MagicMock for sync methods like set_default_timeout
        browser.new_page = AsyncMock(return_value=page)

        # Create 3 job containers with distinct data
        containers = []
        job_data = [
            ("Senior Python Developer", "San Francisco, CA"),
            ("DevOps Engineer", "Remote"),
            ("Data Scientist", "New York, NY"),
        ]

        for title, location in job_data:
            container = AsyncMock()

            # Create element mocks
            title_elem = AsyncMock()
            title_elem.text_content = AsyncMock(return_value=title)

            location_elem = AsyncMock()
            location_elem.text_content = AsyncMock(return_value=location)

            link_elem = AsyncMock()
            link_elem.get_attribute = AsyncMock(
                return_value=f"https://careers.worksource.com/jobs/{title.lower().replace(' ', '-')}"
            )

            posted_elem = AsyncMock()
            posted_elem.text_content = AsyncMock(return_value="Posted 2 Days Ago")

            # Store in container with direct dict lookup
            element_map = {
                ".job-title": title_elem,
                ".job-location": location_elem,
                "a.job-link": link_elem,
                ".posted-date": posted_elem,
            }

            async def make_side_effect(elem_map):
                async def side_effect(sel):
                    return elem_map.get(sel)

                return side_effect

            container.query_selector = AsyncMock(side_effect=await make_side_effect(element_map))
            containers.append(container)

        # Setup page mocks
        page.query_selector_all = AsyncMock(return_value=containers)
        page.wait_for_selector = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.close = AsyncMock()
        page.set_default_timeout = MagicMock()  # Sync mock
        page.go_back = AsyncMock()  # Mock go_back() as async method
        page.url = "https://careers.worksource.com/jobs"  # Mock url property
        page.goto = AsyncMock()  # Mock goto() as async method

        # WorkSource config
        company_config = {
            "enabled": True,
            "name": "WorkSource",
            "url": "https://careers.worksource.com/jobs",
            "selectors": {
                "job_container": ".job-card",
                "job_card": ".job-card",
                "title": ".job-title",
                "location": ".job-location",
                "link": "a.job-link",
                "posted_on": ".posted-date",
            },
            "crawler": {
                "delay_ms": 0,
                "max_jobs_debug": None,
            },
        }

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True
            jobs = await crawl_company_jobs(
                browser=browser,
                company_key="WorkSource",
                company_config=company_config,
                timeout_ms=30000,
            )

        # Assertions
        assert len(jobs) == 3, f"Expected 3 jobs, got {len(jobs)}"

        # Verify schema
        for job in jobs:
            expected_fields = {
                "id",
                "title",
                "company",
                "location",
                "url",
                "description",
                "requirements",
                "salary_min",
                "salary_max",
                "posted_date",
                "crawled_at",
                "status",
                "source_config",
            }
            assert set(job.keys()) == expected_fields

        # Verify titles
        titles = [job["title"] for job in jobs]
        assert "Senior Python Developer" in titles
        assert "DevOps Engineer" in titles
        assert "Data Scientist" in titles

        # Verify locations
        locations = [job["location"] for job in jobs]
        assert "San Francisco, CA" in locations
        assert "Remote" in locations
        assert "New York, NY" in locations

        # Verify company name from config
        for job in jobs:
            assert job["company"] == "WorkSource"

        # Verify posted dates are parsed
        for job in jobs:
            assert job["posted_date"] is not None
            assert len(job["posted_date"]) == 10


class TestExtractDetailPageDirectSelectors:
    """Test suite for detail page extraction using direct selectors (Issue coordinator update)."""

    @pytest.mark.asyncio
    async def test_extract_detail_page_with_all_direct_selectors(self):
        """Test extraction of all detail page fields using direct selectors (WorkSource config format)."""
        page = AsyncMock()

        # Mock all direct selector elements
        description_elem = AsyncMock()
        description_elem.text_content = AsyncMock(return_value="Senior Python developer with 5+ years")

        job_id_elem = AsyncMock()
        job_id_elem.text_content = AsyncMock(return_value="abc123xyz789")

        job_type_elem = AsyncMock()
        job_type_elem.text_content = AsyncMock(return_value="Full-Time")

        compensation_elem = AsyncMock()
        compensation_elem.text_content = AsyncMock(return_value="$120,000 - $150,000")

        async def query_selector_side_effect(sel):
            if sel == "div.common-jobdetails-job-description":
                return description_elem
            elif sel == "p.wswa-h5:nth-child(5)":
                return job_id_elem
            elif sel == "p.detail-amount:nth-child(3) > span:nth-child(1)":
                return job_type_elem
            elif sel == "p.detail-amount:nth-child(2)":
                return compensation_elem
            return None

        page.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        page.wait_for_timeout = AsyncMock()

        # Use WorkSource config selectors
        selectors = {
            "detail_page_description": "div.common-jobdetails-job-description",
            "detail_page_job_id": "p.wswa-h5:nth-child(5)",
            "detail_page_job_type": "p.detail-amount:nth-child(3) > span:nth-child(1)",
            "detail_page_compensation": "p.detail-amount:nth-child(2)",
        }

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True
            result = await extract_detail_page_fields(
                page,
                "https://example.com/jobs",
                selectors,  # No jobId in URL - should use selector
            )

        # Verify all fields extracted via direct selectors
        assert result["description"] == "Senior Python developer with 5+ years"
        assert result["job_id"] == "abc123xyz789"  # From selector (URL has no jobId)
        assert result["job_type"] == "Full-Time"
        assert result["compensation"] == "$120,000 - $150,000"

    @pytest.mark.asyncio
    async def test_extract_detail_page_job_type_direct_selector(self):
        """Test job_type extraction via direct selector (no text parsing needed)."""
        page = AsyncMock()

        job_type_elem = AsyncMock()
        job_type_elem.text_content = AsyncMock(return_value="Contract")

        page.query_selector = AsyncMock(return_value=job_type_elem)
        page.wait_for_timeout = AsyncMock()

        selectors = {
            "detail_page_job_type": "p.detail-amount:nth-child(3) > span:nth-child(1)",
        }

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True
            result = await extract_detail_page_fields(page, "https://example.com/jobs?jobId=test", selectors)

        # Should extract job_type from direct selector
        assert result["job_type"] == "Contract"

    @pytest.mark.asyncio
    async def test_extract_detail_page_job_type_fallback_text_parsing(self):
        """Test that job_type falls back to text parsing if direct selector not configured."""
        page = AsyncMock()

        # Mock details container for text parsing fallback
        details_container = AsyncMock()
        details_container.text_content = AsyncMock(
            return_value="Job types: Part-Time\nLocation type: Remote\nSkills: Python"
        )

        async def query_selector_side_effect(sel):
            if sel == "div.job-details":
                return details_container
            return None

        page.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        page.wait_for_timeout = AsyncMock()

        selectors = {
            "detail_page_details_container": "div.job-details",
            # No detail_page_job_type selector - should fall back to text parsing
        }

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True
            result = await extract_detail_page_fields(page, "https://example.com/jobs?jobId=test", selectors)

        # Should fall back to text parsing
        assert result["job_type"] == "Part-Time"
        assert result["location_type"] == "Remote"

    @pytest.mark.asyncio
    async def test_extract_detail_page_prefers_direct_selector_over_parsing(self):
        """Test that direct selector takes precedence over text parsing."""
        page = AsyncMock()

        # Mock direct selector
        job_type_elem = AsyncMock()
        job_type_elem.text_content = AsyncMock(return_value="Full-Time")

        # Mock details container (should not be used)
        details_container = AsyncMock()
        details_container.text_content = AsyncMock(return_value="Job types: Contract\nLocation type: Hybrid")

        async def query_selector_side_effect(sel):
            if sel == "p.detail-amount:nth-child(3) > span:nth-child(1)":
                return job_type_elem
            elif sel == "div.job-details":
                return details_container
            return None

        page.query_selector = AsyncMock(side_effect=query_selector_side_effect)
        page.wait_for_timeout = AsyncMock()

        selectors = {
            "detail_page_job_type": "p.detail-amount:nth-child(3) > span:nth-child(1)",
            "detail_page_details_container": "div.job-details",
        }

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True
            result = await extract_detail_page_fields(page, "https://example.com/jobs?jobId=test", selectors)

        # Should use direct selector result, not text parsing result
        assert result["job_type"] == "Full-Time"

    @pytest.mark.asyncio
    async def test_extract_detail_page_with_location_type_direct_selector(self):
        """Test location_type extraction via direct selector."""
        page = AsyncMock()

        location_type_elem = AsyncMock()
        location_type_elem.text_content = AsyncMock(return_value="Hybrid")

        page.query_selector = AsyncMock(return_value=location_type_elem)
        page.wait_for_timeout = AsyncMock()

        selectors = {
            "detail_page_location_type": "p.detail-amount:nth-child(4)",
        }

        with patch("src.poc.tweak.crawl_list.retry_goto", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = True
            result = await extract_detail_page_fields(page, "https://example.com/jobs?jobId=test", selectors)

        # Should extract location_type from direct selector
        assert result["location_type"] == "Hybrid"
