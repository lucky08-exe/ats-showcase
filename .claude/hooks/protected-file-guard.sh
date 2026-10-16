#!/bin/bash
# PreToolUse Protected File Guard Hook (Issue #659)
#
# Denies Edit/Write on protected paths (.claude/**, AGENTS.md, CLAUDE.md,
# .claude/settings.json) when agent_type matches a known subagent type.
# Allows when agent_type is absent/unrecognized (human main session never blocked)
# or when tool is not Edit/Write, or when file_path is not protected.
# Fails open on any error (missing jq, malformed JSON, etc.).

set -e

# Resolve project root
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

# Known subagent types that trigger enforcement
KNOWN_TYPES=(
  "caveman:cavecrew-builder"
  "caveman:cavecrew-reviewer"
  "caveman:cavecrew-investigator"
  "cavecrew-builder"
  "cavecrew-reviewer"
  "builder"
  "reviewer"
  "architect"
  "slop-hunter"
  "gate-enforcer"
)

# Protected paths (relative to repo root, no trailing slash)
PROTECTED_PATHS=(
  "AGENTS.md"
  "CLAUDE.md"
  ".claude/agents"
  ".claude/rules"
  ".claude/skills"
  ".claude/settings.json"
)

# Read JSON from stdin
input_json=$(cat 2>/dev/null || echo '{}')

# Extract tool_name, file_path, agent_type using jq
# Fails open (defaults to empty) if jq is unavailable or JSON is malformed
tool_name=$(echo "$input_json" | jq -r '.tool_name // empty' 2>/dev/null || echo '')
file_path=$(echo "$input_json" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo '')
agent_type=$(echo "$input_json" | jq -r '.agent_type // empty' 2>/dev/null || echo '')

# Allow: SubagentHandback tool (pseudo-tool, never block)
if [ "$tool_name" = "SubagentHandback" ]; then
  exit 0
fi

# Allow: agent_type absent or empty (human main session)
if [ -z "$agent_type" ]; then
  exit 0
fi

# Allow: tool is not Edit or Write
if [ "$tool_name" != "Edit" ] && [ "$tool_name" != "Write" ]; then
  exit 0
fi

# Allow: file_path is empty
if [ -z "$file_path" ]; then
  exit 0
fi

# Check if agent_type is in known subagent types list
type_is_known=0
for known_type in "${KNOWN_TYPES[@]}"; do
  if [ "$agent_type" = "$known_type" ]; then
    type_is_known=1
    break
  fi
done

# Allow: agent_type is not a known subagent type (unrecognized)
if [ $type_is_known -eq 0 ]; then
  exit 0
fi

# Normalize file_path: remove leading slash, resolve .., remove symlinks, normalize to relative
# If it's already relative (no leading /), use as-is after normalization
normalized_path="$file_path"
if [[ "$normalized_path" =~ ^/ ]]; then
  normalized_path="${normalized_path:1}"
fi

# Resolve .. and normalize the path (simple approach: cd to repo root conceptually)
# Use realpath if available, else manual normalization
if command -v realpath >/dev/null 2>&1; then
  # realpath normalizes the path; we want it relative to REPO_ROOT
  abs_path=$(realpath -m "$REPO_ROOT/$normalized_path" 2>/dev/null || echo "")
  if [ -n "$abs_path" ]; then
    # Make it relative to REPO_ROOT
    normalized_path="${abs_path#$REPO_ROOT/}"
  fi
fi

# Check if normalized_path matches any protected path
# Match logic: exact match or path component match (for .claude/agents/**, etc.)
path_is_protected=0
for protected in "${PROTECTED_PATHS[@]}"; do
  # Exact match
  if [ "$normalized_path" = "$protected" ]; then
    path_is_protected=1
    break
  fi
  # Prefix match for directories (e.g., .claude/agents/foo.md matches .claude/agents)
  if [[ "$normalized_path" =~ ^"${protected}"/ ]]; then
    path_is_protected=1
    break
  fi
done

# Allow: file_path is not a protected path
if [ $path_is_protected -eq 0 ]; then
  exit 0
fi

# Deny: all conditions met (Edit/Write, known agent_type, protected path)
# Output permissionDecision JSON via jq
jq -n --arg tool "$tool_name" --arg path "$file_path" --arg agent "$agent_type" \
  '{permissionDecision: {decision: "deny", reason: "Edit/Write on protected file \($path) denied for subagent \($agent)"}}' 2>/dev/null || exit 0

exit 0
