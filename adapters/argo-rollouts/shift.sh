#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# shift-argo-rollouts: moves <percent> of traffic to the canary
# (docs/adr/0051 §3). Argo Rollouts has no imperative weight: the Rollout
# declares `setWeight: <percent>` steps, each followed by an indefinite
# `pause: {}`, and this verb promotes past pauses (the plugin's `promote`,
# a status patch) until the Rollout is paused right after the step that
# sets <percent>, then reads the router's weight back. A <percent> no step
# sets is one stderr line and exit 1, never a nearest match. Not a gate.
set -eu
percent=${1:?usage: shift.sh <canary-percent>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/argo-rollouts/env.sh
. "$here/env.sh"

r=$(rollout_json)
target=$(printf '%s' "$r" | jq -r --argjson p "$percent" '
  [.spec.strategy.canary.steps // [] | to_entries[] | select(.value.setWeight == $p) | .key] | first // empty')
[ -n "$target" ] || {
  printf 'shift-argo-rollouts: rollout %s/%s has no setWeight: %s step\n' "$ARGO_NAMESPACE" "$ARGO_ROLLOUT" "$percent" >&2
  exit 1
}
want=$((target + 1))

# One promote per pause: the controller takes a moment to move past it,
# and a second promote read off a stale index would skip a stage.
promoted=-1
i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  r=$(rollout_json) || r='{}'
  at=$(printf '%s' "$r" | jq -r '.status.currentStepIndex // 0')
  paused=$(printf '%s' "$r" | jq -r '(.status.pauseConditions // []) | length')
  aborted=$(printf '%s' "$r" | jq -r '.status.abort // false')
  [ "$aborted" = false ] || {
    printf 'shift-argo-rollouts: rollout %s/%s is aborted; deploy first\n' "$ARGO_NAMESPACE" "$ARGO_ROLLOUT" >&2
    exit 1
  }
  if [ "$at" -eq "$want" ] && [ "$paused" -gt 0 ]; then
    got=$(weight_of "$r")
    [ "$got" = "$percent" ] && exit 0
  elif [ "$at" -lt "$want" ] && [ "$paused" -gt 0 ] && [ "$at" -ne "$promoted" ]; then
    status_patch '{"status":{"pauseConditions":null}}'
    promoted=$at
  elif [ "$at" -gt "$want" ]; then
    printf 'shift-argo-rollouts: rollout %s/%s is already past step %s\n' "$ARGO_NAMESPACE" "$ARGO_ROLLOUT" "$target" >&2
    exit 1
  fi
  i=$((i + 1))
  sleep 1
done
printf 'shift-argo-rollouts: router reports weight %s at step %s after %ss, want %s at step %s\n' \
  "${got:-none}" "${at:-?}" "$READY_TIMEOUT" "$percent" "$want" >&2
exit 1
