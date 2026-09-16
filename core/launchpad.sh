#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-launchpad: the release controller (docs/adr/0013 §4, amended by
# docs/adr/0014 §1). Vendor-free: it only calls the DELIVERY and METRICS
# adapter scripts the profile names and the verify/slo.sh gate — no Envoy
# or Prometheus word appears below. Stages: rollback to a known state, read
# the stable version, check the freeze flag, staging, then 5% and 25%, each
# gated by verify/slo.sh. A NO-GO at any stage rolls back and exits 1. A
# full pass holds the canary at 25%, waiting for go-for-launch (core/
# promote.sh, docs/adr/0020 §4), and exits 0. Either way the decision and
# the numbers that produced it are written to RELEASE_RECORD, the file
# promote reads. Generates no traffic itself: production has real
# traffic, the Makefile `release` target starts app/load.sh beside this
# at L0.
#
# Not scanned by ci/contract.sh (core/, not ci/ gates/ verify/), but reuses
# ci/lib.sh's go/nogo for the same GO:/NO-GO: line shape.
set -eu
name=launchpad
. ci/lib.sh

: "${CANARY_VERSION:?CANARY_VERSION not set}"
: "${STAGE_SECONDS:=60}"
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"
: "${DELIVERY:?DELIVERY not set; run this via ./go, not directly}"
: "${METRICS:?METRICS not set; run this via ./go, not directly}"

: "${RELEASE_RECORD:=.crew/release.json}"

delivery="adapters/$DELIVERY"
metrics_query="adapters/$METRICS/query.sh"
export METRICS_QUERY="$metrics_query"

rollback() {
  sh "$delivery/rollback.sh"
}

# The release record (docs/adr/0020 §4): version, stable, one entry per
# verified stage with its verdict and the `slo:` lines behind it, and the
# outcome. Built up as stages pass; written on every exit path below.
stages='[]'
record() {
  # record VERDICT [HELD_AT]
  mkdir -p "$(dirname "$RELEASE_RECORD")"
  jq -n --arg v "$CANARY_VERSION" --arg s "${STABLE_VERSION:-}" --argjson stages "$stages" \
    --arg verdict "$1" --arg held "${2:-}" \
    '{version: $v, stable: $s, stages: $stages, verdict: $verdict,
      held_at: (if $held == "" then null else ($held | tonumber) end),
      image: "stable image, not built from merge.sha (M8)"}' > "$RELEASE_RECORD"
}

fail_stage() {
  # fail_stage STAGE REASON: rolls back, records, then NO-GOs with both in one line.
  rollback >&2
  record rolled-back
  nogo "$1: $2 → rolled back"
}

frozen() {
  freeze=$(curl -fsS --connect-timeout 1 --max-time 3 \
      -H 'Content-Type: application/json' -d '{"context":{}}' \
      "http://$PLANE_HOST:8016/ofrep/v1/evaluate/flags/release-freeze" \
    | jq -r .value 2>/dev/null) || freeze=false
  [ "$freeze" = "true" ]
}

# Known state before anything else: idempotent, safe even if a previous run
# was killed mid-flight.
rollback

stable_version=$(curl -fsS --connect-timeout 1 --max-time 3 "$APP_URL/healthz" | jq -r .version) \
  || nogo "could not read the stable version from $APP_URL/healthz; run ./go up"
export STABLE_VERSION="$stable_version"
export CANARY_VERSION

if frozen; then
  nogo "release-freeze is on"
fi

printf '[launchpad] staging: deploying %s (stable is %s)\n' "$CANARY_VERSION" "$stable_version" >&2
sh "$delivery/deploy.sh" "$CANARY_VERSION" >&2 || fail_stage staging "deploy did not become healthy"

for pct in 5 25; do
  if frozen; then
    fail_stage "$pct%" "release-freeze is on"
  fi

  sh "$delivery/shift.sh" "$pct" >&2 || fail_stage "$pct%" "shift did not take"

  sleep "$STAGE_SECONDS"

  # verify's stderr (the slo: lines) is kept for the record and passed on.
  slo_err=$(mktemp)
  slo_out=$(sh verify/slo.sh 2>"$slo_err") && slo_rc=0 || slo_rc=$?
  cat "$slo_err" >&2
  numbers=$(grep '^slo: ' "$slo_err" | jq -R . | jq -cs .)
  rm -f "$slo_err"
  stages=$(printf '%s' "$stages" | jq -c --argjson pct "$pct" --arg verdict "$slo_out" --argjson numbers "$numbers" \
    '. + [{pct: $pct, verdict: $verdict, numbers: $numbers}]')
  if [ "$slo_rc" -eq 0 ]; then
    printf '[launchpad] %s%%: GO\n' "$pct" >&2
  else
    reason=$(printf '%s' "$slo_out" | sed 's/^NO-GO: slo — //')
    fail_stage "$pct%" "$reason"
  fi
done

record held 25
printf '[launchpad] 25%%: GO — held; ./go promote runs go-for-launch (record at %s)\n' "$RELEASE_RECORD" >&2
go
