"""Tests for CustomSpanCategorizer regex-based span extraction.

Model-free unit tests covering pattern validation, categorization,
pattern loading, and spaCy component integration.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import spacy
from spacy.tokens import Doc

from src.preprocessing.custom_span_categorizer import (
    MAX_PATTERN_LENGTH,
    MAX_TEXT_LENGTH,
    CustomSpanCategorizer,
    SpanCategorizerComponent,
    load_patterns,
    validate_pattern,
)
from src.preprocessing.span_types import (
    DEFAULT_RULES,
    BoundaryRules,
    SpanPattern,
)


class TestValidatePattern:
    """Tests for validate_pattern function."""

    def test_valid_simple_pattern(self) -> None:
        """Simple patterns should validate without error."""
        validate_pattern("a+b")
        validate_pattern(r"\d+")
        validate_pattern(r"python|java")

    def test_valid_lazy_quantifiers(self) -> None:
        """Lazy quantifiers (+?, *?) should not be flagged as ReDoS."""
        validate_pattern("a+?b")
        validate_pattern("a*?")
        validate_pattern(r"\d+?\s*years?")

    def test_valid_multiword_pattern(self) -> None:
        """Patterns matching multiple words should validate."""
        validate_pattern(r"\d+\s*years?\s+experience")
        validate_pattern(r"python|java|c\+\+")

    def test_redos_nested_plus_plus(self) -> None:
        """(a+)+ pattern should raise ValueError."""
        with pytest.raises(ValueError, match="ReDoS"):
            validate_pattern("(a+)+")

    def test_redos_nested_star_star(self) -> None:
        """(a*)* pattern should raise ValueError."""
        with pytest.raises(ValueError, match="ReDoS"):
            validate_pattern("(a*)*")

    def test_redos_nested_quantifier_brace(self) -> None:
        """(a+){2,} pattern should raise ValueError."""
        with pytest.raises(ValueError, match="ReDoS"):
            validate_pattern("(a+){2,}")

    def test_redos_with_closing_paren_before(self) -> None:
        """Nested quantifiers separated by ) should be detected."""
        with pytest.raises(ValueError, match="ReDoS"):
            validate_pattern("(a+)+")

    def test_pattern_exceeds_max_length(self) -> None:
        """Pattern longer than MAX_PATTERN_LENGTH should raise ValueError."""
        long_pattern = "a" * (MAX_PATTERN_LENGTH + 1)
        with pytest.raises(ValueError, match="exceeds max length"):
            validate_pattern(long_pattern)

    def test_invalid_regex(self) -> None:
        """Invalid regex syntax should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid regex"):
            validate_pattern("(unclosed")

    def test_invalid_regex_bad_quantifier(self) -> None:
        """Unescaped special chars should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid regex"):
            validate_pattern("(?P<invalid")


class TestValidatePatternAlternationOverlap:
    """Tests for the static alternation-overlap heuristic in validate_pattern.

    The check rejects quantified groups whose alternation branches overlap
    (one branch equals or is a textual prefix of another). This is a
    heuristic: see validate_pattern docstring for known limits.
    """

    @pytest.mark.parametrize(
        "pattern",
        [
            "(a|a)+",
            "(a|aa)+",
            "(a|ab)*",
            "(x|xy){2,}",
            "(x|xy){2,5}",
            "(a|aa)+?",
            "(a|aa)++",
            "(?:a|a)+",
            "(?:a|aa)*",
            "(ab|a)+",
            "(a|b|a)+",
            "(c|b|bc)+",
            "(a|)+",
            "(|a)+",
            "(?i)(a|A)+",
            "(?i:a|A)+",
            "(a|a\\d)+",
            "(a[)]|a)+",
            "((a|aa)+|b)+",
            "(x|x\\.y)+",
        ],
    )
    def test_overlapping_alternation_rejected(self, pattern: str) -> None:
        """Quantified groups with overlapping branches should raise ValueError."""
        with pytest.raises(ValueError, match="ReDoS"):
            validate_pattern(pattern)

    @pytest.mark.parametrize(
        "pattern",
        [
            "a+b",
            "a+?b",
            "(foo|bar)+",
            "(?:red|green)*",
            "(a|b)+",
            "(a|b|c)+",
            "(a|aa)",
            "(a|aa)?",
            "(a|A)+",
            "(a\\|a|b)+",
            "(a\\|a)+",
            "(a[|]a|b)+",
            "(a[|a]b)+",
            "([]|]a|b)+",
            "((a|aa)|b)+",
            "(a|aa){3}",
            "(a|aa)(b|c)+",
            "(a|b)+(a|aa)",
        ],
    )
    def test_benign_alternation_accepted(self, pattern: str) -> None:
        """Non-overlapping, unquantified, or escaped alternations should pass."""
        validate_pattern(pattern)

    def test_overlap_check_applies_at_load_time(self, tmp_path: Path) -> None:
        """Overlapping alternation in JSON pattern file should be rejected."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(json.dumps([{"category": "test", "pattern": "(a|aa)+"}]))

        with pytest.raises(ValueError, match="ReDoS"):
            load_patterns(pattern_file)

    def test_overlap_check_applies_at_categorizer_init(self) -> None:
        """CustomSpanCategorizer should refuse overlapping alternation patterns."""
        patterns = [SpanPattern(category="test", pattern="(x|xy){2,}")]

        with pytest.raises(ValueError, match="ReDoS"):
            CustomSpanCategorizer(patterns)


