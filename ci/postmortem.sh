#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-postmortem: proves core/postmortem.sh, core/incident.sh and
# adapters/file/put.sh (docs/adr/0044 §1-§6, §9) on stubs, cold: no plane, no
# engine, no model, no network. The ci/promote.sh shape: a throwaway root
# symlinking core/ and ci/ and the real adapters/file/, a
# roles/ops-triage/role.env pointing HARNESS at a stub harness whose run.sh
# answers with whatever $root/world/calls.json the case wrote (so the case
# controls what "the ops-triage role said"), a stub-tracker/put.sh that
# delegates to the real adapters/file/put.sh unless a case tells it to
# refuse, and a stub-state/get.sh that serves $root/state/ and logs its
# calls. The tickets directory is the root's own, seeded with 0001.md and
# 0007.md so that the next id is 0008. Every case proves what did NOT happen
# as well as what did: the harness log (no model call before the input checks
# pass), the Tracker log and the tickets directory (no ticket before the
# content checks pass), .crew/postmortem/ (output only on GO), the state
# store log (the post mortem never touches the plane).
# Written from docs/adr/0044 (and docs/adr/0020 §1, §3 for the harness
# artefacts and the alert shape), not from core/postmortem.sh, core/incident.sh
# or adapters/file/put.sh. The hand-written incident document below is the
# spec's shape; core/incident.sh must produce exactly it, and
# core/postmortem.sh must accept exactly it.
#
# Assumptions where the ADR leaves a detail open (the gate-writer's report
# lists them for the implementer to align):
#   A1  core reads its inputs from the environment, as ./go passes them:
#       INCIDENT; NAME FROM TO LOGS TICKET RELEASE_RECORD; and, by the
#       existing conventions, TRACKER, STATE_STORE, AGENT_HARNESS and
#       TICKETS_DIR. Adapters are reached as adapters/$TRACKER/put.sh and
#       adapters/$STATE_STORE/get.sh (get.sh <collection> <id>, collection
#       "tickets") from the working directory; outputs are written below it.
#   A2  the harness is ${HARNESS:-$AGENT_HARNESS} (docs/adr/0020 §1); it is
#       given ROLE=ops-triage, INPUT (a file holding the incident document)
#       and OUT. "Did not finish" is a non-zero exit (P4).
#   A3  entry and action numbers are 1-based, as the alert and log anchors
#       are; the action number in the origin line is that number.
#   A4  a stage in an alert is the record's stage object (docs/adr/0020 §3:
#       {headline, version, stable, stage:{pct, verdict, numbers}}).
#   A5  "output written only on GO" means no FILE under .crew/postmortem/
#       after a NO-GO; an empty directory is not output. Likewise
#       core/incident.sh leaves no file under .crew/incidents/ on a NO-GO.
#   A6  postmortem.json: the keys are exactly those the ADR lists;
#       actions[].ticket is the id as a string ("0008"); .incident holds the
#       incident's name somewhere; .run holds the run's model; causes keep
#       the model's text; evidence[] is an array of strings, never empty.
#   A7  stdout of the GO is exactly "GO: postmortem — <k> action item(s):
#       tickets <id> <id>..." (ids separated by one space); the reasons of P1,
#       P3, P4, P5, P7, P8, P9 and P6's named anchors are the ADR's text
#       verbatim; where the ADR writes <what> or <sequence> only the prefix
#       is matched.
#   A8  P7 is satisfied by a bare release:<version> anchor.
#   A9  an empty tickets directory gets 0001; an id is allocated from the
#       highest numeric *.md basename, non-numeric ones are ignored.
#   A10 a release verdict that is neither held, rolled-back nor in-progress,
#       a missing timeline, an entry with no anchor or two anchors, an empty
#       harness answer and a harness that exits 0 with no artefacts are each
#       a NO-GO, with any reason (the ADR names no text for them); the
#       verdict one is judged before the harness is called.
#   A11 the md prints each anchor's evidence on the lines after the event
#       and before the next event; the model line holds run.json's model
#       (the L0 "replayed, recorded by <provider> <model>" wording is not
#       tested: the stub harness is not a replay).
#   A12 core/incident.sh prints "GO: incident — <path>" with the path ending
#       .crew/incidents/<name>.json; chain.pr and chain.merge are the store
#       document's .pr.number and .merge.sha, chain.ticket the id given.
#   A13 put.sh is given an absolute TICKETS_DIR; a failure it reports is exit
#       1 and one stderr line (tested with a path that is a file). P10 is
#       tested by refusing the LAST action (or every action), so whether core
#       stops at the first refusal or tries the rest is left open.
#   A14 no ordering among P6, P7, P8 and P9 is tested: each case has one
#       defect only.
set -eu
name=postmortem
. ci/lib.sh

for f in core/incident.sh core/postmortem.sh adapters/file/put.sh; do
  [ -f "$f" ] || nogo "$f not found"
done
for tool in jq cksum find awk; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool not on PATH"
done

repo=$(pwd)
root=$(mktemp -d)
# Whatever stops this script other than its own verdict (a command that fails
# where the case did not expect it to) is still one NO-GO line and exit 1.
settled=""
trap 'rc=$?; rm -rf "$root"; if [ -z "$settled" ] && [ "$rc" -ne 0 ]; then printf "NO-GO: %s — the check stopped on an unexpected error (exit %s); see stderr\n" "$name" "$rc"; exit 1; fi' EXIT
mkdir -p "$root/adapters/stub-harness" "$root/adapters/stub-tracker" "$root/adapters/stub-state" \
  "$root/roles/ops-triage" "$root/world" "$root/state" "$root/.crew"
ln -s "$repo/core" "$root/core"
ln -s "$repo/ci" "$root/ci"
ln -s "$repo/adapters/file" "$root/adapters/file"

# The one thing no case may touch: this checkout's own tickets/.
real_tickets() { find "$repo/tickets" -type f -exec cksum {} + 2>/dev/null | sort; }
real_before=$(real_tickets)

cat > "$root/roles/ops-triage/role.env" <<'ENV'
THINKING=low
TIMEOUT_S=900
HARNESS=stub-harness
ENV

# stub-harness/run.sh: the artefact contract of docs/adr/0020 §1 (calls.json,
# final.md, run.json in $OUT), the answer being whatever $root/world/calls.json
# the case wrote. world/harness-fail: exit 1. world/harness-silent: exit 0
# with no artefacts. The log line carries the role it was asked to run.
cat > "$root/adapters/stub-harness/run.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
: "${OUT:?OUT not set}"
mkdir -p "$OUT"
printf 'harness-called role=%s\n' "${ROLE:-}" >> "$d/harness.log"
if [ -n "${INPUT:-}" ] && [ -f "$INPUT" ]; then cp "$INPUT" "$d/world/harness-input.json"; fi
if [ -f "$d/world/harness-fail" ]; then
  printf 'stub-harness: told to fail\n' >&2
  exit 1
fi
[ ! -f "$d/world/harness-silent" ] || exit 0
cp "$d/world/calls.json" "$OUT/calls.json"
printf 'stub post mortem run\n' > "$OUT/final.md"
printf '{"harness":"stub-harness","model":"stub-model-7"}\n' > "$OUT/run.json"
STUB

# stub-tracker/put.sh: logs the call, then is the real file Tracker -- unless
# world/put-fail holds a glob that the origin matches, when it refuses the way
# an adapter does: one stderr line, exit 1 (docs/adr/0044 §6).
cat > "$root/adapters/stub-tracker/put.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
printf 'put %s | %s\n' "$1" "$2" >> "$d/tracker.log"
if [ -f "$d/world/put-fail" ]; then
  pat=$(cat "$d/world/put-fail")
  case "$2" in
    $pat) printf 'stub-tracker: refusing %s\n' "$2" >&2; exit 1 ;;
  esac
