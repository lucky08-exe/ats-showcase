"""Unit tests for SkillExtractor POC module."""

from pathlib import Path

import pytest
import spacy

from src.poc.skills.extract_skills_a import SkillExtractor
from src.poc.skills.patterns import SKILL_VERBS


@pytest.fixture(scope="session")
def extractor():
    """Initialize SkillExtractor with spaCy model."""
    return SkillExtractor(model_name="en_core_web_md")


@pytest.fixture
def fixture_what_you_ll_do():
    """Load 'What You'll Do' fixture."""
    path = Path("tests/poc/fixtures/raw_jd_what_you_ll_do.md")
    return path.read_text() if path.exists() else ""


@pytest.fixture
def fixture_knowledge_skills():
    """Load 'Knowledge, Skills & Abilities' fixture."""
    path = Path("tests/poc/fixtures/raw_jd_knowledge_skills_abilities.md")
    return path.read_text() if path.exists() else ""


class TestSkillExtractorBasics:
    """Test basic extraction functionality."""

    def test_extractor_initialization(self, extractor):
        """Extractor initializes with spaCy model and matcher."""
        assert extractor.nlp is not None
        assert extractor.matcher is not None

    def test_extract_simple_skill(self, extractor):
        """Extract single skill phrase with action verb."""
        text = "Must design machine learning systems."
        skills = extractor.extract(text)
        assert len(skills) > 0
        assert any("design" in s for s in skills)

    def test_extract_multiple_skills(self, extractor):
        """Extract multiple skill phrases."""
        text = "You will design neural networks. You will develop production systems. You will deploy at scale."
        skills = extractor.extract(text)
        assert skills == ["deploy at scale", "design neural networks", "develop production systems"]

    def test_extract_returns_list(self, extractor):
        """Extract returns sorted list."""
        text = "Lead the team and develop solutions."
        skills = extractor.extract(text)
        assert isinstance(skills, list)
        assert all(isinstance(s, str) for s in skills)

    def test_extract_lowercase_output(self, extractor):
        """All results are lowercase."""
        text = "You will design Python applications. You will deploy systems."
        skills = extractor.extract(text)
        assert skills == ["deploy systems", "design python applications"]

    def test_extract_no_duplicates(self, extractor):
        """Results deduplicated."""
        # Identical matches must collapse to a single entry (sorted(set(...)))
        text = "You will design systems. You will design systems. You will design systems."
        skills = extractor.extract(text)
        assert skills == ["design systems"]

    def test_extract_handles_newlines(self, extractor):
        """Handles newlines in text."""
        text = "Lead the\ndesign of\narchitectures."
        skills = extractor.extract(text)
        # Should extract without newline issues
        assert isinstance(skills, list)

    def test_extract_empty_text(self, extractor):
        """Extract from empty text returns empty list."""
        skills = extractor.extract("")
        assert skills == []

    def test_extract_no_verbs(self, extractor):
        """Text without skill verbs returns empty."""
        text = "The quick brown fox jumps over the lazy dog."
        skills = extractor.extract(text)
        assert skills == []


class TestSkillExtractorPatternMatching:
    """Test pattern matching against SKILL_VERBS."""

    def test_all_skill_verbs_present(self):
        """SKILL_VERBS list populated."""
        assert len(SKILL_VERBS) > 0
        assert "design" in SKILL_VERBS
        assert "develop" in SKILL_VERBS
        assert "lead" in SKILL_VERBS

    def test_lemmatization_base_form(self, extractor):
        """Captures base form (lemma) of verbs."""
        text = "You will lead teams and develop solutions."
        skills = extractor.extract(text)
        assert skills == ["develop solutions", "lead teams"]

    def test_captures_past_tense(self, extractor):
        """Captures past tense forms."""
        text = "Designed systems. Developed architectures."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_captures_continuous_form(self, extractor):
        """Captures -ing forms."""
        text = "Designing neural networks. Deploying models."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_captures_descriptive_nouns(self, extractor):
        """Captures nouns/adjectives after verb."""
        text = "Lead the design of deep learning architectures."
        skills = extractor.extract(text)
        assert len(skills) > 0
        assert any("design" in s for s in skills)

    def test_optional_preposition_handling(self, extractor):
        """Handles optional prepositions (with, the, of)."""
        text1 = "You will lead the design of systems."
        text2 = "You will lead design efforts."
        skills1 = extractor.extract(text1)
        skills2 = extractor.extract(text2)
        # Observed: the optional "the/of" connector is kept; "of systems" is not
        # (ADP is excluded from the noun run), so the span stops at "design".
        assert skills1 == ["lead the design"]
        assert skills2 == ["lead design efforts"]

    def test_compound_noun_phrases(self, extractor):
        """Captures compound nouns (deep learning)."""
        text = "Lead the design of deep learning architectures."
        skills = extractor.extract(text)
        assert len(skills) > 0
        # Should capture "deep learning" as part of phrase

    def test_coordinated_nouns_full_span(self, extractor):
        """Coordinated object nouns stay in one span (snippet s6, #498)."""
        text = "Lead data science and platform teams building services in Python and Docker."
        skills = extractor.extract(text)
        # Span must not stop at "and"; "building services" is a separate verb phrase.
        assert skills == ["building services", "lead data science and platform teams"]

    def test_and_before_verb_not_merged(self, extractor):
        """'and' followed by a verb does not extend the noun span."""
        text = "You will design systems and develop platforms."
        skills = extractor.extract(text)
        assert skills == ["design systems", "develop platforms"]

    def test_longest_span_filtering(self, extractor):
        """Filters overlapping spans, keeps longest."""
        text = "Design and develop novel deep learning architectures."
        skills = extractor.extract(text)
        # Should pick longest matches, avoid duplicates
        assert len(skills) > 0


