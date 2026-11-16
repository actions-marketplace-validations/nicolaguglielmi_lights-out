#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# shift-flagger: moves <percent> of traffic to the canary (docs/adr/0095
# §2-§3). Flagger weighs the canary only through the Canary's stepWeights,
# and only after its confirm-traffic-increase webhook, the loadtester's
# /gate/check, answers 200. This verb opens that gate, waits until Flagger
# reports <percent>, and closes it: one step per call, so verify/slo.sh
# judges each stage before the next one opens. Flagger's own analysis keeps
# running meanwhile and may roll the canary back; that is one stderr line
# and exit 1, as is a <percent> no step declares or one below the current
# weight. Not a gate.
set -eu
percent=${1:?usage: shift.sh <canary-percent>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/flagger/env.sh
. "$here/env.sh"

fail() { printf 'shift-flagger: canary %s/%s %s\n' "$FLAGGER_NAMESPACE" "$FLAGGER_CANARY" "$*" >&2; exit 1; }

c=$(canary_json) || fail "not found"
declared=$(printf '%s' "$c" | jq -r --argjson p "$percent" '[.spec.analysis.stepWeights // [] | .[] | select(. == $p)] | length')
[ "$declared" -gt 0 ] || fail "declares no stepWeights step of $percent"
phase=$(field "$c" '.status.phase // ""')
weight=$(weight_of "$c")
in_flight "$phase" || fail "has no canary in flight ($phase); deploy first"
[ "$weight" -le "$percent" ] || fail "is already at $weight, past $percent"
[ "$weight" -ne "$percent" ] || exit 0

trap 'tester /gate/close || :' EXIT
tester /gate/open
i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  c=$(canary_json) || c='{}'
  phase=$(field "$c" '.status.phase // ""')
  weight=$(weight_of "$c")
  case "$phase" in
    Failed) fail "was rolled back by Flagger's analysis on the way to $percent: $(k get events \
      --field-selector "involvedObject.kind=Canary,involvedObject.name=$FLAGGER_CANARY" -o json 2>/dev/null \
      | jq -r '[.items[] | .message] | last // "no event"')" ;;
  esac
  if [ "$weight" -eq "$percent" ]; then
    tester /gate/close
    exit 0
  fi
  [ "$weight" -lt "$percent" ] || fail "went past $percent to $weight"
  i=$((i + 1))
  sleep 1
done
fail "reports weight $weight after ${READY_TIMEOUT}s, want $percent ($phase)"
