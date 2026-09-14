#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-zot: polls the OCI Distribution API root, not a gate (docs/adr/0012
# §6): no GO/NO-GO, silent on success, one stderr line and exit 1 on timeout.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${READY_TIMEOUT:=60}"

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  curl -fsS --connect-timeout 1 --max-time 3 "http://$PLANE_HOST:5050/v2/" >/dev/null 2>&1 && exit 0
  i=$((i + 1))
  sleep 1
done
printf 'ready: zot not ready after %ss: GET http://%s:5050/v2/\n' "$READY_TIMEOUT" "$PLANE_HOST" >&2
exit 1
