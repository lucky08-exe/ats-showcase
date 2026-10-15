"""Tests for .claude/hooks/pre-commit-no-main.sh (issues #593, #597).

Each test builds throwaway git repositories under tmp_path and runs the hook
with a repository as cwd. The real checkout is never touched.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".claude" / "hooks" / "pre-commit-no-main.sh"
BLOCK_MESSAGE = "Direct commits to main are not allowed."


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(path: Path, branch: str) -> Path:
    """Create a temporary git repo at ``path`` on ``branch`` with one commit."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", branch)
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "commit.gpgsign", "false")
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Temporary git repo on branch main with one commit."""
    return _init_repo(tmp_path / "cwd-main", "main")


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
    assert BLOCK_MESSAGE in result.stderr


def test_compound_add_and_commit_on_main_is_blocked(repo: Path) -> None:
    result = _run_hook(repo, _bash_input("git add x && git commit -m y"))

    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


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


def test_grep_for_git_commit_text_on_main_is_allowed(repo: Path) -> None:
    """Regression (#597): `git commit` as an argument is not a commit."""
    result = _run_hook(repo, _bash_input("grep git commit docs/"))

    assert result.returncode == 0
    assert result.stderr == ""


def test_git_commit_after_newline_argument_text_is_not_a_commit(repo: Path) -> None:
    """Newline is not a command boundary, so argument text cannot match."""
    result = _run_hook(repo, _bash_input("grep -e foo \\\n  git commit docs/"))

    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize(
    "command",
    [
        "/usr/bin/git commit -m x",
        "sh -c 'git commit -m x'",
        'bash -lc "git commit -m x"',
        "git --no-pager commit -m x",
        "git --no-pager -C {dir} commit -m x",
    ],
    ids=["abs-path", "sh-c-single-quote", "bash-lc-double-quote", "long-option", "long-option-then-C"],
)
def test_false_negative_forms_are_blocked_on_main(repo: Path, command: str) -> None:
    result = _run_hook(repo, _bash_input(command.format(dir=repo)))

    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


@pytest.mark.parametrize("quote", ['"', "'"], ids=["double", "single"])
@pytest.mark.parametrize("dir_name", ["plain", "with space"])
@pytest.mark.parametrize(
    ("target_branch", "expected_code"),
    [("main", 2), ("feat/issue-597-example", 0)],
    ids=["target-main", "target-feature"],
)
def test_quoted_C_dir_selects_branch_of_that_directory(
    tmp_path: Path,
    quote: str,
    dir_name: str,
    target_branch: str,
    expected_code: int,
) -> None:
    """Quoted -C dirs are unquoted and checked, with or without spaces.

    The hook's cwd is on the opposite branch, so only honouring -C gives the
    expected result.
    """
    cwd_branch = "feat/issue-597-cwd" if target_branch == "main" else "main"
    cwd_repo = _init_repo(tmp_path / "cwd", cwd_branch)
    target = _init_repo(tmp_path / dir_name, target_branch)

    command = f"git -C {quote}{target}{quote} commit -m x"
    result = _run_hook(cwd_repo, _bash_input(command))

    assert result.returncode == expected_code
    if expected_code == 2:
        assert BLOCK_MESSAGE in result.stderr
    else:
        assert result.stderr == ""


def test_DIR_RE_is_anchored_to_command_position(tmp_path: Path) -> None:
    """A -C inside quoted text must not select the directory checked.

    The first `git -C` is inside an echo argument pointing at a main checkout.
    The real commit runs in the cwd, which is a feature branch, so it is allowed.
    """
    cwd_repo = _init_repo(tmp_path / "cwd", "feat/issue-597-cwd")
    main_other = _init_repo(tmp_path / "main-other", "main")

    command = f'echo "git -C {main_other} status" && git commit -m y'
    result = _run_hook(cwd_repo, _bash_input(command))

    assert result.returncode == 0
    assert result.stderr == ""


def test_python3_missing_fails_open_with_warning(tmp_path: Path) -> None:
    """Without python3 the guard is disabled: exit 0 plus a visible warning."""
    repo = _init_repo(tmp_path / "cwd-main", "main")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cat_path = shutil.which("cat")
    assert cat_path is not None
    (bin_dir / "cat").symlink_to(cat_path)
    bash_path = shutil.which("bash")
    assert bash_path is not None

    result = subprocess.run(
        [bash_path, str(HOOK)],
        cwd=repo,
        input=_bash_input("git commit -m x"),
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": str(bin_dir)},
    )

    assert result.returncode == 0
    assert "python3 not found" in result.stderr
    assert BLOCK_MESSAGE not in result.stderr