class TestSkillExtractorFixtures:
    """Test against real job description fixtures."""

    def test_extract_from_what_you_ll_do(self, extractor, fixture_what_you_ll_do):
        """Extract skills from 'What You'll Do' section."""
        if not fixture_what_you_ll_do:
            pytest.skip("Fixture file not found")

        skills = extractor.extract(fixture_what_you_ll_do)
        assert len(skills) > 0

        # Verify results are properly formatted
        assert all(isinstance(s, str) for s in skills)
        assert all(s.islower() for s in skills)

        # At least one skill should be extracted
        assert len(skills) >= 1

    def test_extract_from_knowledge_skills(self, extractor, fixture_knowledge_skills):
        """Extract skills from 'Knowledge, Skills & Abilities' section."""
        if not fixture_knowledge_skills:
            pytest.skip("Fixture file not found")

        skills = extractor.extract(fixture_knowledge_skills)
        assert len(skills) > 0

        # Verify results are properly formatted
        assert all(isinstance(s, str) for s in skills)
        assert all(s.islower() for s in skills)
        # All skills should be non-empty after stripping
        assert all(s.strip() for s in skills)

    def test_fixture_combined_extraction(self, extractor, fixture_what_you_ll_do, fixture_knowledge_skills):
        """Extract from combined fixtures."""
        combined_text = fixture_what_you_ll_do + "\n" + fixture_knowledge_skills
        skills = extractor.extract(combined_text)

        # Should extract from both sections
        assert len(skills) > 3
        # All results should be lowercase
        assert all(s.islower() for s in skills)
        # All results should be strings
        assert all(isinstance(s, str) for s in skills)
        # No empty strings
        assert all(s.strip() for s in skills)

    def test_fixture_extraction_accuracy(self, extractor, fixture_what_you_ll_do):
        """Verify extraction hit rate on fixture."""
        if not fixture_what_you_ll_do:
            pytest.skip("Fixture file not found")

        skills = extractor.extract(fixture_what_you_ll_do)

        # Expected verbs to find
        expected_verbs = ["lead", "design", "develop", "own", "drive", "define", "partner", "mentor", "communicate"]
        found_verbs = set()
        for skill in skills:
            for verb in expected_verbs:
                if verb in skill.split():
                    found_verbs.add(verb)

        # Should find at least 50% of expected verbs
        hit_rate = len(found_verbs) / len(expected_verbs)
        assert hit_rate >= 0.5, f"Hit rate {hit_rate:.0%} below 50%"


class TestSkillExtractorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_sentence_with_punctuation(self, extractor):
        """Handles end-of-sentence punctuation."""
        text = "Design robust systems. Deploy at scale."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_multiple_verbs_in_sequence(self, extractor):
        """Handles comma-separated verbs."""
        text = "Design, develop, and deploy solutions."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_verb_with_many_modifiers(self, extractor):
        """Captures skill with multiple adjectives."""
        text = "Develop robust, scalable, production-ready systems."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_skill_at_sentence_start(self, extractor):
        """Extracts skill at sentence beginning."""
        text = "Lead the design of systems from scratch."
        skills = extractor.extract(text)
        assert len(skills) > 0

    def test_skill_at_sentence_end(self, extractor):
        """Extracts skill at sentence end."""
        text = "The team must design systems."
        skills = extractor.extract(text)
        assert skills == ["design systems"]

    def test_hyphenated_noun(self, extractor):
        """Keeps the full hyphenated span (#508); no truncation at the hyphen."""
        text = "You will design high-performance distributed systems."
        skills = extractor.extract(text)
        # Deliberate #508 pin updated in #523: "distributed" is tagged VERB (amod) by the
        # parser; it now joins the run, so the full span is kept.
        assert skills == ["design high-performance distributed systems"]

    def test_parenthetical_context(self, extractor):
        """Handles skill in parenthetical context."""
        text = "Lead the design and development of novel architectures (state-of-the-art)."
        skills = extractor.extract(text)
        # Should handle parentheses without crashing
        assert isinstance(skills, list)

    def test_special_characters_in_text(self, extractor):
        """Handles special characters."""
        text = "Design & develop → production systems."
        skills = extractor.extract(text)
        # Should not crash
        assert isinstance(skills, list)

    def test_very_long_skill_phrase(self, extractor):
        """Handles long skill phrases."""
        text = "Design and develop novel deep learning architectures for computer vision in production environments."
        skills = extractor.extract(text)
        assert len(skills) > 0


