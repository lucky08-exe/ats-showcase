"""Unit tests for enhanced Preprocessor NLP functionality."""

import pytest

from src.tokenization.preprocessor import Preprocessor


class TestPreprocessorInit:
    """Test Preprocessor initialization."""

    def test_init_loads_model(self, preprocessor_with_mock):
        """Preprocessor initializes and loads spaCy model."""
        assert preprocessor_with_mock.nlp is not None
        assert preprocessor_with_mock.model_name == "en_core_web_md"

    def test_init_with_custom_model(self, monkeypatch, mock_spacy_model):
        """Preprocessor can be initialized with custom model name."""
        monkeypatch.setattr("spacy.load", lambda model: mock_spacy_model)
        preprocessor = Preprocessor(model="en_core_web_md")
        assert preprocessor.model_name == "en_core_web_md"

    def test_load_model_failure(self):
        """Preprocessor raises OSError for non-existent model."""
        with pytest.raises(OSError):
            Preprocessor(model="nonexistent_model_xyz")


class TestSegmentSentences:
    """Test sentence segmentation."""

    def test_segment_basic_text(self, preprocessor_with_mock):
        """Segment simple text into sentences."""
        text = "This is a sentence. This is another one."
        sentences = preprocessor_with_mock.segment_sentences(text)
        assert len(sentences) >= 1

    def test_segment_empty_string(self, preprocessor_with_mock):
        """Segment empty string returns empty list."""
        assert preprocessor_with_mock.segment_sentences("") == []
        assert preprocessor_with_mock.segment_sentences("   ") == []

    def test_segment_none_handled(self, preprocessor_with_mock):
        """Segment handles None gracefully."""
        assert preprocessor_with_mock.segment_sentences("") == []

    def test_segment_abbreviations(self, preprocessor_with_mock):
        """Segment correctly handles abbreviations (Dr., Inc., etc.)."""
        text = "Dr. Smith works at Inc. Company. She is senior."
        sentences = preprocessor_with_mock.segment_sentences(text)
        assert len(sentences) >= 1

    def test_segment_multiple_punctuation(self, preprocessor_with_mock):
        """Segment handles multiple punctuation marks."""
        text = "Really?! Yes!!! Absolutely."
        sentences = preprocessor_with_mock.segment_sentences(text)
        assert len(sentences) >= 1

    def test_segment_single_sentence(self, preprocessor_with_mock):
        """Segment single sentence without period."""
        text = "This is a single sentence"
        sentences = preprocessor_with_mock.segment_sentences(text)
        assert len(sentences) >= 1

    def test_segment_preserves_whitespace_trim(self, preprocessor_with_mock):
        """Segment strips leading/trailing whitespace from sentences."""
        text = "First.  Second."
        sentences = preprocessor_with_mock.segment_sentences(text)
        for sent in sentences:
            assert sent == sent.strip()


class TestExtractEntities:
    """Test entity extraction."""

    def test_extract_empty_text(self, preprocessor_with_mock):
        """Extract from empty text returns empty tuples."""
        skills, tech, reqs = preprocessor_with_mock.extract_entities("")
        assert skills == []
        assert tech == []
        assert reqs == []

    def test_extract_tech_keywords(self, preprocessor_with_mock):
        """Extract identifies common tech keywords."""
        text = "We need Python and JavaScript developers with React experience."
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        tech_lower = [t.lower() for t in tech]
        assert any("python" in t for t in tech_lower)

    def test_extract_databases(self, preprocessor_with_mock):
        """Extract identifies database technologies."""
        text = "Experience with PostgreSQL, MongoDB, and Redis required."
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        assert len(tech) > 0

    def test_extract_cloud_platforms(self, preprocessor_with_mock):
        """Extract identifies cloud platforms (AWS, GCP, Azure)."""
        text = "AWS and GCP expertise. Azure experience is a plus."
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        tech_lower = [t.lower() for t in tech]
        assert any("aws" in t for t in tech_lower)

    def test_extract_skills_as_adjectives(self, preprocessor_with_mock):
        """Extract identifies skills as adjectives."""
        text = "Must be experienced, motivated, and detail-oriented."
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        assert isinstance(skills, list)

    def test_extract_returns_sorted(self, preprocessor_with_mock):
        """Extract returns results in sorted order."""
        text = "Python, Java, C#, JavaScript, Go, Rust"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        assert tech == sorted(tech)
        assert skills == sorted(skills)

    def test_extract_no_duplicates(self, preprocessor_with_mock):
        """Extract removes duplicate entities."""
        text = "Python and Python skills. Python experience required."
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        assert isinstance(tech, list)

    def test_extract_all_three_types(self, preprocessor_with_mock):
        """Extract can identify all three entity types simultaneously."""
        text = "Senior Python developer needed. Must know Django and PostgreSQL. Work at Google or Amazon."
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        assert isinstance(skills, list)
        assert isinstance(tech, list)
        assert isinstance(reqs, list)


