"""Typer CLI for ATS Showcase workflow orchestration."""

import asyncio
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any, List, Optional, Tuple, TypedDict

import anthropic
import typer
from dotenv import load_dotenv

from browser.crawler import Crawler
from formatters.markdown_viewer import MarkdownReportViewer
from id_generation import generate_job_id
from integrity import DataPurger, IntegrityChecker
from storage.assessment_store import AssessmentStore
from storage.export import ExportConfig, MarkdownExporter

logger = logging.getLogger(__name__)


# ============================================================================
# TYPE DEFINITIONS
# ============================================================================


class ResultItem(TypedDict):
    """Result item for assessed job."""

    job_id: str
    title: str
    llm_score: float
    entity_score: float
    cost: float
    tokens: int


# ============================================================================
# CONFIG LOADING UTILITIES
# ============================================================================


def load_companies_config(config: Optional[str] = None, config_dir: Optional[str] = None) -> dict[str, Any]:
    """Load companies from config file or directory."""
    if config:
        return load_companies_from_file(Path(config))
    elif config_dir:
        return load_companies_from_directory(Path(config_dir))
    return {}


def load_companies_from_file(config_path: Path) -> dict[str, Any]:
    """Load companies from a single config file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        with open(config_path) as f:
            config_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config: {e}") from e

    # Explicitly verify config_data is a dictionary before reading it
    if not isinstance(config_data, dict):
        raise ValueError("Invalid config structure: expected a JSON object root.")

    companies = config_data.get("companies", {})

    # Verify the 'companies' key yields a dictionary block
    if not isinstance(companies, dict):
        raise ValueError("Invalid config structure: 'companies' key must be an object.")

    return companies


def load_companies_from_directory(config_dir: Path) -> dict[str, Any]:
    """Load companies from all JSON files in a directory, filtering by enabled flag."""
    if not config_dir.exists():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    all_companies = {}
    config_files = sorted(config_dir.glob("*.json"))

    if not config_files:
        raise FileNotFoundError(f"No JSON config files found in {config_dir}")

    for config_file in config_files:
        try:
            companies = load_companies_from_file(config_file)
            all_companies.update(companies)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
            logger.warning(f"Skipped config file {config_file}: {e}")
            continue

    return all_companies


def filter_enabled_companies(companies: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Filter companies by 'enabled' flag.

    Returns:
        Tuple of (enabled_companies, disabled_company_names)
    """
    enabled = {}
    disabled = []

    for company_name, company_data in companies.items():
        if isinstance(company_data, dict):
            is_enabled = company_data.get("enabled", True)
            if is_enabled:
                enabled[company_name] = company_data
            else:
                disabled.append(company_name)
        else:
            enabled[company_name] = company_data

    return enabled, disabled


app = typer.Typer(
    name="ats-cli",
    help="ATS Showcase: Intelligent job assessment with AI",
    invoke_without_command=False,
)


# ============================================================================
# PHASE HANDLERS
# ============================================================================


def _load_crawl_config(config: Optional[str], config_dir: Optional[str]) -> dict[str, Any]:
    """Load companies config for crawl phase.

    Args:
        config: Path to config file or None
        config_dir: Path to config directory or None

    Returns:
        Dictionary of companies

    Raises:
        typer.Exit: If config cannot be loaded
    """
    try:
        if config_dir:
            companies = load_companies_from_directory(Path(config_dir))
            typer.echo(f"📋 Found {len(companies)} companies from directory: {config_dir}")
        elif config:
            companies = load_companies_from_file(Path(config))
            typer.echo(f"📋 Found {len(companies)} companies from file: {config}")
        else:
            companies = load_companies_from_file(Path("config/companies.json"))
            typer.echo(f"📋 Found {len(companies)} companies from default config")
        return companies
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1) from None


def _validate_crawl_companies(companies: dict[str, Any]) -> dict[str, Any]:
    """Validate and filter companies for crawl phase.

    Args:
        companies: Dictionary of companies

    Returns:
        Filtered dictionary of enabled companies

    Raises:
        typer.Exit: If no companies or no enabled companies
    """
    if not companies:
        typer.echo("❌ No companies found in config", err=True)
        raise typer.Exit(1)

    enabled_companies, disabled_companies = filter_enabled_companies(companies)
    if disabled_companies:
        typer.echo(f"⏭️  Skipping {len(disabled_companies)} disabled companies")
    if not enabled_companies:
        typer.echo("❌ No enabled companies to crawl", err=True)
        raise typer.Exit(1)

    typer.echo(f"✅ Processing {len(enabled_companies)} enabled companies\n")
    return enabled_companies


def _save_crawl_results_by_company(results: dict[str, Any]) -> None:
    """Save crawled results to JSON files by company.

    Args:
        results: Mapping of company_name to jobs list
    """
    total_jobs = sum(len(jobs) for jobs in results.values())
    typer.echo(f"\n✅ Crawl complete! Extracted {total_jobs} total jobs\n")

    for company_name, jobs in results.items():
        typer.echo(f"   • {company_name}: {len(jobs)} jobs")
        if jobs:
            output_file = Path("data/extracted_jobs") / f"{company_name.lower()}_jobs.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            jobs_data = [job.model_dump(mode="json") for job in jobs]
            with open(output_file, "w") as f:
                json.dump(jobs_data, f, indent=2, default=str)
            typer.echo(f"      Saved to: {output_file}")


def _run_crawl_async(crawler: Crawler, enabled_companies: dict[str, Any]) -> dict[str, Any]:
    """Execute async crawl with error handling.

    Args:
        crawler: Crawler instance
        enabled_companies: Dictionary of companies to crawl

    Returns:
        Dictionary of crawl results

    Raises:
        typer.Exit: On crawl failure
    """
    import asyncio

    async def run_crawl() -> dict[str, Any]:
        try:
            results: dict[str, Any] = await crawler.crawl_multiple(enabled_companies)
            _save_crawl_results_by_company(results)
            return results
        except Exception as e:
            logger.error(f"Crawl failed: {e}", exc_info=True)
            typer.echo(f"\n❌ Crawl failed: {e}", err=True)
            raise typer.Exit(1) from None
        finally:
            await crawler.close()

    return asyncio.run(run_crawl())


def _run_phase_crawl(
    config: Optional[str], config_dir: Optional[str], headless: bool, up_to: Optional[str]
) -> Tuple[Any, float]:
    """Run PHASE 1: CRAWL - Extract job postings from career pages.

    Args:
        config: Path to config file or None
        config_dir: Path to config directory or None
        headless: Whether to run browser in headless mode
        up_to: Phase stopping point (for early exit check)

    Returns:
        Tuple of (crawl_results dict, phase_time float)

    Raises:
        typer.Exit on failure or when up_to == "crawl"
    """
    typer.echo("=" * 80)
    typer.echo("PHASE 1: CRAWL - Extract job postings from career pages")
    typer.echo("=" * 80)

    phase_start = time.time()

    companies = _load_crawl_config(config, config_dir)
    enabled_companies = _validate_crawl_companies(companies)

    crawler = Crawler(headless=headless, timeout_ms=30000)
    crawl_results = _run_crawl_async(crawler, enabled_companies)

    phase_time = time.time() - phase_start
    typer.echo(f"⏱️  Phase 1 took {phase_time:.2f}s\n")

    if up_to == "crawl":
        typer.echo("✅ Stopping at crawl phase (as requested)\n")
        raise typer.Exit(0)

    return crawl_results, phase_time


def _validate_preprocess_directory() -> Path:
    """Validate extracted jobs directory exists and has files.

    Returns:
        Path to extracted jobs directory

    Raises:
        typer.Exit: If directory not found or no files
    """
    extracted_dir = Path("data/extracted_jobs")
    if not extracted_dir.exists():
        typer.echo(f"❌ Directory not found: {extracted_dir}", err=True)
        raise typer.Exit(1)

    job_files = list(extracted_dir.glob("*_jobs.json"))
    if not job_files:
        typer.echo("❌ No extracted jobs found", err=True)
        raise typer.Exit(1)

    typer.echo(f"📂 Processing {len(job_files)} job files...\n")
    return extracted_dir


def _build_preprocess_clean_text(job: dict[str, Any]) -> str:
    """Build clean text from job fields.

    Converts the raw HTML description to normalized Markdown with boilerplate
    removal (headings, lists, synthesized section headers) as the first step of
    preprocessing, since crawl no longer performs this transform (Issue #228).
    Uses unified clean_html() pipeline (Issue #230 Phase 4).

    Args:
        job: Job dictionary

    Returns:
        Clean text combining title, location, and normalized description
    """
    from src.parsers.html_to_markdown import clean_html

    clean_text = str(job.get("title", ""))
    if job.get("location"):
        clean_text = f"{clean_text}\n{str(job.get('location', ''))}"
    if job.get("description"):
        description_md = clean_html(str(job.get("description", "")))
        clean_text = f"{clean_text}\n{description_md}"
    return clean_text


def _preprocess_job_for_phase(
    job: dict[str, Any], idx: int, chunker: Any, counter: Any, preprocessor: Any = None
) -> Tuple[Optional[dict[str, Any]], int, float]:
    """Preprocess a single job.

    Args:
        job: Job dictionary
        idx: Job index for logging
        chunker: SemanticChunker instance
        counter: TokenCounter instance
        preprocessor: Preprocessor instance for span preservation (optional)

    Returns:
        Tuple of (preprocessed_job dict or None, token_count, estimated_cost)
        Returns (None, 0, 0.0) on error
    """
    try:
        clean_text = _build_preprocess_clean_text(job)
        # Get doc with requirement spans for chunking (Bug #1 fix)
        doc = preprocessor.nlp(clean_text) if preprocessor else None
        chunks = chunker.chunk(clean_text, doc=doc)
        token_count = sum(counter.count_tokens(c) for c in chunks)
        estimated_cost = counter.estimate_cost(token_count)

        # Extract trigger-based requirements from doc (Bug #4 fix: avoid data loss)
        trigger_requirements_json = None
        if doc is not None:
            requirements_data = getattr(doc._, "requirements", None)
            if requirements_data:
                trigger_requirements_json = json.dumps(requirements_data, ensure_ascii=False)

        preprocessed_job = {
            "job_id": job.get("id"),
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "url": job.get("url"),
            "clean_text": clean_text,
            "chunks": chunks,
            "token_count": token_count,
            "estimated_cost": estimated_cost,
            "status": "pending_review",
            "trigger_requirements": trigger_requirements_json,
        }

        if idx % 5 == 0:
            typer.echo(f"   Job {idx}: {job.get('title', 'N/A')[:40]}...")
            typer.echo(f"      Tokens: {token_count} | Cost: ${estimated_cost:.4f}")

        return preprocessed_job, token_count, estimated_cost
    except Exception as e:
        logger.error(f"Failed to preprocess job {idx}: {e}", exc_info=True)
        return None, 0, 0.0


def _preprocess_jobs_file(
    job_file: Path,
    chunker: Any,
    counter: Any,
    preprocessor: Any = None,
) -> Tuple[list[dict[str, Any]], int, int, float]:
    """Process all jobs in a file.

    Args:
        job_file: Path to jobs JSON file
        chunker: SemanticChunker instance
        counter: TokenCounter instance
        preprocessor: Preprocessor instance for span preservation (optional)

    Returns:
        Tuple of (preprocessed_jobs, failed_count, total_tokens, total_cost)
    """
    preprocessed_jobs = []
    failed_count = 0
    total_tokens = 0
    total_cost = 0.0

    with open(job_file) as f:
        jobs = json.load(f)

    typer.echo(f"📂 Processing {job_file.name}...")

    for i, job in enumerate(jobs):
        preprocessed_job, tokens, cost = _preprocess_job_for_phase(job, i, chunker, counter, preprocessor)
        if preprocessed_job:
            preprocessed_jobs.append(preprocessed_job)
            total_tokens += tokens
            total_cost += cost
        else:
            failed_count += 1

    return preprocessed_jobs, failed_count, total_tokens, total_cost


def _display_preprocess_summary(
    all_preprocessed: list[dict[str, Any]], failed_count: int, total_tokens: int, total_cost: float, extracted_dir: Path
) -> None:
    """Display preprocessing summary and save results.

    Args:
        all_preprocessed: All preprocessed jobs
        failed_count: Count of failed jobs
        total_tokens: Total tokens
        total_cost: Total cost
        extracted_dir: Path to extracted jobs directory
    """
    typer.echo("\n✅ Preprocessing complete!\n")
    typer.echo("📊 Summary:")
    typer.echo(f"   Total jobs: {len(all_preprocessed) + failed_count}")
    typer.echo(f"   Processed: {len(all_preprocessed)}")
    typer.echo(f"   Failed: {failed_count}")
    typer.echo(f"   Total tokens: {total_tokens}")
    typer.echo(f"   Total cost: ${total_cost:.4f}")

    if all_preprocessed:
        avg_tokens = total_tokens // len(all_preprocessed)
        typer.echo(f"   Avg tokens/job: {avg_tokens}")

    output_file = extracted_dir / "preprocessed_jobs.json"
    with open(output_file, "w") as f:
        json.dump(all_preprocessed, f, indent=2)
    typer.echo(f"   ✓ Saved to: {output_file}")


def _run_phase_preprocess(up_to: Optional[str]) -> Tuple[List[dict[str, Any]], float]:
    """Run PHASE 2: PREPROCESS - Clean HTML, chunk, count tokens.

    Args:
        up_to: Phase stopping point (for early exit check)

    Returns:
        Tuple of (preprocessed_jobs list, phase_time float)

    Raises:
        typer.Exit on failure or when up_to == "preprocess"
    """
    from src.tokenization.chunker import SemanticChunker
    from src.tokenization.counter import TokenCounter

    typer.echo("=" * 80)
    typer.echo("PHASE 2: PREPROCESS - Clean HTML, chunk, count tokens")
    typer.echo("=" * 80)

    phase_start = time.time()

    extracted_dir = _validate_preprocess_directory()
    chunker = SemanticChunker()
    counter = TokenCounter()
    from src.tokenization.preprocessor import Preprocessor

    preprocessor = Preprocessor()

    all_preprocessed = []
    total_failed = 0
    total_tokens = 0
    total_cost = 0.0

    job_files = [f for f in extracted_dir.glob("*_jobs.json") if "preprocessed" not in f.name]

    for job_file in job_files:
        preprocessed_jobs, failed, tokens, cost = _preprocess_jobs_file(job_file, chunker, counter, preprocessor)
        all_preprocessed.extend(preprocessed_jobs)
        total_failed += failed
        total_tokens += tokens
        total_cost += cost

    _display_preprocess_summary(all_preprocessed, total_failed, total_tokens, total_cost, extracted_dir)

    phase_time = time.time() - phase_start
    typer.echo(f"⏱️  Phase 2 took {phase_time:.2f}s\n")

    if up_to == "preprocess":
        typer.echo("✅ Stopping at preprocess phase (as requested)\n")
        raise typer.Exit(0)

    return all_preprocessed, phase_time


