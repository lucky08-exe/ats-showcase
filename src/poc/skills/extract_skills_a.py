import logging

import spacy
from spacy.matcher import Matcher
from spacy.tokens import Doc, Span, Token
from spacy.util import filter_spans

from .patterns import SKILL_VERBS

_SKILL_VERB_SET = frozenset(SKILL_VERBS)
# Tokens that may sit between a verb and its object ('ship TO the market', 'ship THE platform').
_CONNECTOR_POS = ("ADP", "DET", "PART")

logger = logging.getLogger(__name__)

# POS tags that can form a noun run (a head object or a coordinated conjunct).
_NOUN_RUN_POS = ("ADJ", "NOUN", "PROPN")
# Conjunctions that can join conjuncts ("data and ML", "data or ML").
_JOIN_CONJUNCTIONS = ("and", "or")


def _is_spaced_dash(tok: Token) -> bool:
    """True if a "-" token is not glued to both neighbours.

    spaCy keeps "high-performance" as [high, -, performance] with no whitespace
    around the "-", so the hyphen can join a noun run. A dash set off by spaces
    ("design systems - build tools") is punctuation and must end the span.
    Em/en dashes ("—", "–") are different tokens and never match the "-" pattern.
    """
    return tok.text == "-" and bool(tok.whitespace_ or tok.doc[tok.i - 1].whitespace_)


def _has_spaced_dash(span: Span) -> bool:
    """True if a "-" token in the span is not glued to both neighbours."""
    return any(_is_spaced_dash(tok) for tok in span)


# --- Coordination extension (#509) ---------------------------------------------
#
# The Matcher finds a HEAD: action verb, optional connector, noun run, with at
# most one hyphen join (see SkillExtractor patterns). _coordinated_end() then
# grows the head through a chain of conjuncts. Matcher token patterns cannot
# repeat a multi-token group, so one walker covers "A and B", "A or B",
# "A, B, and C", "A, B and C" and chains of any length.
#
# Intended spans (HEAD ends where the list starts; [...] is the added tail):
#   "lead data [or ML teams]"                 -> "lead data or ml teams"
#   "lead data [, platform, and ML teams]"    -> "lead data, platform, and ml teams"
#   "lead data [, platform and ML teams]"     -> "lead data, platform and ml teams"
#   "lead data [and ML or cloud teams]"       -> mixed and/or chain merges
#   "build or develop data pipelines"         -> "develop data pipelines" (no merge:
#                                                "or" is followed by a VERB)
#   "lead data science, platform teams"       -> "lead data science" (bare comma)
#   "design systems, platforms, and develop"  -> "design systems" + "develop ..."
#                                                (tail commits only at the conjunct
#                                                before the VERB, which is rejected)
#
# A conjunct commits the span end only when a conjunction ("and"/"or", optionally
# after a comma) precedes it. Bare-comma conjuncts are tentative: they are kept
# only if a later conjunction-led conjunct commits.
#
# --- Verb tagged NOUN (#511) ----------------------------------------------------
#
# spaCy sometimes tags a coordinated skill verb as NOUN with dep 'conj':
#   "manage Kafka clusters on GCP and ship Terraform modules"
# The Matcher needs VERB, so such a token never starts a match. The guard below
# lets it start its own match when ALL of these hold:
#   - tag NOUN and dep conj, and the lemma is in SKILL_VERBS;
#   - an object noun group follows (optionally after one connector).
# "the ship and crew" fails the dep test (ship is not conj) and "and crew" has no
# verb lemma, so noun coordination is not matched.
#
# A verb-tagged-NOUN conjunct that passes the guard is never merged into the
# preceding span: _conjunct_end() refuses it, so it becomes its own match, the same
# as a VERB conjunct ("design systems and develop platforms").


def _is_verb_tagged_noun(tok: Token) -> bool:
    """True for a skill verb that spaCy tagged NOUN as a conjunct (#511)."""
    return tok.pos_ == "NOUN" and tok.dep_ == "conj" and tok.lemma_ in _SKILL_VERB_SET


def _verb_start_end(doc: Doc, start: int) -> int | None:
    """End (exclusive) of the object of a verb-tagged-NOUN start at ``start``, or None.

    None unless the guard passes: the token is a verb-tagged-NOUN conjunct and an
    object noun run follows it, optionally after one connector.
    """
    if start >= len(doc) or not _is_verb_tagged_noun(doc[start]):
        return None
    obj = start + 1
    if obj < len(doc) and doc[obj].pos_ in _CONNECTOR_POS:
        obj += 1
    return _noun_run_end(doc, obj)


def _noun_run_end(doc: Doc, start: int) -> int | None:
    """End (exclusive) of a noun run starting at ``start``, or None.

    The run is maximal over _NOUN_RUN_POS tokens and may contain one glued
    hyphen join ("high-performance"). Spaced dashes end the run.
    """
    if start >= len(doc) or doc[start].pos_ not in _NOUN_RUN_POS:
        return None
    end = _run_end(doc, start)
    if end < len(doc) and doc[end].text == "-" and not _is_spaced_dash(doc[end]):
        if end + 1 < len(doc) and doc[end + 1].pos_ in _NOUN_RUN_POS:
            end = _run_end(doc, end + 1)
    return end


def _conjunct_end(doc: Doc, start: int) -> int | None:
    """End (exclusive) of a conjunct noun run starting at ``start``, or None.

    None also when ``start`` is a verb-tagged-NOUN that passes the #511 guard: it
    starts its own match and must not be merged into the preceding span.
    """
    if _verb_start_end(doc, start) is not None:
        return None
    return _noun_run_end(doc, start)


