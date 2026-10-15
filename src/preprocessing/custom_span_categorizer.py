"""Custom regex-based span categorizer without spaCy NLP overhead.

Pure regex pattern matching for requirement span extraction, ideal for
lightweight categorization without full NLP pipeline dependency.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from spacy.language import Language
from spacy.tokens import Doc

from src.preprocessing.span_types import (
    DEFAULT_RULES,
    BoundaryRules,
    SpanCategory,
    SpanPattern,
)

# Constants
MAX_PATTERN_LENGTH = 500
MAX_TEXT_LENGTH = 200_000

# Register custom extension at module level
if not Doc.has_extension("custom_spans"):
    Doc.set_extension("custom_spans", default=None)


# Quantifier that makes a group repeatable: +, *, {n,}, {n,m}, plus an
# optional lazy (?) or possessive (+) suffix. Exact {n} is not flagged.
_REPEAT_AFTER_GROUP = re.compile(r"(?:[+*]|\{\d*,\d*\})[?+]?")

# Group header that is not part of the alternation body: (?:, (?=, (?!,
# (?<=, (?<!, (?P<name>, scoped inline flags such as (?i: or (?-i:.
_GROUP_HEADER = re.compile(r"\?(?:P<\w+>|<[=!]|[=!:]|[aiLmsux]*(?:-[imsx]+)?:)")

# Inline flag group that enables case-insensitive matching somewhere.
_CASE_INSENSITIVE_FLAG = re.compile(r"\(\?[aiLmsux]*i")


def _skip_char_class(pattern: str, start: int) -> int:
    """Return index just past the character class opened at ``start``.

    Handles a leading ``^``, a leading literal ``]``, and backslash escapes.
    Returns ``len(pattern)`` if the class is unterminated.
    """
    n = len(pattern)
    j = start + 1
    if j < n and pattern[j] == "^":
        j += 1
    if j < n and pattern[j] == "]":
        j += 1
    while j < n and pattern[j] != "]":
        j += 2 if pattern[j] == "\\" else 1
    return min(j + 1, n)


def _branches_overlap(branches: list[str], case_insensitive: bool) -> bool:
    """Return True if any two branches are equal or one is a prefix of the other."""
    norm = [b.casefold() if case_insensitive else b for b in branches]
    for i, left in enumerate(norm):
        for right in norm[i + 1 :]:
            if left.startswith(right) or right.startswith(left):
                return True
    return False


def _has_overlapping_repeated_alternation(pattern: str) -> bool:
    """Scan pattern for a repeated group whose alternation branches overlap.

    Tracks escapes, character classes and group nesting so that only the
    top-level branches of each group are compared. Never raises: malformed
    input is left for ``re.compile`` to report.
    """
    case_insensitive = _CASE_INSENSITIVE_FLAG.search(pattern) is not None
    # Each open group: (index where the current branch starts, finished branches)
    stack: list[tuple[int, list[str]]] = []
    n = len(pattern)
    i = 0
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "[":
            i = _skip_char_class(pattern, i)
            continue
        if ch == "(":
            header = _GROUP_HEADER.match(pattern, i + 1)
            body_start = header.end() if header else i + 1
            stack.append((body_start, []))
            i = body_start
            continue
        if ch == "|" and stack:
            start, branches = stack[-1]
            branches.append(pattern[start:i])
            stack[-1] = (i + 1, branches)
        elif ch == ")" and stack:
            start, branches = stack.pop()
            branches.append(pattern[start:i])
            repeated = _REPEAT_AFTER_GROUP.match(pattern, i + 1) is not None
            if repeated and len(branches) > 1 and _branches_overlap(branches, case_insensitive):
                return True
        i += 1
    return False


def _has_quantified_group_wrapper(pattern: str) -> bool:
    """Scan pattern for a repeated group whose body ends in a quantified atom.

    Catches multi-level wrappers the single-``)`` nested-quantifier regex
    misses, e.g. ``((a+))+``. Each open group tracks whether its last item
    is quantified: directly (``a+``), or as a closed group whose own body
    ends quantified. An alternation counts if any branch ends quantified.
    Escapes, character classes and group headers are skipped as in
    ``_has_overlapping_repeated_alternation``. Never raises.
    """
    # Each frame: [last item quantified, an earlier alternation branch was]
    frames: list[list[bool]] = [[False, False]]
    n = len(pattern)
    i = 0
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            frames[-1][0] = False
            i += 2
            continue
        if ch == "[":
            frames[-1][0] = False
            i = _skip_char_class(pattern, i)
            continue
        if ch == "(":
            header = _GROUP_HEADER.match(pattern, i + 1)
            i = header.end() if header else i + 1
            frames.append([False, False])
            continue
        if ch == "|":
            top = frames[-1]
            top[1] = top[1] or top[0]
            top[0] = False
        elif ch == ")" and len(frames) > 1:
            last, earlier = frames.pop()
            body_quantified = last or earlier
            repeat = _REPEAT_AFTER_GROUP.match(pattern, i + 1)
            if repeat is not None and body_quantified:
                return True
            # The closed group is a quantified item if it is repeated, and
            # otherwise carries its body's quantified-ness to the parent.
            frames[-1][0] = body_quantified or repeat is not None
        else:
            repeat = _REPEAT_AFTER_GROUP.match(pattern, i)
            if repeat is not None:
                frames[-1][0] = True
                i = repeat.end()
                continue
            # A bare "?" is not a repeat and does not change the flag: it
            # follows an atom or group whose state is already recorded.
            if ch != "?":
                frames[-1][0] = False
        i += 1
    return False


def validate_pattern(pattern: str) -> None:
    """Validate regex pattern for safety and correctness.

    Checks pattern length, detects ReDoS-prone nested quantifiers like
    (a+)+, (a*)*, and rejects repeated groups whose alternation branches
    overlap, like (a|aa)+ or (x|xy){2,}. Lazy quantifiers (+?, *?) are
    safe and not flagged.

    The alternation check is a static heuristic, not a regex engine
    analysis. It compares the raw text of each branch of a group followed
    by +, *, {n,} or {n,m} (optionally with a ? or + suffix). A group is
    rejected when two branches are equal or one is a textual prefix of the
    other. Case is folded only when the pattern contains an inline (?i)
    style flag. Known limits:
      - Overlap via character classes, ``.``, or ``\\w``-style escapes is
        not detected, e.g. (\\w+|x)+ or (a|[a])+.
      - Textual prefixes that never overlap in practice are rejected, e.g.
        (a|a\\d)+ (a false positive).
      - Exact counts {n} are not checked, e.g. (a|aa){3}.
      - Ambiguity across sibling groups, e.g. (a|b)*(a|b)*, is not detected.
      - Escaped metacharacters are compared as written, so (\\.|.)+ is
        not detected.
      - Only the last item of a group body decides whether the body ends in
        a quantifier, so a repeated group with a trailing optional atom is
        accepted, e.g. (a+c?)+. A bare ``?`` is not a repeat, e.g. (a?)+.
      - A ``(?i`` flag anywhere in the pattern (including a scoped ``(?i:...)``)
        enables case-insensitive branch comparison for every group in the
        pattern, which can over-reject.

    Args:
        pattern: Regex pattern string to validate.

    Raises:
        ValueError: If pattern exceeds length limit, contains ReDoS-prone
            nested quantifiers or overlapping repeated alternation, or
            fails to compile.

    Examples:
        >>> validate_pattern("a+b")  # OK
        >>> validate_pattern("a+?b")  # OK (lazy quantifier)
        >>> validate_pattern("(a+)+")  # Raises ValueError (ReDoS)
        >>> validate_pattern("(a|aa)+")  # Raises ValueError (ReDoS)
        >>> validate_pattern("((a+))+")  # Raises ValueError (ReDoS)
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise ValueError(f"Pattern exceeds max length {MAX_PATTERN_LENGTH}: {len(pattern)}")

    # Strip lazy quantifiers (? directly after +, *, or })
    # to detect nested quantifiers properly
    stripped = re.sub(r"([+*}])\?", r"\1", pattern)

    # Check for nested quantifiers: [+*}] followed optionally by )
    # then another quantifier [+*{]
    redos_pattern = r"[+*}]\)?[+*{]"
    if re.search(redos_pattern, stripped):
        raise ValueError(f"Pattern contains ReDoS-prone nested quantifiers: {pattern}")

    # Check for repeated groups with overlapping alternation branches
    if _has_overlapping_repeated_alternation(pattern):
        raise ValueError(f"Pattern contains ReDoS-prone overlapping alternation: {pattern}")

    # Check for repeated groups whose body ends in a quantified atom, at any depth
    if _has_quantified_group_wrapper(pattern):
        raise ValueError(f"Pattern contains ReDoS-prone nested quantifiers: {pattern}")

    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex pattern: {exc}") from exc


class CustomSpanCategorizer:
    """Pure regex-based span categorizer without spaCy NLP.

    Matches text against a list of regex patterns and extracts spans
    with category labels and metadata. Zero-length matches are skipped.

    Attributes:
        patterns: List of (SpanPattern, compiled regex) tuples.
    """

    def __init__(self, patterns: list[SpanPattern]) -> None:
        """Initialize categorizer with patterns.

        Filters out patterns with None regex, validates each pattern,
        and pre-compiles regexes for efficiency.

        Args:
            patterns: List of SpanPattern objects. Patterns with
                .pattern = None are silently skipped.

        Raises:
            ValueError: If any pattern fails validation.
        """
        self.patterns: list[tuple[SpanPattern, re.Pattern[str]]] = []

        for sp in patterns:
            # Skip patterns with None regex
            if sp.pattern is None:
                continue

            # Validate pattern (raises ValueError if invalid)
            validate_pattern(sp.pattern)

            # Compile and store
            compiled = re.compile(sp.pattern)
            self.patterns.append((sp, compiled))

    def categorize(self, text: str) -> list[SpanCategory]:
        """Extract and categorize spans from text.

        Applies all patterns to text, collects matches, and returns
        sorted list of SpanCategory objects. Zero-length matches are
        skipped. Metadata from pattern is deep-copied per match.

        Args:
            text: Input text to categorize.

        Returns:
            List of SpanCategory objects sorted by (start_char, end_char).

        Raises:
            ValueError: If text exceeds MAX_TEXT_LENGTH.
        """
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"Text exceeds max length {MAX_TEXT_LENGTH}: {len(text)}")

        results: list[SpanCategory] = []

        for pattern_obj, compiled_regex in self.patterns:
            for match in compiled_regex.finditer(text):
                # Skip zero-length matches
                if match.start() == match.end():
                    continue

                # Copy metadata to isolate per match
                metadata = dict(pattern_obj.metadata)

                span = SpanCategory(
                    category=pattern_obj.category,
                    text=match.group(0),
                    start_char=match.start(),
                    end_char=match.end(),
                    metadata=metadata,
                )
                results.append(span)

        # Sort by start position, then end position
        results.sort(key=lambda s: (s.start_char, s.end_char))

        return results


