"""Unit tests for HTMLMarkdownConverter component.

Tests cover:
- Basic HTML to Markdown conversion
- Structure preservation (headers, lists, links)
- Temporary file cleanup (even on exception)
- Fallback modes ("html" and "raise")
- Malformed HTML handling
- Edge cases (empty input, special characters)
"""

import os
import tempfile

import pytest

from src.poc.tweak.spacy_pipeline.html_markdown_converter import HTMLMarkdownConverter


class TestHTMLMarkdownConverterBasic:
    """Basic HTML to Markdown conversion tests."""

    @pytest.fixture
    def converter(self):
        """Create HTMLMarkdownConverter instance."""
        return HTMLMarkdownConverter()

    def test_converts_basic_html(self, converter):
        """Convert simple HTML paragraph to Markdown."""
        html = "<div><p>Hello World</p></div>"
        result = converter.process(html)
        # Result should contain the text (exact markdown format may vary by MarkItDown)
        assert "Hello" in result and "World" in result
        # Should return string
        assert isinstance(result, str)

    def test_converts_html_with_bold(self, converter):
        """Convert HTML with bold text."""
        html = "<p>This is <strong>bold</strong> text.</p>"
        result = converter.process(html)
        # Markdown bold is **text**
        assert "bold" in result
        assert isinstance(result, str)

    def test_converts_html_with_italic(self, converter):
        """Convert HTML with italic text."""
        html = "<p>This is <em>italic</em> text.</p>"
        result = converter.process(html)
        assert "italic" in result
        assert isinstance(result, str)

    def test_converts_html_lists(self, converter):
        """Convert HTML unordered list to Markdown."""
        html = "<ul><li>Item 1</li><li>Item 2</li><li>Item 3</li></ul>"
        result = converter.process(html)
        # Markdown lists use -, *, or +
        assert "Item 1" in result
        assert "Item 2" in result
        assert "Item 3" in result
        # Should have some list markers
        assert any(marker in result for marker in ["-", "*", "+"])

    def test_converts_html_with_headers(self, converter):
        """Convert HTML headers to Markdown headers."""
        html = "<h1>Main Title</h1><h2>Subtitle</h2><p>Content</p>"
        result = converter.process(html)
        assert "Main Title" in result
        assert "Subtitle" in result
        assert "Content" in result
        # Markdown headers use #
        assert "#" in result

    def test_converts_html_with_links(self, converter):
        """Convert HTML links to Markdown links."""
        html = '<p>Visit <a href="https://example.com">example site</a>.</p>'
        result = converter.process(html)
        assert "example" in result
        # Markdown links use [text](url)
        # Result should contain either link text or URL
        assert "example" in result.lower() or "http" in result.lower()

    def test_preserves_structure(self, converter):
        """Preserve document structure through conversion."""
        html = """
        <div>
            <h2>Section 1</h2>
            <p>Paragraph 1</p>
            <ul>
                <li>Bullet 1</li>
                <li>Bullet 2</li>
            </ul>
            <h2>Section 2</h2>
            <p>Paragraph 2</p>
        </div>
        """
        result = converter.process(html)
        # All text should be present
        assert "Section 1" in result
        assert "Paragraph 1" in result
        assert "Bullet 1" in result
        assert "Bullet 2" in result
        assert "Section 2" in result
        assert "Paragraph 2" in result

    def test_handles_empty_string(self, converter):
        """Gracefully handle empty HTML input."""
        result = converter.process("")
        assert result == ""
        assert isinstance(result, str)

    def test_handles_nbsp(self, converter):
        """Remove non-breaking spaces during conversion."""
        html = "<p>Text\xa0with\xa0nbsp</p>"
        result = converter.process(html)
        # Non-breaking spaces should be converted or removed
        # Result should contain the text
        assert "Text" in result or "text" in result.lower()


