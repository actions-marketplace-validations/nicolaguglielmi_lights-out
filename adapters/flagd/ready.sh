#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-flagd: polls the OFREP evaluate endpoint for the waitlist flag, not
# a gate (docs/adr/0012 §6): no GO/NO-GO, silent on success, one stderr line
# and exit 1 on timeout.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${READY_TIMEOUT:=60}"

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  if curl -fsS --connect-timeout 1 --max-time 3 \
      -H 'Content-Type: application/json' -d '{"context":{}}' \
      "http://$PLANE_HOST:8016/ofrep/v1/evaluate/flags/waitlist" 2>/dev/null | grep -q '"value":false'
  then
    exit 0
  fi
  i=$((i + 1))
  sleep 1
done
printf 'ready: flagd not ready after %ss: POST http://%s:8016/ofrep/v1/evaluate/flags/waitlist\n' "$READY_TIMEOUT" "$PLANE_HOST" >&2
exit 1
