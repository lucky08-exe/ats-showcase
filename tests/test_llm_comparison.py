"""
Compare LLM model performance for assessment task.

Tests Haiku 4.5 vs Sonnet 5 vs Opus 4.8 on sample jobs.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import pytest

# Configure logging to show in pytest output
logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class LLMComparator:
    """Compare different Claude models on assessment task."""

    # Model configs: (model_id, input_price_per_1m, output_price_per_1m)
    MODELS = {
        "haiku": ("claude-haiku-4-5-20251001", 0.80, 4.0),
        "sonnet": ("claude-sonnet-5", 3.0, 15.0),
        "opus": ("claude-opus-4-8", 15.0, 75.0),
    }

    def __init__(self, api_key: str):
        """Initialize with API key."""
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.results: dict[str, Optional[Dict]] = {}

    def assess_with_model(self, model_id: str, cv_text: str, job_chunks: list) -> Optional[Dict]:
        """Run assessment with specific model.

        Args:
            model_id: Claude model ID
            cv_text: CV text
            job_chunks: List of job description chunks (same format as assess command)
        """
        # Join chunks same way as provider.py does
        job_text = "\n".join(job_chunks)
        prompt = self._build_prompt(cv_text, job_text)

        try:
            response = self.client.messages.create(
                model=model_id,
                max_tokens=1024,
                system="You are an expert recruiter evaluating job fit. "
                "Respond with ONLY a valid JSON object, no markdown, no extra text.",
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = ""
            if response.content and hasattr(response.content[0], "text"):
                response_text = response.content[0].text
            print(f"[DEBUG] {model_id} raw response: {response_text[:200]}...")

            # Save response to data/prompt-flow
            self._save_response(model_id, response_text, response.usage)

            # Parse response
            try:
                # Try to extract JSON if wrapped in markdown
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()

                assessment = json.loads(response_text)
            except (json.JSONDecodeError, IndexError) as e:
                print(f"[ERROR] {model_id} JSON parse failed: {e}")
                print(f"[ERROR] Response text: {response_text[:500]}")
                return None

            # Validate required keys
            required_keys = {"overall_score", "tech_score", "seniority_score", "location_score"}
            if not all(k in assessment for k in required_keys):
                missing = required_keys - set(assessment.keys())
                print(f"[ERROR] {model_id} missing keys: {missing}")
                print(f"[ERROR] Got keys: {set(assessment.keys())}")
                return None

            return {
                "model": model_id,
                "overall_score": float(assessment.get("overall_score", 0)),
                "tech_score": float(assessment.get("tech_score", 0)),
                "seniority_score": float(assessment.get("seniority_score", 0)),
                "location_score": float(assessment.get("location_score", 0)),
                "summary": assessment.get("summary", ""),
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
        except Exception as e:
            print(f"[ERROR] {model_id} exception: {type(e).__name__}: {e}")
            return None

    def compare_models(self, cv_text: str, job_chunks: list) -> Dict:
        """Run assessment on all models, return comparison.

        Args:
            cv_text: CV text
            job_chunks: List of job description chunks from preprocessed_jobs.json
        """
        results: dict[str, Optional[Dict]] = {}

        for model_name, (model_id, _, _) in self.MODELS.items():
            logger.info(f"Testing {model_name} ({model_id})...")
            result = self.assess_with_model(model_id, cv_text, job_chunks)
            if result:
                results[model_name] = result
            else:
                results[model_name] = None

        # Calculate variance from valid results
        valid_scores = [r["overall_score"] for r in results.values() if r is not None and "overall_score" in r]

        if not valid_scores:
            logger.error("No valid results from any model")
            variance = float("inf")
            recommendation = "❌ All models failed"
        else:
            variance = max(valid_scores) - min(valid_scores)
            recommendation = self._get_recommendation(variance)

        return {
            "results": results,
            "variance": variance,
            "recommendation": recommendation,
        }

    def _build_prompt(self, cv_text: str, job_text: str) -> str:
        """Build assessment prompt."""
        return f"""Assess how well this CV matches the job description.

CV:
{cv_text}

Job Description:
{job_text}