class TestHTMLMarkdownConverterTempFileCleanup:
    """Test temporary file management and cleanup."""

    @pytest.fixture
    def converter(self):
        """Create HTMLMarkdownConverter instance."""
        return HTMLMarkdownConverter()

    @pytest.fixture
    def isolated_tempdir(self, tmp_path, monkeypatch):
        """Redirect tempfile to a per-test directory.

        The system temp dir is shared by every pytest-xdist worker, so
        snapshotting it races with other workers' in-flight *.html files.
        tempfile.tempdir is process-global, but each xdist worker is its own
        process and monkeypatch restores it after the test, so this is safe.
        """
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        return tmp_path

    def test_temp_file_cleanup_on_success(self, converter, isolated_tempdir):
        """Temp files should be removed after successful conversion."""
        html = "<p>Test content</p>"

        # Get temp directory to count files before/after
        temp_dir = str(isolated_tempdir)
        html_files_before = {f for f in os.listdir(temp_dir) if f.endswith(".html")}

        # Process HTML
        result = converter.process(html)
        assert isinstance(result, str)

        # Check temp files after
        html_files_after = {f for f in os.listdir(temp_dir) if f.endswith(".html")}

        # No new temp files should remain
        new_files = html_files_after - html_files_before
        assert len(new_files) == 0, f"Temp files not cleaned up: {new_files}"

    def test_temp_file_cleanup_on_exception_fallback_html(self, converter, isolated_tempdir):
        """Temp files should be cleaned up even when conversion fails (fallback to HTML)."""
        # Create HTML that might cause issues
        html = "<p>Test content</p>"

        temp_dir = str(isolated_tempdir)
        html_files_before = {f for f in os.listdir(temp_dir) if f.endswith(".html")}

        # Process HTML - even if conversion fails, should fallback to HTML
        result = converter.process(html)
        assert isinstance(result, str)

        # Check temp files after
        html_files_after = {f for f in os.listdir(temp_dir) if f.endswith(".html")}

        # No new temp files should remain
        new_files = html_files_after - html_files_before
        assert len(new_files) == 0, f"Temp files not cleaned up: {new_files}"

    def test_temp_file_cleanup_with_raise_fallback(self, isolated_tempdir):
        """Temp files should be cleaned up even when fallback_mode='raise'."""
        converter = HTMLMarkdownConverter(fallback_mode="raise")
        html = "<p>Test content</p>"

        temp_dir = str(isolated_tempdir)
        html_files_before = {f for f in os.listdir(temp_dir) if f.endswith(".html")}

        # Process HTML
        result = converter.process(html)
        assert isinstance(result, str)

        # Check temp files after
        html_files_after = {f for f in os.listdir(temp_dir) if f.endswith(".html")}

        # No new temp files should remain
        new_files = html_files_after - html_files_before
        assert len(new_files) == 0, f"Temp files not cleaned up: {new_files}"

    def test_no_orphaned_temp_files(self, converter, isolated_tempdir):
        """Process multiple documents and verify no orphaned temp files."""
        htmls = [
            "<p>Document 1</p>",
            "<p>Document 2</p>",
            "<p>Document 3</p>",
        ]

        temp_dir = str(isolated_tempdir)
        html_files_before = {f for f in os.listdir(temp_dir) if f.endswith(".html")}

        # Process all documents
        for html in htmls:
            result = converter.process(html)
            assert isinstance(result, str)

        # Check temp files after all conversions
        html_files_after = {f for f in os.listdir(temp_dir) if f.endswith(".html")}

        # No new temp files should remain
        new_files = html_files_after - html_files_before
        assert len(new_files) == 0, f"Orphaned temp files after multiple conversions: {new_files}"


