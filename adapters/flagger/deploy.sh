#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# deploy-flagger: stages <image> as the Canary's new revision, reporting
# <version>, at weight 0 (docs/adr/0095 §3). Closes the stage gate and the
# rollback flag first, so nothing left open by a previous run moves the new
# canary. Then patches the target Deployment: the first container's image,
# the pod-template annotation lights-out.dev/version (the workload maps it
# to its version through the downward API), and lights-out.dev/deploy, a
# stamp per deploy: Flagger starts no analysis for a template whose hash it
# has already recorded, and a Failed canary records its own every tick
# (pkg/canary/spec.go, hasSpecChanged, v1.45.0), so the same version
# deployed again after a rollback must still be a new template. Waits until
# Flagger is Progressing at weight 0 with a canary pod answering /healthz
# with <version>. <image> is a bare repo@digest (docs/adr/0025 §1),
# prefixed with FLAGGER_REGISTRY_HOST. Not a gate: one stderr line and
# exit 1 on timeout.
set -eu
version=${1:?usage: deploy.sh <version> <image>}
image=${2:?usage: deploy.sh <version> <image>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/flagger/env.sh
. "$here/env.sh"
: "${FLAGGER_REGISTRY_HOST:=localhost:5050}"

tester /gate/close
tester /rollback/close

annotations=$(k get deployment "$FLAGGER_CANARY" -o json \
  | jq -c --arg v "$version" --arg d "$(date +%s)" \
      '(.spec.template.metadata.annotations // {}) + {"lights-out.dev/version": $v, "lights-out.dev/deploy": $d}')
patch=$(jq -cn --arg i "$FLAGGER_REGISTRY_HOST/$image" --argjson a "$annotations" '[
  {op: "replace", path: "/spec/template/spec/containers/0/image", value: $i},
  {op: "add", path: "/spec/template/metadata/annotations", value: $a}
]')
k patch deployment "$FLAGGER_CANARY" --type json -p "$patch" >/dev/null

# Flagger notices on its next tick, scales the canary up and restarts the
# analysis at weight 0; the closed gate holds it there.
i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  c=$(canary_json) || c='{}'
  phase=$(field "$c" '.status.phase // ""')
  weight=$(field "$c" '.status.canaryWeight // 0')
  if [ "$phase" = Progressing ] && [ "$weight" = 0 ]; then
    got=$(version_of "$FLAGGER_CANARY") || got=""
    [ "$got" = "$version" ] && exit 0
  fi
  i=$((i + 1))
  sleep 1
done
printf 'deploy-flagger: canary reports %s after %ss, want %s (canary %s/%s: %s at weight %s)\n' \
  "${got:-no answer}" "$READY_TIMEOUT" "$version" "$FLAGGER_NAMESPACE" "$FLAGGER_CANARY" "${phase:-no phase}" "${weight:-?}" >&2
exit 1
