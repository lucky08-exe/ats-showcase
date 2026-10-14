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
# verb lemma, so noun coordination is not matched. A skill verb must also govern the
# coordination up the parse: "Our team includes the design and build managers" has
# the same tags but is ruled by "includes", so it is not matched.
#
# A verb-tagged-NOUN conjunct that passes the guard is never merged into the
# preceding span: _conjunct_end() refuses it, so it becomes its own match, the same
# as a VERB conjunct ("design systems and develop platforms").


def _is_verb_tagged_noun(tok: Token) -> bool:
    """True for a skill verb that spaCy tagged NOUN as a conjunct under a skill verb (#511).

    The coordination must be governed by a skill verb somewhere up the parse. Noun
    coordinations under another verb ("Our team includes the design and build
    managers") have the same tags but no skill verb above them, so they do not match.
    """
    if tok.pos_ != "NOUN" or tok.dep_ != "conj" or tok.lemma_ not in _SKILL_VERB_SET:
        return False
    return any(anc.pos_ == "VERB" and anc.lemma_ in _SKILL_VERB_SET for anc in tok.ancestors)


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


# --- Participle inside a noun run (#523) ----------------------------------------
#
# spaCy tags a participle that modifies a noun as VERB (dep amod), e.g. "distributed"
# in "design high-performance distributed systems". Such a token is part of the run
# when a noun-run token follows it. It is not a run start on its own (no noun in front
# of it) and a trailing participle is not absorbed. Other participles keep their
# tags: "We build and deploy distributed systems" tags "distributed" ADJ, and a
# participle with dep acl ("systems used internally") is a clause, not a modifier.


def _is_amod_participle(tok: Token) -> bool:
    """True for a VBN/VBG token tagged VERB that modifies the following noun (dep amod)."""
    return tok.pos_ == "VERB" and tok.tag_ in ("VBN", "VBG") and tok.dep_ == "amod"


def _noun_run_end(doc: Doc, start: int) -> int | None:
    """End (exclusive) of a noun run starting at ``start``, or None.

    The run is maximal over _NOUN_RUN_POS tokens and amod participles that precede
    a noun (see _run_end) and may contain one glued hyphen join ("high-performance").
    Spaced dashes end the run.
    """
    if start >= len(doc) or not _starts_noun_run(doc, start):
        return None
    end = _run_end(doc, start)
    if end < len(doc) and doc[end].text == "-" and not _is_spaced_dash(doc[end]):
        # The glued join may continue with a participle ("data-driven platforms", #556).
        if end + 1 < len(doc) and _starts_noun_run(doc, end + 1):
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


def _starts_noun_run(doc: Doc, start: int) -> bool:
    """True if a noun run can begin at ``start``: a noun-run token, or an amod participle before a noun."""
    if doc[start].pos_ in _NOUN_RUN_POS:
        return True
    return _is_amod_participle(doc[start]) and start + 1 < len(doc) and doc[start + 1].pos_ in _NOUN_RUN_POS


def _run_end(doc: Doc, start: int) -> int:
    """Index just past the contiguous run tokens starting at ``start`` (#523).

    Run tokens are _NOUN_RUN_POS tokens and amod participles that are followed by a
    noun-run token. A trailing participle is not part of the run.
    """
    end = start
    while end < len(doc):
        if doc[end].pos_ in _NOUN_RUN_POS:
            end += 1
        elif _is_amod_participle(doc[end]) and end + 1 < len(doc) and doc[end + 1].pos_ in _NOUN_RUN_POS:
            end += 1
        else:
            break
    return end


def _participle_head_end(doc: Doc, head_end: int) -> int:
    """Extend a matched head across an amod participle that continues its noun run (#523).

    "design high-performance" + "distributed systems" -> the run through "systems".
    Returns ``head_end`` unchanged when the token there does not continue the run.
    """
    if head_end < len(doc) and _is_amod_participle(doc[head_end]) and _starts_noun_run(doc, head_end):
        return _run_end(doc, head_end)
    return head_end


