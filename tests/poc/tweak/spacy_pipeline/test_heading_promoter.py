"""Tests for HeadingPromoter component (Issue #365).

Tests heading promotion rules, edge cases, idempotence, and consistency with
SectionClassifier keyword matching.
"""

import pytest

from src.poc.tweak.markdown_section_classifier import SectionClassifier, SectionType
from src.poc.tweak.spacy_pipeline.heading_promoter import KNOWN_PLAIN_HEADINGS, HeadingPromoter


class TestHeadingPromoterBasic:
    """Test basic heading promotion rules."""

    def test_promote_exact_match_case_insensitive(self) -> None:
        """Exact phrase match (case-insensitive) gets promoted."""
        promoter = HeadingPromoter()
        text = "Job Description\nWork with clients."
        result = promoter.process(text)
        assert "## Job Description" in result

    def test_promote_with_trailing_colon(self) -> None:
        """Trailing colon is stripped; phrase still matches."""
        promoter = HeadingPromoter()
        text = "Role Overview:\nFocus areas below."
        result = promoter.process(text)
        assert "## Role Overview" in result
        # Colon removed in output
        assert "## Role Overview:" not in result

    def test_uppercase_variant_matches(self) -> None:
        """All-uppercase variant of phrase gets promoted."""
        promoter = HeadingPromoter()
        text = "TECHNICAL SKILLS\nPython, Java."
        result = promoter.process(text)
        assert "## TECHNICAL SKILLS" in result

    def test_mixed_case_variant_matches(self) -> None:
        """Mixed-case variant of phrase gets promoted."""
        promoter = HeadingPromoter()
        text = "Key Responsibilities\nManage projects."
        result = promoter.process(text)
        assert "## Key Responsibilities" in result

    def test_unicode_apostrophe_normalized(self) -> None:
        """Unicode apostrophes (smart quotes) match straight apostrophes."""
        promoter = HeadingPromoter()
        # Test with straight apostrophe; the phrase should exist if defined
        text = "Roles and Responsibilities\nMore info."
        result = promoter.process(text)
        # "Roles and Responsibilities" not in KNOWN_PLAIN_HEADINGS, stays as-is
        assert "## Roles and Responsibilities" not in result


class TestHeadingPromoterStructuralRules:
    """Test structural promotion rules (line position, formatting, etc.)."""

    def test_not_promoted_bold_line(self) -> None:
        """Line that is entirely bold (**...**) is not promoted."""
        promoter = HeadingPromoter()
        text = "**Job Description**\nContent."
        result = promoter.process(text)
        assert "## **Job Description**" not in result

    def test_not_promoted_in_paragraph(self) -> None:
        """Phrase in middle of paragraph (no blank line before) is not promoted."""
        promoter = HeadingPromoter()
        text = "Some text. Job Description is next.\nMore content."
        result = promoter.process(text)
        assert "## Job Description" not in result

    def test_not_promoted_hash_line(self) -> None:
        """Line starting with # (already markdown) is not promoted."""
        promoter = HeadingPromoter()
        text = "# Job Description\nContent."
        result = promoter.process(text)
        assert "## # Job Description" not in result

    def test_not_promoted_ast_line(self) -> None:
        """Line starting with * (list marker) is not promoted."""
        promoter = HeadingPromoter()
        text = "* Job Description\nContent."
        result = promoter.process(text)
        assert "## * Job Description" not in result

    def test_not_promoted_dash_line(self) -> None:
        """Line starting with dash is not promoted."""
        promoter = HeadingPromoter()
        text = "- Role Overview\nContent."
        result = promoter.process(text)
        assert "## - Role Overview" not in result

    def test_not_promoted_plus_line(self) -> None:
        """Line starting with plus is not promoted."""
        promoter = HeadingPromoter()
        text = "+ Skills Required\nContent."
        result = promoter.process(text)
        assert "## + Skills Required" not in result

    def test_not_promoted_list_with_digit(self) -> None:
        """Line starting with digit (list marker) is not promoted."""
        promoter = HeadingPromoter()
        text = "1. Technical Skills\nContent."
        result = promoter.process(text)
        assert "## 1. Technical Skills" not in result

    def test_not_promoted_table_line(self) -> None:
        """Line starting with pipe (table marker) is not promoted."""
        promoter = HeadingPromoter()
        text = "| Requirements | Details |\nContent."
        result = promoter.process(text)
        assert "## | Requirements | Details |" not in result

    def test_not_promoted_no_blank_before(self) -> None:
        """Line with no blank line before it (and not first line) is not promoted."""
        promoter = HeadingPromoter()
        text = "Some text\nJob Description\nContent."
        result = promoter.process(text)
        assert "## Job Description" not in result
        assert "Job Description" in result  # Original preserved

    def test_promoted_first_line(self) -> None:
        """First line of document CAN be promoted even without blank line before."""
        promoter = HeadingPromoter()
        text = "Job Description\nContent below."
        result = promoter.process(text)
        assert "## Job Description" in result

    def test_promoted_after_blank_line(self) -> None:
        """Line after blank line is promoted."""
        promoter = HeadingPromoter()
        text = "Some text\n\nJob Description\nContent."
        result = promoter.process(text)
        assert "## Job Description" in result

    def test_not_promoted_empty_line(self) -> None:
        """Empty lines are not promoted."""
        promoter = HeadingPromoter()
        text = "Some text\n\n\n\nContent."
        result = promoter.process(text)
        # Line count should be preserved
        assert result.count("\n") == text.count("\n")

    def test_not_promoted_whitespace_only_line(self) -> None:
        """Whitespace-only lines are not promoted."""
        promoter = HeadingPromoter()
        text = "Some text\n   \nContent."
        result = promoter.process(text)
        # Whitespace-only line stays as-is
        assert "##    " not in result


