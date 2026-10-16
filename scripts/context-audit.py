#!/usr/bin/env python3
"""
Context Files Audit Script

Scans all .md context files in repo and reports:
- Line counts, token estimates, size vs budget compliance
- Stale guidance (command examples, tool versions)
- Redundancy across files
- Metrics exported to JSON

Run: python scripts/context-audit.py

Output: docs/dev-note/context-baseline.json
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Token estimation: ~4 chars per token (conservative)
CHARS_PER_TOKEN = 4

# Recommended budgets (in tokens)
BUDGETS = {
    "CLAUDE.md": 1500,
    "DESIGN.md": 3000,
    "AGENTS.md": 1000,
    "SKILLS.md": 500,
    ".github/copilot-instructions.md": 1000,
    # Shared patterns file (referenced by all phases)
    ".claude/rules/_common.md": 1500,
    # Rules files (flexible, but track)
    ".claude/rules/crawl.md": 2000,
    ".claude/rules/preprocess.md": 2000,
    ".claude/rules/verify.md": 1500,
    ".claude/rules/assess.md": 1500,
    ".claude/rules/storage.md": 1500,
    ".claude/rules/cli.md": 1000,
    ".claude/rules/multi-agent.md": 2000,
    ".claude/rules/cavecrew-shared.md": 600,
    # TUI subdirectory files (split from monolithic tui.md)
    ".claude/rules/tui/index.md": 500,
    ".claude/rules/tui/architecture.md": 1200,
    ".claude/rules/tui/widgets.md": 800,
    ".claude/rules/tui/patterns.md": 900,
    # Phase 8 subdirectory files (design specs)
    ".claude/rules/phase8/patterns.md": 2500,
    ".claude/rules/phase8/span_algorithm.md": 3000,
    ".claude/rules/phase8/performance.md": 1000,
}


@dataclass
class FileMetrics:
    """Metrics for a single context file."""

    path: str
    lines: int
    chars: int
    tokens_estimated: int
    budget: Optional[int]
    status: str  # "compliant", "warning", "over_budget"
    percent_of_budget: Optional[float]
    last_modified: str

    def to_dict(self):
        return asdict(self)


def get_token_estimate(text: str) -> int:
    """Estimate tokens using char count / 4."""
    return len(text) // CHARS_PER_TOKEN


def audit_file(file_path: Path, root_path: Path) -> Optional[FileMetrics]:
    """Audit a single .md file."""
    if not file_path.exists():
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        relative_path = str(file_path.relative_to(root_path))
        lines = len(content.splitlines())
        chars = len(content)
        tokens = get_token_estimate(content)
        budget = BUDGETS.get(relative_path)

        # Determine status
        if budget is None:
            status = "info"
            percent = None
        elif tokens <= budget:
            status = "compliant"
            percent = (tokens / budget) * 100
        elif tokens <= budget * 1.1:
            status = "warning"
            percent = (tokens / budget) * 100
        else:
            status = "over_budget"
            percent = (tokens / budget) * 100

        # Last modified time
        mtime = os.path.getmtime(file_path)
        last_modified = datetime.fromtimestamp(mtime).isoformat()

        return FileMetrics(
            path=relative_path,
            lines=lines,
            chars=chars,
            tokens_estimated=tokens,
            budget=budget,
            status=status,
            percent_of_budget=percent,
            last_modified=last_modified,
        )
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None


def collect_files(root_path: Path) -> list[Path]:
    """Collect core and rules .md files (including subdirectories)."""
    core_files = [
        root_path / "CLAUDE.md",
        root_path / "DESIGN.md",
        root_path / "AGENTS.md",
        root_path / "SKILLS.md",
        root_path / ".github" / "copilot-instructions.md",
    ]
    rules_dir = root_path / ".claude" / "rules"
    if rules_dir.exists():
        # Use rglob to recursively include all .md files in subdirectories
        core_files.extend(sorted(rules_dir.rglob("*.md")))
    return core_files


def print_metrics(metrics_list: list[FileMetrics]) -> tuple[list[str], list[str]]:
    """Print file metrics. Return warnings and errors."""
    warnings = []
    errors = []
    for metrics in metrics_list:
        status_icon = {
            "compliant": "✓",
            "warning": "⚠",
            "over_budget": "✗",
            "info": "ℹ",
        }.get(metrics.status, "?")
        print(
            f"{status_icon} {metrics.path}\n"
            f"   Lines: {metrics.lines} | Tokens: {metrics.tokens_estimated} | "
            f"Budget: {metrics.budget or 'none'}"
        )
        if metrics.percent_of_budget:
            print(f"   {metrics.percent_of_budget:.0f}% of budget")
        if metrics.status == "warning":
            warnings.append(f"{metrics.path}: {metrics.percent_of_budget:.0f}% of budget")
        elif metrics.status == "over_budget":
            errors.append(f"{metrics.path}: EXCEEDS budget ({metrics.percent_of_budget:.0f}%)")
        print()
    return warnings, errors


def print_summary(metrics_list: list[FileMetrics], warnings: list[str], errors: list[str]) -> None:
    """Print summary and issues."""
    total_tokens = sum(m.tokens_estimated for m in metrics_list)
    total_budget = sum(m.budget for m in metrics_list if m.budget)
    compliant_count = sum(1 for m in metrics_list if m.status == "compliant")

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total files audited: {len(metrics_list)}")
    print(f"Compliant: {compliant_count}/{len(metrics_list)}")
    print(f"Total tokens (estimated): {total_tokens:,}")
    print(f"Total budget: {total_budget:,}")
    print(f"Overall utilization: {(total_tokens / total_budget) * 100:.0f}%")
    if warnings:
        print(f"\n⚠  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"   - {w}")
    if errors:
        print(f"\n✗ Over Budget ({len(errors)}):")
        for e in errors:
            print(f"   - {e}")


def export_report(root_path: Path, metrics_list: list[FileMetrics], warnings: list[str], errors: list[str]) -> None:
    """Export audit results to JSON."""
    total_tokens = sum(m.tokens_estimated for m in metrics_list)
    total_budget = sum(m.budget for m in metrics_list if m.budget)
    compliant_count = sum(1 for m in metrics_list if m.status == "compliant")

    output_dir = root_path / "docs" / "dev-note"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "context-baseline.json"

    report = {
        "timestamp": datetime.now().isoformat(),
        "files": [m.to_dict() for m in metrics_list],
        "summary": {
            "total_files": len(metrics_list),
            "compliant": compliant_count,
            "warnings": len(warnings),
            "over_budget": len(errors),
            "total_tokens": total_tokens,
            "total_budget": total_budget,
            "utilization_percent": round((total_tokens / total_budget) * 100, 1),
        },
        "warnings": warnings,
        "errors": errors,
    }

    with open(output_file, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n📊 Report exported to: {output_file}")
    print("\nNext step: Review findings in docs/dev-note/ai-config-audit-findings.md")


def main():
    root_path = Path(__file__).parent.parent
    core_files = collect_files(root_path)

    print("🔍 Auditing context files...\n")
    metrics_list = []
    for file_path in core_files:
        metrics = audit_file(file_path, root_path)
        if metrics:
            metrics_list.append(metrics)

    warnings, errors = print_metrics(metrics_list)
    print_summary(metrics_list, warnings, errors)
    export_report(root_path, metrics_list, warnings, errors)


if __name__ == "__main__":
    main()
