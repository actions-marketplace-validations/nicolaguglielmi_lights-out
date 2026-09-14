#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-readme: README truth. Every `./go <word>` and `make <word>` in
# README.md must name a target `make help` actually lists (first column of
# lines starting with two spaces; that also covers the host-side `shell`
# and `clean` entries, which are valid `./go` commands).
set -eu
name=readme
. ci/lib.sh

[ -f README.md ] || nogo "README.md not found"

out=$(make --no-print-directory help 2>&1) || nogo "make --no-print-directory help exited nonzero" "$out"

targets=$(printf '%s\n' "$out" | awk '/^  [a-z]/{print $1}')
words=$(grep -Eo '(\./go|make) [a-z][a-z0-9-]*' README.md | awk '{print $2}' | sort -u)

bad=""
for w in $words; do
  found=no
  for t in $targets; do
    [ "$t" = "$w" ] && found=yes
  done
  [ "$found" = yes ] || bad="$bad $w"
done

[ -z "$bad" ] || nogo "README.md names target(s) make help does not list:$bad"

go
