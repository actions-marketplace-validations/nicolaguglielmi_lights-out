#!/bin/sh
# budget-before (BeforeModel hook): denies the next model call once tokens
# accumulated by budget-after.sh reach TOKEN_BUDGET (docs/adr/0017 §8).
# Fails open (allows) if TOKEN_BUDGET is unset or nothing has been recorded
# yet: this hook only ever tightens the pre-emptive limits, MAX_TURNS
# (model.maxSessionTurns) and TIMEOUT_S (the entrypoint's `timeout`), never
# substitutes for them.
set -eu
: "${CREW_OUT:=.}"
: "${TOKEN_BUDGET:=}"

cat >/dev/null

[ -n "$TOKEN_BUDGET" ] || exit 0
[ -f "$CREW_OUT/tokens" ] || exit 0

spent=$(cat "$CREW_OUT/tokens")
case "$spent" in
  ''|*[!0-9]*) exit 0 ;;
esac

if [ "$spent" -ge "$TOKEN_BUDGET" ]; then
  # The stop marker run.sh reads (docs/adr/0041 §5): which budget stopped
  # the run, whatever exit code the CLI then chooses.
  printf 'TOKEN_BUDGET\n' > "$CREW_OUT/stop" 2>/dev/null || :
  printf 'TOKEN_BUDGET exceeded: %s >= %s\n' "$spent" "$TOKEN_BUDGET" >&2
  exit 2
fi

exit 0
