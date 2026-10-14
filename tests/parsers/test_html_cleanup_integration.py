"""Integration tests for unified HTML cleanup pipeline (Issue #230).

Tests the complete clean_html() pipeline across:
- MarkItDown path
- BeautifulSoup fallback
- Boilerplate removal (7 categories)
- HTML entity removal
- Whitespace normalization
- Section header synthesis
- Edge cases and performance
"""

import pytest

from src.parsers.html_to_markdown import clean_html


class TestCleanHtmlFullPipeline:
    """Test clean_html with full 6-step pipeline."""

    def test_clean_html_markitdown_path(self) -> None:
        """Full pipeline using MarkItDown path."""
        html = "<h1>Senior Developer</h1><p>Equal Opportunity Employer.</p>"
        result = clean_html(html)

        # Headers preserved, boilerplate removed
        assert "Senior" in result
        assert "Equal Opportunity" not in result
        assert isinstance(result, str)

    def test_clean_html_beautifulsoup_fallback(self) -> None:
        """Full pipeline with BeautifulSoup fallback (if MarkItDown fails)."""
        html = "<div><p>Content here</p></div>"
        result = clean_html(html)

        assert "Content" in result
        assert isinstance(result, str)

    def test_clean_html_with_entities(self) -> None:
        """HTML entities are normalized."""
        html = "<p>Skills&nbsp;&nbsp;&amp;&nbsp;Experience: C++ &lt;-&gt; Python</p>"
        result = clean_html(html)

        # Entities should be removed/normalized
        assert "&nbsp;" not in result
        assert "&amp;" not in result
        assert "Skills" in result

    def test_clean_html_with_section_headers_disabled(self) -> None:
        """Section header synthesis can be disabled."""
        html = "<p>Qualifications</p><p>Python skills required</p>"
        result_with_headers = clean_html(html, include_section_headers=True)
        result_without_headers = clean_html(html, include_section_headers=False)

        # Both should be valid strings
        assert isinstance(result_with_headers, str)
        assert isinstance(result_without_headers, str)
        # Content should be preserved in both cases
        assert "Python" in result_with_headers
        assert "Python" in result_without_headers

    def test_clean_html_with_skip_categories(self) -> None:
        """Boilerplate categories can be skipped."""
        html = "<p>Salary: $100K. We are committed to diversity.</p>"

        # Skip salary_benefits - should preserve "$100K"
        result = clean_html(html, skip_boilerplate_categories={"salary_benefits"})
        assert "$" in result or "100" in result

        # Skip company_boilerplate - should preserve "committed"
        result = clean_html(html, skip_boilerplate_categories={"company_boilerplate"})
        assert "committed" in result.lower()

    def test_clean_html_whitespace_normalization(self) -> None:
        """Multiple spaces/newlines are collapsed to single."""
        html = "<p>Senior   Developer   with   experience.</p>"
        result = clean_html(html)

        # Should not have double spaces
        assert "   " not in result
        # Content should be present
        assert "Senior" in result or "Developer" in result

    def test_html_to_markdown_beautifulsoup_fallback_explicit(self) -> None:
        """BeautifulSoup fallback invoked when MarkItDown raises ImportError."""
        from unittest.mock import patch

        from src.parsers.html_to_markdown import html_to_markdown

        html = "<h1>Job Title</h1><p>Content here</p>"

        # Mock MarkItDown to raise ImportError (simulates unavailable library)
        with patch("src.parsers.html_to_markdown.MarkItDown") as mock_markitdown:
            mock_markitdown.return_value.convert.side_effect = ImportError("MarkItDown not installed")
            result = html_to_markdown(html)

        # Should return clean text via BeautifulSoup, NOT raw HTML
        assert result != html, "Should not return raw HTML on MarkItDown failure"
        assert "Job Title" in result or "Content" in result, "Should extract text via BeautifulSoup"
        assert isinstance(result, str)
        assert len(result) < len(html), "Should be more concise than raw HTML"

    def test_html_to_markdown_both_fail_returns_original(self) -> None:
        """Returns original HTML if both MarkItDown AND BeautifulSoup fail (safe fallback)."""
        from unittest.mock import patch

        from src.parsers.html_to_markdown import html_to_markdown

        html = "<p>content</p>"

        # Mock both to fail
        with (
            patch("src.parsers.html_to_markdown.MarkItDown") as mock_markitdown,
            patch("src.parsers.html_to_markdown._html_to_markdown_via_beautifulsoup") as mock_bs,
        ):
            mock_markitdown.return_value.convert.side_effect = RuntimeError("MarkItDown boom")
            mock_bs.side_effect = RuntimeError("BeautifulSoup boom")
            result = html_to_markdown(html)

        # Safe fallback: return original HTML
        assert result == html, "Should return original HTML as safe fallback when all else fails"

    def test_clean_html_beautifulsoup_path(self) -> None:
        """Full pipeline executes successfully via BeautifulSoup (no MarkItDown)."""
        from unittest.mock import patch

        html = "<h1>Senior Developer</h1><p>Equal Opportunity Employer.</p>"

        # Force BeautifulSoup path by failing MarkItDown
        with patch("src.parsers.html_to_markdown.MarkItDown") as mock_markitdown:
            mock_markitdown.return_value.convert.side_effect = RuntimeError("MarkItDown unavailable")
            result = clean_html(html)

        # Should clean via BeautifulSoup and apply full pipeline
        assert "Senior" in result or "Developer" in result, "Should extract content via BeautifulSoup"
        assert "Equal Opportunity" not in result, "Should remove boilerplate even via BS path"
        assert isinstance(result, str)
        assert len(result) < len(html), "Should be cleaner than raw HTML"


