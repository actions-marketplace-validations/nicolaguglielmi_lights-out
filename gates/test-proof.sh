#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-test-proof: docs/adr/0053 §2. The tests a PR adds or changes
# (WORKLOAD_TEST_PATHS, §1) must fail on the base: in a throwaway
# worktree of the merge-base, only those files are taken from HEAD, and
# the workload's TEST_CMD runs there, where the test gate runs it
# (core/toolchain.sh, docs/adr/0042 §2). A non-zero exit is GO; exit 0 is
# NO-GO, the tests pass without the change. Passing on HEAD is the test
# gate's verdict, which runs before this one in GATES (§4). GO by absence
# of subject, nothing run: no test changed, only tests changed, or the
# base is the empty tree. require_range first (docs/adr/0015 §2).
set -eu
# shellcheck disable=SC2209 # the gate's name, not the test(1) command
name=test-proof
. ci/lib.sh
require_range
. core/toolchain.sh

[ -n "${WORKLOAD_TEST_PATHS:-}" ] || nogo "WORKLOAD_TEST_PATHS is empty (docs/adr/0053 §1)"
[ -n "${TEST_CMD:-}" ] || nogo "TEST_CMD is empty (docs/adr/0042 §1)"
if [ "$(git -C "$WORKLOAD" cat-file -t "$base" 2>/dev/null)" = tree ]; then
  go_with "nothing ran: the base is the empty tree, nothing to fail on"
fi
prefix=$(git -C "$WORKLOAD" rev-parse --show-prefix) || nogo "$WORKLOAD is not inside a git repository"
contract=$(git -C "$WORKLOAD_CONTRACT" rev-parse --show-prefix) || nogo "$WORKLOAD_CONTRACT is not inside a git repository"
tests=$(git -C "$WORKLOAD" diff --no-renames --name-only "$base" "$head" \
  | python3 core/testdiff.py subject "$WORKLOAD_TEST_PATHS" "$prefix") \
  || { [ $? -eq 3 ] && go_with "nothing ran: $tests"; nogo "could not list the changed tests: $tests"; }
toolchain_preflight

tmp=$(mktemp -d)
wt=$tmp/wt
trap 'git -C "$WORKLOAD" worktree remove --force "$wt" >/dev/null 2>&1 || :; rm -rf "$tmp"' EXIT
err=$(git -C "$WORKLOAD" worktree add --detach "$wt" "$base" 2>&1 >/dev/null) || nogo "git worktree add on the base failed" "$err"
# shellcheck disable=SC2086 # one path per line, none with a newline
(cd "$wt" && set -f && IFS='
' && git restore --source="$head" --worktree -- $tests) || nogo "could not take the tests from $head onto the base"

# A bundled workload runs from its worktree, as demo-gates does; an
# attached one keeps this checkout's compose.yaml, its own path absolute.
root=$(pwd)
[ -n "${WORKLOAD_ATTACHED:-}" ] || root=$wt
short=$(printf '%s' "$base" | cut -c1-7)
set +e
(cd "$root" && WORKLOAD="$wt/$prefix" WORKLOAD_CONTRACT="$wt/$contract" \
  COMPOSE_FILE="compose.yaml:$wt/${contract}compose.yaml" && export WORKLOAD WORKLOAD_CONTRACT COMPOSE_FILE \
  && run_in_toolchain "$TEST_CMD") >&2
rc=$?
set -e
[ "$rc" -ne 125 ] || nogo "in $toolchain_where: the toolchain itself failed on the base; see stderr"
[ "$rc" -eq 0 ] || go_with "in $toolchain_where, the changed tests fail on the base $short"
nogo "in $toolchain_where: the changed tests pass on the base $short too, so they do not prove the change" "$tests"
