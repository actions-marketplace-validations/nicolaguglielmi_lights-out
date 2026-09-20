#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# evaluate-flagd: prints <flag>'s OFREP value for the optional [version]
# context (docs/adr/0026 §3 — the port launchpad's frozen() and the
# conformance suite's preflight go through, instead of curling flagd's
# port directly). Not a gate (docs/adr/0012 §6): the flag's raw value on
# stdout (e.g. true/false), one stderr line and exit 1 if flagd cannot be
# reached or the response has no value — never a silent default; a
# caller that wants "unreachable means X" decides that itself.
set -eu
flag=${1:?usage: evaluate.sh <flag> [version]}
version=${2:-}
: "${PLANE_HOST:=host.containers.internal}"

if [ -n "$version" ]; then
  ctx=$(jq -cn --arg v "$version" '{context: {version: $v}}')
else
  ctx='{"context":{}}'
fi

value=$(curl -fsS --connect-timeout 1 --max-time 3 \
    -H 'Content-Type: application/json' -d "$ctx" \
    "http://$PLANE_HOST:8016/ofrep/v1/evaluate/flags/$flag" 2>/dev/null \
  | jq -r 'if has("value") then .value else empty end')
[ -n "$value" ] || { printf 'evaluate-flagd: no value for %s from http://%s:8016\n' "$flag" "$PLANE_HOST" >&2; exit 1; }
printf '%s\n' "$value"
