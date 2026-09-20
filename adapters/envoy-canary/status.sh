#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# status-envoy-canary: the Delivery port's state verb (docs/adr/0026 §2):
# one JSON object, exactly three keys — stable, canary (string or null),
# weight (0-100) — read from the plane itself, not from RELEASE_RECORD,
# so a divergence between what launchpad decided and what is actually
# running is detectable. Not a gate (docs/adr/0012 §6): exit 1 and one
# stderr line if a revision that should answer does not.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${ENVOY_ADMIN_URL:=http://$PLANE_HOST:9901}"

# read_version SERVICE: the version SERVICE reports at its own
# localhost:8000/healthz, bypassing Envoy — the mechanism deploy.sh
# already uses to confirm a canary is really up (docs/adr/0013 §4).
read_version() {
  docker-compose exec -T "$1" python3 -c '
import json, sys, urllib.request
try:
    with urllib.request.urlopen("http://localhost:8000/healthz", timeout=2) as r:
        print(json.load(r)["version"])
except Exception:
    sys.exit(1)
' 2>/dev/null
}

stable=$(read_version backend) \
  || { printf 'status-envoy-canary: backend did not report a version\n' >&2; exit 1; }

if [ -n "$(docker-compose ps -q backend-canary 2>/dev/null)" ]; then
  canary=$(read_version backend-canary) \
    || { printf 'status-envoy-canary: backend-canary is running but did not report a version\n' >&2; exit 1; }
  canary_json=$(printf '%s' "$canary" | jq -R .)
else
  canary_json=null
fi

weight=$(curl -fsS --connect-timeout 1 --max-time 3 "$ENVOY_ADMIN_URL/runtime" \
    | jq -r '.entries["weights.canary"].final_value // 0') \
  || { printf 'status-envoy-canary: could not read %s/runtime\n' "$ENVOY_ADMIN_URL" >&2; exit 1; }

jq -cn --arg s "$stable" --argjson c "$canary_json" --argjson w "$weight" '{stable: $s, canary: $c, weight: $w}'
