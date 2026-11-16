#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-toolchain (docs/adr/0042 §2, §4): where a workload's declared command
# runs. Sourced after ci/lib.sh by gates/test.sh, gates/sast.sh,
# gates/mutation.sh, core/init.sh and core/mutation-baseline.sh; not a gate
# of its own, so it never prints the contract line itself except through
# nogo on a contract error.
#
#   toolchain_preflight     # NO-GOes on a contract error; sets $toolchain_where
#   run_in_toolchain CMD    # CMD's exit code, or 125 when the toolchain itself failed
#
# The forms, the checks and the runs are core/gates/toolchain.py (docs/adr/
# 0084, amendment A3), whose docstring is the spec. Python is run with -P and
# PYTHONPATH set to $toolchain_root, the checkout this file belongs to: the
# caller's directory unless the caller set it first, so a caller that runs
# from elsewhere (a base worktree, a temp directory) never imports another
# checkout's core/.
toolchain_root=${toolchain_root:-$(pwd)}

toolchain_py() {
  PYTHONPATH="$toolchain_root${PYTHONPATH:+:$PYTHONPATH}" python3 -P -m core.gates.toolchain "$@"
}

toolchain_preflight() {
  toolchain_where=$(toolchain_py preflight) || nogo "${toolchain_where:-the toolchain preflight failed; see stderr}"
}

run_in_toolchain() {
  [ -n "${toolchain_where:-}" ] || { printf 'toolchain: run_in_toolchain called before toolchain_preflight\n' >&2; return 125; }
  toolchain_py run "$1"
}
