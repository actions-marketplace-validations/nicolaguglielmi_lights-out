#!/bin/sh
# agy-guard (Antigravity CLI PreToolUse hook, docs/adr/0050 §3): the shim
# between agy and the one guard, hooks/guard.sh, which stays byte-identical
# to every other harness's (docs/adr/0041 §11). Verified 2026-11-05 against
# agy 1.5.1: the hook gets {"toolCall": {"name", "args"}, "stepIdx",
# "conversationId", "transcriptPath", ...} on stdin and denies only by
# printing {"decision": "deny", "reason": ...} on stdout; its exit code is
# ignored, so guard.sh run unchanged allowed everything (the spike's push
# went through and .env was read).
#
# Two steps. First, only the tools this harness offers reach the guard:
# agy's command and file tools and manage_task, the one that reads back a
# command agy moved to the background. Every other tool agy declares to the
# model (search_web, which reads the web through the provider and which
# permissions.deny did not stop; the subagent, schedule, message and
# question tools, whose own calls were never verified to reach this hook)
# is denied by name, with its own hooks.log line, as gemini-cli excludes
# its web tools: a tool a new agy release adds is denied until it is
# named here. Second, the call is handed to guard.sh as {tool_name,
# tool_input}, and guard.sh's exit 2 becomes the deny JSON with its stderr
# as the reason. guard.sh writes the hooks.log line for every call it
# judges.
set -eu
here=$(dirname "$0")
crew_out=${CREW_OUT:-.}

input=$(cat)
name=$(printf '%s' "$input" | jq -r '.toolCall.name // "unknown"' 2>/dev/null) || name=unknown

case "$name" in
  run_command|read_file|write_file|edit_file|manage_task) ;;
  *)
    printf 'DENY %s not-offered\n' "$name" >> "$crew_out/hooks.log" 2>/dev/null || :
    jq -nc --arg r "denied: $name is not a tool this harness offers" '{decision: "deny", reason: $r}'
    exit 0
    ;;
esac

if reason=$(printf '%s' "$input" | jq -c '{tool_name: .toolCall.name, tool_input: .toolCall.args}' 2>/dev/null \
    | sh "$here/guard.sh" 2>&1 >/dev/null); then
  exit 0
fi
jq -nc --arg r "${reason:-denied}" '{decision: "deny", reason: $r}'
exit 0
