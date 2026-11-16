#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-gitea: polls the API, not a gate (docs/adr/0012 §6): no GO/NO-GO,
# silent on success, one stderr line and exit 1 on timeout. No runner to
# wait for since docs/adr/0060 §5.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${READY_TIMEOUT:=60}"
: "${CODE_HOST_PORT:=3000}"
url="http://$PLANE_HOST:$CODE_HOST_PORT/api/v1/version"

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  if curl -fsS --connect-timeout 1 --max-time 3 "$url" >/dev/null 2>&1; then
    exit 0
  fi
  i=$((i + 1))
  sleep 1
done
# A busy port answers, but not as Gitea (docs/adr/0093 §1e): say so, with
# the port and what answered, so the person is not left with a timeout.
code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 1 --max-time 3 "$url" 2>/dev/null) || :
case "$code" in
  ''|000) why="nothing answers on port $CODE_HOST_PORT" ;;
  *) why="port $CODE_HOST_PORT answers HTTP $code, not as Gitea: another server holds it on this host (./go doctor names it; CODE_HOST_PORT in .env moves Gitea)" ;;
esac
printf 'ready: gitea not ready after %ss: GET %s: %s\n' "$READY_TIMEOUT" "$url" "$why" >&2
exit 1