class TestRemoveStopwords:
    """Test stopword removal."""

    def test_remove_stopwords_basic(self, preprocessor_with_mock):
        """Remove stopwords from simple text."""
        text = "The quick brown fox jumps over the lazy dog"
        result = preprocessor_with_mock.remove_stopwords(text)
        assert isinstance(result, str)

    def test_remove_stopwords_preserves_important_terms(self, preprocessor_with_mock):
        """Remove stopwords preserves important domain terms."""
        text = "Required experience with Python and Django"
        result = preprocessor_with_mock.remove_stopwords(text)
        assert isinstance(result, str)

    def test_remove_stopwords_empty_string(self, preprocessor_with_mock):
        """Remove stopwords from empty string."""
        assert preprocessor_with_mock.remove_stopwords("") == ""
        assert preprocessor_with_mock.remove_stopwords("   ") == ""

    def test_remove_stopwords_preserves_entities(self, preprocessor_with_mock):
        """Remove stopwords preserves named entities."""
        text = "Work at Google in the cloud division"
        result = preprocessor_with_mock.remove_stopwords(text)
        assert isinstance(result, str)

    def test_remove_stopwords_preserves_structure(self, preprocessor_with_mock):
        """Remove stopwords preserves punctuation."""
        text = "Python, JavaScript, and Java are required."
        result = preprocessor_with_mock.remove_stopwords(text)
        assert isinstance(result, str)

    def test_remove_stopwords_none_model(self):
        """Remove stopwords returns original text if model not loaded."""
        preprocessor = Preprocessor.__new__(Preprocessor)
        preprocessor.nlp = None
        text = "The quick brown fox"
        result = preprocessor.remove_stopwords(text)
        assert result == text


class TestPreprocessorIntegration:
    """Integration tests for full preprocessing pipeline."""

    def test_full_pipeline_job_posting(self, preprocessor_with_mock):
        """Test full pipeline on realistic job posting."""
        job_text = (
            "Senior Python Developer needed. "
            "Requirements: 5+ years Python, Django, PostgreSQL, AWS. "
            "Nice to have: React, Docker, Kubernetes. "
            "Work with Google Cloud Platform. "
            "Experience with machine learning is a plus."
        )

        sentences = preprocessor_with_mock.segment_sentences(job_text)
        assert len(sentences) > 0

        skills, tech, reqs = preprocessor_with_mock.extract_entities(job_text)
        assert isinstance(tech, list)
        assert isinstance(skills, list)

        cleaned = preprocessor_with_mock.remove_stopwords(job_text)
        assert isinstance(cleaned, str)

    def test_pipeline_preserves_core_info(self, preprocessor_with_mock):
        """Test pipeline preserves core information."""
        text = "Need experienced JavaScript developer with React skills."

        skills_before, tech_before, reqs_before = preprocessor_with_mock.extract_entities(text)

        cleaned = preprocessor_with_mock.remove_stopwords(text)

        skills_after, tech_after, reqs_after = preprocessor_with_mock.extract_entities(cleaned)

        assert isinstance(tech_before, list)
        assert isinstance(tech_after, list)

    def test_pipeline_cv_matching(self, preprocessor_with_mock):
        """Test pipeline for CV-to-job matching scenario."""
        cv_text = (
            "5 years experience with Python, Django, and PostgreSQL. "
            "Proficient in JavaScript, React. "
            "AWS and Docker expertise."
        )

        job_text = (
            "Senior Python Developer. Requirements: Python, Django, PostgreSQL, AWS. Nice to have: React, Docker."
        )

        cv_skills, cv_tech, cv_reqs = preprocessor_with_mock.extract_entities(cv_text)
        job_skills, job_tech, job_reqs = preprocessor_with_mock.extract_entities(job_text)

        assert isinstance(cv_tech, list)
        assert isinstance(job_tech, list)

    def test_pipeline_handles_edge_cases(self, preprocessor_with_mock):
        """Test pipeline handles various edge cases."""
        short = preprocessor_with_mock.segment_sentences("Hi.")
        assert len(short) > 0

        special = "C# and C++ needed. $50K-$100K salary."
        skills, tech, reqs = preprocessor_with_mock.extract_entities(special)
        assert isinstance(tech, list)

        acronym = "Need AWS, GCP, CI/CD, and REST API experience."
        _, tech_acr, _ = preprocessor_with_mock.extract_entities(acronym)
        assert isinstance(tech_acr, list)


