"""Tests for .claude/hooks/pre-commit-no-main.sh (issues #593, #597).

Each test builds throwaway git repositories under tmp_path and runs the hook
with a repository as cwd. The real checkout is never touched. No test runs a
real `git commit`; the hook only inspects the command text and the branch.
"""

import json
import shutil
import subprocess
import time
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


def _nested_substitution(depth: int, inner: str) -> str:
    """Wrap ``inner`` in ``depth`` levels of double-quoted command substitution."""
    command = inner
    for _ in range(depth):
        command = f'echo "$({command})"'
    return command


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


def test_git_commit_after_line_continuation_argument_text_is_not_a_commit(
    repo: Path,
) -> None:
    """A backslash-newline joins lines, so `git commit` stays an argument of grep."""
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
        "git -c core.hooksPath=/x commit -m x",
        "git commit; echo hi",
        "git commit&&echo",
        "git commit|tee f",
        "(git commit)",
        "git add x\ngit commit -m y",
        "time git commit -m x",
        "env X=1 git commit -m x",
        "GIT_DIR=x git commit -m x",
        "sudo git commit -m x",
        "command git commit -m x",
        "exec git commit -m x",
        "xargs git commit -m x",
        "if true; then git commit -m x; fi",
        "for i in 1; do git commit -m x; done",
        "! git commit -m x",
        "{ git commit -m x; }",
        "git --git-dir /x commit -m x",
        "git --work-tree /x commit -m x",
    ],
    ids=[
        "abs-path",
        "sh-c-single-quote",
        "bash-lc-double-quote",
        "long-option",
        "lowercase-c-option",
        "semicolon-after-commit",
        "ampersand-after-commit",
        "pipe-after-commit",
        "subshell",
        "plain-newline",
        "prefix-time",
        "prefix-env",
        "prefix-assignment",
        "prefix-sudo",
        "prefix-command",
        "prefix-exec",
        "prefix-xargs",
        "keyword-then",
        "keyword-do",
        "keyword-bang",
        "keyword-brace",
        "long-option-git-dir-value",
        "long-option-work-tree-value",
    ],
)
def test_commit_forms_are_blocked_on_main(repo: Path, command: str) -> None:
    result = _run_hook(repo, _bash_input(command))

    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "echo x | xargs -s 100 git commit",
        "echo x | xargs -E EOF git commit",
        "echo x | xargs -n 1 git commit -m x",
        "echo x | xargs -rn1 git commit -m x",
        "echo x | xargs -P 2 -I {} git commit -m {}",
        "echo x | xargs -e git commit -m x",
        "echo x | xargs -i git commit -m x",
        "echo x | xargs -l git commit -m x",
        "echo x | xargs --max-args 1 git commit -m x",
        "echo x | xargs --max-args=1 git commit -m x",
        "echo x | xargs -- git commit -m x",
    ],
    ids=[
        "separate-s-value",
        "separate-E-value",
        "separate-n-value",
        "bundled-rn-value",
        "separate-P-and-I-values",
        "attached-only-e",
        "attached-only-i",
        "attached-only-l",
        "long-separate-value",
        "long-attached-value",
        "double-dash-end",
    ],
)
def test_xargs_option_values_do_not_hide_git_commit(repo: Path, command: str) -> None:
    result = _run_hook(repo, _bash_input(command))

    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "echo x | xargs -s 100 git status",
        "echo git | xargs -I {} echo commit",
    ],
    ids=["value-swallowed-then-status", "git-is-argument-of-echo"],
)
def test_xargs_non_commit_commands_are_allowed(repo: Path, command: str) -> None:
    result = _run_hook(repo, _bash_input(command))

    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize(
    "command",
    [
        "nice -n 5 git commit -m x",
        "nice -10 git commit -m x",
        "nice --adjustment 5 git commit -m x",
        "timeout 5 git commit -m x",
        "timeout -s KILL 5 git commit -m x",
        "timeout -k 1 5 git commit -m x",
        "stdbuf -oL git commit -m x",
        "stdbuf -o L git commit -m x",
        "setsid git commit -m x",
        "ionice -c 2 -n 4 git commit -m x",
        "find . -maxdepth 0 -exec git commit -m x \\;",
        "find . -execdir git commit -m x {} +",
    ],
    ids=[
        "nice-n-value",
        "nice-attached-digits",
        "nice-long-value",
        "timeout-duration",
        "timeout-signal-value",
        "timeout-kill-after-value",
        "stdbuf-attached-mode",
        "stdbuf-separate-mode",
        "setsid",
        "ionice-class-and-level",
        "find-exec-escaped-semicolon",
        "find-execdir-plus",
    ],
)
def test_wrapper_forms_are_blocked_on_main(repo: Path, command: str) -> None:
    result = _run_hook(repo, _bash_input(command))

    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "nice -n 5 ls",
        "timeout 5 ls",
        "find . -exec ls {} \\;",
        "find . -name git",
    ],
    ids=["nice-non-commit", "timeout-non-commit", "find-exec-ls", "find-name-git"],
)
def test_wrapper_non_commit_commands_are_allowed(repo: Path, command: str) -> None:
    result = _run_hook(repo, _bash_input(command))

    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize(
    "command",
    [
        'echo "$(git commit -m x)"',
        'x="$(git commit -m y)"',
        'echo "`git commit -m x`"',
        'echo "$(echo "$(git commit -m x)")"',
    ],
    ids=["dollar-paren", "assignment", "backticks", "nested-in-substitution"],
)
def test_command_substitution_in_double_quotes_is_blocked_on_main(repo: Path, command: str) -> None:
    result = _run_hook(repo, _bash_input(command))

    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "echo '$(git commit -m x)'",
        'echo "\\$(git commit -m x)"',
        'echo "\\`git commit -m x\\`"',
        'echo "$(ls docs/)"',
    ],
    ids=["single-quoted", "escaped-dollar", "escaped-backtick", "substitution-without-commit"],
)
def test_substitution_text_that_is_not_run_is_allowed(repo: Path, command: str) -> None:
    result = _run_hook(repo, _bash_input(command))

    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize(
    "command",
    [
        "# note; git commit -m x",
        "ls # git commit -m x",
    ],
    ids=["comment-line", "trailing-comment"],
)
def test_comment_text_is_not_a_commit(repo: Path, command: str) -> None:
    result = _run_hook(repo, _bash_input(command))

    assert result.returncode == 0
    assert result.stderr == ""