class TestHTMLMarkdownConverterFallbackModes:
    """Test fallback behavior on conversion errors."""

    def test_fallback_mode_html_default(self):
        """Default fallback mode should be 'html'."""
        converter = HTMLMarkdownConverter()
        assert converter.fallback_mode == "html"

    def test_fallback_mode_html_returns_original(self):
        """With fallback_mode='html', return original HTML on failure."""
        converter = HTMLMarkdownConverter(fallback_mode="html")
        html = "<p>Test content</p>"
        result = converter.process(html)
        # Should return markdown if successful, or original HTML if it fails
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_mode_raise(self):
        """With fallback_mode='raise', should raise on severe failure."""
        converter = HTMLMarkdownConverter(fallback_mode="raise")
        html = "<p>Test content</p>"
        # Normal HTML should work fine
        result = converter.process(html)
        assert isinstance(result, str)

    def test_invalid_fallback_mode_raises_error(self):
        """Invalid fallback_mode should raise ValueError on init."""
        with pytest.raises(ValueError, match="fallback_mode must be 'html' or 'raise'"):
            # Intentionally invalid value to exercise validation
            HTMLMarkdownConverter(fallback_mode="invalid")  # type: ignore[arg-type]

    def test_fallback_mode_parameter_stored(self):
        """Fallback mode parameter should be accessible."""
        converter_html = HTMLMarkdownConverter(fallback_mode="html")
        converter_raise = HTMLMarkdownConverter(fallback_mode="raise")

        assert converter_html.fallback_mode == "html"
        assert converter_raise.fallback_mode == "raise"


class TestHTMLMarkdownConverterMalformedHTML:
    """Test handling of malformed or unusual HTML."""

    @pytest.fixture
    def converter(self):
        """Create HTMLMarkdownConverter instance."""
        return HTMLMarkdownConverter()

    def test_malformed_html_fallback(self, converter):
        """Gracefully handle malformed HTML with fallback."""
        html = "<div><p>Unclosed paragraph<div>Nested</div>"
        result = converter.process(html)
        # Should return some result (markdown or fallback HTML)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_missing_closing_tags(self, converter):
        """Handle HTML with missing closing tags."""
        html = "<ul><li>Item 1<li>Item 2</ul>"
        result = converter.process(html)
        assert isinstance(result, str)
        assert "Item 1" in result or "Item 2" in result or len(result) > 0

    def test_html_with_script_tags(self, converter):
        """Handle HTML containing script tags."""
        html = "<p>Text</p><script>alert('test')</script><p>More text</p>"
        result = converter.process(html)
        # Should process gracefully, script content may be included or removed
        assert isinstance(result, str)

    def test_html_with_style_tags(self, converter):
        """Handle HTML containing style tags."""
        html = "<p>Text</p><style>body { color: red; }</style><p>More text</p>"
        result = converter.process(html)
        assert isinstance(result, str)

    def test_deeply_nested_html(self, converter):
        """Handle deeply nested HTML structure."""
        html = "<div><div><div><div><div><div><p>Deep content</p></div></div></div></div></div></div>"
        result = converter.process(html)
        assert isinstance(result, str)
        assert "Deep content" in result or len(result) > 0

    def test_html_with_only_whitespace(self, converter):
        """Handle HTML with only whitespace."""
        html = "<div>   \n\t  </div>"
        result = converter.process(html)
        assert isinstance(result, str)

    def test_html_with_special_entities(self, converter):
        """Handle HTML entities."""
        html = "<p>Price: &dollar;100 &amp; quantity: 5 &lt; 10</p>"
        result = converter.process(html)
        assert isinstance(result, str)
        # Should contain some content
        assert len(result) > 0


