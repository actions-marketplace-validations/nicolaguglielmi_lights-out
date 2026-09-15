#!/bin/sh
# budget-after (AfterModel hook): accumulates token usage into
# $CREW_OUT/tokens so budget-before.sh can deny the next model call once
# TOKEN_BUDGET is exceeded (docs/adr/0017 §8). Best-effort: if the AfterModel
# input carries no llm_response.usageMetadata, this hook adds nothing and
# the post-run check on the `result` event's stats in adapters/gemini-cli/
# run.sh is the fallback enforcement — which mode is real is settled at the
# first L1 run (docs/adr/0017 "Verify at L1" #1) and recorded there. Never
# denies; always exits 0.
set -eu
: "${CREW_OUT:=.}"

input=$(cat)
tokens=$(printf '%s' "$input" | jq -r '.llm_response.usageMetadata.totalTokenCount // empty' 2>/dev/null || true)

if [ -n "$tokens" ]; then
  prev=0
  [ -f "$CREW_OUT/tokens" ] && prev=$(cat "$CREW_OUT/tokens")
  printf '%s\n' "$((prev + tokens))" > "$CREW_OUT/tokens"
fi

exit 0