def load_patterns(path: str | Path) -> list[SpanPattern]:
    """Load patterns from JSON file.

    File format: JSON array of objects with keys:
    - category (required, string)
    - pattern (optional, string regex)
    - metadata (optional, dict)
    - boundary_rules (optional, object with optional lists
      hard_stops, soft_stops, stop_words)

    Each pattern is validated during construction (via SpanPattern
    __post_init__ and validate_pattern).

    Args:
        path: Path to JSON file.

    Returns:
        List of SpanPattern objects.

    Raises:
        ValueError: If JSON top-level is not a list or category is
            missing from any object.
        FileNotFoundError: If file does not exist.
        json.JSONDecodeError: If JSON is malformed.

    Examples:
        >>> patterns = load_patterns("config/patterns.json")
    """
    path = Path(path)

    with open(path) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("JSON file must contain a top-level array")

    patterns = []
    for obj in data:
        if not isinstance(obj, dict):
            raise ValueError("Each pattern entry must be a dict")

        category = obj.get("category")
        if not category:
            raise ValueError("Each pattern must have a 'category' key")

        pattern_str = obj.get("pattern")
        metadata = obj.get("metadata", {})

        # Parse boundary_rules if present
        boundary_rules = DEFAULT_RULES
        if "boundary_rules" in obj:
            br_obj = obj["boundary_rules"]
            hard_stops = frozenset(br_obj.get("hard_stops", DEFAULT_RULES.hard_stops))
            soft_stops = frozenset(br_obj.get("soft_stops", DEFAULT_RULES.soft_stops))
            stop_words = frozenset(br_obj.get("stop_words", DEFAULT_RULES.stop_words))
            boundary_rules = BoundaryRules(
                hard_stops=hard_stops,
                soft_stops=soft_stops,
                stop_words=stop_words,
            )

        # Validate pattern if provided
        if pattern_str is not None:
            validate_pattern(pattern_str)

        sp = SpanPattern(
            category=category,
            pattern=pattern_str,
            boundary_rules=boundary_rules,
            metadata=metadata,
        )
        patterns.append(sp)

    return patterns


