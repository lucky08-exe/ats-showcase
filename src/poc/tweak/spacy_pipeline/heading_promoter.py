"""Plain-text heading promotion to markdown section headers.

Promotes plain-text lines that match known job description heading patterns
to markdown section headers (## prefix), enabling MarkdownSpanRuler to
recognize section boundaries in unstructured job descriptions.

Rules for promotion:
- Line must be non-empty after stripping whitespace
- Line must not start with markdown markers (#, *, -, +) or list indicators (digits + .)
- Line must not be already formatted (bold **, italic *, or table |)
- Previous line must be blank OR this is the first line of the document
- Normalised line (casefold, apostrophe normalisation, collapse spaces, strip trailing ':')
  must match a known heading phrase from KNOWN_PLAIN_HEADINGS (exact match)
- Promotion is idempotent: already-promoted lines (starting with ##) are not re-promoted

Also isolates trailing EEO (Equal Opportunity Employer) paragraphs by inserting
a synthesized ## Equal Opportunity Employer heading before them (Issue #374).

Example:
    >>> promoter = HeadingPromoter()
    >>> text = "Job Description\\nRequirements below.\\nRole Overview\\nFocus areas."
    >>> result = promoter.process(text)
    >>> "## Job Description" in result
    True
    >>> "## Role Overview" in result
    True

The promoter is designed to be non-fatal; if any error occurs during processing,
the original text is returned unchanged.
"""

import logging
import re
from typing import FrozenSet, List, Optional

from src.poc.tweak.spacy_pipeline.base import PipelineComponent

logger = logging.getLogger(__name__)

# 64-phrase base set + 2 live-job-seen extras (Issue #365).
# All phrases pass consistency test: classify as non-'other' type via SectionClassifier.
# Derived from architect's 74-phrase draft minus 10 'other' phrases (duties, education,
# eeo statement, equal employment opportunity, job duties, must have, nice to have,
# the role, who we are, who you are).
# Extras: "in this role you will" (RESPONSIBILITIES), "what will make you succeed" (QUALIFICATIONS).
KNOWN_PLAIN_HEADINGS: FrozenSet[str] = frozenset(
    [
        "ability",
        "about",
        "about the position",
        "about the role",
        "about this opportunity",
        "about this position",
        "about this role",
        "about us",
        "about you",
        "basic qualifications",
        "benefits",
        "compensation",
        "core competencies",
        "core skills",
        "day to day responsibilities",
        "description",
        "desired qualifications",
        "duty",
        "equal opportunity employer",
        "essential",
        "essential functions",
        "essential qualifications",
        "essential requirements",
        "experience",
        "expertise",
        "how to apply",
        "in this role you will",
        "job description",
        "job overview",
        "job responsibilities",
        "key responsibilities",
        "knowledge",
        "minimum qualifications",
        "minimum requirements",
        "organization overview",
        "overview",
        "physical requirements",
        "position description",
        "position overview",
        "preferred qualifications",
        "preferred requirements",
        "preferred skills",
        "qualifications",
        "required experience",
        "required qualifications",
        "required skills",
        "requirement",
        "requirements",
        "responsibilities",
        "role description",
        "role overview",
        "role responsibilities",
        "salary",
        "skill",
        "skills",
        "summary",
        "technical",
        "technical knowledge",
        "technical skills",
        "travel requirements",
        "what will make you succeed",
        "what you bring",
        "what you will bring",
        "what you will do",
        "work location",
        "working conditions",
    ]
)

# EEO phrase triggers for Issue #374 (small, high-precision set)
# Matched case-insensitively in first ~200 chars of paragraph, anchored to start
EEO_TRIGGERS: FrozenSet[str] = frozenset(
    [
        "equal opportunity employer",
        "equal employment opportunity",
        "is an equal opportunity",
        "are an equal opportunity",
        "does not discriminate",
        "without regard to",
        "affirmative action",
    ]
)


