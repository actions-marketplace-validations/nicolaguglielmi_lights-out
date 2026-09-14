#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-envoy-canary: polls the app's health endpoint through Envoy, not a
# gate (docs/adr/0012 §6): no GO/NO-GO, silent on success, one stderr line
# and exit 1 on timeout.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"
: "${READY_TIMEOUT:=60}"

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  curl -fsS --connect-timeout 1 --max-time 3 "$APP_URL/healthz" >/dev/null 2>&1 && exit 0
  i=$((i + 1))
  sleep 1
done
printf 'ready: envoy-canary not ready after %ss: GET %s/healthz\n' "$READY_TIMEOUT" "$APP_URL" >&2
exit 1