class TestValidatePatternMultiLevelWrapper:
    """Tests for repeated groups whose body ends in a quantified atom.

    The single-``)`` nested-quantifier regex misses wrappers with two or more
    closing parens between the inner and outer quantifier. The group-stack
    scanner catches them at any depth. Neighbours (escaped parens, character
    classes, unrepeated or exact-count groups) must still pass.
    """

    @pytest.mark.parametrize(
        "pattern",
        [
            "((a+))+",
            "(((a+)))*",
            "(?:(?:a+))+",
            "((((a+))))*",
            "((a+)?)+",
            "(x(a+))+",
            "(b|a+)+",
        ],
    )
    def test_multi_level_wrapper_rejected(self, pattern: str) -> None:
        """Repeated groups whose body ends quantified at any depth should raise."""
        with pytest.raises(ValueError, match="ReDoS"):
            validate_pattern(pattern)

    @pytest.mark.parametrize(
        "pattern",
        [
            # Must-pass set: no nested quantifier, or quantifier not in a repeated group
            "(a+)b+",
            "(ab)+",
            "(a|b)+",
            "a+b",
            "a+?b",
            # Escaped parens are literals, so the outer + does not repeat a group
            r"\(a+\)+",
            # Quantifier characters inside a class are not quantifiers
            "[a+]+",
            # Body ends in an escaped literal paren, not a group close
            r"(a+\))+",
            # Class holding ')' must not close the group early; body ends in literal a
            "([)]+a)+",
            # Class holding '(' must not open a group
            "([(]a)+",
            # Escaped quantifier is a literal, not a quantified atom
            r"((a\+))+",
            # Body ends in a literal after the quantified atom
            "((a+)b)+",
            # Wrapper without an outer repeat
            "((a+))",
            # Exact count is not a repeat (matches the existing {n} policy)
            "((a+)){2}",
            # Sibling groups do not nest
            "(a+)(b+)",
        ],
    )
    def test_multi_level_neighbours_accepted(self, pattern: str) -> None:
        """Escapes, classes, literals and non-repeated wrappers should pass."""
        validate_pattern(pattern)


