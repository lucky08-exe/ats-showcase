"""Tests for MarkdownSpanRuler and markdown section parsing.

Tests cover:
- Header detection (H1, H2, H3, bold markers)
- Title extraction
- Content preservation
- Metadata calculation (word_count, line_count, has_list)
- Export formats (dict, JSON)
- Edge cases (empty sections, unicode, special characters)
- Preamble handling (text before first header)
"""

import json
import sys
from pathlib import Path

import pytest
import spacy

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.poc.tweak.multi_line_paragraph import (
    MarkdownSection,
    MarkdownSpanRuler,
    count_words,
    detect_has_list,
    extract_title,
    get_header_level,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def nlp():
    """Load spaCy model for testing."""
    try:
        return spacy.load("en_core_web_md")
    except OSError:
        return spacy.load("en_core_web_sm")


@pytest.fixture
def ruler(nlp):
    """Create MarkdownSpanRuler instance."""
    return MarkdownSpanRuler(nlp)


# ============================================================================
# Phase 1 Tests: Helper Functions
# ============================================================================


class TestExtractTitle:
    """Test title extraction from header lines."""

    def test_extract_h1_title(self):
        """Extract title from H1 header."""
        title = extract_title("# Introduction", 1)
        assert title == "Introduction"

    def test_extract_h2_title(self):
        """Extract title from H2 header."""
        title = extract_title("## Requirements", 2)
        assert title == "Requirements"

    def test_extract_h3_title(self):
        """Extract title from H3 header."""
        title = extract_title("### Details", 3)
        assert title == "Details"

    def test_extract_bold_title(self):
        """Extract title from bold marker."""
        title = extract_title("**Qualifications**", -1)
        assert title == "Qualifications"

    def test_extract_header_bold_pattern(self):
        """Extract title from ## ** pattern."""
        title = extract_title("## **Experience**", 2)
        assert title == "Experience"

    def test_extract_title_with_extra_whitespace(self):
        """Title extraction handles extra whitespace."""
        title = extract_title("##   Spacing   ", 2)
        assert title == "Spacing"

    def test_extract_title_empty_line(self):
        """Returns None for empty header."""
        title = extract_title("##", 2)
        assert title is None

    def test_extract_title_no_marker_found(self):
        """Returns None when markers removed result in empty string."""
        title = extract_title("**  **", -1)
        assert title is None


class TestGetHeaderLevel:
    """Test header level detection."""

    def test_detect_h1(self):
        """Detect H1 header."""
        assert get_header_level("# Title") == 1

    def test_detect_h2(self):
        """Detect H2 header."""
        assert get_header_level("## Title") == 2

    def test_detect_h3(self):
        """Detect H3 header."""
        assert get_header_level("### Title") == 3

    def test_detect_bold(self):
        """Detect bold marker."""
        assert get_header_level("**Title**") == -1

    def test_detect_header_bold_pattern(self):
        """Detect ## ** pattern."""
        assert get_header_level("## **Title**") == 2

    def test_detect_no_header(self):
        """Return -2 for regular text."""
        assert get_header_level("Regular text here") == -2

    def test_detect_with_whitespace(self):
        """Header detection works with leading/trailing whitespace."""
        assert get_header_level("  ## Title  ") == 2


class TestCountWords:
    """Test word counting."""

    def test_count_simple_words(self):
        """Count words in simple text."""
        assert count_words("hello world") == 2

    def test_count_with_extra_whitespace(self):
        """Word count handles extra whitespace."""
        assert count_words("  hello   world  ") == 2

    def test_count_empty_string(self):
        """Empty string returns 0."""
        assert count_words("") == 0

    def test_count_multiline(self):
        """Count words across multiple lines."""
        text = "line one\nline two\nline three"
        assert count_words(text) == 6

    def test_count_with_punctuation(self):
        """Punctuation attached to words counts as single word."""
        assert count_words("hello, world!") == 2


class TestDetectHasList:
    """Test list detection."""

    def test_detect_asterisk_list(self):
        """Detect * bullet points."""
        assert detect_has_list("* Item 1\n* Item 2") is True

    def test_detect_dash_list(self):
        """Detect - bullet points."""
        assert detect_has_list("- Item 1\n- Item 2") is True

    def test_detect_dot_list(self):
        """Detect • bullet points."""
        assert detect_has_list("• Item 1\n• Item 2") is True

    def test_detect_plus_list(self):
        """Detect + bullet points."""
        assert detect_has_list("+ Item 1\n+ Item 2") is True

    def test_no_list_regular_text(self):
        """No list in regular text."""
        assert detect_has_list("Regular text\nMore text") is False

    def test_no_list_with_asterisk_in_middle(self):
        """Asterisk in middle of line is not a list marker."""
        assert detect_has_list("Text with * in middle") is False

    def test_detect_mixed_content(self):
        """Detect list in mixed content."""
        content = "Some text\n* Item 1\n* Item 2\nMore text"
        assert detect_has_list(content) is True

    def test_empty_content_no_list(self):
        """Empty content has no list."""
        assert detect_has_list("") is False


# ============================================================================
# Phase 2 Tests: MarkdownSpanRuler Core
# ============================================================================


class TestMarkdownSpanRulerInit:
    """Test MarkdownSpanRuler initialization."""

    def test_init_creates_instance(self, ruler):
        """Initialization creates ruler instance."""
        assert ruler is not None
        assert ruler.nlp is not None

    def test_init_registers_doc_extension(self, ruler):
        """Initialization registers Doc extension."""
        doc = ruler.nlp("test text")
        assert hasattr(doc._, "sections")


class TestMarkdownSpanRulerParse:
    """Test markdown parsing."""

    def test_parse_single_h1_section(self, ruler):
        """Parse single H1 header with content."""
        text = "# Introduction\n\nContent here"
        sections = ruler.parse(text)
        assert len(sections) == 1
        assert sections[0].title == "Introduction"
        assert "Content here" in sections[0].content

    def test_parse_multiple_sections(self, ruler):
        """Parse multiple sections with different headers."""
        text = "# Title 1\n\nContent 1\n\n## Title 2\n\nContent 2"
        sections = ruler.parse(text)
        assert len(sections) == 2
        assert sections[0].title == "Title 1"
        assert sections[1].title == "Title 2"
        assert sections[0].level == 1
        assert sections[1].level == 2

    def test_parse_h1_h2_h3_hierarchy(self, ruler):
        """Parse headers at different levels."""
        text = "# H1\n\n## H2\n\n### H3"
        sections = ruler.parse(text)
        assert len(sections) == 3
        assert sections[0].level == 1
        assert sections[1].level == 2
        assert sections[2].level == 3

    def test_parse_bold_marker(self, ruler):
        """Parse bold marker as section."""
        text = "**Bold Title**\n\nContent here"
        sections = ruler.parse(text)
        assert len(sections) == 1
        assert sections[0].title == "Bold Title"
        assert sections[0].level == -1

    def test_parse_no_headers(self, ruler):
        """Parse text with no headers creates single section."""
        text = "Just plain text\nNo headers here"
        sections = ruler.parse(text)
        # Text with no headers should be treated as content-only section
        # depending on implementation
        assert len(sections) >= 1

    def test_parse_preserves_content_exactly(self, ruler):
        """Content is preserved exactly (no transformation)."""
        text = "## Section\n\n* Item 1  \n* Item 2\n\nParagraph."
        sections = ruler.parse(text)
        # Content should be stripped at section level but preserve internal formatting
        assert "* Item 1" in sections[0].content
        assert "* Item 2" in sections[0].content

    def test_parse_empty_string(self, ruler):
        """Parse empty string returns no sections."""
        sections = ruler.parse("")
        assert len(sections) == 0

    def test_parse_stores_doc_sections(self, ruler):
        """Parse stores sections in nlp doc."""
        text = "# Title\n\nContent"
        sections = ruler.parse(text)
        assert ruler.doc_sections == sections


class TestMarkdownSectionMetadata:
    """Test metadata extraction in sections."""

    def test_section_word_count(self, ruler):
        """Section metadata includes word count."""
        text = "# Title\n\none two three four five"
        sections = ruler.parse(text)
        assert sections[0].word_count == 7  # Title + 5 words

    def test_section_line_count(self, ruler):
        """Section metadata includes line count."""
        text = "# Title\n\nLine 1\nLine 2\nLine 3"
        sections = ruler.parse(text)
        # Non-empty lines
        assert sections[0].line_count >= 3

    def test_section_has_list_true(self, ruler):
        """Section detects list presence."""
        text = "## Section\n\n* Item 1\n* Item 2"
        sections = ruler.parse(text)
        assert sections[0].has_list is True

    def test_section_has_list_false(self, ruler):
        """Section detects no list."""
        text = "## Section\n\nRegular text"
        sections = ruler.parse(text)
        assert sections[0].has_list is False

    def test_section_boundaries(self, ruler):
        """Section has correct start and end line indices."""
        text = "# H1\n\nContent\n\n## H2\n\nMore content"
        sections = ruler.parse(text)
        assert sections[0].start_line == 0
        assert sections[1].start_line > sections[0].end_line


# ============================================================================
# Phase 3 Tests: Export Methods
# ============================================================================


class TestMarkdownSpanRulerExport:
    """Test export functionality."""

    def test_to_dict_basic(self, ruler):
        """Export to dict contains sections key."""
        text = "# Title\n\nContent"
        sections = ruler.parse(text)
        result = ruler.to_dict(sections)
        assert "sections" in result
        assert isinstance(result["sections"], list)

    def test_to_dict_section_structure(self, ruler):
        """Exported dict has all section fields."""
        text = "# Title\n\nContent"
        sections = ruler.parse(text)
        result = ruler.to_dict(sections)
        section_dict = result["sections"][0]
        assert "title" in section_dict
        assert "content" in section_dict
        assert "level" in section_dict
        assert "start_line" in section_dict
        assert "end_line" in section_dict
        assert "word_count" in section_dict
        assert "line_count" in section_dict
        assert "has_list" in section_dict
        assert "metadata" in section_dict

    def test_to_dict_uses_doc_sections_by_default(self, ruler):
        """to_dict uses stored sections if none provided."""
        text = "# Title\n\nContent"
        ruler.parse(text)
        result = ruler.to_dict()
        assert len(result["sections"]) == 1

    def test_to_json_is_valid_json(self, ruler):
        """Export to JSON is valid JSON string."""
        text = "# Title\n\nContent"
        sections = ruler.parse(text)
        json_str = ruler.to_json(sections)
        # Should not raise
        parsed = json.loads(json_str)
        assert "sections" in parsed

    def test_to_json_with_indent(self, ruler):
        """JSON export respects indent parameter."""
        text = "# Title\n\nContent"
        sections = ruler.parse(text)
        json_str = ruler.to_json(sections, indent=4)
        # With indent=4, should have readable formatting
        assert "\n    " in json_str or len(json_str.split("\n")) > 1

    def test_to_json_preserves_unicode(self, ruler):
        """JSON export preserves unicode characters."""
        text = "## Français\n\n• Élément 1"
        sections = ruler.parse(text)
        json_str = ruler.to_json(sections)
        parsed = json.loads(json_str)
        assert "Français" in json_str or "Fran" in str(parsed)

    def test_to_json_uses_doc_sections_by_default(self, ruler):
        """to_json uses stored sections if none provided."""
        text = "# Title\n\nContent"
        ruler.parse(text)
        json_str = ruler.to_json()
        parsed = json.loads(json_str)
        assert len(parsed["sections"]) == 1


# ============================================================================
# Phase 3 Tests: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_sections_between_headers(self, ruler):
        """Adjacent headers with no content between."""
        text = "# Title 1\n## Title 2\n### Title 3"
        sections = ruler.parse(text)
        # Should create sections even with minimal content
        assert len(sections) >= 2

    def test_trailing_content_after_last_header(self, ruler):
        """Content after last header is captured."""
        text = "# Title\n\nContent line 1\nContent line 2"
        sections = ruler.parse(text)
        assert len(sections) == 1
        assert "Content line 2" in sections[0].content

    def test_special_characters_in_content(self, ruler):
        """Special characters preserved in content."""
        text = "# Title\n\n@#$%^&*() test [brackets]"
        sections = ruler.parse(text)
        assert "@#$%" in sections[0].content or "test" in sections[0].content

    def test_unicode_in_headers(self, ruler):
        """Unicode characters in headers."""
        text = "## 中文标题\n\nContent"
        sections = ruler.parse(text)
        # Should parse without error
        assert len(sections) == 1

    def test_unicode_in_content(self, ruler):
        """Unicode characters in content."""
        text = "# Title\n\n日本語テキスト"
        sections = ruler.parse(text)
        assert len(sections) == 1

    def test_large_document(self, ruler):
        """Parse large document efficiently."""
        # Create a large document
        lines = ["# Section " + str(i) + "\n\nContent " + str(i) for i in range(100)]
        text = "\n\n".join(lines)
        sections = ruler.parse(text)
        # Should have parsed all sections
        assert len(sections) > 50

    def test_mixed_header_styles(self, ruler):
        """Mix of different header styles."""
        text = "# H1\n\n## H2\n\n**Bold**\n\n### H3"
        sections = ruler.parse(text)
        levels = [s.level for s in sections]
        assert 1 in levels
        assert 2 in levels
        assert -1 in levels
        assert 3 in levels

    def test_code_block_preservation(self, ruler):
        """Code blocks are preserved (no special handling)."""
        text = "# Code\n\n```python\nprint('hello')\n```"
        sections = ruler.parse(text)
        assert "print" in sections[0].content

    def test_multiline_list_items(self, ruler):
        """Multi-line list items detected as list."""
        text = "## Items\n\n* First item\n  continued here\n* Second item"
        sections = ruler.parse(text)
        assert sections[0].has_list is True


# ============================================================================
# Phase 4 Tests: Preamble Handling (Issue #373)
# ============================================================================


class TestPreambleHandling:
    """Test preamble text before first header."""

    def test_preamble_before_first_heading(self, ruler):
        """Preamble text before first heading is emitted as a section."""
        text = "This is preamble text.\nMore preamble.\n\n# Heading\n\nHeading content"
        sections = ruler.parse(text)
        assert len(sections) == 2
        # First section is preamble (title=None, level=-2)
        assert sections[0].title is None
        assert sections[0].level == -2
        assert sections[0].start_line == 0
        assert sections[0].end_line == 2
        assert "This is preamble text" in sections[0].content
        # Second section is the heading
        assert sections[1].title == "Heading"
        assert sections[1].level == 1

    def test_preamble_with_bullets(self, ruler):
        """Preamble with bullet points is marked as has_list=True."""
        text = "* Item 1\n* Item 2\n\n## Section\n\nContent"
        sections = ruler.parse(text)
        assert len(sections) == 2
        assert sections[0].title is None
        assert sections[0].level == -2
        assert sections[0].has_list is True
        assert "Item 1" in sections[0].content

    def test_whitespace_only_preamble_dropped(self, ruler):
        """Whitespace-only preamble is dropped (not emitted as section)."""
        text = "\n\n# Heading\n\nContent"
        sections = ruler.parse(text)
        assert len(sections) == 1
        assert sections[0].title == "Heading"

    def test_header_at_line_zero_no_preamble(self, ruler):
        """When header is at line 0, no preamble section."""
        text = "# Title\n\nContent"
        sections = ruler.parse(text)
        assert len(sections) == 1
        assert sections[0].title == "Title"
        assert sections[0].start_line == 0

    def test_preamble_with_multiple_headers(self, ruler):
        """Preamble before multiple headers."""
        text = "Preamble text\n\n# H1\n\nContent 1\n\n## H2\n\nContent 2"
        sections = ruler.parse(text)
        assert len(sections) == 3
        assert sections[0].title is None
        assert sections[0].level == -2
        assert sections[1].title == "H1"
        assert sections[2].title == "H2"

    def test_preamble_content_boundaries(self, ruler):
        """Preamble section has correct start and end line indices."""
        text = "Preamble line 1\nPreamble line 2\n\n# Heading"
        sections = ruler.parse(text)
        preamble = sections[0]
        assert preamble.start_line == 0
        assert preamble.end_line == 2  # Line with empty string before heading

    def test_preamble_word_count(self, ruler):
        """Preamble word count is calculated correctly."""
        text = "word one word two word three\n\n# Title\n\nContent"
        sections = ruler.parse(text)
        assert sections[0].word_count == 6
        assert sections[0].title is None

    def test_preamble_line_count(self, ruler):
        """Preamble line count counts non-empty lines."""
        text = "Line 1\n\nLine 3\n\n# Title\n\nContent"
        sections = ruler.parse(text)
        preamble = sections[0]
        assert preamble.line_count == 2

    def test_single_dash_preamble(self, ruler):
        """Leading --- becomes a preamble section."""
        text = "---\n\n# Title\n\nContent"
        sections = ruler.parse(text)
        assert len(sections) == 2
        assert sections[0].title is None
        assert sections[0].level == -2
        assert "---" in sections[0].content

    def test_preamble_multiple_headers_preserves_later_sections(self, ruler):
        """Preamble insertion doesn't affect later sections."""
        text = "Preamble\n\n# H1\n\nC1\n\n## H2\n\nC2\n\n### H3\n\nC3"
        sections = ruler.parse(text)
        assert len(sections) == 4
        # Check all headers are intact
        assert sections[1].title == "H1"
        assert sections[2].title == "H2"
        assert sections[3].title == "H3"
        # Check header levels and boundaries
        assert sections[1].level == 1
        assert sections[2].level == 2
        assert sections[3].level == 3

    def test_preamble_export_to_dict(self, ruler):
        """Preamble section exports correctly to dict."""
        text = "Preamble content\n\n# Title\n\nBody"
        sections = ruler.parse(text)
        result = ruler.to_dict(sections)
        assert len(result["sections"]) == 2
        assert result["sections"][0]["title"] is None
        assert result["sections"][0]["level"] == -2

    def test_preamble_export_to_json(self, ruler):
        """Preamble section exports correctly to JSON."""
        text = "Preamble\n\n# Title\n\nContent"
        sections = ruler.parse(text)
        json_str = ruler.to_json(sections)
        parsed = json.loads(json_str)
        assert len(parsed["sections"]) == 2
        assert parsed["sections"][0]["title"] is None
        assert parsed["sections"][0]["level"] == -2


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests with realistic markdown."""

    def test_job_description_parsing(self, ruler):
        """Parse realistic job description markdown."""
        text = """# Senior Python Developer

## About Us

We build tools.

## Qualifications

* 5+ years Python
* Experience with Django
* Strong communication

## Compensation

- Competitive salary
- Health benefits

**Next Steps**

Apply now!"""
        sections = ruler.parse(text)
        assert len(sections) > 3
        titles = [s.title for s in sections if s.title]
        assert "Senior Python Developer" in titles
        assert any("Qualifications" in str(t) for t in titles if t)

    def test_round_trip_export_import(self, ruler):
        """Parse -> export -> reimport preserves structure."""
        text = "# Title\n\nContent line 1\nContent line 2"
        sections = ruler.parse(text)
        json_str = ruler.to_json(sections)
        data = json.loads(json_str)
        # Should be able to reconstruct
        assert len(data["sections"]) == 1
        assert data["sections"][0]["title"] == "Title"
        assert data["sections"][0]["word_count"] >= 5


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Performance and efficiency tests."""

    def test_parse_1000_line_document(self, ruler):
        """Parse 1000-line document efficiently."""
        # Create document with 200 sections
        lines = []
        for i in range(200):
            lines.append(f"## Section {i}\n\nContent for section {i}")
        text = "\n\n".join(lines)

        sections = ruler.parse(text)
        # Should parse successfully
        assert len(sections) > 100

    def test_metadata_calculation_efficiency(self, ruler):
        """Metadata calculation is efficient."""
        text = "# Title\n\n" + "\n".join(["Word"] * 10000)
        sections = ruler.parse(text)
        # Should complete without hanging
        assert sections[0].word_count > 100
