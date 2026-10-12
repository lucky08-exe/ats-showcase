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
from typing import FrozenSet, List, Optional, Tuple

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

# Normalised form of the synthesized heading, used by Guard 5 to detect an existing EEO heading.
EEO_HEADING_NORMALIZED = "equal opportunity employer"

# EEO phrase triggers for Issue #374 (small, high-precision set)
# Matched case-insensitively in first ~200 chars of paragraph.
# Known limitation: "is an equal opportunity", "does not discriminate" and "affirmative action" are
# generic and can false-positive on non-EEO sentences, e.g. "This is an equal opportunity to grow
# your career." or "Our affirmative action plan is posted in the lobby."
# followed by a boilerplate paragraph ("Please contact HR.") is isolated under an EEO heading.
# Accepted for now; tightening the phrases would change detection behaviour, so it is not done here.
EEO_TRIGGERS: FrozenSet[str] = frozenset(
    [
        "equal opportunity employer",
        "equal employment opportunity",
        "is an equal opportunity",
        "are an equal opportunity",
        "does not discriminate",
        "affirmative action",
    ]
)

# Markdown heading prefix (Issue #374). Stripped before the known-heading check in Guard 4 so
# that a line already promoted to "## Benefits" by an earlier pass still matches "benefits".
HEADING_PREFIX_PATTERN = re.compile(r"^#{1,6}\s+")

# End of a sentence: sentence-ending punctuation followed by whitespace (Issue #374). An EEO
# paragraph is only a candidate when its trigger sits in this first sentence.
FIRST_SENTENCE_END_PATTERN = re.compile(r"[.!?](?=\s)")

# Sentence boundary used to examine every sentence after the first (Issue #374).
# Known limitation (accepted): this splits after abbreviations such as "U.S.", so "Acme is an equal
# opportunity employer. Applicants from the U.S. are welcome." is not isolated: the fragment
# "Applicants from the U.S." is not EEO-ish and blocks isolation.
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")

# DEI vocabulary that may follow an EEO sentence in the same paragraph (Issue #374).
# Known limitation: hand-picked DEI vocabulary, so a job sentence that contains "diversity"
# (e.g. "You will build diversity dashboards.") is treated as EEO-ish and does not block isolation.
EEO_CONTINUATION_PATTERN = re.compile(r"\b(diversity|diverse|inclusion|inclusive|belonging)\b", re.IGNORECASE)

# "without regard to" followed by a protected-class term within ~60 chars (Issue #374 Defect 3).
# A bare "on the basis of" lead-in is deliberately absent: job content such as "Pay is set on the
# basis of age and experience." or "Decisions are made on the basis of race conditions." would
# otherwise be read as an EEO statement.
# Protected-class terms, singular and plural: race(s), color(s), religion(s)/religious, sex(es),
# gender(s), national origin(s), age(s), disability/disabilities, veteran(s), sexual orientation(s),
# marital status(es), genetic(s).
PROTECTED_CLASS_PATTERN = re.compile(
    r"without regard to\s+.{0,60}?\b(races?|colors?|religions?|religious|sex(?:es)?|genders?|"
    r"national origins?|ages?|disabilit(?:y|ies)|veterans?|sexual orientations?|marital status(?:es)?|"
    r"genetics?)\b",
    re.IGNORECASE,
)

# Discrimination-disclaimer wording for a sentence after an EEO first sentence (Issue #374 round 6).
# "does not discriminate" is also an EEO trigger for the first sentence; this pattern additionally
# covers a first-person disclaimer ("We do not discriminate.", "We will not discriminate.") and a
# "do/does/will not discriminate" followed by "on", "against" or "based" (e.g. "Acme will not
# discriminate on the basis of race."), so that such a later sentence is EEO-ish and does not block
# isolation. "never" is deliberately absent: "Our ranking never discriminates against junior
# candidates." is job content. Known limitation: a first-person job sentence such as "We do not
# discriminate between file types." is still EEO-ish, and a third-person subject without a following
# on/against/based ("The tool will not discriminate between file types.") is job content.
DISCRIMINATE_PATTERN = re.compile(
    r"\b(?:(?:we|i)\s+(?:do|will)\s+not\s+discriminat\w*|"
    r"(?:do(?:es)?|will)\s+not\s+discriminat\w*\s+(?:on|against|based)\b)",
    re.IGNORECASE,
)