# --- Glued compound tails (#556) -----------------------------------------------
#
# A glued compound can hold a function word between two hyphens: "state-of-the-art",
# "end-to-end" (matched by the ADP pattern in SkillExtractor). Its participle second
# half, "data-driven", is tagged VERB and would start a match as a skill verb ("drive"),
# yielding "driven platform". A participle glued after a hyphen is never a head verb,
# so such a match is dropped. The full span "design data-driven platforms" comes from
# the participle hyphen pattern.


def _is_glued_participle_head(doc: Doc, start: int) -> bool:
    """True if ``start`` is an amod participle glued to a preceding hyphen ("driven" in "data-driven")."""
    return (
        _is_amod_participle(doc[start])
        and start > 0
        and doc[start - 1].text == "-"
        and not _is_spaced_dash(doc[start - 1])
    )


# --- Participial "built with <tech>" (#551) -------------------------------------
#
# "Built with Go and gRPC." names a stack; it is not a skill verb phrase. The Matcher's
# action verb matches lemma "build" whatever its tag, and the optional connector takes
# "with", so "Built with Go" (extended to "... and gRPC") was emitted. A past-tense or
# participle skill verb followed by "with" is dropped. The base form "Build scalable
# APIs with Python" (tag VB/VBP) and a participle not followed by "with" are unchanged.


def _is_participial_with_head(doc: Doc, start: int) -> bool:
    """True for a past-tense/participle skill verb followed by "with" ("Built with Go", #551)."""
    return doc[start].tag_ in ("VBN", "VBD") and start + 1 < len(doc) and doc[start + 1].lower_ == "with"


def _is_join_conjunction(tok: Token) -> bool:
    return tok.pos_ == "CCONJ" and tok.lower_ in _JOIN_CONJUNCTIONS


# --- Bare comma inside an adjective list (#557) ----------------------------------
#
# "design fault-tolerant, low-latency services": the bare comma separates premodifiers
# of one head noun, so the comma is part of the noun run. Under the #509 rule a bare
# comma is punctuation, which cut the run at "fault-tolerant". The adjective-list
# branch below is the exception, and it applies only when BOTH hold:
#   - the token before the comma is adjectival: an ADJ, an amod participle, or a glued
#     compound whose first half is one ("high-performance", "data-driven");
#   - the comma list continues through ADJ-led segments and ends at a plain noun head.
# A segment is a plain head only when its last token is a NOUN/PROPN not glued to a
# hyphen before it, so "low-latency" alone is not a head and "low-latency services" is.
# A noun before the comma ("design systems, platform teams") keeps the #509 rule.
# The list commits only at a plain-noun head; a trailing clause ("..., building APIs")
# is not absorbed. A conjunction closes the list ("..., low-latency, and scalable services").


def _is_glued_hyphen(doc: Doc, i: int) -> bool:
    return 0 <= i < len(doc) and doc[i].text == "-" and not _is_spaced_dash(doc[i])


def _is_adjectival(tok: Token) -> bool:
    return tok.pos_ == "ADJ" or _is_amod_participle(tok)


def _ends_adjectival_modifier(doc: Doc, comma: int) -> bool:
    """True if the token before the comma at ``comma`` is an adjectival modifier (#557)."""
    before = comma - 1
    if before < 0:
        return False
    if _is_adjectival(doc[before]):
        return True
    # Glued compound before the comma: "high-performance" (NOUN after ADJ), "data-driven".
    return _is_glued_hyphen(doc, before - 1) and before >= 2 and _is_adjectival(doc[before - 2])


def _is_plain_noun_head(doc: Doc, run_start: int, run_end: int) -> bool:
    """True if the run ends in a noun that is not the second half of a glued compound."""
    last = run_end - 1
    if last < run_start or doc[last].pos_ not in ("NOUN", "PROPN"):
        return False
    return not (last - 1 >= run_start and _is_glued_hyphen(doc, last - 1))


