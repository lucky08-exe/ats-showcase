"""Integration tests for spaCy pipeline component factory registration.

Tests verify:
1. Components can be created via nlp.create_pipe()
2. Component names are correctly registered
3. Components can be chained together (HTML → preprocess → convert → polish)
4. Component properties are accessible
"""

import pytest

# Import to trigger factory registration
from src.poc.tweak.spacy_pipeline import (
    HTMLMarkdownConverter,
    HTMLPreprocessor,
    MarkdownPolisher,
    registry,  # noqa: F401
)


class TestSpaCyFactoryRegistration:
    """Test spaCy factory registration of pipeline components."""

    @pytest.fixture(scope="session")
    def spacy_module(self):
        """Import spacy (skip test if not available)."""
        try:
            import spacy

            return spacy
        except ImportError:
            pytest.skip("spaCy not installed")

    @pytest.fixture(scope="session")
    def nlp(self, spacy_module):
        """Load spaCy model (skip if not available)."""
        try:
            # Try to load model; skip if not installed
            nlp = spacy_module.load("en_core_web_md")
            return nlp
        except OSError:
            pytest.skip("en_core_web_md model not installed")

    def test_create_html_preprocessor_via_factory(self, nlp):
        """Verify HTMLPreprocessor can be created via nlp.create_pipe()."""
        preprocessor = nlp.create_pipe("html_preprocessor")
        assert isinstance(preprocessor, HTMLPreprocessor)
        assert preprocessor.name == "html_preprocessor"

    def test_create_html_markdown_converter_via_factory(self, nlp):
        """Verify HTMLMarkdownConverter can be created via nlp.create_pipe()."""
        converter = nlp.create_pipe("html_markdown_converter")
        assert isinstance(converter, HTMLMarkdownConverter)
        assert converter.name == "html_markdown_converter"

    def test_create_markdown_polisher_via_factory(self, nlp):
        """Verify MarkdownPolisher can be created via nlp.create_pipe()."""
        polisher = nlp.create_pipe("markdown_polisher")
        assert isinstance(polisher, MarkdownPolisher)
        assert polisher.name == "markdown_polisher"


class TestComponentNamesRegistered:
    """Test that component names are correctly registered."""

    @pytest.fixture(scope="session")
    def spacy_module(self):
        """Import spacy (skip test if not available)."""
        try:
            import spacy

            return spacy
        except ImportError:
            pytest.skip("spaCy not installed")

    @pytest.fixture(scope="session")
    def nlp(self, spacy_module):
        """Load spaCy model (skip if not available)."""
        try:
            nlp = spacy_module.load("en_core_web_md")
            return nlp
        except OSError:
            pytest.skip("en_core_web_md model not installed")

    def test_html_preprocessor_name(self, nlp):
        """Verify html_preprocessor component name."""
        preprocessor = nlp.create_pipe("html_preprocessor")
        assert preprocessor.name == "html_preprocessor"
        assert isinstance(preprocessor.name, str)

    def test_html_markdown_converter_name(self, nlp):
        """Verify html_markdown_converter component name."""
        converter = nlp.create_pipe("html_markdown_converter")
        assert converter.name == "html_markdown_converter"
        assert isinstance(converter.name, str)

    def test_markdown_polisher_name(self, nlp):
        """Verify markdown_polisher component name."""
        polisher = nlp.create_pipe("markdown_polisher")
        assert polisher.name == "markdown_polisher"
        assert isinstance(polisher.name, str)