class HeadingPromoter(PipelineComponent):
    """Promote plain-text section headings to markdown format.

    Scans text line-by-line and converts lines matching known heading patterns
    to markdown section headers (## prefix). This enables structure recovery
    from plain-text job descriptions before the MarkdownSpanRuler parser runs.

    Also isolates trailing EEO paragraphs by inserting a synthesized heading
    before them (Issue #374). An EEO paragraph is detected if its text matches
    an EEO trigger phrase in the first ~200 characters, and if all paragraphs
    after it are empty or other boilerplate (nothing substantive follows).

    Attributes:
        headings: Frozenset of allowed heading phrases (lowercase, no trailing ':').
                  Defaults to KNOWN_PLAIN_HEADINGS.
    """

    def __init__(self, headings: Optional[FrozenSet[str]] = None) -> None:
        """Initialize the promoter with an optional custom heading set.

        Args:
            headings: Custom frozenset of heading phrases. If None, uses KNOWN_PLAIN_HEADINGS.
        """
        self._headings = headings if headings is not None else KNOWN_PLAIN_HEADINGS

    @property
    def name(self) -> str:
        """Return the component name for logging."""
        return "heading_promoter"

    def process(self, text: str) -> str:
        """Promote plain-text headings to markdown section headers and isolate EEO.

        Processes text in two phases:
        1. Detect and isolate trailing EEO paragraphs by inserting a synthesized
           ## Equal Opportunity Employer heading before them.
        2. Promote plain-text lines matching known heading patterns to ## format.

        The conversion preserves line structure and is idempotent (processing
        twice produces same output).

        Args:
            text: Input text (may be empty, contain CRLF, or Unicode).

        Returns:
            Text with promoted headings and isolated EEO paragraphs. If any error
            occurs, returns original text unchanged (non-fatal error handling).

        Example:
            >>> promoter = HeadingPromoter()
            >>> text = "Job Description\\nWork with clients.\\nRole Overview\\nFocus on delivery."
            >>> result = promoter.process(text)
            >>> result
            '## Job Description\\nWork with clients.\\n## Role Overview\\nFocus on delivery.'
        """
        try:
            # Handle empty input
            if not text:
                return text

            # Phase 1: Isolate trailing EEO paragraphs
            text = self._isolate_eeo_paragraphs(text)

            # Phase 2: Promote plain-text headings
            lines = text.split("\n")
            result_lines = []

            for i, line in enumerate(lines):
                stripped = line.strip()

                # Check if line should be promoted
                if self._should_promote(stripped, i == 0, i > 0 and not lines[i - 1].strip()):
                    # Normalize and check against known headings
                    normalized = self._normalize(stripped)
                    if normalized in self._headings:
                        # Promote: preserve leading/trailing whitespace from original line
                        # Extract the part of the line that should become the heading
                        promoted = "## " + stripped.rstrip(":").strip()
                        result_lines.append(promoted)
                    else:
                        result_lines.append(line)
                else:
                    result_lines.append(line)

            return "\n".join(result_lines)

        except Exception as e:
            # Non-fatal: log and return original text
            logger.warning(f"Error in heading_promoter.process(): {e}")
            return text

    def _isolate_eeo_paragraphs(self, text: str) -> str:
        """Isolate trailing EEO paragraphs by inserting a synthesized heading.

        Detects EEO paragraphs (blank-line separated blocks that match EEO trigger
        phrases in their first ~200 chars) and inserts ## Equal Opportunity Employer
        before them, but only if the paragraph is truly trailing (no real sections follow).

        Idempotent: repeated calls produce same result.

        Args:
            text: Input text with possible EEO paragraphs

        Returns:
            Text with EEO paragraphs isolated under a heading if conditions are met
        """
        if not text:
            return text

        lines = text.split("\n")
        paragraphs = self._split_paragraphs(lines)

        if len(paragraphs) < 2:
            # Need at least 2 paragraphs to have meaningful trailing EEO
            return text

        # Find last real (non-EEO) content
        last_real_idx = -1
        for i in range(len(paragraphs) - 1, -1, -1):
            if self._has_real_content(paragraphs[i]) and not self._is_eeo_paragraph(paragraphs[i]):
                last_real_idx = i
                break

        if last_real_idx >= len(paragraphs) - 1:
            # No trailing EEO (last content is real content, not EEO)
            return text

        # Find first EEO after last real content
        first_eeo_idx = -1
        for i in range(last_real_idx + 1, len(paragraphs)):
            if self._is_eeo_paragraph(paragraphs[i]):
                first_eeo_idx = i
                break
            elif self._has_real_content(paragraphs[i]):
                # Found real section after potential EEO, not trailing
                return text

        if first_eeo_idx < 0:
            return text

        # Check guards before inserting synthetic heading
        eeo_para = paragraphs[first_eeo_idx]
        if not eeo_para:
            return text

        # Guard 1: First line should not already be a heading
        first_line_stripped = eeo_para[0].strip()
        if first_line_stripped.startswith("##"):
            return text

        # Guard 2: First line should not be a known heading (else it will be promoted anyway)
        normalized = self._normalize(first_line_stripped)
        if normalized in self._headings:
            return text

        # Guard 3: Check if preceding paragraph ends with a heading
        if first_eeo_idx > 0:
            preceding_para = paragraphs[first_eeo_idx - 1]
            if preceding_para and preceding_para[-1].strip().startswith("##"):
                return text

        # Reconstruct with heading inserted before first EEO paragraph
        result_lines: List[str] = []
        for i, para in enumerate(paragraphs):
            if i == first_eeo_idx:
                # Insert EEO heading before this paragraph
                result_lines.append("## Equal Opportunity Employer")
                result_lines.append("")  # Blank line after heading

            result_lines.extend(para)
            if i < len(paragraphs) - 1:
                result_lines.append("")  # Blank line between paragraphs

        return "\n".join(result_lines)

    def _split_paragraphs(self, lines: List[str]) -> List[List[str]]:
        """Split lines into paragraphs (blank-line separated blocks).

        Args:
            lines: List of text lines

        Returns:
            List of paragraphs, each a list of lines
        """
        paragraphs: List[List[str]] = []
        current_para: List[str] = []

        for line in lines:
            if not line.strip():
                if current_para:
                    paragraphs.append(current_para)
                    current_para = []
            else:
                current_para.append(line)

        if current_para:
            paragraphs.append(current_para)

        return paragraphs

    def _is_eeo_paragraph(self, para: List[str]) -> bool:
        """Check if a paragraph is an EEO paragraph.

        Checks if the paragraph's text (first ~200 chars) matches an EEO trigger
        phrase. Must not be a bullet or heading line.

        Args:
            para: Paragraph as list of lines

        Returns:
            True if paragraph is an EEO paragraph
        """
        if not para:
            return False

        first_line = para[0].strip()

        # Must not be a bullet or heading
        if not first_line or first_line[0] in "#*-+|" or first_line[0].isdigit():
            return False

        # Combine paragraph text for matching
        para_text = " ".join(line.strip() for line in para)

        # Check first ~200 chars against EEO triggers
        check_text = para_text[:200].casefold()

        for trigger in EEO_TRIGGERS:
            if trigger in check_text:
                return True

        return False

    def _has_real_content(self, para: List[str]) -> bool:
        """Check if a paragraph has real (non-empty) content.

        Args:
            para: Paragraph as list of lines

        Returns:
            True if paragraph has content
        """
        if not para:
            return False

        text = " ".join(line.strip() for line in para).strip()
        return bool(text)

    def _should_promote(self, stripped_line: str, is_first: bool, prev_blank: bool) -> bool:
        """Check if a line is eligible for promotion (before checking against phrase set).

        Args:
            stripped_line: The line after calling .strip()
            is_first: True if this is the first line of the document
            prev_blank: True if the previous line was blank or first line

        Returns:
            True if the line passes structural checks (not already formatted, correct position)
        """
        # Empty lines cannot be promoted
        if not stripped_line:
            return False

        # Must not start with markdown/list markers
        if stripped_line[0] in "#*-+|":
            return False

        # Must not start with digit (list indicator like "1. ", "2. ")
        if stripped_line[0].isdigit():
            return False

        # Must not be already formatted as bold (**...**)
        if stripped_line.startswith("**") and stripped_line.endswith("**"):
            return False

        # Must not contain list-like patterns (digit followed by . or ))
        if re.match(r"^\d+[\.\)]", stripped_line):
            return False

        # Previous line must be blank or this is first line
        if not (is_first or prev_blank):
            return False

        return True

    def _normalize(self, text: str) -> str:
        """Normalize text for comparison against known headings.

        Transformations:
        - Convert to lowercase (casefold for Unicode)
        - Normalize apostrophes (' and ' both become ')
        - Collapse multiple spaces to single space
        - Strip trailing ':' and whitespace
        - Strip leading/trailing whitespace

        Args:
            text: Raw text from the line

        Returns:
            Normalised text suitable for set membership testing
        """
        # Lowercase
        text = text.casefold()

        # Normalise apostrophes (both straight ' and curly ')
        text = text.replace("'", "'").replace("'", "'")

        # Collapse multiple spaces
        text = " ".join(text.split())

        # Strip trailing colon and whitespace
        text = text.rstrip(":").strip()

        return text
