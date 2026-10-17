r"""Standalone, fully-isolated POC: regex-based sentence splitter spaCy component.

Issue #638. Independent re-implementation of "sentences" output. Does NOT import
any ``src.*`` module. Only spaCy and stdlib. Runs on ``spacy.blank("en")`` with no
parser, sentencizer, or model dependency.

Known limitations (accepted for the POC):

- Abbreviations split. ``"e.g. Django."`` yields 2 entries.
- A closing quote or bracket after a terminator blocks the split.
- Unspaced ellipses (``...``) split only before following whitespace; spaced ``. . .`` splits at each dot.
- A soft-wrapped newline with no structural marker now splits. ``"Must know\nPython."`` yields
  ``["Must know", "Python."]``.
"""

from __future__ import annotations

import re

from spacy.language import Language
from spacy.tokens import Doc

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|\s*\n\s*")

Doc.set_extension("poc_sentences", default=None, force=True)


class PocSentenceSplitterComponent:
    """Regex-only sentence splitter. No parser or sentencizer dependency."""

    def __call__(self, doc: Doc) -> Doc:
        """Set ``doc._.poc_sentences`` to stripped, non-empty sentences from ``doc.text``."""
        parts = _SENTENCE_BOUNDARY_RE.split(doc.text)
        doc._.poc_sentences = [part.strip() for part in parts if part.strip()]
        return doc


@Language.factory("poc_sentence_splitter", default_config={})
def create_poc_sentence_splitter(nlp: Language, name: str) -> PocSentenceSplitterComponent:
    """Build the regex-only sentence splitter pipe for ``nlp``."""
    return PocSentenceSplitterComponent()


__all__ = ["PocSentenceSplitterComponent", "create_poc_sentence_splitter"]