class TestSkillExtractorSorting:
    """Test result sorting and ordering."""

    def test_results_are_sorted(self, extractor):
        """Results returned in sorted order."""
        text = "You will develop solutions. You will design architectures. You will deploy systems."
        skills = extractor.extract(text)
        assert skills == ["deploy systems", "design architectures", "develop solutions"]

    def test_sorted_case_insensitive(self, extractor):
        """Mixed-case input yields sorted, lowercase output."""
        text = "You will design systems. You will BUILD tools. You will manage teams."
        skills = extractor.extract(text)
        assert skills == ["build tools", "design systems", "manage teams"]


class TestSkillExtractorPerformance:
    """Test performance characteristics."""

    def test_extraction_completes_quickly(self, extractor, fixture_what_you_ll_do):
        """Extraction completes in reasonable time."""
        if not fixture_what_you_ll_do:
            pytest.skip("Fixture file not found")

        import time

        start = time.perf_counter()
        skills = extractor.extract(fixture_what_you_ll_do)
        elapsed = time.perf_counter() - start

        # Coarse sanity bound only (5s), not a perf assertion; avoids CI flake
        assert elapsed < 5.0
        assert len(skills) > 0

    def test_repeated_extraction_consistent(self, extractor):
        """Multiple extractions produce same results."""
        text = "Design and develop systems."
        skills1 = extractor.extract(text)
        skills2 = extractor.extract(text)
        assert skills1 == skills2


class TestSkillExtractorVocabularyAdditions:
    """Verbs added for #499 (manage, ship, evaluate)."""

    def test_new_verbs_in_skill_verbs(self):
        """New verbs are registered in SKILL_VERBS."""
        assert {"manage", "ship", "evaluate"} <= set(SKILL_VERBS)

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("You will manage teams.", ["manage teams"]),
            ("You will ship products.", ["ship products"]),
            ("You will evaluate vendors.", ["evaluate vendors"]),
        ],
    )
    def test_new_verb_extracted(self, extractor, text, expected):
        """Base and inflected forms of new verbs produce a skill phrase."""
        assert extractor.extract(text) == expected

    def test_inflected_new_verb_extracted(self, extractor):
        """Inflected forms lemmatize to the new verb."""
        assert extractor.extract("Managing teams and evaluating vendors.") == [
            "evaluating vendors",
            "managing teams",
        ]

    def test_ship_as_noun_not_extracted(self, extractor):
        """'ship' tagged as a noun is not treated as an action verb."""
        assert extractor.extract("The ship sailed at dawn.") == []


class TestSkillExtractorHyphenatedNouns:
    """Hyphen-joined noun runs (#508): full span kept, dashes as punctuation rejected."""

    def test_hyphen_inside_noun_run(self, extractor):
        """Hyphen joins two nouns; following nouns stay in the run."""
        skills = extractor.extract("You will design high-performance data pipelines.")
        assert skills == ["design high-performance data pipelines"]

    def test_longest_span_over_hyphen_prefix(self, extractor):
        """The hyphen variant beats the plain 'design high' prefix (longest span wins)."""
        skills = extractor.extract("You will design high-performance systems.")
        assert skills == ["design high-performance systems"]

    def test_multiple_hyphenated_forms_two_verbs(self, extractor):
        """Two hyphenated object phrases, each under its own verb."""
        text = "You will design high-performance systems and develop fault-tolerant platforms."
        skills = extractor.extract(text)
        assert skills == ["design high-performance systems", "develop fault-tolerant platforms"]

    def test_hyphen_in_second_conjunct(self, extractor):
        """Hyphen in the second coordinated noun run extends the coordinated span."""
        skills = extractor.extract("You will design systems and high-performance platforms.")
        assert skills == ["design systems and high-performance platforms"]

    def test_hyphen_in_first_conjunct(self, extractor):
        """Hyphen in the first coordinated noun run keeps the 'and' conjunct (#498 shape)."""
        skills = extractor.extract("Design high-performance systems and platforms.")
        assert skills == ["design high-performance systems and platforms"]

    def test_plain_nouns_unchanged(self, extractor):
        """No hyphen: plain noun runs extract exactly as before."""
        skills = extractor.extract("You will design machine learning systems.")
        assert skills == ["design machine learning systems"]

    def test_coordinated_nouns_without_hyphen_unchanged(self, extractor):
        """#498 coordinated behaviour is intact when no hyphen is present."""
        text = "Lead data science and platform teams building services in Python and Docker."
        assert extractor.extract(text) == ["building services", "lead data science and platform teams"]

    def test_spaced_hyphen_is_punctuation(self, extractor):
        """A dash set off by spaces ends the span; it does not join nouns."""
        assert extractor.extract("You will design systems - build tools.") == ["design systems"]

    def test_spaced_hyphen_between_verb_and_noun(self, extractor):
        """'design - build' has no noun run before the dash, so no skill is produced."""
        assert extractor.extract("You will design - build systems.") == []

    def test_spaced_hyphen_after_prefix(self, extractor):
        """Spaced hyphen after a noun run does not join; plain prefix is kept."""
        assert extractor.extract("You will design build - systems.") == ["design build"]

    def test_unspaced_em_dash_not_joined(self, extractor):
        """Em dash is a separate token and never joins a noun run."""
        skills = extractor.extract("You will design systems—build tools.")
        assert skills == ["design systems"]

    def test_unspaced_en_dash_not_joined(self, extractor):
        """En dash is a separate token and never joins a noun run."""
        skills = extractor.extract("You will design systems–build tools.")
        assert skills == ["design systems"]

    def test_en_dash_inside_compound_not_joined(self, extractor):
        """En dash inside a compound is not treated as an intra-word hyphen."""
        skills = extractor.extract("You will design high\u2013performance systems.")
        assert "design high-performance systems" not in skills
        assert all("\u2013" not in s and "\u2014" not in s for s in skills)


