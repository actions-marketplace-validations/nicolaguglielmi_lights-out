#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-firestore-emulator: polls the emulator's root page, not a gate
# (docs/adr/0012 §6): no GO/NO-GO, silent on success, one stderr line and
# exit 1 on timeout.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${READY_TIMEOUT:=60}"

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  if body=$(curl -fsS --connect-timeout 1 --max-time 3 "http://$PLANE_HOST:8086/" 2>/dev/null) \
      && [ "$body" = "Ok" ]
  then
    exit 0
  fi
  i=$((i + 1))
  sleep 1
done
printf 'ready: firestore-emulator not ready after %ss: GET http://%s:8086/\n' "$READY_TIMEOUT" "$PLANE_HOST" >&2
exit 1