fi
exec sh "$d/adapters/file/put.sh" "$@"
STUB

# stub-state/get.sh: the StateStore verb, over $root/state/<collection>.<id>.json.
cat > "$root/adapters/stub-state/get.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
printf 'get %s %s\n' "$1" "$2" >> "$d/state.log"
f="$d/state/$1.$2.json"
[ -f "$f" ] || { printf 'stub-state: no document %s/%s\n' "$1" "$2" >&2; exit 1; }
cat "$f"
STUB

cd "$root"
tdir="$root/tickets"
stdout_f="$root/stdout"
log="$root/run.log"
: > "$log"

mismatch=""
fail_case() {  # CASE REASON: every disagreement is reported, the first is named
  [ -n "$mismatch" ] || mismatch=$1
  printf 'ci-postmortem: %s: %s\n' "$1" "$2" >&2
  if [ -s "$log" ]; then head -n 6 "$log" | sed 's/^/    | /' >&2; fi
}

# run_sh SCRIPT [VAR=val...]: sets $out, $rc and $nlines. A scrubbed
# environment, stdin /dev/null; the plane is an address that resolves nowhere.
run_sh() {
  script=$1
  shift
  env -i PATH="$PATH" HOME="$root" PLANE_HOST=nowhere.invalid AGENT_HARNESS=stub-harness \
    TRACKER=stub-tracker STATE_STORE=stub-state TICKETS_DIR="$tdir" "$@" \
    sh "$script" >"$stdout_f" 2>"$log" </dev/null && rc=0 || rc=$?
  out=$(cat "$stdout_f")
  nlines=$(awk 'END{print NR}' "$stdout_f")
}
shape() {  # CASE RC: stdout is one line and the exit code agrees
  [ "$nlines" -eq 1 ] || fail_case "$1" "stdout has $nlines lines, want 1: $out"
  [ "$rc" -eq "$2" ] || fail_case "$1" "exit $rc, want $2"
}
snap() { find "$tdir" -type f -exec cksum {} + 2>/dev/null | sort; }
names() { find "$1" -type f 2>/dev/null | sed 's|.*/||' | sort | tr '\n' ' '; }
lines_in() { awk 'END{print NR}' "$1"; }
sum_of() { if [ -f "$1" ]; then cksum < "$1"; else printf 'missing'; fi; }

# --- the documents, written out from the ADR ---
sha1=0123456789abcdef0123456789abcdef01234567
sha2=fedcba9876543210fedcba9876543210fedcba98
chain="{\"ticket\":\"0012\",\"pr\":7,\"merge\":\"$sha1\"}"

# The incident of docs/adr/0044 §1, release rolled back at the 25% stage, one
# alert (the stage that is not GO), no chain. The alert is derived below by the
# §2 rule; the log lines carry characters a careless writer would mangle.
cat > "$root/world/base-raw.json" <<'JSON'
{
  "kind": "incident",
  "name": "pm-demo",
  "window": {"from": "2026-11-04T10:00:00Z", "to": "2026-11-04T10:05:00Z"},
  "release": {
    "version": "0.2.0-waitlist",
    "stable": "0.1.0-m2",
    "stages": [
      {"pct": 5, "verdict": "GO", "numbers": ["slo: traffic canary(0.2.0-waitlist)=0.208 stable(0.1.0-m2)=4.018"]},
      {"pct": 25, "verdict": "NO-GO: launchpad — 25%: error_rate 1.000 → rolled back", "numbers": ["slo: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000", "slo: latency_p95 canary(0.2.0-waitlist)=0.120 stable(0.1.0-m2)=0.110"]}
    ],
    "verdict": "rolled-back",
    "held_at": null,
    "image": "stub-image"
  },
  "alerts": [],
  "logs": [
    "[launchpad] shifting 5% to 0.2.0-waitlist",
    "slo: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000",
    "[launchpad] 25%: NO-GO \"error_rate\" 100% \\ $HOME rolled back"
  ],
  "chain": null
}
JSON
jq -c '.alerts = [.release as $r | $r.stages[] | select(.verdict != "GO") | {headline: .verdict, version: $r.version, stable: $r.stable, stage: .}]' \
  "$root/world/base-raw.json" > "$root/world/base.json"
[ "$(jq '.alerts | length' "$root/world/base.json")" -eq 1 ] || { settled=1; nogo "ci/postmortem.sh: the base incident has no alert; the check itself is broken"; }
base="$root/world/base.json"
rec="$root/world/record.json"
logs="$root/world/logs.txt"
jq -c .release "$base" > "$rec"
jq -r '.logs[]' "$base" > "$logs"

# mk_inc FILE FILTER [jq args]: the base incident, changed by FILTER.
mk_inc() {
  f=$1
  flt=$2
  shift 2
  jq -c "$@" "$flt" "$base" > "$f"
}

# What the ops-triage role says: file_postmortem(title, timeline, causes,
# actions) of docs/adr/0044 §4. Texts carry markers (TL1, PROB1) so that a
# check can find them, and characters a careless writer would mangle.
cat > "$root/world/args-base.json" <<'JSON'
{
  "title": "Cold cache turned the waitlist endpoint into a 100% 5xx",
  "timeline": [
    {"event": "TL1 The canary 0.2.0-waitlist is released.", "anchor": "release:0.2.0-waitlist"},
    {"event": "TL2 At 5% the SLO gate passes.", "anchor": "release:0.2.0-waitlist@5"},
    {"event": "TL3 At 25% the error rate is 1.000.", "anchor": "release:0.2.0-waitlist@25"},
    {"event": "TL4 launchpad logs the rollback.", "anchor": "log:3"},
    {"event": "TL5 The alert names the 25% stage.", "anchor": "alert:1"}
  ],
  "causes": [
    {"cause": "CAUSE1 the endpoint fails once its cache is cold", "evidence": "the 25% stage error_rate"}
  ],
  "actions": [
    {"title": "Test the cold-cache path of /waitlist & the \"retry\" (100% of $HOME)", "problem": "PROB1 nothing exercises a cold cache; \"retry\" & 100% of $HOME \\ stay", "acceptance": "ACC1 a test fails when the cache is empty"},
    {"title": "Alert on canary error_rate at 5%", "problem": "PROB2 the 5% stage passed and the 25% one did not", "acceptance": "ACC2 the 5% stage fails on a cold cache"}
  ]
}
JSON
args_base="$root/world/args-base.json"
calls_with() {  # FILTER [jq args]: calls.json = one file_postmortem call, args changed by FILTER
  flt=$1
  shift
  jq -n -c --slurpfile base "$args_base" "$@" "[{name: \"file_postmortem\", args: (\$base[0] | $flt)}]" > "$root/world/calls.json"
}
# shellcheck disable=SC2016 # $sha is a jq variable
chain_tl='.timeline = [{event: "TL0a Ticket 0012 is opened.", anchor: "ticket:0012"}, {event: "TL0b PR 7 is opened.", anchor: "pr:7"}, {event: "TL0c The PR is merged.", anchor: ("merge:" + $sha)}] + .timeline'
calls_raw() { printf '%s\n' "$1" > "$root/world/calls.json"; }

