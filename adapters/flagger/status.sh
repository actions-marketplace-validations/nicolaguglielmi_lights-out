#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# status-flagger: the Delivery port's state verb (docs/adr/0026 §2):
# exactly three keys, read from the cluster, never from RELEASE_RECORD.
# stable is what a pod of the primary (<target>-primary) reports at
# /healthz; canary is what a pod of the target Deployment reports while
# Flagger has it in flight (Progressing, WaitingPromotion, Promoting,
# Finalising), else null; weight is the Canary's status.canaryWeight, the
# weight Flagger last gave the router (docs/adr/0095 §3). Not a gate: exit
# 1 and one stderr line if a revision that should answer does not.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/flagger/env.sh
. "$here/env.sh"

c=$(canary_json) \
  || { printf 'status-flagger: no canary %s/%s\n' "$FLAGGER_NAMESPACE" "$FLAGGER_CANARY" >&2; exit 1; }
phase=$(field "$c" '.status.phase // ""')
weight=$(field "$c" '.status.canaryWeight // 0')

stable=$(version_of "$FLAGGER_CANARY-primary") \
  || { printf 'status-flagger: the primary %s-primary did not report a version\n' "$FLAGGER_CANARY" >&2; exit 1; }

if in_flight "$phase"; then
  canary=$(version_of "$FLAGGER_CANARY") \
    || { printf 'status-flagger: the canary is %s but no pod of %s reported a version\n' "$phase" "$FLAGGER_CANARY" >&2; exit 1; }
  canary_json=$(printf '%s' "$canary" | jq -R .)
else
  canary_json=null
fi

jq -cn --arg s "$stable" --argjson c "$canary_json" --argjson w "$weight" '{stable: $s, canary: $c, weight: $w}'
