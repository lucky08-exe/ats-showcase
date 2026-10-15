"""POC Batch Processor for multi-job markdown pipeline.

This module runs multiple job descriptions through the 4-stage spaCy markdown
pipeline to validate and test the processing workflow.

Stages:
0. Scope to selector (optional)
1. HTMLPreprocessor: Clean HTML, normalize structure
2. HTMLMarkdownConverter: Convert HTML to Markdown using MarkItDown
3. MarkdownPolisher: Apply formatting rules for polished output
3b. HeadingPromoter: Promote plain-text headings to markdown (optional, Issue #365)
4. MarkdownSpanRuler: Parse sections from markdown content
5. SectionClassifier: Classify parsed sections into semantic types
6. RequirementProcessor: Extract requirements from sections (Issue #321)
7. SkillProcessor: Extract skills from sections (Issue #321)
8. TechnologyProcessor: Extract technologies from sections (Issue #321)

Stage 9 (Issue #643): poc_sentence_splitter populates ``JobResult.sentences`` from the
polished markdown; disable with ``--no-poc-sentences`` / ``enable_poc_sentence_splitter=False``.

Components are instantiated once and reused across all jobs for efficiency.
Per-job errors are captured without aborting the batch.

Usage:
    >>> from src.poc.tweak.batch_processor import run_batch, print_summary
    >>>
    >>> results = run_batch("data/work/details_test.json")
    >>> summary = print_summary(results)
    >>> print(summary)

CLI:
    python -m src.poc.tweak.batch_processor --input-path data/work/details_test.json
    python -m src.poc.tweak.batch_processor --input-path data/work/details_test.json --output-json results.json
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import spacy

import src.poc.sentence_splitter  # noqa: F401  (registers poc_sentence_splitter factory + doc extension)
from src.poc.tweak.markdown_section_classifier import SectionClassifier
from src.poc.tweak.multi_line_paragraph import MarkdownSpanRuler
from src.poc.tweak.section_model import MarkdownSection
from src.poc.tweak.spacy_pipeline import (
    HTMLMarkdownConverter,
    HTMLPreprocessor,
    MarkdownPolisher,
    RequirementProcessor,
    SkillProcessor,
    TechnologyProcessor,
)
from src.poc.tweak.spacy_pipeline.heading_promoter import HeadingPromoter

# Allowed description_selector_match strategies
DESCRIPTION_MATCH_STRATEGIES = {"first", "all", "longest"}


@dataclass
class JobResult:
    """Result of processing a single job through the markdown pipeline.

    Attributes:
        job_id: Unique identifier for the job
        title: Job title
        company: Company name
        sections_detected: Number of markdown sections detected
        keyword_matches: Total number of keyword matches in classifications
        confidence_min: Minimum confidence score across classifications
        confidence_max: Maximum confidence score across classifications
        confidence_avg: Average confidence score across classifications
        requirements: List of extracted requirements (Issue #321)
        skills: List of extracted skills (Issue #321)
        technologies: List of extracted technologies (Issue #321)
        markdown_sections: List of MarkdownSection objects with full metadata (Issue #338)
        errors: List of (stage_name, error_message) tuples for per-stage errors
        warnings: List of (stage_name, warning_message) tuples for per-job warnings (not failures)
        sentences: Sentences split from polished_markdown by poc_sentence_splitter (Issue #643)
    """

    job_id: str
    title: str
    company: str
    sections_detected: int
    keyword_matches: int
    confidence_min: float
    confidence_max: float
    confidence_avg: float
    requirements: List[Dict[str, Any]] = field(default_factory=list)
    skills: List[Dict[str, Any]] = field(default_factory=list)
    technologies: List[Dict[str, Any]] = field(default_factory=list)
    markdown_sections: List[MarkdownSection] = field(default_factory=list)
    errors: List[tuple] = field(default_factory=list)
    warnings: List[Tuple[str, str]] = field(default_factory=list)
    sentences: List[str] = field(default_factory=list)

    def add_error(self, stage: str, error: str) -> None:
        """Add a per-stage error to the result.

        Args:
            stage: Pipeline stage name (e.g., 'preprocessor', 'converter')
            error: Error message
        """
        self.errors.append((stage, error))

    def add_warning(self, stage: str, warning: str) -> None:
        """Add a per-stage warning to the result.

        Warnings do not count as errors (job processing continues normally).

        Args:
            stage: Pipeline stage name (e.g., 'html_scoping')
            warning: Warning message
        """
        self.warnings.append((stage, warning))

    def has_errors(self) -> bool:
        """Check if this job had any processing errors."""
        return len(self.errors) > 0


def load_jobs(path: str) -> List[Dict[str, Any]]:
    """Load and validate jobs from JSON file.

    Validates that:
    - Input is a JSON array
    - Each record contains a 'description' field
    - description field can be null (handled gracefully downstream)

    Args:
        path: Path to JSON file containing job records

    Returns:
        List of job record dicts

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is not an array or records lack description field
        json.JSONDecodeError: If JSON is malformed
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Job file not found: {path}")

    with open(file_path) as f:
        data = json.load(f)

    # Validate input is array
    if not isinstance(data, list):
        raise ValueError(
            f"Expected JSON array at root, got {type(data).__name__}. Input must be an array of job records."
        )

    # Validate each record has description field (but allow null values)
    for i, job in enumerate(data):
        if not isinstance(job, dict):
            raise ValueError(f"Record {i} is not a dict (type: {type(job).__name__}). Each job must be an object.")
        if "description" not in job:
            raise ValueError(
                f"Record {i} (ID: {job.get('id', 'unknown')}) missing 'description' field. "
                "Each job must have a description field (can be null)."
            )

    return data


def process_job(
    job: Dict[str, Any],
    *,
    nlp: spacy.language.Language,
    preprocessor: HTMLPreprocessor,
    converter: HTMLMarkdownConverter,
    polisher: MarkdownPolisher,
    classifier: SectionClassifier,
    ruler: MarkdownSpanRuler,
    req_processor: RequirementProcessor,
    skill_processor: SkillProcessor,
    tech_processor: TechnologyProcessor,
    description_selector: Optional[str] = None,
    description_match: str = "first",
    heading_promoter: Optional[HeadingPromoter] = None,
) -> JobResult:
    """Process a single job through the markdown pipeline.

    Runs job through 8 stages with per-stage error handling. Errors are captured
    in JobResult.errors and do not abort processing.

    Stages:
    0. Scope to selector (optional, Issue #363, #367)
    1. HTMLPreprocessor: Clean raw HTML
    2. HTMLMarkdownConverter: Convert HTML to Markdown
    3. MarkdownPolisher: Polish Markdown formatting
    3b. HeadingPromoter: Promote plain-text headings to markdown (optional, Issue #365)
    4. MarkdownSpanRuler: Parse sections from markdown
    5. SectionClassifier: Classify sections via keyword-based matching
    6. RequirementProcessor: Extract requirements (Issue #321)
    7. SkillProcessor: Extract skills (Issue #321)
    8. TechnologyProcessor: Extract technologies (Issue #321)

    Args:
        job: Job record dict (must have 'id', 'title', 'company', 'description')
        nlp: Configured spaCy Language object with all extensions and components registered
        preprocessor: HTMLPreprocessor instance
        converter: HTMLMarkdownConverter instance
        polisher: MarkdownPolisher instance
        classifier: SectionClassifier instance
        ruler: MarkdownSpanRuler instance for parsing sections
        req_processor: RequirementProcessor instance
        skill_processor: SkillProcessor instance
        tech_processor: TechnologyProcessor instance
        description_selector: Optional CSS selector to scope HTML fragment before processing
        description_match: Strategy for multi-match selection: "first", "all", or "longest"
                          (default "first"). Invalid values treated as "first" with warning.
        heading_promoter: Optional HeadingPromoter instance for promoting plain-text headings
                          (default None skips heading promotion)

    Returns:
        JobResult with processing stats and any errors encountered

    Note:
        This function NEVER raises. All errors are captured in JobResult.errors.
    """
    job_id = job.get("id", "unknown")
    title = job.get("title", "Unknown")
    company = job.get("company", "Unknown")

    # Initialize result
    result = JobResult(
        job_id=job_id,
        title=title,
        company=company,
        sections_detected=0,
        keyword_matches=0,
        confidence_min=1.0,
        confidence_max=0.0,
        confidence_avg=0.0,
    )

    raw_html = job.get("description", "")

    # Handle null description gracefully
    if raw_html is None:
        raw_html = ""

    # Stage 0: Scope to selector if provided (Issue #363, #367)
    if description_selector:
        # Validate description_match strategy (only when selector is provided)
        effective_strategy = description_match
        # isinstance guard: an unhashable value (e.g. list from malformed config) would raise TypeError
        # on set membership and abort the batch; treat it as invalid instead.
        if not isinstance(description_match, str) or description_match not in DESCRIPTION_MATCH_STRATEGIES:
            # Invalid strategy: log warning and use "first"
            result.add_warning(
                "html_scoping",
                f"Invalid description_selector_match value '{description_match}'; "
                f"allowed values are {sorted(DESCRIPTION_MATCH_STRATEGIES)}; falling back to 'first'",
            )
            effective_strategy = "first"

        try:
            from src.poc.tweak.html_scope import scope_to_selector

            scope_result = scope_to_selector(raw_html, description_selector, strategy=effective_strategy)

            # Handle different match scenarios
            if scope_result.match_count == 0:
                # No matches: warn and use full HTML
                result.add_warning(
                    "html_scoping",
                    f"Selector '{description_selector}' matched 0 elements; processing full HTML",
                )
            elif scope_result.fragment:
                # Have a fragment (matched 1+ elements)
                if scope_result.match_count > 1:
                    # Multiple matches: warn with strategy name
                    strategy_msg = {
                        "first": "using first match",
                        "all": "using all matches",
                        "longest": "using longest match",
                    }.get(effective_strategy, "using first match")
                    result.add_warning(
                        "html_scoping",
                        f"Selector '{description_selector}' matched {scope_result.match_count} "
                        f"elements; {strategy_msg}",
                    )
                # Use the scoped fragment (single or strategy-selected of multiple)
                raw_html = scope_result.fragment
        except ValueError as e:
            # Invalid CSS selector: warn and use full HTML
            result.add_warning(
                "html_scoping",
                f"Invalid CSS selector '{description_selector}': {e}; processing full HTML",
            )

    # Stage 1: Preprocess
    try:
        clean_html = preprocessor.process(raw_html)
    except Exception as e:
        result.add_error("preprocessor", str(e))
        return result

    # Stage 2: Convert to Markdown
    try:
        markdown = converter.process(clean_html)
    except Exception as e:
        result.add_error("converter", str(e))
        return result

    # Stage 3: Polish Markdown
    try:
        polished_markdown = polisher.process(markdown)
    except Exception as e:
        result.add_error("polisher", str(e))
        return result

    # Stage 3b: Promote plain-text headings (optional, Issue #365)
    promoted_markdown = polished_markdown
    if heading_promoter is not None:
        try:
            promoted_markdown = heading_promoter.process(polished_markdown)
        except Exception as e:
            result.add_error("heading_promoter", str(e))
            # Non-fatal: continue with unpromoted markdown

    # Stage 4: Parse sections using MarkdownSpanRuler
    try:
        sections = ruler.parse(promoted_markdown)
        result.sections_detected = len(sections)

        # Stage 5: Classify each section and aggregate confidence stats
        if sections:
            confidences = []
            markdown_sections = []

            for section_idx, section in enumerate(sections):
                try:
                    classification = classifier.classify(section)

                    # Extract primary (highest-confidence) type for backward compatibility
                    # (Issue #338: preserving full multi-type data without breaking existing fields)
                    if classification.all_types:
                        primary_type = classification.all_types[0]
                        confidences.append(primary_type.confidence)

                        # Count total keyword matches from all candidate types
                        for type_class in classification.all_types:
                            result.keyword_matches += len(type_class.matched_keywords)

                        # Build all_types list: convert TypeClassification tuples to dicts
                        # Note: Store full precision here; rounding only happens in MarkdownSection.to_dict()
                        all_types_list = [
                            {
                                "section_type": type_class.section_type.value,
                                "confidence": type_class.confidence,
                            }
                            for type_class in classification.all_types
                        ]

                        # Build keyword_matches list: convert KeywordMatch tuples to dicts
                        keyword_matches_list = [
                            {
                                "keyword": km.keyword,
                                "section_type": km.section_type.value,
                                "source": km.source,
                                "position": km.position,
                            }
                            for km in classification.keyword_matches
                        ]

                        # Create MarkdownSection with full classification metadata (Issue #338, #295)
                        md_section = MarkdownSection(
                            section_id=f"sec_{section_idx}",
                            heading=section.title or "",
                            content=section.content,
                            section_type=primary_type.section_type.value,
                            confidence=primary_type.confidence,
                            line_start=section.start_line or 0,
                            line_end=section.end_line or 0,
                            matched_keywords=list(primary_type.matched_keywords),
                            # Preserve full classification data (Issue #295: closes data-loss gap)
                            all_types=all_types_list,
                            labels=[label.value for label in classification.labels],
                            is_skip=classification.is_skip,
                            keyword_matches=keyword_matches_list,
                        )
                        markdown_sections.append(md_section)
                    else:
                        # No types classified: create default section with zero confidence
                        md_section = MarkdownSection(
                            section_id=f"sec_{section_idx}",
                            heading=section.title or "",
                            content=section.content,
                            section_type="unknown",
                            confidence=0.0,
                            line_start=section.start_line or 0,
                            line_end=section.end_line or 0,
                            matched_keywords=[],
                            all_types=[],
                            labels=[],
                            is_skip=False,
                            keyword_matches=[],
                        )
                        markdown_sections.append(md_section)

                except Exception as sec_err:
                    result.add_error("section_classification", str(sec_err))
                    # Continue processing other sections

            result.markdown_sections = markdown_sections

            # Aggregate confidence stats across all sections
            if confidences:
                result.confidence_min = min(confidences)
                result.confidence_max = max(confidences)
                result.confidence_avg = sum(confidences) / len(confidences)
            else:
                # If all section classifications failed, reset to valid defaults
                result.confidence_min = 0.0
                result.confidence_max = 0.0
                result.confidence_avg = 0.0

    except Exception as e:
        result.add_error("section_parsing", str(e))
        # Errors in section parsing/classification do not halt further processing;
        # we report sections detected and partial confidence stats if any

    # Stages 6-8: Extract requirements, skills, technologies from doc (per-stage error handling)
    try:
        # Create a spaCy Doc for extraction using the fully-configured nlp pipeline
        # This ensures all extensions and components are available
        doc = nlp(polished_markdown)
        # Sentences come from polished_markdown, not promoted_markdown (intentional; no section alignment)
        result.sentences = list(doc._.poc_sentences or [])

        # Ensure sections are populated on the doc for classification
        doc._.sections = sections  # Pre-populate sections from ruler output

        # Apply classifiers and extract data
        from src.poc.tweak.spacy_pipeline import SectionClassifierComponent

        section_classifier = SectionClassifierComponent(nlp, "section_classifier")
        doc = section_classifier(doc)

        # Extract requirements
        try:
            doc = req_processor(doc)
            result.requirements = doc._.requirements if doc._.requirements else []
        except Exception as e:
            result.add_error("requirement_extraction", str(e))

        # Extract skills
        try:
            doc = skill_processor(doc)
            result.skills = doc._.skills if doc._.skills else []
        except Exception as e:
            result.add_error("skill_extraction", str(e))

        # Extract technologies
        try:
            doc = tech_processor(doc)
            result.technologies = doc._.technologies if doc._.technologies else []
        except Exception as e:
            result.add_error("technology_extraction", str(e))

    except Exception as e:
        result.add_error("extraction_pipeline", str(e))

    return result


def run_batch(
    input_path: str,
    description_selector: Optional[str] = None,
    description_match: str = "first",
    promote_headings: bool = True,
    config_dir: str = "config_test",
    enable_poc_sentence_splitter: bool = True,
) -> List[JobResult]:
    """Run batch processing on all jobs in input file.

    Loads spaCy model, instantiates pipeline components once, then processes
    all jobs sequentially through the pipeline.

    When ``description_selector`` is None, each job's selector and match strategy
    are resolved from its ``source_config`` key (Issue #376). A global
    ``description_selector`` (e.g. from ``--company``) overrides this for all jobs.
    A ``source_config`` that cannot be resolved (missing config dir, unknown key,
    unparsable or malformed config) does not fail the batch: the job is processed unscoped
    and a ``source_config`` warning is recorded on that job. The warning is recorded per
    affected job. Each distinct ``source_config`` is resolved once per batch (cache keyed by
    key); a cache miss loads the company configs twice (once for selector, once for match).

    Args:
        input_path: Path to JSON file with job records
        description_selector: Optional CSS selector to scope HTML fragments. When set,
                          applies to every job and disables per-job resolution.
        description_match: Strategy for multi-match selection ("first", "all", "longest").
                          Default "first". Applies to the global description_selector and to
                          records without source_config; resolved source_config match wins otherwise.
        promote_headings: Whether to promote plain-text headings (default True, Issue #365)
        config_dir: Directory of company config JSON files used to resolve per-job
                          selectors from ``source_config`` (default "config_test")
        enable_poc_sentence_splitter: Whether to add the poc_sentence_splitter pipe and
                          populate ``JobResult.sentences`` (default True, Issue #643)

    Returns:
        List of JobResult objects (one per job)

    Raises:
        FileNotFoundError: If input file not found
        ValueError: If input file is not valid JSON array
        OSError: If spaCy model cannot be loaded
    """
    # Load jobs
    jobs = load_jobs(input_path)

    # Load spaCy model once
    try:
        nlp = spacy.load("en_core_web_md")
    except OSError as e:
        raise OSError(
            f"Failed to load spaCy model 'en_core_web_md': {e}. Run: uv run python -m spacy download en_core_web_md"
        ) from e

    # Explicit entity_ruler registration (required by TechnologyProcessor, D5 decision)
    if "entity_ruler" not in nlp.pipe_names:
        nlp.add_pipe("entity_ruler", before="ner")

    # Sentence splitter (Issue #643); default-on, disable with --no-poc-sentences
    if enable_poc_sentence_splitter and "poc_sentence_splitter" not in nlp.pipe_names:
        nlp.add_pipe("poc_sentence_splitter")

    # Load technology patterns into entity_ruler (Issue #321 fix)
    ruler = nlp.get_pipe("entity_ruler")
    tech_patterns = TechnologyProcessor.generate_tech_patterns()
    ruler.add_patterns(tech_patterns)  # type: ignore

    # Instantiate components once
    preprocessor = HTMLPreprocessor()
    converter = HTMLMarkdownConverter()
    polisher = MarkdownPolisher()
    heading_promoter = HeadingPromoter() if promote_headings else None
    markdown_ruler = MarkdownSpanRuler(nlp)
    classifier = SectionClassifier()

    # Add pipeline components (all use last=True, D3 decision)
    req_processor = RequirementProcessor(nlp, "requirement_processor")
    skill_processor = SkillProcessor(nlp, "skill_processor")
    tech_processor = TechnologyProcessor(nlp, "technology_processor")

    # Process all jobs
    results = []
    # Cache of source_config -> (selector, match, error): skips re-resolving a key already seen in this batch
    scoping_cache: Dict[str, Tuple[Optional[str], str, Optional[str]]] = {}
    for job in jobs:
        job_selector = description_selector
        job_match = description_match
        resolve_error: Optional[str] = None
        source_config = job.get("source_config")
        if description_selector is None and source_config:
            # Per-job scoping from source_config (Issue #376); --company (global) still wins above
            key = str(source_config).strip()
            if key not in scoping_cache:
                scoping_cache[key] = _resolve_job_scoping(key, config_dir)
            job_selector, job_match, resolve_error = scoping_cache[key]

        result = process_job(
            job,
            nlp=nlp,
            preprocessor=preprocessor,
            converter=converter,
            polisher=polisher,
            classifier=classifier,
            ruler=markdown_ruler,
            req_processor=req_processor,
            skill_processor=skill_processor,
            tech_processor=tech_processor,
            description_selector=job_selector,
            description_match=job_match,
            heading_promoter=heading_promoter,
        )
        if resolve_error is not None:
            # Unknown/invalid source_config: process job unscoped (as before), record a warning
            result.add_warning("source_config", resolve_error)
        results.append(result)

    return results


def print_summary(results: List[JobResult]) -> str:
    """Generate and print summary of batch processing results.

    Outputs per-job statistics and aggregate stats.

    Args:
        results: List of JobResult objects from run_batch()

    Returns:
        Formatted summary string (also prints to stdout)
    """
    lines = []

    # Header
    lines.append("=" * 80)
    lines.append("BATCH PROCESSING SUMMARY")
    lines.append("=" * 80)
    lines.append("")

    # Per-job results
    lines.append("PER-JOB RESULTS:")
    lines.append("-" * 80)

    for i, result in enumerate(results, 1):
        lines.append(f"\n[Job {i}] {result.title}")
        lines.append(f"  Job ID: {result.job_id}")
        lines.append(f"  Company: {result.company}")
        lines.append(f"  Sections Detected: {result.sections_detected}")
        lines.append(f"  Keyword Matches: {result.keyword_matches}")
        if result.sections_detected > 0:
            lines.append(
                f"  Confidence Scores: min={result.confidence_min:.3f}, "
                f"max={result.confidence_max:.3f}, avg={result.confidence_avg:.3f}"
            )
        else:
            lines.append("  Confidence Scores: N/A (no sections detected)")

        # Extraction stats (Issue #321)
        lines.append("  Extracted:")
        lines.append(f"    - Requirements: {len(result.requirements)}")
        lines.append(f"    - Skills: {len(result.skills)}")
        lines.append(f"    - Technologies: {len(result.technologies)}")

        if result.has_errors():
            lines.append(f"  Errors ({len(result.errors)}):")
            for stage, error in result.errors:
                lines.append(f"    - {stage}: {error}")
        else:
            lines.append("  Status: SUCCESS")

        # Show warnings (if any) - warnings do not count as failures
        if result.warnings:
            lines.append(f"  Warnings ({len(result.warnings)}):")
            for stage, warning in result.warnings:
                lines.append(f"    - {stage}: {warning}")

    # Aggregate statistics
    lines.append("")
    lines.append("-" * 80)
    lines.append("AGGREGATE STATISTICS:")
    lines.append("-" * 80)

    total_jobs = len(results)
    successful = sum(1 for r in results if not r.has_errors())
    failed = total_jobs - successful
    total_sections = sum(r.sections_detected for r in results)
    total_keywords = sum(r.keyword_matches for r in results)
    total_requirements = sum(len(r.requirements) for r in results)
    total_skills = sum(len(r.skills) for r in results)
    total_technologies = sum(len(r.technologies) for r in results)

    lines.append(f"Total Jobs Processed: {total_jobs}")
    lines.append(f"Successful: {successful}")
    lines.append(f"Failed: {failed}")
    lines.append(f"Success Rate: {successful / total_jobs * 100:.1f}%")
    lines.append(f"Total Sections Detected: {total_sections}")
    lines.append(f"Total Keyword Matches: {total_keywords}")
    lines.append(f"Total Requirements Extracted: {total_requirements}")
    lines.append(f"Total Skills Extracted: {total_skills}")
    lines.append(f"Total Technologies Extracted: {total_technologies}")

    # Confidence stats
    confidences_with_values = [r.confidence_avg for r in results if r.sections_detected > 0 and r.confidence_avg > 0]
    if confidences_with_values:
        avg_confidence = sum(confidences_with_values) / len(confidences_with_values)
        lines.append(f"Average Confidence (across all jobs): {avg_confidence:.3f}")

    lines.append("")
    lines.append("=" * 80)

    summary = "\n".join(lines)
    print(summary)
    return summary


def _resolve_description_selector(company: str, config_dir: str) -> str:
    """Resolve description_selector from company config (lazy import).

    Loads company configs only when called (lazy import to avoid playwright/spaCy imports
    when --company flag is not used).

    Args:
        company: Company config key or name to search for
        config_dir: Directory containing config JSON files

    Returns:
        The description_selector value from matched company config

    Raises:
        ValueError: If company not found, or found but has no selectors.description_selector
    """
    # Lazy import: only import common.py when --company is used
    from src.poc.tweak.common import load_all_company_configs, resolve_company_selectors

    merged_config = load_all_company_configs(config_dir)

    # Try to resolve selectors for the given company
    selectors = resolve_company_selectors(company, merged_config)

    if not selectors:
        # No selectors found for this company
        raise ValueError(f"No configuration found for company '{company}' in {config_dir}")

    description_selector = selectors.get("description_selector")
    if not description_selector:
        raise ValueError(f"Company '{company}' config found but has no 'selectors.description_selector' defined")

    if not isinstance(description_selector, str):
        raise ValueError(
            f"Company '{company}' config has non-string 'selectors.description_selector' "
            f"({type(description_selector).__name__})"
        )

    return description_selector


def _resolve_description_match(company: str, config_dir: str) -> str:
    """Resolve description_selector_match from company config (lazy import, Issue #367).

    Loads company configs only when called (lazy import to avoid playwright/spaCy imports
    when --company flag is not used).

    Returns "first" (default) if the key is not present in config.

    Args:
        company: Company config key or name to search for
        config_dir: Directory containing config JSON files

    Returns:
        The description_selector_match value from matched company config,
        or "first" if key is absent

    Raises:
        ValueError: If company not found
    """
    # Lazy import: only import common.py when --company is used
    from src.poc.tweak.common import load_all_company_configs, resolve_company_selectors

    merged_config = load_all_company_configs(config_dir)

    # Try to resolve selectors for the given company
    selectors = resolve_company_selectors(company, merged_config)

    if not selectors:
        # No selectors found for this company
        raise ValueError(f"No configuration found for company '{company}' in {config_dir}")

    # Return the strategy value, or "first" if key is absent
    return selectors.get("description_selector_match", "first")


def _resolve_job_scoping(source_config: str, config_dir: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Resolve (description_selector, description_match, error) for one source_config key (Issue #376).

    Never raises. On any failure (ValueError for unknown key / missing selector / unparsable
    config, OSError for a missing config dir, or AttributeError/TypeError from a malformed
    config shape such as a top-level JSON array or a non-dict company value) returns
    (None, "first", message) so the job is processed unscoped, matching the no-source_config
    default; the caller records the message as a ``source_config`` warning on each affected job.
    """
    try:
        selector = _resolve_description_selector(source_config, config_dir)
        match = _resolve_description_match(source_config, config_dir)
    except Exception as e:
        # Deliberately broad: user-supplied config JSON can have any shape, and a malformed
        # config must never abort the whole batch. Degrade this key to unscoped instead.
        return (
            None,
            "first",
            f"source_config '{source_config}' could not be resolved: {e}",
        )
    return selector, match, None


def main() -> int:
    """CLI entry point for batch processor.

    Parses arguments, runs batch processing, prints summary, and optionally
    exports results to JSON.

    Returns:
        Exit code (0 on success, 1 on error)
    """
    parser = argparse.ArgumentParser(description="POC Batch Processor for multi-job markdown pipeline")
    parser.add_argument(
        "--input-path",
        type=str,
        default="data/work/details_test.json",
        help="Path to JSON file with job records (default: data/work/details_test.json)",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Output path for JSON results (optional)",
    )
    parser.add_argument(
        "--company",
        type=str,
        default=None,
        help="Company config key or name; selector applies to ALL records, overriding source_config (optional)",
    )
    parser.add_argument(
        "--config-dir",
        type=str,
        default="config_test",
        help="Company config JSON directory; also resolves each record's source_config (default: config_test)",
    )
    parser.add_argument(
        "--no-promote-headings",
        action="store_true",
        help="Disable plain-text heading promotion (default: headings promoted, Issue #365)",
    )
    parser.add_argument(
        "--no-poc-sentences",
        action="store_true",
        help="Disable poc_sentence_splitter; sentences field stays empty (default: enabled, Issue #643)",
    )

    args = parser.parse_args()

    # Resolve description_selector and description_selector_match from --company if provided
    description_selector = None
    description_match = "first"
    if args.company:
        try:
            description_selector = _resolve_description_selector(args.company, args.config_dir)
            description_match = _resolve_description_match(args.company, args.config_dir)
        except (ValueError, FileNotFoundError, AttributeError, TypeError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    try:
        results = run_batch(
            args.input_path,
            description_selector=description_selector,
            description_match=description_match,
            promote_headings=not args.no_promote_headings,
            config_dir=args.config_dir,
            enable_poc_sentence_splitter=not args.no_poc_sentences,
        )
        print_summary(results)

        # Export to JSON if requested
        if args.output_json:
            with open(args.output_json, "w") as f:
                json.dump([asdict(r) for r in results], f, indent=2)
            print(f"\nResults saved to {args.output_json}")

        return 0
    except (FileNotFoundError, ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
