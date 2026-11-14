#!/bin/sh
# budget-after (AfterModel hook): records the running token total of the
# model call in flight into $CREW_OUT/tokens.call, so budget-before.sh can
# add it to $CREW_OUT/tokens before the next call and deny that call once
# TOKEN_BUDGET is reached (docs/adr/0017 §8). gemini-cli 0.61.0-preview.0
# fires AfterModel once per streamed chunk, and each chunk's
# usageMetadata.totalTokenCount is the call's running total (amendment
# 2026-11-14): the largest one seen is the call's, never their sum. A chunk
# with no usageMetadata changes nothing; the post-run check on the `result`
# event's stats in adapters/gemini-cli/run.sh stays the fallback. Never
# denies; always exits 0.
set -eu
: "${CREW_OUT:=.}"

input=$(cat)
tokens=$(printf '%s' "$input" | jq -r '.llm_response.usageMetadata.totalTokenCount // empty' 2>/dev/null || true)

case "$tokens" in
  ''|*[!0-9]*) exit 0 ;;
esac
call=0
[ -f "$CREW_OUT/tokens.call" ] && call=$(cat "$CREW_OUT/tokens.call")
case "$call" in ''|*[!0-9]*) call=0 ;; esac
[ "$tokens" -gt "$call" ] && printf '%s\n' "$tokens" > "$CREW_OUT/tokens.call"

exit 0
