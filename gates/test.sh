#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-test: the PR gate for plan §7's first three M4 line items — unit,
# integration and contract tests — which are one thing: the workload's
# TEST_CMD (docs/adr/0042 §1), run where its TOOLCHAIN_IMAGE says
# (docs/adr/0042 §2, core/toolchain.sh). The command's exit code is the
# verdict, as backend-test's was (docs/adr/0030 §3): for the bundled app
# that is still `python -m pytest tests -q` in the compose service
# backend-test, which starts the real compose Postgres (integration; no
# Testcontainers, docs/adr/0015 §1). No test infrastructure of this
# gate's own; the GO line says where the suite ran (docs/adr/0042 §3).
#
# require_range (docs/adr/0015 §2) still runs first, unconditionally: it is
# what ci/contract.sh's cold scan sees (NO-GO in one line, no engine, when
# BASE or HEAD is unset), matching every other gate's contract. This gate
# does not otherwise use $base/$head — it does not diff BASE..HEAD, it runs
# the whole suite against whatever is checked out at HEAD.
set -eu
# shellcheck disable=SC2209 # "test" is this gate's name (matches the file
# name and the NO-GO line), not a mistaken reference to the test(1) command
name=test
. ci/lib.sh
require_range
. core/toolchain.sh

out=${GATES_OUT:-.gates-out}
mkdir -p "$out"

[ -n "${TEST_CMD:-}" ] || nogo "TEST_CMD is empty (docs/adr/0042 §1)"
toolchain_preflight

# The suite's own output is not the gate's verdict: on stderr. The exit
# code is; the runner's own failure output already tells the story, so it
# is not parsed or summarised here.
set +e
run_in_toolchain "$TEST_CMD" >&2
rc=$?
set -e

if [ "$rc" -eq 0 ]; then
  printf '{"passed": true, "where": "%s"}\n' "$toolchain_where" > "$out/test.json"
  go_with "in $toolchain_where"
fi

printf '{"passed": false, "where": "%s"}\n' "$toolchain_where" > "$out/test.json"
if [ "$rc" -eq 125 ]; then
  nogo "in $toolchain_where: the toolchain itself failed before the suite ran; see stderr"
fi
nogo "in $toolchain_where: the test command failed (exit $rc), see stderr"
