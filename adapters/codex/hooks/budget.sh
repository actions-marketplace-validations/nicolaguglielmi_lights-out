#!/bin/sh
# budget (Codex PreModelRequest hook, docs/adr/0041 §5): codex has no
# --max-turns and no token flag, and no hook can stop a run (exit 2 and
# {"continue":false} were ignored, verified on 0.166.0). So this hook,
# which runs before every model request, counts the requests (MAX_TURNS)
# and reads the cumulative total_token_usage.total_tokens the rollout
# named on stdin records after each response (TOKEN_BUDGET, the unit the
# budget was measured in: input, cached included, plus output); on a
# limit it writes the budget's name to $CREW_OUT/stop and kills the
# `timeout` the entrypoint wrote to /tmp/codex.pid, which forwards the
# TERM to codex before this request leaves (verified: limit 2, exactly 2
# requests reached the endpoint).
set -eu
: "${CREW_OUT:=.}"

transcript=$(jq -r '.transcript_path // empty' 2>/dev/null || true)
n=$(( $(cat "$CREW_OUT/requests" 2>/dev/null || echo 0) + 1 ))
printf '%s\n' "$n" > "$CREW_OUT/requests" 2>/dev/null || :
spent=0
if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  spent=$(jq -s '[.[] | select(.type == "event_msg" and .payload.type == "token_count")
    | .payload.info.total_token_usage.total_tokens // empty] | last // 0' "$transcript" 2>/dev/null || echo 0)
fi
printf '%s\n' "$spent" > "$CREW_OUT/tokens" 2>/dev/null || :

stop=""
if [ -n "${MAX_TURNS:-}" ] && [ "$n" -gt "$MAX_TURNS" ]; then
  stop=MAX_TURNS
elif [ -n "${TOKEN_BUDGET:-}" ] && [ "$spent" -ge "$TOKEN_BUDGET" ]; then
  stop=TOKEN_BUDGET
fi
if [ -n "$stop" ]; then
  printf '%s\n' "$stop" > "$CREW_OUT/stop" 2>/dev/null || :
  kill -TERM "$(cat /tmp/codex.pid)" 2>/dev/null || :
  # Hold this request until the TERM has landed.
  sleep 10
fi
exit 0
