#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-egress: gives the `egress` proxy a harness's allowlist and returns
# once that proxy is listening (docs/adr/0046 §2, §4). Called by each CLI
# harness's run.sh, after its own refusals and before `docker-compose run`:
#
#   sh core/egress.sh "<name:port> ..."     the adapter's EGRESS
#
# The list it writes to .crew/egress/allow is, in order:
#   - the adapter's EGRESS, or, when MODEL_BASE_URL is set (the conformance
#     seam, docs/adr/0041 §7), that URL's host:port instead;
#   - the lines of $WORKLOAD_CONTRACT/crew-egress.txt, if the workload's
#     contract has one (§5): the package indexes it names, nothing by default.
# The proxy re-reads the file on every connection, so a harness switch never
# recreates the service; `up -d` only starts it, or keeps the running one.
# It is never stopped here: parallel network members share it (ADR 0036).
# Names no provider (ci/vendor-free.sh): the hosts come from the caller.
#
# Adapter convention (docs/adr/0012 §6): silent on success, one stderr line
# and exit 1 on failure.
set -eu

fail() { printf 'egress: %s\n' "$*" >&2; exit 1; }

hosts=${1:-}
if [ -n "${MODEL_BASE_URL:-}" ]; then
  rest=${MODEL_BASE_URL#*://}
  scheme=${MODEL_BASE_URL%%://*}
  authority=${rest%%/*}
  case "$authority" in
    *:*) hosts=$authority ;;
    *) [ "$scheme" = https ] && hosts=$authority:443 || hosts=$authority:80 ;;
  esac
fi
if [ -n "${WORKLOAD_CONTRACT:-}" ] && [ -f "$WORKLOAD_CONTRACT/crew-egress.txt" ]; then
  hosts="$hosts $(grep -v '^[[:space:]]*#' "$WORKLOAD_CONTRACT/crew-egress.txt" | tr -s ' \t\n' ' ')"
fi

list=""
for h in $hosts; do
  case "$h" in
    *[!a-z0-9.:-]*|:*|*:|*:*:*) fail "'$h' is not a lowercase name:port (docs/adr/0046 §4)" ;;
    *:*) ;;
    *) fail "'$h' has no port (docs/adr/0046 §4)" ;;
  esac
  list="$list$h
"
done
[ -n "$list" ] || fail "no host to allow: the adapter's EGRESS is empty (docs/adr/0046 §4)"

dir=.crew/egress
mkdir -p "$dir"
printf '%s' "$list" > "$dir/allow.tmp"
mv "$dir/allow.tmp" "$dir/allow"

# Two parallel members can race on the container's creation: one retry.
docker-compose --profile crew up -d egress >&2 2>&1 \
  || docker-compose --profile crew up -d egress >&2 2>&1 \
  || fail "could not start the egress proxy (docker-compose --profile crew up -d egress)"

# Ready means this container wrote its own hostname, never an earlier one's
# file. 30 s: decision (the proxy binds in well under a second; the rest is
# a slow engine's start).
waited=0
while :; do
  cid=$(docker-compose --profile crew ps -q egress 2>/dev/null | head -n 1 | cut -c1-12)
  ready=$(cat "$dir/ready" 2>/dev/null || true)
  [ -n "$cid" ] && [ "$cid" = "$ready" ] && exit 0
  waited=$((waited + 1))
  [ "$waited" -le 30 ] || fail "the egress proxy did not report ready within 30 s (container ${cid:-none}, ready file ${ready:-none})"
  sleep 1
done
