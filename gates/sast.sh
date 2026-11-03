#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-sast: docs/adr/0015 §4. Static analysis over the workload's shipped
# code by the workload's own SAST_CMD (docs/adr/0042 §1), run where its
# TOOLCHAIN_IMAGE says (core/toolchain.sh): one JSON line {"findings": N}
# on stdout, its report on stderr, non-zero only if the tool itself failed
# (docs/adr/0030 §3's runner contract, unchanged). For the bundled app the
# command is still `sh tests/sast/run.sh` (bandit) in the compose service
# backend-test. Any finding is a NO-GO: a severity floor would be a number
# with no provenance.
#
# require_range runs first and its result is otherwise unused: the runner
# scans the working tree as checked out at $head, not a diff. It still has
# to run first so this gate answers a cold, env-less `ci/contract.sh` run
# the same one-line way every other gate does.
set -eu
name=sast
. ci/lib.sh
require_range
. core/toolchain.sh

out_dir=${GATES_OUT:-.gates-out}
mkdir -p "$out_dir"

[ -n "${SAST_CMD:-}" ] || nogo "SAST_CMD is empty (docs/adr/0042 §1)"
toolchain_preflight

log=$(mktemp)
trap 'rm -f "$log"' EXIT

set +e
result=$(run_in_toolchain "$SAST_CMD" 2>"$log")
rc=$?
set -e

cat "$log" >&2

# The runner's line is the last non-empty one on stdout (docs/adr/0042 §1).
result=$(printf '%s\n' "$result" | grep -v '^[[:space:]]*$' | tail -1) || result=""

if [ "$rc" -eq 125 ]; then
  printf '{"findings": null, "where": "%s"}\n' "$toolchain_where" > "$out_dir/sast.json"
  nogo "in $toolchain_where: the toolchain itself failed before the scan ran; see stderr"
fi

count=$(printf '%s' "$result" | jq -r '.findings' 2>/dev/null) || count=""
case "$count" in
  ''|*[!0-9]*) count="" ;;
esac

printf '{"findings": %s, "where": "%s"}\n' "${count:-null}" "$toolchain_where" > "$out_dir/sast.json"

if [ -z "$count" ]; then
  nogo "in $toolchain_where: SAST_CMD did not print valid JSON on stdout: $result"
fi
if [ "$count" -gt 0 ]; then
  nogo "in $toolchain_where: $count SAST finding(s) in the workload's scope"
fi
if [ "$rc" -ne 0 ]; then
  nogo "in $toolchain_where: SAST_CMD exited $rc with no findings parsed; see stderr"
fi

go_with "in $toolchain_where"