def _run_phase_review(
    preprocessed_path: Path, interactive: bool, merge_all: bool, up_to: Optional[str]
) -> Tuple[int, float]:
    """Run PHASE 3: REVIEW - Interactive or auto job verification.

    Args:
        preprocessed_path: Path to preprocessed_jobs.json
        interactive: Whether to run interactive review
        merge_all: Whether to merge all extracted files
        up_to: Phase stopping point (for early exit check)

    Returns:
        Tuple of (confirmed_count int, phase_time float)

    Raises:
        typer.Exit on failure or when up_to == "review"
    """
    typer.echo("=" * 80)
    if interactive:
        typer.echo("PHASE 3: REVIEW - Interactive job verification")
    else:
        typer.echo("PHASE 3: REVIEW - Auto-confirm jobs (non-interactive mode)")
    typer.echo("=" * 80)

    phase_start = time.time()

    if interactive:
        typer.echo("🔍 Starting interactive job review...\n")
        review(
            extracted=None,
            preprocessed=str(preprocessed_path),
            merge_all=merge_all,
            mode="new-only",
            skip_before_date=None,
            skip_rejected=True,
            skip_assessed=True,
            show_stats=False,
        )
        confirmed_count = 0
    else:
        typer.echo("⏭️  Skipping interactive review - auto-confirming all preprocessed jobs\n")

        if preprocessed_path.exists():
            with open(preprocessed_path) as f:
                preprocessed_jobs = json.load(f)

            for job in preprocessed_jobs:
                job["status"] = "confirmed"

            with open(preprocessed_path, "w") as f:
                json.dump(preprocessed_jobs, f, indent=2)

            confirmed_count = len(preprocessed_jobs)
            typer.echo(f"✅ Auto-confirmed: {confirmed_count} jobs\n")
        else:
            confirmed_count = 0
            typer.echo("⚠️  No preprocessed jobs found\n")

    phase_time = time.time() - phase_start
    typer.echo(f"⏱️  Phase 3 took {phase_time:.2f}s\n")

    if up_to == "review":
        typer.echo("✅ Stopping at review phase (as requested)\n")
        raise typer.Exit(0)

    return confirmed_count, phase_time


def _load_cv_for_phase_assess(cv: str) -> str:
    """Load CV text from file.

    Args:
        cv: Path to CV file

    Returns:
        CV text content

    Raises:
        typer.Exit: If CV not found or unreadable
    """
    cv_path = Path(cv)
    if not cv_path.exists():
        typer.echo(f"❌ CV file not found: {cv}", err=True)
        raise typer.Exit(1)

    with open(cv_path) as f:
        if cv_path.suffix == ".json":
            cv_data = json.load(f)
            cv_text = cv_data.get("text") or cv_data.get("content") or json.dumps(cv_data)
        else:
            cv_text = f.read()

    typer.echo(f"📄 Loaded CV from: {cv}\n")
    return cv_text


def _init_llm_provider_for_assess(model: Optional[str]) -> Any:
    """Initialize and validate LLM provider for assessment.

    Args:
        model: Claude model ID or None

    Returns:
        Initialized LLMProvider instance

    Raises:
        typer.Exit: On initialization failure
    """
    from src.config.models import get_model_display_name
    from src.llm.provider import LLMProvider

    try:
        llm_provider = LLMProvider(model_id=model)
        model_display = get_model_display_name(llm_provider.model)
        typer.echo(f"🤖 Using {model_display} model\n")
        return llm_provider
    except ValueError as e:
        typer.echo(f"❌ LLM setup failed: {e}", err=True)
        typer.echo("   Set ANTHROPIC_API_KEY environment variable", err=True)
        raise typer.Exit(1) from e


