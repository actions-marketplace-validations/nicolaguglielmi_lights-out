#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-toolchain-run: where the workload's TOOLCHAIN_IMAGE says a command
# runs, for a gate's Python (docs/adr/0084 §4), over core/gates/toolchain.py
# (amendment A3).
#
#   sh core/toolchain-run.sh CMD          CMD where the form says, from the
#       caller's directory (a base worktree, for gates/sast.sh); exit CMD's,
#       or 125 when the toolchain itself failed or the form is malformed (a
#       "toolchain:" line on stderr, never a contract line on stdout)
#   sh core/toolchain-run.sh --preflight  the preflight: exit 0 with
#       $toolchain_where on stdout, or 1 with the preflight's NO-GO reason
#       on stdout, for a gate whose preflight comes after a verdict that
#       needs no toolchain (gates/test-proof.sh)
#
# -P and PYTHONPATH: this checkout's core/, never the caller directory's.
set -u
root=$(cd "$(dirname "$0")/.." && pwd)
PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
if [ "${1:-}" = --preflight ]; then
  exec python3 -P -m core.gates.toolchain preflight
fi
exec python3 -P -m core.gates.toolchain run "${1:?usage: core/toolchain-run.sh CMD | --preflight}"
