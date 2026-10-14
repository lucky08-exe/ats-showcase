import json
import logging
import re

import spacy

from .patterns import TECH_TERMS

logger = logging.getLogger(__name__)


def _generate_patterns():
    patterns = []
    for term in TECH_TERMS:
        # Check if it's a multi-word phrase
        if " " in term or "-" in term:
            # Phrase pattern: Case-insensitive by using the text logic
            # 'computer vision' -> [{'LOWER': 'computer'}, {'LOWER': 'vision'}]
            # spaCy splits intra-word hyphens into 3 tokens, so emit '-' too:
            # 'anchor-free' -> [{'LOWER': 'anchor'}, {'LOWER': '-'}, {'LOWER': 'free'}]
            tokens = re.findall(r"[^\s-]+|-", term.lower())
            patterns.append({"label": "TECH", "pattern": [{"LOWER": t} for t in tokens]})
        else:
            # Single word pattern: Simple case-insensitive token match
            # 'PyTorch' -> {'LOWER': 'pytorch'}
            patterns.append({"label": "TECH", "pattern": [{"LOWER": term.lower()}]})
    # Vue.js: tokenizer may keep it whole or split on the dot
    patterns.append({"label": "TECH", "pattern": [{"LOWER": "vue.js"}]})
    patterns.append({"label": "TECH", "pattern": [{"LOWER": "vue"}, {"ORTH": "."}, {"LOWER": "js"}]})
    return patterns


AMBIGUOUS_TERMS = frozenset({"go", "spring", "vue", "lightning"})
_PREV_CUES = frozenset({"with", "in", "using", "use", "built", "written", "proficient", "experience", "of", "on"})
_NEXT_CUES = frozenset({"boot", "framework", "mvc", "cloud", "data", "security", "lang", "js"})
_LIST_JOINERS = frozenset({",", "and", "&", "/", "or"})
# Terms whose common English meaning ("lightning strike") makes a preceding cue
# ("with", "experience", "of") too weak to prove tech usage. For these, only a
# following cue (_LIGHTNING_NEXT_CUES), a "built with X." sentence end (#513), or an
# adjacent TECH term counts as evidence.
_PREV_CUE_INSUFFICIENT = frozenset({"lightning"})
# Next cues specific to lightning (#513). The shared _NEXT_CUES ("data", "cloud", ...)
# collide with the common English phrase ("Lightning data storms").
_LIGHTNING_NEXT_CUES = frozenset({"trainer", "module", "fabric", "datamodule", "callback", "callbacks"})
_SENTENCE_END = frozenset({".", "!", "?"})
# A hyphen after an ambiguous term joins an English compound ("Go-to-market", "Go-live")
# unless the next word is a tech qualifier ("Go-based services").
_HYPHEN_TECH_SUFFIXES = frozenset({"based", "native", "lang", "like"})
# Negation (#497). spaCy splits "don't"/"doesn't" into "do" + "n't", so "n't" is
# listed explicitly. "nice to have" is deliberately NOT a cue (optional, not absent).
_NEGATION_CUES = frozenset({"no", "not", "without", "never", "lacking", "nor", "n't"})
# A contrast word between a cue and an entity ends the negation scope, so
# "No prior experience needed, but Kubernetes is required." keeps kubernetes.
_CONTRAST_RESET = frozenset({"but", "however", "though", "yet"})
# Clause separators that also end a negation scope (list joiners are handled separately).
_CLAUSE_STOPS = frozenset({";", ":"})
# "not only" / "not just" ("not merely") are affirmative idioms, not negation cues (#516).
_NOT_ONLY_NEXT = frozenset({"only", "just"})
# Multi-word TECH terms that also emit their first token as its own term (#504).
# "PyTorch Lightning" yields "pytorch lightning" plus "pytorch" (as before this term
# existed), but never a standalone "lightning": the longer match wins the overlap.
_COMPOUND_HEADS = {"pytorch lightning": "pytorch"}


def _is_built_with_final(doc, ent):
    """Lightning closes a 'built with' phrase at sentence end, as in 'Built with Lightning.' (#513)."""
    if ent.start < 2 or doc[ent.start - 2].lower_ != "built" or doc[ent.start - 1].lower_ != "with":
        return False
    return ent.end == len(doc) or doc[ent.end].lower_ in _SENTENCE_END


def _is_tech_context(doc, ent, other_techs):
    """Require capitalization plus a tech cue for ambiguous common-word terms."""
    if ent.text == ent.text.lower():
        return False
    word = ent.text.lower()
    nxt = doc[ent.end] if ent.end < len(doc) else None
    prev = doc[ent.start - 1] if ent.start > 0 else None
    if nxt is not None and nxt.lower_ == "-":
        after = doc[ent.end + 1] if ent.end + 1 < len(doc) else None
        if after is None or after.lower_ not in _HYPHEN_TECH_SUFFIXES:
            return False
    next_cues = _LIGHTNING_NEXT_CUES if word in _PREV_CUE_INSUFFICIENT else _NEXT_CUES
    if nxt is not None and (nxt.lower_ in next_cues or doc.text[nxt.idx :].startswith(".js")):
        return True
    if prev is not None and prev.lower_ in _PREV_CUES and word not in _PREV_CUE_INSUFFICIENT:
        return True
    if word in _PREV_CUE_INSUFFICIENT and _is_built_with_final(doc, ent):
        return True
    # Adjacent to another TECH match (optionally across a list joiner)
    for tok_idx, step in ((ent.end, 1), (ent.start - 1, -1)):
        if 0 <= tok_idx < len(doc) and doc[tok_idx].lower_ in _LIST_JOINERS:
            tok_idx += step
        if 0 <= tok_idx < len(doc) and tok_idx in other_techs:
            return True
    return False