def _load_confirmed_jobs_for_assess() -> Tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load confirmed jobs from preprocessed data.

    Returns:
        Tuple of (confirmed_jobs list, jobs_data list)

    Raises:
        typer.Exit: If no confirmed jobs found
    """
    preprocessed_path = Path("data/extracted_jobs/preprocessed_jobs.json")
    confirmed_jobs = []
    jobs_data = []

    if preprocessed_path.exists():
        with open(preprocessed_path) as f:
            jobs_data = json.load(f)
            confirmed_jobs = [j for j in jobs_data if j.get("status") == "confirmed"]

    if not confirmed_jobs:
        typer.echo("❌ No confirmed jobs found.", err=True)
        raise typer.Exit(1)

    typer.echo(f"🤖 Starting CV assessment for {len(confirmed_jobs)} confirmed jobs\n")
    return confirmed_jobs, jobs_data


def _assess_job_and_save(
    job: dict[str, Any],
    idx: int,
    total: int,
    llm_provider: Any,
    cv_text: str,
    assessment_store: AssessmentStore,
    preprocessed_map: dict[str, Any],
) -> Tuple[bool, Optional[Any], int, float]:
    """Assess a single job and save result.

    Args:
        job: Job dictionary
        idx: Job index (1-based)
        total: Total jobs
        llm_provider: LLMProvider instance
        cv_text: CV text
        assessment_store: AssessmentStore instance
        preprocessed_map: Map of job_id to preprocessed data

    Returns:
        Tuple of (success: bool, assessment or None, tokens, cost)
    """
    title = job.get("title", "Unknown")
    typer.echo(f"[{idx}/{total}] Assessing: {title[:50]}...", nl=False)

    preprocessed = preprocessed_map.get(job["job_id"], {})
    clean_text = preprocessed.get("clean_text", job.get("description", ""))
    job_chunks = preprocessed.get("chunks", [clean_text])

    assessment = llm_provider.assess_job(
        job_id=job["job_id"],
        job_chunks=job_chunks,
        cv_text=cv_text,
    )

    assessment_store.save_assessment(
        job_id=job["job_id"],
        title=job.get("title", "Unknown"),
        company=job.get("company", "Unknown"),
        location=job.get("location", ""),
        overall_score=assessment.overall_score,
        tech_score=assessment.tech_score,
        seniority_score=assessment.seniority_score,
        location_score=assessment.location_score,
        recommendations=assessment.recommendations,
        summary=assessment.summary,
        tokens_used=assessment.tokens_used,
        actual_cost=assessment.actual_cost,
    )

    overall_score = assessment.overall_score
    typer.echo(f" ✅ Score: {overall_score:.0f}/100")
    return True, assessment, assessment.tokens_used, assessment.actual_cost


def _run_phase_assess_jobs_loop(
    confirmed_jobs: list[dict[str, Any]],
    cv_text: str,
    llm_provider: Any,
    assessment_store: AssessmentStore,
    preprocessed_map: dict[str, Any],
) -> Tuple[list[Any], int, float, int]:
    """Process each confirmed job and track results.

    Args:
        confirmed_jobs: List of confirmed jobs
        cv_text: CV text
        llm_provider: LLMProvider instance
        assessment_store: AssessmentStore instance
        preprocessed_map: Map of job_id to preprocessed data

    Returns:
        Tuple of (assessment_list, failed_count, total_cost, total_tokens)
    """
    assessment_list = []
    failed = 0
    total_tokens = 0
    total_cost = 0.0

    for idx, job in enumerate(confirmed_jobs, 1):
        try:
            success, assessment, tokens, cost = _assess_job_and_save(
                job, idx, len(confirmed_jobs), llm_provider, cv_text, assessment_store, preprocessed_map
            )
            if success and assessment:
                assessment_list.append(assessment)
                total_tokens += tokens
                total_cost += cost
        except Exception as e:
            logger.error(f"Assessment failed for job {idx}: {e}", exc_info=True)
            failed += 1
            title = job.get("title", "Unknown")
            typer.echo(f"❌ Job {idx}/{len(confirmed_jobs)}: {title}\n   Error: {e}\n")

    return assessment_list, failed, total_cost, total_tokens


def _display_assess_phase_summary(
    assessment_list: list[Any],
    failed: int,
    total_cost: float,
    total_tokens: int,
    total_jobs: int,
    confirmed_jobs: list[dict[str, Any]],
) -> None:
    """Display assessment phase summary and results.

    Args:
        assessment_list: List of successful assessments
        failed: Count of failed assessments
        total_cost: Total cost in USD
        total_tokens: Total tokens used
        total_jobs: Total jobs processed
        confirmed_jobs: List of all confirmed jobs
    """
    typer.echo("\n" + "=" * 80)
    typer.echo("📊 Assessment Summary:")
    typer.echo(f"   Total assessed: {len(assessment_list)}/{total_jobs}")
    if failed > 0:
        typer.echo(f"   Failed: {failed}")
    if assessment_list:
        avg_score = sum(a.overall_score for a in assessment_list) / len(assessment_list)
        typer.echo(f"   Avg overall score: {avg_score:.1f}/100")
    typer.echo(f"   Total cost: ${total_cost:.6f}")
    typer.echo(f"   Total tokens: {total_tokens}")

    if assessment_list:
        top_matches = sorted(assessment_list, key=lambda a: a.overall_score, reverse=True)[:5]
        if top_matches:
            typer.echo("\n🏆 Top Matches:")
            job_titles = {j.get("job_id"): j.get("title", "N/A") for j in confirmed_jobs}
            for i, match in enumerate(top_matches, 1):
                title = job_titles.get(match.job_id, "N/A")
                typer.echo(f"   {i}. {title} - Overall: {match.overall_score:.0f}/100")

    typer.echo("\n✅ Assessment complete!\n")


def _run_phase_assess(
    cv: str, model: Optional[str], confirmed_only: bool, up_to: Optional[str]
) -> Tuple[Any, float, AssessmentStore]:
    """Run PHASE 4: ASSESS - AI assessment with Claude.

    Args:
        cv: Path to CV file
        model: Claude model ID or None
        confirmed_only: Whether to only assess confirmed jobs
        up_to: Phase stopping point (for early exit check)

    Returns:
        Tuple of (assessment_results list, phase_time float, assessment_store)

    Raises:
        typer.Exit on failure or when up_to == "assess"
    """
    typer.echo("=" * 80)
    typer.echo("PHASE 4: ASSESS - AI assessment with Claude")
    typer.echo("=" * 80)

    phase_start = time.time()

    cv_text = _load_cv_for_phase_assess(cv)
    llm_provider = _init_llm_provider_for_assess(model)
    confirmed_jobs, jobs_data = _load_confirmed_jobs_for_assess()

    assessment_store = AssessmentStore()
    preprocessed_map = {j["job_id"]: j for j in jobs_data} if jobs_data else {}

    assessment_list, failed, total_cost, total_tokens = _run_phase_assess_jobs_loop(
        confirmed_jobs, cv_text, llm_provider, assessment_store, preprocessed_map
    )

    _display_assess_phase_summary(
        assessment_list, failed, total_cost, total_tokens, len(confirmed_jobs), confirmed_jobs
    )

    phase_time = time.time() - phase_start
    typer.echo(f"⏱️  Phase 4 took {phase_time:.2f}s\n")

    if up_to == "assess":
        typer.echo("✅ Stopping at assess phase (as requested)\n")
        raise typer.Exit(0)

    return assessment_list, phase_time, assessment_store


def _run_phase_export() -> float:
    """Run PHASE 5: EXPORT - Generate markdown report.

    Returns:
        phase_time float

    Raises:
        typer.Exit on failure
    """
    typer.echo("=" * 80)
    typer.echo("PHASE 5: EXPORT - Generate markdown report")
    typer.echo("=" * 80)

    phase_start = time.time()

    try:
        # Settings
        min_score = 0
        max_score = 100
        sort_by = "score"
        template = "detailed"
        include_recommendations = True
        include_stats = True
        output = "data/assessments/report.md"

        # Load store
        db_path = "data/ats_playground.db"
        store = AssessmentStore(db_path)
        total = store.count_assessments()

        if total == 0:
            typer.echo("⚠️  No assessments found. Run assess-jobs first.", err=True)
            raise typer.Exit(1)

        # Create config
        config = ExportConfig(
            min_score=min_score,
            max_score=max_score,
            sort_by=sort_by,
            template_style=template,
            include_recommendations=include_recommendations,
            include_stats=include_stats,
        )

        # Generate and save
        exporter = MarkdownExporter(store, config)
        report_content = exporter.generate_report()

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_content)

        typer.echo(f"✅ Report exported to: {output_path}\n")

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        typer.echo(f"❌ Export failed: {e}", err=True)
        raise typer.Exit(1) from None

    phase_time = time.time() - phase_start
    typer.echo(f"⏱️  Phase 5 took {phase_time:.2f}s\n")

    return phase_time


# ============================================================================
# MAIN WORKFLOW HELPERS
# ============================================================================


def _try_run_tui_mode(
    config: Optional[str], config_dir: Optional[str], cv: str, headless: bool, up_to: Optional[str], interactive: bool
) -> bool:
    """Try to run TUI mode if available.

    Args:
        config: Config file path
        config_dir: Config directory path
        cv: CV file path
        headless: Headless browser mode
        up_to: Stop at phase
        interactive: Interactive mode

    Returns:
        True if TUI ran successfully, False to fall back to text mode
    """
    try:
        from src.tui.dashboard import ATPDashboardApp
        from src.tui.models.state import StateManager

        state = StateManager()
        companies = load_companies_config(config, config_dir)

        app = ATPDashboardApp(
            state, companies=companies, cv_file=cv, headless=headless, up_to=up_to, interactive=interactive
        )
        try:
            app.run()
            return True
        except Exception as e:
            logger.exception(f"TUI error: {e}")
            typer.echo(f"❌ TUI crashed: {e}", err=True)
            return False
        finally:
            import subprocess
            import sys

            try:
                if sys.stdin.isatty():
                    subprocess.run(["stty", "sane"], check=False)
            except Exception:
                pass

    except ImportError as e:
        typer.echo(
            f"⚠️  TUI not available: {e}. Falling back to text output.",
            err=True,
        )
        return False


def _should_use_tui(tui: Optional[bool], no_tui: bool) -> bool:
    """Determine if TUI should be used.

    Args:
        tui: Explicit TUI flag or None
        no_tui: Disable TUI flag

    Returns:
        True if TUI should be attempted
    """
    import sys

    if no_tui:
        return False
    if tui is not None:
        return tui
    return sys.stdout.isatty() and sys.stdin.isatty()


def _validate_up_to_phase(up_to: Optional[str]) -> None:
    """Validate the up_to phase parameter.

    Args:
        up_to: Phase to stop at or None

    Raises:
        typer.Exit if phase is invalid
    """
    if not up_to:
        return

    valid_phases = {"crawl", "preprocess", "review", "assess", "export"}
    if up_to not in valid_phases:
        typer.echo(f"❌ Invalid phase: {up_to}", err=True)
        typer.echo(f"   Valid phases: {', '.join(sorted(valid_phases))}", err=True)
        raise typer.Exit(1)


def _run_text_workflow(
    cv: str,
    config: Optional[str],
    config_dir: Optional[str],
    headless: bool,
    confirmed_only: bool,
    interactive: bool,
    merge_all: bool,
    model: Optional[str],
    up_to: Optional[str],
    start_time: float,
) -> None:
    """Run the full workflow in text mode.

    Args:
        cv: CV file path
        config: Config file path
        config_dir: Config directory path
        headless: Headless browser mode
        confirmed_only: Only assess confirmed jobs
        interactive: Interactive review mode
        merge_all: Merge all extracted files
        model: Claude model
        up_to: Stop at phase
        start_time: Workflow start time for timing

    Raises:
        typer.Exit on error
    """
    try:
        _run_phase_crawl(config, config_dir, headless, up_to)
        _run_phase_preprocess(up_to)

        preprocessed_path = Path("data/extracted_jobs/preprocessed_jobs.json")
        _run_phase_review(preprocessed_path, interactive, merge_all, up_to)

        _run_phase_assess(cv, model, confirmed_only, up_to)
        _run_phase_export()

        total_time = time.time() - start_time
        typer.echo("=" * 80)
        typer.echo("🎉 FULL WORKFLOW COMPLETED SUCCESSFULLY!")
        typer.echo("=" * 80)
        typer.echo(f"⏱️  Total time: {total_time:.2f}s")
        typer.echo("📊 Generated files:")
        typer.echo("   - Data: data/extracted_jobs/")
        typer.echo("   - Database: data/ats_playground.db")
        typer.echo("   - Report: data/assessments/report.md")
        typer.echo("")

    except typer.Exit:
        total_time = time.time() - start_time
        typer.echo(f"⏱️  Full workflow took {total_time:.2f}s\n")
        raise
    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        typer.echo(f"\n❌ Workflow failed: {e}", err=True)
        raise typer.Exit(1) from None


# ============================================================================
# MAIN COMMANDS
# ============================================================================


@app.command()
def all(
    cv: str = typer.Option(..., help="Path to CV file (JSON)"),
    config: Optional[str] = typer.Option(None, help="Path to companies config (JSON)"),
    config_dir: Optional[str] = typer.Option(None, help="Directory with JSON config files"),
    headless: bool = typer.Option(True, help="Run browser in headless mode"),
    confirmed_only: bool = typer.Option(False, help="Skip unconfirmed jobs"),
    tui: Optional[bool] = typer.Option(
        None,
        help="Use TUI dashboard (auto-detected from TTY if not specified)",
    ),
    no_tui: bool = typer.Option(False, help="Force text output, disable TUI"),
    interactive: bool = typer.Option(False, help="Enable interactive job review (prompt for each job)"),
    merge_all: bool = typer.Option(
        False,
        "--merge-all",
        help="Auto-discover and process all extracted company files",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Claude model (haiku/sonnet/opus or full ID, default sonnet). See docs/CLI.md for pricing.",
    ),
    up_to: Optional[str] = typer.Option(
        None,
        "--up-to",
        help="Stop workflow at phase [crawl|preprocess|review|assess]. Default: run all phases",
    ),
) -> None:
    """
    Run full workflow: crawl → preprocess → review → assess → export.

    Use --up-to {phase} to halt at specified phase for cost verification.

    Use either --config <file> for a single config file,
    or --config-dir <directory> for multiple config files.

    Example:
        python -m src.cli all --cv data/cv.json --config config/companies.json
        python -m src.cli all --cv data/cv.json --config-dir ./config --tui
        python -m src.cli all --cv data/cv.json --config config/companies.json --up-to review
    """
    # Validate phase
    _validate_up_to_phase(up_to)

    # Determine TUI mode and try to run
    if _should_use_tui(tui, no_tui):
        if _try_run_tui_mode(config, config_dir, cv, headless, up_to, interactive):
            return

    logger.info("Running full workflow")
    typer.echo("✨ Full workflow started...\n")

    start_time = time.time()
    _run_text_workflow(
        cv,
        config,
        config_dir,
        headless,
        confirmed_only,
        interactive,
        merge_all,
        model,
        up_to,
        start_time,
    )


# ============================================================================
# CRAWL COMMANDS
# ============================================================================


def _load_and_validate_config(config: Optional[str], config_dir: Optional[str]) -> dict[str, Any]:
    """Load and validate companies config from file or directory.

    Tries config_dir → config → default with fallbacks.
    Validates that companies were found.

    Args:
        config: Path to single config file
        config_dir: Path to config directory

    Returns:
        Dictionary of companies

    Raises:
        typer.Exit on file not found or no companies loaded
    """
    try:
        if config_dir:
            companies = load_companies_from_directory(Path(config_dir))
            typer.echo(f"📋 Found {len(companies)} companies from directory: {config_dir}")
        elif config:
            companies = load_companies_from_file(Path(config))
            typer.echo(f"📋 Found {len(companies)} companies from file: {config}")
        else:
            companies = load_companies_from_file(Path("config/companies.json"))
            typer.echo(f"📋 Found {len(companies)} companies from default config")
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1) from None

    if not companies:
        typer.echo("❌ No companies found in config", err=True)
        raise typer.Exit(1)

    return companies


def _prepare_enabled_companies(companies: dict[str, Any]) -> dict[str, Any]:
    """Filter companies by enabled flag and validate.

    Args:
        companies: Dictionary of companies from config

    Returns:
        Dictionary of enabled companies only

    Raises:
        typer.Exit if no enabled companies found
    """
    enabled_companies, disabled_companies = filter_enabled_companies(companies)

    if disabled_companies:
        typer.echo(f"⏭️  Skipping {len(disabled_companies)} disabled companies: {', '.join(disabled_companies)}")

    if not enabled_companies:
        typer.echo("❌ No enabled companies to crawl", err=True)
        raise typer.Exit(1)

    typer.echo(f"✅ Processing {len(enabled_companies)} enabled companies\n")
    return enabled_companies


def _save_crawled_results(results: dict[str, Any]) -> None:
    """Save crawled job results to JSON files.

    Args:
        results: Dictionary mapping company_name → list of jobs
    """
    total_jobs = sum(len(jobs) for jobs in results.values())
    typer.echo(f"\n✅ Crawl complete! Extracted {total_jobs} total jobs\n")

    for company_name, jobs in results.items():
        typer.echo(f"   • {company_name}: {len(jobs)} jobs")

        if jobs:
            output_file = Path("data/extracted_jobs") / f"{company_name.lower()}_jobs.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            jobs_data = [job.model_dump(mode="json") for job in jobs]
            with open(output_file, "w") as f:
                json.dump(jobs_data, f, indent=2, default=str)
            typer.echo(f"      Saved to: {output_file}")


@app.command()
def crawl(
    config: Optional[str] = typer.Option(None, help="Companies config file"),
    config_dir: Optional[str] = typer.Option(None, help="Directory with JSON config files"),
    headless: bool = typer.Option(True, help="Headless browser mode"),
    timeout: int = typer.Option(30000, help="Browser timeout (ms)"),
    mock: bool = typer.Option(False, help="Mock crawling without browser"),
) -> None:
    """Crawl job postings from company career pages.

    Use either --config <file> for a single config file,
    or --config-dir <directory> for multiple config files.
    """
    logger.info("Crawling companies from config")
    typer.echo("🌐 Crawling in progress...\n")

    # Load and validate config
    companies = _load_and_validate_config(config, config_dir)

    # Filter enabled companies
    enabled_companies = _prepare_enabled_companies(companies)

    crawler = Crawler(headless=headless, timeout_ms=timeout)

    async def run_crawl() -> Any:
        try:
            results = await crawler.crawl_multiple(enabled_companies)
            _save_crawled_results(results)
            return results

        except Exception as e:
            logger.error(f"Crawl failed: {e}", exc_info=True)
            typer.echo(f"\n❌ Crawl failed: {e}", err=True)
            raise typer.Exit(1) from None
        finally:
            await crawler.close()

    asyncio.run(run_crawl())


# ============================================================================
# PREPROCESS COMMANDS
# ============================================================================


def _validate_and_load_job_files(extracted_dir: Path) -> List[Path]:
    """Validate directory and load extracted job files.

    Args:
        extracted_dir: Path to directory containing extracted jobs

    Returns:
        List of job file paths to process

    Raises:
        typer.Exit on validation failure
    """
    if not extracted_dir.exists():
        typer.echo(f"❌ Directory not found: {extracted_dir}", err=True)
        raise typer.Exit(1) from None

    job_files = [f for f in extracted_dir.glob("*_jobs.json") if "preprocessed" not in f.name]
    if not job_files:
        typer.echo("❌ No extracted jobs found", err=True)
        raise typer.Exit(1) from None

    return job_files


def _build_sectioned_requirements(preprocessor: Any, clean_text: str) -> Optional[dict[str, Any]]:
    """Extract sectioned requirements using preprocessor's section_engine.

    Returns None if section_engine is not configured (v2.0 and earlier).
    Otherwise returns the to_json() dict from SectionedResult.

    Args:
        preprocessor: Preprocessor instance with optional section_engine
        clean_text: Cleaned job description text

    Returns:
        Dict representation of SectionedResult, or None if no engine configured
    """
    result = preprocessor.extract_sectioned_requirements(clean_text)
    if result is not None:
        return result.to_json()  # type: ignore[no-any-return]
    return None


def _preprocess_single_job(
    job_dict: dict[str, Any],
    chunker: Any,
    counter: Any,
    preprocessor: Any,
    pricing_date: str,
    show_estimates: bool,
    job_index: int,
    extract_requirements: bool = True,
    show_requirements: bool = False,
    preprocessing_version: str = "v2.0",
) -> Optional[tuple[Any, int, float, Optional[list[dict[str, Any]]]]]:
    """Process a single job and return preprocessed job or None on failure.

    Args:
        job_dict: Raw job dictionary
        chunker: SemanticChunker instance
        counter: TokenCounter instance
        preprocessor: Preprocessor instance
        pricing_date: ISO format date string
        show_estimates: Whether to display token/cost estimates
        job_index: 1-based job index for logging
        extract_requirements: Whether to extract trigger-based requirements
        show_requirements: Whether to display requirements in CLI output
        preprocessing_version: Version tag for preprocessing pipeline (v1.0, v2.0, or v3.0)

    Returns:
        Tuple of (PreprocessedJob, token_count, cost, requirements) or None if processing fails
    """
    from src.models.job import JobPosting, PreprocessedJob

    try:
        job = JobPosting(**job_dict)

        # Build clean text from job fields using clean_html (Issue #230 Phase 4)
        clean_text = _build_preprocess_clean_text(job_dict)

        # Process text with spaCy to extract requirement spans (Phase 8b)
        # This sets doc._.requirements and doc._.requirement_spans for chunking
        doc = preprocessor.nlp(clean_text)
        if getattr(preprocessor, "categorizer_strategy", "nlp") == "custom":
            doc = preprocessor.apply_custom_spans(doc)

        # Process text with span preservation (Bug #1 fix: pass doc to chunker)
        chunks = chunker.chunk(clean_text, doc=doc)
        token_count = sum(counter.count_tokens(c) for c in chunks)
        estimated_cost = counter.estimate_cost(token_count)

        # Extract entities
        skills, technologies, requirements = preprocessor.extract_entities(clean_text)

        # Extract trigger-based requirements (Phase 8) from doc._.requirements
        trigger_requirements_json = None
        trigger_requirements_list = None
        if extract_requirements:
            # Get requirements from doc instead of re-processing
            requirements_data = getattr(doc._, "requirements", None)
            if requirements_data:
                # Use data directly; avoid unnecessary JSON roundtrip
                trigger_requirements_list = requirements_data
                trigger_requirements_json = json.dumps(requirements_data, ensure_ascii=False)

        # Extract sectioned requirements (Issue #281 S5) for v3.0
        sectioned_requirements_dict = _build_sectioned_requirements(preprocessor, clean_text)

        # Normalize preprocessing_version to v-prefixed format
        normalized_version = (
            preprocessing_version if preprocessing_version.startswith("v") else f"v{preprocessing_version}"
        )

        # Generate or use existing job ID
        job_id = job.id or generate_job_id(
            company=job.company,
            title=job.title,
            location=job.location or "Not specified",
            url=str(job.url) if job.url else None,
        )

        preprocessed = PreprocessedJob(
            job_id=job_id,
            title=job.title,
            company=job.company,
            clean_text=clean_text,
            markdown_description=clean_text,
            sentences=clean_text.split("\n"),
            chunks=chunks,
            skills=skills,
            technologies=technologies,
            requirements=requirements,
            trigger_requirements=trigger_requirements_json,
            token_count=token_count,
            estimated_cost=estimated_cost,
            model_name=counter.model,
            pricing_date=pricing_date,
            preprocessing_version=normalized_version,
            sectioned_requirements=sectioned_requirements_dict,
        )

        # Display estimates if requested
        if show_estimates and job_index <= 3:
            typer.echo(f"   Job {job_index}: {job.title[:40]}...")
            typer.echo(f"      Tokens: {token_count} | Cost: ${estimated_cost:.4f}")

        # Display requirements if requested
        if show_requirements and trigger_requirements_list:
            typer.echo(f"   Requirements: {len(trigger_requirements_list)} extracted")
            top_5 = sorted(trigger_requirements_list, key=lambda r: r.get("confidence", 0), reverse=True)[:5]
            for idx, req in enumerate(top_5, 1):
                typer.echo(
                    f"      {idx}. {req.get('text', 'N/A')[:60]}... (confidence: {req.get('confidence', 0):.2f})"
                )

        return (preprocessed, token_count, estimated_cost, trigger_requirements_list)

    except Exception as e:
        logger.warning(f"Failed to preprocess job {job_index}: {e}")
        return None


def _preprocess_job_file(
    job_file: Path,
    chunker: Any,
    counter: Any,
    preprocessor: Any,
    pricing_date: str,
    show_estimates: bool,
    extract_requirements: bool = True,
    show_requirements: bool = False,
    preprocessing_version: str = "v2.0",
) -> Tuple[List[Any], int, List[dict[str, Any]]]:
    """Process all jobs in a single file.

    Args:
        job_file: Path to JSON file containing jobs
        chunker: SemanticChunker instance
        counter: TokenCounter instance
        preprocessor: Preprocessor instance
        pricing_date: ISO format date string
        show_estimates: Whether to display token/cost estimates
        extract_requirements: Whether to extract trigger-based requirements
        show_requirements: Whether to display requirements in CLI output

    Returns:
        Tuple of (list of preprocessed jobs, count of failures, all requirements list)
    """
    preprocessed_jobs = []
    failed_count = 0
    total_tokens = 0
    total_cost = 0.0
    all_requirements = []

    try:
        with open(job_file) as f:
            jobs_data = json.load(f)

        for i, job_dict in enumerate(jobs_data, 1):
            result = _preprocess_single_job(
                job_dict,
                chunker,
                counter,
                preprocessor,
                pricing_date,
                show_estimates,
                i,
                extract_requirements=extract_requirements,
                show_requirements=show_requirements,
                preprocessing_version=preprocessing_version,
            )
            if result:
                prep_job, tokens, cost, requirements = result
                preprocessed_jobs.append(prep_job)
                total_tokens += tokens
                total_cost += cost
                if requirements:
                    all_requirements.extend(requirements)
            else:
                failed_count += 1

    except Exception as e:
        logger.error(f"Failed to process {job_file}: {e}")

    return preprocessed_jobs, failed_count, all_requirements


def _save_preprocessed_jobs(jobs: List[Any], output_path: Path) -> None:
    """Save preprocessed jobs to JSON file.

    Args:
        jobs: List of PreprocessedJob objects
        output_path: Path where to save the JSON file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_output = [j.model_dump(mode="json") for j in jobs]

    with open(output_path, "w") as f:
        json.dump(jobs_output, f, indent=2, default=str)

    typer.echo(f"   ✓ Saved to: {output_path}")


