#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# tests/sast/run.sh: runs inside the backend-test image (docs/adr/0030 §3),
# invoked by gates/sast.sh through `docker-compose --profile test run --rm
# --no-deps -T backend-test sh tests/sast/run.sh`; --no-deps because this is
# static analysis and needs no Postgres.
#
# Scope is exactly meetups/ (docs/adr/0015 §4): tests/ and fakes/ are not
# scanned (bandit would flag `assert`, B101, in every pytest test, which is
# not a signal here) and the README says so. Any finding at all is a
# finding -- no severity floor, because a floor is a number with no stated
# provenance; a bandit `# nosec <reason>` comment on the flagged line is the
# escape hatch, reviewed per finding. Whether a finding is NO-GO is
# gates/sast.sh's call, not this script's.
#
# Output contract (docs/adr/0030 §3): exactly one JSON line, {"findings":
# N}, on stdout; bandit's own report on stderr; non-zero exit only when
# bandit itself failed to run (its own exit code nonzero *and* no findings
# could be parsed from its output) -- a bandit exit of 1 because it found
# something is not a tool failure.
set -eu

log=$(mktemp)
trap 'rm -f "$log"' EXIT

rc=0
bandit -r meetups -q >"$log" 2>&1 || rc=$?

cat "$log" >&2

count=$(grep -c '^>> Issue:' "$log") || count=0
printf '{"findings": %s}\n' "$count"

if [ "$rc" -eq 0 ]; then
  exit 0
fi
if [ "$count" -gt 0 ]; then
  exit 0
fi
printf 'run: bandit exited %s with no findings parsed -- not a scored run\n' "$rc" >&2
exit 1