class TestCustomSpanCategorizer:
    """Tests for CustomSpanCategorizer class."""

    def test_basic_match_with_offsets(self) -> None:
        """Single pattern should match and return correct offsets."""
        patterns = [SpanPattern(category="skill", pattern="Python")]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("I know Python")
        assert len(spans) == 1
        assert spans[0].category == "skill"
        assert spans[0].text == "Python"
        assert spans[0].start_char == 7
        assert spans[0].end_char == 13

    def test_multiple_matches_sorted(self) -> None:
        """Multiple matches should be sorted by position."""
        patterns = [SpanPattern(category="skill", pattern=r"\w+")]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("Python Java C++")
        assert len(spans) == 3
        assert spans[0].text == "Python"
        assert spans[1].text == "Java"
        assert spans[2].text == "C"

    def test_multiple_patterns(self) -> None:
        """Multiple patterns should all match."""
        patterns = [
            SpanPattern(category="lang", pattern="Python"),
            SpanPattern(category="lang", pattern="Java"),
        ]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("Python and Java")
        assert len(spans) == 2
        assert {s.category for s in spans} == {"lang"}

    def test_pattern_none_skipped(self) -> None:
        """Patterns with None regex should be skipped silently."""
        patterns = [
            SpanPattern(category="skip_me", pattern=None),
            SpanPattern(category="keep_me", pattern="Python"),
        ]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("Python")
        assert len(spans) == 1
        assert spans[0].category == "keep_me"

    def test_zero_length_match_skipped(self) -> None:
        """Zero-length matches should be skipped."""
        # Pattern that can match zero chars: a*
        patterns = [SpanPattern(category="test", pattern=r"a*")]
        cat = CustomSpanCategorizer(patterns)

        # The pattern a* will match at every position including zero-length
        # We should skip those and only get matches with actual length
        spans = cat.categorize("aaa")
        # Should only have 1 span (the full "aaa"), not multiple zero-length
        # Actually, a* matches "aaa" once at position 0, then zero-length
        # at position 3. We skip the zero-length, so should be 1.
        assert all(s.start_char != s.end_char for s in spans)

    def test_metadata_copied_per_match(self) -> None:
        """Metadata should be copied (not aliased) per match."""
        metadata = {"confidence": 0.95}
        patterns = [
            SpanPattern(
                category="skill",
                pattern=r"Python|Java",
                metadata=metadata,
            )
        ]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("Python and Java")
        assert len(spans) == 2

        # Modify first span's metadata
        spans[0].metadata["confidence"] = 0.50

        # Second span should still have original value
        assert spans[1].metadata["confidence"] == 0.95

    def test_metadata_isolated_from_pattern(self) -> None:
        """Span metadata should not affect pattern object."""
        metadata = {"v": 1}
        pattern = SpanPattern(
            category="test",
            pattern="test",
            metadata=metadata,
        )
        patterns = [pattern]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("test test")
        spans[0].metadata["v"] = 999

        # Original pattern metadata unchanged
        assert pattern.metadata["v"] == 1

    def test_text_exceeds_max_length_raises(self) -> None:
        """Text exceeding MAX_TEXT_LENGTH should raise ValueError."""
        patterns = [SpanPattern(category="test", pattern="a")]
        cat = CustomSpanCategorizer(patterns)

        huge_text = "a" * (MAX_TEXT_LENGTH + 1)
        with pytest.raises(ValueError, match="exceeds max length"):
            cat.categorize(huge_text)

    def test_empty_text(self) -> None:
        """Empty text should return empty spans."""
        patterns = [SpanPattern(category="test", pattern="test")]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("")
        assert spans == []

    def test_no_matches(self) -> None:
        """Text with no matches should return empty spans."""
        patterns = [SpanPattern(category="test", pattern="xyz")]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("abc def ghi")
        assert spans == []

    def test_case_sensitive_by_default(self) -> None:
        """Patterns are case-sensitive by default."""
        patterns = [SpanPattern(category="test", pattern="Python")]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("python Python PYTHON")
        assert len(spans) == 1
        assert spans[0].text == "Python"

    def test_sorted_by_start_then_end(self) -> None:
        """Spans should sort by start_char, then end_char."""
        patterns = [SpanPattern(category="test", pattern=r"\w+")]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("foo bar baz")
        starts = [s.start_char for s in spans]
        assert starts == sorted(starts)