# "encouraged to apply" (Issue #374 round 6), e.g. "Women, minorities, veterans and individuals with
# disabilities are encouraged to apply." The phrase is generic, so it is accepted only as a sentence
# after an EEO first sentence. Known limitation: a generic "Candidates with 5+ years are encouraged
# to apply." sharing a paragraph with an EEO first sentence would be swept in; accepted.
ENCOURAGED_TO_APPLY_PATTERN = re.compile(r"encouraged to apply", re.IGNORECASE)

# ADA keyword and contact/email phrases, matched on word boundaries so that "ada" does not match
# "Canada" or "adapt" (Issue #374). The ADA token is case-sensitive so the language "Ada"
# ("Experience with Ada.") is not treated as boilerplate; all other alternatives are
# case-insensitive. Bare "contact" and "email" are deliberately absent: they also open
# ordinary sentences such as "Contact the hiring manager for role details.", which must not be
# treated as boilerplate. A bare "accommodation" is also absent: "Relocation accommodations are
# available for this role." is job content. Accommodation notices are matched by
# ACCOMMODATION_REQUEST_PATTERN and ACCOMMODATION_LABEL_PATTERN instead.
# Known limitation: bare "disability" and "by email" are still matched case-insensitively, so
# ordinary sentences containing them can be read as boilerplate.
BOILERPLATE_WORD_PATTERN = re.compile(
    r"\b(?:(?-i:ADA)|disability|contact\s+(?:us|hr)|email\s+(?:us|hr)|by\s+email)\b",
    re.IGNORECASE,
)

# Accommodation notices only: "accommodation(s)" followed by "on/upon/to request" within ~60 chars
# on the same sentence (e.g. "Accommodations are available on request."), or "request(ed)
# [a] [reasonable] accommodation(s)" (e.g. "Request reasonable accommodations here."). Business
# uses such as "Manage travel accommodation requests" are job content and do not match.
# Also "accommodation request(s) can/may/should/will be made|submitted|sent|directed" (e.g.
# "Accommodation requests can be made through HR."), "if/should you require ... accommodation(s)"
# (e.g. "If you require accommodation, let us know.") and a notice lead-in "applicants/candidates/
# individuals/persons/those who/whom require ... accommodation(s)" (e.g. "Applicants who require
# accommodation in the application process will be supported."). The lead-in is limited to people who
# apply, so job content such as "Engineers who require accommodations for travel." is not matched, and
# the bare "require ... accommodation(s)" wording is not matched either: "The role may require
# accommodations for travel." is job content.
# Known false positives (accepted): the "request(ed) [a] accommodation" alternative matches travel and
# booking wording such as "Request accommodation from the hiring manager." or "Request accommodations
# for travel.", and "accommodations ... to request" matches "Book accommodations to request approval.".
# "that" is not a lead-in: job wording such as "A role that requires accommodations for travel." is job content.
# These are pinned as isolated in test_travel_booking_accommodation_wording_is_boilerplate_known_limitation.
ACCOMMODATION_REQUEST_PATTERN = re.compile(
    r"\baccommodations?\b[^.!?]{0,60}\b(?:on|upon|to)\s+request\w*|"
    r"\brequest\w*\s+(?:a\s+)?(?:reasonable\s+)?accommodations?\b|"
    r"\baccommodations?\s+requests?\s+(?:can|may|should|will)\s+be\s+(?:made|submitted|sent|directed)\b|"
    r"\b(?:if\s+you\s+require|should\s+you\s+require)\b[^.!?]{0,80}?\baccommodations?\b|"
    r"\b(?:applicants|candidates|individuals|persons|those|anyone|people|someone|all)\s+(?:who|whom)\s+require\w*\b[^.!?]{0,80}?\baccommodations?\b",
    re.IGNORECASE,
)

# A paragraph that is only a bare "Accommodations" section label (optional trailing colon).
ACCOMMODATION_LABEL_PATTERN = re.compile(r"accommodations?:?", re.IGNORECASE)

# Multi-word boilerplate phrases, matched as plain substrings.
BOILERPLATE_PHRASES: Tuple[str, ...] = (
    "if you need",
    "reasonable accommodation",
    "please contact",
    "get in touch",
)


