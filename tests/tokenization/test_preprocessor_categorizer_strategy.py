"""Tests for Preprocessor categorizer_strategy parameter.

Tests constructor validation, apply_custom_spans behavior,
and pipeline component registration for Issue #380.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import spacy


class TestPreprocessorCategorizerStrategy:
    """Test Preprocessor categorizer strategy initialization."""

    def test_unknown_categorizer_strategy_raises_value_error(self, monkeypatch) -> None:
        """Unknown strategy should raise ValueError."""
        monkeypatch.setattr("spacy.load", lambda model: MagicMock())
        from src.tokenization.preprocessor import Preprocessor

        with pytest.raises(ValueError, match="Unknown categorizer strategy"):
            Preprocessor(
                model="en_core_web_md",
                categorizer_strategy="invalid_strategy",
            )

    def test_custom_strategy_without_path_raises_value_error(self, monkeypatch) -> None:
        """custom strategy without span_patterns_path should raise ValueError."""
        monkeypatch.setattr("spacy.load", lambda model: MagicMock())
        from src.tokenization.preprocessor import Preprocessor

        with pytest.raises(ValueError, match="custom.*requires.*span_patterns_path"):
            Preprocessor(
                model="en_core_web_md",
                categorizer_strategy="custom",
                span_patterns_path=None,
            )

    def test_custom_strategy_with_valid_patterns_builds_component(self, monkeypatch) -> None:
        """custom strategy with valid patterns should build component.

        # SYNTHETIC: Test fixture patterns
        """
        # Create a temporary valid patterns file
        patterns = [
            {
                "category": "tech",
                "pattern": r"python|javascript",
                "metadata": {"test": True},
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            patterns_file = Path(tmpdir) / "patterns.json"
            with open(patterns_file, "w") as f:
                json.dump(patterns, f)

            # Mock spacy.load
            mock_nlp = MagicMock()
            monkeypatch.setattr("spacy.load", lambda model: mock_nlp)

            from src.tokenization.preprocessor import Preprocessor

            # Should not raise
            preprocessor = Preprocessor(
                model="en_core_web_md",
                categorizer_strategy="custom",
                span_patterns_path=str(patterns_file),
            )
            assert preprocessor.categorizer_strategy == "custom"
            assert preprocessor._custom_span_component is not None

    def test_nlp_strategy_does_not_build_custom_component(self, monkeypatch) -> None:
        """nlp strategy should not build custom span component."""
        mock_nlp = MagicMock()
        monkeypatch.setattr("spacy.load", lambda model: mock_nlp)

        from src.tokenization.preprocessor import Preprocessor

        preprocessor = Preprocessor(
            model="en_core_web_md",
            categorizer_strategy="nlp",
        )
        assert preprocessor.categorizer_strategy == "nlp"
        assert preprocessor._custom_span_component is None

    def test_apply_custom_spans_noop_for_nlp_strategy(self, monkeypatch) -> None:
        """apply_custom_spans should be no-op for nlp strategy."""
        mock_nlp = MagicMock()
        monkeypatch.setattr("spacy.load", lambda model: mock_nlp)

        from src.tokenization.preprocessor import Preprocessor

        preprocessor = Preprocessor(
            model="en_core_web_md",
            categorizer_strategy="nlp",
        )

        # Create a blank spaCy doc
        nlp = spacy.blank("en")
        doc = nlp("test text")

        result = preprocessor.apply_custom_spans(doc)
        # Should return doc unchanged
        assert result is doc
        assert not hasattr(doc._, "custom_spans") or doc._.custom_spans is None

    def test_apply_custom_spans_sets_extension_for_custom_strategy(self, monkeypatch) -> None:
        """apply_custom_spans should set doc._.custom_spans for custom strategy.

        # SYNTHETIC: Minimal test pattern
        """
        patterns = [
            {
                "category": "skill",
                "pattern": r"python",
                "metadata": {},
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            patterns_file = Path(tmpdir) / "patterns.json"
            with open(patterns_file, "w") as f:
                json.dump(patterns, f)

            mock_nlp = MagicMock()
            monkeypatch.setattr("spacy.load", lambda model: mock_nlp)

            from src.tokenization.preprocessor import Preprocessor

            preprocessor = Preprocessor(
                model="en_core_web_md",
                categorizer_strategy="custom",
                span_patterns_path=str(patterns_file),
            )

            # Create a blank spaCy doc (no model needed, custom categorizer is regex-only)
            nlp = spacy.blank("en")
            doc = nlp("python developer")

            # apply_custom_spans should call the component
            result = preprocessor.apply_custom_spans(doc)
            assert result is doc
            # custom_spans extension should be set (from component)
            assert hasattr(result._, "custom_spans")

    def test_nlp_strategy_default_parameter(self, monkeypatch) -> None:
        """Default categorizer_strategy should be 'nlp'."""
        mock_nlp = MagicMock()
        monkeypatch.setattr("spacy.load", lambda model: mock_nlp)

        from src.tokenization.preprocessor import Preprocessor

        preprocessor = Preprocessor(model="en_core_web_md")
        assert preprocessor.categorizer_strategy == "nlp"

    def test_custom_strategy_with_missing_pattern_file_raises_error(self, monkeypatch) -> None:
        """custom strategy with missing patterns file should raise error.

        The error should be raised during __init__ when _build_custom_span_component
        calls load_patterns.
        """
        mock_nlp = MagicMock()
        monkeypatch.setattr("spacy.load", lambda model: mock_nlp)

        from src.tokenization.preprocessor import Preprocessor

        with pytest.raises((FileNotFoundError, OSError)):
            Preprocessor(
                model="en_core_web_md",
                categorizer_strategy="custom",
                span_patterns_path="/nonexistent/patterns.json",
            )

    def test_custom_strategy_with_invalid_patterns_structure_raises_error(self, monkeypatch) -> None:
        """custom strategy with invalid patterns JSON structure should raise error.

        # SYNTHETIC: Invalid pattern structure test
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            patterns_file = Path(tmpdir) / "invalid.json"
            # Not an array
            with open(patterns_file, "w") as f:
                json.dump({"invalid": "structure"}, f)

            mock_nlp = MagicMock()
            monkeypatch.setattr("spacy.load", lambda model: mock_nlp)

            from src.tokenization.preprocessor import Preprocessor

            with pytest.raises(ValueError, match="must contain a top-level array"):
                Preprocessor(
                    model="en_core_web_md",
                    categorizer_strategy="custom",
                    span_patterns_path=str(patterns_file),
                )
