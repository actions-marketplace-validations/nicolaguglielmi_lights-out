#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-argo-rollouts: the plane readiness probe (docs/adr/0026 §1): the
# Rollout is Healthy or Paused and the app answers $APP_URL/healthz
# through the cluster's traffic router 10 times in a row, a second apart
# (ADR 0013 §4's 10). One answer is not enough: a router still taking in
# a fresh Rollout's Services answered once, then failed the load's login
# a second later (found 2026-11-06, case 1). Not a gate (docs/adr/0012
# §6): silent on success, one stderr line and exit 1 on timeout.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/argo-rollouts/env.sh
. "$here/env.sh"
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"

i=0
ok=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  phase=$(rollout_json 2>/dev/null | jq -r '.status.phase // empty') || phase=""
  case "$phase" in
    Healthy|Paused)
      if curl -fsS --connect-timeout 1 --max-time 3 "$APP_URL/healthz" >/dev/null 2>&1; then
        ok=$((ok + 1))
        [ "$ok" -lt 10 ] || exit 0
      else
        ok=0
      fi ;;
    *) ok=0 ;;
  esac
  i=$((i + 1))
  sleep 1
done
printf 'ready: argo-rollouts not ready after %ss: rollout %s/%s is %s, GET %s/healthz\n' \
  "$READY_TIMEOUT" "$ARGO_NAMESPACE" "$ARGO_ROLLOUT" "${phase:-absent}" "$APP_URL" >&2
exit 1
