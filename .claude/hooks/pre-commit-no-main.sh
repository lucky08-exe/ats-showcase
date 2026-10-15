#!/bin/bash
# Enforce feature branch workflow: block `git commit` directly on main.
#
# Registered as a Claude Code PreToolUse hook (matcher: Bash). Claude Code
# passes the hook input as JSON on stdin. A python3 tokenizer (stdlib only,
# run with -I) splits the Bash command into simple commands at unquoted shell
# separators (newline, ; & | ( ) ` and redirections) and drops leading prefixes
# (env assignments, time, env, sudo, xargs, command, exec, then, do, !, {).
# A simple command whose program is git (any path) and whose subcommand is
# `commit` after global options (-c <kv>, -C <dir>, --no-pager, --git-dir <v>)
# is a commit. `sh|bash|zsh|dash|ksh -c <script>` is parsed recursively.
# Quoted text is one word, so `echo "a; git commit"` and `grep git commit docs/`
# never match. A backslash-newline continues the line; a bare newline separates
# commands.
#
# The branch is read from the directory of the commit: `git -C <dir>` (repeated
# -C is cumulative; ~ is expanded) or the hook's cwd when no -C is given. Exit 2
# blocks the tool call and shows stderr to Claude. Any other outcome (including
# unparseable input) exits 0 so the hook fails open. A missing python3 also exits
# 0, with a one-line warning on stderr.
#
# Known limitations (#597, documented, not fixed here):
# - The branch is read from the hook's own cwd, not from a `cd <dir>` in the
#   command. `cd <worktree> && git commit` from a main session is a false
#   positive; `cd <main checkout> && git commit` from a feature session is a
#   false negative. A real fix would be git's own pre-commit hook.
# - --git-dir / --work-tree are parsed but do not select the branch checked.
# - $VAR, $(...) and backticks inside double quotes, and eval, are not expanded.

if ! command -v python3 >/dev/null 2>&1; then
  echo "pre-commit-no-main: python3 not found; no-main guard disabled" >&2
  exit 0
fi

# Reads hook JSON on stdin and prints the directory of a `git commit` found in
# tool_input.command, or nothing. Exit status is non-zero on any error.
CHECK='import json, os, re, sys

SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
PREFIX_WORDS = {"!", "{", "then", "do", "else", "if", "while", "until", "time",
                "command", "exec", "builtin", "xargs", "sudo", "env", "nohup"}
VALUE_OPTS = {"-u", "-g", "-I", "-n", "-P", "-L", "-d", "-a"}
LONG_VALUE_OPTS = {"--git-dir", "--work-tree", "--namespace", "--super-prefix",
                   "--config-env"}
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
SHELL_C = re.compile(r"-[A-Za-z]*c[A-Za-z]*")


def segments(text):
    """Split text into simple commands; each is a list of unquoted words."""
    segs = [[]]
    word = None
    skip = False
    i, n = 0, len(text)

    def end_word():
        nonlocal word, skip
        if word is not None:
            if skip:
                skip = False
            else:
                segs[-1].append(word)
        word = None

    while i < n:
        c = text[i]
        if c == "\\":
            if text[i + 1 : i + 2] != "\n":
                word = (word or "") + text[i + 1 : i + 2]
            i += 2
        elif c == "\x27":
            end = text.find("\x27", i + 1)
            end = n if end < 0 else end
            word = (word or "") + text[i + 1 : end]
            i = end + 1
        elif c == "\"":
            i += 1
            buf = word or ""
            while i < n and text[i] != "\"":
                if text[i] == "\\" and text[i + 1 : i + 2] in ("\"", "\\", "$", "`", "\n"):
                    if text[i + 1] != "\n":
                        buf += text[i + 1]
                    i += 2
                else:
                    buf += text[i]
                    i += 1
            word = buf
            i += 1
        elif c in "<>":
            if word is not None and word.isdigit():
                word = None
            end_word()
            skip = True
            i += 1
            if text[i : i + 1] == "&":
                i += 1
        elif c in ";&|()`\n":
            end_word()
            skip = False
            segs.append([])
            i += 1
        elif c in " \t\r":
            end_word()
            i += 1
        else:
            word = (word or "") + c
            i += 1
    end_word()
    return segs


def strip_prefixes(words):
    i = 0
    while i < len(words):
        w = words[i]
        if w in VALUE_OPTS:
            i += 2
        elif w.startswith("-") or w in PREFIX_WORDS or ASSIGN.match(w):
            i += 1
        else:
            break
    return words[i:]


def git_commit_dir(args, base):
    d = base
    i = 0
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a.startswith("-C") and len(a) > 2:
            d = os.path.join(d, os.path.expanduser(a[2:]))
            i += 1
        elif a == "-C":
            if i + 1 < len(args):
                d = os.path.join(d, os.path.expanduser(args[i + 1]))
            i += 2
        elif a == "-c" or a in LONG_VALUE_OPTS:
            i += 2
        else:
            i += 1
    if i < len(args) and args[i] == "commit":
        return d
    return None


def shell_script(args):
    for i, a in enumerate(args):
        if SHELL_C.fullmatch(a):
            return args[i + 1] if i + 1 < len(args) else None
        if not a.startswith("-"):
            return None
    return None


def find_commit_dir(cmd, base, depth=0):
    if depth > 5:
        return None
    for seg in segments(cmd):
        words = strip_prefixes(seg)
        if not words:
            continue
        head = os.path.basename(words[0])
        found = None
        if head == "git":
            found = git_commit_dir(words[1:], base)
        elif head in SHELLS:
            script = shell_script(words[1:])
            if script is not None:
                found = find_commit_dir(script, base, depth + 1)
        if found is not None:
            return found
    return None


try:
    command = json.load(sys.stdin)["tool_input"]["command"]
except Exception:
    sys.exit(0)
if not isinstance(command, str):
    sys.exit(0)
found = find_commit_dir(command, os.getcwd())
if found is not None:
    sys.stdout.write(found)
'

INPUT=$(cat)
[ -n "$INPUT" ] || exit 0

DIR=$(printf '%s' "$INPUT" | python3 -I -c "$CHECK" 2>/dev/null) || exit 0
[ -n "$DIR" ] || exit 0

BRANCH=$(git -C "$DIR" rev-parse --abbrev-ref HEAD 2>/dev/null)

if [ "$BRANCH" = "main" ]; then
  {
    echo "❌ Direct commits to main are not allowed."
    echo ""
    echo "Workflow:"
    echo "  1. Create feature branch: git checkout -b feat/issue-XXX-description"
    echo "  2. Commit changes: git commit -m '...'"
    echo "  3. Push branch: git push -u origin feat/issue-XXX-description"
    echo "  4. Create PR on GitHub"
    echo "  5. Merge via PR"
    echo ""
  } >&2
  exit 2
fi

exit 0
