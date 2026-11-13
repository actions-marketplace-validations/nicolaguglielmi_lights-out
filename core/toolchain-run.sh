#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-toolchain-run: where the workload's TOOLCHAIN_IMAGE says a command
# runs, for a gate's Python (docs/adr/0084 §4), over core/toolchain.sh.
#
#   sh core/toolchain-run.sh CMD          run_in_toolchain CMD, from the
#       caller's directory (a base worktree, for gates/sast.sh); exit CMD's,
#       or 125 when the toolchain itself failed or the form is malformed (a
#       "toolchain:" line on stderr, never a contract line on stdout)
#   sh core/toolchain-run.sh --preflight  toolchain_preflight: exit 0 with
#       $toolchain_where on stdout, or 1 with the preflight's NO-GO reason
#       on stdout, for a gate whose preflight comes after a verdict that
#       needs no toolchain (gates/test-proof.sh)
set -u
name=toolchain-run
here=$(dirname "$0")
. "$here/../ci/lib.sh"
. "$here/toolchain.sh"
if [ "${1:-}" = --preflight ]; then
  nogo() { printf '%s\n' "$1"; exit 1; }
  toolchain_preflight
  printf '%s\n' "$toolchain_where"
  exit 0
fi
nogo() { printf 'toolchain: %s\n' "$1" >&2; exit 125; }
toolchain_form
run_in_toolchain "${1:?usage: core/toolchain-run.sh CMD | --preflight}"
