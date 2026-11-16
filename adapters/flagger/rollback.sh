#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# rollback-flagger: all traffic back to the primary (docs/adr/0095 §3).
# Idempotent: with no canary in flight (Flagger already rolled it back, or
# promoted it, or none was deployed) it does nothing, so the launchpad's
# opening rollback costs nothing. Otherwise it closes the stage gate, opens
# the rollback flag the Canary's `rollback` webhook reads (/rollback/check),
# waits until Flagger marks the canary Failed at weight 0, and closes the
# flag again, so the next canary is not rolled back on sight. A canary
# Flagger is promoting cannot be rolled back: one stderr line and exit 1.
# Not a gate.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/flagger/env.sh
. "$here/env.sh"

c=$(canary_json)
phase=$(field "$c" '.status.phase // ""')
case "$phase" in
  Progressing|WaitingPromotion) ;;
  Promoting|Finalising)
    printf 'rollback-flagger: canary %s/%s is being promoted (%s); Flagger rolls back no promotion\n' \
      "$FLAGGER_NAMESPACE" "$FLAGGER_CANARY" "$phase" >&2
    exit 1 ;;
  *) exit 0 ;;
esac

trap 'tester /rollback/close || :' EXIT
tester /gate/close
tester /rollback/open
i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  c=$(canary_json) || c='{}'
  phase=$(field "$c" '.status.phase // ""')
  weight=$(weight_of "$c")
  if [ "$phase" = Failed ] && [ "$weight" = 0 ]; then
    tester /rollback/close
    exit 0
  fi
  i=$((i + 1))
  sleep 1
done
printf 'rollback-flagger: canary %s/%s is %s at weight %s after %ss, want Failed at 0\n' \
  "$FLAGGER_NAMESPACE" "$FLAGGER_CANARY" "$phase" "$weight" "$READY_TIMEOUT" >&2
exit 1
