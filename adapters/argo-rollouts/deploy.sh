#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# deploy-argo-rollouts: stages <image> as the Rollout's canary revision,
# reporting <version>, at weight 0 (docs/adr/0051 §3). One JSON patch sets
# the first container's image and the pod-template annotation
# lights-out.dev/version, which a workload that serves several versions
# from one image maps to its version through the downward API. A Rollout
# left aborted by the previous release with this same template does not
# start again on its own: the patch changes nothing, so the abort is
# cleared (the plugin's `retry`). Then waits until the Rollout is paused
# on its first step's pause with a canary pod answering /healthz with
# <version>. <image> is a bare repo@digest (docs/adr/0025 §1), prefixed
# with ARGO_REGISTRY_HOST as envoy-canary prefixes localhost:5050. Not a
# gate: one stderr line and exit 1 on timeout.
set -eu
version=${1:?usage: deploy.sh <version> <image>}
image=${2:?usage: deploy.sh <version> <image>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/argo-rollouts/env.sh
. "$here/env.sh"
: "${ARGO_REGISTRY_HOST:=localhost:5050}"

# Annotations the template already has are kept: the add replaces the map.
annotations=$(rollout_json | jq -c --arg v "$version" '(.spec.template.metadata.annotations // {}) + {"lights-out.dev/version": $v}')
patch=$(jq -cn --arg i "$ARGO_REGISTRY_HOST/$image" --argjson a "$annotations" '[
  {op: "replace", path: "/spec/template/spec/containers/0/image", value: $i},
  {op: "add", path: "/spec/template/metadata/annotations", value: $a}
]')
k patch rollout "$ARGO_ROLLOUT" --type json -p "$patch" >/dev/null

if [ "$(rollout_json | jq -r '.status.abort // false')" = true ]; then
  status_patch '{"status":{"abort":false}}'
fi

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  r=$(rollout_json) || r='{}'
  stable=$(printf '%s' "$r" | jq -r '.status.stableRS // empty')
  canary=$(printf '%s' "$r" | jq -r '.status.currentPodHash // empty')
  paused=$(printf '%s' "$r" | jq -r '(.status.pauseConditions // []) | length')
  if [ -n "$canary" ] && [ "$canary" != "$stable" ] && [ "$paused" -gt 0 ]; then
    got=$(version_of "$canary") || got=""
    [ "$got" = "$version" ] && exit 0
  fi
  i=$((i + 1))
  sleep 1
done
printf 'deploy-argo-rollouts: canary reports %s after %ss, want %s (rollout %s/%s: %s)\n' \
  "${got:-no answer}" "$READY_TIMEOUT" "$version" "$ARGO_NAMESPACE" "$ARGO_ROLLOUT" \
  "$(printf '%s' "$r" | jq -r '"\(.status.phase // "?"): \(.status.message // "")"')" >&2
exit 1
