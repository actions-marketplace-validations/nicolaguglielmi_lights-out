#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# shift-envoy-canary: moves <percent> of traffic to canary through the
# Envoy admin API, verified by reading the runtime layer back
# (docs/adr/0013 §3). Not a gate: no GO/NO-GO, one stderr line and exit 1
# if the admin API did not take the change.
set -eu
percent=${1:?usage: shift.sh <canary-percent>}
: "${PLANE_HOST:=host.containers.internal}"
: "${ENVOY_ADMIN_URL:=http://$PLANE_HOST:9901}"

stable=$((100 - percent))

curl -fsS --connect-timeout 1 --max-time 3 -X POST \
  "$ENVOY_ADMIN_URL/runtime_modify?weights.canary=$percent&weights.stable=$stable" >/dev/null

got=$(curl -fsS --connect-timeout 1 --max-time 3 "$ENVOY_ADMIN_URL/runtime" \
  | jq -r '.entries["weights.canary"].final_value // empty')
[ "$got" = "$percent" ] || {
  printf 'shift-envoy-canary: admin reports weights.canary=%s after asking for %s\n' "${got:-none}" "$percent" >&2
  exit 1
}