def _sentence_bounds(doc, ent):
    """Token bounds of the entity's sentence; whole doc if no sentence boundaries are set."""
    try:
        sent = ent.sent
    except ValueError:
        return 0, len(doc)
    return sent.start, sent.end


def _scan_for_cue(doc, indices, tech_tokens):
    """True when a negation cue is found scanning `indices` before any scope-ending token."""
    for i in indices:
        lower = doc[i].lower_
        if lower == "not" and i + 1 < len(doc) and doc[i + 1].lower_ in _NOT_ONLY_NEXT:
            continue  # "not only" / "not just" (#516)
        if lower in _NEGATION_CUES:
            return True
        if lower in _CONTRAST_RESET or lower in _LIST_JOINERS or lower in _CLAUSE_STOPS or i in tech_tokens:
            break
    return False


def _direct_cues(doc, ent, tech_tokens):
    """(cue_left, cue_right): whether a negation cue directly governs ent from each side.

    Scans outward from ent within its sentence. A cue scan stops at a contrast word,
    list joiner, clause separator, or another TECH token (no cue in that direction).
    """
    lo, hi = _sentence_bounds(doc, ent)
    return (
        _scan_for_cue(doc, range(ent.start - 1, lo - 1, -1), tech_tokens),
        _scan_for_cue(doc, range(ent.end, hi), tech_tokens),
    )


def _list_gap(doc, a, b):
    """Lower-cased joiner tokens between adjacent list items a and b; None when they are not a list."""
    if a.start < b.end and b.start < a.end:
        # Overlapping spans (compound and its head term, #504) are not a list.
        return None
    left, right = (a, b) if a.end <= b.start else (b, a)
    gap = doc[left.end : right.start]
    if len(gap) <= 2 and all(tok.lower_ in _LIST_JOINERS for tok in gap):
        return [tok.lower_ for tok in gap]
    return None


def _propagation_blocked(source_cues, source_is_left, gap):
    """Block list propagation that a directly-cued item's cue should not reach (#516).

    - Rightward, cue on the left: "Docker, no Kubernetes, and Redis" ends the cue's scope
      at ", and" (Redis is a new affirmed item).
    - Leftward, cue on the right: "Python, Kubernetes is not required" ends the scope at a
      bare comma (Python is not part of the negated item). "Kubernetes and Docker are not
      required" still propagates across "and".
    Only items cued from one side are blocked; items reached via propagation are not.
    """
    cue_left, cue_right = source_cues
    if source_is_left:
        return cue_left and not cue_right and "," in gap and ("and" in gap or "&" in gap)
    return cue_right and not cue_left and bool(gap) and all(tok == "," for tok in gap)


def _negated_flags(doc, candidates, tech_tokens):
    """Per-candidate negation flags; negation propagates across list joiners (#497, #516)."""
    cues = [_direct_cues(doc, ent, tech_tokens) for ent in candidates]
    negated = [left or right for left, right in cues]
    changed = True
    while changed:
        changed = False
        for i, ent in enumerate(candidates):
            if negated[i]:
                continue
            for j, other in enumerate(candidates):
                if j == i or not negated[j]:
                    continue
                gap = _list_gap(doc, ent, other)
                if gap is None:
                    continue
                if _propagation_blocked(cues[j], other.end <= ent.start, gap):
                    continue
                negated[i] = True
                changed = True
                break
    return negated


class TechExtractor:
    def __init__(self, nlp):
        self.nlp = nlp
        # Check if entity_ruler already exists
        if "entity_ruler" not in nlp.pipe_names:
            self.ruler = nlp.add_pipe("entity_ruler", before="ner")
        else:
            self.ruler = nlp.get_pipe("entity_ruler")
        self.ruler.add_patterns(_generate_patterns())

    def extract(self, doc):
        try:
            # Extract all TECH entities and normalize to lowercase for deduplication
            # This handles case-insensitive matching results (PyTorch vs pytorch)
            tech_ents = [ent for ent in doc.ents if ent.label_ == "TECH"]
            heads = [doc[ent.start : ent.start + 1] for ent in tech_ents if ent.text.lower() in _COMPOUND_HEADS]
            tech_ents = sorted(tech_ents + heads, key=lambda span: span.start)
            unambiguous_tokens = {
                i for ent in tech_ents if ent.text.lower() not in AMBIGUOUS_TERMS for i in range(ent.start, ent.end)
            }
            # Ambiguity gate first; negation is applied only to confirmed candidates (#497).
            candidates = [
                ent
                for ent in tech_ents
                if ent.text.lower() not in AMBIGUOUS_TERMS or _is_tech_context(doc, ent, unambiguous_tokens)
            ]
            all_tech_tokens = {i for ent in tech_ents for i in range(ent.start, ent.end)}
            negated = _negated_flags(doc, candidates, all_tech_tokens)
            techs_lower = {
                ent.text.lower() for ent, is_negated in zip(candidates, negated, strict=True) if not is_negated
            }
            return sorted(techs_lower)
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return []


def main():
    # Load spaCy model
    nlp = spacy.load("en_core_web_md")

    # Initialize modules
    tech_engine = TechExtractor(nlp)

    text = """[PASTE THE JOB DESCRIPTION HERE]"""

    # Process text
    doc = nlp(text)

    # Run extractions
    results = {"technologies": tech_engine.extract(doc)}

    # Post-process: Remove common noise/duplicates
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