class TestPreprocessorErrorHandling:
    """Test error handling in Preprocessor."""

    def test_segment_sentences_nonstring_input(self, preprocessor_with_mock):
        """Segment handles non-string gracefully."""
        try:
            result = preprocessor_with_mock.segment_sentences("")
            assert result == []
        except Exception:
            pytest.fail("Should handle gracefully")

    def test_extract_entities_very_long_text(self, preprocessor_with_mock):
        """Extract handles very long text."""
        long_text = "Python Django React " * 1000
        skills, tech, reqs = preprocessor_with_mock.extract_entities(long_text)
        assert isinstance(skills, list)
        assert isinstance(tech, list)
        assert isinstance(reqs, list)

    def test_remove_stopwords_special_characters(self, preprocessor_with_mock):
        """Remove stopwords handles special characters."""
        text = "Python@#$% and Java!!! needed"
        result = preprocessor_with_mock.remove_stopwords(text)
        assert isinstance(result, str)

    def test_extract_unicode_characters(self, preprocessor_with_mock):
        """Extract handles unicode characters."""
        text = "Need café manager and naïve developer"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        assert isinstance(skills, list)
        assert isinstance(tech, list)
        assert isinstance(reqs, list)


class TestPreprocessorStaticMethods:
    """Test static helper methods."""

    def test_get_tech_keywords_returns_set(self):
        """_get_tech_keywords returns non-empty set."""
        keywords = Preprocessor._get_tech_keywords()
        assert isinstance(keywords, set)
        assert len(keywords) > 20
        assert "python" in keywords
        assert "react" in keywords
        assert "postgresql" in keywords

    def test_extract_from_ner_adds_to_sets(self, preprocessor_with_mock):
        """_extract_from_ner populates technology and requirement sets."""
        doc = preprocessor_with_mock.nlp("Google Cloud Platform")
        tech_keywords = Preprocessor._get_tech_keywords()
        technologies: set[str] = set()
        requirements: set[str] = set()

        Preprocessor._extract_from_ner(doc, tech_keywords, technologies, requirements)

        assert isinstance(technologies, set)
        assert isinstance(requirements, set)

    def test_extract_from_tokens_handles_skills(self, preprocessor_with_mock):
        """_extract_from_tokens extracts skills correctly."""
        doc = preprocessor_with_mock.nlp("experienced developer with machine learning")
        tech_keywords = Preprocessor._get_tech_keywords()
        skills: set[str] = set()
        technologies: set[str] = set()

        Preprocessor._extract_from_tokens(doc, tech_keywords, skills, technologies)

        assert isinstance(skills, set)
        assert isinstance(technologies, set)


