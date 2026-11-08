#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-statestore-conformance: the StateStore port's conformance suite
# (docs/adr/0060 §4, in the shape of docs/adr/0026 and gates/codehost-
# conformance.sh; the contract is docs/adr/0019 §2). Written from the ADRs,
# never from an adapter. It drives whichever STATE_STORE is set, only through
# `sh adapters/$STATE_STORE/{get,put,delete}.sh <collection> <id>` from the
# current directory. Eight cases, in this order, the first disagreement a
# NO-GO naming the case:
#   1 get of an absent document exits 1 with nothing on stdout
#   2 a document holding every JSON type round-trips, equal as a JSON value
#   3 put replaces the whole document: no merge
#   4 one id in two collections is two documents
#   5 put of non-JSON and of a JSON array exits non-zero and leaves the
#     stored document unchanged
#   6 a 65,536-letter ASCII string round-trips (a decision of ADR 0060 §4:
#     above any tower document seen, below the 128 KiB Linux puts on one
#     argument, MAX_ARG_STRLEN, which an adapter that sends a document with
#     `curl -d` meets: an external constraint)
#   7 delete, then get exits 1; the other collection's document is still there
#   8 delete of an absent document exits 0
# Documents are compared as JSON values with jq, never as text: an adapter
# may print them pretty or compact, with its keys in any order. Documents go
# to put on stdin from files, never as arguments. The ids are the tower's:
# 0001 (a ticket), main (the mainline document) and a 40-hex one (a sha).
#
# It writes only collection conformance-<run id> and, for case 4,
# conformance-<run id>-b, and deletes every document it wrote in a trap on
# any exit, ignoring errors. The run id is date and random hex, as
# codehost-conformance makes it: runs never collide, and two suites on one
# store do not meet.
#
# Lives in gates/, so ci/contract.sh cold-runs it inside `make ci` with no
# CONFORMANCE set and no store: the guard below must be the first thing that
# runs. `./go statestore-conformance` is the only caller that sets
# CONFORMANCE=1, never a bare `sh gates/...` (CLAUDE.md). ci/store-bus.sh
# proves this suite can fail, on stub stores broken one behaviour at a time.
set -eu
name=statestore-conformance
. ci/lib.sh

# Instant NO-GO, before anything touches a store (docs/adr/0026 §4).
if [ "${CONFORMANCE:-}" != "1" ]; then
  nogo "set CONFORMANCE=1: this suite writes and deletes documents in the state store (./go statestore-conformance)"
fi

[ -n "${STATE_STORE:-}" ] || nogo "STATE_STORE is not set; a profile sets it: run this via ./go statestore-conformance"
ss=adapters/$STATE_STORE
for v in get put delete; do
  [ -f "$ss/$v.sh" ] || nogo "$ss/$v.sh is missing: a state store ships get, put and delete (docs/adr/0019 §2)"
done
for tool in jq od date awk tr head wc; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool is not on PATH; run this via ./go statestore-conformance"
done

run_id=$(date -u +%Y%m%d-%H%M%S)-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')
col=conformance-$run_id
colb=$col-b
sha=$(od -An -N20 -tx1 /dev/urandom | tr -d ' \n')

