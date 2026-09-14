#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-readme: README truth. Every `./go <word>` and `make <word>` in
# README.md must name a target `make help` actually lists (first column of
# lines starting with two spaces; that also covers the host-side `shell`
# and `clean` entries, which are valid `./go` commands).
set -eu
name=readme

if [ ! -f README.md ]; then
  printf 'NO-GO: %s: README.md not found\n' "$name" >&2
  exit 1
fi

if ! out=$(make --no-print-directory help); then
  printf 'NO-GO: %s: make --no-print-directory help exited nonzero\n' "$name" >&2
  exit 1
fi

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

if [ -n "$bad" ]; then
  printf 'NO-GO: %s: README.md names target(s) make help does not list:%s\n' "$name" "$bad" >&2
  exit 1
fi

printf 'GO: %s\n' "$name"