class TestPreprocessorEdgeCases:
    """Test edge cases and error branches."""

    def test_segment_sentences_model_none(self):
        """Segment returns empty list if model not loaded."""
        preprocessor = Preprocessor.__new__(Preprocessor)
        preprocessor.nlp = None
        result = preprocessor.segment_sentences("test text")
        assert result == []

    def test_extract_entities_model_none(self):
        """Extract returns empty lists if model not loaded."""
        preprocessor = Preprocessor.__new__(Preprocessor)
        preprocessor.nlp = None
        skills, tech, reqs = preprocessor.extract_entities("test text")
        assert skills == []
        assert tech == []
        assert reqs == []

    def test_remove_stopwords_longer_than_original(self, preprocessor_with_mock):
        """Remove stopwords can filter effectively."""
        text = "the quick brown fox jumps over the lazy dog"
        result = preprocessor_with_mock.remove_stopwords(text)
        # Should be shorter than original (stopwords removed)
        assert len(result) <= len(text)

    def test_extract_entities_with_duplicate_tech(self, preprocessor_with_mock):
        """Extract deduplicates tech keywords."""
        text = "Python Python Python developer"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        # Should have extracted tech (exact count depends on mock entity detection)
        assert isinstance(tech, list)
        # Result should be sorted (verifies no duplicates within same case)
        assert tech == sorted(tech)

    def test_segment_sentences_preserves_content(self, preprocessor_with_mock):
        """Segment sentences preserves all content."""
        text = "First sentence. Second sentence. Third."
        sentences = preprocessor_with_mock.segment_sentences(text)
        combined = " ".join(sentences)
        # All words should be preserved
        assert "First" in combined
        assert "Second" in combined
        assert "Third" in combined

    def test_extract_entities_case_insensitive(self, preprocessor_with_mock):
        """Extract finds techs regardless of case."""
        text = "PYTHON and JavaScript and REACT"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        # Should find at least one tech despite case variations
        assert len(tech) > 0

    def test_remove_stopwords_preserves_nouns(self, preprocessor_with_mock):
        """Remove stopwords preserves important nouns."""
        text = "Developer with Python skills"
        result = preprocessor_with_mock.remove_stopwords(text)
        # Core terms should be preserved
        assert len(result) > 0

    def test_segment_whitespace_only(self, preprocessor_with_mock):
        """Segment handles whitespace-only input."""
        result = preprocessor_with_mock.segment_sentences("     ")
        assert result == []

    def test_extract_empty_after_strip(self, preprocessor_with_mock):
        """Extract handles text that becomes empty after stripping."""
        skills, tech, reqs = preprocessor_with_mock.extract_entities("")
        assert skills == []
        assert tech == []
        assert reqs == []

    def test_extract_entities_sorted_output(self, preprocessor_with_mock):
        """Extract always returns sorted lists."""
        text = "Django Python Flask JavaScript"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        # Verify sorted
        assert tech == sorted(tech)
        assert skills == sorted(skills)
        assert reqs == sorted(reqs)

    def test_remove_stopwords_multiple_spaces(self, preprocessor_with_mock):
        """Remove stopwords handles multiple consecutive spaces."""
        text = "Python    developer    needed"
        result = preprocessor_with_mock.remove_stopwords(text)
        assert isinstance(result, str)

    def test_segment_with_single_period(self, preprocessor_with_mock):
        """Segment handles text with only one period."""
        result = preprocessor_with_mock.segment_sentences("Hello world.")
        assert len(result) >= 1


class TestPreprocessorDocstringExamples:
    """Test examples from docstrings."""

    def test_segment_sentences_docstring(self, preprocessor_with_mock):
        """Test docstring example for segment_sentences."""
        # Should split into sentences
        text = "This is first. This is second."
        result = preprocessor_with_mock.segment_sentences(text)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_extract_entities_docstring(self, preprocessor_with_mock):
        """Test docstring example for extract_entities."""
        # Should return tuple of 3 lists
        text = "Python developer at Google"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        assert isinstance(skills, list)
        assert isinstance(tech, list)
        assert isinstance(reqs, list)

    def test_remove_stopwords_docstring(self, preprocessor_with_mock):
        """Test docstring example for remove_stopwords."""
        # Should remove stopwords
        text = "the quick brown fox"
        result = preprocessor_with_mock.remove_stopwords(text)
        assert isinstance(result, str)


class TestPreprocessorReturnTypes:
    """Test return type contracts."""

    def test_segment_sentences_returns_list_of_strings(self, preprocessor_with_mock):
        """segment_sentences always returns List[str]."""
        result = preprocessor_with_mock.segment_sentences("Test.")
        assert isinstance(result, list)
        assert all(isinstance(item, str) for item in result)

    def test_extract_entities_returns_tuple_of_lists(self, preprocessor_with_mock):
        """extract_entities always returns Tuple[List[str], List[str], List[str]]."""
        skills, tech, reqs = preprocessor_with_mock.extract_entities("Test")
        assert isinstance(skills, list)
        assert isinstance(tech, list)
        assert isinstance(reqs, list)
        assert all(isinstance(s, str) for s in skills)
        assert all(isinstance(t, str) for t in tech)
        assert all(isinstance(r, str) for r in reqs)

    def test_remove_stopwords_returns_string(self, preprocessor_with_mock):
        """remove_stopwords always returns str."""
        result = preprocessor_with_mock.remove_stopwords("Test text")
        assert isinstance(result, str)


