#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# rollback-envoy-canary: all traffic back to stable through the Envoy admin
# API (docs/adr/0013 §3). Idempotent — safe to call before any deploy has
# happened, and safe to call twice. The canary container, if any, is left
# running at weight 0, same as a Cloud Run revision after a rollback; the
# next deploy.sh recreates it. Not a gate.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${ENVOY_ADMIN_URL:=http://$PLANE_HOST:9901}"

curl -fsS --connect-timeout 1 --max-time 3 -X POST \
  "$ENVOY_ADMIN_URL/runtime_modify?weights.canary=0&weights.stable=100" >/dev/null
