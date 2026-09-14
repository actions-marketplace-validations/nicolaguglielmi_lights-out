#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-shell: shellcheck on every POSIX sh script the repo ships: the host
# entrypoint, the workbench fetch helper, the self-check scripts themselves,
# the readiness pollers under adapters/*/ready.sh, the app smoke test, and
# any script under gates/, verify/ or e2e/ once those exist.
set -eu
name=shell
. ci/lib.sh

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

{
  printf '%s\n' go workbench/fetch.sh app/smoke.sh
  find ci -maxdepth 1 -type f -name '*.sh'
  find adapters -type f -name 'ready.sh'
  for d in gates verify e2e; do
    [ -d "$d" ] && find "$d" -type f -name '*.sh'
  done
  true
} > "$tmp"

xargs shellcheck -s sh --color=never < "$tmp" >&2 || nogo "shellcheck reported problems"

go