class TestComponentChaining:
    """Test chaining components together (HTML → preprocess → convert → polish)."""

    @pytest.fixture(scope="session")
    def spacy_module(self):
        """Import spacy (skip test if not available)."""
        try:
            import spacy

            return spacy
        except ImportError:
            pytest.skip("spaCy not installed")

    @pytest.fixture(scope="session")
    def nlp(self, spacy_module):
        """Load spaCy model (skip if not available)."""
        try:
            nlp = spacy_module.load("en_core_web_md")
            return nlp
        except OSError:
            pytest.skip("en_core_web_md model not installed")

    def test_chain_all_three_components(self, nlp):
        """Chain all 3 components together: HTML → preprocess → convert → polish."""
        # Create components via factory
        preprocessor = nlp.create_pipe("html_preprocessor")
        converter = nlp.create_pipe("html_markdown_converter")
        polisher = nlp.create_pipe("markdown_polisher")

        # Input HTML
        raw_html = "<div><p>Job\xa0Description</p><ul><li>Requirement\xa01</li><li>Requirement\xa02</li></ul></div>"

        # Chain: HTML → preprocess → convert → polish
        step1 = preprocessor(raw_html)
        assert isinstance(step1, str)
        assert "\xa0" not in step1  # nbsp removed

        step2 = converter(step1)
        assert isinstance(step2, str)
        # Should be markdown-ish (or original HTML if conversion fails)
        assert len(step2) > 0

        step3 = polisher(step2)
        assert isinstance(step3, str)
        # Final output should be string
        assert len(step3) > 0

    def test_chain_preprocessor_to_converter(self, nlp):
        """Test chaining preprocessor to converter."""
        preprocessor = nlp.create_pipe("html_preprocessor")
        converter = nlp.create_pipe("html_markdown_converter")

        html = "<div><p>Test\xa0Content</p></div>"
        cleaned = preprocessor(html)
        markdown = converter(cleaned)

        assert isinstance(markdown, str)
        assert len(markdown) > 0
        # If successful conversion to markdown, should not have HTML tags
        # (or have minimal HTML)

    def test_chain_converter_to_polisher(self, nlp):
        """Test chaining converter to polisher."""
        converter = nlp.create_pipe("html_markdown_converter")
        polisher = nlp.create_pipe("markdown_polisher")

        html = "<div><p>Content</p><ul><li>Item1</li><li>Item2</li></ul></div>"
        markdown = converter(html)
        polished = polisher(markdown)

        assert isinstance(polished, str)
        assert len(polished) > 0


class TestComponentProperties:
    """Test component properties are accessible."""

    @pytest.fixture(scope="session")
    def spacy_module(self):
        """Import spacy (skip test if not available)."""
        try:
            import spacy

            return spacy
        except ImportError:
            pytest.skip("spaCy not installed")

    @pytest.fixture(scope="session")
    def nlp(self, spacy_module):
        """Load spaCy model (skip if not available)."""
        try:
            nlp = spacy_module.load("en_core_web_md")
            return nlp
        except OSError:
            pytest.skip("en_core_web_md model not installed")

    def test_preprocessor_properties(self, nlp):
        """Verify HTMLPreprocessor properties accessible."""
        preprocessor = nlp.create_pipe("html_preprocessor")
        assert hasattr(preprocessor, "name")
        assert hasattr(preprocessor, "process")
        assert callable(preprocessor.process)

    def test_converter_properties(self, nlp):
        """Verify HTMLMarkdownConverter properties accessible."""
        converter = nlp.create_pipe("html_markdown_converter")
        assert hasattr(converter, "name")
        assert hasattr(converter, "process")
        assert hasattr(converter, "fallback_mode")
        assert converter.fallback_mode == "html"
        assert callable(converter.process)

    def test_polisher_properties(self, nlp):
        """Verify MarkdownPolisher properties accessible."""
        polisher = nlp.create_pipe("markdown_polisher")
        assert hasattr(polisher, "name")
        assert hasattr(polisher, "process")
        assert hasattr(polisher, "rules")
        assert callable(polisher.process)
        assert isinstance(polisher.rules, list)
        assert len(polisher.rules) > 0


class TestDirectInstantiation:
    """Test components can still be instantiated directly (not via factory)."""

    def test_direct_instantiation_preprocessor(self):
        """Verify direct instantiation of HTMLPreprocessor."""
        preprocessor = HTMLPreprocessor()
        assert preprocessor.name == "html_preprocessor"
        html = "Test\xa0String"
        result = preprocessor.process(html)
        assert "\xa0" not in result

    def test_direct_instantiation_converter(self):
        """Verify direct instantiation of HTMLMarkdownConverter."""
        converter = HTMLMarkdownConverter()
        assert converter.name == "html_markdown_converter"
        html = "<p>Test</p>"
        result = converter.process(html)
        assert isinstance(result, str)

    def test_direct_instantiation_polisher(self):
        """Verify direct instantiation of MarkdownPolisher."""
        polisher = MarkdownPolisher()
        assert polisher.name == "markdown_polisher"
        text = "Line1\n\n* Item1\n\n* Item2"
        result = polisher.process(text)
        assert isinstance(result, str)

    def test_direct_instantiation_with_custom_args(self):
        """Verify direct instantiation with custom arguments."""
        # MarkdownPolisher with custom rules
        polisher = MarkdownPolisher(rules=["line_norm", "cleanup"])
        assert len(polisher.rules) == 2
        assert "line_norm" in polisher.rules

        # HTMLMarkdownConverter with fallback_mode
        converter = HTMLMarkdownConverter(fallback_mode="raise")
        assert converter.fallback_mode == "raise"