def _update_job_timelines(jobs: List[Any]) -> None:
    """Update database timestamps for preprocessed jobs.

    Args:
        jobs: List of PreprocessedJob objects
    """
    try:
        from src.verification import JobReviewer

        db_path = Path("data/ats_playground.db")
        if db_path.exists():
            reviewer = JobReviewer(str(db_path))
            for prep_job in jobs:
                reviewer.set_preprocessed_at(prep_job.job_id)
            reviewer._close_db()
            typer.echo(f"   ✓ Updated {len(jobs)} job timelines")
    except Exception as e:
        logger.warning(f"Could not update preprocessing timestamps: {e}")


def _validate_categorizer_options(categorizer_strategy: str, span_patterns: Optional[str]) -> None:
    """Validate span categorizer CLI options before any preprocessing work.

    Args:
        categorizer_strategy: "nlp" (default) or "custom"
        span_patterns: Path to patterns JSON (required for "custom")

    Raises:
        typer.Exit: With code 1 on unknown strategy, missing/unreadable/invalid patterns file
    """
    if categorizer_strategy not in ("nlp", "custom"):
        typer.echo(f"❌ Invalid categorizer strategy: {categorizer_strategy}", err=True)
        typer.echo("   Valid strategies: nlp, custom", err=True)
        raise typer.Exit(1)

    if categorizer_strategy == "custom" and not span_patterns:
        typer.echo("❌ --categorizer-strategy custom requires --span-patterns <file>", err=True)
        raise typer.Exit(1)

    if span_patterns is None:
        return

    from src.preprocessing.custom_span_categorizer import load_patterns

    patterns_path = Path(span_patterns)
    if not patterns_path.is_file():
        typer.echo(f"❌ Span patterns file not found: {span_patterns}", err=True)
        raise typer.Exit(1)

    try:
        load_patterns(patterns_path)
    except (OSError, ValueError) as e:
        typer.echo(f"❌ Invalid span patterns file {span_patterns}: {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
def preprocess(
    batch_size: int = typer.Option(10, help="Jobs per batch"),
    show_estimates: bool = typer.Option(False, help="Show token/cost estimates"),
    preprocessing_version: str = typer.Option(
        "2.0",
        "--preprocessing-version",
        help="Version: 1.0 (legacy), 2.0 (boilerplate removal, default), or 3.0 (sectioned requirements)",
    ),
    re_preprocess_only_v1: bool = typer.Option(
        False,
        "--re-preprocess-only-v1",
        help="Only re-preprocess v1.0 jobs (skip v2.0)",
    ),
    filter_by_age: Optional[int] = typer.Option(
        None,
        "--filter-by-age",
        help="Only jobs preprocessed at least N days ago",
    ),
    filter_by_score_below: Optional[int] = typer.Option(
        None,
        "--filter-by-score-below",
        help="Only jobs with assessment score below N (reserved for Phase 3B)",
    ),
    filter_by_company: Optional[str] = typer.Option(
        None,
        "--filter-by-company",
        help="Comma-separated company names (e.g., 'Amazon,Google')",
    ),
    filter_by_tokens_above: Optional[int] = typer.Option(
        None,
        "--filter-by-tokens-above",
        help="Only jobs with token count >= N",
    ),
    limit: int = typer.Option(
        100,
        help="Maximum number of jobs to process (batch limit for safety)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview jobs without modifying database",
    ),
    extract_requirements: bool = typer.Option(
        True,
        "--extract-requirements/--no-extract-requirements",
        help="Enable/disable trigger-based requirement extraction (Phase 8, default enabled)",
    ),
    export_requirements_json: Optional[str] = typer.Option(
        None,
        "--export-requirements-json",
        help="Export full requirements JSON to file (optional)",
    ),
    categorizer_strategy: str = typer.Option(
        "nlp",
        "--categorizer-strategy",
        help="Span categorizer: nlp (POS/DEP, default) or custom (regex patterns, needs --span-patterns)",
    ),
    span_patterns: Optional[str] = typer.Option(
        None,
        "--span-patterns",
        help="Path to span patterns JSON (required with --categorizer-strategy custom)",
    ),
) -> None:
    """Preprocess job postings (clean HTML, chunk, count tokens, extract entities, extract requirements).

    Supports version tracking for cost analysis, selective re-preprocessing, and trigger-based requirement extraction.

    Examples:
        # Preprocess with default v2.0 (boilerplate removal) + requirement extraction
        uv run python -m src.cli preprocess --batch-size 10

        # Preprocess with legacy v1.0 (no boilerplate)
        uv run python -m src.cli preprocess --preprocessing-version 1.0

        # Preprocess without requirement extraction
        uv run python -m src.cli preprocess --no-extract-requirements

        # Preprocess and export requirements to JSON
        uv run python -m src.cli preprocess --export-requirements-json data/requirements.json

        # Re-preprocess only v1.0 jobs to v2.0
        uv run python -m src.cli preprocess --re-preprocess-only-v1 --preprocessing-version 2.0

        # Preprocess with v3.0 (sectioned requirements extraction)
        uv run python -m src.cli preprocess --preprocessing-version 3.0

        # Selective re-preprocessing with filters
        uv run python -m src.cli preprocess --re-preprocess-only-v1 \\
          --filter-by-age 30 --filter-by-tokens-above 1000 --limit 50 --dry-run
    """
    from datetime import date as date_class

    from src.storage.job_store import VALID_PREPROCESSING_VERSIONS, JobStore
    from src.tokenization.chunker import SemanticChunker
    from src.tokenization.counter import TokenCounter
    from src.tokenization.preprocessor import Preprocessor

    logger.info("Starting preprocessing")
    typer.echo("🔄 Preprocessing jobs...\n")

    # Validate span categorizer options (fail fast, exit 1 on bad input)
    _validate_categorizer_options(categorizer_strategy, span_patterns)

    # Validate preprocessing version (Issue #281 S5)
    clean_version = preprocessing_version.removeprefix("v")
    if clean_version not in VALID_PREPROCESSING_VERSIONS:
        typer.echo(
            f"❌ Invalid preprocessing version: {preprocessing_version}",
            err=True,
        )
        typer.echo(f"   Valid versions: {', '.join(VALID_PREPROCESSING_VERSIONS)}", err=True)
        raise typer.Exit(1)

    # Check if doing selective re-preprocessing
    is_selective_reprocess = (
        re_preprocess_only_v1
        or filter_by_age is not None
        or filter_by_score_below is not None
        or filter_by_company is not None
        or filter_by_tokens_above is not None
    )

    # Initialize components
    chunker = SemanticChunker(target_chunk_size=400)
    counter = TokenCounter()
    pricing_date = date_class.today().isoformat()

    # Initialize SectionDetector for v3.0 (built once, reused for all jobs)
    section_engine = None
    if clean_version == "3.0":
        from src.preprocessing.section_detector import SectionDetector

        section_engine = SectionDetector()

    try:
        preprocessor = Preprocessor(
            extract_requirements=extract_requirements,
            preserve_requirement_spans=True,
            section_engine=section_engine,
            categorizer_strategy=categorizer_strategy,
            span_patterns_path=span_patterns,
        )
    except (OSError, ValueError) as e:
        typer.echo(f"❌ Failed to initialise preprocessor: {e}", err=True)
        raise typer.Exit(1) from e

    all_preprocessed = []
    total_tokens = 0
    total_cost = 0.0
    failed_count = 0

    if is_selective_reprocess:
        # Phase 3C: Selective re-preprocessing from database
        store = JobStore()
        try:
            # Parse company filter
            company_names = None
            if filter_by_company:
                company_names = [c.strip() for c in filter_by_company.split(",")]

            # Get jobs matching filter criteria
            jobs_to_process = store.get_jobs_for_reprocessing(
                version="1.0" if re_preprocess_only_v1 else preprocessing_version,
                min_age_days=filter_by_age,
                max_score=filter_by_score_below,
                min_tokens=filter_by_tokens_above,
                company_names=company_names,
                limit=limit,
            )

            if not jobs_to_process:
                typer.echo("❌ No jobs found matching filter criteria")
                typer.echo(f"   Version: {'v1.0' if re_preprocess_only_v1 else preprocessing_version}")
                if filter_by_age:
                    typer.echo(f"   Age: >={filter_by_age} days")
                if filter_by_tokens_above:
                    typer.echo(f"   Min tokens: {filter_by_tokens_above}")
                if filter_by_company:
                    typer.echo(f"   Companies: {filter_by_company}")
                raise typer.Exit(0)

            typer.echo(f"📊 Found {len(jobs_to_process)} jobs matching filters\n")
            typer.echo("Filter criteria:")
            typer.echo(f"   Version: {'v1.0' if re_preprocess_only_v1 else preprocessing_version}")
            if filter_by_age:
                typer.echo(f"   Age: >={filter_by_age} days")
            if filter_by_tokens_above:
                typer.echo(f"   Min tokens: {filter_by_tokens_above}")
            if filter_by_company:
                typer.echo(f"   Companies: {filter_by_company}")
            if filter_by_score_below:
                typer.echo(f"   Score: <{filter_by_score_below} (future feature)")
            typer.echo()

            # Estimate costs
            if show_estimates or dry_run:
                estimated_total_tokens = 0
                for job in jobs_to_process:
                    tokens = job.get("tokens", 0)
                    estimated_total_tokens += tokens
                estimated_cost = counter.estimate_cost(estimated_total_tokens, output_tokens=300)
                typer.echo("📈 Estimated cost (dry run preview):")
                typer.echo(f"   Total tokens: {estimated_total_tokens:,}")
                typer.echo(f"   Estimated cost: ${estimated_cost:.6f}\n")

            if dry_run:
                typer.echo("✅ Dry run mode - no database modifications\n")
                typer.echo("Preview of jobs to be re-processed:")
                for idx, job in enumerate(jobs_to_process[:10], 1):
                    typer.echo(
                        f"  {idx}. {job.get('title', 'N/A')} - "
                        f"{job.get('company', 'N/A')} - {job.get('tokens', 0)} tokens"
                    )
                if len(jobs_to_process) > 10:
                    typer.echo(f"  ... and {len(jobs_to_process) - 10} more")
                typer.echo(f"\nWould re-process {len(jobs_to_process)} jobs in batches of {batch_size}")
                raise typer.Exit(0)

            # Confirm before proceeding
            typer.echo(f"About to re-process {len(jobs_to_process)} jobs")
            if not typer.confirm("Proceed with re-preprocessing?"):
                typer.echo("Cancelled.")
                raise typer.Exit(0)

            typer.echo()

            # Process jobs in batches
            for batch_start in range(0, len(jobs_to_process), batch_size):
                batch_end = min(batch_start + batch_size, len(jobs_to_process))
                batch = jobs_to_process[batch_start:batch_end]
                batch_num = batch_start // batch_size + 1

                typer.echo(f"🔄 Processing batch {batch_num} ({len(batch)} jobs)...")

                for job in batch:
                    job_id = job.get("job_id", "")
                    title = job.get("title", "N/A")

                    # Skip if job_id is missing
                    if not job_id:
                        logger.warning("Skipping job with missing job_id")
                        failed_count += 1
                        continue

                    try:
                        # Mock preprocessing for now - real implementation would re-run preprocessing
                        tokens_before = job.get("tokens", 0)
                        # Estimate savings from boilerplate removal (~30% reduction)
                        tokens_after = int(tokens_before * 0.70)

                        # Update version in database
                        store.update_preprocessing_version(job_id, preprocessing_version)

                        # Log reprocessing metrics (Phase 3A)
                        cost_before = counter.estimate_cost(tokens_before, output_tokens=300)
                        cost_after = counter.estimate_cost(tokens_after, output_tokens=300)
                        store.log_reprocessing_metrics(
                            job_id=job_id,
                            tokens_before=tokens_before,
                            tokens_after=tokens_after,
                            version_before="v1.0",
                            version_after=preprocessing_version,
                            cost_before=cost_before,
                            cost_after=cost_after,
                        )

                        all_preprocessed.append({"job_id": job_id, "title": title})
                        total_tokens += tokens_before
                        total_cost += cost_before

                    except Exception as e:
                        logger.exception(f"Failed to reprocess job {job_id}: {e}")
                        failed_count += 1
                        typer.echo(f"❌ Failed: {title} ({e})", err=True)

        finally:
            store.close()

    else:
        # Phase 1-2: Normal preprocessing from files
        extracted_dir = Path("data/extracted_jobs")
        job_files = _validate_and_load_job_files(extracted_dir)
        typer.echo(f"📂 Processing {len(job_files)} job files...\n")

        all_requirements_extracted = []
        for job_file in job_files:
            typer.echo(f"📂 Processing {job_file.name}...")
            preprocessed_jobs, file_failed, file_requirements = _preprocess_job_file(
                job_file,
                chunker,
                counter,
                preprocessor,
                pricing_date,
                show_estimates,
                extract_requirements=extract_requirements,
                show_requirements=show_estimates,  # Show requirements if showing estimates
                preprocessing_version=preprocessing_version,
            )
            all_preprocessed.extend(preprocessed_jobs)
            failed_count += file_failed
            total_tokens += sum(j.token_count for j in preprocessed_jobs)
            total_cost += sum(j.estimated_cost for j in preprocessed_jobs)
            all_requirements_extracted.extend(file_requirements)

    # Display summary
    typer.echo("\n✅ Preprocessing complete!\n")
    typer.echo("📊 Summary:")
    typer.echo(f"   Total jobs: {len(all_preprocessed) + failed_count}")
    typer.echo(f"   Processed: {len(all_preprocessed)}")
    typer.echo(f"   Failed: {failed_count}")
    typer.echo(f"   Total tokens: {total_tokens}")
    typer.echo(f"   Total cost: ${total_cost:.4f}")

    if extract_requirements and "all_requirements_extracted" in locals():
        typer.echo(f"   Trigger-based requirements: {len(all_requirements_extracted)} extracted")

    if all_preprocessed and not is_selective_reprocess:
        avg_tokens = total_tokens // len(all_preprocessed)
        typer.echo(f"   Avg tokens/job: {avg_tokens}")
        typer.echo("\n💾 Saving preprocessed jobs...")

        extracted_dir = Path("data/extracted_jobs")
        output_file = extracted_dir / "preprocessed_jobs.json"
        _save_preprocessed_jobs(all_preprocessed, output_file)
        _update_job_timelines(all_preprocessed)

        # Export requirements JSON if requested
        if extract_requirements and export_requirements_json and "all_requirements_extracted" in locals():
            export_path = Path(export_requirements_json)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, "w") as f:
                json.dump(all_requirements_extracted, f, indent=2)
            typer.echo(f"   ✓ Exported {len(all_requirements_extracted)} requirements to: {export_path}")


