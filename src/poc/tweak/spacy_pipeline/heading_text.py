import re
from typing import Optional

_HEADING_MARKER_PATTERN = re.compile(r"^[#*_\s]+|[#*_:\s]+$")

KNOWN_HEADING_PHRASES: frozenset[str] = frozenset(
    {
        "minimum qualifications",
        "additional qualifications",
        "preferred qualifications",
        "required qualifications",
        "working conditions",
        "key responsibilities",
        "applicants who do not meet these qualifications will not be forwarded to the hiring department",
    }
)


def normalize_heading_text(text: str) -> str:
    """Normalize heading text for comparison."""

    cleaned = _HEADING_MARKER_PATTERN.sub("", text)
    cleaned = cleaned.strip().lower()
    return cleaned


def is_heading_only(candidate: str, heading: Optional[str] = None) -> bool:
    """Return whether candidate contains only a heading."""

    normalized = normalize_heading_text(candidate)
    if normalized == "":
        return False

    if heading is not None:
        return normalized == normalize_heading_text(heading)

    return normalized in KNOWN_HEADING_PHRASES
