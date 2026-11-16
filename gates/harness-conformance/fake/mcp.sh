#!/bin/sh
# fake-cli's mcp.sh (docs/adr/0073 §8's contract): decl.json in, its own
# configuration (fake-mcp.json: each server's command and cwd, the workspace) and
# the allow file out. `mcp-own-cwd` leaves the cwd out: the server starts where
# fake-cli runs.
set -eu
decl=$1
outdir=$2
mkdir -p "$outdir"
jq --arg cwd "$3" --arg defect "${FAKE_DEFECT:-}" \
  '{servers: [.servers[] | {name, command} + (if $defect == "mcp-own-cwd" then {} else {cwd: $cwd} end)]}' \
  "$decl" > "$outdir/fake-mcp.json" || { echo "harness-fake-cli: $decl is not a declaration" >&2; exit 1; }
jq -r '.servers[] | .name as $s | .tools[] | "mcp__\($s)__\(.) \($s) \(.)"' "$decl" > "$outdir/allow"