class TestSkillExtractorCoordination:
    """Coordinated object spans after a skill verb (#509, extends #498 'and').

    Span semantics. HEAD = verb [connector] noun run (at most one glued hyphen
    join), as before. A CONJUNCT is a noun run of the same form. The span grows
    from the head through a chain of conjuncts:

    - "and" / "or" join conjuncts:
        "lead data or ML teams"            -> "lead data or ml teams"
    - Serial list closed by a conjunction ("A, B, and C" or "A, B and C"):
        "lead data, platform, and ML teams" -> one span (Oxford comma optional)
    - Mixed "and"/"or" chains merge:
        "lead data and ML or cloud teams"  -> one span
    - A conjunction followed by a VERB never merges (#498 rule, now for "or"):
        "build or develop data pipelines"  -> "develop data pipelines" only
        "design systems or develop platforms" -> two spans
    - A bare comma is punctuation unless a conjunction-led conjunct follows it.
        "lead data science, platform teams" -> "lead data science"
        "design systems, platforms, and develop tools"
                                           -> "design systems", "develop tools"
    - Hyphen joins inside any conjunct stay in the span (#508).
    - Spaced dash ("platforms - build") is punctuation and ends the span.
    """

    def test_or_conjunct_merges(self, extractor):
        """'or' between noun runs is a coordinated object: one span."""
        assert extractor.extract("You will lead data or ML teams.") == ["lead data or ml teams"]

    def test_or_before_verb_not_merged(self, extractor):
        """'or' followed by a verb stays two verbs; no 'build or develop' span."""
        assert extractor.extract("You will build or develop data pipelines.") == ["develop data pipelines"]

    def test_or_after_head_before_verb_not_merged(self, extractor):
        """'or' + verb after a complete head keeps two separate spans."""
        assert extractor.extract("You will design systems or develop platforms.") == [
            "design systems",
            "develop platforms",
        ]

    def test_serial_list_with_oxford_comma(self, extractor):
        """'A, B, and C' is one coordinated span."""
        assert extractor.extract("You will lead data, platform, and ML teams.") == ["lead data, platform, and ml teams"]

    def test_serial_list_without_oxford_comma(self, extractor):
        """'A, B and C' (no comma before the final conjunction) is one span."""
        assert extractor.extract("You will lead data, platform and ML teams.") == ["lead data, platform and ml teams"]

    def test_serial_list_with_or(self, extractor):
        """A serial list may be closed by 'or'."""
        assert extractor.extract("You will lead data, platform, or ML teams.") == ["lead data, platform, or ml teams"]

    def test_mixed_and_or_chain_merges(self, extractor):
        """Mixed 'and'/'or' conjuncts form one coordinated noun span."""
        assert extractor.extract("You will lead data and ML or cloud teams.") == ["lead data and ml or cloud teams"]

    def test_chained_and_merges(self, extractor):
        """A chain of 'and' conjuncts is one span, not only the first pair."""
        assert extractor.extract("You will lead data and platform and ML teams.") == [
            "lead data and platform and ml teams"
        ]

    def test_comma_without_conjunction_not_merged(self, extractor):
        """A bare comma between noun runs is punctuation: the span stops at the comma."""
        assert extractor.extract("You will lead data science, platform teams.") == ["lead data science"]

    def test_comma_tail_before_verb_not_merged(self, extractor):
        """Comma tail closed by 'and' + verb commits nothing; the verb is its own span."""
        assert extractor.extract("You will design systems, platforms, and develop tools.") == [
            "design systems",
            "develop tools",
        ]

    def test_comma_tail_after_committed_conjunct_not_merged(self, extractor):
        """Text after the committed 'and' conjunct, separated by a bare comma, is not merged."""
        assert extractor.extract("You will lead data and platform teams, building services.") == [
            "lead data and platform teams",
        ]

    def test_serial_list_with_hyphen_conjunct(self, extractor):
        """Hyphen join inside a serial-list conjunct keeps the full span (#508)."""
        assert extractor.extract("You will lead data, high-performance platform, and ML teams.") == [
            "lead data, high-performance platform, and ml teams"
        ]

    def test_or_with_hyphen_conjunct(self, extractor):
        """Hyphen join inside an 'or' conjunct keeps the full span (#508)."""
        assert extractor.extract("You will design systems or high-performance platforms.") == [
            "design systems or high-performance platforms"
        ]

    def test_hyphen_in_head_with_or_conjunct(self, extractor):
        """Hyphen in the head noun run plus an 'or' conjunct (longest span wins)."""
        assert extractor.extract("You will design high-performance systems or platforms.") == [
            "design high-performance systems or platforms"
        ]

    def test_spaced_dash_in_serial_list_is_punctuation(self, extractor):
        """A spaced dash after an uncommitted comma tail ends the span (#508)."""
        assert extractor.extract("You will design systems, platforms - build tools.") == ["design systems"]

    def test_498_and_coordination_unchanged(self, extractor):
        """#498 regression: 'and' coordinated objects and 'and' + verb split."""
        text = "Lead data science and platform teams building services in Python and Docker."
        assert extractor.extract(text) == ["building services", "lead data science and platform teams"]
        assert extractor.extract("You will design systems and develop platforms.") == [
            "design systems",
            "develop platforms",
        ]

    def test_508_hyphen_regression(self, extractor):
        """#508 regression: hyphenated head and hyphenated 'and' conjunct."""
        assert extractor.extract("You will design high-performance distributed systems.") == [
            "design high-performance distributed systems"
        ]
        assert extractor.extract("Design high-performance systems and platforms.") == [
            "design high-performance systems and platforms"
        ]