def _adjective_list_end(doc: Doc, comma: int) -> int | None:
    """End (exclusive) of an adjective list after the bare comma at ``comma``, or None (#557).

    Returns the end of the last segment that is a plain noun head. None when the
    comma does not follow an adjectival modifier or no segment ends in a noun head.
    """
    if not _ends_adjectival_modifier(doc, comma):
        return None
    best: int | None = None
    cursor = comma
    while cursor < len(doc) and doc[cursor].text == ",":
        seg = cursor + 1
        closes = seg < len(doc) and _is_join_conjunction(doc[seg])
        if closes:
            seg += 1
        if seg >= len(doc) or not _is_adjectival(doc[seg]):
            break
        run_end = _noun_run_end(doc, seg)
        if run_end is None:
            break
        if _is_plain_noun_head(doc, seg, run_end):
            best = run_end
            break
        if closes:
            break
        cursor = run_end
    return best


def _coordinated_end(doc: Doc, head_end: int) -> int:
    """Return the end of the coordinated span that starts at a head ending at ``head_end``.

    Returns ``head_end`` unchanged when no conjunction-led conjunct follows.
    """
    committed = head_end
    cursor = head_end
    bare_comma_conjunct = False
    while cursor < len(doc):
        if doc[cursor].text == ",":
            # ", and X" / ", or X" commits; a bare ", X" is tentative.
            after_comma = cursor + 1
            commits = after_comma < len(doc) and _is_join_conjunction(doc[after_comma])
            if not commits:
                # A bare comma may open an adjective list at the head or after a
                # conjunction-led conjunct (#557). Never after a bare noun conjunct (#509).
                if not bare_comma_conjunct:
                    list_end = _adjective_list_end(doc, cursor)
                    if list_end is not None:
                        committed = list_end
                        cursor = list_end
                        continue
                bare_comma_conjunct = True
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
        # Function word inside a glued compound (#556): "state-of-the-art" (ADP + DET) and
        # "end-to-end" (ADP only). The DET and its hyphen are optional; each hyphen is glued.
        hyphen_adp_pattern = [
            action_verb(),
            connector(),
            noun_group(),
            {"ORTH": "-"},
            {"POS": "ADP"},
            {"ORTH": "-"},
            {"POS": "DET", "OP": "?"},
            {"ORTH": "-", "OP": "?"},
            noun_group(),
        ]
        # Participle second half of a glued compound (#556): "data-driven platforms". spaCy
        # tags the participle VERB with dep amod, which the noun-run pattern does not accept.
        hyphen_participle_pattern = [
            action_verb(),
            connector(),
            noun_group(),
            {"ORTH": "-"},
            {"TAG": {"IN": ["VBN", "VBG"]}, "DEP": "amod"},
            noun_group(),
        ]
        # Participle-led head (#558): "Design distributed systems" at the start of a sentence.
        # spaCy tags the sentence-initial imperative NOUN (npadvmod) and the participle VERB
        # (amod), so no action verb starts a match. The head is a skill-verb lemma tagged NOUN
        # at a sentence start, followed by a participle modifier and a noun run. The participle
        # must not itself be a skill verb: "Lead managed services" keeps the participle head.
        participle_head_pattern = [
            {"POS": "NOUN", "LEMMA": {"IN": SKILL_VERBS}, "IS_SENT_START": True},
            {"TAG": {"IN": ["VBN", "VBG"]}, "DEP": "amod", "LEMMA": {"NOT_IN": SKILL_VERBS}},
            noun_group(),
        ]
        # Add patterns to matcher
        self.matcher.add(
            "SKILL_PHRASE",
            [pattern, hyphen_pattern, hyphen_adp_pattern, hyphen_participle_pattern, participle_head_pattern],
        )

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
            matches = [
                m
                for m in matches
                if not _has_spaced_dash(m)
                and not _is_glued_participle_head(doc, m.start)
                and not _is_participial_with_head(doc, m.start)
            ]
            # Extend each head through its coordinated conjuncts (#509). The extended
            # span contains the head, so filter_spans keeps it over the bare head.
            extended = [doc[m.start : _coordinated_end(doc, _participle_head_end(doc, m.end))] for m in matches]

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
