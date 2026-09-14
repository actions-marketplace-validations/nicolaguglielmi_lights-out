#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-shell: shellcheck on every POSIX sh script the repo ships: the host
# entrypoint, the workbench fetch helper, the self-check scripts themselves,
# and any script under gates/, verify/ or e2e/ once those exist.
set -eu
name=shell

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

{
  printf '%s\n' go workbench/fetch.sh
  find ci -maxdepth 1 -type f -name '*.sh'
  for d in gates verify e2e; do
    [ -d "$d" ] && find "$d" -type f -name '*.sh'
  done
  true
} > "$tmp"

if ! xargs shellcheck -s sh < "$tmp"; then
  printf 'NO-GO: %s: shellcheck reported problems\n' "$name" >&2
  exit 1
fi

printf 'GO: %s\n' "$name"
