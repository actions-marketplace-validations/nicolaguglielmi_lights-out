#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-shell: shellcheck on every POSIX sh script the repo ships: the host
# entrypoint, the workbench fetch helper, the self-check scripts themselves,
# the readiness pollers and the rest of the per-adapter scripts under
# adapters/*/, the release controller under core/, any script under gates/,
# verify/ or e2e/ once those exist, and every workload's own scripts (app/
# today, workloads/*/ once a second one exists, docs/adr/0030 §5): smoke.sh,
# load.sh, the optional crew-prepare.sh, and each in-image runner
# (tests/mutation/run.sh, tests/sast/run.sh) found by suffix, not by a fixed
# depth — a workload with no backend/-style subdirectory places them one
# level shallower than app/'s do.
set -eu
name=shell
. ci/lib.sh

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

{
  printf '%s\n' go workbench/fetch.sh
  find ci -maxdepth 1 -type f -name '*.sh'
  find adapters -type f -name '*.sh'
  find core -type f -name '*.sh'
  for d in gates verify e2e; do
    [ -d "$d" ] && find "$d" -type f -name '*.sh'
  done
  for w in app workloads/*; do
    [ -d "$w" ] || continue
    [ -f "$w/smoke.sh" ] && printf '%s\n' "$w/smoke.sh"
    [ -f "$w/load.sh" ] && printf '%s\n' "$w/load.sh"
    [ -f "$w/crew-prepare.sh" ] && printf '%s\n' "$w/crew-prepare.sh"
    find "$w" \( -path '*/tests/mutation/run.sh' -o -path '*/tests/sast/run.sh' \) -type f
  done
  true
} > "$tmp"

xargs shellcheck -s sh --color=never < "$tmp" >&2 || nogo "shellcheck reported problems"

go