reset() {  # a clean world for one case: seeded tickets, empty logs, no output, a good answer
  rm -rf "$root/.crew" "$tdir" "$root/world/harness-fail" "$root/world/harness-silent" \
    "$root/world/put-fail" "$root/world/harness-input.json"
  mkdir -p "$root/.crew" "$tdir"
  printf '# 0001 — first seed ticket\n\n- Status: done\n' > "$tdir/0001.md"
  printf '# 0007 — seventh seed ticket\n\n- Status: open\n' > "$tdir/0007.md"
  : > "$root/harness.log"
  : > "$root/tracker.log"
  : > "$root/state.log"
  calls_with '.'
}

# ---------------------------------------------------------------------------
# A. adapters/file/put.sh alone (docs/adr/0044 §6)
# ---------------------------------------------------------------------------
run_put() {  # DIR TITLE ORIGIN: the body on stdin is world/body.md
  env -i PATH="$PATH" HOME="$root" TICKETS_DIR="$1" sh adapters/file/put.sh "$2" "$3" \
    >"$stdout_f" 2>"$log" <"$root/world/body.md" && rc=0 || rc=$?
  out=$(cat "$stdout_f")
  nlines=$(awk 'END{print NR}' "$stdout_f")
}
printf '## Problem\nBODY1 line one\n\n## Acceptance criteria\nBODY2 line two\n' > "$root/world/body.md"
putdir="$root/put"

# u1: seeded 0001 and 0007 -> 0008 (highest + 1, not the first gap, not the
# count + 1), padded, stdout only the id, the file exactly the spec's.
rm -rf "$putdir"
mkdir -p "$putdir"
printf '# 0001 — a\n' > "$putdir/0001.md"
printf '# 0007 — b\n' > "$putdir/0007.md"
# shellcheck disable=SC2016 # a literal $HOME and \n are the point
title_hard='Fix 5xx on /api & the "retry" (100% of $HOME \n)'
run_put "$putdir" "$title_hard" "postmortem x action 1"
shape u1-stdout 0
[ "$out" = 0008 ] || fail_case u1-id "stdout: $out, want only 0008"
printf '# 0008 — %s\n\n- Status: open\n- Origin: postmortem x action 1\n\n' "$title_hard" > "$root/world/want-ticket.md"
cat "$root/world/body.md" >> "$root/world/want-ticket.md"
cmp -s "$root/world/want-ticket.md" "$putdir/0008.md" 2>/dev/null || fail_case u1-file "0008.md is not '# <id> — <title>', blank, '- Status: open', '- Origin: <origin>', blank, then stdin"
[ "$(names "$putdir")" = "0001.md 0007.md 0008.md " ] || fail_case u1-files "files: $(names "$putdir")"
[ "$(grep -c '^## Perimeter' "$putdir/0008.md" || true)" = 0 ] || fail_case u1-perimeter "put.sh added a ## Perimeter"

# u2: the same origin again -> the same id, nothing written, nothing rewritten
# (a new title and body change nothing).
before=$(sum_of "$putdir/0008.md")
printf 'OTHER BODY\n' > "$root/world/other-body.md"
env -i PATH="$PATH" HOME="$root" TICKETS_DIR="$putdir" sh adapters/file/put.sh "A different title" "postmortem x action 1" \
  >"$stdout_f" 2>"$log" <"$root/world/other-body.md" && rc=0 || rc=$?
out=$(cat "$stdout_f")
nlines=$(awk 'END{print NR}' "$stdout_f")
shape u2-stdout 0
[ "$out" = 0008 ] || fail_case u2-id "stdout: $out, want the existing 0008"
[ "$(sum_of "$putdir/0008.md")" = "$before" ] || fail_case u2-rewrite "an existing ticket was rewritten"
[ "$(names "$putdir")" = "0001.md 0007.md 0008.md " ] || fail_case u2-files "a file was added: $(names "$putdir")"

# u3: another origin -> the next id.
run_put "$putdir" "Second" "postmortem x action 2"
shape u3-stdout 0
[ "$out" = 0009 ] || fail_case u3-id "stdout: $out, want 0009"

# u4: an origin is a whole line, compared literally: action 1 is not action
# 10, and a dot is not any character.
rm -rf "$putdir"
mkdir -p "$putdir"
run_put "$putdir" "Ten" "postmortem x action 10"
[ "$out" = 0001 ] || fail_case u4-premise "an empty directory gave $out, want 0001"
run_put "$putdir" "One" "postmortem x action 1"
[ "$out" = 0002 ] || fail_case u4-prefix "origin 'action 1' got $out, the id of 'action 10' is 0001: a longer origin was taken for it"
run_put "$putdir" "Plain" "postmortem yxz action 1"
[ "$out" = 0003 ] || fail_case u4-premise-2 "got '$out', want 0003"
run_put "$putdir" "Dotted" "postmortem y.z action 1"
[ "$out" = 0004 ] || fail_case u4-regex "origin 'y.z' got $out, 'yxz' is 0003: the origin was read as a pattern"

# u5: ids that are not octal. 0009 -> 0010, 0099 -> 0100, 0008 -> 0009.
for pair in 0009:0010 0099:0100 0008:0009; do
  rm -rf "$putdir"
  mkdir -p "$putdir"
  printf '# x\n' > "$putdir/${pair%%:*}.md"
  run_put "$putdir" "T" "postmortem o action 1"
  [ "$out" = "${pair##*:}" ] || fail_case "u5-${pair%%:*}" "after ${pair%%:*} got '$out' (rc $rc), want ${pair##*:}"
done

# u6: names that are not ids are not counted.
rm -rf "$putdir"
mkdir -p "$putdir"
printf '# x\n' > "$putdir/0003.md"
printf '# x\n' > "$putdir/README.md"
printf '# x\n' > "$putdir/12-notes.md"
printf '# x\n' > "$putdir/9999.txt"
run_put "$putdir" "T" "postmortem o action 1"
[ "$out" = 0004 ] || fail_case u6-ignored "got '$out' (rc $rc), want 0004: only numeric *.md names are ids"

# u7: a failure is one stderr line and exit 1, with nothing on stdout.
printf 'not a directory\n' > "$root/world/not-a-dir"
run_put "$root/world/not-a-dir" "T" "postmortem o action 1"
[ "$rc" -eq 1 ] || fail_case u7-exit "a tickets path that is a file: exit $rc, want 1"
[ ! -s "$stdout_f" ] || fail_case u7-stdout "stdout is not empty on a failure: $out"
[ "$(lines_in "$log")" -eq 1 ] || fail_case u7-stderr "stderr has $(lines_in "$log") lines, want 1"
env -i PATH="$PATH" HOME="$root" TICKETS_DIR="$putdir" sh adapters/file/put.sh >"$stdout_f" 2>"$log" </dev/null && rc=0 || rc=$?
[ "$rc" -eq 1 ] || fail_case u7-args "no arguments: exit $rc, want 1"
[ ! -s "$stdout_f" ] || fail_case u7-args-stdout "stdout is not empty with no arguments"
[ "$(lines_in "$log")" -eq 1 ] || fail_case u7-args-stderr "no arguments: stderr has $(lines_in "$log") lines, want 1"

