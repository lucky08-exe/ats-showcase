import logging

import spacy
from spacy.matcher import Matcher
from spacy.tokens import Span
from spacy.util import filter_spans

from .patterns import SKILL_VERBS

logger = logging.getLogger(__name__)


def _has_spaced_dash(span: Span) -> bool:
    """True if a "-" token in the span is not glued to both neighbours.

    spaCy keeps "high-performance" as [high, -, performance] with no whitespace
    around the "-", so the hyphen can join a noun run. A dash set off by spaces
    ("design systems - build tools") is punctuation and must end the span.
    Em/en dashes ("—", "–") are different tokens and never match the "-" pattern.
    """
    for tok in span:
        if tok.text != "-":
            continue
        if tok.whitespace_ or span.doc[tok.i - 1].whitespace_:
            return True
    return False


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

        # Coordinated objects: [Verb] [Connector] [Nouns] "and" [Nouns]
        # (e.g., "lead data science AND platform teams"). Without this, the span
        # stops at "and" and the second conjunct is lost. Only "and" followed by
        # a noun run extends the span; "and" + VERB (e.g., "design and develop")
        # does not match and keeps the single-verb behaviour.
        coordinated_pattern = [
            action_verb(),
            connector(),
            noun_group(),
            {"POS": "CCONJ", "LOWER": "and"},
            noun_group(),
        ]

        # Hyphenated compounds: "high-performance" is tokenized [high, -, performance]
        # and the "-" is PUNCT, which would stop the noun run at "high". These variants
        # let one intra-word hyphen join two noun runs; spaced dashes are rejected in
        # extract() via _has_spaced_dash(). Only one hyphen join per run is matched.
        hyphen_pattern = [action_verb(), connector(), noun_group(), {"ORTH": "-"}, noun_group()]
        # Hyphen in the first conjunct ("high-performance systems and platforms") ...
        hyphen_first_coordinated_pattern = [
            action_verb(),
            connector(),
            noun_group(),
            {"ORTH": "-"},
            noun_group(),
            {"POS": "CCONJ", "LOWER": "and"},
            noun_group(),
        ]
        # ... and in the second conjunct ("systems and high-performance platforms").
        coordinated_hyphen_pattern = [
            action_verb(),
            connector(),
            noun_group(),
            {"POS": "CCONJ", "LOWER": "and"},
            noun_group(),
            {"ORTH": "-"},
            noun_group(),
        ]

        # Add patterns to matcher
        self.matcher.add(
            "SKILL_PHRASE",
            [
                pattern,
                coordinated_pattern,
                hyphen_pattern,
                hyphen_first_coordinated_pattern,
                coordinated_hyphen_pattern,
            ],
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
            matches = self.matcher(doc, as_spans=True)
            # Drop hyphen-variant matches whose "-" is spaced punctuation; the plain
            # pattern still yields the non-hyphenated prefix for those sentences.
            matches = [m for m in matches if not _has_spaced_dash(m)]

            # 4. Best Practice: Filter Overlaps
            # If the matcher finds "design architectures" and "design deep learning architectures",
            # filter_spans will only keep the longest one.
            unique_spans = filter_spans(matches)

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
