#!/bin/sh
# budget-before (BeforeModel hook): adds the call budget-after.sh recorded to
# $CREW_OUT/tokens, then denies the next model call once that total reaches
# TOKEN_BUDGET (docs/adr/0017 §8).
# Fails open (allows) if TOKEN_BUDGET is unset or nothing has been recorded
# yet: this hook only ever tightens the pre-emptive limits, MAX_TURNS
# (model.maxSessionTurns) and TIMEOUT_S (the entrypoint's `timeout`), never
# substitutes for them.
set -eu
: "${CREW_OUT:=.}"
: "${TOKEN_BUDGET:=}"

cat >/dev/null

# The call that just ended counts once, at the running total budget-after.sh
# kept for it (docs/adr/0017 §8, amendment 2026-11-14), whatever the budget.
spent=0
[ -f "$CREW_OUT/tokens" ] && spent=$(cat "$CREW_OUT/tokens")
case "$spent" in ''|*[!0-9]*) spent=0 ;; esac
if [ -f "$CREW_OUT/tokens.call" ]; then
  call=$(cat "$CREW_OUT/tokens.call")
  case "$call" in ''|*[!0-9]*) call=0 ;; esac
  spent=$((spent + call))
  printf '%s\n' "$spent" > "$CREW_OUT/tokens"
  rm -f "$CREW_OUT/tokens.call"
fi

[ -n "$TOKEN_BUDGET" ] || exit 0

if [ "$spent" -ge "$TOKEN_BUDGET" ]; then
  # The stop marker run.sh reads (docs/adr/0041 §5): which budget stopped
  # the run, whatever exit code the CLI then chooses.
  printf 'TOKEN_BUDGET\n' > "$CREW_OUT/stop" 2>/dev/null || :
  printf 'TOKEN_BUDGET exceeded: %s >= %s\n' "$spent" "$TOKEN_BUDGET" >&2
  exit 2
fi

exit 0
