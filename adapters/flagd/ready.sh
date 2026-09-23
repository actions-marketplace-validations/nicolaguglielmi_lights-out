#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-flagd: polls the OFREP evaluate endpoint for the release-freeze
# flag, not a gate (docs/adr/0012 §6): no GO/NO-GO, silent on success, one
# stderr line and exit 1 on timeout. Polls `release-freeze`, not a
# workload's own kill-switch flag (docs/adr/0013 §6): release-freeze is
# the one flag the Workload port fixes for every workload (docs/adr/0030
# §3), so this adapter never names a workload or one of its flags. Any
# answered value counts as ready — the flag defaults off, but a
# differently-configured plane must not hang waiting for a specific value
# flagd was never going to serve.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${READY_TIMEOUT:=60}"

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  if curl -fsS --connect-timeout 1 --max-time 3 \
      -H 'Content-Type: application/json' -d '{"context":{}}' \
      "http://$PLANE_HOST:8016/ofrep/v1/evaluate/flags/release-freeze" 2>/dev/null | grep -q '"value":'
  then
    exit 0
  fi
  i=$((i + 1))
  sleep 1
done
printf 'ready: flagd not ready after %ss: POST http://%s:8016/ofrep/v1/evaluate/flags/release-freeze\n' "$READY_TIMEOUT" "$PLANE_HOST" >&2
exit 1
