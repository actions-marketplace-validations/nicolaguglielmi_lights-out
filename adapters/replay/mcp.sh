#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-replay mcp (docs/adr/0073 §8): replay translates nothing, since no
# server runs when a recorded run is replayed. It checks that the recording
# was made under the same declaration: decl.json's sha256 against the
# fixture's run.json `.mcp.sha256` (both absent counts as equal), and
# refuses when they differ, naming both: the instruction-sha precedent of
# lights_out_adk/replay.py. On a match it writes an empty OUTDIR/allow.
# The fixture's run.json is FIXTURE_RUN_JSON when set (run.sh sets it),
# else derived as adapters/replay/run.sh derives its fixture, from TICKET,
# ROLE and ATTEMPT. Adapter convention (docs/adr/0012 §6): silent on
# success, one stderr line and exit 1 on failure.
#
#   sh adapters/replay/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER
set -eu
decl=${1:?usage: sh adapters/replay/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}
outdir=${2:?usage: sh adapters/replay/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}

fail() { printf 'harness-replay: %s\n' "$1" >&2; exit 1; }

if [ -n "${FIXTURE_RUN_JSON:-}" ]; then
  recorded=$FIXTURE_RUN_JSON
else
  : "${ROLE:?ROLE not set (or set FIXTURE_RUN_JSON)}"
  : "${TICKET:?TICKET not set (or set FIXTURE_RUN_JSON)}"
  # shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
  root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
  rel="$TICKET/$ROLE"
  [ "${ATTEMPT:-1}" -le 1 ] || rel="$rel/attempt-$ATTEMPT"
  recorded="$root/fixtures/$rel/run.json"
fi

want=none
if [ -f "$decl" ]; then
  want=$(jq -r '.sha256 // "none"' "$decl" 2>/dev/null) || fail "$decl is not JSON"
fi
got=none
if [ -f "$recorded" ]; then
  got=$(jq -r '.mcp.sha256 // "none"' "$recorded" 2>/dev/null) || fail "$recorded is not JSON"
fi
[ "$want" = "$got" ] \
  || fail "mcp.json's declaration $want is not the one the recording was made under, $got ($recorded .mcp.sha256); record the run again (ADR 0073 §8)"

mkdir -p "$outdir" || fail "cannot create $outdir"
: > "$outdir/allow"
