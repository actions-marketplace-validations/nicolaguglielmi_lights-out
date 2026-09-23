#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# minimal-smoke: exit 0 when the happy path answers through Envoy
# (docs/adr/0030 §3). Not a gate: no GO/NO-GO, no engine socket needed.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

if ! code=$(curl -sS -o "$tmp/ping.json" -w '%{http_code}' --connect-timeout 1 --max-time 3 \
    "$APP_URL/ping" 2>"$tmp/ping.err")
then
  printf 'smoke: ping failed: %s\n' "$(cat "$tmp/ping.err")" >&2
  exit 1
fi
[ "$code" = "200" ] || { printf 'smoke: ping answered %s, want 200: %s\n' "$code" "$(cat "$tmp/ping.json")" >&2; exit 1; }

printf 'smoke: ping answered 200 through Envoy at %s\n' "$APP_URL" >&2
