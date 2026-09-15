#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-harness: proves core/harness-check.sh (docs/adr/0017 §1) -- the
# harness-independent "exit 0 is not success" invariant -- rejects each of
# its three failure modes and accepts the valid case, on throwaway git
# repos and OUT directories built here. No model, no adapter, no range.
set -eu
name=harness
. ci/lib.sh

check=core/harness-check.sh
[ -f "$check" ] || nogo "$check not found"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# stub_workspace DIR: git init, a base commit, then a real commit over it.
# Every one of the 4 cases below gets this same real commit -- only
# OUT/patch and OUT/pr.json vary below, since those are what
# core/harness-check.sh is proven on here. Prints the base sha on stdout.
stub_workspace() {
  ws=$1
  mkdir -p "$ws"
  git init -q "$ws"
  git -C "$ws" -c user.name=lights-out-tests -c user.email=tests@lights-out.invalid \
    commit -q --allow-empty -m base
  base_sha=$(git -C "$ws" rev-parse HEAD)
  printf 'line\n' > "$ws/file.txt"
  git -C "$ws" add -A
  git -C "$ws" -c user.name=lights-out-tests -c user.email=tests@lights-out.invalid \
    commit -q -m change
  printf '%s' "$base_sha"
}

mismatch=""

# run_case NAME WANT_RC OUT_DIR WORKSPACE_DIR BASE_SHA: runs
# core/harness-check.sh on the stub, sets $mismatch on disagreement.
run_case() {
  case_name=$1
  want_rc=$2
  out_dir=$3
  ws=$4
  base=$5
  rc=0
  sh "$check" "$out_dir" "$ws" "$base" >"$work/$case_name.out" 2>"$work/$case_name.err" || rc=$?
  if [ "$rc" != "$want_rc" ]; then
    printf 'ci-harness: %s: want exit %s, got %s\n' "$case_name" "$want_rc" "$rc" >&2
    cat "$work/$case_name.err" >&2
    mismatch="$case_name(want exit $want_rc, got $rc)"
  fi
}

# (a) empty patch file, non-empty pr.json with a title, a real commit:
# expect harness-check to fail on the patch check.
out_a="$work/a/out"; ws_a="$work/a/ws"
mkdir -p "$out_a"
: > "$out_a/patch"
printf '{"title":"a title","body":"a body"}\n' > "$out_a/pr.json"
base_a=$(stub_workspace "$ws_a")
run_case empty-patch 1 "$out_a" "$ws_a" "$base_a"

# (b) real commit, non-empty patch, no pr.json at all: expect fail.
if [ -z "$mismatch" ]; then
  out_b="$work/b/out"; ws_b="$work/b/ws"
  mkdir -p "$out_b"
  printf 'diff --git a/x b/x\n' > "$out_b/patch"
  base_b=$(stub_workspace "$ws_b")
  run_case missing-pr-json 1 "$out_b" "$ws_b" "$base_b"
fi

# (c) real commit, non-empty patch, pr.json present but title is empty:
# expect fail.
if [ -z "$mismatch" ]; then
  out_c="$work/c/out"; ws_c="$work/c/ws"
  mkdir -p "$out_c"
  printf 'diff --git a/x b/x\n' > "$out_c/patch"
  printf '{"title":""}\n' > "$out_c/pr.json"
  base_c=$(stub_workspace "$ws_c")
  run_case empty-title 1 "$out_c" "$ws_c" "$base_c"
fi

# (d) real commit, non-empty patch, pr.json with a real title: the valid
# case, expect harness-check to succeed.
if [ -z "$mismatch" ]; then
  out_d="$work/d/out"; ws_d="$work/d/ws"
  mkdir -p "$out_d"
  printf 'diff --git a/x b/x\n' > "$out_d/patch"
  printf '{"title":"a real title","body":"a real body"}\n' > "$out_d/pr.json"
  base_d=$(stub_workspace "$ws_d")
  run_case valid 0 "$out_d" "$ws_d" "$base_d"
fi

[ -z "$mismatch" ] || nogo "stub case $mismatch disagrees with core/harness-check.sh"

go