work=$(mktemp -d)
out=$work/out
err=$work/err
# Never prints to stdout: the one line this gate owns is already out when it
# runs. Every document the suite may have written, deleted through the port.
# shellcheck disable=SC2329 # invoked by name via `trap` below, not called directly
cleanup() {
  ec=$?
  trap - EXIT INT TERM
  for id in 0001 main "$sha"; do
    sh "$ss/delete.sh" "$col" "$id" >/dev/null 2>&1 </dev/null || :
  done
  sh "$ss/delete.sh" "$colb" 0001 >/dev/null 2>&1 </dev/null || :
  rm -rf "$work"
  exit "$ec"
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Helpers. None of these may be called inside a $(...) capture that is not a
# plain read: a nogo inside one would only exit the subshell (POSIX sh).
# ---------------------------------------------------------------------------

say() { printf '[statestore-conformance] %s\n' "$*" >&2; }

# verb VERB COLLECTION ID [STDIN-FILE]: stdout in $out, exit code in $rc, the
# adapter's stderr relayed on ours.
verb() {
  if sh "$ss/$1.sh" "$2" "$3" >"$out" 2>"$err" <"${4:-/dev/null}"; then rc=0; else rc=$?; fi
  while IFS= read -r l || [ -n "$l" ]; do printf '  [%s] %s\n' "$1" "$l" >&2; done < "$err"
}

# same FILE FILE: succeeds when both hold the same JSON value(s). Slurped, so
# a verb that prints the document twice, or nothing, is not the same.
# shellcheck disable=SC2016 # the jq program is single-quoted on purpose; $a and $b are jq's
same() { jq -en --slurpfile a "$1" --slurpfile b "$2" '$a == $b' >/dev/null 2>&1; }

# snip: the start of the last stdout, on one line, for a NO-GO reason.
snip() { head -c 200 "$out" | tr '\n' ' '; }

say "run $run_id on STATE_STORE=$STATE_STORE, collections $col and $colb"

# ---------------------------------------------------------------------------
# Case 1: an absent document is exit 1 and silence on stdout (docs/adr/0019
# §2): the caller tells "absent" from "the store is down" by the code.
# ---------------------------------------------------------------------------
verb get "$col" 0001
{ [ "$rc" -eq 1 ] && [ ! -s "$out" ]; } \
  || nogo "case1 absent: get of a document never written exited $rc and printed [$(snip)], want exit 1 and nothing on stdout"
say "case 1 get of an absent document: GO"

# ---------------------------------------------------------------------------
# Case 2: every JSON type, equal as a value after a round trip. The nesting
# goes through objects: Firestore refuses an array directly inside an array.
# ---------------------------------------------------------------------------
cat > "$work/types.json" <<'DOC'
{
  "string": "quote \" backslash \\ newline \n tab \t u-umlaut é ü 日本語 😀",
  "empty_string": "",
  "integer": 42,
  "negative": -7,
  "non_integer": 1.5,
  "yes": true,
  "no": false,
  "nothing": null,
  "array": [1, "two", {"three": [3, {"four": null}]}, null, false, 2.5],
  "object": {"nested": {"deeper": ["x", {"y": [true]}]}, "empty_array": [], "empty_object": {}},
  "empty_array": [],
  "empty_object": {}
}
DOC
verb put "$col" 0001 "$work/types.json"
[ "$rc" -eq 0 ] || nogo "case2 roundtrip: put exited $rc on a document holding every JSON type"
verb get "$col" 0001
[ "$rc" -eq 0 ] || nogo "case2 roundtrip: get exited $rc right after the put"
same "$work/types.json" "$out" \
  || nogo "case2 roundtrip: get printed [$(snip)], which is not, as a JSON value, the document that was put"
say "case 2 every JSON type round-trips: GO"

# ---------------------------------------------------------------------------
# Case 3: put replaces. A key the second document lacks is gone, and a key
# whose type changed is the new type.
# ---------------------------------------------------------------------------
printf '{"alpha":1,"beta":{"x":1},"keep":"old"}\n' > "$work/first.json"
printf '{"gamma":[2],"beta":"new"}\n' > "$work/second.json"
verb put "$col" main "$work/first.json"
[ "$rc" -eq 0 ] || nogo "case3 replace: put exited $rc on the first document"
verb put "$col" main "$work/second.json"
[ "$rc" -eq 0 ] || nogo "case3 replace: put exited $rc on the second document"
verb get "$col" main
{ [ "$rc" -eq 0 ] && same "$work/second.json" "$out"; } \
  || nogo "case3 replace: after two puts get exited $rc and printed [$(snip)], want exactly the second document: put replaces, it does not merge"
say "case 3 put replaces: GO"

# ---------------------------------------------------------------------------
# Case 4: the collection is part of the key.
# ---------------------------------------------------------------------------
printf '{"where":"a"}\n' > "$work/doc-a.json"
printf '{"where":"b"}\n' > "$work/doc-b.json"
verb put "$col" 0001 "$work/doc-a.json"
[ "$rc" -eq 0 ] || nogo "case4 collections: put exited $rc in $col"
verb put "$colb" 0001 "$work/doc-b.json"
[ "$rc" -eq 0 ] || nogo "case4 collections: put exited $rc in $colb"
verb get "$col" 0001
{ [ "$rc" -eq 0 ] && same "$work/doc-a.json" "$out"; } \
  || nogo "case4 collections: $col/0001 reads [$(snip)] after $colb/0001 was written, want its own document: the collection is ignored"
verb get "$colb" 0001
{ [ "$rc" -eq 0 ] && same "$work/doc-b.json" "$out"; } \
  || nogo "case4 collections: $colb/0001 reads [$(snip)], want its own document"
say "case 4 one id in two collections is two documents: GO"

# ---------------------------------------------------------------------------
# Case 5: what is not a JSON object is refused and changes nothing (docs/adr/
# 0060 §1): a failed put must not take the stored document with it.
# ---------------------------------------------------------------------------
printf '{"keep":"me"}\n' > "$work/keep.json"
verb put "$col" "$sha" "$work/keep.json"
[ "$rc" -eq 0 ] || nogo "case5 refuse: put exited $rc on a valid document"
# refuses FILE WHAT: put of FILE fails, and the document stored is still keep.json.
refuses() {
  verb put "$col" "$sha" "$1"
  [ "$rc" -ne 0 ] || nogo "case5 refuse: put of $2 exited 0, want non-zero"
  verb get "$col" "$sha"
  { [ "$rc" -eq 0 ] && same "$work/keep.json" "$out"; } \
    || nogo "case5 refuse: after the refused put of $2 get exited $rc and printed [$(snip)], want the stored document unchanged"
}
printf 'this is not JSON {\n' > "$work/garbage.txt"
refuses "$work/garbage.txt" "text that is not JSON"
printf '[1,2,3]\n' > "$work/array.json"
refuses "$work/array.json" "a JSON array"
say "case 5 non-JSON and an array are refused, the document unchanged: GO"

# ---------------------------------------------------------------------------
# Case 6: a large string, on stdin from a file. Letters in a cycle, so a
# chunk that is dropped, repeated or shifted is not the same string.
# ---------------------------------------------------------------------------
awk 'BEGIN {
  s = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"; n = length(s)
  printf "{\"big\":\""
  for (i = 0; i < 65536; i++) printf "%s", substr(s, i % n + 1, 1)
  printf "\"}\n"
}' > "$work/big.json"
jq -e '(.big | length) == 65536' "$work/big.json" >/dev/null 2>&1 \
  || nogo "case6 large: the suite's own document is not a 65,536-character string"
