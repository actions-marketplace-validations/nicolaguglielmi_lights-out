#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-test-weakening: docs/adr/0053 §3. The range BASE..HEAD may not
# weaken the workload's tests (WORKLOAD_TEST_PATHS, §1): delete or rename
# away a test file, lose assertions or test definitions, or gain skip,
# xfail, todo or only markers, counted per file with the patterns in
# core/testdiff.py. A file the ticket's `## Removes tests` declares is
# excused; the ticket is GATES_TICKET, which the tower's CI step sets
# from the Tracker, never from the PR. A diff check: no engine, no
# toolchain. require_range first, as every gate (docs/adr/0015 §2).
set -eu
name=test-weakening
. ci/lib.sh
require_range

[ -n "${WORKLOAD_TEST_PATHS:-}" ] || nogo "WORKLOAD_TEST_PATHS is empty (docs/adr/0053 §1)"
prefix=$(git -C "$WORKLOAD" rev-parse --show-prefix) || nogo "$WORKLOAD is not inside a git repository"

diff=$(mktemp)
trap 'rm -f "$diff"' EXIT
git -C "$WORKLOAD" -c core.quotePath=false diff --no-color --no-ext-diff -M -U0 "$base" "$head" > "$diff" \
  || nogo "could not read the diff for $base..$head"

out=$(python3 core/testdiff.py weakening "$WORKLOAD_TEST_PATHS" "$prefix" "${GATES_TICKET:-}" < "$diff") \
  && go_with "$out"

reason=$(printf '%s\n' "$out" | head -n 1)
old_ifs=$IFS
IFS='
'
set -f
# shellcheck disable=SC2046 # one finding per line, split on newlines only
set -- $(printf '%s\n' "$out" | tail -n +2)
set +f
IFS=$old_ifs
nogo "$reason" "$@"