def test_git_commit_on_line_after_comment_is_blocked(repo: Path) -> None:
    result = _run_hook(repo, _bash_input("# note\ngit commit -m x"))

    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


@pytest.mark.parametrize(
    ("depth", "inner", "expected_code"),
    [
        (5, "git commit -m x", 2),
        (40, "git commit -m x", 2),
        (40, "ls", 0),
    ],
    ids=["depth-5-commit", "depth-40-commit-fails-closed", "depth-40-no-commit"],
)
def test_deep_nesting_is_capped_and_fails_closed_on_main(
    repo: Path, depth: int, inner: str, expected_code: int
) -> None:
    result = _run_hook(repo, _bash_input(_nested_substitution(depth, inner)))

    assert result.returncode == expected_code
    if expected_code == 2:
        assert BLOCK_MESSAGE in result.stderr
    else:
        assert result.stderr == ""


def test_long_option_then_C_targets_other_dir(tmp_path: Path) -> None:
    """`-C` after a long option selects the checked directory, not the cwd."""
    cwd_repo = _init_repo(tmp_path / "cwd", "feat/issue-597-cwd")
    target = _init_repo(tmp_path / "target", "main")

    result = _run_hook(cwd_repo, _bash_input(f"git --no-pager -C {target} commit -m x"))

    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        'grep -c "git commit" docs/',
        'echo "a; git commit"',
        'git log --grep="x; git commit"',
    ],
    ids=["grep-c-quoted", "echo-quoted-separator", "log-grep-quoted"],
)
def test_quoted_commit_text_as_argument_is_not_a_commit(repo: Path, command: str) -> None:
    result = _run_hook(repo, _bash_input(command))

    assert result.returncode == 0
    assert result.stderr == ""


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


def test_git_C_inside_quoted_echo_does_not_select_directory(tmp_path: Path) -> None:
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


@pytest.mark.parametrize(
    "command",
    [
        "echo " + "a" * 1_000_000,
        "echo " + "word " * 200_000,
        'echo "' + "a" * 1_000_000 + '"',
    ],
    ids=["single-word", "many-words", "double-quoted"],
)
def test_one_megabyte_command_finishes_quickly(repo: Path, command: str) -> None:
    start = time.monotonic()
    result = _run_hook(repo, _bash_input(command))
    elapsed = time.monotonic() - start

    assert result.returncode == 0
    assert elapsed < 10


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