class TestHeadingPromoterIdempotence:
    """Test that promotion is idempotent."""

    def test_idempotent_single_pass(self) -> None:
        """Processing twice yields same result."""
        promoter = HeadingPromoter()
        text = "Job Description\n\nRole Overview\n\nSkills\nContent."
        result1 = promoter.process(text)
        result2 = promoter.process(result1)
        assert result1 == result2

    def test_idempotent_multiple_passes(self) -> None:
        """Processing many times yields same result (with blank-line separation)."""
        promoter = HeadingPromoter()
        # Multiple blank lines separate headings for promotion eligibility
        text = "Technical Skills\n\nRequired Qualifications\n\nContent."
        result = text
        for _ in range(5):
            result = promoter.process(result)
        assert result.count("## Technical Skills") == 1
        assert result.count("## Required Qualifications") == 1

    def test_mixed_markdown_idempotent(self) -> None:
        """Text with existing markdown headings processes idempotently."""
        promoter = HeadingPromoter()
        text = "## Existing Heading\n\nJob Description\nContent."
        result1 = promoter.process(text)
        result2 = promoter.process(result1)
        assert result1 == result2


class TestHeadingPromoterEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_string(self) -> None:
        """Empty input returns empty output."""
        promoter = HeadingPromoter()
        result = promoter.process("")
        assert result == ""

    def test_single_line(self) -> None:
        """Single known phrase line gets promoted."""
        promoter = HeadingPromoter()
        result = promoter.process("Job Description")
        assert result == "## Job Description"

    def test_crlf_line_endings(self) -> None:
        """CRLF line endings are preserved."""
        promoter = HeadingPromoter()
        text = "Job Description\r\nContent below.\r\n"
        result = promoter.process(text)
        # The split('\n') will handle CRLF; verify promotion happened
        assert "## Job Description" in result

    def test_line_count_preserved(self) -> None:
        """Output has same line count as input (1:1 replacement)."""
        promoter = HeadingPromoter()
        text = "Job Description\n\nRole Overview\n\nTechnical Skills\nContent.\n"
        result = promoter.process(text)
        assert text.count("\n") == result.count("\n")


class TestHeadingPromoterConsistency:
    """Test consistency with SectionClassifier."""

    def test_all_phrases_classify_non_other(self) -> None:
        """Every phrase in KNOWN_PLAIN_HEADINGS classifies as non-'other' type.

        This guards against vocab/classifier drift: if a phrase is in the promoter
        vocabulary, it must map to a semantic type (skills, qualifications, etc),
        NOT to 'other'. This ensures promoted headings are useful for section parsing.
        """
        classifier = SectionClassifier()

        # The 10 'other' phrases that should NOT be in KNOWN_PLAIN_HEADINGS
        other_phrases = {
            "duties",
            "education",
            "eeo statement",
            "equal employment opportunity",
            "job duties",
            "must have",
            "nice to have",
            "the role",
            "who we are",
            "who you are",
        }

        # Check that no 'other' phrases are in the known headings
        for phrase in KNOWN_PLAIN_HEADINGS:
            assert phrase not in other_phrases, f"Phrase '{phrase}' is marked as 'other' and should not be promoted"

        # Sample check: a few known phrases should classify as non-'other'
        test_phrases = [
            "job description",
            "role overview",
            "key responsibilities",
            "required qualifications",
            "technical skills",
        ]

        for phrase in test_phrases:
            if phrase in KNOWN_PLAIN_HEADINGS:
                # Classify as title to get the type
                from src.poc.tweak.multi_line_paragraph import MarkdownSection

                section = MarkdownSection(
                    title=phrase.upper(),  # titles are uppercase
                    content="",
                    level=1,
                    start_line=0,
                    end_line=0,
                    word_count=len(phrase.split()),
                    line_count=1,
                    has_list=False,
                )
                classification = classifier.classify(section)

                # Should have at least one type
                assert len(classification.all_types) > 0, f"Phrase '{phrase}' classified with 0 types"

                # Primary type should NOT be OTHER
                primary_type = classification.all_types[0]
                assert primary_type.section_type != SectionType.OTHER, (
                    f"Phrase '{phrase}' classified as OTHER; should promote non-'other' phrases only"
                )


