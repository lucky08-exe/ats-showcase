#!/bin/bash
# Enforce feature branch workflow: block `git commit` directly on main.
#
# Registered as a Claude Code PreToolUse hook (matcher: Bash). Claude Code
# passes the hook input as JSON on stdin; we only enforce when the Bash
# command contains a `git commit` invocation at command position. Exit 2
# blocks the tool call and shows stderr to Claude. Any other outcome
# (including unparseable input) exits 0 so the hook fails open. A missing
# python3 also exits 0, with a one-line warning on stderr.
#
# Command position: the git invocation must start the string, follow a shell
# separator (; & | ( ), or follow a quote that opens a `-c` script
# (`sh -c 'git commit ...'`). Newline is not a boundary, so text in an argument
# list (`grep git commit docs/`) never matches.
#
# Known limitation (#597, documented, not fixed here): the branch is read from
# the hook's own cwd, not from a `cd <dir>` inside the command.
# `cd <worktree> && git commit` from a main session is a false positive;
# `cd <main checkout> && git commit` from a feature session is a false
# negative. Only `git -C <dir>` is honoured. A real fix would be git's own
# pre-commit hook.

if ! command -v python3 >/dev/null 2>&1; then
  echo "pre-commit-no-main: python3 not found; no-main guard disabled" >&2
  exit 0
fi

# Parse tool_input.command from the hook JSON without third-party deps.
# -I isolates python3 so a stray module in the cwd cannot shadow the stdlib.
PARSE_CMD='import json, sys
try:
    data = json.load(sys.stdin)
    command = data["tool_input"]["command"]
except Exception:
    sys.exit(0)
if isinstance(command, str):
    sys.stdout.write(command)'

INPUT=$(cat)
[ -n "$INPUT" ] || exit 0

CMD=$(printf '%s' "$INPUT" | python3 -I -c "$PARSE_CMD" 2>/dev/null) || exit 0
[ -n "$CMD" ] || exit 0

SQ="'"
DQ='"'
# Shell word for a -C argument: "double quoted" (may hold spaces),
# 'single quoted', or bare.
TOK="(${DQ}[^${DQ}]*${DQ}|${SQ}[^${SQ}]*${SQ}|[^[:space:]${DQ}${SQ}]+)"
# Command position: start of string, a separator, or a quote opening a -c script.
CMD_START="(^|[;&|(]|-[A-Za-z]*c[[:space:]]+[${DQ}${SQ}])[[:space:]]*"
# Optional path prefix on git, e.g. /usr/bin/git.
PATHP="([^[:space:]]*/)?"
# Global options before the subcommand: -C <dir>, -c <kv>, --long-option[=v].
GLOBAL="(-[Cc][[:space:]]+${TOK}|--[A-Za-z][A-Za-z-]*(=[^[:space:]]+)?)"
# Word end after `commit`: whitespace, closing quote, or end of string.
ENDW="([[:space:]${DQ}${SQ}]|\$)"

COMMIT_RE="${CMD_START}${PATHP}git([[:space:]]+${GLOBAL})*[[:space:]]+commit${ENDW}"
# Group 3 is the -C argument (quoted or bare), anchored to the same position.
DIR_RE="${CMD_START}${PATHP}git[[:space:]]+-[Cc][[:space:]]+${TOK}"

# Remove one pair of surrounding " or ' from a shell word.
strip_quotes() {
  local s=$1
  if [ "${#s}" -ge 2 ]; then
    case $s in
      \"*\") s=${s:1:${#s}-2} ;;
      \'*\') s=${s:1:${#s}-2} ;;
    esac
  fi
  printf '%s' "$s"
}

if ! [[ $CMD =~ $COMMIT_RE ]]; then
  exit 0
fi

# Honour `git -C <dir> commit` by checking the branch of that directory.
if [[ $CMD =~ $DIR_RE ]]; then
  DIR=$(strip_quotes "${BASH_REMATCH[3]}")
  BRANCH=$(git -C "$DIR" rev-parse --abbrev-ref HEAD 2>/dev/null)
else
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
fi

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