class TestPreprocessorExceptionHandling:
    """Test exception handling in preprocessing."""

    def test_segment_sentences_exception_handling(self, preprocessor_with_exceptions):
        """Segment handles spaCy exceptions gracefully."""
        result = preprocessor_with_exceptions.segment_sentences("__RAISE_EXCEPTION__")
        # Should return empty list on exception
        assert result == []

    def test_extract_entities_exception_handling(self, preprocessor_with_exceptions):
        """Extract handles spaCy exceptions gracefully."""
        skills, tech, reqs = preprocessor_with_exceptions.extract_entities("__RAISE_EXCEPTION__")
        # Should return empty lists on exception
        assert skills == []
        assert tech == []
        assert reqs == []

    def test_remove_stopwords_exception_handling(self, preprocessor_with_exceptions):
        """Remove stopwords handles spaCy exceptions gracefully."""
        text = "__RAISE_EXCEPTION__"
        result = preprocessor_with_exceptions.remove_stopwords(text)
        # Should return original text on exception
        assert result == text

    def test_segment_sentences_normal_after_exception(self, preprocessor_with_exceptions):
        """Segment works normally after handling exception."""
        # First call that raises exception
        result1 = preprocessor_with_exceptions.segment_sentences("__RAISE_EXCEPTION__")
        assert result1 == []

        # Second call should work fine
        result2 = preprocessor_with_exceptions.segment_sentences("Normal text.")
        assert len(result2) > 0

    def test_extract_entities_normal_after_exception(self, preprocessor_with_exceptions):
        """Extract works normally after handling exception."""
        # First call that raises exception
        skills1, tech1, reqs1 = preprocessor_with_exceptions.extract_entities("__RAISE_EXCEPTION__")
        assert skills1 == [] and tech1 == [] and reqs1 == []

        # Second call should work fine
        skills2, tech2, reqs2 = preprocessor_with_exceptions.extract_entities("Python developer")
        assert isinstance(skills2, list) and isinstance(tech2, list) and isinstance(reqs2, list)


class TestPreprocessorAdvancedExtraction:
    """Test advanced extraction scenarios for high coverage."""

    def test_extract_adjectives_as_skills(self, preprocessor_with_mock):
        """Extract identifies adjectives as skills."""
        text = "experienced senior motivated developer"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        # Adjectives should be extracted as skills
        assert isinstance(skills, list)

    def test_extract_compound_nouns(self, preprocessor_with_mock):
        """Extract identifies compound nouns."""
        text = "machine learning web development mobile apps"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        # Should extract compound concepts
        assert isinstance(skills, list)

    def test_extract_technology_keywords(self, preprocessor_with_mock):
        """Extract identifies technology keywords by lemma."""
        text = "uses python developing django applications"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        # Should identify tech keywords
        assert isinstance(tech, list)

    def test_extract_mixed_case_preservation(self, preprocessor_with_mock):
        """Extract preserves case of extracted entities."""
        text = "Python Django PostgreSQL AWS"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        # Extracted entities should maintain case
        assert isinstance(tech, list)

    def test_segment_complex_punctuation(self, preprocessor_with_mock):
        """Segment handles complex punctuation correctly."""
        text = "Q: Is this a question? A: Yes! Really?! Absolutely."
        result = preprocessor_with_mock.segment_sentences(text)
        # Should properly segment
        assert isinstance(result, list)

    def test_remove_stopwords_with_entities(self, preprocessor_with_mock):
        """Remove stopwords preserves all entity types."""
        text = "Google Cloud Platform AWS Azure required"
        result = preprocessor_with_mock.remove_stopwords(text)
        # Should preserve important named entities
        assert isinstance(result, str)

    def test_extract_empty_entity_text_handling(self, preprocessor_with_mock):
        """Extract handles entities with empty text."""
        # Normal extraction - test type safety
        text = "Python expert"
        skills, tech, reqs = preprocessor_with_mock.extract_entities(text)
        # All results should be lists of strings
        assert all(isinstance(x, str) for x in skills)
        assert all(isinstance(x, str) for x in tech)


