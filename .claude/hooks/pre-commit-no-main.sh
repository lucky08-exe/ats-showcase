#!/bin/bash
# Enforce feature branch workflow: block `git commit` directly on main.
#
# Registered as a Claude Code PreToolUse hook (matcher: Bash). Claude Code
# passes the hook input as JSON on stdin. A python3 tokenizer (stdlib only,
# run with -I) splits the Bash command into simple commands at unquoted shell
# separators (newline, ; & | ( ) ` and redirections). It drops leading wrappers
# (env assignments, if/then/do/!/{ keywords, command, exec, builtin, nohup, time,
# env, sudo, xargs, nice, timeout, stdbuf, setsid, ionice) and skips their
# options best-effort, including xargs value options. `find ... -exec|-execdir|
# -ok|-okdir CMD ;` checks CMD.
# A simple command whose program is git (any path) and whose subcommand is
# `commit` after global options (-c <kv>, -C <dir>, --no-pager, --git-dir <v>)
# is a commit. `sh|bash|zsh|dash|ksh -c <script>` is parsed recursively, and so
# are $(...) and backtick bodies inside double quotes (not inside single quotes;
# \$ and \` are literal). Nesting deeper than 32 levels counts as a commit in the
# hook's cwd when the text still has `git` followed later by `commit`.
# Quoted text is one word, so `echo "a; git commit"` and `grep git commit docs/`
# never match. A backslash-newline continues the line; a bare newline separates
# commands. An unquoted # at the start of a word begins a comment to end of line.
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
#   positive (accepted). `cd <main checkout> && git commit` from a feature
#   session is a false negative. A real fix would be git's own pre-commit hook.
# - --git-dir / --work-tree are parsed but do not select the branch checked.
# - eval: `eval "git commit"` is not parsed; its argument is one plain word.
# - Process substitution: `<(...)` and `>(...)` are parsed as subshells, so they
#   are covered when unquoted. Inside double quotes they are literal text.
# - git rebase --exec: the string it runs through the shell is not parsed.
# - git aliases: an alias that expands to commit (for example `git ci`) is not
#   resolved.
# - Variables are not expanded: `x=git; $x commit` is not caught. $'...' ANSI-C
#   quoting is not decoded.
# - env -S and shell options before -c (for example `bash -o pipefail -c ...`)
#   are not parsed, so the script is skipped.
# - Wrapper options are skipped best-effort; an unknown option can hide the
#   command that follows it.
# - Heredoc bodies are parsed as commands (a false positive, fails closed).

if ! command -v python3 >/dev/null 2>&1; then
  echo "pre-commit-no-main: WARNING python3 not found; commits to main are NOT guarded" >&2
  exit 0
fi

# Reads hook JSON on stdin and prints the directory of a `git commit` found in
# tool_input.command, or nothing. Exit status is non-zero on any error.
CHECK='import json, os, re, sys

SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
PREFIX_WORDS = {"!", "{", "then", "do", "else", "if", "while", "until"}
# wrapper -> (short options taking a value, short options with attached-only
# value, long options taking a value). GNU forms, best effort.
WRAPPERS = {
    "builtin": ("", "", ()),
    "command": ("", "", ()),
    "nohup": ("", "", ()),
    "setsid": ("", "", ()),
    "exec": ("a", "", ()),
    "time": ("fo", "", ("--format", "--output")),
    "env": ("uCS", "", ("--unset", "--chdir", "--split-string")),
    "sudo": ("CDgphRrtTUu", "", ("--user", "--group", "--host", "--prompt",
                                 "--chdir", "--other-user")),
    "xargs": ("nPLsEdaI", "eil", ("--arg-file", "--delimiter", "--max-args",
                                  "--max-procs", "--max-chars",
                                  "--process-slot-var")),
    "nice": ("n", "", ("--adjustment",)),
    "timeout": ("ks", "", ("--kill-after", "--signal")),
    "stdbuf": ("ioe", "", ("--input", "--output", "--error")),
    "ionice": ("cnpPu", "", ("--class", "--classdata", "--pid", "--pgid",
                             "--uid")),
}
DURATION_WRAPPERS = {"timeout"}
FIND_EXEC = {"-exec", "-execdir", "-ok", "-okdir"}
LONG_VALUE_OPTS = {"--git-dir", "--work-tree", "--namespace", "--super-prefix",
                   "--config-env"}
MAX_DEPTH = 32
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
SHELL_C = re.compile(r"-[A-Za-z]*c[A-Za-z]*")
DEEP_COMMIT = re.compile(r"\bgit\b.*\bcommit\b", re.S)
PLAIN = re.compile(r"[^\s;&|()`<>\\\x27\x22]+")
DQ_PLAIN = re.compile(r"[^\x22\\$`]+")