verb put "$col" "$sha" "$work/big.json"
[ "$rc" -eq 0 ] || nogo "case6 large: put exited $rc on a 65,536-character string"
verb get "$col" "$sha"
{ [ "$rc" -eq 0 ] && same "$work/big.json" "$out"; } \
  || nogo "case6 large: get exited $rc and printed $(wc -c < "$out" | tr -d ' ') bytes starting [$(snip)], want the 65,536-character string back"
say "case 6 a 65,536-letter string round-trips: GO"

# ---------------------------------------------------------------------------
# Case 7: delete, then get is exit 1; the document with the same id in the
# other collection is untouched.
# ---------------------------------------------------------------------------
verb delete "$col" 0001
[ "$rc" -eq 0 ] || nogo "case7 delete: delete of an existing document exited $rc"
verb get "$col" 0001
{ [ "$rc" -eq 1 ] && [ ! -s "$out" ]; } \
  || nogo "case7 delete: after delete, get exited $rc and printed [$(snip)], want exit 1 and nothing on stdout"
verb get "$colb" 0001
{ [ "$rc" -eq 0 ] && same "$work/doc-b.json" "$out"; } \
  || nogo "case7 delete: deleting $col/0001 left $colb/0001 reading [$(snip)] (exit $rc), want its own document"
say "case 7 delete: GO"

# ---------------------------------------------------------------------------
# Case 8: deleting what is not there is success: e2e replays from a clean
# document (docs/adr/0019 §7), and so does this suite's own cleanup.
# ---------------------------------------------------------------------------
verb delete "$col" 0001
[ "$rc" -eq 0 ] || nogo "case8 delete-absent: delete of a document deleted a moment ago exited $rc, want 0"
verb delete "$col" never-written
[ "$rc" -eq 0 ] || nogo "case8 delete-absent: delete of an id never written exited $rc, want 0"
say "case 8 delete of an absent document: GO"

go_with "$STATE_STORE, 8 cases"
