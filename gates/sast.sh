#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-sast: docs/adr/0015 §4. Static analysis over the shipped backend
# package, run inside the same `backend-test` image as the test suite
# (docs/adr/0010 §4) by the workload's own in-image runner,
# tests/sast/run.sh (docs/adr/0030 §3: one JSON line {"findings": N} on
# stdout, its report on stderr, non-zero only if the tool itself failed).
# `--no-deps` because static analysis needs no Postgres. The frontend gets
# no SAST at M4 (React/Vite/TS, no tests until M11, static bundle).
#
# require_range runs first and its result is otherwise unused: the runner
# scans the working tree as checked out at $head, not a diff. It still has
# to run first so this gate answers a cold, env-less `ci/contract.sh` run
# the same one-line way every other gate does, and so a future integration
# knows to check out $head before calling this script if it isn't already
# on disk.
set -eu
name=sast
. ci/lib.sh

require_range

out_dir=${GATES_OUT:-.gates-out}
mkdir -p "$out_dir"

log=$(mktemp)
trap 'rm -f "$log"' EXIT

# Built separately from run, below: `run --build`'s own image-build log
# goes to *its* stdout (confirmed empirically -- not stderr, contrary to
# what the classic, non-Buildkit builder's docs might suggest; see
# gates/mutation.sh's own comment), which would otherwise land inside
# $result and break the one-JSON-line contract. -T disables the pseudo-TTY
# that would otherwise interleave the run's own stdout and stderr.
docker-compose --profile test build backend-test >&2 \
  || nogo "backend-test image build failed; see stderr"

set +e
result=$(docker-compose --profile test run --rm --no-deps -T backend-test \
  sh tests/sast/run.sh 2>"$log")
rc=$?
set -e

cat "$log" >&2

count=$(printf '%s' "$result" | jq -r '.findings' 2>/dev/null) || count=""
case "$count" in
  ''|*[!0-9]*) count="" ;;
esac

printf '{"findings": %s}\n' "${count:-null}" > "$out_dir/sast.json"

if [ -z "$count" ]; then
  nogo "tests/sast/run.sh did not print valid JSON on stdout: $result"
fi
if [ "$count" -gt 0 ]; then
  nogo "$count SAST finding(s) in the workload's scope"
fi
if [ "$rc" -ne 0 ]; then
  nogo "tests/sast/run.sh exited $rc with no findings parsed; see stderr"
fi

go
