#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-hooks: proves adapters/gemini-cli/hooks/guard.sh (ADR 0017 §9) both
# allows and denies, on a fixed set of committed cases -- no Gemini needed,
# no git range needed (unlike gates/*.sh's require_range, this judges fixed
# stdin cases, not a git range, so it runs cold the same way ci/contract.sh
# does). Cases live in ci/hooks-cases/<name>.json with a sibling
# ci/hooks-cases/<name>.expect containing exactly "allow" or "deny" (the
# .json/.expect extensions, not .sh, keep ci/contract.sh's *.sh glob from
# picking these up as gates of their own).
set -eu
name=hooks
. ci/lib.sh

guard=adapters/gemini-cli/hooks/guard.sh
[ -f "$guard" ] || nogo "$guard not found"

cases_dir=ci/hooks-cases
[ -d "$cases_dir" ] || nogo "$cases_dir not found"

mismatch=""
for expect_file in "$cases_dir"/*.expect; do
  [ -e "$expect_file" ] || continue
  case_name=$(basename "$expect_file" .expect)
  json_file="$cases_dir/$case_name.json"
  [ -f "$json_file" ] || { mismatch="$case_name(missing .json)"; break; }

  want=$(cat "$expect_file")
  case "$want" in
    allow|deny) ;;
    *) mismatch="$case_name(.expect must be allow or deny, got $want)"; break ;;
  esac

  crew_out=$(mktemp -d)

  rc=0
  CREW_OUT="$crew_out" sh "$guard" <"$json_file" >/dev/null 2>"$crew_out/stderr.log" || rc=$?

  got=""
  case "$rc" in
    0) got=allow ;;
    2) got=deny ;;
    *) got="exit($rc)" ;;
  esac

  if [ "$got" != "$want" ]; then
    printf 'ci-hooks: %s: want %s, got %s\n' "$case_name" "$want" "$got" >&2
    cat "$crew_out/stderr.log" >&2
    mismatch="$case_name(want $want, got $got)"
    rm -rf "$crew_out"
    break
  fi

  rm -rf "$crew_out"
done

[ -z "$mismatch" ] || nogo "case $mismatch disagrees with guard.sh"

go
