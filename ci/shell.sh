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
  # A workload laid out to be attached keeps these in .lights-out/
  # (docs/adr/0036 §2).
  for w in app workloads/*; do
    [ -d "$w" ] || continue
    for c in "$w" "$w/.lights-out"; do
      [ -f "$c/smoke.sh" ] && printf '%s\n' "$c/smoke.sh"
      [ -f "$c/load.sh" ] && printf '%s\n' "$c/load.sh"
      [ -f "$c/crew-prepare.sh" ] && printf '%s\n' "$c/crew-prepare.sh"
    done
    find "$w" \( -path '*/tests/mutation/run.sh' -o -path '*/tests/sast/run.sh' \) -type f
  done
  true
} > "$tmp"

xargs shellcheck -s sh --color=never < "$tmp" >&2 || nogo "shellcheck reported problems"

go
