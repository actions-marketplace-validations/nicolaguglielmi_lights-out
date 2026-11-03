#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-deps: dependency scan, docs/adr/0015 §5 as amended by docs/adr/0032.
# `osv-scanner` over every lockfile the workload names (WORKLOAD_LOCKFILES,
# colon-separated, docs/adr/0030 §2 -- dev tools included: they run in the
# build-and-test chain, docs/adr/0015 §1), against the live OSV database at
# api.osv.dev. No engine, network only, so this runs in plain workbench.
#
# The verdict is on the diff (docs/adr/0032): each lockfile is scanned at
# the merge-base and at HEAD, a finding is the tuple (ecosystem, package,
# advisory id), and only a tuple HEAD has and the base does not is NO-GO.
# Advisories already in the base are inherited debt: counted and listed on
# stderr every run, never gating. A lockfile absent at the base is judged
# whole. Any osv-scanner exit other than 0 (clean) or 1 (findings), on
# either scan -- a network failure, most often -- is NO-GO with the tool's
# own error: a scanner that cannot reach its database has not cleared the PR.
set -eu
name=deps
. ci/lib.sh
require_range

gates_out=${GATES_OUT:-.gates-out}
mkdir -p "$gates_out"

[ -n "${WORKLOAD_LOCKFILES:-}" ] || nogo "WORKLOAD_LOCKFILES is empty"

old_ifs=$IFS
IFS=:
set -f
# shellcheck disable=SC2086 # WORKLOAD_LOCKFILES is deliberately word-split on IFS=:
set -- $WORKLOAD_LOCKFILES
set +f
IFS=$old_ifs

lockfiles=""
entries=""
count=0
for entry in "$@"; do
  [ -n "$entry" ] || nogo "WORKLOAD_LOCKFILES names an empty entry"
  path="$WORKLOAD/$entry"
  # <rev>:./<path> is relative to git -C's directory: the workload's place
  # in its repository, whichever repository that is (docs/adr/0037 §3).
  git -C "$WORKLOAD" cat-file -e "$head:./$entry" 2>/dev/null \
    || nogo "$path is not tracked at $head (from WORKLOAD_LOCKFILES)"
  lockfiles="${lockfiles:+$lockfiles }$path"
  entries="${entries:+$entries }$entry"
  count=$((count + 1))
done

printf 'deps: scanning %s lockfile(s) at %s and at the base %s: %s\n' \
  "$count" "$head" "$base" "$lockfiles" >&2

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/base" "$tmp/head"

# scan <out-json> <lockfile>...: osv-scanner's JSON on <out-json>, its own
# messages on stderr; exits 0 or 1 as the tool does, NO-GO on anything else.
scan() {
  scan_out=$1
  shift
  [ "$#" -gt 0 ] || { printf '{"results":[]}\n' > "$scan_out"; return 0; }
  scan_args=""
  for f in "$@"; do
    scan_args="$scan_args -L $f"
  done
  # shellcheck disable=SC2086 # -L <path> pairs, no spaces in paths
  osv-scanner scan source --format json $scan_args > "$scan_out" 2> "$scan_out.err" && rc=0 || rc=$?
  case "$rc" in
    0|1) : ;;
    *) cat "$scan_out.err" >&2; nogo "osv-scanner exited $rc; error on stderr" ;;
  esac
}

# tuples <json> <out>: one sorted "ecosystem package id" line per finding.
# jq on its own line, so unparseable scanner output is NO-GO, not an empty
# list that would read as "nothing new".
tuples() {
  jq -r '.results[]?.packages[]? | .package as $p
         | .vulnerabilities[]? | "\($p.ecosystem) \($p.name) \(.id)"' "$1" > "$2.raw" \
    || nogo "osv-scanner wrote output jq cannot read: $1"
  sort -u "$2.raw" > "$2"
}

# Both sides come from git, the head side included: the gate judges the
# range it was given, whatever the working tree holds.
base_files=""
head_files=""
for entry in $entries; do
  mkdir -p "$tmp/head/$(dirname "$entry")"
  git -C "$WORKLOAD" show "$head:./$entry" > "$tmp/head/$entry"
  head_files="${head_files:+$head_files }$tmp/head/$entry"
  if git -C "$WORKLOAD" cat-file -e "$base:./$entry" 2>/dev/null; then
    mkdir -p "$tmp/base/$(dirname "$entry")"
    git -C "$WORKLOAD" show "$base:./$entry" > "$tmp/base/$entry"
    base_files="${base_files:+$base_files }$tmp/base/$entry"
  else
    printf 'deps: %s is new at HEAD, judged whole\n' "$WORKLOAD/$entry" >&2
  fi
done

# shellcheck disable=SC2086 # space-separated path lists, no spaces in paths
scan "$tmp/head.json" $head_files
# shellcheck disable=SC2086
scan "$tmp/base.json" $base_files

tuples "$tmp/head.json" "$tmp/head.txt"
tuples "$tmp/base.json" "$tmp/base.txt"
comm -13 "$tmp/base.txt" "$tmp/head.txt" > "$tmp/new.txt"
comm -12 "$tmp/base.txt" "$tmp/head.txt" > "$tmp/inherited.txt"
new=$(wc -l < "$tmp/new.txt" | tr -d ' ')
inherited=$(wc -l < "$tmp/inherited.txt" | tr -d ' ')

if [ "$inherited" -gt 0 ]; then
  printf 'deps: %s advisory finding(s) inherited from the base, not gating (docs/adr/0032):\n' "$inherited" >&2
  sed 's/^/  /' "$tmp/inherited.txt" >&2
fi
if [ "$new" -gt 0 ]; then
  printf 'deps: %s advisory finding(s) introduced by this diff:\n' "$new" >&2
  sed 's/^/  /' "$tmp/new.txt" >&2
fi

json_list=""
for path in $lockfiles; do
  json_list="${json_list:+$json_list,}\"$path\""
done

verdict=GO
[ "$new" -eq 0 ] || verdict=NO-GO
printf '{"lockfiles":[%s],"new":%s,"inherited":%s,"verdict":"%s"}\n' \
  "$json_list" "$new" "$inherited" "$verdict" > "$gates_out/deps.json"

[ "$new" -eq 0 ] || nogo "this diff introduces $new advisory finding(s); list on stderr"
go
