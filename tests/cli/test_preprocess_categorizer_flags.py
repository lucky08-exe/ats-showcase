"""Tests for preprocess CLI --categorizer-strategy and --span-patterns flags.

Tests validation of categorizer strategy options, patterns file handling,
and help text for Issue #380.
"""

import json
import re
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from src.cli import app

runner = CliRunner()


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text.

    Args:
        text: Text potentially containing ANSI escape sequences

    Returns:
        Text with all ANSI escape codes removed
    """
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def valid_patterns_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a valid span patterns JSON file.

    # SYNTHETIC: Test fixture file structure
    """
    patterns = [
        {
            "category": "technical_skill",
            "pattern": r"(?:python|javascript|java)",
            "metadata": {"source": "test"},
        },
        {
            "category": "seniority",
            "pattern": r"(?:senior|junior|lead)",
            "metadata": {"source": "test"},
        },
    ]
    patterns_file = tmp_path / "patterns.json"
    with open(patterns_file, "w") as f:
        json.dump(patterns, f)
    yield patterns_file


@pytest.fixture
def invalid_patterns_json_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Create an invalid JSON patterns file (not an array).

    # SYNTHETIC: Test fixture for malformed JSON
    """
    patterns_file = tmp_path / "invalid.json"
    with open(patterns_file, "w") as f:
        f.write('{"category": "test"}')  # Object, not array
    yield patterns_file


@pytest.fixture
def malformed_json_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a completely malformed JSON patterns file.

    # SYNTHETIC: Test fixture for invalid JSON syntax
    """
    patterns_file = tmp_path / "malformed.json"
    with open(patterns_file, "w") as f:
        f.write("{invalid json [")
    yield patterns_file


