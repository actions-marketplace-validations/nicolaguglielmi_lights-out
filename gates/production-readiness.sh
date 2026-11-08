#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-production-readiness: docs/adr/0057 §10, `./go production-readiness`.
# Whether this setup may take real traffic. GO only when all four hold;
# otherwise one NO-GO naming every item that fails, details on stderr:
#
#   delivery    DELIVERY's adapter has a rollback.sh, and a conformance
#               record (docs/adr/0057 §9, written by
#               gates/delivery-conformance.sh on GO) whose HASH is the
#               adapter's hash today: changed since it passed is not passed
#   metrics     METRICS=promql with METRICS_URL set, and that endpoint
#               answers count(target_info) with at least one sample; the
#               plane's own prometheus scrapes the demo app, not yours
#   secrets     .env holds no value, other than empty or replace-me, for a
#               key ending in _KEY, _TOKEN, _SECRET or _PASSWORD, or for
#               METRICS_AUTH_HEADER: production takes them from its
#               environment, where a secret manager puts them
#   human gate  GO_FOR_LAUNCH is not preset (a preset answer is silence
#               that promotes), and the console names who presses:
#               CONSOLE_AUTH=proxy, CONSOLE_IDENTITY_HEADER and a non-empty
#               CONSOLE_LAUNCHERS (docs/adr/0047)
#
# At L0 it is NO-GO by construction. Not one of the eight PR gates, never
# run by `gates`. READINESS_ENV_FILE (default .env) and CONFORMANCE_DIR
# (default .crew/conformance) let ci/production-readiness.sh judge
# constructed cases.
set -eu
name=production-readiness
. ci/lib.sh

envfile=${READINESS_ENV_FILE:-.env}
records=${CONFORMANCE_DIR:-.crew/conformance}
failed=""
said=""
miss() { failed="$failed${failed:+, }$1 ($2)"; printf 'production-readiness: %-10s FAIL, %s\n' "$1" "$2" >&2; }
ok() { said="$said${said:+, }$2"; printf 'production-readiness: %-10s ok, %s\n' "$1" "$2" >&2; }
envval() { [ -f "$envfile" ] && sed -n "s/^$1=//p" "$envfile" | tail -1; }

# delivery
d=${DELIVERY:-}
if [ -z "$d" ]; then
  miss delivery "DELIVERY is not set"
elif [ ! -f "adapters/$d/rollback.sh" ]; then
  miss delivery "DELIVERY=$d has no adapters/$d/rollback.sh, so no rollback"
elif [ ! -f "$records/delivery-$d.env" ]; then
  miss delivery "$d has no conformance record in $records/: its suite has not passed here"
elif [ "$(sed -n 's/^HASH=//p' "$records/delivery-$d.env")" != "$(adapter_hash "adapters/$d")" ]; then
  miss delivery "adapters/$d changed since its conformance passed at $(sed -n 's/^AT=//p' "$records/delivery-$d.env"); run its suite again"
else
  ok delivery "delivery $d, conformance passed $(sed -n 's/^AT=//p' "$records/delivery-$d.env")"
fi

# metrics
if [ "${METRICS:-}" != promql ]; then
  miss metrics "METRICS=${METRICS:-} is not promql on an endpoint you name"
elif [ -z "${METRICS_URL:-}" ]; then
  miss metrics "METRICS_URL is not set"
else
  answer=$(sh adapters/promql/query.sh 'count(target_info)' 2>/dev/null) || answer=""
  n=$(printf '%s' "$answer" | jq -r '[.data.result[]?.value[1] | tonumber] | add // 0' 2>/dev/null) || n=0
  case "$n" in ''|*[!0-9]*) n=0 ;; esac
  if [ "$n" -gt 0 ]; then
    ok metrics "metrics from METRICS_URL, $n target_info series"
  else
    miss metrics "METRICS_URL answers no target_info series, or does not answer"
  fi
fi

# secrets
leaked=""
if [ -f "$envfile" ]; then
  leaked=$(grep -E '^[A-Za-z0-9_]*(_KEY|_TOKEN|_SECRET|_PASSWORD)=|^METRICS_AUTH_HEADER=' "$envfile" \
    | while IFS= read -r l; do v=${l#*=}; [ -z "$v" ] || [ "$v" = replace-me ] || printf '%s ' "${l%%=*}"; done)
fi
if [ -n "$leaked" ]; then
  miss secrets "$envfile holds ${leaked% }; take them from the environment"
else
  ok secrets "no secrets in $envfile"
fi

# human gate
launchers=${CONSOLE_LAUNCHERS:-}
if [ -n "${GO_FOR_LAUNCH:-}" ] || [ -n "$(envval GO_FOR_LAUNCH)" ]; then
  miss "human gate" "GO_FOR_LAUNCH is preset, so no person answers"
elif [ "${CONSOLE_AUTH:-loopback}" != proxy ]; then
  miss "human gate" "CONSOLE_AUTH=${CONSOLE_AUTH:-loopback}, not proxy: nobody named presses"
elif [ -z "${CONSOLE_IDENTITY_HEADER:-}" ]; then
  miss "human gate" "CONSOLE_AUTH=proxy without CONSOLE_IDENTITY_HEADER"
elif [ -z "$(printf '%s' "$launchers" | tr -d ' ,')" ]; then
  miss "human gate" "CONSOLE_LAUNCHERS names nobody"
else
  ok "human gate" "launchers $launchers"
fi

[ -z "$failed" ] || nogo "$failed"
go_with "$said"
