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
# following cue (_NEXT_CUES) or an adjacent TECH term counts as evidence.
# Accepted limitation: "Built with Lightning." (no next cue, no adjacent TECH) is
# now not extracted, and a next-cue collision such as "Lightning data storms" still
# passes because _NEXT_CUES is shared across all ambiguous terms.
_PREV_CUE_INSUFFICIENT = frozenset({"lightning"})
# Negation (#497). spaCy splits "don't"/"doesn't" into "do" + "n't", so "n't" is
# listed explicitly. "nice to have" is deliberately NOT a cue (optional, not absent).
_NEGATION_CUES = frozenset({"no", "not", "without", "never", "lacking", "nor", "n't"})
# A contrast word between a cue and an entity ends the negation scope, so
# "No prior experience needed, but Kubernetes is required." keeps kubernetes.
_CONTRAST_RESET = frozenset({"but", "however", "though", "yet"})
# Clause separators that also end a negation scope (list joiners are handled separately).
_CLAUSE_STOPS = frozenset({";", ":"})
# Multi-word TECH terms that also emit their first token as its own term (#504).
# "PyTorch Lightning" yields "pytorch lightning" plus "pytorch" (as before this term
# existed), but never a standalone "lightning": the longer match wins the overlap.
_COMPOUND_HEADS = {"pytorch lightning": "pytorch"}


def _is_tech_context(doc, ent, other_techs):
    """Require capitalization plus a tech cue for ambiguous common-word terms."""
    if ent.text == ent.text.lower():
        return False
    nxt = doc[ent.end] if ent.end < len(doc) else None
    prev = doc[ent.start - 1] if ent.start > 0 else None
    if nxt is not None and (nxt.lower_ in _NEXT_CUES or doc.text[nxt.idx :].startswith(".js")):
        return True
    if prev is not None and prev.lower_ in _PREV_CUES and ent.text.lower() not in _PREV_CUE_INSUFFICIENT:
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


def _has_negation_cue(doc, ent, tech_tokens):
    """Scan outward from ent (both directions, same sentence) for a negation cue.

    The scan stops at a negation cue (negated, unless a contrast word was crossed
    first), or at a contrast word, list joiner, clause separator, or another TECH
    token (no negation found in that direction).
    """
    lo, hi = _sentence_bounds(doc, ent)
    for indices in (range(ent.start - 1, lo - 1, -1), range(ent.end, hi)):
        for i in indices:
            lower = doc[i].lower_
            if lower in _NEGATION_CUES:
                return True
            if lower in _CONTRAST_RESET or lower in _LIST_JOINERS or lower in _CLAUSE_STOPS or i in tech_tokens:
                break
    return False


def _list_joined(doc, a, b):
    """True when a and b are adjacent or separated only by list joiners (e.g. ", or" in a serial list)."""
    if a.start < b.end and b.start < a.end:
        # Overlapping spans (compound and its head term, #504) are not a list.
        return False
    left, right = (a, b) if a.end <= b.start else (b, a)
    gap = doc[left.end : right.start]
    return len(gap) <= 2 and all(tok.lower_ in _LIST_JOINERS for tok in gap)


def _negated_flags(doc, candidates, tech_tokens):
    """Per-candidate negation flags; negation propagates across list joiners (#497)."""
    negated = [_has_negation_cue(doc, ent, tech_tokens) for ent in candidates]
    changed = True
    while changed:
        changed = False
        for i, ent in enumerate(candidates):
            if not negated[i] and any(
                negated[j] and _list_joined(doc, ent, other) for j, other in enumerate(candidates) if j != i
            ):
                negated[i] = True
                changed = True
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