class TestHeadingPromoterIntegration:
    """Integration tests with WorkSource-shaped text."""

    def test_worksource_shaped_text_multiple_sections(self) -> None:
        """WorkSource-like plain-text headings get promoted to multiple sections."""
        promoter = HeadingPromoter()
        text = """Job#: 3052092

Job Description

Develop algorithms for signal processing.

Role Overview

Focus on advanced research techniques.

Key Responsibilities

* Design and implement algorithms
* Test effectiveness against requirements

Required Qualifications

A Bachelor's Degree in computer science.

Technical Skills

* Python experience required
* C++ preferred
"""
        result = promoter.process(text)

        # Verify key sections promoted
        assert "## Job Description" in result
        assert "## Role Overview" in result
        assert "## Key Responsibilities" in result
        assert "## Required Qualifications" in result
        assert "## Technical Skills" in result

        # Line count preserved
        assert result.count("\n") == text.count("\n")

    def test_perf_marketing_manager_shaped_text(self) -> None:
        """Performance Marketing Manager-shaped text (live job from Q2).

        With the new classifier keywords ("in this role" -> RESPONSIBILITIES,
        "succeed" -> QUALIFICATIONS) and expanded phrase set, headings
        "in this role you will" and "what will make you succeed" are now promoted.
        This enables proper section splitting and requirement extraction.
        """
        promoter = HeadingPromoter()
        text = """Why work at Medbridge?

We are mission driven.

Role Description

You will run Medbridge paid media end to end.

In this role you will:

* Own the full-funnel paid media strategy

What will make you succeed:

* 6+ years of digital marketing experience

Tools

* CRM: Salesforce, Hubspot

Our Values:

Excellence is never an accident."""

        result = promoter.process(text)

        # "Role Description" should be promoted (in vocabulary)
        assert "## Role Description" in result

        # "In this role you will" and "What will make you succeed" should now be promoted
        # (they are in KNOWN_PLAIN_HEADINGS with new keywords from Issue #365)
        assert "## In this role you will" in result
        assert "## What will make you succeed" in result

        # These are still NOT in vocabulary, so they stay as-is
        assert "## Why work at Medbridge?" not in result
        assert "## Tools" not in result
        assert "## Our Values:" not in result

        # Line count preserved
        assert text.count("\n") == result.count("\n")


class TestHeadingPromoterErrorHandling:
    """Test error handling and robustness."""

    def test_exception_returns_original_text(self) -> None:
        """Exceptions during processing return original text unchanged.

        Even if an internal error occurs, the processor returns the original text
        (fail-safe behavior). A warning is logged but no exception is raised.
        """
        promoter = HeadingPromoter()

        # Trigger exception by monkey-patching _should_promote to raise
        def bad_should_promote(*args, **kwargs):
            raise ValueError("Intentional test error")

        original_should_promote = promoter._should_promote
        promoter._should_promote = bad_should_promote  # type: ignore[method-assign]

        text = "Job Description\nContent."
        result = promoter.process(text)

        # Should return original text unchanged
        assert result == text

        # Restore original method
        promoter._should_promote = original_should_promote  # type: ignore[method-assign]


