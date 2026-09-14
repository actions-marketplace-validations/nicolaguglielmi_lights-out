#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# deploy-envoy-canary: starts backend-canary at the given version and waits
# until it answers directly, not through Envoy, with that exact version
# (docs/adr/0013 §4). No `--build`: backend-canary shares the `backend`
# image tag, already built by `./go up`. Not a gate: no GO/NO-GO, one
# stderr line and exit 1 on timeout.
set -eu
version=${1:?usage: deploy.sh <version>}
: "${READY_TIMEOUT:=60}"

CANARY_VERSION="$version" docker-compose --profile canary up -d backend-canary >&2

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  got=$(docker-compose exec -T backend-canary python3 -c '
import json
import sys
import urllib.request

try:
    with urllib.request.urlopen("http://localhost:8000/healthz", timeout=2) as r:
        print(json.load(r)["version"])
except Exception:
    sys.exit(1)
' 2>/dev/null) || got=""
  [ "$got" = "$version" ] && exit 0
  i=$((i + 1))
  sleep 1
done
printf 'deploy-envoy-canary: backend-canary reports %s after %ss, want %s\n' "${got:-no answer}" "$READY_TIMEOUT" "$version" >&2
exit 1
