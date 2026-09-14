#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# query-prometheus: runs one instant PromQL query and prints the raw
# `/api/v1/query` JSON on stdout (docs/adr/0013 §4). managed-prometheus
# differs only by URL and auth, which is why this is behind the Metrics
# port and not called directly by verify/slo.sh. Not a gate.
set -eu
query=${1:?usage: query.sh '<promql>'}
: "${PLANE_HOST:=host.containers.internal}"
: "${PROMETHEUS_URL:=http://$PLANE_HOST:9090}"

curl -fsS --connect-timeout 1 --max-time 3 -G "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode "query=$query"