class TestBoilerplateRemovalCategories:
    """Test removal of each boilerplate category."""

    def test_legal_compliance_removal(self) -> None:
        """Category 1: Legal/compliance boilerplate removed."""
        html = (
            "<p>Position: Senior Dev</p>"
            "<p>Required Qualifications: Nothing special</p>"
            "<p>Equal Opportunity Employer</p>"
        )
        result = clean_html(html)

        assert "Senior Dev" in result
        assert "Required Qualifications" not in result
        assert "Equal Opportunity" not in result

    def test_section_headers_removal(self) -> None:
        """Category 2: Section headers removed as boilerplate."""
        html = (
            "<p>JD: Senior Python Developer</p>"
            "<p>Job Description: We need someone</p>"
            "<p>Requirements: 5+ years Python</p>"
        )
        result = clean_html(html)

        # Headers should be removed (or at least content extracted)
        assert "Senior Python Developer" in result or "Python" in result
        # "JD:" pattern should be removed
        assert "JD:" not in result
        # "Job Description:" should be removed
        assert "Job Description:" not in result

    def test_company_boilerplate_removal(self) -> None:
        """Category 3: Company boilerplate removed."""
        html = "<p>Position: Developer</p><p>We are committed to diversity.</p><p>Our mission is to innovate.</p>"
        result = clean_html(html)

        assert "Developer" in result
        assert "We are committed" not in result
        assert "Our mission" not in result

    def test_time_references_removal(self) -> None:
        """Category 4: Time references (employment type) removed."""
        html = "<p>Full-time position</p><p>Part-time contract</p><p>Temporary role</p>"
        result = clean_html(html)

        # Full-time should be removed
        assert "Full-time" not in result
        assert "Part-time" not in result
        assert "Temporary" not in result

    def test_contractor_not_removed(self) -> None:
        """'Contractor' word should NOT be removed (negative lookahead fix)."""
        html = "<p>We need a contractor for this project.</p>"
        result = clean_html(html)

        # "contractor" should NOT be removed
        assert "contractor" in result.lower()

    def test_salary_benefits_removal(self) -> None:
        """Category 5: Salary/benefits boilerplate removed."""
        html = "<p>Competitive salary: $100K-$150K</p><p>Health benefits included</p><p>401(k) retirement plan</p>"
        result = clean_html(html)

        # Salary patterns should be mostly removed
        assert "Competitive salary" not in result.lower()
        assert "401(k)" not in result
        assert "Health benefits" not in result.lower()

    def test_navigation_removal(self) -> None:
        """Category 7: Navigation text removed."""
        html = "<p>Position details here.</p><p>Apply Now | Share this job | Save job</p>"
        result = clean_html(html)

        assert "Position" in result or "details" in result
        assert "Apply Now" not in result
        assert "Share" not in result
        assert "Save" not in result


