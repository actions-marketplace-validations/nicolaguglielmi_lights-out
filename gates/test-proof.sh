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
# base is the empty tree. require_range first (docs/adr/0015 §2). The
# subject, the worktree, the run and the verdict are core/gates/testproof.py
# (docs/adr/0084); its toolchain preflight comes after a GO by absence of
# subject, as before.
set -eu
# shellcheck disable=SC2209 # the gate's name, not the test(1) command
name=test-proof
. ci/lib.sh
require_range
verdict core.gates.testproof "$base" "$head"