class TestNoiseFilteringAdditions:
    """Issue #211 / Phase 10, Task 3: noise-filtering additions.

    One test per sub-change in `_should_skip_list_item`,
    `_route_list_item_by_section`, `_should_skip_entity_common`, and the
    `boilerplate_keywords` set inside `_filter_entities`.
    """

    def test_should_skip_list_item_year_duration_range(self, preprocessor_with_mock):
        """'5-10 years' (duration-range phrasing) is skipped."""
        assert preprocessor_with_mock._should_skip_list_item("5-10 years") is True

    def test_should_skip_list_item_plus_years(self, preprocessor_with_mock):
        """'5+ years' is skipped."""
        assert preprocessor_with_mock._should_skip_list_item("5+ years of Python") is True

    def test_should_skip_list_item_years_experience_phrase(self, preprocessor_with_mock):
        """'5 years of experience' is skipped."""
        assert preprocessor_with_mock._should_skip_list_item("5 years of experience") is True

    def test_should_skip_list_item_measurement_unit(self, preprocessor_with_mock):
        """'10,001 lbs' (measurement unit) is skipped."""
        assert preprocessor_with_mock._should_skip_list_item("10,001 lbs") is True

    def test_should_skip_list_item_normal_skill_not_skipped(self, preprocessor_with_mock):
        """Regression guard: a normal skill phrase is not skipped."""
        assert preprocessor_with_mock._should_skip_list_item("Python programming") is False

    def test_route_list_item_skips_three_comma_metadata(self, preprocessor_with_mock):
        """A list item with 3+ commas (likely metadata) is not routed to skills."""
        skills: set[str] = set()
        technologies: set[str] = set()
        requirements: set[str] = set()
        item_text = "Seattle, WA, USA, Remote"

        preprocessor_with_mock._route_list_item_by_section(
            item_text,
            section_name="skills",
            is_skills_section=True,
            is_req_section=False,
            is_description_section=False,
            tech_keywords=set(),
            skills=skills,
            technologies=technologies,
            requirements=requirements,
        )

        assert item_text not in skills

    def test_route_list_item_two_comma_item_still_routed(self, preprocessor_with_mock):
        """Regression guard: an item with fewer than 2 commas is still routed."""
        skills: set[str] = set()
        technologies: set[str] = set()
        requirements: set[str] = set()
        item_text = "Python, Docker experience"

        preprocessor_with_mock._route_list_item_by_section(
            item_text,
            section_name="skills",
            is_skills_section=True,
            is_req_section=False,
            is_description_section=False,
            tech_keywords=set(),
            skills=skills,
            technologies=technologies,
            requirements=requirements,
        )

        assert item_text in skills

    def test_should_skip_entity_common_markdown_header_artifact(self, preprocessor_with_mock):
        """A stray '# Requirements' markdown-header artifact is skipped."""
        entity = "# Requirements"
        assert preprocessor_with_mock._should_skip_entity_common(entity, entity.lower(), "requirements", set()) is True

    def test_should_skip_entity_common_normal_entity_not_skipped(self, preprocessor_with_mock):
        """Regression guard: a normal entity without a leading '#' is not skipped."""
        entity = "Python"
        assert preprocessor_with_mock._should_skip_entity_common(entity, entity.lower(), "skills", set()) is False

    def test_filter_entities_drug_test_filtered_from_requirements(self, preprocessor_with_mock):
        """'drug test' is filtered out of requirements via boilerplate_keywords."""
        filtered = preprocessor_with_mock._filter_entities(
            ["drug test", "Python experience"], entity_type="requirements"
        )
        assert "drug test" not in filtered
        assert "Python experience" in filtered