@pytest.fixture
def stub_preprocessor(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stub Preprocessor to avoid loading spaCy model during tests.

    Patches src.tokenization.preprocessor.Preprocessor with a MagicMock
    so that categorizer validation tests can proceed to the jobs-check phase
    without requiring en_core_web_md model to be installed.

    Args:
        monkeypatch: pytest fixture for patching modules

    Returns:
        MagicMock instance that replaces Preprocessor
    """
    mock_preprocessor = MagicMock()
    monkeypatch.setattr("src.tokenization.preprocessor.Preprocessor", mock_preprocessor)
    return mock_preprocessor


class TestPreprocessCategorizerFlagsHelp:
    """Test help text for new CLI flags."""

    def test_help_shows_categorizer_strategy_flag(self) -> None:
        """--help should display --categorizer-strategy flag."""
        result = runner.invoke(app, ["preprocess", "--help"])
        assert result.exit_code == 0
        clean_output = strip_ansi(result.output)
        # Help text truncates long flag names, so check for partial match
        assert "categorizer" in clean_output.lower()
        assert "nlp" in clean_output.lower() and "custom" in clean_output.lower()

    def test_help_shows_span_patterns_flag(self) -> None:
        """--help should display --span-patterns flag."""
        result = runner.invoke(app, ["preprocess", "--help"])
        assert result.exit_code == 0
        clean_output = strip_ansi(result.output)
        assert "span" in clean_output.lower()
        assert "patterns" in clean_output.lower()


class TestPreprocessCategorizerValidation:
    """Test categorizer strategy validation."""

    def test_unknown_categorizer_strategy_exits_with_error(self) -> None:
        """Unknown strategy should exit with code 1 and error message."""
        result = runner.invoke(app, ["preprocess", "--categorizer-strategy", "unknown"])
        assert result.exit_code == 1
        clean_output = strip_ansi(result.output).lower()
        assert "invalid categorizer strategy" in clean_output
        assert "traceback" not in clean_output

    def test_custom_strategy_without_span_patterns_exits_with_error(self) -> None:
        """--categorizer-strategy custom without --span-patterns should exit 1."""
        result = runner.invoke(app, ["preprocess", "--categorizer-strategy", "custom"])
        assert result.exit_code == 1
        clean_output = strip_ansi(result.output).lower()
        assert "--span-patterns" in clean_output
        assert "traceback" not in clean_output

    def test_custom_strategy_with_nonexistent_file_exits_with_error(self) -> None:
        """--categorizer-strategy custom with missing file should exit 1."""
        result = runner.invoke(
            app,
            [
                "preprocess",
                "--categorizer-strategy",
                "custom",
                "--span-patterns",
                "/nonexistent/patterns.json",
            ],
        )
        assert result.exit_code == 1
        clean_output = strip_ansi(result.output).lower()
        assert "span patterns file not found" in clean_output
        assert "traceback" not in clean_output

    def test_custom_strategy_with_invalid_patterns_json_exits_with_error(
        self, invalid_patterns_json_file: Path
    ) -> None:
        """--span-patterns with non-array JSON should exit 1."""
        result = runner.invoke(
            app,
            [
                "preprocess",
                "--categorizer-strategy",
                "custom",
                "--span-patterns",
                str(invalid_patterns_json_file),
            ],
        )
        assert result.exit_code == 1
        clean_output = strip_ansi(result.output).lower()
        assert "invalid span patterns file" in clean_output
        assert "traceback" not in clean_output

    def test_custom_strategy_with_malformed_json_exits_with_error(self, malformed_json_file: Path) -> None:
        """--span-patterns with malformed JSON should exit 1."""
        result = runner.invoke(
            app,
            [
                "preprocess",
                "--categorizer-strategy",
                "custom",
                "--span-patterns",
                str(malformed_json_file),
            ],
        )
        assert result.exit_code == 1
        clean_output = strip_ansi(result.output).lower()
        assert "invalid span patterns file" in clean_output
        assert "traceback" not in clean_output

    def test_nlp_strategy_with_span_patterns_validates_file(
        self, valid_patterns_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_preprocessor
    ) -> None:
        """nlp strategy with --span-patterns should still validate the file.

        Validates that file and strategy checks pass; command fails with no-jobs error
        to prove validation succeeded before the jobs check.
        """
        # Stub Preprocessor so the spaCy model is not loaded; chdir to tmp_path
        # and create empty extracted_jobs dir so preprocess reaches the jobs-check
        # phase (validation occurs before that)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "extracted_jobs").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(
            app,
            [
                "preprocess",
                "--categorizer-strategy",
                "nlp",
                "--span-patterns",
                str(valid_patterns_file),
            ],
        )
        output_lower = strip_ansi(result.output).lower()
        # File validation should succeed (file exists and is valid)
        # Command may fail for other reasons (no jobs in DB, etc), but not for patterns
        # Assert the span-patterns validation did NOT fail
        assert "span patterns file not found" not in output_lower
        assert "invalid span patterns file" not in output_lower
        # Verify we got past the categorizer strategy validation (nlp is valid)
        assert "invalid categorizer strategy" not in output_lower
        # Prove validation passed by checking exit code and jobs-check message
        assert result.exit_code == 1
        assert "no extracted jobs found" in output_lower

    def test_default_strategy_unchanged_without_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_preprocessor
    ) -> None:
        """Default behavior without --categorizer-strategy should use nlp and pass validation.

        Validates that omitting categorizer flags uses nlp strategy (default) without
        triggering validation errors. Command fails at jobs-check (no jobs found),
        proving validation passed.
        """
        # Hermetic setup: stub Preprocessor so the spaCy model is not loaded;
        # chdir to tmp_path, create empty extracted_jobs dir
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "extracted_jobs").mkdir(parents=True, exist_ok=True)

        # Invoke preprocess without any categorizer strategy or span-patterns flags
        result = runner.invoke(app, ["preprocess"])
        output_lower = strip_ansi(result.output).lower()

        # Should fail at jobs-check, not at validation
        assert result.exit_code == 1
        assert "no extracted jobs found" in output_lower
        # Validation error messages must NOT appear
        assert "invalid categorizer strategy" not in output_lower
        assert "--span-patterns" not in output_lower
        assert "span patterns file not found" not in output_lower
        assert "invalid span patterns file" not in output_lower