class SpanCategorizerComponent:
    """Thin spaCy wrapper for CustomSpanCategorizer.

    Wraps CustomSpanCategorizer to use as a spaCy pipeline component
    (without @Language.factory decorator). Sets doc._.custom_spans
    attribute.

    Attributes:
        categorizer: CustomSpanCategorizer instance.

    Examples:
        >>> import spacy
        >>> nlp = spacy.blank("en")
        >>> patterns = [SpanPattern(category="skill", pattern=r"Python")]
        >>> cat = CustomSpanCategorizer(patterns)
        >>> comp = SpanCategorizerComponent(cat)
        >>> doc = nlp("I know Python")
        >>> doc = comp(doc)
        >>> print(doc._.custom_spans)
    """

    def __init__(self, categorizer: CustomSpanCategorizer) -> None:
        """Initialize component with categorizer.

        Args:
            categorizer: CustomSpanCategorizer instance.
        """
        self.categorizer = categorizer

    def __call__(self, doc: Doc) -> Doc:
        """Extract spans and attach to doc.

        Runs categorizer on doc.text and stores results as list of dicts
        (category, text, start_char, end_char, metadata) in doc._.custom_spans.

        Args:
            doc: spaCy Doc object.

        Returns:
            Doc with custom_spans attribute set.
        """
        spans = self.categorizer.categorize(doc.text)

        # Convert to list of dicts for serialization
        spans_list = [
            {
                "category": s.category,
                "text": s.text,
                "start_char": s.start_char,
                "end_char": s.end_char,
                "metadata": s.metadata,
            }
            for s in spans
        ]

        doc._.custom_spans = spans_list
        return doc


@Language.factory("custom_span_categorizer", default_config={"patterns_path": None})
def create_custom_span_categorizer_component(
    nlp: Language, name: str, patterns_path: str | None
) -> SpanCategorizerComponent:
    """Build a SpanCategorizerComponent from a JSON patterns file.

    Args:
        nlp: Owning spaCy pipeline (unused, required by factory protocol).
        name: Component name in the pipeline (unused).
        patterns_path: Path to patterns JSON (see load_patterns).

    Returns:
        SpanCategorizerComponent writing doc._.custom_spans.

    Raises:
        ValueError: If patterns_path is missing or None.
    """
    if not patterns_path:
        raise ValueError("custom_span_categorizer factory requires 'patterns_path' config")
    return SpanCategorizerComponent(CustomSpanCategorizer(load_patterns(patterns_path)))


__all__ = [
    "MAX_PATTERN_LENGTH",
    "MAX_TEXT_LENGTH",
    "validate_pattern",
    "CustomSpanCategorizer",
    "load_patterns",
    "SpanCategorizerComponent",
]
