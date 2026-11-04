#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# query-promql: runs one instant PromQL query against METRICS_URL, any
# Prometheus-compatible endpoint, and prints the raw `/api/v1/query` JSON
# on stdout (docs/adr/0044 §8). The Metrics port's general case; the
# plane's `prometheus` adapter calls it with its own URL. METRICS_URL is
# the base `/api/v1/query` is appended to. METRICS_AUTH_HEADER, when set,
# is one header line ("Authorization: Bearer …") handed to curl on stdin,
# never in argv and never printed. Not a gate.
set -eu
query=${1:?usage: query.sh '<promql>'}
[ -n "${METRICS_URL:-}" ] || { printf 'query-promql: METRICS_URL is not set; point it at a Prometheus-compatible endpoint (docs/adr/0044)\n' >&2; exit 1; }

if [ -n "${METRICS_AUTH_HEADER:-}" ]; then
  printf '%s\n' "$METRICS_AUTH_HEADER" | curl -fsS --connect-timeout 1 --max-time 3 -H @- \
    -G "$METRICS_URL/api/v1/query" --data-urlencode "query=$query"
else
  curl -fsS --connect-timeout 1 --max-time 3 -G "$METRICS_URL/api/v1/query" \
    --data-urlencode "query=$query"
fi