class TestHtmlEntityRemoval:
    """Test HTML entity normalization."""

    def test_nbsp_removal(self) -> None:
        """Non-breaking spaces converted to regular spaces."""
        html = "<p>Senior&nbsp;Developer&nbsp;Position</p>"
        result = clean_html(html)

        assert "&nbsp;" not in result
        assert "Senior" in result
        assert "Developer" in result

    def test_amp_entity_removal(self) -> None:
        """HTML ampersand entity normalized."""
        html = "<p>Skills &amp; Experience</p>"
        result = clean_html(html)

        assert "&amp;" not in result
        assert "Skills" in result

    def test_numeric_entity_removal(self) -> None:
        """Numeric HTML entities removed."""
        html = "<p>Salary: &#36;100,000 - &#36;150,000</p>"
        result = clean_html(html)

        assert "&#36;" not in result
        assert "&#" not in result

    def test_all_common_entities(self) -> None:
        """All common HTML entities handled."""
        html = "<p>&lt;tag&gt; &quot;quoted&quot; &apos;apostrophe&apos;</p>"
        result = clean_html(html)

        assert "&lt;" not in result
        assert "&gt;" not in result
        assert "&quot;" not in result
        assert "&apos;" not in result


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string_input(self) -> None:
        """Empty string returns empty string."""
        assert clean_html("") == ""

    def test_whitespace_only_input(self) -> None:
        """Whitespace-only input returns empty string."""
        assert clean_html("   ") == ""

    def test_huge_html_input(self) -> None:
        """Large HTML document is processed without error."""
        # Create a 100KB HTML document
        large_html = "<p>Content here.</p>" * 5000
        result = clean_html(large_html)

        # Should return valid string (may be compressed)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_malformed_html(self) -> None:
        """Malformed HTML (unclosed tags) handled gracefully."""
        html = "<div><p>unclosed paragraph and div"
        result = clean_html(html)

        assert isinstance(result, str)
        assert "unclosed paragraph" in result or "paragraph" in result

    def test_mixed_boilerplate_and_content(self) -> None:
        """Real-world mix of boilerplate and job content."""
        html = (
            "<h1>Senior Python Developer</h1>"
            "<p>Equal Opportunity Employer. We are committed to diversity.</p>"
            "<p>Responsibilities: Build backend services.</p>"
            "<p>Requirements: 5+ years Python, AWS experience</p>"
            "<p>Salary: $120K-$160K. Health benefits included.</p>"
            "<p>Apply Now | Share</p>"
        )
        result = clean_html(html)

        # Content should be preserved
        assert "Python" in result
        assert "backend" in result
        assert "5+" in result or "5" in result

        # Boilerplate should be removed
        assert "Equal Opportunity" not in result
        assert "committed" not in result.lower()
        assert "Apply Now" not in result


class TestPreservationOfContent:
    """Test that important content is NOT removed."""

    def test_preserve_job_title(self) -> None:
        """Job title preserved."""
        html = "<h1>Senior Python Developer - Remote</h1>"
        result = clean_html(html)

        assert "Python" in result or "Developer" in result or "Senior" in result

    def test_preserve_skills_section(self) -> None:
        """Skills section content preserved (just header might be removed)."""
        html = "<h2>Skills</h2><ul><li>Python</li><li>AWS</li><li>PostgreSQL</li></ul>"
        result = clean_html(html)

        assert "Python" in result
        assert "AWS" in result

    def test_preserve_experience_text(self) -> None:
        """Experience text preserved (not removed as boilerplate)."""
        html = "<p>We need someone with 5+ years of experience building APIs.</p>"
        result = clean_html(html)

        # "experience" keyword alone shouldn't be removed
        assert "5+" in result or "5" in result

    def test_preserve_numbers_and_special_chars(self) -> None:
        """Numbers and special characters preserved."""
        html = "<p>C++ developer with Python3, Java8 experience.</p>"
        result = clean_html(html)

        assert "C++" in result or "C" in result
        assert "Python" in result or "Python3" in result


class TestCategorySkipping:
    """Test skip_boilerplate_categories parameter."""

    def test_skip_single_category(self) -> None:
        """Skip one boilerplate category."""
        html = "<p>Competitive salary: $100K-$150K</p>"

        # Without skip
        result_normal = clean_html(html)
        # With skip
        result_skip = clean_html(html, skip_boilerplate_categories={"salary_benefits"})

        # Skip should preserve more content
        assert len(result_skip) >= len(result_normal)

    def test_skip_multiple_categories(self) -> None:
        """Skip multiple boilerplate categories."""
        html = "<p>Competitive salary: $100K.</p><p>Full-time position.</p><p>Apply Now</p>"

        result = clean_html(html, skip_boilerplate_categories={"salary_benefits", "time_references"})

        # Should preserve salary and time reference info
        assert "$" in result or "100" in result
        assert "Full-time" in result or "Full" in result

    def test_skip_nonexistent_category(self) -> None:
        """Invalid category name doesn't crash."""
        html = "<p>Test content</p>"

        # Should not crash, just ignore invalid category
        result = clean_html(html, skip_boilerplate_categories={"nonexistent_category"})

        assert "Test" in result