# ---------------------------------------------------------------------------
# B. core/incident.sh on canned records (docs/adr/0044 §1, §2)
# ---------------------------------------------------------------------------
inc_out="$root/.crew/incidents/pm-demo.json"
inc_reset() { rm -rf "$root/.crew/incidents" "$root/state.log"; : > "$root/state.log"; }
# inc_run [VAR=val...]: NAME, FROM and TO default to the base incident's.
inc_run() {
  run_sh core/incident.sh NAME=pm-demo FROM=2026-11-04T10:00:00Z TO=2026-11-04T10:05:00Z "$@"
}
inc_files() { find "$root/.crew/incidents" -type f 2>/dev/null | wc -l | tr -d ' '; }
want_inc_go() {  # CASE
  shape "$1" 0
  case "$out" in "GO: incident — "*".crew/incidents/pm-demo.json") : ;; *) fail_case "$1" "stdout: $out, want GO: incident — <path>.crew/incidents/pm-demo.json" ;; esac
  [ -f "$inc_out" ] || fail_case "$1" "no document at $inc_out"
}
want_inc_nogo() {  # CASE [PATTERN]
  shape "$1" 1
  # shellcheck disable=SC2254 # the pattern is a glob on purpose
  case "$out" in "NO-GO: incident — "${2:-?*}) : ;; *) fail_case "$1" "stdout: $out, want NO-GO: incident — ${2:-?*}" ;; esac
  [ "$(inc_files)" -eq 0 ] || fail_case "$1" "a document was left behind after a NO-GO: $(find "$root/.crew/incidents" -type f)"
}
same_json() {  # CASE GOT WANT: the same JSON, whatever the key order
  [ "$(jq -S -c . "$2" 2>/dev/null)" = "$(jq -S -c . "$3")" ] || fail_case "$1" "the incident differs from the spec's: got $(jq -S -c . "$2" 2>&1 | head -c 600) want $(jq -S -c . "$3" | head -c 600)"
}
# A store document for ticket 0012: what the tower holds for a rolled-back release.
store_doc() {  # VERSION
  jq -n -c --arg v "$1" --arg sha "$sha1" \
    '{state: "rolled-back", release: {version: $v, verdict: "rolled-back", image: "stub-image"}, pr: {number: 7, url: "stub://pr/7"}, merge: {sha: $sha}}' \
    > "$root/state/tickets.0012.json"
}

# i-a: no TICKET: the document is the spec's, chain is null, and the store is
# not needed (the adapter named does not exist).
inc_reset
inc_run RELEASE_RECORD="$rec" LOGS="$logs" STATE_STORE=no-such-store
want_inc_go i-a
same_json i-a "$inc_out" "$base"
cp "$inc_out" "$root/world/first.json" 2>/dev/null || :
inc_run RELEASE_RECORD="$rec" LOGS="$logs" STATE_STORE=no-such-store
cmp -s "$root/world/first.json" "$inc_out" || fail_case i-a-bytes "two runs on the same inputs gave different bytes"

# i-b: TICKET, a store document that agrees: chain from the tower's own
# .pr.number and .merge.sha, read through get.sh <collection> <id>.
inc_reset
store_doc 0.2.0-waitlist
mk_inc "$root/world/want-chain.json" ".chain = $chain"
inc_run RELEASE_RECORD="$rec" LOGS="$logs" TICKET=0012
want_inc_go i-b
same_json i-b "$inc_out" "$root/world/want-chain.json"
[ "$(cat "$root/state.log")" = "get tickets 0012" ] || fail_case i-b-store "the store was asked: $(tr '\n' '|' < "$root/state.log"), want exactly 'get tickets 0012'"
cp "$inc_out" "$root/world/first.json" 2>/dev/null || :
inc_run RELEASE_RECORD="$rec" LOGS="$logs" TICKET=0012
cmp -s "$root/world/first.json" "$inc_out" || fail_case i-b-bytes "two runs with a TICKET gave different bytes"

# i-c: the document's release is another version: NO-GO, nothing written.
inc_reset
store_doc 9.9.9
inc_run RELEASE_RECORD="$rec" LOGS="$logs" TICKET=0012
want_inc_nogo i-c

# i-d: no such document in the store: NO-GO, nothing written.
inc_reset
inc_run RELEASE_RECORD="$rec" LOGS="$logs" TICKET=0099
want_inc_nogo i-d

# i-e: a held record: no stage is not GO, so no alert; no LOGS, so no log lines.
inc_reset
jq -c '.stages |= map(.verdict = "GO") | .verdict = "held" | .held_at = 25' "$rec" > "$root/world/held.json"
jq -c --slurpfile r "$root/world/held.json" '.release = $r[0] | .alerts = [] | .logs = []' "$base" > "$root/world/want-held.json"
inc_run RELEASE_RECORD="$root/world/held.json"
want_inc_go i-e
same_json i-e "$inc_out" "$root/world/want-held.json"

# i-f: one alert per stage that is not GO, in order, whatever the stage's
# position: GO, NO-GO, NO-GO is two alerts.
inc_reset
jq -c '.stages = [{pct: 5, verdict: "GO", numbers: ["slo: a"]}, {pct: 25, verdict: "NO-GO: x — 25%", numbers: ["slo: b"]}, {pct: 50, verdict: "NO-GO: y — 50%", numbers: ["slo: c"]}]' "$rec" > "$root/world/three.json"
inc_run RELEASE_RECORD="$root/world/three.json"
want_inc_go i-f
jq -e --slurpfile r "$root/world/three.json" \
  '(.alerts | length) == 2 and .alerts[0].headline == "NO-GO: x — 25%" and .alerts[1].headline == "NO-GO: y — 50%"
   and (.alerts | all(.[]; keys == ["headline", "stable", "stage", "version"] and .version == "0.2.0-waitlist" and .stable == "0.1.0-m2"))
   and .alerts[0].stage == $r[0].stages[1] and .alerts[1].stage == $r[0].stages[2]' "$inc_out" >/dev/null 2>&1 \
  || fail_case i-f-alerts "alerts: $(jq -c .alerts "$inc_out" 2>&1 | head -c 500)"

# i-g: an in-progress record is not a verdict.
inc_reset
jq -c '.verdict = "in-progress"' "$rec" > "$root/world/inprogress.json"
inc_run RELEASE_RECORD="$root/world/inprogress.json" LOGS="$logs"
want_inc_nogo i-g '*in-progress*'

# i-h: no record at all.
inc_reset
inc_run RELEASE_RECORD="$root/world/no-such-record.json"
want_inc_nogo i-h

# i-i: RELEASE_RECORD defaults to .crew/release.json.
inc_reset
cp "$rec" "$root/.crew/release.json"
inc_run LOGS="$logs"
want_inc_go i-i
same_json i-i "$inc_out" "$base"
rm -f "$root/.crew/release.json"

# i-j: a LOGS file that is not there.
inc_reset
inc_run RELEASE_RECORD="$rec" LOGS="$root/world/no-such-logs.txt"
want_inc_nogo i-j

# i-k: log lines are copied verbatim: leading blanks, a tab, non-ASCII.
inc_reset
printf '  indented line\nwith\ttab\n日本語 ünïcode\nlast "quoted" line\n' > "$root/world/odd-logs.txt"
inc_run RELEASE_RECORD="$rec" LOGS="$root/world/odd-logs.txt"
want_inc_go i-k
jq -n -c --rawfile l "$root/world/odd-logs.txt" '$l | split("\n")[:-1]' > "$root/world/want-logs.json"
[ "$(jq -c .logs "$inc_out" 2>/dev/null)" = "$(cat "$root/world/want-logs.json")" ] || fail_case i-k-logs "logs: $(jq -c .logs "$inc_out" 2>&1), want $(cat "$root/world/want-logs.json")"

# i-l: a NAME that is not ^[a-z0-9][a-z0-9-]*$ is a NO-GO, and nothing is written.
for n in Bad_Name -x 'a/b' ../x 'a b' ''; do
  inc_reset
  inc_run NAME="$n" RELEASE_RECORD="$rec"
  want_inc_nogo "i-l-name($n)"
done
if [ -e "$root/x.json" ] || [ -e "$root/.crew/x.json" ]; then fail_case i-l-escape "a document was written outside .crew/incidents/"; fi

