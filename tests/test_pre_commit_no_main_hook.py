"""Tests for .claude/hooks/pre-commit-no-main.sh (issue #593).

Each test builds a throwaway git repository under tmp_path and runs the hook
with that repository as cwd. The real checkout is never touched.
"""

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".claude" / "hooks" / "pre-commit-no-main.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Temporary git repo on branch main with one commit."""
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Test User")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "initial")
    return tmp_path


def _run_hook(repo: Path, stdin_text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HOOK)],
        cwd=repo,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _bash_input(command: str) -> str:
    return json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
    )


def test_non_commit_command_on_main_is_allowed(repo: Path) -> None:
    result = _run_hook(repo, _bash_input("ls"))

    assert result.returncode == 0
    assert result.stderr == ""


def test_git_commit_on_main_is_blocked(repo: Path) -> None:
    result = _run_hook(repo, _bash_input("git commit -m x"))

    assert result.returncode == 2
    assert "Direct commits to main are not allowed." in result.stderr


def test_compound_add_and_commit_on_main_is_blocked(repo: Path) -> None:
    result = _run_hook(repo, _bash_input("git add x && git commit -m y"))

    assert result.returncode == 2
    assert "Direct commits to main are not allowed." in result.stderr


def test_git_commit_on_feature_branch_is_allowed(repo: Path) -> None:
    _git(repo, "checkout", "-b", "feat/issue-593-example")

    result = _run_hook(repo, _bash_input("git commit -m x"))

    assert result.returncode == 0
    assert result.stderr == ""


def test_empty_stdin_fails_open(repo: Path) -> None:
    result = _run_hook(repo, "")

    assert result.returncode == 0


def test_malformed_json_fails_open(repo: Path) -> None:
    result = _run_hook(repo, "{not valid json")

    assert result.returncode == 0


def test_commit_word_inside_other_command_is_not_a_commit(repo: Path) -> None:
    result = _run_hook(repo, _bash_input("git commit-tree HEAD"))

    assert result.returncode == 0
