#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-sast: docs/adr/0015 §4. Static analysis over the shipped backend
# package only: `bandit -r meetups -q`, run inside the same `backend-test`
# image as the test suite (docs/adr/0010 §4), `--no-deps` because bandit is
# static analysis and needs no Postgres. Any finding at all is NO-GO — no
# severity floor, because a floor is a number with no stated provenance;
# a bandit `# nosec <reason>` comment on the flagged line is the escape
# hatch, reviewed per finding. Scope is exactly `meetups/`: `tests/` and
# `fakes/` are not scanned (bandit would flag `assert`, B101, in every
# pytest test, which is not a signal here) and the README says so. The
# frontend gets no SAST at M4 (React/Vite/TS, no tests until M10, static
# bundle).
#
# require_range runs first and its result is otherwise unused: bandit scans
# the working tree as checked out at $head, not a diff. It still has to run
# first so this gate answers a cold, env-less `ci/contract.sh` run the same
# one-line way every other gate does, and so a future integration knows to
# check out $head before calling this script if it isn't already on disk.
set -eu
name=sast
. ci/lib.sh

require_range

out_dir=${GATES_OUT:-.gates-out}
mkdir -p "$out_dir"

log=$(mktemp)
trap 'rm -f "$log"' EXIT

# --build: scan the package as it is on disk now, not a stale cached image.
# Compose's own build/run bookkeeping and bandit's report land in the same
# log and go to stderr together — never stdout, which carries only the one
# contract line.
rc=0
docker-compose --profile test run --rm --no-deps --build backend-test \
  bandit -r meetups -q >"$log" 2>&1 || rc=$?

cat "$log" >&2

count=$(grep -c '^>> Issue:' "$log") || count=0
printf '{"findings": %s}\n' "$count" > "$out_dir/sast.json"

if [ "$rc" -eq 0 ]; then
  go
fi

if [ "$count" -gt 0 ]; then
  nogo "$count bandit finding(s) in meetups/"
fi
nogo "bandit exited $rc with no findings parsed; see stderr"