# i-m: a window in the tower's format with from <= to; equal is allowed.
inc_reset
inc_run RELEASE_RECORD="$rec" FROM=2026-11-04T10:05:00Z TO=2026-11-04T10:05:00Z
want_inc_go i-m-equal
for w in 'FROM=' 'TO=' 'FROM=2026-11-04 10:00:00' 'TO=2026-11-04T10:05:00' 'FROM=2026-11-04T10:00:00+00:00' 'FROM=2026-11-04T10:06:00Z'; do
  inc_reset
  inc_run RELEASE_RECORD="$rec" "$w"
  want_inc_nogo "i-m-window($w)"
done

# ---------------------------------------------------------------------------
# C. core/postmortem.sh (docs/adr/0044 §3-§5)
# ---------------------------------------------------------------------------

# pm_nogo CASE INCIDENT PATTERN HARNESS_CALLS: a NO-GO whose reason matches
# PATTERN (a glob after "NO-GO: postmortem — "), exit 1, the harness called
# HARNESS_CALLS times, no call to the Tracker, the tickets directory as it
# was, no file under .crew/postmortem/, the state store untouched.
pm_nogo() {
  before=$(snap)
  run_sh core/postmortem.sh INCIDENT="$2"
  shape "$1" 1
  # shellcheck disable=SC2254 # the pattern is a glob on purpose
  case "$out" in "NO-GO: postmortem — "$3) : ;; *) fail_case "$1" "stdout: $out, want NO-GO: postmortem — $3" ;; esac
  calls=$(lines_in "$root/harness.log")
  [ "$calls" -eq "$4" ] || fail_case "$1" "the harness was called $calls time(s), want $4"
  [ ! -s "$root/tracker.log" ] || fail_case "$1" "the Tracker was called before the checks passed: $(tr '\n' '|' < "$root/tracker.log")"
  [ "$(snap)" = "$before" ] || fail_case "$1" "the tickets directory changed"
  [ -z "$(find "$root/.crew/postmortem" -type f 2>/dev/null)" ] || fail_case "$1" "output left under .crew/postmortem/ after a NO-GO: $(find "$root/.crew/postmortem" -type f | tr '\n' ' ')"
  [ ! -s "$root/state.log" ] || fail_case "$1" "the state store was called: $(tr '\n' '|' < "$root/state.log")"
}

inc="$root/world/inc.json"
inc_chain="$root/world/inc-chain.json"
cp "$base" "$inc"
mk_inc "$inc_chain" ".chain = $chain"

# --- P1: no incident at the path ---
reset
pm_nogo p1 "$root/world/no-such-incident.json" "no incident at $root/world/no-such-incident.json" 0
reset
pm_nogo p1-unset "" '?*' 0

# --- P2: not an incident document ---
p2() {  # LABEL FILTER: the base incident, changed by FILTER, is refused before the harness
  reset
  mk_inc "$root/world/p2.json" "$2"
  pm_nogo "p2-$1" "$root/world/p2.json" "$root/world/p2.json is not an incident document: ?*" 0
}
reset
printf '{ this is not json\n' > "$root/world/p2.json"
pm_nogo p2-not-json "$root/world/p2.json" "$root/world/p2.json is not an incident document: ?*" 0
reset
: > "$root/world/p2.json"
pm_nogo p2-empty-file "$root/world/p2.json" "$root/world/p2.json is not an incident document: ?*" 0
p2 no-kind 'del(.kind)'
p2 kind-alert '.kind = "alert"'
p2 name-upper '.name = "Bad_Name"'
p2 name-empty '.name = ""'
p2 name-dash '.name = "-x"'
p2 name-slash '.name = "../x"'
p2 name-space '.name = "a b"'
p2 name-missing 'del(.name)'
p2 window-missing 'del(.window)'
p2 window-from-format '.window.from = "2026-11-04 10:00:00"'
p2 window-to-format '.window.to = "2026-11-04T10:05:00"'
p2 window-offset '.window.from = "2026-11-04T10:00:00+00:00"'
p2 window-reversed '.window = {from: "2026-11-04T10:05:00Z", to: "2026-11-04T10:00:00Z"}'
p2 release-missing 'del(.release)'
p2 release-not-object '.release = "0.2.0-waitlist"'
p2 alerts-missing 'del(.alerts)'
p2 alerts-not-array '.alerts = "none"'
p2 logs-not-array '.logs = "a line"'
p2 logs-not-strings '.logs = [1, 2]'
p2 chain-partial '.chain = {ticket: "0012"}'
p2 chain-string '.chain = "0012"'

# --- P3: a release that is still in progress ---
reset
mk_inc "$root/world/p3.json" '.release.verdict = "in-progress"'
pm_nogo p3 "$root/world/p3.json" "release 0.2.0-waitlist is in-progress" 0
# a verdict that is none of held, rolled-back, in-progress: refused too (A10).
reset
mk_inc "$root/world/p3b.json" '.release.verdict = "GO"'
pm_nogo p3-other-verdict "$root/world/p3b.json" '?*' 0

# --- P4: the role did not finish ---
reset
: > "$root/world/harness-fail"
pm_nogo p4 "$inc" "the ops-triage role did not finish (stub-harness)" 1
reset
: > "$root/world/harness-silent"
pm_nogo p4-silent "$inc" '?*' 1

# --- P5: exactly one file_postmortem, nothing else ---
reset
calls_raw '[{"name":"file_incident","args":{"title":"t","hypotheses":[]}},{"name":"propose_rollback","args":{"version":"0.2.0-waitlist","reason":"r"}}]'
pm_nogo p5-triage-sequence "$inc" 'expected exactly file_postmortem, got: *file_incident*propose_rollback*' 1
reset
calls_raw '[{"name":"propose_hold","args":{"reason":"r"}}]'
pm_nogo p5-proposal-only "$inc" 'expected exactly file_postmortem, got: *propose_hold*' 1
reset
calls_with '.'
jq -c '. + .' "$root/world/calls.json" > "$root/world/calls-two.json"
cp "$root/world/calls-two.json" "$root/world/calls.json"
pm_nogo p5-twice "$inc" 'expected exactly file_postmortem, got: *file_postmortem*file_postmortem*' 1
reset
calls_with '.'
jq -c '. + [{name: "propose_rollback", args: {version: "0.2.0-waitlist", reason: "r"}}]' "$root/world/calls.json" > "$root/world/calls-prop.json"
cp "$root/world/calls-prop.json" "$root/world/calls.json"
pm_nogo p5-with-proposal "$inc" 'expected exactly file_postmortem, got: *file_postmortem*propose_rollback*' 1
reset
calls_raw '[]'
pm_nogo p5-empty "$inc" '?*' 1