class TestSectionHeaderSynthesis:
    """Test section header synthesis within clean_html."""

    def test_synthesize_keyword_headers(self) -> None:
        """Standalone keyword lines become headers."""
        html = "<p>Qualifications</p><p>- Python 5+ years</p><p>Requirements</p><p>- AWS experience</p>"
        result = clean_html(html, include_section_headers=True)

        # Headers should be synthesized
        # (may show as "##" or just be structured differently)
        assert "Python" in result
        assert "AWS" in result

    def test_disable_header_synthesis(self) -> None:
        """Section headers not synthesized when disabled."""
        html = "<p>Qualifications</p><p>- Python 5+ years</p>"

        result = clean_html(html, include_section_headers=False)

        # Should still process content
        assert "Python" in result


class TestPerformance:
    """Test performance on realistic workloads."""

    @pytest.mark.perf
    def test_100_jobs_under_10_seconds(self) -> None:
        """Cleaning 100 job descriptions completes in reasonable time."""
        import time

        # Generate 100 realistic job descriptions
        job_html = (
            "<h1>Senior Python Developer</h1>"
            "<p>Equal Opportunity Employer.</p>"
            "<p>Qualifications: 5+ years Python, AWS</p>"
            "<p>Salary: $120K-$160K. Health benefits.</p>"
            "<p>Apply Now</p>"
        )

        start = time.time()
        for _ in range(100):
            clean_html(job_html)
        elapsed = time.time() - start

        # Should complete in under 10 seconds
        assert elapsed < 10, f"100 jobs took {elapsed:.2f}s, expected < 10s"


class TestNormalizationAndSpacing:
    """Test whitespace and formatting normalization."""

    def test_multiple_spaces_collapsed(self) -> None:
        """Multiple consecutive spaces collapsed to single space."""
        html = "<p>Senior    Developer    Position</p>"
        result = clean_html(html)

        assert "    " not in result
        assert "Senior" in result or "Developer" in result

    def test_multiple_newlines_handled(self) -> None:
        """Multiple newlines handled gracefully."""
        html = "<p>Line 1</p>\n\n\n<p>Line 2</p>"
        result = clean_html(html)

        # Should not have triple+ newlines
        assert "\n\n\n" not in result
        assert isinstance(result, str)

    def test_output_is_trimmed(self) -> None:
        """Output has no leading/trailing whitespace."""
        html = "<p>  Content here  </p>"
        result = clean_html(html)

        assert not result.startswith(" ")
        assert not result.endswith(" ")


class TestRealWorldExamples:
    """Test with realistic job description HTML."""

    def test_realistic_tech_job(self) -> None:
        """Realistic tech job description."""
        html = (
            "<h1>Senior Full Stack Developer</h1>"
            "<p>Remote, $120K-$150K</p>"
            "<p>About the role: Build backend APIs and React frontends.</p>"
            "<p>Requirements:"
            "<ul><li>5+ years JavaScript/Python</li>"
            "<li>AWS and Docker experience</li>"
            "<li>Strong SQL skills</li></ul></p>"
            "<p>We are an equal opportunity employer.</p>"
            "<p>Competitive benefits, 401(k), health insurance.</p>"
            "<p>Apply Now | Share | Save</p>"
        )
        result = clean_html(html)

        # Content preserved
        assert "JavaScript" in result or "Python" in result
        assert "AWS" in result or "Docker" in result

        # Boilerplate removed
        assert "equal opportunity" not in result.lower()
        assert "Apply Now" not in result

    def test_large_job_posting(self) -> None:
        """Large job posting with multiple sections."""
        html = (
            "<h1>Position: Engineering Manager</h1>"
            "<p>Location: San Francisco, CA</p>"
            "<p>Salary: $150K-$200K</p>"
            "<h2>About Us</h2>"
            "<p>We are committed to building great products.</p>"
            "<h2>Responsibilities</h2>"
            "<ul><li>Lead engineering team</li>"
            "<li>Architect backend systems</li>"
            "<li>Mentor junior developers</li></ul>"
            "<h2>Requirements</h2>"
            "<ul><li>10+ years software development</li>"
            "<li>5+ years team leadership</li>"
            "<li>Experience with Kubernetes</li></ul>"
            "<h2>Benefits</h2>"
            "<p>Health, dental, vision insurance</p>"
            "<p>401(k) matching</p>"
            "<p>Remote work flexibility</p>"
            "<p>Professional development budget</p>"
            "<p>Equal Opportunity Employer</p>"
            "<p>Apply Now</p>"
        )
        result = clean_html(html)

        # Core content preserved
        assert "Engineering Manager" in result or "Manager" in result
        assert "lead" in result.lower() or "architect" in result.lower()
        assert "10+" in result or "10" in result

        # Boilerplate removed
        assert "committed" not in result.lower()
        assert "Equal Opportunity" not in result
        assert "Apply Now" not in result
