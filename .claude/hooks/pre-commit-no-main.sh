#!/bin/bash
# Enforce feature branch workflow: block `git commit` directly on main.
#
# Registered as a Claude Code PreToolUse hook (matcher: Bash). Claude Code
# passes the hook input as JSON on stdin; we only enforce when the Bash
# command contains a `git commit` invocation. Exit 2 blocks the tool call and
# shows stderr to Claude. Any other outcome (including unparseable input)
# exits 0 so the hook fails open.

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

# `git commit` as its own word, optionally after `-C <dir>` / `-c <kv>` global
# options, and preceded by start-of-string, whitespace, or a shell separator
# (so compound commands such as `git add x && git commit -m y` match).
COMMIT_RE='(^|[;&|(]|[[:space:]])git([[:space:]]+-[Cc][[:space:]]+[^[:space:]]+)*[[:space:]]+commit([[:space:]]|$)'
DIR_RE='git[[:space:]]+-C[[:space:]]+([^[:space:]]+)'

if ! [[ $CMD =~ $COMMIT_RE ]]; then
  exit 0
fi

# Honour `git -C <dir> commit` by checking the branch of that directory.
if [[ $CMD =~ $DIR_RE ]]; then
  BRANCH=$(git -C "${BASH_REMATCH[1]}" rev-parse --abbrev-ref HEAD 2>/dev/null)
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