# --- P6: an anchor the document does not hold ---
p6() {  # LABEL INCIDENT ANCHOR TEXT: entry 2 carries ANCHOR, the rest are fine
  reset
  # shellcheck disable=SC2016 # $a is a jq variable
  calls_with '.timeline = [.timeline[0], {event: "TL2 bad", anchor: $a}] + .timeline[2:]' --arg a "$3"
  pm_nogo "p6-$1" "$2" "timeline entry 2: anchor \"$3\" $4" 1
}
p6 release "$inc" 'release:9.9.9' 'names no release in the incident'
p6 stage "$inc" 'release:0.2.0-waitlist@50' 'names no stage of 0.2.0-waitlist in the incident'
p6 pr-no-chain "$inc" 'pr:7' 'names no PR in the incident'
p6 merge-no-chain "$inc" "merge:$sha1" 'names no merge in the incident'
p6 ticket-no-chain "$inc" 'ticket:0012' 'names no ticket in the incident'
p6 pr-other "$inc_chain" 'pr:8' 'names no PR in the incident'
p6 merge-other "$inc_chain" "merge:$sha2" 'names no merge in the incident'
p6 ticket-other "$inc_chain" 'ticket:0013' 'names no ticket in the incident'
p6 log "$inc" 'log:4' 'names no log line in the incident'
p6 alert "$inc" 'alert:2' 'names no alert in the incident'
p6 release-longer "$inc" 'release:0.2.0-waitlist-rc1' 'names no release in the incident'
p6 release-shorter "$inc" 'release:0.2.0' 'names no release in the incident'
p6 pr-longer "$inc_chain" 'pr:70' 'names no PR in the incident'
p6 ticket-longer "$inc_chain" 'ticket:00120' 'names no ticket in the incident'
p6 unknown "$inc" 'bogus:1' 'is not a known anchor'
p6 no-colon "$inc" 'release' '?*'
p6 log-zero "$inc" 'log:0' '?*'
p6 log-word "$inc" 'log:two' '?*'
p6 merge-short "$inc_chain" 'merge:abc123' '?*'
p6 empty "$inc" '' '?*'
reset
calls_with '.timeline[1] |= del(.anchor)'
pm_nogo p6-no-anchor "$inc" '?*' 1
reset
calls_with '.timeline[1].anchor = ["release:0.2.0-waitlist", "log:1"]'
pm_nogo p6-two-anchors "$inc" '?*' 1

# --- P7: nothing anchored to the release ---
reset
calls_with '.timeline = [.timeline[3], .timeline[4]]'
pm_nogo p7 "$inc" "no timeline entry is anchored to release 0.2.0-waitlist" 1
reset
calls_with 'del(.timeline)'
pm_nogo p7-no-timeline "$inc" '?*' 1

# --- P8: the chain's PR is not in the timeline ---
reset
pm_nogo p8 "$inc_chain" "the chain has PR #7 and no timeline entry is anchored to it" 1

# --- P9: a post mortem that files nothing does not close the loop ---
reset
calls_with '.causes = []'
pm_nogo p9-no-causes "$inc" "a post mortem needs at least one contributing cause" 1
reset
calls_with 'del(.causes)'
pm_nogo p9-causes-missing "$inc" "a post mortem needs at least one contributing cause" 1
reset
calls_with '.actions = []'
pm_nogo p9-no-actions "$inc" "a post mortem needs at least one action item" 1
reset
calls_with 'del(.actions)'
pm_nogo p9-actions-missing "$inc" "a post mortem needs at least one action item" 1
reset
calls_with '.actions[1].acceptance = ""'
pm_nogo p9-empty-acceptance "$inc" "action 2 has no acceptance" 1
reset
calls_with '.actions[0] |= del(.problem)'
pm_nogo p9-missing-problem "$inc" "action 1 has no problem" 1
reset
calls_with '.actions[1].title = ""'
pm_nogo p9-empty-title "$inc" "action 2 has no title" 1

# --- P10: a ticket the Tracker would not take ---
# Fails on the last action: actions 1 and 2 are filed and stay, 3 is not, and
# nothing is written as output. A re-run picks up the two and files the third.
reset
calls_with '.actions += [{title: "Third action", problem: "PROB3 third", acceptance: "ACC3 third"}]'
printf '*action 3\n' > "$root/world/put-fail"
run_sh core/postmortem.sh INCIDENT="$inc"
shape p10 1
case "$out" in "NO-GO: postmortem — action 3 has no ticket: "*"stub-tracker: refusing"*) : ;; *) fail_case p10 "stdout: $out, want NO-GO: postmortem — action 3 has no ticket: <the adapter's line>" ;; esac
[ "$(lines_in "$root/harness.log")" -eq 1 ] || fail_case p10-harness "the harness was called $(lines_in "$root/harness.log") times, want 1"
if [ ! -f "$tdir/0008.md" ] || [ ! -f "$tdir/0009.md" ]; then fail_case p10-filed "tickets for actions 1 and 2 are not in the directory: $(names "$tdir")"; fi
[ ! -e "$tdir/0010.md" ] || fail_case p10-third "a ticket exists for the action the Tracker refused"
[ -z "$(find "$root/.crew/postmortem" -type f 2>/dev/null)" ] || fail_case p10-output "output left under .crew/postmortem/ after P10"
grep -Fxq -- '- Origin: postmortem pm-demo action 1' "$tdir/0008.md" 2>/dev/null || fail_case p10-origin-1 "0008.md is not action 1's ticket"
rm -f "$root/world/put-fail"
run_sh core/postmortem.sh INCIDENT="$inc"
shape p10-rerun 0
[ "$out" = "GO: postmortem — 3 action item(s): tickets 0008 0009 0010" ] || fail_case p10-rerun-ids "stdout: $out, want the two filed tickets picked up and a third filed: 0008 0009 0010"
[ "$(names "$tdir")" = "0001.md 0007.md 0008.md 0009.md 0010.md " ] || fail_case p10-rerun-files "files: $(names "$tdir")"

# P10 with the Tracker down altogether: the first action has no ticket.
reset
printf '*\n' > "$root/world/put-fail"
pm_nogo_tracker_down() {
  before=$(snap)
  run_sh core/postmortem.sh INCIDENT="$inc"
  shape p10-down 1
  case "$out" in "NO-GO: postmortem — action 1 has no ticket: "*"stub-tracker: refusing"*) : ;; *) fail_case p10-down "stdout: $out, want NO-GO: postmortem — action 1 has no ticket: <the adapter's line>" ;; esac
  [ "$(snap)" = "$before" ] || fail_case p10-down-tickets "the tickets directory changed"
  [ -z "$(find "$root/.crew/postmortem" -type f 2>/dev/null)" ] || fail_case p10-down-output "output left under .crew/postmortem/"
}
pm_nogo_tracker_down

# --- the GO path ---
# What the ADR says the artefacts hold, derived from the documents the case
# gave, never from what core wrote.
expected_evidence() {  # INCIDENT ANCHOR: the evidence lines core prints for ANCHOR (§3)
  jq -r --arg a "$2" '
    . as $i | ($a | capture("^(?<kind>[a-z]+):(?<rest>.*)$")) as $m |
    if $m.kind == "release" then
      ($m.rest | split("@")) as $p |
      if ($p | length) == 1 then [$i.release.version, $i.release.verdict, $i.release.image][]
      else ($i.release.stages[] | select(.pct == ($p[1] | tonumber)) | .verdict, .numbers[])
      end
    elif $m.kind == "log" then $i.logs[($m.rest | tonumber) - 1]
    elif $m.kind == "alert" then $i.alerts[($m.rest | tonumber) - 1].headline
    else $m.rest end' "$1"
}
md_section() {  # FILE HEADING: the lines under HEADING up to the next "## "
  awk -v h="$2" '$0 == h { on = 1; next } /^## / { on = 0 } on' "$1"
}
md_under() {  # FILE EVENT NEXT WANT: WANT is on EVENT's line or after it, before NEXT's
  EV=$2 NX=$3 WT=$4 awk '
    BEGIN { ev = ENVIRON["EV"]; nx = ENVIRON["NX"]; wt = ENVIRON["WT"] }
    !seen && index($0, ev) { seen = 1 }
    seen && nx != "" && index($0, nx) { exit }
    seen && index($0, wt) { found = 1 }
    END { exit !found }' "$1"
}