def _run_end(doc: Doc, start: int) -> int:
    """Index just past the contiguous _NOUN_RUN_POS tokens starting at ``start``."""
    end = start
    while end < len(doc) and doc[end].pos_ in _NOUN_RUN_POS:
        end += 1
    return end


def _is_join_conjunction(tok: Token) -> bool:
    return tok.pos_ == "CCONJ" and tok.lower_ in _JOIN_CONJUNCTIONS


def _coordinated_end(doc: Doc, head_end: int) -> int:
    """Return the end of the coordinated span that starts at a head ending at ``head_end``.

    Returns ``head_end`` unchanged when no conjunction-led conjunct follows.
    """
    committed = head_end
    cursor = head_end
    while cursor < len(doc):
        if doc[cursor].text == ",":
            # ", and X" / ", or X" commits; a bare ", X" is tentative.
            after_comma = cursor + 1
            commits = after_comma < len(doc) and _is_join_conjunction(doc[after_comma])
            run_start = after_comma + 1 if commits else after_comma
        elif _is_join_conjunction(doc[cursor]):
            commits = True
            run_start = cursor + 1
        else:
            break
        run_end = _conjunct_end(doc, run_start)
        if run_end is None:
            break
        if commits:
            committed = run_end
        cursor = run_end
    return committed


class SkillExtractor:
    def __init__(self, model_name="en_core_web_md", nlp=None):
        # Reuse a pre-loaded pipeline when given; otherwise load the model.
        if nlp is not None:
            self.nlp = nlp
        else:
            # Load spaCy model with error handling
            try:
                self.nlp = spacy.load(model_name)
            except OSError:
                logger.error(
                    f"Failed to load spaCy model '{model_name}'. Ensure it's installed: "
                    f"python -m spacy download {model_name}"
                )
                raise
        self.matcher = Matcher(self.nlp.vocab)

        # 2. Define the Matcher Patterns
        # Logic: [Action Verb] + [Optional Preposition/Article] + [Descriptive Nouns/Adjectives]
        def noun_group() -> dict:
            # The Meat: A sequence of Nouns, Adjectives, or Proper Nouns
            # (e.g., "novel deep learning architectures")
            # Note: ADP excluded from this group (prepositions shouldn't appear as descriptors)
            return {"POS": {"IN": ["ADJ", "NOUN", "PROPN"]}, "OP": "+"}

        def action_verb() -> dict:
            # The Action: Must be a verb and its base form must be in our list
            return {"POS": "VERB", "LEMMA": {"IN": SKILL_VERBS}}

        def connector() -> dict:
            # Optional: Connector words like "with", "the", "of"
            # (e.g., "partner WITH", "lead THE")
            return {"POS": {"IN": ["ADP", "DET", "PART"]}, "OP": "?"}

        pattern = [action_verb(), connector(), noun_group()]

        # Coordinated objects ("lead data science and platform teams") are not matched
        # here: _coordinated_end() extends each head through and/or/serial conjuncts (#509).

        # Hyphenated compounds: "high-performance" is tokenized [high, -, performance]
        # and the "-" is PUNCT, which would stop the noun run at "high". These variants
        # let one intra-word hyphen join two noun runs; spaced dashes are rejected in
        # extract() via _has_spaced_dash(). Only one hyphen join per run is matched.
        hyphen_pattern = [action_verb(), connector(), noun_group(), {"ORTH": "-"}, noun_group()]
        # Add patterns to matcher
        self.matcher.add("SKILL_PHRASE", [pattern, hyphen_pattern])

    def extract(self, text):
        try:
            doc = self.nlp(text)
        except Exception as e:
            logger.error(f"Failed to process text with spaCy pipeline: {e}")
            return []

        try:
            # 3. Find matches in the document
            # 'as_spans=True' returns spaCy Span objects instead of ID tuples
            matches = list(self.matcher(doc, as_spans=True))
            # Verb-tagged-NOUN starts (#511) are matched by the guard, not the Matcher.
            for i in range(len(doc)):
                obj_end = _verb_start_end(doc, i)
                if obj_end is not None:
                    matches.append(doc[i:obj_end])
            # Drop hyphen-variant matches whose "-" is spaced punctuation; the plain
            # pattern still yields the non-hyphenated prefix for those sentences.
            matches = [m for m in matches if not _has_spaced_dash(m)]
            # Extend each head through its coordinated conjuncts (#509). The extended
            # span contains the head, so filter_spans keeps it over the bare head.
            extended = [doc[m.start : _coordinated_end(doc, m.end)] for m in matches]

            # 4. Best Practice: Filter Overlaps
            # If the matcher finds "design architectures" and "design deep learning architectures",
            # filter_spans will only keep the longest one.
            unique_spans = filter_spans(matches + extended)

            # Clean the text: strip whitespace and convert to lowercase
            results = [span.text.replace("\n", " ").strip().lower() for span in unique_spans]

            # Deduplicate and return
            return sorted(set(results))
        except Exception as e:
            logger.error(f"Matcher extraction failed: {e}")
            return []


# --- Implementation Example ---

if __name__ == "__main__":
    # Example input from the Carbon Robotics JD
    carbon_jd_bullets = """[PASTE THE JOB DESCRIPTION HERE]"""

    # Initialize and Run
    extractor = SkillExtractor()
    skills = extractor.extract(carbon_jd_bullets)

    print(f"{'INDEX':<5} | {'EXTRACTED SKILL'}")
    print("-" * 50)
    for i, skill in enumerate(skills):
        print(f"{i + 1:<5} | {skill}")