class TestSkillExtractorVerbTaggedNoun:
    """Skill verbs tagged NOUN after 'and'/'or' (#511).

    spaCy sometimes tags a coordinated verb as NOUN (dep ``conj``): "... GCP and
    ship Terraform modules". The Matcher needs VERB, so such a token starts its own
    match only when its lemma is in SKILL_VERBS, its dep is ``conj``, and an object
    noun group follows it (optionally after one connector). Without an object
    ("the ship and crew") or with a non-conj dep ("Hiring the crew and ship
    captains") it stays a noun.

    A verb-tagged-NOUN conjunct is never merged into the previous span: it is its
    own skill, the same as a verb conjunct ("design systems and develop platforms").

    The skill verb must also govern the coordination somewhere up the parse, so a
    noun coordination under another verb ("Our team includes the design and build
    managers") is not matched.

    Known limitation (not fixed): the guard needs spaCy dep ``conj``. When the parse
    tags the verb as ``compound`` instead, it is not split out, e.g. "You will lead
    data and ship terraform modules." stays one span, and "design systems or build
    platforms" merges. These are parser variants, not covered by the guard.
    """

    def test_s2_verb_after_and_extracts_object(self, extractor):
        """s2 eval sentence: 'ship' conj after 'GCP and' yields 'ship terraform modules'."""
        text = "Manage Kafka clusters on GCP and ship Terraform modules for the platform team."
        assert extractor.extract(text) == ["manage kafka clusters", "ship terraform modules"]

    def test_noun_use_ship_and_crew_not_matched(self, extractor):
        """'the ship and crew' is a noun coordination: no skill is produced."""
        assert extractor.extract("Stakeholders across the ship and crew need data.") == []

    def test_noun_use_ship_and_crew_after_verb_not_matched(self, extractor):
        """'brief the ship and crew' has no verb-tagged-NOUN start: no skill."""
        assert extractor.extract("Brief the ship and crew on the plan.") == []

    def test_compound_noun_modifier_not_matched(self, extractor):
        """'ship' as a compound modifier (dep not conj) never starts a match."""
        assert extractor.extract("Hiring the crew and ship captains for the fleet.") == []
        assert extractor.extract("We value the test and ship process.") == []

    def test_comma_and_verb_tagged_noun_splits(self, extractor):
        """'lead data, and build platforms': 'build' (NOUN) is not merged into 'lead data'."""
        assert extractor.extract("You will lead data, and build platforms.") == [
            "build platforms",
            "lead data",
        ]

    def test_and_verb_tagged_noun_splits(self, extractor):
        """'lead data and build platforms': 'build' (NOUN) starts its own span."""
        assert extractor.extract("You will lead data and build platforms.") == [
            "build platforms",
            "lead data",
        ]

    def test_verb_tagged_noun_chain_stays_one_span(self, extractor):
        """A verb-tagged-NOUN start extends through its own 'and' conjuncts (#509 walker)."""
        text = "Manage Kafka clusters on GCP and ship Terraform modules and Helm charts."
        assert extractor.extract(text) == ["manage kafka clusters", "ship terraform modules and helm charts"]

    def test_or_verb_tagged_noun_not_merged_with_head(self, extractor):
        """'or' + verb-tagged-NOUN after a head: two spans, the verb is not merged (#509 'or' rule)."""
        text = "Manage Kafka clusters on GCP or ship Terraform modules."
        assert extractor.extract(text) == ["manage kafka clusters", "ship terraform modules"]

    def test_ambiguous_verbs_as_nouns_not_matched(self, extractor):
        """Ambiguous verbs (ship/build/manage/design/test) used as nouns are not skills."""
        assert extractor.extract("Our crew and ship maintenance team is hiring.") == []

    def test_noun_use_design_and_build_managers_not_matched(self, extractor):
        """'design and build managers' is a noun coordination under 'includes' (not a skill verb).

        spaCy tags 'build' as conj NOUN with an object after it, but no skill verb
        governs the coordination, so no span is produced (#511 follow-up).
        """
        assert extractor.extract("Our team includes the design and build managers.") == []
        assert extractor.extract("Our team includes design and build managers.") == []

    def test_det_object_and_verb_tagged_noun_splits(self, extractor):
        """A determiner in the object ('lead the data') does not block a verb-tagged-NOUN split."""
        assert extractor.extract("You will lead the data and build platforms.") == [
            "build platforms",
            "lead the data",
        ]

    def test_509_regressions_unchanged(self, extractor):
        """#509 spans are unchanged: serial lists, 'or' chains, hyphen conjuncts."""
        assert extractor.extract("You will lead data, platform, and ML teams.") == ["lead data, platform, and ml teams"]
        assert extractor.extract("You will design systems or develop platforms.") == [
            "design systems",
            "develop platforms",
        ]
        assert extractor.extract("You will lead data or ML teams.") == ["lead data or ml teams"]