verify_files() {  # CASE INCIDENT NAME IDS...: postmortem.json and postmortem.md
  c=$1
  incf=$2
  nm=$3
  shift 3
  pdir="$root/.crew/postmortem/$nm"
  pj="$pdir/postmortem.json"
  pmd="$pdir/postmortem.md"
  if [ ! -f "$pj" ] || [ ! -f "$pmd" ]; then
    fail_case "$c" "postmortem.json or postmortem.md is missing under $pdir"
    return 0
  fi
  for f in calls.json final.md run.json; do
    [ -f "$pdir/out/$f" ] || fail_case "$c" "out/$f is missing under $pdir"
  done
  [ "$(jq -S -c . "$pdir/out/calls.json" 2>/dev/null)" = "$(jq -S -c . "$root/world/calls.json")" ] \
    || fail_case "$c" "out/calls.json is not the harness's calls.json"
  jq -e --slurpfile inc "$incf" --slurpfile calls "$root/world/calls.json" --arg ids "$*" '
    ($calls[0][0].args) as $a | $inc[0] as $i | . as $out |
    (keys == ["actions", "causes", "chain", "incident", "release", "run", "timeline", "title", "window"])
    and .title == $a.title
    and .window == $i.window
    and .chain == $i.chain
    and (.release | keys) == ["image", "stable", "verdict", "version"]
    and .release.version == $i.release.version and .release.stable == $i.release.stable
    and .release.verdict == $i.release.verdict and .release.image == $i.release.image
    and ((.incident | tostring) | contains($i.name))
    and (.timeline | length) == ($a.timeline | length)
    and ([.timeline[] | keys == ["anchor", "event", "evidence"]] | all)
    and [.timeline[].anchor] == [$a.timeline[].anchor]
    and [.timeline[].event] == [$a.timeline[].event]
    and ([.timeline[] | (.evidence | type == "array" and length > 0 and all(.[]; type == "string"))] | all)
    and (.causes | length) == ($a.causes | length)
    and ([$a.causes[].cause as $c | ($out.causes | tostring | contains($c))] | all)
    and ([.actions[] | keys == ["n", "ticket", "title"]] | all)
    and [.actions[].n] == [range(1; ($a.actions | length) + 1)]
    and [.actions[].title] == [$a.actions[].title]
    and [.actions[].ticket] == ($ids | split(" "))
    and ((.run | tostring) | contains("stub-model-7"))' "$pj" >/dev/null 2>"$log" \
    || fail_case "$c" "postmortem.json does not hold what ADR §5(e) lists: $(jq -c 'del(.timeline)' "$pj" 2>&1 | head -c 700)"

  # Each timeline entry's evidence, in the json.
  n=$(jq '.[0].args.timeline | length' "$root/world/calls.json")
  i=0
  while [ "$i" -lt "$n" ]; do
    anchor=$(jq -r ".[0].args.timeline[$i].anchor" "$root/world/calls.json")
    expected_evidence "$incf" "$anchor" > "$root/world/want-evidence.txt"
    got=$(jq -r ".timeline[$i].evidence | map(tostring) | join(\"\\n\")" "$pj" 2>/dev/null || true)
    while IFS= read -r line; do
      case "$got" in
        *"$line"*) : ;;
        *) fail_case "$c" "timeline entry $((i + 1)) ($anchor): evidence in postmortem.json lacks: $line" ;;
      esac
    done < "$root/world/want-evidence.txt"
    i=$((i + 1))
  done

  # The md: title, headings in order, each event with its evidence beneath it.
  title=$(jq -r '.[0].args.title' "$root/world/calls.json")
  [ "$(sed -n 1p "$pmd")" = "# Post mortem $nm: $title" ] || fail_case "$c" "first line of postmortem.md: $(sed -n 1p "$pmd"), want: # Post mortem $nm: $title"
  prev=0
  for h in '## Timeline' '## Contributing causes' '## Action items'; do
    cnt=$(grep -Fxc -- "$h" "$pmd" || true)
    [ "$cnt" -eq 1 ] || { fail_case "$c" "postmortem.md has $cnt line(s) '$h', want 1"; continue; }
    ln=$(grep -Fxn -- "$h" "$pmd" | cut -d: -f1)
    [ "$ln" -gt "$prev" ] || fail_case "$c" "'$h' is out of order in postmortem.md"
    prev=$ln
  done
  header=$(sed -n '1,/^## Timeline$/p' "$pmd")
  for want in "$(jq -r .window.from "$incf")" "$(jq -r .window.to "$incf")" "$(jq -r .release.version "$incf")" "$(jq -r .release.verdict "$incf")"; do
    case "$header" in *"$want"*) : ;; *) fail_case "$c" "the header of postmortem.md does not hold: $want" ;; esac
  done
  if [ "$(jq -c .chain "$incf")" = null ]; then
    case "$header" in *"none: not released by the tower"*) : ;; *) fail_case "$c" "the header does not say 'none: not released by the tower' for a null chain" ;; esac
  else
    case "$header" in *"none: not released by the tower"*) fail_case "$c" "the header says the release was not by the tower, and the incident has a chain" ;; esac
    for want in "$(jq -r .chain.ticket "$incf")" "$(jq -r .chain.merge "$incf")"; do
      case "$header" in *"$want"*) : ;; *) fail_case "$c" "the header of postmortem.md does not hold the chain's $want" ;; esac
    done
    grep -Fq -- "./go audit TICKET=$(jq -r .chain.ticket "$incf")" "$pmd" || fail_case "$c" "postmortem.md does not name ./go audit TICKET=<id>"
  fi
  grep -Fq -- stub-model-7 "$pmd" || fail_case "$c" "postmortem.md has no model line from run.json (stub-model-7)"
  i=0
  while [ "$i" -lt "$n" ]; do
    ev=$(jq -r ".[0].args.timeline[$i].event" "$root/world/calls.json")
    if [ "$((i + 1))" -lt "$n" ]; then nx=$(jq -r ".[0].args.timeline[$((i + 1))].event" "$root/world/calls.json"); else nx='## Contributing causes'; fi
    anchor=$(jq -r ".[0].args.timeline[$i].anchor" "$root/world/calls.json")
    grep -Fq -- "$ev" "$pmd" || fail_case "$c" "postmortem.md does not hold the event: $ev"
    expected_evidence "$incf" "$anchor" > "$root/world/want-evidence.txt"
    while IFS= read -r line; do
      md_under "$pmd" "$ev" "$nx" "$line" || fail_case "$c" "postmortem.md: the evidence of $anchor is not printed under its event: $line"
    done < "$root/world/want-evidence.txt"
    i=$((i + 1))
  done
  md_section "$pmd" '## Contributing causes' > "$root/world/causes.txt"
  jq -r '.[0].args.causes[].cause' "$root/world/calls.json" | while IFS= read -r line; do
    grep -Fq -- "$line" "$root/world/causes.txt" || echo "$line"
  done > "$root/world/missing-causes.txt"
  [ ! -s "$root/world/missing-causes.txt" ] || fail_case "$c" "'## Contributing causes' lacks: $(cat "$root/world/missing-causes.txt")"
  md_section "$pmd" '## Action items' > "$root/world/actions.txt"
  k=0
  for id in "$@"; do
    atitle=$(jq -r ".[0].args.actions[$k].title" "$root/world/calls.json")
    A="$atitle" B="$id" awk 'index($0, ENVIRON["A"]) && index($0, ENVIRON["B"]) { f = 1 } END { exit !f }' "$root/world/actions.txt" \
      || fail_case "$c" "'## Action items' has no line with both '$atitle' and its ticket $id"
    k=$((k + 1))
  done
  return 0
}

