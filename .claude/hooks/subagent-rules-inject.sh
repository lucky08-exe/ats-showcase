#!/bin/bash
set -e

if [ -n "$CLAUDE_PROJECT_DIR" ]; then
    PROJECT_ROOT="$CLAUDE_PROJECT_DIR"
else
    PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fi

RULES_FILE="$PROJECT_ROOT/.claude/rules/cavecrew-shared.md"

# Fail open: TTY input, empty stdin
if [ -t 0 ]; then
    exit 0
fi

INPUT=$(cat 2>/dev/null || echo "")
if [ -z "$INPUT" ]; then
    exit 0
fi

# Extract agent_type from JSON
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null || echo "")

# Match only caveman:cavecrew-builder and caveman:cavecrew-reviewer
case "$AGENT_TYPE" in
    "caveman:cavecrew-builder"|"caveman:cavecrew-reviewer")
        # Check rules file exists
        if [ ! -f "$RULES_FILE" ]; then
            exit 0
        fi

        # Read rules content
        RULES_CONTENT=$(cat "$RULES_FILE" 2>/dev/null || echo "")
        if [ -z "$RULES_CONTENT" ]; then
            exit 0
        fi

        # Output JSON with injected rules (jq failure is silent, exit 0)
        jq -n --arg ctx "$RULES_CONTENT" '{hookSpecificOutput:{hookEventName:"SubagentStart",additionalContext:$ctx}}' 2>/dev/null || true
        exit 0
        ;;
    *)
        # No match: silent fail-open
        exit 0
        ;;
esac
