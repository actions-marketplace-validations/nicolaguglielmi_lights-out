#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-help: `make help` must exit 0 and list at least `ci` and `demo`.
set -eu
name=help
. ci/lib.sh

out=$(make --no-print-directory help 2>&1) || nogo "make --no-print-directory help exited nonzero" "$out"

targets=$(printf '%s\n' "$out" | awk '/^  [a-z]/{print $1}')

missing=""
for t in ci demo; do
  found=no
  for x in $targets; do
    [ "$x" = "$t" ] && found=yes
  done
  [ "$found" = yes ] || missing="$missing $t"
done

[ -z "$missing" ] || nogo "make help does not list target(s):$missing"

go
