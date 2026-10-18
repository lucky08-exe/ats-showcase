"""Tests for heading-only text normalization and detection (Issue #724)."""

import pytest

from src.poc.tweak.spacy_pipeline.heading_text import is_heading_only, normalize_heading_text

KNOWN_HEADING_PHRASES = (
    "minimum qualifications",
    "additional qualifications",
    "preferred qualifications",
    "required qualifications",
    "working conditions",
    "key responsibilities",
    "applicants who do not meet these qualifications will not be forwarded to the hiring department",
)


class TestNormalizeHeadingText:
    """Test normalization before heading comparisons."""

    @pytest.mark.parametrize(
        ("candidate", "expected"),
        [
            ("  WORKING CONDITIONS*", "working conditions"),
            ("**Required Qualifications**", "required qualifications"),
            ("_Required Qualifications_", "required qualifications"),
            ("## Working Conditions", "working conditions"),
            ("Required Qualifications:", "required qualifications"),
            ("\t ## Working Conditions: \n", "working conditions"),
        ],
    )
    def test_removes_edge_markers_and_normalizes_case(self, candidate: str, expected: str) -> None:
        """Supported edge markers, colon, and surrounding whitespace are removed."""
        assert normalize_heading_text(candidate) == expected

    @pytest.mark.parametrize(
        ("candidate", "expected"),
        [
            ("Required: Python", "required: python"),
            ("Key Responsibilities & Duties", "key responsibilities & duties"),
        ],
    )
    def test_preserves_internal_punctuation(self, candidate: str, expected: str) -> None:
        """Punctuation in the middle of a candidate must not be removed."""
        assert normalize_heading_text(candidate) == expected


class TestIsHeadingOnly:
    """Test known and explicitly supplied heading detection."""

    @pytest.mark.parametrize(
        "candidate",
        [variant for phrase in KNOWN_HEADING_PHRASES for variant in (phrase, f"**{phrase}**", f"{phrase}:")],
    )
    def test_recognizes_all_known_phrases_in_supported_forms(self, candidate: str) -> None:
        """Every issue-defined heading matches in plain, bold, and colon forms."""
        assert is_heading_only(candidate)

    @pytest.mark.parametrize(
        "candidate",
        [
            "Required: Python",
            "5+ years of software engineering experience.",
            "Experience with Python and SQL",
        ],
    )
    def test_rejects_requirement_text(self, candidate: str) -> None:
        """Requirement content is not treated as a standalone heading."""
        assert not is_heading_only(candidate)

    @pytest.mark.parametrize("candidate", ["", "   ", "\t\n"])
    def test_rejects_empty_or_whitespace_only_text(self, candidate: str) -> None:
        """Empty candidates cannot be headings."""
        assert not is_heading_only(candidate)

    def test_matches_a_normalized_supplied_heading(self) -> None:
        """Candidate and supplied heading are both normalized before comparison."""
        assert is_heading_only("## Job Benefits:", "**Job Benefits**")

    def test_rejects_a_mismatched_supplied_heading(self) -> None:
        """A supplied heading must match rather than falling back to known phrases."""
        assert not is_heading_only("Job Benefits", "Job Requirements")
        assert not is_heading_only("Working Conditions", "Required Qualifications")

    def test_handles_none_and_empty_supplied_headings(self) -> None:
        """None uses known-phrase detection, while an empty supplied heading does not match."""
        assert is_heading_only("Required Qualifications", None)
        assert not is_heading_only("Required Qualifications", "")
        assert not is_heading_only("", "")