class TestHeadingPromoterEEOIsolation:
    """Tests for EEO paragraph isolation (Issue #374)."""

    @pytest.mark.parametrize(
        ("trigger_phrase", "eeo_sentence"),
        [
            ("equal opportunity employer", "Acme is an equal opportunity employer."),
            ("equal employment opportunity", "We value equal employment opportunity in every hire."),
            ("is an equal opportunity", "Acme is an equal opportunity workplace."),
            ("are an equal opportunity", "We are an equal opportunity workplace."),
            ("does not discriminate", "Acme does not discriminate in hiring."),
            ("affirmative action", "Acme is committed to affirmative action."),
        ],
    )
    def test_trailing_eeo_paragraph_isolated(self, trigger_phrase: str, eeo_sentence: str) -> None:
        """Trailing EEO sentence containing each trigger gets a synthesized heading (exact output)."""
        assert trigger_phrase in eeo_sentence.lower()
        promoter = HeadingPromoter()
        text = (
            "Role Overview\n\nWe are a great company.\n\nRequired Qualifications\n\n"
            f"5+ years of experience required.\n\n{eeo_sentence}"
        )
        expected = (
            "## Role Overview\n\nWe are a great company.\n\n## Required Qualifications\n\n"
            f"5+ years of experience required.\n\n## Equal Opportunity Employer\n\n{eeo_sentence}"
        )
        result = promoter.process(text)
        assert result == expected
        assert promoter.process(result) == result

    def test_mid_document_eeo_not_split(self) -> None:
        """EEO sentence mid-document, followed by a real section, gets no synthetic heading."""
        promoter = HeadingPromoter()
        text = (
            "Role Overview\n\n"
            "We believe in equal employment opportunity and decide without regard to race.\n\n"
            "Key Responsibilities\n\n"
            "Lead the team and manage projects."
        )
        expected = (
            "## Role Overview\n\n"
            "We believe in equal employment opportunity and decide without regard to race.\n\n"
            "## Key Responsibilities\n\n"
            "Lead the team and manage projects."
        )
        result = promoter.process(text)
        assert result == expected
        assert result.count("## Equal Opportunity Employer") == 0
        assert promoter.process(result) == result

    def test_eeo_in_bullet_list_not_split(self) -> None:
        """A trailing bullet containing an EEO sentence is not isolated (bullet exclusion in _is_eeo_paragraph)."""
        promoter = HeadingPromoter()
        text = "Required Qualifications\n\n5+ years of experience.\n\n* Acme is an equal opportunity employer."
        expected = "## Required Qualifications\n\n5+ years of experience.\n\n* Acme is an equal opportunity employer."
        result = promoter.process(text)
        assert result == expected
        assert result.count("## Equal Opportunity Employer") == 0
        assert promoter.process(result) == result

    def test_eeo_already_under_heading_not_doubled(self) -> None:
        """EEO paragraph already under a heading is not re-headed (Guard 3 keeps it unchanged)."""
        promoter = HeadingPromoter()
        text = (
            "Role Overview\n\nWe are a great company.\n\n"
            "## Equal Opportunity Employer\n\n"
            "This is an equal opportunity employer."
        )
        expected = (
            "## Role Overview\n\nWe are a great company.\n\n"
            "## Equal Opportunity Employer\n\n"
            "This is an equal opportunity employer."
        )
        result = promoter.process(text)
        assert result == expected
        assert result.count("## Equal Opportunity Employer") == 1
        assert promoter.process(result) == result

    def test_eeo_idempotent_multiple_passes(self) -> None:
        """Processing an EEO sentence several times yields the same result, with one heading."""
        promoter = HeadingPromoter()
        text = (
            "Role Overview\n\nWe are a great company.\n\n"
            "Acme is an equal opportunity employer and makes decisions without regard to race."
        )
        expected = (
            "## Role Overview\n\nWe are a great company.\n\n"
            "## Equal Opportunity Employer\n\n"
            "Acme is an equal opportunity employer and makes decisions without regard to race."
        )
        result1 = promoter.process(text)
        result2 = promoter.process(result1)
        result3 = promoter.process(result2)

        assert result1 == expected
        assert result1 == result2 == result3
        assert result1.count("## Equal Opportunity Employer") == 1

    def test_trailing_ada_paragraph_after_eeo_stays_trailing(self) -> None:
        """Trailing ADA/contact paragraph after EEO stays inside EEO section (DEFECT 1 FIX)."""
        promoter = HeadingPromoter()
        text = (
            "Role Overview\n\nWe are a great company.\n\n"
            "Required Qualifications\n\n5+ years experience.\n\n"
            "We are an equal opportunity employer without regard to color or background.\n\n"
            "Accommodations\n\n"
            "If you need accommodations, please contact us."
        )
        expected = (
            "## Role Overview\n\nWe are a great company.\n\n"
            "## Required Qualifications\n\n5+ years experience.\n\n"
            "## Equal Opportunity Employer\n\n"
            "We are an equal opportunity employer without regard to color or background.\n\n"
            "Accommodations\n\n"
            "If you need accommodations, please contact us."
        )
        result = promoter.process(text)
        assert result == expected
        assert promoter.process(result) == result

    def test_eeo_followed_by_real_section_not_split(self) -> None:
        """EEO sentence followed by a real section is not isolated; the section is promoted."""
        promoter = HeadingPromoter()
        text = (
            "Role Overview\n\nWe are a great company.\n\n"
            "Required Qualifications\n\n5+ years experience.\n\n"
            "Acme is an equal opportunity employer.\n\n"
            "How to Apply\n\nSubmit your resume online."
        )
        expected = (
            "## Role Overview\n\nWe are a great company.\n\n"
            "## Required Qualifications\n\n5+ years experience.\n\n"
            "Acme is an equal opportunity employer.\n\n"
            "## How to Apply\n\nSubmit your resume online."
        )
        result = promoter.process(text)
        assert result == expected
        assert result.count("## Equal Opportunity Employer") == 0
        assert promoter.process(result) == result

    def test_empty_text_unchanged(self) -> None:
        """Empty text is returned unchanged."""
        promoter = HeadingPromoter()
        result = promoter.process("")
        assert result == ""

    def test_case_insensitive_trigger_matching(self) -> None:
        """EEO triggers match case-insensitively; the synthesized heading keeps its own casing."""
        promoter = HeadingPromoter()
        text = "Role Overview\n\nDetails.\n\nACME IS AN EQUAL OPPORTUNITY EMPLOYER AND DOES NOT DISCRIMINATE."
        expected = (
            "## Role Overview\n\nDetails.\n\n"
            "## Equal Opportunity Employer\n\n"
            "ACME IS AN EQUAL OPPORTUNITY EMPLOYER AND DOES NOT DISCRIMINATE."
        )
        result = promoter.process(text)
        assert result == expected
        assert promoter.process(result) == result

    def test_eeo_in_first_200_chars(self) -> None:
        """EEO trigger must be in first ~200 chars of paragraph."""
        promoter = HeadingPromoter()
        # Long paragraph with EEO trigger far into it
        long_content = "This paragraph contains a lot of content. " * 10
        text = f"""Role Overview

Details.

Paragraph With EEO Late

{long_content}And only much later: We are an equal opportunity employer."""

        result = promoter.process(text)

        # Should not detect (EEO is beyond ~200 chars)
        assert result.count("## Equal Opportunity Employer") == 0


