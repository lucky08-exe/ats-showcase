#!/bin/bash
# SubagentStop Loop Cap Hook (Issue #660)
#
# Caps the cavecrew-builder/cavecrew-reviewer review loop at 4 iterations.
# Reads SubagentStop hook JSON on stdin; maintains a per-agent_id counter.
#
# Scoped by agent_type to {caveman:cavecrew-builder, caveman:cavecrew-reviewer,
# cavecrew-builder, cavecrew-reviewer} only. Fails open on any error (allows stop).

set -e

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
COUNTER_DIR="${REPO_ROOT}/.claude/logs/subagent-loop-cap"
ALLOWED_TYPES=(
  "caveman:cavecrew-builder"
  "caveman:cavecrew-reviewer"
  "cavecrew-builder"
  "cavecrew-reviewer"
)

# Read JSON from stdin
input_json=$(cat 2>/dev/null || echo '{}')

# Extract agent_id and agent_type using jq
# Fails open (returns empty) if jq is unavailable or JSON is malformed
agent_id=$(echo "$input_json" | jq -r '.agent_id // empty' 2>/dev/null || echo '')
agent_type=$(echo "$input_json" | jq -r '.agent_type // empty' 2>/dev/null || echo '')

# Fail open: missing agent_id or agent_type
if [ -z "$agent_id" ] || [ -z "$agent_type" ]; then
  exit 0
fi

# Check if agent_type is in allowed list
type_allowed=0
for allowed in "${ALLOWED_TYPES[@]}"; do
  if [ "$agent_type" = "$allowed" ]; then
    type_allowed=1
    break
  fi
done

# Fail open: agent_type not in scope
if [ $type_allowed -eq 0 ]; then
  exit 0
fi

# Sanitize agent_id: alphanumeric, hyphen, underscore only; max 50 chars
sanitized_agent_id=$(echo "$agent_id" | sed 's/[^a-zA-Z0-9_-]//g' | cut -c1-50)

# Fail open: sanitization resulted in empty string
if [ -z "$sanitized_agent_id" ]; then
  exit 0
fi

# Create counter directory if it doesn't exist
mkdir -p "$COUNTER_DIR" 2>/dev/null || exit 0

counter_file="${COUNTER_DIR}/${sanitized_agent_id}.count"

# Read current counter value (default 0 if missing or unreadable)
current_count=0
if [ -f "$counter_file" ]; then
  current_count=$(cat "$counter_file" 2>/dev/null) || current_count=0
  # Validate it's a number
  if ! [[ "$current_count" =~ ^[0-9]+$ ]]; then
    current_count=0
  fi
fi

# Increment counter
new_count=$((current_count + 1))

# Write back (fail open if write fails)
echo "$new_count" > "$counter_file" 2>/dev/null || exit 0

# Check if we've hit the cap (4 events)
if [ "$new_count" -eq 4 ]; then
  # Output JSON to stdout so hook system shows it to user (fail open if jq is missing)
  jq -n --arg agent_id "$agent_id" \
    '{systemMessage: "SubagentStop loop cap hit for agent_id \($agent_id) (4 stop events): escalate to human review."}' 2>/dev/null || exit 0
fi

exit 0
