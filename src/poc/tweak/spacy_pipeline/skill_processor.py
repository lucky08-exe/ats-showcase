"""Skill extraction processor for spaCy pipeline.

Implements pattern-based skill detection using spaCy Matcher with action verb lemmas
and noun-led fallback for bullet-point skills (Issue #372).

Extracts skills from SKILLS section type only (B2 decision - Issue #321).

Processes spaCy Doc with classified sections (doc._.classified_sections) and
extracts skills into doc._.skills extension.

Classes:
    SkillProcessor: spaCy pipeline component for skill extraction

Usage:
    >>> import spacy
    >>> from src.poc.tweak.spacy_pipeline import SkillProcessor
    >>>
    >>> nlp = spacy.load("en_core_web_md")
    >>> processor = SkillProcessor(nlp, "skill_processor")
    >>> nlp.add_pipe("skill_processor", last=True)
    >>>
    >>> doc = nlp("Building scalable architectures with Python")
    >>> doc._.skills
    [{"skill": "building scalable architectures", "confidence": 1.0}]

Issue #321: Implement skill processor for batch pipeline.
Issue #372: Add noun-led fallback for bullet-point skills.
"""

import logging
import re
from typing import Any, Dict, List, Set

from spacy.language import Language
from spacy.matcher import Matcher
from spacy.tokens import Doc
from spacy.util import filter_spans

from src.poc.tweak.patterns import SectionType
from src.poc.tweak.spacy_pipeline.patterns import QUALIFIER_STOPLIST, SKILL_VERBS, TECH_TERMS

logger = logging.getLogger(__name__)