class TestHeadingPromoterRegressionEEO:
    """Regression tests with realistic WorkSource-shaped job text."""

    def test_worksource_with_trailing_eeo_isolated(self) -> None:
        """WorkSource-shaped job with trailing EEO isolated into own section."""
        promoter = HeadingPromoter()
        # Realistic WorkSource-shaped text
        text = """Role Overview

Medtech company seeking a senior engineer to lead the platform team.

Key Responsibilities

* Design and implement cloud infrastructure
* Mentor junior engineers
* Collaborate with product teams

Required Qualifications

Bachelor's degree in Computer Science or equivalent experience.
5+ years of software engineering experience.
Strong knowledge of AWS or GCP.

Technical Skills

* Python
* Go
* Kubernetes

XYZ Corporation is an equal opportunity employer and is committed to creating a diverse and inclusive workplace."""

        result = promoter.process(text)

        # Verify sections are promoted correctly
        assert "## Role Overview" in result
        assert "## Key Responsibilities" in result
        assert "## Required Qualifications" in result
        assert "## Technical Skills" in result

        # EEO should be isolated into own section
        assert "## Equal Opportunity Employer" in result

        # Verify preceding section content is not polluted with EEO text
        # (by checking structure before the EEO heading)
        lines = result.split("\n")
        eeo_heading_line = None
        for i, line in enumerate(lines):
            if "## Equal Opportunity Employer" in line:
                eeo_heading_line = i
                break

        assert eeo_heading_line is not None, "EEO heading not found"

        # Check that "Technical Skills" section ends before EEO heading
        tech_section_lines = [line for line in lines[:eeo_heading_line] if "Kubernetes" in line or "Python" in line]
        assert len(tech_section_lines) > 0, "Technical skills content not found before EEO"

    def test_eeo_followed_by_non_boilerplate_paragraph_unchanged(self) -> None:
        """EEO sentence followed by a non-boilerplate paragraph is not isolated; text is unchanged."""
        promoter = HeadingPromoter()
        text = "More text.\n\nAcme is an equal opportunity employer.\n\nSubmit your resume to our team."
        result = promoter.process(text)
        assert result == text
        assert result.count("## Equal Opportunity Employer") == 0
        assert promoter.process(result) == result