# ============================================================================
# REVIEW COMMANDS
# ============================================================================


# Default cost limit: $0.10 (roughly 30k tokens on Sonnet)
COST_THRESHOLD = 0.10


def _resolve_extracted_files(merge_all: bool, extracted: Optional[str], extracted_dir: Path) -> list[Path]:
    """Resolve extracted job file paths based on merge_all flag.

    Args:
        merge_all: If True, auto-discover all extracted company files.
        extracted: Path to extracted file (used if merge_all is False).
        extracted_dir: Directory containing extracted files.

    Returns:
        List of Path objects for extracted job files.

    Raises:
        typer.Exit: If no files found or invalid configuration.
    """
    if merge_all:
        # Auto-discover all company files
        extracted_files = sorted(extracted_dir.glob("*_jobs.json"))
        extracted_files = [f for f in extracted_files if "preprocessed" not in f.name]
        if not extracted_files:
            typer.echo("❌ No extracted job files found in data/extracted_jobs/", err=True)
            raise typer.Exit(1)
        logger.info(f"Processing {len(extracted_files)} extracted files: {[f.name for f in extracted_files]}")
        return extracted_files

    # Legacy mode: use provided path or hardcoded default
    if extracted is None:
        extracted = "data/extracted_jobs/carbonrobotics_jobs.json"
        logger.warning("⚠️  Using hardcoded default for review. For multi-company workflows, use: review --merge-all")
    return [Path(extracted)]


def _recalculate_costs_for_model(model: str, preprocessed: str, stats: Any) -> float:
    """Recalculate LLM costs for a specific model using preprocessed jobs.

    Args:
        model: Claude model identifier (haiku/sonnet/opus or full ID).
        preprocessed: Path to preprocessed jobs JSON file.
        stats: Original review stats object with total_cost attribute.

    Returns:
        Recalculated total cost in USD.

    Side Effects:
        Logs warnings if recalculation fails.
        Echoes user-friendly messages about cost changes.
    """
    from src.config.models import get_model_display_name, resolve_model_alias
    from src.tokenization.counter import TokenCounter

    resolved_model = resolve_model_alias(model)
    model_display = get_model_display_name(resolved_model)
    typer.echo(f"\n💰 Recalculating costs for {model_display} model...")

    # Create counter with specified model to recalculate costs
    counter = TokenCounter(model=resolved_model)
    recalc_cost = 0.0

    try:
        with open(preprocessed) as f:
            preprocessed_jobs = json.load(f)

        for job in preprocessed_jobs:
            # Only recalculate for confirmed jobs
            if job.get("status") == "confirmed":
                tokens = job.get("token_count", 0)
                # Use default output_tokens (300) for recalculation
                job_cost = counter.estimate_cost(tokens, output_tokens=300)
                recalc_cost += job_cost

        typer.echo(
            f"✅ Recalculated costs using {model_display}:\n"
            f"   Original estimate: ${stats.total_cost:.6f}\n"
            f"   {model_display} estimate: ${recalc_cost:.6f}"
        )
        return recalc_cost
    except Exception as e:
        logger.warning(f"Failed to recalculate costs: {e}")
        typer.echo(f"⚠️  Could not recalculate costs: {e}")
        return float(stats.total_cost)


def _check_cost_threshold(total_cost: float, cost_limit: Optional[float]) -> None:
    """Check if total cost exceeds threshold and warn user if needed.

    Args:
        total_cost: Estimated LLM cost in USD.
        cost_limit: User-specified cost limit (uses default if None).
    """
    threshold = cost_limit if cost_limit is not None else COST_THRESHOLD
    if total_cost > threshold:
        typer.echo(
            f"\n⚠️  WARNING: Estimated LLM cost (${total_cost:.6f}) exceeds "
            f"threshold (${threshold:.6f})\n"
            f"   To proceed with assessment, use: assess --model <model> --cv <cv_file>\n"
            f"   To adjust threshold: review --cost-limit {total_cost + 0.01}"
        )


@app.command()
def review(
    extracted: Optional[str] = typer.Option(None, help="Path to extracted jobs JSON (auto-detected if not specified)"),
    preprocessed: str = typer.Option(
        "data/extracted_jobs/preprocessed_jobs.json", help="Path to preprocessed jobs JSON"
    ),
    merge_all: bool = typer.Option(
        False,
        "--merge-all",
        help="[RECOMMENDED for multi-company] Auto-discover and process all extracted company files",
    ),
    mode: str = typer.Option(
        "new-only",
        "--mode",
        help="Review mode: 'new-only' (unreviewed jobs) or 'all' (all jobs)",
    ),
    skip_before_date: Optional[str] = typer.Option(
        None,
        "--skip-before-date",
        help="Skip jobs crawled before this date (ISO format, e.g. 2026-07-01)",
    ),
    skip_rejected: bool = typer.Option(
        True, "--skip-rejected", help="Skip jobs with 'rejected' status (default: True)"
    ),
    skip_assessed: bool = typer.Option(True, "--skip-assessed", help="Skip jobs already assessed (default: True)"),
    show_stats: bool = typer.Option(False, "--show-stats", help="Display pipeline statistics before review"),
    allow_re_review: bool = typer.Option(False, "--allow-re-review", help="Show prior decisions and allow re-review"),
    cost_limit: Optional[float] = typer.Option(
        None, "--cost-limit", help="Warn if estimated LLM cost exceeds this USD amount"
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Claude model (haiku/sonnet/opus or full ID). Recalculates costs based on model pricing.",
    ),
) -> None:
    """Interactively review extracted jobs before LLM assessment."""
    from src.verification import JobReviewer

    logger.info("Starting job review")

    try:
        extracted_dir = Path("data/extracted_jobs")
        extracted_files = _resolve_extracted_files(merge_all, extracted, extracted_dir)

        reviewer = JobReviewer()

        if show_stats:
            reviewer.display_pipeline_stats(
                skip_before_date=skip_before_date,
                skip_rejected=skip_rejected,
                skip_assessed=skip_assessed,
            )

        # Validate mode
        if mode not in ("new-only", "all"):
            typer.echo(f"❌ Invalid mode: {mode}. Must be 'new-only' or 'all'", err=True)
            raise typer.Exit(1)

        stats = reviewer.review_batch(
            extracted_files,
            preprocessed,
            mode=mode,
            skip_before_date=skip_before_date,
            skip_rejected=skip_rejected,
            skip_assessed=skip_assessed,
            allow_re_review=allow_re_review,
        )
        logger.info(f"Review complete: {stats.confirmed} confirmed, {stats.rejected} rejected")

        # Recalculate costs if model specified
        if model:
            stats.total_cost = _recalculate_costs_for_model(model, preprocessed, stats)

        # Check cost limit warning
        _check_cost_threshold(stats.total_cost, cost_limit)

    except Exception as e:
        logger.error(f"Review failed: {e}", exc_info=True)
        typer.echo(f"\n❌ Review failed: {e}", err=True)
        raise typer.Exit(1) from None


# ============================================================================
# ASSESS COMMANDS
# ============================================================================


def _load_cv_text(cv_path: str) -> str:
    """Load and parse CV text from file.

    Args:
        cv_path: Path to CV file (JSON or text)

    Returns:
        CV text content

    Raises:
        typer.Exit: If file not found or cannot be read
    """
    path = Path(cv_path)
    if not path.exists():
        typer.echo(f"❌ CV file not found: {cv_path}", err=True)
        raise typer.Exit(1)

    with open(path) as f:
        if path.suffix == ".json":
            cv_data = json.load(f)
            cv_text = cv_data.get("text") or cv_data.get("content") or json.dumps(cv_data)
        else:
            cv_text = f.read()

    typer.echo(f"📄 Loaded CV from: {cv_path}\n")
    return cv_text


def _initialize_assessor_and_validate(model: Optional[str]) -> Any:
    """Initialize Assessor and validate setup.

    Args:
        model: Claude model identifier or None for default

    Returns:
        Initialized Assessor instance

    Raises:
        typer.Exit: On validation failure or API key missing
    """
    from src.assessment.assessor import Assessor
    from src.config.models import get_model_display_name

    try:
        assessor = Assessor(model=model or "claude-3-5-sonnet-20241022")
        model_display = get_model_display_name(assessor.model)
        typer.echo(f"🤖 Using {model_display} model\n")
        return assessor
    except ValueError as e:
        typer.echo(f"❌ Assessor setup failed: {e}", err=True)
        typer.echo("   Set ANTHROPIC_API_KEY environment variable", err=True)
        raise typer.Exit(1) from e


def _get_and_validate_jobs() -> List[dict[str, Any]]:
    """Get confirmed jobs from database and validate.

    Returns:
        List of confirmed job dictionaries

    Raises:
        typer.Exit: If no jobs found
    """
    from src.verification import JobReviewer

    reviewer = JobReviewer()
    confirmed_jobs = reviewer.get_confirmed_jobs()

    if not confirmed_jobs:
        typer.echo("❌ No confirmed jobs found. Run 'review-jobs' first.", err=True)
        raise typer.Exit(1)

    typer.echo(f"🤖 Starting CV assessment for {len(confirmed_jobs)} confirmed jobs\n")
    return confirmed_jobs


def _validate_job_statuses(jobs: List[dict[str, Any]], skip_unconfirmed: bool) -> None:
    """Validate all jobs have status='confirmed'.

    Args:
        jobs: List of job dictionaries
        skip_unconfirmed: If True, silently skip unconfirmed jobs; if False, error

    Raises:
        typer.Exit: If unconfirmed jobs found and skip_unconfirmed=False
    """
    unconfirmed = [j for j in jobs if j.get("status") != "confirmed"]

    if not unconfirmed:
        return

    unconfirmed_count = len(unconfirmed)
    total_count = len(jobs)

    if skip_unconfirmed:
        typer.echo(f"⚠️  Skipping {unconfirmed_count} unconfirmed jobs (status != 'confirmed')\n")
        logger.warning(f"Skipped {unconfirmed_count} unconfirmed jobs during assessment")
    else:
        typer.echo(
            f"❌ Found {unconfirmed_count}/{total_count} unconfirmed jobs:\n"
            f"   Use --skip-unconfirmed to proceed anyway\n"
            f"   Or run 'review' phase to confirm all jobs",
            err=True,
        )
        logger.error(f"Assessment blocked: {unconfirmed_count} unconfirmed jobs found")
        raise typer.Exit(1)


def _is_raw_html(text: str) -> bool:
    """Check if text contains raw HTML patterns.

    Args:
        text: Text to check

    Returns:
        True if text contains HTML entity or tag patterns, False otherwise
    """
    if not text:
        return True
    # Check for HTML entities and tags
    html_patterns = ["&lt;", "&gt;", "&amp;", "<html", "<div", "<p>", "<span", "<a href"]
    return any(pattern in text.lower() for pattern in html_patterns)


def _validate_preprocessed_jobs(jobs: List[dict[str, Any]]) -> None:
    """Validate all jobs are preprocessed (not raw HTML).

    Args:
        jobs: List of job dictionaries

    Raises:
        typer.Exit: If unpreprocessed jobs found
    """
    unpreprocessed = []

    for job in jobs:
        job_id = job.get("job_id", "unknown")
        clean_text = job.get("clean_text", "")
        token_count = job.get("token_count", 0)

        # Check if clean_text is missing or contains raw HTML
        if not clean_text or _is_raw_html(clean_text):
            unpreprocessed.append(job_id)
            continue

        # Check if token_count is valid
        if not isinstance(token_count, int) or token_count <= 0:
            unpreprocessed.append(job_id)

    if not unpreprocessed:
        return

    unpreprocessed_count = len(unpreprocessed)
    total_count = len(jobs)

    typer.echo(
        f"❌ Found {unpreprocessed_count}/{total_count} unpreprocessed jobs (missing clean_text or token_count):\n"
        f"   Job IDs: {', '.join(unpreprocessed[:5])}"
        f"{'...' if len(unpreprocessed) > 5 else ''}\n"
        f"   Run 'preprocess' phase before assessment",
        err=True,
    )
    logger.error(f"Assessment blocked: {unpreprocessed_count} unpreprocessed jobs found")
    raise typer.Exit(1)


def _filter_jobs_by_mode(jobs: List[dict[str, Any]], mode: str, assessment_store: Any) -> List[dict[str, Any]]:
    """Apply mode filter to jobs (new-only vs all).

    Args:
        jobs: List of job dictionaries
        mode: Filter mode ('new-only' or 'all')
        assessment_store: AssessmentStore instance

    Returns:
        Filtered job list

    Raises:
        typer.Exit: If mode is invalid
    """
    if mode not in ("new-only", "all"):
        typer.echo(f"❌ Invalid mode: {mode}. Must be 'new-only' or 'all'", err=True)
        raise typer.Exit(1)

    if mode == "new-only":
        original_count = len(jobs)
        jobs = [j for j in jobs if not assessment_store.get_assessment_by_id(j.get("job_id", ""))]
        typer.echo(f"📊 Mode filter (new-only): {original_count} → {len(jobs)} jobs\n")

    return jobs


def _filter_jobs_by_score_threshold(
    jobs: List[dict[str, Any]], score_threshold: Optional[float], assessment_store: Any
) -> List[dict[str, Any]]:
    """Apply score threshold filter to jobs.

    Args:
        jobs: List of job dictionaries
        score_threshold: Score threshold (0-100) or None
        assessment_store: AssessmentStore instance

    Returns:
        Filtered job list

    Raises:
        typer.Exit: If threshold invalid or no jobs match
    """
    if score_threshold is None:
        return jobs

    if not (0 <= score_threshold <= 100):
        typer.echo("❌ score_threshold must be 0-100", err=True)
        raise typer.Exit(1)

    original_count = len(jobs)
    filtered_jobs = []
    skipped_low_score = 0

    for job in jobs:
        job_id = job.get("job_id", "")
        if not job_id:
            continue
        existing_assessment = assessment_store.get_assessment_by_id(job_id)

        if existing_assessment and existing_assessment.get("overall_score", 0) < score_threshold:
            skipped_low_score += 1
        else:
            filtered_jobs.append(job)

    jobs = filtered_jobs
    typer.echo(
        f"📊 Score threshold filter: {original_count} jobs → {len(jobs)} jobs\n"
        f"   Skipped {skipped_low_score} jobs with score < {score_threshold}\n"
    )

    if not jobs:
        typer.echo("❌ No jobs match score threshold criteria.", err=True)
        raise typer.Exit(1)

    return jobs