class TestSkillExtractorParticiples:
    """VERB participles (VBN/VBG, dep amod) inside a skill noun run (#523).

    spaCy tags "distributed" in "design high-performance distributed systems" as
    VERB (amod), which used to end the noun run at "performance". A participle that
    modifies the following noun is part of the run when a noun follows it. A
    participle with no noun after it, an ADJ modifier ("distributed systems" after
    "We build and deploy") and a participle used as a clause (dep acl) are unchanged.
    """

    def test_participle_completes_hyphen_run(self, extractor):
        """'distributed' (VERB amod) joins the hyphenated run: the full span is kept."""
        assert extractor.extract("design high-performance distributed systems") == [
            "design high-performance distributed systems"
        ]

    def test_participle_completes_run_in_sentence(self, extractor):
        """Same span inside a sentence; the #508 pin for this sentence is updated (#523)."""
        assert extractor.extract("You will design high-performance distributed systems.") == [
            "design high-performance distributed systems"
        ]

    def test_participle_completes_run_in_conjunct(self, extractor):
        """A participle inside a verb conjunct's run is kept in the conjunct span."""
        assert extractor.extract("Build and deploy high-performance distributed systems") == [
            "deploy high-performance distributed systems"
        ]

    def test_adj_modifier_before_noun_unchanged(self, extractor):
        """'distributed' tagged ADJ (dep amod) after 'We build and deploy' is unchanged."""
        assert extractor.extract("We build and deploy distributed systems") == ["deploy distributed systems"]

    def test_participle_used_as_clause_not_absorbed(self, extractor):
        """'used' (dep acl, no noun object in the run) does not extend the span."""
        assert extractor.extract("Design high-performance systems used internally by customers") == [
            "design high-performance systems"
        ]

    def test_participle_before_verb_conjunct_not_absorbed(self, extractor):
        """A verb conjunct after 'and' is not extended by a following participle.

        Known gap (not fixed in #523): 'develop distributed platforms' gives no
        span because a verb head cannot start with a participle; the head span is kept.
        """
        assert extractor.extract("Design high-performance systems and develop distributed platforms") == [
            "design high-performance systems",
        ]

    def test_participle_without_following_noun_unchanged(self, extractor):
        """A participle-led run needs a noun after it: 'Use distributed systems' stays a no-match."""
        assert extractor.extract("Use distributed systems across the stack") == []


class TestSkillExtractorGluedCompounds:
    """Glued hyphen compounds with a function word or participle inside (#556).

    spaCy splits "state-of-the-art" and "end-to-end" into noun, ADP, and DET tokens
    joined by "-", so the noun run stopped at the preposition. "data-driven" puts a
    VERB participle (dep amod) after the hyphen; a glued participle is not a skill
    verb, so it no longer starts a match ("driven platform"). A compound without a
    skill verb ahead of it is not a skill, so it still yields no span.
    """

    def test_state_of_the_art_kept_whole(self, extractor):
        """ADP + DET inside a glued compound stay in the noun run."""
        assert extractor.extract("You will build state-of-the-art systems.") == ["build state-of-the-art systems"]

    def test_end_to_end_kept_whole(self, extractor):
        """A single ADP between two glued hyphens stays in the noun run."""
        assert extractor.extract("You will build end-to-end pipelines.") == ["build end-to-end pipelines"]

    def test_adp_compound_in_second_conjunct(self, extractor):
        """Glued ADP compounds in both verb conjuncts keep their full spans."""
        text = "You will design state-of-the-art systems and develop end-to-end platforms."
        assert extractor.extract(text) == ["design state-of-the-art systems", "develop end-to-end platforms"]

    def test_machine_to_machine_kept_whole(self, extractor):
        """Same ADP shape with a different preposition."""
        assert extractor.extract("Develop machine-to-machine protocols.") == ["develop machine-to-machine protocols"]

    def test_participle_glued_compound_kept_whole(self, extractor):
        """'data-driven' (VERB amod after a glued hyphen) joins the head's noun run."""
        assert extractor.extract("You will design data-driven platforms.") == ["design data-driven platforms"]

    def test_participle_glued_compound_in_conjunct(self, extractor):
        """A participle compound after 'and' joins the coordinated span (#509 chain)."""
        text = "Build end-to-end ML pipelines and data-driven platforms."
        assert extractor.extract(text) == ["build end-to-end ml pipelines and data-driven platforms"]

    def test_glued_participle_is_not_a_head_verb(self, extractor):
        """'driven' after a glued hyphen is not a skill verb: no 'driven platform' span."""
        assert extractor.extract("data-driven platform") == []
        assert extractor.extract("Work with data-driven teams.") == []

    def test_compound_without_skill_verb_unchanged(self, extractor):
        """No verb ahead of 'state-of-the-art': the generic phrase is not extracted."""
        assert extractor.extract("state-of-the-art") == []
        assert extractor.extract("Experience with state-of-the-art techniques is a plus.") == []

    def test_spaced_dash_still_ends_span_with_adp(self, extractor):
        """Spaced dashes are punctuation even when a function word sits between them."""
        assert extractor.extract("You will design systems - to - end tools.") == ["design systems"]