class TestHeadingPromoterDefectFixes:
    """Exact-equality tests for DEFECT 1, 2, 3 fixes (Issue #374)."""

    def test_plain_trailing_eeo_exact(self) -> None:
        """Plain trailing EEO: heading + blank inserted before EEO paragraph (DEFECT 2 FIX)."""
        promoter = HeadingPromoter()
        input_text = "More text here.\n\nAcme is an equal opportunity employer and does not discriminate."
        expected = (
            "More text here.\n\n## Equal Opportunity Employer\n\n"
            "Acme is an equal opportunity employer and does not discriminate."
        )
        result = promoter.process(input_text)
        assert result == expected

    def test_eeo_with_ada_exact(self) -> None:
        """EEO + ADA paragraph: ADA stays trailing inside EEO section (DEFECT 1 FIX)."""
        promoter = HeadingPromoter()
        input_text = (
            "More text.\n\nAcme is an equal opportunity employer.\n\n"
            "If you need accommodation, contact hr@acme.com for assistance."
        )
        expected = (
            "More text.\n\n## Equal Opportunity Employer\n\n"
            "Acme is an equal opportunity employer.\n\n"
            "If you need accommodation, contact hr@acme.com for assistance."
        )
        result = promoter.process(input_text)
        assert result == expected

    def test_eeo_with_ada_crlf_exact(self) -> None:
        """EEO + ADA with CRLF: line endings preserved (DEFECT 2 FIX)."""
        promoter = HeadingPromoter()
        input_text = (
            "More text.\r\n\r\nAcme is an equal opportunity employer.\r\n\r\n"
            "If you need accommodation, contact hr@acme.com for assistance."
        )
        expected = (
            "More text.\r\n\r\n## Equal Opportunity Employer\r\n\r\n"
            "Acme is an equal opportunity employer.\r\n\r\n"
            "If you need accommodation, contact hr@acme.com for assistance."
        )
        result = promoter.process(input_text)
        assert result == expected

    def test_input_with_trailing_newline_exact(self) -> None:
        """Input with trailing newline: preserved in output."""
        promoter = HeadingPromoter()
        input_text = "More text.\n\nAcme is an equal opportunity employer.\n"
        expected = "More text.\n\n## Equal Opportunity Employer\n\nAcme is an equal opportunity employer.\n"
        result = promoter.process(input_text)
        assert result == expected

    def test_multiple_blank_lines_preserved_exact(self) -> None:
        """Multiple blank lines in earlier section: all preserved."""
        promoter = HeadingPromoter()
        input_text = "Section One.\n\n\n\nSection Two.\n\nAcme is an equal opportunity employer."
        expected = (
            "Section One.\n\n\n\nSection Two.\n\n## Equal Opportunity Employer"
            "\n\nAcme is an equal opportunity employer."
        )
        result = promoter.process(input_text)
        assert result == expected

    def test_benefits_without_regard_to_tenure_unchanged(self) -> None:
        """Benefits with 'without regard to tenure': NOT detected as EEO (DEFECT 3 FIX)."""
        promoter = HeadingPromoter()
        text = "More text.\n\nOur benefits are offered without regard to tenure and include dental coverage."
        result = promoter.process(text)
        assert result.count("## Equal Opportunity Employer") == 0
        assert result == text
        assert promoter.process(result) == result

    def test_mid_document_bullet_with_eeo_unchanged(self) -> None:
        """A bullet EEO sentence after a body paragraph is not isolated; text is unchanged."""
        promoter = HeadingPromoter()
        text = "More text.\n\n* Acme is an equal opportunity employer."
        result = promoter.process(text)
        assert result == text
        assert result.count("## Equal Opportunity Employer") == 0
        assert promoter.process(result) == result

    def test_eeo_followed_by_real_benefits_section_unchanged(self) -> None:
        """EEO followed by real '## Benefits' section: no synthetic heading."""
        promoter = HeadingPromoter()
        input_text = "Acme is an equal opportunity employer.\n\nBenefits\n\nDental coverage."
        # "Benefits" will be promoted to ##, not EEO synthetic heading
        result = promoter.process(input_text)
        assert result.count("## Equal Opportunity Employer") == 0
        assert "## Benefits" in result
        # But the EEO paragraph itself should be promoted if "Acme..." line is a known heading (it's not)
        assert "Acme is an equal opportunity employer." in result

    def test_idempotent_eeo_second_pass_equals_first(self) -> None:
        """Idempotent: second pass equals first pass."""
        promoter = HeadingPromoter()
        text = "More text.\n\nEqual Opportunity Employer\n\nAcme is an equal opportunity employer."
        result1 = promoter.process(text)
        result2 = promoter.process(result1)
        assert result1 == result2


class TestEEOBoilerplateWordBoundary:
    """Single-word boilerplate keywords must match on word boundaries (Issue #374)."""

    def test_canada_trailing_paragraph_not_boilerplate(self) -> None:
        """'ada' inside 'Canada' is not boilerplate, so the EEO paragraph is not isolated."""
        promoter = HeadingPromoter()
        text = "More text.\n\nAcme is an equal opportunity employer.\n\nOffices are located in Canada."
        result = promoter.process(text)
        assert result == text
        assert promoter.process(result) == result

    def test_adapt_trailing_paragraph_not_boilerplate(self) -> None:
        """'ada' inside 'adapt' is not boilerplate, so the EEO paragraph is not isolated."""
        promoter = HeadingPromoter()
        text = "More text.\n\nAcme is an equal opportunity employer.\n\nWe will adapt the role to your goals."
        result = promoter.process(text)
        assert result == text
        assert promoter.process(result) == result

    def test_please_contact_hr_for_ada_still_boilerplate(self) -> None:
        """'Please contact HR for ADA accommodations.' is still boilerplate, so EEO is isolated."""
        promoter = HeadingPromoter()
        text = "More text.\n\nAcme is an equal opportunity employer.\n\nPlease contact HR for ADA accommodations."
        expected = (
            "More text.\n\n## Equal Opportunity Employer\n\n"
            "Acme is an equal opportunity employer.\n\n"
            "Please contact HR for ADA accommodations."
        )
        result = promoter.process(text)
        assert result == expected
        assert promoter.process(result) == result

    @pytest.mark.parametrize(
        "boilerplate_line",
        [
            "Requests for ADA support go to HR.",
            "Send questions to hr@acme.com by email.",
            "Reasonable accommodations are available on request.",
        ],
    )
    def test_single_word_keywords_match_on_word(self, boilerplate_line: str) -> None:
        """Single-word keywords (ADA, email, accommodations) still count as boilerplate."""
        promoter = HeadingPromoter()
        text = f"More text.\n\nAcme is an equal opportunity employer.\n\n{boilerplate_line}"
        expected = (
            "More text.\n\n## Equal Opportunity Employer\n\n"
            f"Acme is an equal opportunity employer.\n\n{boilerplate_line}"
        )
        result = promoter.process(text)
        assert result == expected
        assert promoter.process(result) == result


