#!/bin/sh
# budget (Antigravity CLI PreInvocation hook, docs/adr/0050 §4): stops the
# run before the next model call once MAX_TURNS calls were made or
# TOKEN_BUDGET tokens were spent. agy has no turn or token flag. Verified
# 2026-11-05/06 against agy 1.5.1: the hook's stdin carries invocationNum,
# 0 for the first model call of the turn; printing {"injectSteps":
# [{"errorMessage": {"userMessage": ...}}], "terminationBehavior":
# "terminate"} ends the run with exit 3 and that message as the result's
# error; and the stream-json transcript the entrypoint captures already
# holds every earlier call's usage when the hook runs (at a limit of 4 and
# 1,000 tokens a call, the hook saw 0, 1000, 2000, 3000 and stopped the
# fifth call). TOKEN_BUDGET counts each agent_response step's
# usage.total_tokens, input plus output, the unit the budget was measured
# in (docs/adr/0041 §5). Writes the budget's name to $CREW_OUT/stop, the
# marker run.sh reads (docs/adr/0041 §5). Fails open on what it cannot
# read: MAX_TURNS and TIMEOUT_S still bind.
set -eu
: "${CREW_OUT:=.}"

input=$(cat)
n=$(printf '%s' "$input" | jq -r '.invocationNum // 0' 2>/dev/null) || n=0
case "$n" in ''|*[!0-9]*) n=0 ;; esac
spent=$(jq -R 'fromjson? | .step_update.usage.total_tokens? // empty' "$CREW_OUT/transcript.jsonl" 2>/dev/null \
  | awk '{s += $1} END {print s + 0}') || spent=0

stop=""
if [ -n "${MAX_TURNS:-}" ] && [ "$n" -ge "$MAX_TURNS" ]; then
  stop=MAX_TURNS
elif [ -n "${TOKEN_BUDGET:-}" ] && [ "$spent" -ge "$TOKEN_BUDGET" ]; then
  stop=TOKEN_BUDGET
fi
[ -n "$stop" ] || exit 0

printf '%s\n' "$stop" > "$CREW_OUT/stop" 2>/dev/null || :
jq -nc --arg m "over $stop" '{injectSteps: [{errorMessage: {userMessage: $m}}], terminationBehavior: "terminate"}'
exit 0