class TestLoadPatterns:
    """Tests for load_patterns function."""

    def test_load_patterns_basic(self, tmp_path: Path) -> None:
        """Happy path: load valid patterns from JSON."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(
            json.dumps(
                [
                    {
                        "category": "skill",
                        "pattern": r"\w+",
                        "metadata": {"confidence": 0.9},
                    }
                ]
            )
        )

        patterns = load_patterns(pattern_file)
        assert len(patterns) == 1
        assert patterns[0].category == "skill"
        assert patterns[0].pattern == r"\w+"
        assert patterns[0].metadata["confidence"] == 0.9

    def test_load_patterns_with_boundary_rules(self, tmp_path: Path) -> None:
        """Load patterns with custom boundary_rules."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(
            json.dumps(
                [
                    {
                        "category": "test",
                        "pattern": "test",
                        "boundary_rules": {
                            "hard_stops": [".", "!"],
                            "soft_stops": [","],
                            "stop_words": ["if"],
                        },
                    }
                ]
            )
        )

        patterns = load_patterns(pattern_file)
        assert patterns[0].boundary_rules.hard_stops == frozenset({".", "!"})
        assert patterns[0].boundary_rules.soft_stops == frozenset({","})
        assert patterns[0].boundary_rules.stop_words == frozenset({"if"})

    def test_load_patterns_partial_boundary_rules(self, tmp_path: Path) -> None:
        """Partial boundary_rules should fall back to DEFAULT_RULES."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(
            json.dumps(
                [
                    {
                        "category": "test",
                        "pattern": "test",
                        "boundary_rules": {
                            "hard_stops": [".", "!"],
                        },
                    }
                ]
            )
        )

        patterns = load_patterns(pattern_file)
        assert patterns[0].boundary_rules.hard_stops == frozenset({".", "!"})
        # soft_stops and stop_words should use DEFAULT_RULES
        assert patterns[0].boundary_rules.soft_stops == DEFAULT_RULES.soft_stops
        assert patterns[0].boundary_rules.stop_words == DEFAULT_RULES.stop_words

    def test_load_patterns_no_pattern_key(self, tmp_path: Path) -> None:
        """Pattern with missing 'pattern' key should be valid (None regex)."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(
            json.dumps(
                [
                    {
                        "category": "test",
                        "metadata": {"info": "no regex"},
                    }
                ]
            )
        )

        patterns = load_patterns(pattern_file)
        assert patterns[0].pattern is None

    def test_load_patterns_rejects_non_list(self, tmp_path: Path) -> None:
        """JSON top-level must be array, not dict."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(json.dumps({"category": "test", "pattern": "x"}))

        with pytest.raises(ValueError, match="must contain a top-level array"):
            load_patterns(pattern_file)

    def test_load_patterns_missing_category(self, tmp_path: Path) -> None:
        """Missing or empty 'category' should raise ValueError."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(json.dumps([{"pattern": "test"}]))

        with pytest.raises(ValueError, match="must have a 'category' key"):
            load_patterns(pattern_file)

    def test_load_patterns_redos_pattern_rejected(self, tmp_path: Path) -> None:
        """ReDoS pattern in JSON should be rejected."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(json.dumps([{"category": "test", "pattern": "(a+)+"}]))

        with pytest.raises(ValueError, match="ReDoS"):
            load_patterns(pattern_file)

    def test_load_patterns_invalid_regex_rejected(self, tmp_path: Path) -> None:
        """Invalid regex pattern should be rejected."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(json.dumps([{"category": "test", "pattern": "(unclosed"}]))

        with pytest.raises(ValueError, match="Invalid regex"):
            load_patterns(pattern_file)

    def test_load_patterns_file_not_found(self) -> None:
        """Missing file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_patterns("/nonexistent/path/patterns.json")

    def test_load_patterns_multiple_entries(self, tmp_path: Path) -> None:
        """Load multiple patterns from single file."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(
            json.dumps(
                [
                    {"category": "skill", "pattern": "Python"},
                    {"category": "skill", "pattern": "Java"},
                    {"category": "seniority", "pattern": r"\d+\s*years?"},
                ]
            )
        )

        patterns = load_patterns(pattern_file)
        assert len(patterns) == 3
        assert patterns[0].category == "skill"
        assert patterns[2].pattern == r"\d+\s*years?"

    def test_load_patterns_empty_array(self, tmp_path: Path) -> None:
        """Empty pattern array should be valid."""
        pattern_file = tmp_path / "patterns.json"
        pattern_file.write_text(json.dumps([]))

        patterns = load_patterns(pattern_file)
        assert patterns == []