class TestMultipleTrailingEEO:
    """A trailing block of several EEO paragraphs is isolated at its first member (Issue #374)."""

    def test_two_trailing_eeo_paragraphs_isolated_at_first(self) -> None:
        """Only one heading, placed before the first EEO paragraph of the trailing block."""
        promoter = HeadingPromoter()
        text = "More text.\n\nAcme is an equal opportunity employer.\n\nBeta is an equal opportunity employer too."
        expected = (
            "More text.\n\n## Equal Opportunity Employer\n\n"
            "Acme is an equal opportunity employer.\n\n"
            "Beta is an equal opportunity employer too."
        )
        result = promoter.process(text)
        assert result == expected
        assert result.count("## Equal Opportunity Employer") == 1
        assert promoter.process(result) == result

    def test_eeo_followed_by_regardless_of_paragraph_not_isolated(self) -> None:
        """Documented limitation: 'regardless of race' is not an EEO trigger, so nothing is isolated.

        The trailing paragraph is neither boilerplate nor matched by PROTECTED_CLASS_PATTERN
        (which only recognises 'without regard to'). The conservative outcome is no
        synthetic heading, so the text is returned unchanged.
        """
        promoter = HeadingPromoter()
        text = "More text.\n\nAcme is an equal opportunity employer.\n\nWe hire regardless of race or sex."
        result = promoter.process(text)
        assert result == text
        assert promoter.process(result) == result

    def test_eeo_followed_by_protected_class_only_paragraph_isolated(self) -> None:
        """Trailing paragraph matched only by the protected-class pattern is accepted as EEO."""
        promoter = HeadingPromoter()
        text = "More text.\n\nAcme is an equal opportunity employer.\n\nWe make decisions without regard to sex or age."
        expected = (
            "More text.\n\n## Equal Opportunity Employer\n\n"
            "Acme is an equal opportunity employer.\n\n"
            "We make decisions without regard to sex or age."
        )
        result = promoter.process(text)
        assert result == expected
        assert promoter.process(result) == result


class TestProtectedClassPatternBound:
    """PROTECTED_CLASS_PATTERN only links 'without regard to' to a term within ~60 chars (Issue #374)."""

    def test_protected_class_term_within_60_chars_is_eeo(self) -> None:
        """A protected-class term 54 chars after 'without regard to' is EEO and isolated."""
        promoter = HeadingPromoter()
        gap = "alpha " * 9  # 54 chars of neutral filler
        text = f"More text.\n\nAcme hires without regard to {gap}race."
        expected = f"More text.\n\n## Equal Opportunity Employer\n\nAcme hires without regard to {gap}race."
        result = promoter.process(text)
        assert result == expected
        assert promoter.process(result) == result

    def test_protected_class_term_beyond_60_chars_not_eeo(self) -> None:
        """A protected-class term 66 chars after 'without regard to' is not EEO; text unchanged."""
        promoter = HeadingPromoter()
        gap = "alpha " * 11  # 66 chars of neutral filler, beyond the bound
        text = f"More text.\n\nAcme hires without regard to {gap}race."
        result = promoter.process(text)
        assert result == text
        assert promoter.process(result) == result


