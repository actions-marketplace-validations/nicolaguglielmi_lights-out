#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-mutation: docs/adr/0015 §3. The workload's MUTATION_CMD over the
# lines the range BASE..HEAD added or changed under the workload's own
# mutation scope ($WORKLOAD/$WORKLOAD_MUTATION_SCOPE, docs/adr/0030 §2),
# run where its TOOLCHAIN_IMAGE says (docs/adr/0042 §1-§2,
# core/toolchain.sh). The gate reads a score, never a tool: cosmic-ray for
# the bundled app, Stryker for a javascript workload, any runner that
# honours the line (MUTATION_LINES in, one JSON line out). require_range
# must be the first thing that can fail: it is what a cold ci/contract.sh
# run sees (no BASE/HEAD, no plane), and it is what keeps this gate instant
# whenever there is no range to judge. Nothing before it may touch git or
# the engine.
#
# Line scope cannot see deletions: a PR that only deletes lines the suite
# never exercised passes this gate untouched; gates/test.sh is what would
# notice a broken deletion (docs/adr/0015 consequences).
#
# The lines, the JUDGED rule (docs/adr/0074 §3-§4), the run and the score
# are core/gates/mutation.py (docs/adr/0084); this keeps the guards and the
# toolchain preflight, in their order.
set -eu
name=mutation
. ci/lib.sh
require_range
. core/toolchain.sh

[ -n "${WORKLOAD_MUTATION_SCOPE:-}" ] || nogo "WORKLOAD_MUTATION_SCOPE is empty"
[ -e "$WORKLOAD/$WORKLOAD_MUTATION_SCOPE" ] || nogo "$WORKLOAD/$WORKLOAD_MUTATION_SCOPE does not exist"
[ -n "${MUTATION_CMD:-}" ] || nogo "MUTATION_CMD is empty (docs/adr/0042 §1)"
toolchain_preflight
verdict core.gates.mutation "$base" "$head" "$toolchain_where"
