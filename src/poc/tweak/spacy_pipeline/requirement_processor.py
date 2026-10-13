"""Requirement extraction processor for spaCy pipeline.

Implements pattern-based requirement detection with confidence scoring,
negation detection, and context adjustments. Extracts requirements from
QUALIFICATIONS section type only (B2 decision - Issue #321).

Processes spaCy Doc with classified sections (doc._.classified_sections)
and extracts requirements into doc._.requirements extension.

Classes:
    RequirementProcessor: spaCy pipeline component for requirement extraction

Usage:
    >>> import spacy
    >>> from src.poc.tweak.spacy_pipeline import RequirementProcessor
    >>>
    >>> nlp = spacy.load("en_core_web_md")
    >>> processor = RequirementProcessor(nlp, "requirement_processor")
    >>> nlp.add_pipe("requirement_processor", last=True)
    >>>
    >>> doc = nlp("Must have Python experience. Nice to have Java.")
    >>> doc._.requirements
    [{"text": "Must have Python experience.", "confidence": 0.93, "source": "pattern"}]

Issue #321: Implement requirement processor for batch pipeline.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from spacy.language import Language
from spacy.tokens import Doc

from src.poc.tweak.patterns import SectionType
from src.poc.tweak.spacy_pipeline.patterns import REQUIREMENT_PATTERNS

logger = logging.getLogger(__name__)


def _has_negation_context(sentence: str, trigger: str) -> bool:
    """Detect negation patterns near trigger word.

    Detects:
    - "not required"
    - "no experience"
    - "don't need"
    - "isn't necessary"
    - "without experience"

    Args:
        sentence: Full sentence text
        trigger: Trigger word to search for

    Returns:
        True if negation found near trigger word
    """
    negation_words = [
        r"\bnot\b",
        r"\bno\b",
        r"\bdon't\b",
        r"\bdoesn't\b",
        r"\bwithout\b",
    ]

    # Find trigger position
    trigger_pos = sentence.lower().find(trigger.lower())
    if trigger_pos == -1:
        return False

    # Look ±50 chars around trigger
    context_start = max(0, trigger_pos - 50)
    context_end = min(len(sentence), trigger_pos + len(trigger) + 50)
    context = sentence[context_start:context_end]

    for neg_pattern in negation_words:
        if re.search(neg_pattern, context, re.IGNORECASE):
            return True

    return False


def _apply_adjustments(base_confidence: float, sentence: str) -> float:
    """Apply confidence adjustments for context.

    Adjustments:
    - Parentheticals (e.g., "(preferred)"): -0.10
    - Conditional ("if you have..."): -0.15
    - Nice to have: -0.25
    - All caps (emphasis): +0.05

    Args:
        base_confidence: Base confidence score
        sentence: Full sentence text

    Returns:
        Adjusted confidence (clamped to [0.0, 1.0])
    """
    adj = base_confidence

    # Parentheticals: lower confidence
    if re.search(r"\(.*?\)", sentence):
        adj -= 0.10

    # Conditional: lower confidence
    if re.search(r"\bif\b", sentence, re.IGNORECASE):
        adj -= 0.15

    # Nice to have: significantly lower
    if re.search(r"nice\s+to\s+have", sentence, re.IGNORECASE):
        adj -= 0.25

    # All-caps emphasis: boost
    if len(re.findall(r"\b[A-Z]{4,}\b", sentence)) > 2:
        adj += 0.05

    return max(0.0, min(1.0, adj))


class RequirementProcessor:
    """spaCy pipeline component for requirement extraction.

    Reads classified sections from doc._.classified_sections and extracts
    requirements from sections classified as QUALIFICATIONS type only.

    Per-stage error handling ensures extraction errors do not halt processing.

    Attributes:
        nlp: spaCy Language object
        _name: Component identifier for logging
    """

    def __init__(self, nlp: Language, name: str, min_confidence: float = 0.70) -> None:
        """Initialize RequirementProcessor.

        Registers doc._.requirements extension if not already present.

        Args:
            nlp: spaCy Language object (required by factory pattern)
            name: Component name for logging (typically 'requirement_processor')
            min_confidence: Minimum confidence required for the top-ranked
                QUALIFICATIONS classification (classification.all_types[0])
                before extraction runs for that section. Sections where
                all_types is empty/absent fall back to labels-only behavior
                regardless of this threshold (Issue #346).

        Raises:
            ValueError: If name is None or empty
        """
        if not name:
            raise ValueError("Component name cannot be None or empty")

        self.nlp = nlp
        self._name = name
        self.min_confidence = min_confidence

        # Register Doc extension for requirements if not present
        if not Doc.has_extension("requirements"):
            Doc.set_extension("requirements", default=[])

    def __call__(self, doc: Doc) -> Doc:
        """Process a spaCy Doc and extract requirements.

        Reads doc._.classified_sections and extracts requirements from
        sections classified as QUALIFICATIONS type only.

        Returns dict list: [{"text": str, "confidence": float, "source": str}, ...]

        Section titles are not extracted (Issue #375); only section content is
        classified, and content lines starting with "#" (markdown headings) are
        skipped.

        Handles edge cases gracefully:
        - If doc._.classified_sections is None: treats as empty list
        - If doc._.classified_sections is empty: doc._.requirements = []
        - Extraction errors are logged but do not halt processing

        Args:
            doc: spaCy Doc to process

        Returns:
            Modified doc with doc._.requirements populated

        Raises:
            TypeError: If doc is not a spaCy Doc
        """
        # Get classified sections from doc extension (handle None/missing gracefully)
        classified_sections = doc._.classified_sections if doc._.classified_sections else []

        # Extract requirements from sections
        requirements: List[Dict[str, Any]] = []

        for section, classification in classified_sections:
            try:
                # Filter to QUALIFICATIONS section type only (B2 decision)
                # "requirements" section type maps to SectionType.QUALIFICATIONS
                if SectionType.QUALIFICATIONS not in classification.labels:
                    continue

                # Issue #346: when all_types is present, gate extraction on the
                # top-ranked type's confidence. Falls back to labels-only
                # behavior above when all_types is empty/absent.
                all_types = classification.all_types
                if all_types and all_types[0].section_type == SectionType.QUALIFICATIONS:
                    top_confidence = all_types[0].confidence
                    if top_confidence < self.min_confidence:
                        logger.info(
                            f"Skipping QUALIFICATIONS extraction: confidence "
                            f"{top_confidence:.2f} < threshold {self.min_confidence:.2f}"
                        )
                        continue

                # Extract from section content. Section titles are never
                # classified (Issue #375): headings must not become requirements.
                if section.content:
                    for sentence in re.split(r"[.\r\n]+", section.content):
                        sentence = sentence.strip()
                        if not sentence:
                            continue

                        # Issue #375: skip literal markdown heading lines
                        # (e.g. "## Essential Qualifications") inside content.
                        if sentence.startswith("#"):
                            continue

                        req = self._classify_sentence(sentence)
                        if req:
                            requirements.append(req)

            except Exception as e:
                logger.error(f"Error extracting requirements from section at line {section.start_line}: {e}")
                # Continue with next section
                continue

        # Store extracted requirements in doc extension
        doc._.requirements = requirements

        return doc

    def _classify_sentence(self, sentence: str) -> Optional[Dict[str, Any]]:
        """Classify single sentence as containing a requirement.

        Returns dict with requirement info or None if no requirement detected.

        Args:
            sentence: Single sentence text

        Returns:
            Dict with keys: text, trigger_word, confidence, source
            or None if no requirement detected
        """
        if not sentence.strip():
            return None

        # Try each pattern
        best_match: Optional[Dict[str, Any]] = None

        for pattern in REQUIREMENT_PATTERNS:
            if re.search(pattern["regex"], sentence, re.IGNORECASE):
                # Found a match
                confidence: float = pattern["confidence"]

                # Check negations
                if _has_negation_context(sentence, pattern["trigger"]):
                    return None  # Negation found, skip entirely

                # Apply context adjustments
                confidence = _apply_adjustments(confidence, sentence)

                if confidence > 0:
                    # Keep best match (by priority, then confidence)
                    if best_match is None:
                        should_update = True
                    else:
                        best_priority: int = best_match["priority"]  # type: ignore
                        best_confidence: float = best_match["confidence"]  # type: ignore
                        should_update = pattern["priority"] < best_priority or (
                            pattern["priority"] == best_priority and confidence > best_confidence
                        )

                    if should_update:
                        best_match = {
                            "text": sentence,
                            "trigger_word": pattern["trigger"],
                            "confidence": confidence,
                            "source": "pattern",
                            "priority": pattern["priority"],
                        }

        if best_match:
            # Remove temporary priority field, simplify output
            best_match.pop("priority")
            best_match.pop("trigger_word")  # Remove trigger word from output
            return best_match

        return None

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
