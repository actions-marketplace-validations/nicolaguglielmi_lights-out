#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# minimal-load: generates the traffic verify/slo.sh needs during a
# launchpad stage (docs/adr/0013 §4: the controller generates none itself).
# Loops GET /ping through Envoy: 200 where the outage flag is off, 501
# where it is targeted on for the requesting version — no state either
# way. Runs until killed; not a gate.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"

while true; do
  curl -s -o /dev/null --connect-timeout 1 --max-time 3 "$APP_URL/ping" || true
  sleep 0.2
done
