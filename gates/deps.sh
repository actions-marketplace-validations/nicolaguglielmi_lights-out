#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-deps: dependency scan, docs/adr/0015 §5. `osv-scanner` over both
# lockfiles whole (backend and frontend, dev tools included: they run in
# the build-and-test chain, docs/adr/0015 §1), against the live OSV
# database at api.osv.dev. No engine, network only, so this runs in plain
# workbench — no compose project, no socket. Exit 1 from osv-scanner
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

lockfiles="app/backend/uv.lock app/frontend/package-lock.json"
printf 'deps: scanning 2 lockfiles: %s\n' "$lockfiles" >&2

out=$(osv-scanner scan source -L app/backend/uv.lock -L app/frontend/package-lock.json 2>&1) \
  && rc=0 || rc=$?
printf '%s\n' "$out" >&2

verdict=GO
[ "$rc" -eq 0 ] || verdict=NO-GO
printf '{"lockfiles":["app/backend/uv.lock","app/frontend/package-lock.json"],"exit_code":%s,"verdict":"%s"}\n' \
  "$rc" "$verdict" > "$gates_out/deps.json"

case "$rc" in
  0) go ;;
  1) nogo "osv-scanner found a vulnerability; findings on stderr" ;;
  *) nogo "osv-scanner exited $rc; error on stderr" ;;
esac