def match_paren(text, i):
    """Return the index of the paren closing the open paren at text[i], or -1."""
    depth = 0
    j, n = i, len(text)
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "\x27":
            end = text.find("\x27", j + 1)
            if end < 0:
                return -1
            j = end + 1
            continue
        if c == "\"":
            j += 1
            while j < n and text[j] != "\"":
                j += 2 if text[j] == "\\" else 1
            j += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def double_quoted(text, i, cur, subs):
    """Read a double-quoted string that starts just before text[i].

    Literal text goes to cur. Bodies of $(...) and backticks go to subs. Returns
    the index after the closing quote, or len(text) when unterminated.
    """
    n = len(text)
    while i < n and text[i] != "\"":
        m = DQ_PLAIN.match(text, i)
        if m:
            cur.append(m.group())
            i = m.end()
            continue
        c = text[i]
        nxt = text[i + 1 : i + 2]
        if c == "\\" and nxt in ("\"", "\\", "$", "`", "\n"):
            if nxt != "\n":
                cur.append(nxt)
            i += 2
        elif c == "$" and nxt == "(":
            close = match_paren(text, i + 1)
            if close < 0:
                break
            subs.append(text[i + 2 : close])
            cur.append(text[i : close + 1])
            i = close + 1
        elif c == "`":
            close = i + 1
            while close < n and text[close] != "`":
                close += 2 if text[close] == "\\" else 1
            if close >= n:
                break
            subs.append(text[i + 1 : close])
            cur.append(text[i : close + 1])
            i = close + 1
        else:
            cur.append(c)
            i += 1
    return min(i + 1, n)


def segments(text):
    """Split text into simple commands, each a list of unquoted words.

    Also returns the bodies of $(...) and backtick substitutions found inside
    double quotes, which bash runs, so the caller checks them as commands too.
    """
    segs = [[]]
    subs = []
    cur = []
    started = False
    skip = False
    i, n = 0, len(text)

    def end_word():
        nonlocal started, skip
        if started:
            word = "".join(cur)
            cur.clear()
            if skip:
                skip = False
            else:
                segs[-1].append(word)
        started = False

    while i < n:
        c = text[i]
        if c == "\\":
            if text[i + 1 : i + 2] != "\n":
                cur.append(text[i + 1 : i + 2])
                started = True
            i += 2
        elif c == "\x27":
            end = text.find("\x27", i + 1)
            end = n if end < 0 else end
            cur.append(text[i + 1 : end])
            started = True
            i = end + 1
        elif c == "\"":
            i = double_quoted(text, i + 1, cur, subs)
            started = True
        elif c == "#" and not started:
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif c in "<>":
            if started and "".join(cur).isdigit():
                cur.clear()
                started = False
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
            m = PLAIN.match(text, i)
            j = m.end() if m else i + 1
            cur.append(text[i:j])
            started = True
            i = j
    end_word()
    return segs, subs


def skip_options(words, i, value_short, attached_short, value_long):
    """Return the index of the first word after the options at words[i]."""
    n = len(words)
    while i < n:
        w = words[i]
        if w == "--":
            return i + 1
        if w.startswith("--"):
            name, eq, _ = w.partition("=")
            i += 2 if name in value_long and not eq else 1
        elif w.startswith("-") and len(w) > 1:
            i += 1
            for j in range(1, len(w)):
                if w[j] in value_short:
                    if j == len(w) - 1:
                        i += 1
                    break
                if w[j] in attached_short:
                    break
        else:
            return i
    return i


def skip_wrapper(name, words, i):
    value_short, attached_short, value_long = WRAPPERS[name]
    i = skip_options(words, i, value_short, attached_short, value_long)
    return i + 1 if name in DURATION_WRAPPERS else i


def strip_prefixes(words):
    i = 0
    while i < len(words):
        w = words[i]
        name = os.path.basename(w)
        if name in WRAPPERS:
            i = skip_wrapper(name, words, i + 1)
        elif w in PREFIX_WORDS or w.startswith("-") or ASSIGN.match(w):
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


def check_words(words, base, depth):
    words = strip_prefixes(words)
    if not words:
        return None
    head = os.path.basename(words[0])
    if head == "git":
        return git_commit_dir(words[1:], base)
    if head in SHELLS:
        script = shell_script(words[1:])
        if script is None:
            return None
        return find_commit_dir(script, base, depth + 1)
    if head == "find":
        for k, w in enumerate(words):
            if w in FIND_EXEC:
                end = k + 1
                while end < len(words) and words[end] not in (";", "+"):
                    end += 1
                found = check_words(words[k + 1 : end], base, depth)
                if found is not None:
                    return found
    return None


def find_commit_dir(cmd, base, depth=0):
    if depth > MAX_DEPTH:
        return base if DEEP_COMMIT.search(cmd) else None
    segs, subs = segments(cmd)
    for seg in segs:
        found = check_words(seg, base, depth)
        if found is not None:
            return found
    for body in subs:
        found = find_commit_dir(body, base, depth + 1)
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
