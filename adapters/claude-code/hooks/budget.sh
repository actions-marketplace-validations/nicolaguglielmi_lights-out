#!/bin/sh
# budget (Claude Code PreToolUse hook, docs/adr/0041 §5): sums the
# session's token use from the stream-json transcript the entrypoint is
# writing to $CREW_OUT/transcript.jsonl and, once it reaches TOKEN_BUDGET,
# writes TOKEN_BUDGET to $CREW_OUT/stop and prints {"continue":false},
# which ends the session before the tool runs (verified on 2.1.311:
# terminal_reason hook_stopped, exit 0; run.sh reads the marker). Not the
# session file Claude Code names in transcript_path: found by
# ./go harness-conformance, that file lags the run by a few messages, so a
# budget read from it stopped three requests late; the stream is written
# per event. The unit is the one the budget was measured in, Gemini's
# totalTokenCount: input, cache writes and reads included, plus output,
# summed over requests, each message counted once by id. Never denies the
# tool call itself; always exits 0.
set -eu
: "${CREW_OUT:=.}"
: "${TOKEN_BUDGET:=}"

cat >/dev/null
transcript="$CREW_OUT/transcript.jsonl"
[ -n "$TOKEN_BUDGET" ] && [ -f "$transcript" ] || exit 0

spent=$(jq -s '[.[] | select(.type == "assistant" and .message.id != null)]
  | unique_by(.message.id)
  | map(.message.usage // {} | (.input_tokens // 0) + (.cache_creation_input_tokens // 0)
      + (.cache_read_input_tokens // 0) + (.output_tokens // 0))
  | add // 0' "$transcript" 2>/dev/null || echo 0)
printf '%s\n' "$spent" > "$CREW_OUT/tokens" 2>/dev/null || :

if [ "$spent" -ge "$TOKEN_BUDGET" ]; then
  printf 'TOKEN_BUDGET\n' > "$CREW_OUT/stop" 2>/dev/null || :
  jq -cn --arg r "TOKEN_BUDGET exceeded: $spent >= $TOKEN_BUDGET" '{continue: false, stopReason: $r}'
fi
exit 0
