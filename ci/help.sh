#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-help: `make help` must exit 0 and list at least `ci` and `demo`.
set -eu
name=help

if ! out=$(make --no-print-directory help); then
  printf 'NO-GO: %s: make --no-print-directory help exited nonzero\n' "$name" >&2
  exit 1
fi

printf '%s\n' "$out"

targets=$(printf '%s\n' "$out" | awk '/^  [a-z]/{print $1}')

missing=""
for t in ci demo; do
  found=no
  for x in $targets; do
    [ "$x" = "$t" ] && found=yes
  done
  [ "$found" = yes ] || missing="$missing $t"
done

if [ -n "$missing" ]; then
  printf 'NO-GO: %s: make help does not list target(s):%s\n' "$name" "$missing" >&2
  exit 1
fi

printf 'GO: %s\n' "$name"
