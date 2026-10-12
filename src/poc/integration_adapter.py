"""Combined skills + technologies extractor adapter (Issue #433).

POC-only. Not wired into src/cli.py. Do not import from production pipeline
modules (src/cli.py, src/preprocessing, src/storage).

Wraps SkillExtractor (raw text input) and TechExtractor (spaCy Doc input) behind
one ``extract`` call that returns ``{"skills": [...], "technologies": [...]}``.
Each extractor fails independently: an error in one yields ``[]`` for its key
while the other is unaffected.
"""

import logging

import spacy
from spacy.language import Language

from src.poc.skills.extract_skills_a import SkillExtractor
from src.poc.technologies.extract_technologies_a import TechExtractor

logger = logging.getLogger(__name__)


def _normalize(items: list[str]) -> list[str]:
    """Return sorted, deduplicated string items.

    Args:
        items: Raw extractor output.

    Returns:
        Sorted list of unique lowercase strings, non-string items dropped.
    """
    return sorted({item.lower() for item in items if isinstance(item, str)})


class CombinedExtractor:
    """Run skill and technology extraction over the same text.

    Attributes:
        skills: SkillExtractor operating on raw text.
        tech_nlp: Separate spaCy pipeline dedicated to technology extraction,
            so its entity_ruler does not touch the skills pipeline.
        tech: TechExtractor operating on a spaCy Doc from ``tech_nlp``.
    """

    def __init__(self, model_name: str = "en_core_web_md") -> None:
        """Load both extractors.

        Args:
            model_name: spaCy model package name used for both pipelines.

        Raises:
            OSError: If the spaCy model is not installed.
        """
        self.skills: SkillExtractor = SkillExtractor(model_name)
        self.tech_nlp: Language = spacy.load(model_name)
        self.tech: TechExtractor = TechExtractor(self.tech_nlp)

    def extract(self, text: str) -> dict[str, list[str]]:
        """Extract skills and technologies from text.

        Args:
            text: Job description text. Empty, whitespace-only, or non-str
                input yields empty lists.

        Returns:
            Dict with exactly the keys ``"skills"`` and ``"technologies"``,
            each a sorted, deduplicated list of lowercase strings.
        """
        if not isinstance(text, str) or not text.strip():
            return {"skills": [], "technologies": []}

        skills: list[str]
        try:
            skills = self.skills.extract(text)
        except Exception as e:
            logger.error(f"Skill extraction failed: {e}")
            skills = []

        technologies: list[str]
        try:
            doc = self.tech_nlp(text)
            technologies = self.tech.extract(doc)
        except Exception as e:
            logger.error(f"Technology extraction failed: {e}")
            technologies = []

        return {
            "skills": _normalize(skills),
            "technologies": _normalize(technologies),
        }
