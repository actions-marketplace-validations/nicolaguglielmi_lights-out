#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# query-prometheus: the plane's Metrics adapter is the promql adapter
# pointed at the plane's own Prometheus (docs/adr/0044 §8; before it, this
# was the whole query, docs/adr/0013 §4). It ignores an ambient
# METRICS_URL and METRICS_AUTH_HEADER, so a user's .env never moves the
# canary's judge. Not a gate.
set -eu
query=${1:?usage: query.sh '<promql>'}
: "${PLANE_HOST:=host.containers.internal}"
: "${PROMETHEUS_URL:=http://$PLANE_HOST:9090}"
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

exec env -u METRICS_AUTH_HEADER METRICS_URL="$PROMETHEUS_URL" sh "$here/../promql/query.sh" "$query"