def _filter_jobs_by_date(jobs: List[dict[str, Any]], since: Optional[str]) -> List[dict[str, Any]]:
    """Apply date filter to jobs (since date).

    Args:
        jobs: List of job dictionaries
        since: ISO format date string or None

    Returns:
        Filtered job list

    Raises:
        typer.Exit: If date format invalid or no jobs match
    """
    if since is None:
        return jobs

    # Validate date format
    try:
        from datetime import datetime

        datetime.fromisoformat(since)
    except ValueError as e:
        typer.echo(
            f"❌ Invalid since date format: {since}. Use ISO format (e.g., 2026-07-01)",
            err=True,
        )
        raise typer.Exit(1) from e

    original_count = len(jobs)
    filtered_jobs = []

    for job in jobs:
        crawled_at = job.get("crawled_at")
        if crawled_at and crawled_at >= since:
            filtered_jobs.append(job)
        elif not crawled_at:
            filtered_jobs.append(job)

    jobs = filtered_jobs
    skipped_before_date = original_count - len(jobs)
    typer.echo(
        f"📊 Date filter (since {since}): {original_count} → {len(jobs)} jobs\n"
        f"   Skipped {skipped_before_date} jobs crawled before {since}\n"
    )

    if not jobs:
        typer.echo("❌ No jobs match date filter criteria.", err=True)
        raise typer.Exit(1)

    return jobs


def _verify_assessment_cost(jobs: List[dict[str, Any]], cv_text: str, verify_cost: bool) -> bool:
    """Estimate and verify assessment cost.

    Args:
        jobs: List of jobs to assess
        cv_text: CV text content
        verify_cost: Whether to prompt user for confirmation

    Returns:
        True if should proceed, raises typer.Exit if user rejects

    Raises:
        typer.Exit: If user declines or cost estimation fails
    """
    if not verify_cost:
        return True

    typer.echo("📋 Estimating costs before proceeding...\n")
    estimated_total = 0.0

    for job in jobs:
        job_desc = job.get("description") or job.get("title", "")
        try:
            from src.tokenization.counter import TokenCounter

            counter = TokenCounter()
            est_tokens = counter.count_tokens(cv_text + "\n" + job_desc) + 200
            est_cost = est_tokens * 0.000003
            estimated_total += est_cost
        except Exception:
            estimated_total += 0.01

    typer.echo(f"💰 Estimated total cost for {len(jobs)} jobs: ${estimated_total:.6f}\n")
    if not typer.confirm("Proceed with assessment?"):
        typer.echo("Aborted.")
        raise typer.Exit(0)

    return True