class HeadingPromoter(PipelineComponent):
    """Promote plain-text section headings to markdown format.

    Scans text line-by-line and converts lines matching known heading patterns
    to markdown section headers (## prefix). This enables structure recovery
    from plain-text job descriptions before the MarkdownSpanRuler parser runs.

    Also isolates trailing EEO paragraphs by inserting a synthesized heading
    before them (Issue #374). An EEO paragraph is a candidate if its first sentence
    contains an EEO trigger phrase (first ~200 characters), or "without regard to"
    followed by a protected-class term within ~60 characters (first ~400 characters).
    Every later sentence of the paragraph must also be EEO-ish: an EEO trigger, a
    protected-class pattern, a discrimination disclaimer (DISCRIMINATE_PATTERN),
    "encouraged to apply", DEI vocabulary, or empty/boilerplate wording. It is isolated
    only if every paragraph after it is empty, boilerplate (ADA/contact/accommodation
    notices), or another EEO paragraph.

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

        The output preserves existing lines; EEO isolation adds a heading and blank
        line; mixed line endings are normalized to the first one detected.
        Idempotent: a second pass over its own output yields the same text.

        Args:
            text: Input text (may be empty, contain CRLF, or Unicode).

        Returns:
            Text with promoted headings and isolated EEO paragraphs. If any error
            occurs, returns original text unchanged (non-fatal error handling).

        Example:
            >>> promoter = HeadingPromoter()
            >>> text = "Job Description\\n\\nWork with clients.\\n\\nRole Overview\\n\\nFocus on delivery."
            >>> result = promoter.process(text)
            >>> result
            '## Job Description\\n\\nWork with clients.\\n\\n## Role Overview\\n\\nFocus on delivery.'
        """
        original = text
        try:
            # Handle empty input
            if not text:
                return text

            # Normalise line endings to the first one detected (CRLF or LF) so that
            # mixed input produces uniform output. Everything below works on LF.
            first_newline = text.find("\n")
            line_ending = "\r\n" if first_newline > 0 and text[first_newline - 1] == "\r" else "\n"
            text = text.replace("\r\n", "\n")

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

            result = "\n".join(result_lines)
            if line_ending == "\r\n":
                result = result.replace("\n", "\r\n")
            return result

        except Exception as e:
            # Non-fatal: log and return original text
            logger.warning(f"Error in heading_promoter.process(): {e}")
            return original

    def _isolate_eeo_paragraphs(self, text: str) -> str:
        """Isolate trailing EEO paragraphs by inserting a synthesized heading.

        Detects EEO paragraphs and inserts ## Equal Opportunity Employer before them,
        but only if all paragraphs after the EEO paragraph are empty, boilerplate
        (ADA/contact/accommodation notices) or further EEO paragraphs. A paragraph is
        an EEO candidate when its first sentence has an EEO trigger or a "without regard
        to" protected-class phrase (see _is_eeo_paragraph). Each later sentence of the
        candidate is then checked on its own by _is_eeo_ish_sentence: a sentence that is
        job content makes the whole paragraph a non-EEO paragraph. Insert directly into
        original line list, preserving blank lines and line endings.

        Idempotent: repeated calls produce same result.

        Args:
            text: LF-normalised input text with possible EEO paragraphs (process() converts
                CRLF to LF before calling this method)

        Returns:
            Text with EEO paragraphs isolated under a heading if conditions are met
        """
        if not text:
            return text

        # Input is LF-normalised by process(); preserve original trailing newline status
        line_ending = "\n"
        has_trailing_newline = text.endswith(line_ending)

        lines = text.split(line_ending)
        paragraphs, para_starts = self._split_paragraphs_with_indices(lines)

        if len(paragraphs) < 2:
            # Need at least 2 paragraphs
            return text

        # Find first EEO paragraph such that everything after it is a trailing block
        # of boilerplate or further EEO paragraphs. Because the first qualifying EEO
        # paragraph is chosen, a run of EEO paragraphs is isolated at its first member.
        first_eeo_idx = -1
        for i in range(len(paragraphs)):
            if self._is_eeo_paragraph(paragraphs[i]):
                # Check if all paragraphs after this one are empty, boilerplate, or EEO
                all_trailing_ok = True
                for j in range(i + 1, len(paragraphs)):
                    if not (self._is_empty_or_boilerplate(paragraphs[j]) or self._is_eeo_paragraph(paragraphs[j])):
                        all_trailing_ok = False
                        break

                if all_trailing_ok:
                    first_eeo_idx = i
                    break

        if first_eeo_idx < 0:
            return text

        # Check guards before inserting synthetic heading
        eeo_para = paragraphs[first_eeo_idx]
        if not eeo_para:
            return text

        # Guard 1: the EEO paragraph's first line is already a markdown heading ("#" to "######",
        # e.g. promoted by an earlier pass). _is_eeo_paragraph ignores a leading heading marker when judging
        # candidacy, so such a paragraph can be selected; it is left unchanged rather than
        # headed twice.
        first_line_stripped = eeo_para[0].strip()
        if HEADING_PREFIX_PATTERN.match(first_line_stripped):
            return text

        # Guard 2 (silent skip): the EEO paragraph's first line is itself a known heading
        # phrase. Two shapes reach here: a standalone "Equal Opportunity Employer" line, which
        # matches the EEO trigger on its own; or a known heading followed by an EEO sentence in
        # the same paragraph (e.g. "Benefits" then "We are an equal opportunity employer."), where
        # the paragraph matches on the sentence, not on the heading line. Phase 2 promotes the
        # heading line to "## ...", so a synthetic heading would give two headings for one block.
        # Return unchanged; the outcome is plain promotion of the existing line.
        # Heading marker and emphasis characters are stripped first, as Guard 5 does, so that
        # "# Benefits", "__Benefits__" and "_Benefits_" are recognised as the known heading.
        heading_text = HEADING_PREFIX_PATTERN.sub("", first_line_stripped).strip("*_: ")
        normalized = self._normalize(heading_text)
        if normalized in self._headings:
            return text

        # Guard 3: Check if preceding paragraph ends with a heading
        if first_eeo_idx > 0:
            preceding_para = paragraphs[first_eeo_idx - 1]
            if preceding_para and HEADING_PREFIX_PATTERN.match(preceding_para[-1].strip()):
                return text

        # Guard 4 (silent skip): the paragraph immediately before the EEO paragraph starts
        # with a known heading phrase (e.g. "Benefits"). That block is a section in its own
        # right, and Phase 2 promotes its first line to "## ..." when it follows a blank
        # line. Intent: do not open a second synthetic section directly under it, so the
        # EEO sentence stays with the preceding known section. Return unchanged.
        # A leading "## " prefix from an earlier pass is stripped first so the check is
        # idempotent (Issue #374).
        if first_eeo_idx > 0:
            preceding_para = paragraphs[first_eeo_idx - 1]
            if preceding_para:
                preceding_first_line = HEADING_PREFIX_PATTERN.sub("", preceding_para[0].strip())
                preceding_normalized = self._normalize(preceding_first_line)
                if preceding_normalized in self._headings:
                    return text

        # Guard 5 (silent skip): an EEO heading already exists anywhere in the document, with a
        # "#" heading marker and/or "*" or "_" emphasis (e.g. a standalone "Equal Opportunity
        # Employer" line above, "**Equal Opportunity Employer**", or one promoted by an earlier
        # pass). Inserting another would duplicate that heading.
        for line in lines:
            if self._normalize(line.strip().strip("#*_: ")) == EEO_HEADING_NORMALIZED:
                return text

        # Insert heading before the first EEO paragraph's first line
        insert_line_idx = para_starts[first_eeo_idx]

        # Build result with inserted lines
        result_lines = list(lines)
        # Insert heading and blank line before EEO paragraph at its start index
        result_lines.insert(insert_line_idx, "## Equal Opportunity Employer")
        result_lines.insert(insert_line_idx + 1, "")

        # Reconstruct, preserving original trailing newline status
        result = line_ending.join(result_lines)
        if not has_trailing_newline and result.endswith(line_ending):
            result = result[: -len(line_ending)]
        elif has_trailing_newline and not result.endswith(line_ending):
            result = result + line_ending
        return result

    def _split_paragraphs_with_indices(self, lines: List[str]) -> Tuple[List[List[str]], List[int]]:
        """Split lines into paragraphs, tracking each paragraph's start index.

        Args:
            lines: List of text lines

        Returns:
            Tuple of (paragraphs, start_indices) where start_indices[i] is the
            line index where paragraphs[i] starts in the original lines list
        """
        paragraphs: List[List[str]] = []
        start_indices: List[int] = []
        current_para: List[str] = []
        para_start = 0

        for i, line in enumerate(lines):
            if not line.strip():
                if current_para:
                    paragraphs.append(current_para)
                    start_indices.append(para_start)
                    current_para = []
            else:
                if not current_para:
                    para_start = i
                current_para.append(line)

        if current_para:
            paragraphs.append(current_para)
            start_indices.append(para_start)

        return paragraphs, start_indices

    def _is_eeo_paragraph(self, para: List[str]) -> bool:
        """Check if a paragraph is an EEO paragraph.

        Checks if the paragraph's first sentence (first ~200 chars) matches an EEO trigger
        phrase, or a protected-class pattern within its first ~400 chars. Must not be a
        bullet, table or list line. A leading "#{1,6} " heading marker and trailing ':' on
        the first line are ignored, so a paragraph gives the same answer before and after
        Phase 2 promotes its first line (idempotence, Issue #374).

        Args:
            para: Paragraph as list of lines

        Returns:
            True if paragraph is an EEO paragraph
        """
        if not para:
            return False

        first_line = HEADING_PREFIX_PATTERN.sub("", para[0].strip()).rstrip(":").strip()

        # Must not be a bullet, table or list line
        if not first_line or first_line[0] in "#*-+|" or first_line[0].isdigit():
            return False

        # Combine paragraph text for matching
        para_text = " ".join([first_line] + [line.strip() for line in para[1:]])
        # Only the first sentence is searched, so an EEO sentence after job content is not
        # isolated together with that content (Issue #374).
        first_sentence = self._first_sentence(para_text)
        check_text = first_sentence[:200].casefold()

        # Check simple triggers, then "without regard to" with protected class pattern
        triggered = any(trigger in check_text for trigger in EEO_TRIGGERS) or bool(
            PROTECTED_CLASS_PATTERN.search(first_sentence[:400])
        )
        if not triggered:
            return False

        # A paragraph whose later sentences are job content is not an EEO paragraph (Issue #374).
        # Only the sentences after the first are checked; the first one has already passed.
        for sentence in _SENTENCE_SPLIT_PATTERN.split(para_text)[1:]:
            if not self._is_eeo_ish_sentence(sentence):
                return False

        return True

    def _is_eeo_ish_sentence(self, sentence: str) -> bool:
        """Check if a sentence after an EEO trigger is EEO, DEI or boilerplate wording.

        The sentence is EEO-ish if any of these branches matches, checked in this order:
        1. EEO_TRIGGERS: a substring of EEO_TRIGGERS (casefolded) appears in the sentence.
        2. PROTECTED_CLASS_PATTERN: "without regard to" followed by a protected-class term.
        3. DISCRIMINATE_PATTERN: a first-person, or on/against/based, discrimination disclaimer.
        4. ENCOURAGED_TO_APPLY_PATTERN: "encouraged to apply".
        5. EEO_CONTINUATION_PATTERN: DEI vocabulary (diversity, inclusion, belonging, ...).
        6. Boilerplate fallback: the sentence is empty or _is_empty_or_boilerplate is True.

        Args:
            sentence: One sentence of a paragraph

        Returns:
            True if any branch above matches, otherwise False (job content)
        """
        casefolded = sentence.casefold()
        if any(trigger in casefolded for trigger in EEO_TRIGGERS):
            return True
        if PROTECTED_CLASS_PATTERN.search(sentence):
            return True
        if DISCRIMINATE_PATTERN.search(sentence) or ENCOURAGED_TO_APPLY_PATTERN.search(sentence):
            return True
        if EEO_CONTINUATION_PATTERN.search(sentence):
            return True
        return self._is_empty_or_boilerplate([sentence])

    @staticmethod
    def _first_sentence(text: str) -> str:
        """Return the text up to and including the first sentence-ending punctuation.

        Args:
            text: Single-line paragraph text

        Returns:
            The first sentence, or the whole text if no sentence end is found
        """
        match = FIRST_SENTENCE_END_PATTERN.search(text)
        return text[: match.end()] if match else text

    def _is_empty_or_boilerplate(self, para: List[str]) -> bool:
        """Check if paragraph is empty or boilerplate (ADA/contact/accommodation).

        Boilerplate patterns: disability, ADA (uppercase only), contact us/hr, email us/hr,
        by email (whole words); accommodation with a request phrase; a bare "Accommodations"
        label; plus the phrases "if you need", "please contact", "reasonable accommodation"
        and "get in touch". A bare "accommodation" in job content is not boilerplate.

        Args:
            para: Paragraph as list of lines

        Returns:
            True if paragraph is empty or boilerplate
        """
        if not para:
            return True

        text = " ".join(line.strip() for line in para).strip()
        if not text:
            return True

        if BOILERPLATE_WORD_PATTERN.search(text):
            return True

        # Strip a markdown heading marker and emphasis so "## Accommodations", "**Accommodations**"
        # and "_Accommodations_" count as a bare label (Issue #374).
        label_text = HEADING_PREFIX_PATTERN.sub("", text).strip().strip("*_: ")
        if ACCOMMODATION_REQUEST_PATTERN.search(text) or ACCOMMODATION_LABEL_PATTERN.fullmatch(label_text):
            return True

        text_lower = text.lower()
        return any(phrase in text_lower for phrase in BOILERPLATE_PHRASES)

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
