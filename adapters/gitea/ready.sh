#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-gitea: polls the API, not a gate (docs/adr/0012 §6): no GO/NO-GO,
# silent on success, one stderr line and exit 1 on timeout. No runner to
# wait for since docs/adr/0060 §5.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${READY_TIMEOUT:=60}"

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  if curl -fsS --connect-timeout 1 --max-time 3 "http://$PLANE_HOST:3000/api/v1/version" >/dev/null 2>&1; then
    exit 0
  fi
  i=$((i + 1))
  sleep 1
done
printf 'ready: gitea not ready after %ss: GET http://%s:3000/api/v1/version\n' "$READY_TIMEOUT" "$PLANE_HOST" >&2
exit 1
