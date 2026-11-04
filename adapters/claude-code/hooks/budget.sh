#!/bin/sh
# budget (Claude Code PostToolUse hook, docs/adr/0041 §5): sums the
# session's token use from the transcript Claude Code names on stdin and,
# once it reaches TOKEN_BUDGET, writes TOKEN_BUDGET to $CREW_OUT/stop and
# prints {"continue":false}, which ends the session (verified on 2.1.311:
# terminal_reason hook_stopped, exit 0; run.sh reads the marker). The unit
# is the one the budget was measured in, Gemini's totalTokenCount: input,
# cache writes and reads included, plus output, summed over requests. A
# transcript holds one line per content block, each repeating its
# message's usage, so lines are counted once per message id. Never denies
# the tool call itself; always exits 0.
set -eu
: "${CREW_OUT:=.}"
: "${TOKEN_BUDGET:=}"

transcript=$(jq -r '.transcript_path // empty' 2>/dev/null || true)
[ -n "$TOKEN_BUDGET" ] && [ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

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