Respond with JSON:
{{
  "overall_score": <0-100>,
  "tech_score": <0-100>,
  "seniority_score": <0-100>,
  "location_score": <0-100>,
  "summary": "<brief summary>",
  "recommendations": [<list of strengths/gaps>]
}}"""

    def _get_recommendation(self, variance: int) -> str:
        """Get model recommendation based on variance."""
        if variance <= 5:
            return "✅ Use Haiku (95% cost savings)"
        elif variance <= 10:
            return "⚠️  Use Sonnet (80% cost savings)"
        else:
            return "❌ Keep Opus (best accuracy)"

    def _save_response(self, model_name: str, response_text: str, usage) -> None:
        """Save raw model response to data/prompt-flow directory.

        Args:
            model_name: Model ID (e.g. claude-haiku-4-5-20251001)
            response_text: Raw response text from API
            usage: Response usage object with input_tokens and output_tokens
        """
        from datetime import datetime

        flow_dir = Path("data/prompt-flow")
        flow_dir.mkdir(parents=True, exist_ok=True)

        # Determine simple model name for filename
        if "haiku" in model_name:
            filename = "haiku-response.json"
        elif "sonnet" in model_name:
            filename = "sonnet-response.json"
        elif "opus" in model_name:
            filename = "opus-response.json"
        else:
            filename = f"{model_name.split('-')[1]}-response.json"

        # Build metadata
        data = {
            "timestamp": datetime.now().isoformat(),
            "model_id": model_name,
            "raw_response": response_text,
            "usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            },
        }

        # Save to file
        output_path = flow_dir / filename
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"[DEBUG] Saved {model_name} response to {output_path}")


def load_cv_text() -> str:
    """Load CV from data/cv.json and convert to text."""
    cv_path = Path("data/cv.json")
    if not cv_path.exists():
        raise FileNotFoundError(f"CV file not found: {cv_path}")

    with open(cv_path) as f:
        cv_data = json.load(f)

    # Extract text from CV JSON (jRES format)
    lines = []
    basics = cv_data.get("basics", {})
    lines.append(f"{basics.get('name', 'Unknown')}")
    lines.append(f"{basics.get('label', '')}")
    if basics.get("summary"):
        lines.append(f"\n{basics['summary']}")

    # Add work experience
    for job in cv_data.get("work", []):
        lines.append(f"\n{job.get('name', '')}: {job.get('position', '')}")
        if job.get("summary"):
            lines.append(job["summary"])
        if job.get("technologies"):
            lines.append(f"Tech: {', '.join(job['technologies'])}")

    # Add skills
    if cv_data.get("skills"):
        lines.append("\nSkills:")
        for skill in cv_data["skills"]:
            lines.append(f"- {skill.get('name', '')}: {', '.join(skill.get('keywords', []))}")

    return "\n".join(lines)


def load_first_job_chunks() -> list[str]:
    """Load first job chunks from data/extracted_jobs/preprocessed_jobs.json.

    Returns chunks list (same format used by assess command).
    """
    job_path = Path("data/extracted_jobs/preprocessed_jobs.json")
    if not job_path.exists():
        raise FileNotFoundError(f"Jobs file not found: {job_path}")

    with open(job_path) as f:
        jobs = json.load(f)

    if not jobs or not isinstance(jobs, list):
        raise ValueError("No jobs found in preprocessed_jobs.json")

    job = jobs[0]
    # Use chunks (same as assess command: preprocessed.get("chunks", [clean_text]))
    chunks: list[str] = job.get("chunks", [])

    if not chunks:
        raise ValueError("First job has no chunks")

    return chunks


@pytest.mark.integration
def test_model_comparison(tmp_path):
    """Run model comparison on real CV + job data."""
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    assert api_key is not None  # narrow str | None for mypy when pytest is untyped (pre-commit env)

    # Load real data
    print("Loading CV and job chunks...")
    try:
        cv_text = load_cv_text()
        job_chunks = load_first_job_chunks()
    except FileNotFoundError as e:
        pytest.skip(f"Data files not found: {e}")
        return

    print(f"CV length: {len(cv_text)} chars")
    print(f"Job chunks: {len(job_chunks)} chunks, total {sum(len(c) for c in job_chunks)} chars")

    comparator = LLMComparator(api_key)
    result = comparator.compare_models(cv_text, job_chunks)

    # Save results
    report_path = tmp_path / "model_comparison.json"
    with open(report_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"\n\n{'=' * 80}")
    print("MODEL COMPARISON RESULTS")
    print("=" * 80)

    # Load job info for context
    with open("data/extracted_jobs/preprocessed_jobs.json") as f:
        jobs = json.load(f)
        job = jobs[0]
        print(f"\nJob: {job.get('company', 'Unknown')} (ID: {job.get('job_id', 'N/A')})")
        print(f"Chunks: {len(job_chunks)} | Token count: {job.get('token_count', 'N/A')}")

    # Pricing table
    print("\n" + "-" * 80)
    print("PRICING & COSTS")
    print("-" * 80)
    print("Model            Input Price    Output Price   Cost/10k tokens")
    for name, (_, in_price, out_price) in comparator.MODELS.items():
        cost_per_10k = (10000 / 1_000_000) * in_price
        print(f"{name:15} ${in_price:7.2f}/1M    ${out_price:7.2f}/1M     ${cost_per_10k:.4f}")

    # Results
    print("\n" + "-" * 80)
    print("ASSESSMENT SCORES")
    print("-" * 80)

    for model, scores in result["results"].items():
        if scores is None:
            print(f"\n{model.upper()}: ❌ FAILED")
            continue

        print(f"\n{model.upper()}:")
        print(
            f"  Scores:    Overall={scores['overall_score']:5.1f} | "
            f"Tech={scores['tech_score']:5.1f} | "
            f"Seniority={scores['seniority_score']:5.1f} | "
            f"Location={scores['location_score']:5.1f}"
        )
        print(f"  Tokens:    {scores['input_tokens']:5d} input | {scores['output_tokens']:5d} output")

        # Calculate cost
        in_price = comparator.MODELS[model][1]
        out_price = comparator.MODELS[model][2]
        in_cost = (scores["input_tokens"] / 1_000_000) * in_price
        out_cost = (scores["output_tokens"] / 1_000_000) * out_price
        total_cost = in_cost + out_cost
        print(f"  Cost:      ${in_cost:.6f} (input) + ${out_cost:.6f} (output) = ${total_cost:.6f}")
        print(f"  Summary:   {scores['summary'][:70]}...")

    # Analysis
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)
    print(f"Score Variance: {result['variance']:.1f} points (max - min)")
    print("\nDecision Criteria:")
    print("  ✅ ≤5 points   → Use Haiku (95% cost savings)")
    print("  ⚠️  5-10 points → Use Sonnet (80% cost savings)")
    print("  ❌ >10 points  → Keep Opus (best accuracy)")
    print(f"\n→ RECOMMENDATION: {result['recommendation']}")
    print(f"\nReport saved: {report_path}")
    print("=" * 80)


if __name__ == "__main__":
    import sys

    # Run manually: python -m tests.test_llm_comparison
    pytest.main([__file__, "-v", "-s"])
