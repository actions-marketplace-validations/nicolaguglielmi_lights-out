#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# status-argo-rollouts: the Delivery port's state verb (docs/adr/0026 §2):
# exactly three keys, read from the cluster, never from RELEASE_RECORD.
# stable is what a pod of the Rollout's stableRS reports at /healthz;
# canary is what a pod of currentPodHash reports, or null when no canary
# is in flight or the Rollout is aborted (Argo has taken that revision out
# of the rollout, even while its pods drain); weight is the router's
# canary weight. Not a gate: exit 1 and one stderr line if a revision
# that should answer does not.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/argo-rollouts/env.sh
. "$here/env.sh"

r=$(rollout_json) \
  || { printf 'status-argo-rollouts: no rollout %s/%s\n' "$ARGO_NAMESPACE" "$ARGO_ROLLOUT" >&2; exit 1; }
stable_rs=$(printf '%s' "$r" | jq -r '.status.stableRS // empty')
canary_rs=$(printf '%s' "$r" | jq -r '.status.currentPodHash // empty')
aborted=$(printf '%s' "$r" | jq -r '.status.abort // false')

stable=$(version_of "$stable_rs") \
  || { printf 'status-argo-rollouts: the stable revision %s did not report a version\n' "${stable_rs:-(none)}" >&2; exit 1; }

if [ -n "$canary_rs" ] && [ "$canary_rs" != "$stable_rs" ] && [ "$aborted" = false ]; then
  canary=$(version_of "$canary_rs") \
    || { printf 'status-argo-rollouts: the canary revision %s is in flight but did not report a version\n' "$canary_rs" >&2; exit 1; }
  canary_json=$(printf '%s' "$canary" | jq -R .)
else
  canary_json=null
fi

jq -cn --arg s "$stable" --argjson c "$canary_json" --argjson w "$(weight_of "$r")" '{stable: $s, canary: $c, weight: $w}'