class SkillProcessor:
    """spaCy pipeline component for skill extraction.

    Reads classified sections from doc._.classified_sections and extracts
    skills from sections classified as SKILLS type only.

    Uses spaCy Matcher with action verb lemmas to identify skill phrases.
    Falls back to noun-led extraction for bullet-point skills when verb
    matcher yields no results (Issue #372).

    Attributes:
        nlp: spaCy Language object
        _name: Component identifier for logging
        matcher: spaCy Matcher instance for skill pattern matching
    """

    def __init__(self, nlp: Language, name: str, min_confidence: float = 0.70) -> None:
        """Initialize SkillProcessor.

        Creates Matcher pattern for skill detection and registers doc._.skills
        extension if not already present.

        Args:
            nlp: spaCy Language object (required by factory pattern)
            name: Component name for logging (typically 'skill_processor')
            min_confidence: Minimum confidence threshold for SKILLS classification
                (Issue #347). Default 0.70. See __call__ for threshold logic.

        Raises:
            ValueError: If name is None or empty
        """
        if not name:
            raise ValueError("Component name cannot be None or empty")

        self.nlp = nlp
        self._name = name
        self.min_confidence = min_confidence
        self.matcher = Matcher(nlp.vocab)

        # Define the Matcher Pattern
        # Logic: [Action Verb] + [Optional Preposition/Article] + [Descriptive Nouns/Adjectives]
        pattern = [
            # The Action: Must be a verb and its base form must be in our list
            {"POS": "VERB", "LEMMA": {"IN": SKILL_VERBS}},
            # Optional: Connector words like "with", "the", "of"
            # (e.g., "partner WITH", "lead THE")
            {"POS": {"IN": ["ADP", "DET", "PART"]}, "OP": "?"},
            # The Meat: A sequence of Nouns, Adjectives, Proper Nouns, or Verbs
            # (e.g., "novel deep learning architectures", "distributed teams")
            # Note: VERB included for past participles (e.g., "distributed") tagged by spaCy
            # as VERB instead of ADJ. ADP excluded (prepositions shouldn't appear as descriptors)
            {"POS": {"IN": ["ADJ", "NOUN", "PROPN", "VERB"]}, "OP": "+"},
        ]

        # Add pattern to matcher
        self.matcher.add("SKILL_PHRASE", [pattern])

        # Register Doc extension for skills if not present
        if not Doc.has_extension("skills"):
            Doc.set_extension("skills", default=[])

    def _is_title_echo(self, line: str, section_title: str) -> bool:
        """Check if line merely echoes the section title (e.g., 'Technical Skills').

        Args:
            line: The line to check
            section_title: The section title

        Returns:
            True if line appears to be an echo of the title
        """
        if not section_title:
            return False
        line_lower = line.lower().strip()
        title_lower = section_title.lower().strip()
        # Check for exact match or match without trailing punctuation
        return line_lower == title_lower or line_lower == title_lower.rstrip(":")

    def _strip_bullet_marker(self, line: str) -> str:
        """Strip leading bullet markers (-, *, •, numbered 1.).

        Args:
            line: The line to process

        Returns:
            Line with bullet marker removed
        """
        # Remove leading whitespace first
        line = line.lstrip()
        # Match bullet markers: -, *, •, or numbered (1. 2. etc)
        line = re.sub(r"^[-*•]\s*", "", line)
        line = re.sub(r"^\d+\.\s*", "", line)
        return line

    def _is_colon_terminated_header(self, line: str) -> bool:
        """Check if line is a colon-terminated header (e.g., 'Skills:').

        Args:
            line: The line to check

        Returns:
            True if line ends with ':' and contains only alphanumeric/spaces before it
        """
        stripped = line.strip()
        if not stripped.endswith(":"):
            return False
        # Check if before the colon, there are only word characters and spaces
        before_colon = stripped[:-1].strip()
        return bool(re.match(r"^[\w\s]+$", before_colon))

    def _split_skill_items(self, text: str) -> List[str]:
        """Split text on delimiter characters (comma, semicolon, forward slash, 'and').

        Args:
            text: The text to split

        Returns:
            List of skill items
        """
        # Replace ' and ' with a delimiter
        text = re.sub(r"\s+and\s+", ",", text, flags=re.IGNORECASE)
        # Split on comma, semicolon, or forward slash
        items = re.split(r"[,;/]", text)
        # Strip whitespace from each item
        return [item.strip() for item in items if item.strip()]

    def _strip_trailing_qualifiers(self, text: str) -> str:
        """Strip trailing qualifier words (required, preferred, experience, etc).

        Args:
            text: The text to process

        Returns:
            Text with trailing qualifiers removed
        """
        words = text.split()
        if not words:
            return ""

        # Check if last word (or last two words for 'a plus') is in stoplist
        while words:
            last_word = words[-1].lower().rstrip(".,;:")
            # Check for "a plus" pattern
            if len(words) >= 2:
                last_two = " ".join(words[-2:]).lower().rstrip(".,;:")
                if last_two in QUALIFIER_STOPLIST:
                    words = words[:-2]
                    continue
            # Check single word
            if last_word in QUALIFIER_STOPLIST:
                words.pop()
            else:
                break

        return " ".join(words)

    def _has_whole_token_tech_term(self, doc: Any) -> bool:
        """Check if doc contains any whole-token TECH_TERMS or special tokens.

        Uses whole-token matching: tokenizes chunk and compares actual tokens
        against TECH_TERMS (with word boundaries for multi-word terms).

        Args:
            doc: spaCy Doc to check (must be pre-parsed)

        Returns:
            True if chunk contains a tech term or special token
        """
        # Special tokens (exact matches after lowercasing)
        special_tokens = {"c++", "c#", "sql"}

        # Build a set of lowercased tokens from the doc
        doc_tokens_lower = {token.text.lower() for token in doc}

        # Check special tokens (exact match)
        if doc_tokens_lower & special_tokens:
            return True

        # Check TECH_TERMS with word-boundary logic
        # For single-word TECH_TERMS, check exact token match
        # For multi-word TECH_TERMS, check if consecutive tokens match the phrase
        for tech_term in TECH_TERMS:
            tech_lower = tech_term.lower()
            # Single-word term: check if any token matches
            if " " not in tech_term:
                if tech_lower in doc_tokens_lower:
                    return True
            else:
                # Multi-word term: check if phrase appears in doc
                # Reconstruct the text and check if phrase is present as words
                doc_text = " ".join(token.text.lower() for token in doc)
                # Use word boundaries to avoid substring matches
                pattern = r"\b" + re.escape(tech_lower) + r"\b"
                if re.search(pattern, doc_text):
                    return True

        return False

    def _is_tech_token(self, token: Any) -> bool:
        """Check if a token is a recognized tech term.

        Args:
            token: spaCy token

        Returns:
            True if token is a tech term
        """
        special_tokens = {"c++", "c#", "sql"}
        token_lower = token.text.lower()

        # Check special tokens
        if token_lower in special_tokens:
            return True

        # Check TECH_TERMS
        if token_lower in TECH_TERMS:
            return True

        return False

    def _is_valid_skill_chunk(self, chunk_text: str) -> bool:
        """Validate a skill chunk against noise filters.

        Args:
            chunk_text: The chunk to validate

        Returns:
            True if chunk passes all filters
        """
        # Strip whitespace
        chunk_text = chunk_text.strip()
        if not chunk_text:
            return False

        # Parse with spaCy once
        try:
            chunk_doc = self.nlp(chunk_text)
        except Exception:
            # If spaCy parsing fails, reject
            return False

        # Check token count (max 6)
        if len(chunk_doc) > 6:
            return False

        # Drop stopword-only and qualifier-only chunks
        chunk_lower = chunk_text.lower()
        if chunk_lower in QUALIFIER_STOPLIST:
            return False

        # Check for NOUN/PROPN/X tokens
        has_noun_propn_x = any(token.pos_ in ("NOUN", "PROPN", "X") for token in chunk_doc)

        # Per-token rule: reject chunk if any VERB/AUX/PRON token
        # is not a tech term (e.g., reject "going forward", allow "Go")
        for token in chunk_doc:
            if token.pos_ in ("VERB", "AUX", "PRON"):
                if not self._is_tech_token(token):
                    return False

        # Check for whole-token tech terms
        has_tech_term = self._has_whole_token_tech_term(chunk_doc)

        # Must have either NOUN/PROPN/X or a tech term
        if not has_noun_propn_x and not has_tech_term:
            return False

        return True

    def _extract_noun_led_skills(self, line: str, section_title: str) -> List[str]:
        """Extract skills from a line using noun-led fallback strategy.

        Args:
            line: The line to process
            section_title: The section title (for title echo detection)

        Returns:
            List of skill strings
        """
        # Skip if line is a title echo
        if self._is_title_echo(line, section_title):
            return []

        # Strip leading bullet marker
        line = self._strip_bullet_marker(line)

        # Skip colon-terminated headers (they yield nothing)
        if self._is_colon_terminated_header(line):
            return []

        line = line.strip()
        if not line:
            return []

        # Split on delimiters
        items = self._split_skill_items(line)

        skills = []
        for item in items:
            # Strip trailing qualifiers
            item = self._strip_trailing_qualifiers(item)
            item = item.strip()

            # Validate chunk
            if self._is_valid_skill_chunk(item):
                skills.append(item.lower())

        return skills

    def __call__(self, doc: Doc) -> Doc:
        """Process a spaCy Doc and extract skills.

        Reads doc._.classified_sections and extracts skills from sections
        classified as SKILLS type only.

        Only section content lines are candidates; section titles and literal
        "#" heading lines are never extracted (Issue #375).

        For each line:
        1. First attempts verb-led extraction using Matcher
        2. If verb Matcher yields no spans, falls back to noun-led extraction
           (Issue #372) from bullet-point formatted skills

        Returns dict list: [{"skill": str, "confidence": 1.0}, ...]

        Handles edge cases gracefully:
        - If doc._.classified_sections is None: treats as empty list
        - If doc._.classified_sections is empty: doc._.skills = []
        - Extraction errors are logged but do not halt processing

        Args:
            doc: spaCy Doc to process

        Returns:
            Modified doc with doc._.skills populated

        Raises:
            TypeError: If doc is not a spaCy Doc
        """
        # Get classified sections from doc extension (handle None/missing gracefully)
        classified_sections = doc._.classified_sections if doc._.classified_sections else []

        # Extract skills from sections
        skills: List[Dict[str, Any]] = []
        seen_skills: Set[str] = set()  # Deduplicate skills

        for section, classification in classified_sections:
            try:
                # Filter to SKILLS section type only (B2 decision)
                if SectionType.SKILLS not in classification.labels:
                    continue

                # Confidence gate (Issue #347). If all_types is empty/absent,
                # fall back to labels-only behavior above (backward compatible).
                all_types = getattr(classification, "all_types", None)
                if all_types:
                    top_type = all_types[0]
                    if top_type.section_type == SectionType.SKILLS:
                        skills_confidence = top_type.confidence
                    else:
                        # SKILLS+TECHNOLOGIES overlap (e.g. "Technical Stack" section
                        # classified TECHNOLOGIES (0.85) / SKILLS (0.72)): unlike
                        # RequirementProcessor's top-ranked-only rule, extraction here
                        # keys off SKILLS' own confidence, scanned from all_types,
                        # even when SKILLS isn't the #1-ranked type.
                        skills_entry = next(
                            (tc for tc in all_types if tc.section_type == SectionType.SKILLS),
                            None,
                        )
                        skills_confidence = skills_entry.confidence if skills_entry else None

                    if skills_confidence is not None and skills_confidence < self.min_confidence:
                        logger.info(
                            f"Skipping SKILLS extraction: confidence {skills_confidence:.2f} "
                            f"< threshold {self.min_confidence:.2f}"
                        )
                        continue

                # Only content lines are candidate text (Issue #354, Issue #375).
                # Section titles are headings by construction and are never treated as
                # skill-bearing text; the title is still used for title-echo detection below.
                text_lines = []
                if section.content:
                    text_lines.extend(section.content.splitlines())

                if not text_lines:
                    continue

                # Process each line separately through spaCy
                for line in text_lines:
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue

                    # Skip literal markdown heading lines such as "## Technical Skills"
                    # so heading text never reaches the Matcher or noun-led fallback (Issue #375)
                    if line_stripped.startswith("#"):
                        continue

                    try:
                        skill_doc = self.nlp(line_stripped)
                    except Exception as e:
                        logger.error(f"Failed to process skills line: {e}")
                        continue

                    # Find matches using verb-led matcher
                    try:
                        matches = self.matcher(skill_doc, as_spans=True)

                        # Filter overlapping spans
                        unique_spans = filter_spans(matches)

                        # Extract skill text, normalize, and deduplicate
                        for span in unique_spans:
                            skill_text = span.text.strip().lower()
                            if skill_text and skill_text not in seen_skills:
                                skills.append({"skill": skill_text, "confidence": 1.0})
                                seen_skills.add(skill_text)

                    except Exception as e:
                        logger.error(
                            f"Matcher extraction failed for section '{section.title}', line '{line_stripped}': {e}"
                        )
                        continue

                    # If verb-led extraction yielded no spans, try noun-led fallback
                    if not unique_spans:
                        try:
                            noun_led_skills = self._extract_noun_led_skills(line_stripped, section.title or "")
                            for skill_text in noun_led_skills:
                                if skill_text and skill_text not in seen_skills:
                                    skills.append({"skill": skill_text, "confidence": 1.0})
                                    seen_skills.add(skill_text)
                        except Exception as e:
                            logger.error(
                                f"Noun-led extraction failed for section '{section.title}', line '{line_stripped}': {e}"
                            )
                            continue

            except Exception as e:
                logger.error(f"Error extracting skills from section '{section.title}': {e}")
                # Continue with next section
                continue

        # Store extracted skills in doc extension
        doc._.skills = skills

        return doc

    @property
    def name(self) -> str:
        """Component name for logging and identification."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Allow spaCy to set component name."""
        if not value:
            raise ValueError("Component name cannot be None or empty")
        self._name = value