verify_tickets() {  # CASE INCIDENT IDS...: ticket k is action k, filed as the ADR says
  c=$1
  incf=$2
  shift 2
  nm=$(jq -r .name "$incf" 2>/dev/null || true)
  ver=$(jq -r .release.version "$incf" 2>/dev/null || true)
  vd=$(jq -r .release.verdict "$incf" 2>/dev/null || true)
  k=0
  for id in "$@"; do
    f="$tdir/$id.md"
    if [ ! -f "$f" ]; then
      fail_case "$c" "no ticket file $f for action $((k + 1))"
      k=$((k + 1))
      continue
    fi
    atitle=$(jq -r ".[0].args.actions[$k].title" "$root/world/calls.json")
    prob=$(jq -r ".[0].args.actions[$k].problem" "$root/world/calls.json")
    acc=$(jq -r ".[0].args.actions[$k].acceptance" "$root/world/calls.json")
    k=$((k + 1))
    [ "$(sed -n 1p "$f")" = "# $id — $atitle" ] || fail_case "$c" "ticket $id first line: $(sed -n 1p "$f"), want: # $id — $atitle"
    [ "$(grep -Fxc -- "- Origin: postmortem $nm action $k" "$f" || true)" -eq 1 ] || fail_case "$c" "ticket $id has not exactly one line '- Origin: postmortem $nm action $k'"
    [ "$(grep -c '^- Origin:' "$f" || true)" -eq 1 ] || fail_case "$c" "ticket $id has more than one Origin line"
    grep -Fxq -- '- Status: open' "$f" || fail_case "$c" "ticket $id has no '- Status: open' line"
    for h in '## Problem' '## Acceptance criteria' '## Notes'; do
      [ "$(grep -Fxc -- "$h" "$f" || true)" -eq 1 ] || fail_case "$c" "ticket $id has not exactly one '$h'"
    done
    [ "$(grep -c '^## Perimeter' "$f" || true)" -eq 0 ] || fail_case "$c" "ticket $id has a ## Perimeter: the role saw no code, a human declares it"
    md_section "$f" '## Problem' > "$root/world/sec.txt"
    grep -Fq -- "$prob" "$root/world/sec.txt" || fail_case "$c" "ticket $id: '## Problem' lacks the action's problem"
    grep -Fq -- "Found by the post mortem of incident \`$nm\` (release \`$ver\`, \`$vd\`)" "$root/world/sec.txt" \
      || fail_case "$c" "ticket $id: '## Problem' lacks 'Found by the post mortem of incident \`$nm\` (release \`$ver\`, \`$vd\`)'"
    md_section "$f" '## Acceptance criteria' | grep -Fq -- "$acc" || fail_case "$c" "ticket $id: '## Acceptance criteria' lacks the action's acceptance"
    md_section "$f" '## Notes' | grep -Fq -- 'ops-triage' || fail_case "$c" "ticket $id: '## Notes' does not say the ops-triage role wrote it"
  done
  return 0
}

# pm_go CASE INCIDENT NAME IDS...: a GO that files exactly those tickets.
pm_go() {
  c=$1
  incf=$2
  nm=$3
  shift 3
  : > "$root/harness.log"
  : > "$root/state.log"
  if [ ! -f "$incf" ]; then
    fail_case "$c" "there is no incident document at $incf to run the post mortem on"
    return 0
  fi
  run_sh core/postmortem.sh INCIDENT="$incf"
  shape "$c" 0
  want="GO: postmortem — $# action item(s): tickets $*"
  [ "$out" = "$want" ] || fail_case "$c" "stdout: $out, want: $want"
  [ "$(lines_in "$root/harness.log")" -eq 1 ] || fail_case "$c" "the harness was called $(lines_in "$root/harness.log") times, want 1"
  grep -Fxq 'harness-called role=ops-triage' "$root/harness.log" || fail_case "$c" "the harness was not asked for the ops-triage role: $(cat "$root/harness.log")"
  [ "$(jq -S -c . "$root/world/harness-input.json" 2>/dev/null)" = "$(jq -S -c . "$incf")" ] || fail_case "$c" "the role's input is not the incident document"
  [ ! -s "$root/state.log" ] || fail_case "$c" "the state store was called: $(tr '\n' '|' < "$root/state.log")"
  verify_files "$c" "$incf" "$nm" "$@"
  verify_tickets "$c" "$incf" "$@"
}

# g-a: no chain, the two actions become 0008 and 0009; then a re-run files
# nothing new and returns the same ids, even when the model words the actions
# otherwise; a ticket once filed is not rewritten.
reset
pm_go g-a "$inc" pm-demo 0008 0009
first_out=$out
first_snap=$(snap)
run_sh core/postmortem.sh INCIDENT="$inc"
shape g-rerun 0
[ "$out" = "$first_out" ] || fail_case g-rerun-ids "a re-run said: $out, want: $first_out"
[ "$(snap)" = "$first_snap" ] || fail_case g-rerun-files "a re-run changed the tickets directory"
calls_with '.actions[0].title = "A different title" | .actions[1].problem = "Different problem text"'
run_sh core/postmortem.sh INCIDENT="$inc"
shape g-rerun-reworded 0
[ "$out" = "$first_out" ] || fail_case g-rerun-reworded-ids "a re-run with other wording said: $out, want: $first_out"
[ "$(snap)" = "$first_snap" ] || fail_case g-rerun-reworded-files "a re-run with other wording changed the tickets directory"
# another incident, another origin: new tickets, the first two stay.
calls_with '.'
mk_inc "$root/world/inc-other.json" '.name = "pm-other"'
pm_go g-other "$root/world/inc-other.json" pm-other 0010 0011

# g-b: a chain: the post mortem anchors to the ticket, the PR and the merge,
# prints their ids as evidence and names ./go audit.
reset
calls_with "$chain_tl" --arg sha "$sha1"
pm_go g-chain "$inc_chain" pm-demo 0008 0009

# g-c: a held release, one action; the ticket says held.
reset
jq -c '.stages |= map(.verdict = "GO") | .stages[1].numbers = ["slo: traffic canary(0.2.0-waitlist)=1.040 stable(0.1.0-m2)=3.186"] | .verdict = "held" | .held_at = 25' "$rec" > "$root/world/held.json"
jq -c --slurpfile r "$root/world/held.json" '.release = $r[0] | .alerts = [] | .logs = ["[launchpad] held at 25%"]' "$base" > "$root/world/inc-held.json"
calls_with '.timeline = [.timeline[0], .timeline[2], {event: "TL4 launchpad holds.", anchor: "log:1"}] | .actions = [.actions[0]]'
pm_go g-held "$root/world/inc-held.json" pm-demo 0008

# g-d: from == to is a window.
reset
mk_inc "$root/world/inc-point.json" '.window.to = .window.from'
pm_go g-point "$root/world/inc-point.json" pm-demo 0008 0009

# g-e: core/incident.sh's own document, with a TICKET through the store, is
# accepted by core/postmortem.sh: the two halves of the ADR meet.
reset
store_doc 0.2.0-waitlist
inc_reset
inc_run RELEASE_RECORD="$rec" LOGS="$logs" TICKET=0012
want_inc_go g-e-incident
cp "$inc_out" "$root/world/inc-built.json" 2>/dev/null || :
: > "$root/state.log"
calls_with "$chain_tl" --arg sha "$sha1"
pm_go g-e "$root/world/inc-built.json" pm-demo 0008 0009

cd "$repo"
settled=1
[ "$(real_tickets)" = "$real_before" ] || nogo "the checks wrote into this checkout's tickets/; remove what they left (git status tickets/)"
[ -z "$mismatch" ] || nogo "case $mismatch disagrees with docs/adr/0044"

go
