#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# rollback-argo-rollouts: all traffic back to the stable revision (docs/
# adr/0051 §3), by aborting the Rollout — the plugin's `abort`, a status
# patch — and waiting until the router's canary weight is 0. Idempotent:
# a Rollout already aborted, or with no canary in flight, is left alone,
# so the launchpad's opening rollback costs nothing. The aborted
# template stays in the spec, as Argo leaves it; the next deploy.sh
# replaces it or retries it. Not a gate.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/argo-rollouts/env.sh
. "$here/env.sh"

r=$(rollout_json)
in_flight=$(printf '%s' "$r" | jq -r '.status.currentPodHash != .status.stableRS')
aborted=$(printf '%s' "$r" | jq -r '.status.abort // false')
if [ "$in_flight" = true ] && [ "$aborted" = false ]; then
  status_patch '{"status":{"abort":true}}'
fi

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  r=$(rollout_json) || r='{}'
  [ "$(weight_of "$r")" = 0 ] && exit 0
  i=$((i + 1))
  sleep 1
done
printf 'rollback-argo-rollouts: router still reports canary weight %s after %ss\n' "$(weight_of "$r")" "$READY_TIMEOUT" >&2
exit 1
