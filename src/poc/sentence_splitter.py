r"""Standalone, fully-isolated POC: regex-based sentence splitter spaCy component.

Issue #638. Independent re-implementation of "sentences" output. Does NOT import
any ``src.*`` module. Only spaCy and stdlib. Runs on ``spacy.blank("en")`` with no
parser, sentencizer, or model dependency.

Known limitations (accepted for the POC):

- Bullet lines without terminal punctuation join into one sentence. ``"- Python\n- SQL"``
  yields 1 entry, since ``\n`` is not a boundary.
- Abbreviations split. ``"e.g. Django."`` yields 2 entries.
- A closing quote or bracket after a terminator blocks the split.
- An ellipsis splits at each dot.
- A markdown heading glues onto the following sentence when no terminator separates them.
  ``"## Requirements\n\nYou must know Python."`` yields 1 entry.
"""

from __future__ import annotations

import re

from spacy.language import Language
from spacy.tokens import Doc

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")

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
