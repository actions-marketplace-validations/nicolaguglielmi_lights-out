#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-gitea: polls the API and the runner's registration file, not a gate
# (docs/adr/0012 §6): no GO/NO-GO, silent on success, one stderr line and
# exit 1 on timeout. Run from the repo root, same cwd as the compose project.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${READY_TIMEOUT:=60}"

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  if curl -fsS --connect-timeout 1 --max-time 3 "http://$PLANE_HOST:3000/api/v1/version" >/dev/null 2>&1 \
      && docker-compose exec -T runner test -f /data/.runner >/dev/null 2>&1
  then
    exit 0
  fi
  i=$((i + 1))
  sleep 1
done
printf 'ready: gitea not ready after %ss: GET http://%s:3000/api/v1/version and docker-compose exec -T runner test -f /data/.runner\n' "$READY_TIMEOUT" "$PLANE_HOST" >&2
exit 1
