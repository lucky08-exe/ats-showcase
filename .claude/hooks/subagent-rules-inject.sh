#!/bin/bash
set -e

if [ -n "$CLAUDE_PROJECT_DIR" ]; then
    PROJECT_ROOT="$CLAUDE_PROJECT_DIR"
else
    PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(dirname "$(dirname "$0")")")"
fi

RULES_FILE="$PROJECT_ROOT/.claude/rules/cavecrew-shared.md"

{
    if [ -t 0 ]; then
        exit 0
    fi

    INPUT=$(cat 2>/dev/null || echo "")
    if [ -z "$INPUT" ]; then
        exit 0
    fi

    AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null || echo "")

    case "$AGENT_TYPE" in
        "caveman:cavecrew-builder"|"caveman:cavecrew-reviewer")
            if [ ! -f "$RULES_FILE" ]; then
                exit 0
            fi

            RULES_CONTENT=$(cat "$RULES_FILE" 2>/dev/null || echo "")
            if [ -z "$RULES_CONTENT" ]; then
                exit 0
            fi

            jq -n --arg ctx "$RULES_CONTENT" '{hookSpecificOutput:{hookEventName:"SubagentStart",additionalContext:$ctx}}' 2>/dev/null || exit 0

            exit 0
            ;;
        *)
            exit 0
            ;;
    esac
} || exit 0

exit 0