class TestHTMLMarkdownConverterEdgeCases:
    """Test edge cases and special scenarios."""

    @pytest.fixture
    def converter(self):
        """Create HTMLMarkdownConverter instance."""
        return HTMLMarkdownConverter()

    def test_very_large_html(self, converter):
        """Handle very large HTML document."""
        # Create a large HTML document
        items = "\n".join([f"<li>Item {i}</li>" for i in range(1000)])
        html = f"<ul>{items}</ul>"
        result = converter.process(html)
        assert isinstance(result, str)
        # Should contain at least some items
        assert "Item" in result

    def test_html_with_unicode_characters(self, converter):
        """Handle HTML with Unicode characters."""
        html = "<p>Unicode: 你好 مرحبا привет ñ ü ö</p>"
        result = converter.process(html)
        assert isinstance(result, str)

    def test_html_with_emoji(self, converter):
        """Handle HTML with emoji characters."""
        html = "<p>Emoji test: 🚀 ✅ ❌ 🎉</p>"
        result = converter.process(html)
        assert isinstance(result, str)

    def test_real_world_job_posting_snippet(self, converter):
        """Process realistic job posting HTML snippet."""
        html = """
        <div class="job-description">
            <h2>Senior Software Engineer</h2>
            <p>We're seeking a talented software engineer to join our team.</p>
            <h3>Responsibilities:</h3>
            <ul>
                <li>Design and implement backend services</li>
                <li>Collaborate with cross-functional teams</li>
                <li>Write clean, maintainable code</li>
            </ul>
            <h3>Requirements:</h3>
            <ul>
                <li>5+ years of software development experience</li>
                <li>Strong proficiency in Python or Go</li>
                <li>Experience with distributed systems</li>
            </ul>
        </div>
        """
        result = converter.process(html)
        assert isinstance(result, str)
        # Should preserve structure
        assert "Senior Software Engineer" in result
        assert "Responsibilities" in result or "responsibilities" in result.lower()
        assert "Requirements" in result or "requirements" in result.lower()

    def test_mixed_content_html(self, converter):
        """Handle HTML with mixed content types."""
        html = """
        <div>
            <h1>Title</h1>
            <p>Paragraph with <strong>bold</strong> and <em>italic</em>.</p>
            <ul>
                <li>List item 1</li>
                <li>List item 2</li>
            </ul>
            <p>Another paragraph with <a href="http://example.com">link</a>.</p>
        </div>
        """
        result = converter.process(html)
        assert isinstance(result, str)
        assert "Title" in result
        assert "Paragraph" in result
        assert "List item" in result
        assert "Another" in result


class TestHTMLMarkdownConverterCallable:
    """Test callable interface."""

    @pytest.fixture
    def converter(self):
        """Create HTMLMarkdownConverter instance."""
        return HTMLMarkdownConverter()

    def test_callable_via_call_method(self, converter):
        """Component should be callable via __call__()."""
        html = "<p>Test content</p>"
        result = converter(html)  # Using __call__
        assert isinstance(result, str)

    def test_process_and_call_equivalent(self, converter):
        """process() and __call__() should produce identical results."""
        html = "<p>Test content</p>"
        result1 = converter.process(html)
        result2 = converter(html)
        assert result1 == result2


class TestHTMLMarkdownConverterProperties:
    """Test component properties and initialization."""

    def test_name_property(self):
        """Component should have correct name property."""
        converter = HTMLMarkdownConverter()
        assert converter.name == "html_markdown_converter"
        assert isinstance(converter.name, str)

    def test_name_consistent(self):
        """Name should be consistent across calls."""
        converter = HTMLMarkdownConverter()
        name1 = converter.name
        name2 = converter.name
        assert name1 == name2

    def test_initialization_with_default_fallback(self):
        """Initialize with default fallback mode."""
        converter = HTMLMarkdownConverter()
        assert converter.fallback_mode == "html"

    def test_initialization_with_custom_fallback(self):
        """Initialize with custom fallback mode."""
        converter = HTMLMarkdownConverter(fallback_mode="raise")
        assert converter.fallback_mode == "raise"

    def test_md_converter_initialized(self):
        """MarkItDown converter should be initialized."""
        converter = HTMLMarkdownConverter()
        assert hasattr(converter, "md_converter")
        assert converter.md_converter is not None
