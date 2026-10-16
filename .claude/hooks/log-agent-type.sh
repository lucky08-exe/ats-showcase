#!/bin/bash
# TEMPORARY diagnostic (#655, removed by T9 #657 after smoke test #656).
# Logs agent_type / agent_id from SubagentStart and PreToolUse hook input so a
# human can confirm the exact string plugin agents report (for example
# caveman:cavecrew-builder). Logging only: never blocks, never denies.
#
# Fail-open: any error (missing python3, malformed or missing stdin JSON, write
# failure) prints a stderr warning and exits 0.

LOG_FILE=".claude/logs/agent-type.log"

if ! command -v python3 >/dev/null 2>&1; then
  echo "log-agent-type: WARNING python3 not found; agent_type NOT logged" >&2
  exit 0
fi

INPUT=$(cat)
if [ -z "$INPUT" ]; then
  echo "log-agent-type: WARNING empty stdin; agent_type NOT logged" >&2
  exit 0
fi

LINE=$(printf '%s' "$INPUT" | python3 -I -c '
import datetime, json, sys
data = json.load(sys.stdin)
if not isinstance(data, dict):
    raise ValueError("hook input is not a JSON object")
event = data.get("hook_event_name", "")
agent_type = data.get("agent_type", "")
agent_id = data.get("agent_id", "")
tool = data.get("tool_name", "")
ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
print("\t".join(str(x) for x in (ts, event, tool, agent_type, agent_id)))
' 2>/dev/null) || {
  echo "log-agent-type: WARNING malformed hook JSON on stdin; agent_type NOT logged" >&2
  exit 0
}

{ mkdir -p "$(dirname "$LOG_FILE")" && printf '%s\n' "$LINE" >> "$LOG_FILE"; } 2>/dev/null || {
  echo "log-agent-type: WARNING could not write $LOG_FILE; agent_type NOT logged" >&2
}
exit 0