class TestSkillExtractorParticipleLedHead:
    """A sentence-initial skill verb that spaCy tags NOUN, followed by a participle (#558).

    "Design distributed systems" at the start of a sentence parses as Design (NOUN,
    npadvmod) + distributed (VERB, amod) + systems, so no action verb starts a match and
    the span was lost. The head is a skill-verb lemma tagged NOUN at a sentence start,
    followed by a participle modifier and a noun run. Guards: the head must start the
    sentence (a mid-sentence verb use is unchanged), the participle must not itself be
    a skill verb ("Lead managed services" keeps "managed services"), and a following verb
    conjunct still ends the span.
    """

    def test_sentence_initial_participle_head_kept(self, extractor):
        """'Design distributed systems' without a sentence after it gives the full span."""
        assert extractor.extract("Design distributed systems") == ["design distributed systems"]

    def test_sentence_initial_participle_head_in_sentence(self, extractor):
        """Same span with a trailing period and a following sentence."""
        assert extractor.extract("Design distributed systems. Build APIs.") == [
            "build apis",
            "design distributed systems",
        ]

    def test_participle_head_extends_through_purpose_clause(self, extractor):
        """The span stops at the noun run; 'to scale across regions' is not absorbed."""
        assert extractor.extract("Design distributed systems to scale across regions.") == [
            "design distributed systems",
            "scale across regions",
        ]

    def test_participle_head_then_verb_conjunct_stops(self, extractor):
        """A verb conjunct after 'and' is its own match, not merged into the participle head."""
        assert extractor.extract("Design distributed systems and build APIs.") == [
            "build apis",
            "design distributed systems",
        ]

    def test_participle_head_with_hyphen_run_unchanged(self, extractor):
        """A head whose run already has a hyphen join is matched as before (#523)."""
        assert extractor.extract("Design high-performance distributed systems") == [
            "design high-performance distributed systems"
        ]

    def test_mid_sentence_participle_verb_use_not_matched(self, extractor):
        """'designed' after a subject is a past-tense verb, not a participle-led head."""
        assert extractor.extract("The team designed distributed systems last year.") == []

    def test_gerund_after_preposition_not_matched(self, extractor):
        """'Experience designing distributed systems' has no NOUN head at a sentence start."""
        assert extractor.extract("Experience designing distributed systems.") == []

    def test_sentence_initial_participle_verb_not_matched(self, extractor):
        """'Designed' sentence-initial is tagged VERB (participle), so no head span is made."""
        assert extractor.extract("Designed distributed systems are key.") == []

    def test_participle_that_is_skill_verb_keeps_existing_span(self, extractor):
        """'managed' is itself a skill verb, so 'Lead managed services' keeps 'managed services'."""
        assert extractor.extract("Lead managed services.") == ["managed services"]

    def test_glued_compound_after_head_unchanged(self, extractor):
        """A function word inside a glued compound after the head is not matched by this pattern."""
        assert extractor.extract("Design end-to-end distributed systems") == []


