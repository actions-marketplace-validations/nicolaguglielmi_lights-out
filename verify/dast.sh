#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# verify-dast (docs/adr/0072 §3): ZAP's baseline scan, passive only, at the
# staging stage, before any traffic reaches the canary. core/launchpad.sh
# calls it after the Delivery port's deploy.sh and before the shift to 5%,
# when DAST=on. It scans the stable at APP_URL (weight 0 at staging) and the
# canary at the URL the Delivery adapter's optional canary-url.sh prints, a
# URL that reaches only the canary revision; an adapter without that verb
# is refused. ZAP runs as the plane's `zap` service (compose.yaml, profile
# dast, pinned by index digest), its report on stdout, its log on stderr.
#
# An alert is (plugin id, method, path without query), the host stripped;
# core/dastdiff.py compares the two reports. NO-GO only for a tuple the
# canary has and the stable does not, at any risk level: no severity floor
# (ADR 0015 §4). ZAP's own exit codes 1 and 2 (warnings, failures by its
# own rules) are ignored; exit 3, any other failure, or a report that
# cannot be read is `cannot judge`, which launchpad rolls back (ADR 0066).
#
# A URL on PLANE_HOST is handed to ZAP with the address this container
# resolves PLANE_HOST to: the scanner is another container, where the name
# need not resolve (docker gives the workbench host.containers.internal
# with --add-host; a compose service has no such entry), and the address
# does on both engines. The host is stripped from every alert anyway.
#
# The passive scanner runs on one thread (`pscans.threads=1`). On its
# default threads, ZAP 2.17 sometimes leaves out of the report an alert a
# rule raised while another thread raised alerts on the same page, so the
# same image scanned twice could differ by one tuple: a NO-GO for the
# stable against itself (ADR 0072, "The stable against itself").
set -eu
name=dast
. ci/lib.sh

[ -n "${CANARY_VERSION:-}" ] && [ -n "${STABLE_VERSION:-}" ] && [ -n "${APP_URL:-}" ] && [ -n "${DELIVERY:-}" ] \
  || nogo "CANARY_VERSION, STABLE_VERSION, APP_URL and DELIVERY must be set; run this via core/launchpad.sh"
[ -f "adapters/$DELIVERY/canary-url.sh" ] \
  || nogo "DELIVERY=$DELIVERY has no canary-url.sh, a URL that reaches only the canary; DAST=on needs one (docs/adr/0072 §3)"
canary_url=$(sh "adapters/$DELIVERY/canary-url.sh") && [ -n "$canary_url" ] \
  || nogo "cannot judge: adapters/$DELIVERY/canary-url.sh printed no URL"

# APP_URL is the stable alone only at weight 0, which the staging stage is.
weight=$(sh "adapters/$DELIVERY/status.sh" 2>/dev/null | jq -r '.weight') || weight=""
[ "$weight" = 0 ] || nogo "cannot judge: the canary's weight is ${weight:-unknown}, not 0, so APP_URL is not the stable alone"

: "${PLANE_HOST:=host.containers.internal}"
addr=$(getent ahostsv4 "$PLANE_HOST" 2>/dev/null | awk '{ print $1; exit }') || addr=""

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# scan SIDE URL: ZAP's JSON report on $tmp/SIDE.json, or a cannot-judge NO-GO.
scan() {
  url=$2
  [ -z "$addr" ] || url=$(printf '%s' "$url" | sed "s|//$PLANE_HOST:|//$addr:|; s|//$PLANE_HOST/|//$addr/|")
  t0=$(date +%s)
  # shellcheck disable=SC2016 # $0 is the inner shell's: the URL
  docker-compose --profile dast run --rm -T zap sh -c \
    'zap-baseline.py -t "$0" -J report.json -I -z "-config pscans.threads=1" >&2; rc=$?; cat /zap/wrk/report.json 2>/dev/null; exit $rc' "$url" \
    > "$tmp/$1.json" </dev/null && rc=0 || rc=$?
  printf 'dast: %s scan of %s: zap exited %s in %ss\n' "$1" "$url" "$rc" "$(($(date +%s) - t0))" >&2
  case "$rc" in
    0|1|2) ;;
    *) nogo "cannot judge: the $1 scan failed, ZAP exited $rc; see stderr" ;;
  esac
}

scan stable "$APP_URL"
scan canary "$canary_url"

verdict=$(python3 core/dastdiff.py diff "$tmp/stable.json" "$tmp/canary.json") && rc=0 || rc=$?
case "$rc" in
  0) go_with "canary $CANARY_VERSION: nothing new ($verdict inherited from $STABLE_VERSION)" ;;
  1) nogo "canary $CANARY_VERSION raises $verdict alert(s) stable $STABLE_VERSION does not; list on stderr" ;;
  *) nogo "cannot judge: $verdict" ;;
esac
