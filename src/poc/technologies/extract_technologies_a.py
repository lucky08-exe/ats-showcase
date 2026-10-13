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


def _is_tech_context(doc, ent, other_techs):
    """Require capitalization plus a tech cue for ambiguous common-word terms."""
    if ent.text == ent.text.lower():
        return False
    nxt = doc[ent.end] if ent.end < len(doc) else None
    prev = doc[ent.start - 1] if ent.start > 0 else None
    if nxt is not None and (nxt.lower_ in _NEXT_CUES or doc.text[nxt.idx :].startswith(".js")):
        return True
    if prev is not None and prev.lower_ in _PREV_CUES:
        return True
    # Adjacent to another TECH match (optionally across a list joiner)
    for tok_idx, step in ((ent.end, 1), (ent.start - 1, -1)):
        if 0 <= tok_idx < len(doc) and doc[tok_idx].lower_ in _LIST_JOINERS:
            tok_idx += step
        if 0 <= tok_idx < len(doc) and tok_idx in other_techs:
            return True
    return False


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
            unambiguous_tokens = {
                i for ent in tech_ents if ent.text.lower() not in AMBIGUOUS_TERMS for i in range(ent.start, ent.end)
            }
            techs_lower = {
                ent.text.lower()
                for ent in tech_ents
                if ent.text.lower() not in AMBIGUOUS_TERMS or _is_tech_context(doc, ent, unambiguous_tokens)
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