class TestSkillExtractorAdjectiveListComma:
    """A bare comma between premodifiers of one head noun stays in the span (#557).

    "design fault-tolerant, low-latency services": the comma separates adjectives, not noun
    conjuncts. The #509 rule (bare comma is punctuation) would cut the run at the comma. The
    adjective-list branch keeps the comma only when the token before it is adjectival (ADJ,
    amod participle, or a glued compound ending in one) and the list ends at a plain noun
    head. A noun before the comma, a clause after the head, and a spaced dash keep #509.
    """

    def test_adjective_pair_before_noun_head(self, extractor):
        """'fault-tolerant, low-latency services' is one premodifier list on one head."""
        assert extractor.extract("You will design fault-tolerant, low-latency services.") == [
            "design fault-tolerant, low-latency services"
        ]

    def test_three_adjectives_before_noun_head(self, extractor):
        """Two bare commas in an adjective list close on the noun head."""
        assert extractor.extract("You will build secure, reliable, scalable services in Python.") == [
            "build secure, reliable, scalable services"
        ]

    def test_adjective_pair_plain_words(self, extractor):
        """Plain single-word adjectives form the same list."""
        assert extractor.extract("You will design clean, maintainable code.") == ["design clean, maintainable code"]

    def test_hyphen_compound_before_comma(self, extractor):
        """A glued compound before the comma ('high-performance') is adjectival."""
        assert extractor.extract("You will design high-performance, low-latency systems.") == [
            "design high-performance, low-latency systems"
        ]

    def test_hyphen_compound_second_segment(self, extractor):
        """A glued compound as the second segment ('cross-functional') still ends at the noun."""
        assert extractor.extract("You will lead agile, cross-functional teams.") == [
            "lead agile, cross-functional teams"
        ]

    def test_adjective_list_closed_by_conjunction(self, extractor):
        """A conjunction-closed adjective list keeps the existing span (no regression)."""
        assert extractor.extract("You will design fault-tolerant, low-latency, and scalable services.") == [
            "design fault-tolerant, low-latency, and scalable services"
        ]

    def test_adjective_list_then_trailing_clause(self, extractor):
        """A verb-led clause after the list is its own match and is not absorbed."""
        assert extractor.extract("You will design fault-tolerant, low-latency services, building APIs.") == [
            "building apis",
            "design fault-tolerant, low-latency services",
        ]

    def test_adjective_list_then_spaced_dash_ends_span(self, extractor):
        """A spaced dash after the list still ends the span (#508 spaced-dash rule)."""
        assert extractor.extract("You will design fault-tolerant, low-latency services - build tools.") == [
            "design fault-tolerant, low-latency services"
        ]

    def test_adjective_comma_without_noun_head_unchanged(self, extractor):
        """A list with no noun head keeps only the head before the comma."""
        assert extractor.extract("You will design fault-tolerant, low-latency.") == ["design fault-tolerant"]

    def test_noun_before_comma_keeps_509_rule(self, extractor):
        """A noun before the comma is a noun conjunct: the span stops at the comma (#509)."""
        assert extractor.extract("You will design systems, low-latency platforms.") == ["design systems"]

    def test_noun_conjunct_then_adjective_list_keeps_head(self, extractor):
        """A later comma after a noun conjunct does not open an adjective list (#557)."""
        assert extractor.extract("You will design systems, fast, reliable services.") == ["design systems"]

    def test_noun_conjunct_then_adjective_pair_keeps_head(self, extractor):
        """'design systems, scalable, reliable platforms' keeps only the head (#557)."""
        assert extractor.extract("You will design systems, scalable, reliable platforms.") == ["design systems"]

    def test_noun_before_comma_with_adjective_pair_unchanged(self, extractor):
        """'design systems, scalable and resilient' keeps the existing tentative-comma result."""
        assert extractor.extract("You will design systems, scalable and resilient.") == [
            "design systems, scalable and resilient"
        ]

    def test_serial_noun_list_unchanged(self, extractor):
        """A serial list of separate nouns with a verb conjunct is unchanged (#509)."""
        assert extractor.extract("You will design systems, platforms, and develop tools.") == [
            "design systems",
            "develop tools",
        ]

    def test_verb_after_comma_is_not_adjective(self, extractor):
        """A verb after a comma ('build tools') is its own match, not a premodifier."""
        assert extractor.extract("You will design systems, build tools.") == ["build tools", "design systems"]

    def test_list_of_separate_skills_unchanged(self, extractor):
        """A list of separate skills after a verb is unchanged."""
        assert extractor.extract("You will build APIs, services, and tools.") == ["build apis, services, and tools"]

    def test_lead_noun_list_unchanged(self, extractor):
        """A noun-led comma list ('data science, platform teams') keeps the #509 cut."""
        assert extractor.extract("You will lead data science, platform teams.") == ["lead data science"]

    def test_no_skill_verb_no_match(self, extractor):
        """Lists without a skill-verb head produce nothing."""
        assert extractor.extract("Experience with Python, Java and Kubernetes.") == []
        assert extractor.extract("No Kubernetes, and Redis.") == []

    def test_adjective_list_after_conjunction_conjunct(self, extractor):
        """A bare-comma adjective list after a 'and' conjunct stays in the span (#557)."""
        assert extractor.extract("You will design APIs and fault-tolerant, low-latency services.") == [
            "design apis and fault-tolerant, low-latency services"
        ]

    def test_adjective_list_stops_at_second_noun_conjunct(self, extractor):
        """The list ends at its first plain noun head; a later noun conjunct is not absorbed (#557)."""
        assert extractor.extract("You will design fault-tolerant, low-latency services, scalable platforms.") == [
            "design fault-tolerant, low-latency services"
        ]

    def test_empty_input_no_match(self, extractor):
        """Empty input yields no skills."""
        assert extractor.extract("") == []

    def test_trailing_comma_after_adjective_keeps_head(self, extractor):
        """A trailing comma with no following segment keeps only the head (#557)."""
        assert extractor.extract("You will design fault-tolerant,") == ["design fault-tolerant"]


class TestSkillExtractorParticipialWith:
    """Past-tense/participle "built with <tech>" names a stack, not a skill (#551).

    The action verb matched "build" whatever its tag, and the optional connector took
    "with", so "Built with Go and gRPC" was emitted. A base-form verb with "with" is a
    real skill phrase and is unchanged, as is a participle not followed by "with".
    """

    def test_built_with_stack_and_conjunct_not_extracted(self, extractor):
        """'Built with Go and gRPC' lists technologies: no 'built with' skill."""
        assert extractor.extract("Built with Go and gRPC.") == []

    def test_built_with_proper_noun_not_extracted(self, extractor):
        """'Built with Lightning' names a technology: no skill is produced."""
        assert extractor.extract("Built with Lightning.") == []

    def test_base_form_verb_with_tech_still_extracted(self, extractor):
        """Base-form 'Build ... with Python' is a skill phrase and keeps its span."""
        assert extractor.extract("Build scalable APIs with Python.") == ["build scalable apis"]

    def test_participle_without_with_still_extracted(self, extractor):
        """A participle skill verb not followed by 'with' keeps its span."""
        assert extractor.extract("Built scalable APIs with Python.") == ["built scalable apis"]
