#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-flagger: the plane readiness probe (docs/adr/0026 §1): Flagger has
# initialized the Canary (the primary exists and the router is its) and the
# app answers $APP_URL/healthz through the cluster's traffic router 10
# times in a row, a second apart (ADR 0013 §4's 10, ADR 0051's rule: one
# answer from a fresh router is not enough). Not a gate (docs/adr/0012
# §6): silent on success, one stderr line and exit 1 on timeout.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/flagger/env.sh
. "$here/env.sh"
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"

i=0
ok=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  phase=$(canary_json 2>/dev/null | jq -r '.status.phase // empty') || phase=""
  case "$phase" in
    ""|Initializing) ok=0 ;;
    *)
      if curl -fsS --connect-timeout 1 --max-time 3 "$APP_URL/healthz" >/dev/null 2>&1; then
        ok=$((ok + 1))
        [ "$ok" -lt 10 ] || exit 0
      else
        ok=0
      fi ;;
  esac
  i=$((i + 1))
  sleep 1
done
printf 'ready: flagger not ready after %ss: canary %s/%s is %s, GET %s/healthz\n' \
  "$READY_TIMEOUT" "$FLAGGER_NAMESPACE" "$FLAGGER_CANARY" "${phase:-absent}" "$APP_URL" >&2
exit 1