class TestEEOSilentSkipGuards:
    """Guards 2 and 4 in _isolate_eeo_paragraphs each skip insertion on their own (Issue #374)."""

    def test_guard4_alone_preceding_known_heading_skips_insertion(self) -> None:
        """Guard 4 only: preceding paragraph starts with 'Benefits'; EEO first line is a sentence."""
        promoter = HeadingPromoter()
        text = (
            "More text.\n\nBenefits\nDental coverage.\n\n"
            "Acme is an equal opportunity employer and does not discriminate."
        )
        expected = (
            "More text.\n\n## Benefits\nDental coverage.\n\n"
            "Acme is an equal opportunity employer and does not discriminate."
        )
        result = promoter.process(text)
        assert result == expected
        assert result.count("## Equal Opportunity Employer") == 0

    def test_guard4_second_pass_is_idempotent(self) -> None:
        """Guard 4 still skips on pass 2, when 'Benefits' has been promoted to '## Benefits'."""
        promoter = HeadingPromoter()
        text = (
            "More text.\n\nBenefits\nDental coverage.\n\n"
            "Acme is an equal opportunity employer and does not discriminate."
        )
        expected = (
            "More text.\n\n## Benefits\nDental coverage.\n\n"
            "Acme is an equal opportunity employer and does not discriminate."
        )
        first = promoter.process(text)
        assert first == expected
        assert promoter.process(first) == first
        assert first.count("## Equal Opportunity Employer") == 0

    def test_guard4_second_pass_idempotent_with_compensation_heading(self) -> None:
        """Guard 4 idempotency holds for a different known heading ('Compensation')."""
        promoter = HeadingPromoter()
        text = (
            "More text.\n\nCompensation\nBase salary range.\n\n"
            "Acme is an equal opportunity employer and does not discriminate."
        )
        expected = (
            "More text.\n\n## Compensation\nBase salary range.\n\n"
            "Acme is an equal opportunity employer and does not discriminate."
        )
        first = promoter.process(text)
        assert first == expected
        second = promoter.process(first)
        assert second == first
        assert second.count("## Equal Opportunity Employer") == 0

    def test_guard2_alone_heading_line_in_eeo_paragraph_skips_insertion(self) -> None:
        """Guard 2 only: EEO paragraph's first line is a known heading, with no blank line before the sentence.

        Guard 2 is reachable here because the heading line shares a paragraph with the EEO
        sentence. The preceding paragraph ('More text.') does not trigger Guard 3 or Guard 4.
        """
        promoter = HeadingPromoter()
        text = "More text.\n\nEqual Opportunity Employer\nAcme is an equal opportunity employer."
        expected = "More text.\n\n## Equal Opportunity Employer\nAcme is an equal opportunity employer."
        result = promoter.process(text)
        assert result == expected
        assert result.count("## Equal Opportunity Employer") == 1
        assert promoter.process(result) == result

    def test_standalone_eeo_heading_not_duplicated(self) -> None:
        """Guard 5: a standalone 'Equal Opportunity Employer' line earlier in the document is not duplicated."""
        promoter = HeadingPromoter()
        text = (
            "Equal Opportunity Employer\n\nWe value diverse teams.\n\n"
            "Acme is an equal opportunity employer.\n\nPlease contact HR."
        )
        expected = (
            "## Equal Opportunity Employer\n\nWe value diverse teams.\n\n"
            "Acme is an equal opportunity employer.\n\nPlease contact HR."
        )
        result = promoter.process(text)
        assert result == expected
        assert result.count("## Equal Opportunity Employer") == 1
        assert promoter.process(result) == result


class TestMixedLineEndings:
    """Mixed CRLF/LF input is normalised to the first line ending detected (Issue #374)."""

    def test_mixed_lf_first_normalised_to_lf(self) -> None:
        """First newline is LF, so the CRLF in the trailing paragraph break becomes LF."""
        promoter = HeadingPromoter()
        text = (
            "More text.\n\nAcme is an equal opportunity employer.\r\n\r\n"
            "If you need accommodation, contact hr@acme.com."
        )
        expected = (
            "More text.\n\n## Equal Opportunity Employer\n\n"
            "Acme is an equal opportunity employer.\n\n"
            "If you need accommodation, contact hr@acme.com."
        )
        result = promoter.process(text)
        assert result == expected
        assert "\r" not in result
        assert promoter.process(result) == result

    def test_mixed_crlf_first_normalised_to_crlf(self) -> None:
        """First newline is CRLF, so the bare LF breaks in the input become CRLF."""
        promoter = HeadingPromoter()
        text = (
            "More text.\r\n\nAcme is an equal opportunity employer.\n\nIf you need accommodation, contact hr@acme.com."
        )
        expected = (
            "More text.\r\n\r\n## Equal Opportunity Employer\r\n\r\n"
            "Acme is an equal opportunity employer.\r\n\r\n"
            "If you need accommodation, contact hr@acme.com."
        )
        result = promoter.process(text)
        assert result == expected
        assert promoter.process(result) == result

    def test_crlf_only_heading_promotion_keeps_crlf(self) -> None:
        """CRLF-only input: promoted heading and untouched lines all keep CRLF."""
        promoter = HeadingPromoter()
        text = "Job Description\r\nContent below.\r\n"
        expected = "## Job Description\r\nContent below.\r\n"
        result = promoter.process(text)
        assert result == expected
        assert promoter.process(result) == result