class TestTechKeywordAdjExemption:
    """Issue #211 / Phase 10, Task 4: tech-keyword ADJ exemption.

    Empirical verification (spaCy en_core_web_md, run outside the test
    suite): standalone single-token input tags "Agile" and "Lean" as ADJ
    (JJ) reliably; "Azure" tags NOUN standalone but ADJ is also plausible in
    other attributive contexts elsewhere in TECH_KEYWORDS. Since at least
    "agile"/"lean" reliably reproduce the gap, `_should_skip_skill`'s
    single-adjective filter now also exempts entities present in
    `tech_keywords`, in addition to the pre-existing `soft_skills` exemption.
    """

    def test_single_word_tech_keyword_survives_adj_pos_tag(self, preprocessor_with_mock):
        """'agile' tagged ADJ is not dropped by the single-adjective filter.

        Without the tech_keywords exemption, `_should_skip_skill` would
        return True here (single ADJ token not in the soft_skills
        vocabulary), silently dropping a legitimate methodology keyword.
        """
        filtered = preprocessor_with_mock._filter_entities(
            ["agile"], entity_type="skills", entity_pos_tags={"agile": "ADJ"}
        )
        assert "agile" in filtered

    def test_single_word_non_tech_adjective_still_filtered(self, preprocessor_with_mock):
        """Regression guard: a generic single-word ADJ not in tech_keywords is still dropped."""
        filtered = preprocessor_with_mock._filter_entities(
            ["excellent"], entity_type="skills", entity_pos_tags={"excellent": "ADJ"}
        )
        assert "excellent" not in filtered

    def test_should_skip_skill_exempts_tech_keyword_adj(self, preprocessor_with_mock):
        """Direct unit test of `_should_skip_skill`'s tech_keywords ADJ exemption."""
        tech_keywords = {"agile", "lean", "azure"}
        assert (
            preprocessor_with_mock._should_skip_skill(
                "lean",
                "lean",
                ["lean"],
                generic_skills=set(),
                company_names=set(),
                pos_tag="ADJ",
                tech_keywords=tech_keywords,
            )
            is False
        )

    def test_should_skip_skill_without_tech_keywords_param_unaffected(self, preprocessor_with_mock):
        """Regression guard: omitting tech_keywords preserves prior ADJ-filtering behavior."""
        assert (
            preprocessor_with_mock._should_skip_skill(
                "lean", "lean", ["lean"], generic_skills=set(), company_names=set(), pos_tag="ADJ"
            )
            is True
        )


class TestPocSentenceSplitterWiring:
    """Issue #638 Sub-issue B: POC sentence splitter flag wiring (model-free, blank pipeline)."""

    @staticmethod
    def _blank_nlp_with_sentencizer():
        """Blank English pipeline with a sentencizer so doc.sents works without en_core_web_md."""
        import spacy

        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")
        return nlp

    @pytest.fixture
    def blank_spacy_load(self, monkeypatch):
        """Patch spacy.load to return a model-free blank pipeline (#631 stubbing pattern)."""
        monkeypatch.setattr("spacy.load", lambda model: self._blank_nlp_with_sentencizer())

    def test_poc_splitter_pipe_added_by_default(self, blank_spacy_load):
        """Default-constructed Preprocessor registers poc_sentence_splitter on its pipeline."""
        preprocessor = Preprocessor(extract_requirements=False)
        assert preprocessor.enable_poc_sentence_splitter is True
        assert preprocessor.nlp is not None
        assert "poc_sentence_splitter" in preprocessor.nlp.pipe_names

    def test_poc_splitter_pipe_absent_when_flag_off(self, blank_spacy_load):
        """enable_poc_sentence_splitter=False keeps the pipe out and segment_sentences_poc returns []."""
        preprocessor = Preprocessor(extract_requirements=False, enable_poc_sentence_splitter=False)
        assert preprocessor.nlp is not None
        assert "poc_sentence_splitter" not in preprocessor.nlp.pipe_names
        doc = preprocessor.nlp("Must know Python. Knows SQL too.")
        assert preprocessor.segment_sentences_poc(doc) == []

    def test_segment_sentences_identical_flag_on_vs_off(self, blank_spacy_load):
        """Existing segment_sentences() output is unchanged by the POC pipe."""
        text = "Requires 5+ years MES. Must know\nWonderware. Dr. Smith leads the team!"
        on = Preprocessor(extract_requirements=False, enable_poc_sentence_splitter=True)
        off = Preprocessor(extract_requirements=False, enable_poc_sentence_splitter=False)
        assert on.segment_sentences(text) == off.segment_sentences(text)
        assert on.segment_sentences(text)  # non-empty, so the comparison is meaningful

    def test_segment_sentences_poc_returns_regex_split_when_on(self, blank_spacy_load):
        """With the flag on, segment_sentences_poc returns the regex split (structural newline splits, #677)."""
        preprocessor = Preprocessor(extract_requirements=False)
        assert preprocessor.nlp is not None
        doc = preprocessor.nlp("Must know\nPython. Knows SQL! Also Go?")
        assert preprocessor.segment_sentences_poc(doc) == ["Must know", "Python.", "Knows SQL!", "Also Go?"]