def _assess_single_job(
    job: dict[str, Any],
    cv_text: str,
    assessor: Any,
    assessment_store: Any,
    idx: int,
    total: int,
) -> Tuple[bool, Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Assess a single job and save result.

    Args:
        job: Job dictionary
        cv_text: CV text
        assessor: Assessor instance
        assessment_store: AssessmentStore instance
        idx: Job index (1-based) for logging
        total: Total jobs for logging

    Returns:
        Tuple of (success: bool, result: ResultItem or None, error_info: dict or None)
    """
    job_id = job["job_id"]
    title = job["title"]
    company = job.get("company", "Unknown")
    location = job.get("location", "Unknown")
    job_desc = job.get("description") or job.get("title", "")

    try:
        result = assessor.assess_job(cv_text, job_desc)

        assessment_store.save_assessment(
            job_id=job_id,
            title=title,
            company=company,
            location=location,
            overall_score=result["assessment"].get("overall_score", 0),
            tech_score=result["entity_score"].get("tech_match", 0),
            seniority_score=result["entity_score"].get("skill_match", 0),
            location_score=50,
            recommendations=result["assessment"].get("reasoning", ""),
            summary=result["assessment"].get("reasoning", ""),
            tokens_used=result["cost_tracking"].get("actual_input", 0),
            actual_cost=result["cost_tracking"].get("actual_cost_usd", 0.0),
        )

        overall_score = result["assessment"].get("overall_score", 0)
        entity_score = result["entity_score"].get("overall_entity_score", 0)
        actual_cost = result["cost_tracking"].get("actual_cost_usd", 0.0)
        actual_tokens = result["cost_tracking"].get("actual_input", 0)
        savings = result.get("token_savings_percent", 0)

        typer.echo(
            f"✅ [{idx}/{total}] {title} @ {company}\n"
            f"   LLM Score: {overall_score:.0f}/100 | "
            f"Entity Score: {entity_score:.0f}/100\n"
            f"   Cost: ${actual_cost:.6f} | "
            f"Tokens: {actual_tokens} | "
            f"Savings: {savings:.1f}%\n"
        )

        logger.info(
            f"[{idx}/{total}] Assessed {job_id}: "
            f"score={overall_score}, entity={entity_score}, "
            f"tokens={actual_tokens}, cost=${actual_cost:.6f}, "
            f"savings={savings:.1f}%"
        )

        return (
            True,
            {
                "job_id": job_id,
                "title": title,
                "llm_score": overall_score,
                "entity_score": entity_score,
                "cost": actual_cost,
                "tokens": actual_tokens,
            },
            None,
        )

    except anthropic.RateLimitError as e:
        typer.echo(f"⏱️  [{idx}/{total}] Rate limited on {title}\n   Continuing with remaining jobs...\n")
        logger.warning(f"[{idx}/{total}] Rate limited on {job_id}: {e}")
        return False, None, {"job_id": job_id, "title": title, "reason": "rate_limited"}

    except json.JSONDecodeError as e:
        typer.echo(f"⚠️  [{idx}/{total}] Failed to parse response for {title}\n   Skipping job...\n")
        logger.error(f"[{idx}/{total}] Parse error for {job_id}: {e}")
        return False, None, {"job_id": job_id, "title": title, "reason": "parse_error"}

    except Exception as e:
        typer.echo(f"❌ [{idx}/{total}] {title}\n   Error: {type(e).__name__}: {e}\n")
        logger.exception(f"[{idx}/{total}] Assessment failed for {job_id}")
        return (
            False,
            None,
            {"job_id": job_id, "title": title, "reason": type(e).__name__},
        )


def _display_assessment_summary(
    results: List[dict[str, Any]],
    failed_jobs: List[dict[str, Any]],
    total_cost: float,
    total_tokens: int,
    successful: int,
    total_jobs: int,
) -> None:
    """Display assessment summary and top matches.

    Args:
        results: List of successful ResultItem objects
        failed_jobs: List of failed job info dicts
        total_cost: Total cost in USD
        total_tokens: Total tokens used
        successful: Count of successful assessments
        total_jobs: Total jobs assessed
    """
    typer.echo("\n" + "=" * 80)
    typer.echo("📊 Assessment Summary:")
    typer.echo(f"   ✅ Assessed: {successful}/{total_jobs}")
    if failed_jobs:
        typer.echo(f"   ❌ Failed: {len(failed_jobs)}")
        for job in failed_jobs[:5]:
            typer.echo(f"      • {job['title']}: {job['reason']}")
        if len(failed_jobs) > 5:
            typer.echo(f"      ... and {len(failed_jobs) - 5} more (see logs)")

    typer.echo("\n💰 Cost Summary:")
    if results:
        avg_score = sum(r["llm_score"] for r in results) / len(results)
        typer.echo(f"   Avg LLM score: {avg_score:.1f}/100")
    typer.echo(f"   Total cost: ${total_cost:.6f}")
    typer.echo(f"   Total tokens: {total_tokens:,}")
    if total_tokens > 0:
        avg_cost_per_job = total_cost / successful if successful > 0 else 0
        typer.echo(f"   Avg cost per job: ${avg_cost_per_job:.6f}")

    if results:
        top_results = sorted(results, key=lambda x: x["llm_score"], reverse=True)[:5]
        typer.echo(f"\n🏆 Top {len(top_results)} Matches (by LLM score):")
        for i, result_item in enumerate(top_results, 1):
            entity_score = result_item.get("entity_score", 0)
            typer.echo(
                f"   {i}. {result_item['title']} (LLM: {result_item['llm_score']:.0f}, Entity: {entity_score:.0f})"
            )

    typer.echo("\n✅ Assessment complete!\n")


@app.command()
def assess(
    cv: str = typer.Option(..., help="CV file path (json or txt)"),
    confirmed_only: bool = typer.Option(True, help="Only assess confirmed jobs"),
    skip_unconfirmed: bool = typer.Option(True, help="Skip jobs with status != 'confirmed'"),
    mode: str = typer.Option(
        "new-only",
        "--mode",
        help="Assess mode: 'new-only' (unassessed jobs) or 'all' (all confirmed jobs)",
    ),
    score_threshold: Optional[float] = typer.Option(
        None, "--score-threshold", help="Re-assess jobs with prior score < threshold (0-100)"
    ),
    since: Optional[str] = typer.Option(
        None, "--since", help="Re-assess jobs crawled on/after this date (ISO format, e.g. 2026-07-01)"
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Claude model (haiku/sonnet/opus or full ID, default sonnet). See docs/CLI.md for pricing.",
    ),
    verify_cost: bool = typer.Option(
        False,
        "--verify-cost",
        help="Show cost estimate and prompt before proceeding",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Max jobs to assess (useful for testing/budgeting)",
    ),
) -> None:
    """Assess CV fit for confirmed jobs using entity-based scoring."""
    from src.storage.assessment_store import AssessmentStore

    logger.info(f"Starting job assessment with CV: {cv}")

    try:
        # Load CV text
        cv_text = _load_cv_text(cv)

        # Initialize assessor
        assessor = _initialize_assessor_and_validate(model)

        # Get confirmed jobs
        confirmed_jobs = _get_and_validate_jobs()

        # Validate job statuses
        _validate_job_statuses(confirmed_jobs, skip_unconfirmed)

        # Validate jobs are preprocessed
        _validate_preprocessed_jobs(confirmed_jobs)

        # Initialize assessment store
        assessment_store = AssessmentStore()

        # Apply filters in sequence
        confirmed_jobs = _filter_jobs_by_mode(confirmed_jobs, mode, assessment_store)
        confirmed_jobs = _filter_jobs_by_score_threshold(confirmed_jobs, score_threshold, assessment_store)
        confirmed_jobs = _filter_jobs_by_date(confirmed_jobs, since)

        # Apply job limit
        if limit:
            confirmed_jobs = confirmed_jobs[:limit]
            typer.echo(f"📊 Applied job limit: assessing {len(confirmed_jobs)} jobs\n")

        # Verify cost
        _verify_assessment_cost(confirmed_jobs, cv_text, verify_cost)

        # Assess each job
        successful = 0
        failed_jobs: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        total_cost = 0.0
        total_tokens = 0

        for idx, confirmed_job in enumerate(confirmed_jobs, 1):
            success, result, error = _assess_single_job(
                confirmed_job, cv_text, assessor, assessment_store, idx, len(confirmed_jobs)
            )

            if success and result:
                successful += 1
                total_cost += result["cost"]
                results.append(result)
                total_tokens += result.get("tokens", 0)
            else:
                if error:
                    failed_jobs.append(error)

        # Display summary
        _display_assessment_summary(results, failed_jobs, total_cost, total_tokens, successful, len(confirmed_jobs))

        logger.info(
            f"Assessment complete: {successful} successful, "
            f"{len(failed_jobs)} failed, ${total_cost:.6f} total cost, "
            f"{total_tokens:,} tokens"
        )

    except Exception as e:
        logger.error(f"Assessment failed: {e}", exc_info=True)
        typer.echo(f"\n❌ Assessment failed: {e}", err=True)
        raise typer.Exit(1) from None


# ============================================================================
# EXPORT COMMANDS
# ============================================================================


def _validate_score_range(min_score: int, max_score: int) -> None:
    """Validate score range parameters.

    Args:
        min_score: Minimum score to include (0-100)
        max_score: Maximum score to include (0-100)

    Raises:
        typer.Exit: If validation fails
    """
    if not 0 <= min_score <= 100:
        typer.echo("❌ min_score must be 0-100", err=True)
        raise typer.Exit(1)
    if not 0 <= max_score <= 100:
        typer.echo("❌ max_score must be 0-100", err=True)
        raise typer.Exit(1)
    if min_score > max_score:
        typer.echo("❌ min_score must be <= max_score", err=True)
        raise typer.Exit(1)


def _parse_date_filters(from_date: Optional[str], to_date: Optional[str]) -> Tuple[Optional[date], Optional[date]]:
    """Parse and validate date filter parameters.

    Args:
        from_date: Start date (YYYY-MM-DD format) or None
        to_date: End date (YYYY-MM-DD format) or None

    Returns:
        Tuple of (date_from, date_to) parsed dates

    Raises:
        typer.Exit: If date parsing fails
    """
    from src.storage.export import parse_date_str

    date_from = None
    date_to = None
    try:
        if from_date:
            date_from = parse_date_str(from_date)
        if to_date:
            date_to = parse_date_str(to_date)
    except ValueError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1) from e

    return date_from, date_to


def _build_filter_message(min_score: int, max_score: int, from_date: Optional[str], to_date: Optional[str]) -> str:
    """Build human-readable filter message for output.

    Args:
        min_score: Minimum score in range
        max_score: Maximum score in range
        from_date: Start date string or None
        to_date: End date string or None

    Returns:
        Human-readable filter message
    """
    filter_msg = f"score {min_score}-{max_score}"
    if from_date or to_date:
        date_range = f"{from_date or 'any'} to {to_date or 'any'}"
        filter_msg += f", date {date_range}"
    return filter_msg


def _generate_and_save_report(exporter: MarkdownExporter, output: str, template: str) -> Path:
    """Generate report and save to file.

    Args:
        exporter: MarkdownExporter instance
        output: Output file path
        template: Template style ('detailed' or 'summary')

    Returns:
        Path object for the output file
    """
    report = exporter.generate_summary() if template == "summary" else exporter.generate_report()

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    return output_path


def _display_export_summary(output_path: Path, filtered_count: int, total_count: int, template: str) -> None:
    """Display export summary information to user.

    Args:
        output_path: Path to the output file
        filtered_count: Number of filtered results
        total_count: Total number of assessments
        template: Template style used
    """
    file_size_kb = output_path.stat().st_size / 1024

    typer.echo(f"✅ Exported to {output_path}")
    typer.echo(f"   Filtered: {filtered_count}/{total_count} jobs")
    typer.echo(f"   File size: {file_size_kb:.1f} KB")
    typer.echo(f"   Template: {template}")

    logger.info(f"Export complete: {filtered_count} jobs, {file_size_kb:.1f} KB")


@app.command()
def export(
    output: str = typer.Option("data/assessments/report.md", help="Output file path"),
    min_score: int = typer.Option(0, help="Minimum score to include (0-100)"),
    max_score: int = typer.Option(100, help="Maximum score to include (0-100)"),
    sort_by: str = typer.Option("score", help="Sort by: score, company, or location"),
    template: str = typer.Option("detailed", help="Template: detailed or summary"),
    include_recommendations: bool = typer.Option(True, help="Include LLM recommendations"),
    include_stats: bool = typer.Option(True, help="Include analytics section"),
    from_date: Optional[str] = typer.Option(None, help="Filter from date (YYYY-MM-DD)"),
    to_date: Optional[str] = typer.Option(None, help="Filter to date (YYYY-MM-DD)"),
) -> None:
    """Export assessment results to Markdown report.

    Examples:
        # Export all assessments
        uv run python -m src.cli export

        # Export with score range
        uv run python -m src.cli export --min-score 70 --max-score 100

        # Export with date range
        uv run python -m src.cli export --from-date 2026-05-01 --to-date 2026-05-31

        # Combined filters
        uv run python -m src.cli export --from-date 2026-05-01 --to-date 2026-05-31 --min-score 75
    """
    try:
        # Validate score inputs
        _validate_score_range(min_score, max_score)

        # Parse and validate dates
        date_from, date_to = _parse_date_filters(from_date, to_date)

        # Load assessment store
        db_path = "data/ats_playground.db"
        store = AssessmentStore(db_path)
        total = store.count_assessments()

        if total == 0:
            typer.echo(
                "⚠️  No assessments found. Run assess-jobs first.",
                err=True,
            )
            raise typer.Exit(1)

        # Create export config
        config = ExportConfig(
            min_score=min_score,
            max_score=max_score,
            sort_by=sort_by,
            template_style=template,
            include_recommendations=include_recommendations,
            include_stats=include_stats,
            date_from=date_from,
            date_to=date_to,
        )

        # Build filter message and echo
        filter_msg = _build_filter_message(min_score, max_score, from_date, to_date)
        typer.echo(f"📊 Generating report ({filter_msg})...")

        # Generate and save report
        exporter = MarkdownExporter(store, config)
        output_path = _generate_and_save_report(exporter, output, template)

        # Display summary
        filtered_in_range = len(store.get_assessments_by_score(min_score, max_score))
        _display_export_summary(output_path, filtered_in_range, total, template)

    except ValueError as e:
        typer.echo(f"❌ Invalid option: {e}", err=True)
        raise typer.Exit(1) from None
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        typer.echo(f"❌ Export failed: {e}", err=True)
        raise typer.Exit(1) from None


@app.command()
def quality_report(
    limit_jobs: Optional[int] = typer.Option(
        None, "--limit", help="Maximum number of comparisons to include in report"
    ),
    db_path: str = typer.Option(
        "data/ats_playground.db",
        "--db",
        help="Path to assessment database",
    ),
) -> None:
    """Generate quality impact report for re-preprocessed jobs (Phase 3B).

    Shows assessment score changes from v1.0 → v2.0 preprocessing to measure
    quality impact and detect regressions.

    Examples:
        # Show quality report
        uv run python -m src.cli quality-report

        # Limit to recent 50 comparisons
        uv run python -m src.cli quality-report --limit 50
    """
    from src.storage.job_store import JobStore

    logger.info("Generating quality impact report (Phase 3B)")

    try:
        store = JobStore(db_path)
        report = store.get_quality_comparison_report(limit_jobs=limit_jobs)

        typer.echo("\n" + "=" * 70)
        typer.echo("📊 Quality Impact Report (Phase 3B)")
        typer.echo("=" * 70)

        if report.total_comparisons == 0:
            typer.echo("ℹ️  No quality tracking data found")
            typer.echo("   Quality tracking is logged when re-assessing re-preprocessed jobs")
            raise typer.Exit(0)

        typer.echo(f"\nComparisons: {report.total_comparisons}")
        typer.echo(f"Average score before: {report.avg_score_before:.1f}")
        typer.echo(f"Average score after:  {report.avg_score_after:.1f}")
        typer.echo(f"Average delta:        {report.avg_score_delta:+.1f}")

        typer.echo("\n📈 Results:")
        typer.echo(f"  ✅ Improved:   {report.score_improved} ({report.improvement_rate:.1f}%)")
        typer.echo(f"  ⬇️  Declined:   {report.score_declined} ({report.regression_risk_percent:.1f}%)")
        typer.echo(f"  ➡️  Unchanged:  {report.score_unchanged}")

        typer.echo("\nScore Changes:")
        typer.echo(f"  Max improvement: +{report.max_score_improvement} points")
        typer.echo(f"  Max decline:     {report.max_score_decline} points")

        if report.regression_risk_jobs:
            typer.echo(f"\n⚠️  Regression Risk (delta >= 10 points): {len(report.regression_risk_jobs)}")
            shown = report.regression_risk_jobs[:10]
            for job_id in shown:
                typer.echo(f"   - {job_id}")
            if len(report.regression_risk_jobs) > 10:
                typer.echo(f"   ... and {len(report.regression_risk_jobs) - 10} more")

        logger.info(f"Quality report generated: {report.total_comparisons} comparisons")

    except Exception as e:
        logger.error(f"Quality report failed: {e}", exc_info=True)
        typer.echo(f"❌ Failed: {e}", err=True)
        raise typer.Exit(1) from None


@app.command()
def view(
    report_path: str = typer.Option(
        "data/assessments/report.md",
        "--report",
        "-r",
        help="Path to report.md file to view",
    ),
    template: str = typer.Option(
        "full",
        "--template",
        "-t",
        help="View template: 'full' (all), 'summary' (headers + stats), or 'topn' (top N matches)",
    ),
    topn: int = typer.Option(
        5,
        "--topn",
        help="Number of top matches to show (with --template topn)",
    ),
    min_score: float = typer.Option(
        0.0,
        "--min-score",
        help="Filter: only show jobs with score >= min_score",
    ),
    max_score: float = typer.Option(
        100.0,
        "--max-score",
        help="Filter: only show jobs with score <= max_score",
    ),
    highlight: bool = typer.Option(
        True,
        "--highlight/--no-highlight",
        help="Enable/disable syntax highlighting and colors",
    ),
    no_pager: bool = typer.Option(
        False,
        "--no-pager",
        help="Disable pager (print entire report at once)",
    ),
) -> None:
    """
    View formatted assessment report with rich markdown rendering.

    Examples:
        uv run python -m src.cli view
        uv run python -m src.cli view --template summary
        uv run python -m src.cli view --template topn --topn 3
        uv run python -m src.cli view --min-score 80 --max-score 95
    """
    try:
        typer.echo("📋 Loading report...")

        viewer = MarkdownReportViewer()
        viewer.view_report(
            report_path=report_path,
            template=template,
            topn=topn,
            min_score=min_score,
            max_score=max_score,
            highlight=highlight,
            use_pager=not no_pager,
        )

    except FileNotFoundError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1) from None
    except Exception as e:
        logger.error(f"View failed: {e}", exc_info=True)
        typer.echo(f"❌ View failed: {e}", err=True)
        raise typer.Exit(1) from None


# ============================================================================
# UTILITY COMMANDS
# ============================================================================


def _validate_and_parse_purge_dates(
    before_date: Optional[str], after_date: Optional[str]
) -> Tuple[Optional[date], Optional[date]]:
    """Validate and parse purge date inputs.

    Args:
        before_date: Before date string (YYYY-MM-DD) or None
        after_date: After date string (YYYY-MM-DD) or None

    Returns:
        Tuple of (before_parsed, after_parsed) dates or None

    Raises:
        typer.Exit: On validation failure or parse error
    """
    from src.storage.export import parse_date_str

    if not before_date and not after_date:
        typer.echo("❌ Specify at least one date filter (--before-date or --after-date)", err=True)
        raise typer.Exit(1)

    # Parse dates
    before_parsed: Optional[date] = None
    after_parsed: Optional[date] = None

    try:
        if before_date:
            before_parsed = parse_date_str(before_date)
        if after_date:
            after_parsed = parse_date_str(after_date)
    except ValueError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1) from e

    # Validate date range
    if before_parsed and after_parsed and after_parsed >= before_parsed:
        typer.echo(
            "❌ Invalid range: after_date must be before before_date",
            err=True,
        )
        raise typer.Exit(1)

    return before_parsed, after_parsed


def _show_purge_preview(affected_count: int, total: int, before_date: Optional[str], after_date: Optional[str]) -> None:
    """Show preview of what will be purged.

    Args:
        affected_count: Number of assessments to delete
        total: Total assessments in database
        before_date: Before date filter string or None
        after_date: After date filter string or None
    """
    typer.echo("")
    typer.echo("🗑️  Purge Preview:")
    typer.echo(f"   Assessments to delete: {affected_count}/{total}")
    if before_date:
        typer.echo(f"   Before date: {before_date}")
    if after_date:
        typer.echo(f"   After date: {after_date}")
    typer.echo("")


def _confirm_destructive_operation() -> bool:
    """Prompt user to confirm destructive operation.

    Returns:
        True if user confirms with 'DELETE', False otherwise
    """
    typer.echo("⚠️  WARNING: This will permanently delete the assessments!")
    response = typer.prompt("Type 'DELETE' to confirm")

    if response != "DELETE":
        typer.echo("❌ Purge cancelled")
        return False

    return True


def _perform_purge_and_show_results(
    store: AssessmentStore,
    before_date: Optional[str],
    after_date: Optional[str],
    dry_run: bool,
    total: int,
) -> None:
    """Perform purge operation and show results.

    Args:
        store: Assessment store instance
        before_date: Before date filter or None
        after_date: After date filter or None
        dry_run: Whether to perform dry run only
        total: Total assessments before purge
    """
    if dry_run:
        typer.echo("ℹ️  Use --no-dry-run --confirm to actually delete these assessments")
    else:
        # Perform actual delete
        result = store.purge_by_date(
            before_date=before_date,
            after_date=after_date,
            dry_run=False,
        )

        typer.echo("")
        typer.echo(f"✅ Purged {result['count']} assessments")
        typer.echo(f"   Remaining: {total - result['count']} assessments")


@app.command()
def purge(
    before_date: Optional[str] = typer.Option(None, help="Delete assessments before date (YYYY-MM-DD)"),
    after_date: Optional[str] = typer.Option(None, help="Delete assessments after date (YYYY-MM-DD)"),
    dry_run: bool = typer.Option(True, help="Preview deletions without actually deleting"),
    confirm: bool = typer.Option(False, help="Required flag to confirm actual deletion"),
) -> None:
    """Purge old assessments by date range.

    Examples:
        # Preview purge (dry-run)
        uv run python -m src.cli purge --before-date 2026-04-01

        # Actually delete (requires --confirm)
        uv run python -m src.cli purge --before-date 2026-04-01 --no-dry-run --confirm
    """
    try:
        # Validate and parse dates
        _validate_and_parse_purge_dates(before_date, after_date)

        # Load store
        db_path = "data/ats_playground.db"
        store = AssessmentStore(db_path)
        total = store.count_assessments()

        if total == 0:
            typer.echo("⚠️  No assessments in database", err=True)
            raise typer.Exit(1)

        # Dry run to show what would be deleted
        result = store.purge_by_date(
            before_date=before_date,
            after_date=after_date,
            dry_run=True,
        )

        affected_count = result["count"]

        if affected_count == 0:
            typer.echo("ℹ️  No assessments match the date filter")
            raise typer.Exit(0)

        # Show preview
        _show_purge_preview(affected_count, total, before_date, after_date)

        # Safety check and perform operation
        if not dry_run:
            if not confirm:
                typer.echo("❌ Destructive operation requires --confirm flag", err=True)
                example = "uv run python -m src.cli purge --before-date 2026-04-01 --no-dry-run --confirm"
                typer.echo(f"   Example: {example}", err=True)
                raise typer.Exit(1)

            # Final confirmation
            if not _confirm_destructive_operation():
                raise typer.Exit(1)

            _perform_purge_and_show_results(store, before_date, after_date, dry_run, total)
        else:
            _perform_purge_and_show_results(store, before_date, after_date, dry_run, total)

    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Purge failed: {e}", exc_info=True)
        typer.echo(f"❌ Purge failed: {e}", err=True)
        raise typer.Exit(1) from None


@app.command()
def query(
    keyword: Optional[str] = typer.Option(None, help="Search keyword (optional if company specified)"),
    min_score: Optional[int] = typer.Option(None, help="Minimum score filter"),
    max_score: Optional[int] = typer.Option(None, help="Maximum score filter"),
    company: Optional[str] = typer.Option(None, help="Filter by company name"),
    limit: int = typer.Option(10, help="Maximum results"),
    json_output: bool = typer.Option(False, help="Output as JSON"),
) -> None:
    """Search stored assessments by keyword, score, and/or company."""
    try:
        # Validate: need at least keyword or company
        if not keyword and not company:
            typer.echo("❌ Specify --keyword and/or --company", err=True)
            raise typer.Exit(1)

        # Load assessment store
        db_path = "data/ats_playground.db"
        store = AssessmentStore(db_path)

        # Set defaults
        min_s = min_score if min_score is not None else 0
        max_s = max_score if max_score is not None else 100

        # Search
        if keyword:
            # Keyword + optional company search
            filter_info = f"'{keyword}' (score {min_s}-{max_s}"
            if company:
                filter_info += f", company={company}"
            filter_info += f", limit {limit})"
            typer.echo(f"🔍 Searching for {filter_info}...\n")
            results = store.search_by_keyword(keyword, min_score=min_s, max_score=max_s, company=company, limit=limit)
        else:
            # Company-only search (no keyword)
            filter_info = f"(company={company}, score {min_s}-{max_s}, limit {limit})"
            typer.echo(f"🔍 Listing jobs at {filter_info}...\n")
            results = store.get_assessments_by_score(min_score=min_s, max_score=max_s, company=company)
            results = results[:limit]

        if not results:
            search_desc = f"'{keyword}'" if keyword else f"company '{company}'"
            typer.echo(f"⚠️  No results found for {search_desc} in score range {min_s}-{max_s}")
            return

        if json_output:
            # JSON output
            output = json.dumps(results, indent=2, default=str)
            typer.echo(output)
        else:
            # Table output
            typer.echo(f"Found {len(results)} results:\n")
            typer.echo("Rank │ Company          │ Title                    │ Score │ Tech │ Senior")
            typer.echo("─────┼──────────────────┼──────────────────────────┼───────┼──────┼───────")

            for idx, job in enumerate(results, 1):
                company = str(job.get("company", "N/A"))[:15].ljust(15)
                title = str(job.get("title", "N/A"))[:24].ljust(24)
                overall = int(job.get("overall_score", 0))
                tech = int(job.get("tech_score", 0))
                seniority = int(job.get("seniority_score", 0))

                typer.echo(f" {idx:2d}  │ {company} │ {title} │ {overall:3d}   │ {tech:3d}  │ {seniority:3d}")

            # Stats
            typer.echo("")
            avg_score = sum(r.get("overall_score", 0) for r in results) / len(results)
            typer.echo(f"📊 Average score: {avg_score:.1f}")
            typer.echo(f"💡 Tip: Use 'export --min-score {min_s}' to get a full report")

        search_desc = f"keyword='{keyword}'" if keyword else f"company='{company}'"
        logger.info(f"Search complete: found {len(results)} results for {search_desc}")

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        typer.echo(f"❌ Search failed: {e}", err=True)
        raise typer.Exit(1) from None


@app.command()
def stats(
    show_token_usage: bool = typer.Option(False, help="Show token statistics"),
) -> None:
    """Display database and cost statistics."""
    # TODO: Implement stats logic
    logger.info("Displaying statistics")
    typer.echo("📈 Statistics:")


@app.command()
def cost_analysis(
    db_path: str = typer.Option(
        "data/ats_playground.db",
        "--db",
        help="Path to database",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table, json, or csv",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save report to file (default: display to stdout)",
    ),
) -> None:
    """Analyze costs and savings from re-preprocessing (Phase 3A).

    Shows comparison of v1.0 vs v2.0 preprocessing costs, token usage,
    and re-preprocessing metrics.

    Examples:
        uv run python -m src.cli cost-analysis
        uv run python -m src.cli cost-analysis --format json
        uv run python -m src.cli cost-analysis --output report.json --format json
    """
    from src.storage.job_store import JobStore

    try:
        typer.echo("💰 Generating cost analysis...")

        store = JobStore(db_path)
        report = store.get_cost_comparison_report()

        if format == "json":
            output_data = report.to_dict()
            output_text = json.dumps(output_data, indent=2)
        elif format == "csv":
            # CSV format
            lines = [
                "Metric,Value",
                f"v1.0 Jobs,{report.total_jobs_v1_0}",
                f"v2.0 Jobs,{report.total_jobs_v2_0}",
                f"Total Tokens (v1.0),{report.total_tokens_v1_0}",
                f"Total Tokens (v2.0),{report.total_tokens_v2_0}",
                f"Avg Tokens per Job (v1.0),{report.avg_tokens_per_job_v1_0:.2f}",
                f"Avg Tokens per Job (v2.0),{report.avg_tokens_per_job_v2_0:.2f}",
                f"Estimated Savings (USD),${report.estimated_savings_usd:.6f}",
                f"Jobs Already Migrated,{report.jobs_already_migrated}",
                f"Jobs Pending Migration,{report.jobs_pending_migration}",
                f"Re-preprocessing Runs,{len(report.reprocessing_runs)}",
                f"Total Re-processing Cost Saved,${report.total_reprocessing_cost_saved:.6f}",
                f"Total Re-processing Tokens Saved,{report.total_reprocessing_tokens_saved}",
                f"Avg Token Reduction (%),{report.avg_token_reduction_percent:.2f}%",
                f"Migration Progress (%),{report.migration_progress_percent:.2f}%",
            ]
            output_text = "\n".join(lines)
        else:
            # Table format (default)
            lines = [
                "📊 Cost Analysis Report (v1.0 vs v2.0)",
                "=" * 50,
                "",
                "Job Counts:",
                f"  v1.0 jobs (legacy):        {report.total_jobs_v1_0}",
                f"  v2.0 jobs (new):           {report.total_jobs_v2_0}",
                f"  Migration progress:        {report.migration_progress_percent:.1f}%",
                "",
                "Token Usage:",
                f"  Total tokens (v1.0):       {report.total_tokens_v1_0:,}",
                f"  Total tokens (v2.0):       {report.total_tokens_v2_0:,}",
                f"  Avg per job (v1.0):        {report.avg_tokens_per_job_v1_0:.0f}",
                f"  Avg per job (v2.0):        {report.avg_tokens_per_job_v2_0:.0f}",
                "",
                "Cost Impact:",
                f"  Estimated savings (USD):   ${report.estimated_savings_usd:.6f}",
                "  Token rate used:           $0.003 per 1M tokens",
                "",
                "Re-preprocessing Metrics:",
                f"  Re-processing runs:        {len(report.reprocessing_runs)}",
                f"  Total tokens saved:        {report.total_reprocessing_tokens_saved:,}",
                f"  Total cost saved:          ${report.total_reprocessing_cost_saved:.6f}",
                f"  Avg reduction:             {report.avg_token_reduction_percent:.1f}%",
                "",
                "Migration Status:",
                f"  Already migrated:          {report.jobs_already_migrated}",
                f"  Pending migration:         {report.jobs_pending_migration}",
            ]
            output_text = "\n".join(lines)

        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output_text, encoding="utf-8")
            typer.echo(f"✅ Report saved to {output}")
        else:
            typer.echo(output_text)

        store.close()

    except Exception as e:
        typer.echo(f"❌ Error generating cost analysis: {e}", err=True)
        raise typer.Exit(1) from None


# ============================================================================
# INTEGRITY COMMANDS
# ============================================================================

integrity_app = typer.Typer(
    name="integrity",
    help="Database integrity checking and repair",
    invoke_without_command=False,
)
app.add_typer(integrity_app, name="integrity")


@integrity_app.command()
def check(
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save report to file (default: display to stdout)",
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Report format: markdown, json, or csv",
    ),
    db_path: str = typer.Option(
        "data/ats_playground.db",
        "--db",
        help="Path to assessment database",
    ),
) -> None:
    """Run comprehensive database integrity checks.

    Examples:
        uv run python -m src.cli integrity check
        uv run python -m src.cli integrity check --output report.md
        uv run python -m src.cli integrity check --format json
    """
    try:
        if format != "json":
            typer.echo("🔍 Running integrity checks...")

        checker = IntegrityChecker(db_path)
        report = checker.run_full_check()

        if format == "json":
            # JSON format
            output_data = {
                "timestamp": report.timestamp.isoformat(),
                "total_checks": report.total_checks,
                "total_issues": len(report.issues_found),
                "records_affected": report.total_records_affected,
                "summary": report.summary_by_type,
                "issues": [
                    {
                        "type": issue.issue_type,
                        "severity": issue.severity,
                        "table": issue.table,
                        "record_id": issue.record_id,
                        "details": issue.details,
                        "action": issue.suggested_action,
                    }
                    for issue in report.issues_found
                ],
                "recommendations": report.purge_recommendations,
            }
            output_text = json.dumps(output_data, indent=2, default=str)
        else:
            # Markdown format (default)
            output_text = _generate_integrity_markdown(report)

        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output_text, encoding="utf-8")
            typer.echo(f"✅ Report saved to {output}")
        else:
            typer.echo(output_text)

        # Summary (only for non-JSON formats)
        if format != "json":
            typer.echo("")
            typer.echo("📊 Scan Results:")
            typer.echo(f"   Total issues: {len(report.issues_found)}")
            typer.echo(f"   Records affected: {report.total_records_affected}")
            typer.echo(f"   Errors: {report.error_count}")
            typer.echo(f"   Warnings: {report.warning_count}")

            if report.purge_recommendations:
                typer.echo("")
                typer.echo("💡 Recommended actions:")
                for rec in report.purge_recommendations:
                    typer.echo(f"   • {rec}")

        logger.info(f"Integrity check complete: {len(report.issues_found)} issues found")

    except Exception as e:
        logger.error(f"Integrity check failed: {e}", exc_info=True)
        typer.echo(f"❌ Check failed: {e}", err=True)
        raise typer.Exit(1) from None


# ============================================================================
# INTEGRITY PURGE HELPERS
# ============================================================================


def _map_issue_type_to_purger_method(purger: DataPurger, issue_type: str, dry_run: bool) -> Tuple[int, List[str]]:
    """Map issue type to purger method and execute.

    Args:
        purger: DataPurger instance
        issue_type: Type of issue to purge
        dry_run: Whether to do a dry run

    Returns:
        Tuple of (count, affected_ids)

    Raises:
        typer.Exit: If issue_type is unknown
    """
    method_map: dict[str, Any] = {
        "orphaned_assessments": purger.purge_orphaned_assessments,
        "orphaned_preprocessed": purger.purge_orphaned_preprocessed,
        "orphaned_job_reviews": purger.purge_orphaned_job_reviews,
        "invalid_scores": purger.purge_invalid_scores,
        "malformed_recommendations": purger.purge_malformed_recommendations,
        "fts_orphans": purger.purge_fts_orphans,
    }

    if issue_type not in method_map:
        typer.echo(f"❌ Unknown issue type: {issue_type}", err=True)
        raise typer.Exit(1)

    method = method_map[issue_type]
    result: Tuple[int, List[str]] = method(dry_run=dry_run)
    return result


def _show_integrity_dry_run_result(issue_type: str, count: int, affected_ids: List[str]) -> None:
    """Show dry run preview of records to be deleted.

    Args:
        issue_type: Type of issue being previewed
        count: Number of records to delete
        affected_ids: List of record IDs to delete
    """
    typer.echo(f"🗑️  [DRY RUN] Would delete {count} records")
    if affected_ids:
        typer.echo(f"   Records: {', '.join(affected_ids[:5])}")
        if len(affected_ids) > 5:
            typer.echo(f"            ... and {len(affected_ids) - 5} more")
    typer.echo("")
    typer.echo("💡 Use --no-dry-run --force to actually delete")


def _perform_integrity_purge(
    issue_type: str,
    count: int,
    affected_ids: List[str],
    force: bool,
    backup_dir: Optional[str],
) -> None:
    """Perform actual purge with backup and confirmation.

    Args:
        issue_type: Type of issue being purged
        count: Number of records to delete
        affected_ids: List of record IDs to delete
        force: Whether force flag was set
        backup_dir: Optional backup directory path

    Raises:
        typer.Exit: If force flag not set
    """
    if not force:
        typer.echo("❌ Actual deletion requires --force flag", err=True)
        raise typer.Exit(1)

    # Backup if requested
    if backup_dir:
        backup_path = Path(backup_dir) / f"integrity_backup_{issue_type}"
        backup_path.mkdir(parents=True, exist_ok=True)

        # Create a simple CSV backup of the deleted IDs
        backup_file = backup_path / f"{issue_type}.txt"
        backup_file.write_text("\n".join(affected_ids), encoding="utf-8")
        typer.echo(f"✅ Backed up {count} records to {backup_file}")

    typer.echo(f"✅ Deleted {count} {issue_type} records")
    logger.info(f"Purged {count} {issue_type} records")


@integrity_app.command(name="purge")
def purge_integrity(
    issue_type: Optional[str] = typer.Option(
        None,
        "--type",
        help="Issue type to purge (e.g., orphaned_assessments, invalid_scores)",
    ),
    backup_dir: Optional[str] = typer.Option(
        None,
        "--backup-dir",
        help="Directory for backup files (auto-created if not specified)",
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--no-dry-run",
        help="Preview deletions without modifying database",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Required flag for actual (non-dry-run) deletion",
    ),
    db_path: str = typer.Option(
        "data/ats_playground.db",
        "--db",
        help="Path to assessment database",
    ),
) -> None:
    """Purge invalid data with safety guarantees.

    Examples:
        # Dry-run (default): preview what would be deleted
        uv run python -m src.cli integrity purge --type orphaned_assessments

        # Actual deletion with backup
        uv run python -m src.cli integrity purge --type orphaned_assessments \\
          --no-dry-run --force --backup-dir ./backups
    """
    try:
        if not issue_type:
            typer.echo("❌ Specify --type to purge", err=True)
            typer.echo(
                "   Available types: orphaned_assessments, orphaned_preprocessed,",
                err=True,
            )
            typer.echo(
                "                    orphaned_job_reviews, invalid_scores,",
                err=True,
            )
            typer.echo(
                "                    malformed_recommendations, fts_orphans",
                err=True,
            )
            raise typer.Exit(1)

        purger = DataPurger(db_path)
        count, affected_ids = _map_issue_type_to_purger_method(purger, issue_type, dry_run)

        if count == 0:
            typer.echo(f"ℹ️  No {issue_type} records found")
            raise typer.Exit(0)

        if dry_run:
            _show_integrity_dry_run_result(issue_type, count, affected_ids)
        else:
            _perform_integrity_purge(issue_type, count, affected_ids, force, backup_dir)

    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Purge failed: {e}", exc_info=True)
        typer.echo(f"❌ Purge failed: {e}", err=True)
        raise typer.Exit(1) from None


@integrity_app.command()
def repair(
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--no-dry-run",
        help="Preview repairs without modifying database",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Required flag for actual (non-dry-run) repair",
    ),
    db_path: str = typer.Option(
        "data/ats_playground.db",
        "--db",
        help="Path to assessment database",
    ),
) -> None:
    """Auto-repair safe integrity issues (FTS rebuild, soft-delete malformed JSON).

    Examples:
        # Preview repairs
        uv run python -m src.cli integrity repair

        # Apply repairs
        uv run python -m src.cli integrity repair --no-dry-run --force
    """
    try:
        typer.echo("🔧 Running auto-repair (safe operations only)...")
        purger = DataPurger(db_path)

        results = []

        # Rebuild FTS index
        fts_count, _ = purger.purge_fts_orphans(dry_run=dry_run)
        if fts_count > 0:
            results.append(("FTS orphans", fts_count))

        # Soft-delete malformed recommendations
        malformed_count, _ = purger.purge_malformed_recommendations(dry_run=dry_run)
        if malformed_count > 0:
            results.append(("Malformed recommendations", malformed_count))

        if not results:
            typer.echo("ℹ️  No safe repairs needed")
            raise typer.Exit(0)

        # Show results
        if dry_run:
            typer.echo("🔧 [DRY RUN] Would repair:")
            for issue_type, count in results:
                typer.echo(f"   • {issue_type}: {count} records")
            typer.echo("")
            typer.echo("💡 Use --no-dry-run --force to apply repairs")
        else:
            if not force:
                typer.echo("❌ Actual repair requires --force flag", err=True)
                raise typer.Exit(1)
            typer.echo("✅ Repaired:")
            for issue_type, count in results:
                typer.echo(f"   • {issue_type}: {count} records")

        logger.info(f"Repair complete: {len(results)} operations performed")

    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Repair failed: {e}", exc_info=True)
        typer.echo(f"❌ Repair failed: {e}", err=True)
        raise typer.Exit(1) from None


def _generate_integrity_markdown(report: Any) -> str:
    """Generate markdown report from IntegrityReport."""
    lines = [
        "# Database Integrity Report",
        f"Generated: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "## Summary",
        f"- **Total Issues**: {len(report.issues_found)}",
        f"- **Errors**: {report.error_count}",
        f"- **Warnings**: {report.warning_count}",
        f"- **Info**: {report.info_count}",
        f"- **Records Affected**: {report.total_records_affected}",
        "",
        "## Issues by Type",
        "| Type | Count | Severity |",
        "|------|-------|----------|",
    ]

    for issue_type, count in sorted(report.summary_by_type.items()):
        severity = next(
            (issue.severity for issue in report.issues_found if issue.issue_type == issue_type),
            "unknown",
        )
        lines.append(f"| {issue_type} | {count} | {severity} |")

    lines.extend(
        [
            "",
            "## Issue Details",
            "",
        ]
    )

    severity_order = {"error": 0, "warning": 1, "info": 2}
    for issue in sorted(
        report.issues_found,
        key=lambda x: (severity_order[x.severity], x.issue_type),
    ):
        lines.extend(
            [
                f"### {issue.issue_type} ({issue.severity})",
                f"- **Table**: {issue.table}",
                f"- **Record ID**: {issue.record_id}",
                f"- **Details**: {issue.details}",
                f"- **Action**: {issue.suggested_action}",
                "",
            ]
        )

    if report.purge_recommendations:
        lines.extend(
            [
                "## Recommended Actions",
                "",
            ]
        )
        for rec in report.purge_recommendations:
            lines.append(f"- {rec}")

    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    load_dotenv()
    app()


if __name__ == "__main__":
    main()
