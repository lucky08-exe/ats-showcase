"""Tests for preprocessing functionality."""

from typing import Any

import pytest

from tokenization.chunker import SemanticChunker
from tokenization.counter import TokenCounter
from tokenization.preprocessor import Preprocessor


@pytest.fixture(scope="session")
def md_preprocessor():
    """Shared Preprocessor (en_core_web_md) for read-only tests; skips if the model is unavailable."""
    try:
        return Preprocessor()
    except Exception as e:
        pytest.skip(f"spaCy model not available: {e}")


@pytest.mark.unit
def test_preprocessor_initialization(md_preprocessor):
    """Test preprocessor with spaCy model."""
    assert md_preprocessor.model_name == "en_core_web_md"


@pytest.mark.unit
def test_semantic_chunker():
    """Test semantic chunking."""
    chunker = SemanticChunker(target_chunk_size=400)

    sentences = [
        "This is sentence one.",
        "This is sentence two.",
        "This is sentence three.",
        "This is sentence four.",
    ]

    chunks = chunker.chunk("test text", sentences)
    # Should chunk into semantic groups
    assert isinstance(chunks, list)


@pytest.mark.unit
def test_token_counter():
    """Test token counting."""
    counter = TokenCounter()

    # Test cost estimation
    cost = counter.estimate_cost(input_tokens=1000, output_tokens=100)
    assert cost > 0
    assert cost < 0.01  # Should be less than a cent for these tokens


@pytest.mark.unit
def test_token_pricing():
    """Verify token pricing is available via model config."""
    from config.models import get_model_pricing

    counter = TokenCounter()

    # Check pricing is set for the model
    input_price, output_price = get_model_pricing(counter.model)
    assert input_price > 0
    assert output_price > 0


@pytest.mark.unit
def test_extract_entities_by_section_routes_responsibilities_ner_entities(md_preprocessor):
    """Issue #196: NER entities in a '## Responsibilities' section route to requirements.

    `_route_entity_by_section`'s is_req_section check substring-matches the
    section name against req_section_keywords, and "responsibility" is not a
    substring of "responsibilities", so entities extracted by spaCy NER from
    a Responsibilities section were previously routed nowhere. The two
    sibling extraction paths (noun-compounds, list-items) already special-case
    section_name == "responsibilities"; this test locks in the NER-entity path
    doing the same.
    """
    preprocessor = md_preprocessor

    markdown_text = (
        "## Responsibilities\n\n"
        "Collaborate closely with stakeholders and coordinate with teams "
        "across Europe to deliver quarterly roadmaps.\n"
    )
    _skills, _technologies, requirements = preprocessor._extract_entities_by_section(markdown_text)
    assert "Europe" in requirements


@pytest.mark.unit
def test_extract_entities_by_section_skips_technical_assessment_section(monkeypatch):
    """Issue #221: a 'technical assessment' section is skipped, not routed to skills.

    Before this fix, `skip_sections` had no entry covering "technical
    assessment", so a section with that name would fall through the
    denylist untouched. `_determine_section_type` would then flag it as a
    skills section because "technical" is one of `skills_section_keywords`
    -- misrouting hiring-process content (e.g. a coding test description)
    into the skills entity bucket instead of being excluded entirely.

    `_extract_markdown_sections` is monkeypatched to hand
    `_extract_entities_by_section` a section literally named "technical
    assessment", isolating the skip-list check from the unrelated
    header-canonicalization behavior of `_classify_section_from_header`
    (which independently buckets markdown headers containing "technical"
    into a "skills" section key -- a separate, pre-existing quirk outside
    this fix's scope).
    """
    try:
        preprocessor = Preprocessor()
    except Exception as e:
        pytest.skip(f"spaCy model not available: {e}")

    monkeypatch.setattr(
        preprocessor,
        "_extract_markdown_sections",
        lambda text: {
            "technical assessment": (
                "Candidates will complete a live Python coding assessment during the onsite interview loop."
            )
        },
    )

    # Wrap (not replace) the real nlp call so we can prove the skip_sections
    # `continue` fired -- i.e. the section never reached spaCy processing at
    # all -- rather than merely happening to produce no entities.
    original_nlp = preprocessor.nlp
    nlp_calls: list[str] = []

    def counting_nlp(text: str) -> Any:
        nlp_calls.append(text)
        return original_nlp(text)

    monkeypatch.setattr(preprocessor, "nlp", counting_nlp)

    skills, technologies, requirements = preprocessor._extract_entities_by_section("placeholder")
    assert nlp_calls == [], "section should have been skipped before spaCy processing"
    assert skills == set()
    assert technologies == set()
    assert requirements == set()


@pytest.mark.unit
@pytest.mark.parametrize(
    "section_name",
    [
        "bargaining",
        "conflict of interest",
        "drug free",
        "e-verify",
        "right to work",
        "safety sensitive",
        "total rewards",
        "union",
        "contingent upon award",
    ],
)
def test_extract_entities_by_section_skips_new_denylist_entries(monkeypatch, section_name):
    """Issue #221: newly-added skip_sections entries exclude their sections.

    Ported from a never-merged branch's expanded skip-list review (commit
    fc44d35) -- see docs/dev-note/issue-221-phase11-review.md. Each of
    these section names must be excluded from entity extraction entirely,
    same mechanism as the dedicated "technical assessment" test above.
    """
    try:
        preprocessor = Preprocessor()
    except Exception as e:
        pytest.skip(f"spaCy model not available: {e}")

    monkeypatch.setattr(
        preprocessor,
        "_extract_markdown_sections",
        lambda text: {
            section_name: ("Candidates will complete a live Python coding assessment during the onsite interview loop.")
        },
    )

    # Same rationale as the dedicated "technical assessment" test above:
    # prove the section never reached spaCy processing, not just that the
    # (possibly vacuous, for section names that don't match any routing
    # keyword either) output happened to be empty.
    original_nlp = preprocessor.nlp
    nlp_calls: list[str] = []

    def counting_nlp(text: str) -> Any:
        nlp_calls.append(text)
        return original_nlp(text)

    monkeypatch.setattr(preprocessor, "nlp", counting_nlp)

    skills, technologies, requirements = preprocessor._extract_entities_by_section("placeholder")
    assert nlp_calls == [], "section should have been skipped before spaCy processing"
    assert skills == set()
    assert technologies == set()
    assert requirements == set()


@pytest.mark.unit
def test_preprocessed_job_company_field():
    """Test that PreprocessedJob model includes company field."""
    from datetime import UTC, datetime

    from models.job import PreprocessedJob

    # Create preprocessed job with company
    job = PreprocessedJob(
        job_id="test_job_1",
        company="Test Company",
        clean_text="Senior Developer position",
        sentences=["Senior Developer position"],
        chunks=["Senior Developer position"],
        token_count=50,
        estimated_cost=0.00015,
        processed_date=datetime.now(UTC),
    )

    # Verify company field is preserved
    assert job.company == "Test Company"
    assert job.job_id == "test_job_1"
    assert job.token_count == 50

    # Test with None company
    job_no_company = PreprocessedJob(
        job_id="test_job_2",
        clean_text="Senior Developer position",
        sentences=["Senior Developer position"],
        chunks=["Senior Developer position"],
        token_count=50,
        estimated_cost=0.00015,
    )
    assert job_no_company.company is None
