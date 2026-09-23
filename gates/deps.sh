#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-deps: dependency scan, docs/adr/0015 §5. `osv-scanner` over every
# lockfile the workload names (WORKLOAD_LOCKFILES, colon-separated,
# docs/adr/0030 §2 -- the app's today are backend and frontend, dev tools
# included: they run in the build-and-test chain, docs/adr/0015 §1),
# against the live OSV database at api.osv.dev. No engine, network only, so
# this runs in plain workbench — no compose project, no socket. Exit 1 from osv-scanner
# (vulnerabilities found) is NO-GO with the tool's own findings passed
# through on stderr; any other non-zero exit (a network failure, most
# often) is also NO-GO, with the tool's own error — never a silent GO: a
# scanner that cannot reach its database has not cleared the PR.
#
# Determinism caveat: the lockfiles are pinned but the advisory database is
# not, so the same commit can go from GO to NO-GO overnight with no code
# change here. The fix, when that happens for real, is a dependency
# version bump or — when a bump is not this gate's call to make — an
# `osv-scanner.toml` `[[IgnoredVulns]]` entry at the repo root naming the
# advisory `id` and a `reason`.
set -eu
name=deps
. ci/lib.sh
require_range

gates_out=${GATES_OUT:-.gates-out}
mkdir -p "$gates_out"

[ -n "${WORKLOAD_LOCKFILES:-}" ] || nogo "WORKLOAD_LOCKFILES is empty"

old_ifs=$IFS
IFS=:
set -f
# shellcheck disable=SC2086 # WORKLOAD_LOCKFILES is deliberately word-split on IFS=:
set -- $WORKLOAD_LOCKFILES
set +f
IFS=$old_ifs

lockfiles=""
count=0
for entry in "$@"; do
  [ -n "$entry" ] || nogo "WORKLOAD_LOCKFILES names an empty entry"
  path="$WORKLOAD/$entry"
  [ -e "$path" ] || nogo "$path does not exist (from WORKLOAD_LOCKFILES)"
  lockfiles="${lockfiles:+$lockfiles }$path"
  count=$((count + 1))
done

printf 'deps: scanning %s lockfile(s): %s\n' "$count" "$lockfiles" >&2

set --
for path in $lockfiles; do
  set -- "$@" -L "$path"
done

out=$(osv-scanner scan source "$@" 2>&1) && rc=0 || rc=$?
printf '%s\n' "$out" >&2

json_list=""
for path in $lockfiles; do
  json_list="${json_list:+$json_list,}\"$path\""
done

verdict=GO
[ "$rc" -eq 0 ] || verdict=NO-GO
printf '{"lockfiles":[%s],"exit_code":%s,"verdict":"%s"}\n' \
  "$json_list" "$rc" "$verdict" > "$gates_out/deps.json"

case "$rc" in
  0) go ;;
  1) nogo "osv-scanner found a vulnerability; findings on stderr" ;;
  *) nogo "osv-scanner exited $rc; error on stderr" ;;
esac