class TestSpanCategorizerComponent:
    """Tests for SpanCategorizerComponent spaCy wrapper."""

    def test_component_sets_custom_spans_attribute(self) -> None:
        """Component should set doc._.custom_spans."""
        nlp = spacy.blank("en")
        patterns = [SpanPattern(category="skill", pattern="Python")]
        cat = CustomSpanCategorizer(patterns)
        comp = SpanCategorizerComponent(cat)

        doc = nlp("I know Python")
        doc = comp(doc)

        assert doc._.custom_spans is not None
        assert isinstance(doc._.custom_spans, list)

    def test_component_extracts_spans_as_dicts(self) -> None:
        """Component should store spans as dicts with required keys."""
        nlp = spacy.blank("en")
        patterns = [SpanPattern(category="skill", pattern="Python")]
        cat = CustomSpanCategorizer(patterns)
        comp = SpanCategorizerComponent(cat)

        doc = nlp("I know Python")
        doc = comp(doc)

        assert len(doc._.custom_spans) == 1
        span_dict = doc._.custom_spans[0]
        assert span_dict["category"] == "skill"
        assert span_dict["text"] == "Python"
        assert "start_char" in span_dict
        assert "end_char" in span_dict
        assert "metadata" in span_dict

    def test_component_correct_offsets(self) -> None:
        """Component should report correct character offsets."""
        nlp = spacy.blank("en")
        patterns = [SpanPattern(category="skill", pattern="Python")]
        cat = CustomSpanCategorizer(patterns)
        comp = SpanCategorizerComponent(cat)

        doc = nlp("I know Python")
        doc = comp(doc)

        span = doc._.custom_spans[0]
        assert span["start_char"] == 7
        assert span["end_char"] == 13
        assert doc.text[span["start_char"] : span["end_char"]] == "Python"

    def test_component_multiple_patterns(self) -> None:
        """Component should handle multiple patterns."""
        nlp = spacy.blank("en")
        patterns = [
            SpanPattern(category="lang", pattern="Python"),
            SpanPattern(category="lang", pattern="Java"),
        ]
        cat = CustomSpanCategorizer(patterns)
        comp = SpanCategorizerComponent(cat)

        doc = nlp("Python and Java")
        doc = comp(doc)

        assert len(doc._.custom_spans) == 2

    def test_component_preserves_metadata(self) -> None:
        """Component should include pattern metadata in dicts."""
        nlp = spacy.blank("en")
        patterns = [
            SpanPattern(
                category="skill",
                pattern="Python",
                metadata={"confidence": 0.95, "tier": 1},
            )
        ]
        cat = CustomSpanCategorizer(patterns)
        comp = SpanCategorizerComponent(cat)

        doc = nlp("I know Python")
        doc = comp(doc)

        span = doc._.custom_spans[0]
        assert span["metadata"]["confidence"] == 0.95
        assert span["metadata"]["tier"] == 1

    def test_component_empty_spans(self) -> None:
        """Component should set empty list when no matches."""
        nlp = spacy.blank("en")
        patterns = [SpanPattern(category="skill", pattern="Rust")]
        cat = CustomSpanCategorizer(patterns)
        comp = SpanCategorizerComponent(cat)

        doc = nlp("Python and Java")
        doc = comp(doc)

        assert doc._.custom_spans == []

    def test_component_multiple_sentences(self) -> None:
        """Component should handle multi-sentence text."""
        nlp = spacy.blank("en")
        patterns = [SpanPattern(category="skill", pattern=r"Python|Java")]
        cat = CustomSpanCategorizer(patterns)
        comp = SpanCategorizerComponent(cat)

        text = "I know Python. Java is also useful."
        doc = nlp(text)
        doc = comp(doc)

        assert len(doc._.custom_spans) == 2
        assert doc._.custom_spans[0]["text"] == "Python"
        assert doc._.custom_spans[1]["text"] == "Java"


class TestEdgeCases:
    """Edge case and integration tests."""

    def test_overlapping_spans(self) -> None:
        """Overlapping matches should all be included."""
        patterns = [
            SpanPattern(category="long", pattern=r"Python"),
            SpanPattern(category="short", pattern=r"Py"),
        ]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("Python")
        # Same start; sorted by (start_char, end_char), so shorter first
        assert len(spans) == 2
        assert spans[0].text == "Py"
        assert spans[1].text == "Python"

    def test_unicode_text(self) -> None:
        """Unicode characters should be handled correctly."""
        patterns = [SpanPattern(category="lang", pattern=r"\w+")]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("Python 파이썬 Java")
        # Should match word boundaries correctly
        assert len(spans) >= 2

    def test_newlines_in_text(self) -> None:
        """Newlines should not break categorization."""
        patterns = [SpanPattern(category="skill", pattern=r"Python|Java")]
        cat = CustomSpanCategorizer(patterns)

        text = "Skills:\nPython\nJava"
        spans = cat.categorize(text)
        assert len(spans) == 2

    def test_pattern_at_text_boundary(self) -> None:
        """Patterns at start/end of text should match."""
        patterns = [SpanPattern(category="test", pattern="Python")]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("Python is great")
        assert spans[0].start_char == 0

        spans = cat.categorize("Language: Python")
        assert spans[0].end_char == len("Language: Python")

    def test_special_regex_chars_escaped(self) -> None:
        """Patterns with escaped special chars should work."""
        patterns = [SpanPattern(category="test", pattern=r"C\+\+")]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("C++ is fast")
        assert len(spans) == 1
        assert spans[0].text == "C++"

    def test_case_insensitive_pattern(self) -> None:
        """Case-insensitive patterns should work with (?i)."""
        patterns = [SpanPattern(category="test", pattern="(?i)python")]
        cat = CustomSpanCategorizer(patterns)

        spans = cat.categorize("python Python PYTHON")
        assert len(spans) == 3

    def test_multiline_pattern(self) -> None:
        """Multiline patterns should work."""
        patterns = [
            SpanPattern(
                category="test",
                pattern=r"skill.*years",
            )
        ]
        cat = CustomSpanCategorizer(patterns)

        text = "skill: 5 years"
        spans = cat.categorize(text)
        assert len(spans) == 1
