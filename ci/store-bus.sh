#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-store-bus: proves the StateStore and EventBus conformance suites
# (docs/adr/0060 §4) and that the lean plane's two adapters pass them (§1,
# §2), cold: no plane, no engine, files under a temporary directory. In order:
#   a  gates/statestore-conformance.sh on adapters/sqlite, STATE_FILE a
#      temporary file: its GO line
#   b  gates/eventbus-conformance.sh on adapters/spool, SPOOL_FILE a
#      temporary file, SPOOL_ACK_DEADLINE=2 and CONFORMANCE_ACK_DEADLINE=2
#      (a decision of ADR 0060 §4: a redelivery `./go ci` can wait for): its
#      GO line with all six cases, so case 5 ran; run beside c, judged after
#   c  each suite can fail. A temporary tree holds symlinks to this repo's
#      gates/, ci/ and core/ (where the suites' cases are, docs/adr/0084),
#      so the suites run unchanged from its root, and one stub StateStore
#      and one stub EventBus in sh over plain files, each with a BREAK=<n>
#      switch that breaks exactly one behaviour. Each stub with
#      BREAK unset must get GO (a fair baseline), each break a NO-GO naming
#      the case it breaks, and the suites must have cleaned up after
#      themselves, a NO-GO or not. A message that is not the suite's must
#      still be on the bus after a case 0 NO-GO and after the clean-up.
#   d  cold, with no CONFORMANCE, each suite prints one NO-GO line naming
#      CONFORMANCE=1 and exits 1: with no store set (what ci/contract.sh
#      sees), and with a store set and nothing written to it.
# The stubs are written here from docs/adr/0019 §2, §3 and docs/adr/0060 §1,
# §2, never from an adapter. adapters/sqlite and adapters/spool are driven
# after their own ready.sh, as `make up` does for a plane adapter.
set -eu
name=store-bus
. ci/lib.sh

for f in gates/statestore-conformance.sh gates/eventbus-conformance.sh; do
  [ -f "$f" ] || nogo "$f not found"
done
for tool in jq awk sed date; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool is not on PATH; run this via ./go ci"
done

# Nothing of the caller's reaches a suite: every variable a run needs is given.
unset CONFORMANCE CONFORMANCE_ACK_DEADLINE STATE_STORE EVENT_BUS STATE_FILE SPOOL_FILE SPOOL_ACK_DEADLINE BREAK BUS_DEADLINE ALSO

repo=$(pwd)
tmp=$(mktemp -d)
bpid=""
trap 'kill "$bpid" 2>/dev/null || true; rm -rf "$tmp"' EXIT

# suite_run DIR SUITE [VAR=value...]: gates/SUITE.sh run from DIR with exactly
# those variables added; its stdout is in $tmp/out, its stderr in $tmp/err.
# Leaves $rc, $lines (stdout lines) and $line (stdout).
suite_run() {
  dir=$1
  suite=$2
  shift 2
  rc=0
  (cd "$dir" && env "$@" sh "gates/$suite.sh") >"$tmp/out" 2>"$tmp/err" </dev/null || rc=$?
  lines=$(awk 'END{print NR}' "$tmp/out")
  line=$(cat "$tmp/out")
}
# expect_go LABEL PATTERN: the last run printed one line "GO: <suite> — " + PATTERN, exit 0.
expect_go() {
  if [ "$rc" -eq 0 ] && [ "$lines" -eq 1 ]; then
    # shellcheck disable=SC2254 # PATTERN is a glob on purpose
    case "$line" in "GO: $suite — "$2) return 0 ;; esac
  fi
  nogo "$1: wanted 'GO: $suite — $2', got exit $rc and $lines line(s): [$line]" "$(tail -n 20 "$tmp/err")"
}
# expect_nogo LABEL PATTERN: one line "NO-GO: <suite> — " + PATTERN, exit 1.
expect_nogo() {
  if [ "$rc" -eq 1 ] && [ "$lines" -eq 1 ]; then
    case "$line" in "NO-GO: $suite — "$2*) return 0 ;; esac
  fi
  nogo "$1: wanted 'NO-GO: $suite — $2', got exit $rc and $lines line(s): [$line]" "$(tail -n 20 "$tmp/err")"
}

# --- a: sqlite ---
sf=$tmp/state.sqlite
env STATE_FILE="$sf" sh adapters/sqlite/ready.sh >&2 || nogo "a: adapters/sqlite/ready.sh failed on a temporary STATE_FILE"
suite_run "$repo" statestore-conformance CONFORMANCE=1 STATE_STORE=sqlite STATE_FILE="$sf"
expect_go "a: sqlite" '*8 cases'

# --- b: spool, with case 5 ---
# Started here and judged after c: its redelivery waits 3 s, which c's stubs
# use (the demo's `ci` stage runs this check twice, once inside contract).
bf=$tmp/spool.sqlite
env SPOOL_FILE="$bf" SPOOL_ACK_DEADLINE=2 sh adapters/spool/ready.sh >&2 || nogo "b: adapters/spool/ready.sh failed on a temporary SPOOL_FILE"
mkdir "$tmp/b"
(env CONFORMANCE=1 EVENT_BUS=spool SPOOL_FILE="$bf" SPOOL_ACK_DEADLINE=2 CONFORMANCE_ACK_DEADLINE=2 \
  sh gates/eventbus-conformance.sh >"$tmp/b/out" 2>"$tmp/b/err" </dev/null; echo "$?" > "$tmp/b/rc") &
bpid=$!

# --- c: the stubs ---
root=$tmp/tree
mkdir -p "$root/adapters/stub-state" "$root/adapters/stub-bus"
ln -s "$repo/gates" "$root/gates"
ln -s "$repo/ci" "$root/ci"
ln -s "$repo/core" "$root/core"
reset() { rm -rf "$root/state" "$root/bus"; mkdir "$root/state" "$root/bus"; }
# empty LABEL DIR EXT: the suite left no DIR/*.EXT behind.
empty() {
  label=$1
  set -- "$root/$2"/*."$3"
  [ ! -e "$1" ] || nogo "$label: the suite left its own behind: $1"
}
# foreign_only MESSAGE: the bus holds that one message and no other, untouched.
foreign_only() {
  set -- "$1" "$root"/bus/*.msg
  [ "$#" -eq 2 ] && [ -f "$2" ] && [ "$(cat "$2")" = "$1" ]
}

# Stub StateStore: a file per collection and id. BREAK: 1 get of an absent
# document prints {} and exits 0; 2 get loses non-ASCII; 3 put merges; 4 the
# collection is ignored; 5 put accepts an array; 6 get cuts a long document
# short; 7 delete does nothing; 8 delete of an absent document exits 1; 9
# put empties the stored document before it judges the new one.
cat > "$root/adapters/stub-state/get.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
c=$1; [ "${BREAK:-}" != 4 ] || c=any
f="$d/state/$c.$2.json"
if [ ! -f "$f" ]; then
  if [ "${BREAK:-}" = 1 ]; then echo '{}'; exit 0; fi
  exit 1
fi
case "${BREAK:-}" in
  2) LC_ALL=C sed 's/[^ -~]/?/g' "$f" ;;
  6) head -c 60000 "$f" ;;
  *) cat "$f" ;;
esac
STUB
cat > "$root/adapters/stub-state/put.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
c=$1; [ "${BREAK:-}" != 4 ] || c=any
f="$d/state/$c.$2.json"
t=$(mktemp)
trap 'rm -f "$t" "$t.n"' EXIT
[ "${BREAK:-}" != 9 ] || : > "$f"
cat > "$t"
if [ "${BREAK:-}" = 5 ]; then jq -e . "$t" >/dev/null || exit 1; else jq -e 'type == "object"' "$t" >/dev/null || exit 1; fi
if [ "${BREAK:-}" = 3 ] && [ -s "$f" ]; then jq -cs '.[0] + .[1]' "$f" "$t" > "$t.n"; else jq -c . "$t" > "$t.n"; fi
mv "$t.n" "$f"
STUB
cat > "$root/adapters/stub-state/delete.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
c=$1; [ "${BREAK:-}" != 4 ] || c=any
f="$d/state/$c.$2.json"
case "${BREAK:-}" in
  7) exit 0 ;;
  8) [ -f "$f" ] || exit 1 ;;
esac
rm -f "$f"
STUB

# Stub EventBus: a FIFO of files, ackId = the file's name, a lease of
# BUS_DEADLINE seconds (600) kept in a file beside the message. BREAK: 1 pull
# loses non-ASCII; 2 the ackId holds a space; 3 a leased message is handed
# out again; 4 every third message published is lost; 5 ack does nothing; 6
# ack fails; 7 ack ends the lease and keeps the message. ALSO, when set, is a
# second message published right after each one: someone else's.
cat > "$root/adapters/stub-bus/publish.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
add() {
  n=$(cat "$d/bus/.seq" 2>/dev/null || printf 0)
  n=$((n + 1))
  printf '%s' "$n" > "$d/bus/.seq"
  if [ "${BREAK:-}" = 4 ] && [ $((n % 3)) -eq 0 ]; then return 0; fi
  printf '%s\n' "$1" > "$d/bus/$(printf '%06d' "$n").msg"
}
add "$1"
if [ -n "${ALSO:-}" ]; then add "$ALSO"; fi
STUB
cat > "$root/adapters/stub-bus/pull.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
now=$(date +%s)
for f in "$d"/bus/*.msg; do
  [ -e "$f" ] || exit 0
  l=${f%.msg}.lease
  if [ "${BREAK:-}" != 3 ] && [ -f "$l" ] && [ "$now" -le "$(cat "$l")" ]; then continue; fi
  printf '%s' $((now + ${BUS_DEADLINE:-600})) > "$l"
  id=$(basename "$f")
  data=$(cat "$f")
  [ "${BREAK:-}" != 2 ] || id="$id x"
  [ "${BREAK:-}" != 1 ] || data=$(printf '%s' "$data" | LC_ALL=C sed 's/[^ -~]/?/g')
  printf '%s %s\n' "$id" "$data"
  exit 0
done
exit 0
STUB
cat > "$root/adapters/stub-bus/ack.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
case "${BREAK:-}" in
  5) exit 0 ;;
  6) exit 1 ;;
  7) rm -f "$d/bus/${1%.msg}.lease"; exit 0 ;;
esac
rm -f "$d/bus/$1" "$d/bus/${1%.msg}.lease"
STUB

# The StateStore: a fair baseline, then each break and the case it must name.
reset
suite_run "$root" statestore-conformance CONFORMANCE=1 STATE_STORE=stub-state
expect_go "stub StateStore, BREAK unset" '*8 cases'
empty "stub StateStore, BREAK unset" state json
for spec in 1:case1 2:case2 3:case3 4:case4 5:case5 9:case5 6:case6 7:case7 8:case8; do
  b=${spec%%:*}
  reset
  suite_run "$root" statestore-conformance CONFORMANCE=1 STATE_STORE=stub-state BREAK="$b"
  expect_nogo "stub StateStore, BREAK=$b" "${spec#*:} "
  # The trap deletes what the suite wrote, however far it got; BREAK=7 is the
  # store whose delete does nothing.
  [ "$b" = 7 ] || empty "stub StateStore, BREAK=$b" state json
done

# The EventBus: baselines with and without case 5, then each break.
reset
suite_run "$root" eventbus-conformance CONFORMANCE=1 EVENT_BUS=stub-bus BUS_DEADLINE=1 CONFORMANCE_ACK_DEADLINE=1
expect_go "stub EventBus, BREAK unset, deadline 1" '*6 cases'
empty "stub EventBus, BREAK unset, deadline 1" bus msg
reset
suite_run "$root" eventbus-conformance CONFORMANCE=1 EVENT_BUS=stub-bus
expect_go "stub EventBus, BREAK unset, no deadline" '*5 cases; case 5 (redelivery) not run*'
for spec in 1:case1 2:case1 3:case2 4:case4 6:case3 7:case3; do
  b=${spec%%:*}
  reset
  suite_run "$root" eventbus-conformance CONFORMANCE=1 EVENT_BUS=stub-bus BREAK="$b"
  expect_nogo "stub EventBus, BREAK=$b" "${spec#*:} "
  # Whatever the suite published and was handed, it acks on its way out; the
  # buses whose ack fails or keeps the message cannot show it.
  case "$b" in 6|7) ;; *) empty "stub EventBus, BREAK=$b" bus msg ;; esac
done
# An ack that does nothing passes cases 1 to 4 (the message is leased), and
# only a redelivery after the deadline shows it: case 5.
reset
suite_run "$root" eventbus-conformance CONFORMANCE=1 EVENT_BUS=stub-bus BREAK=5 BUS_DEADLINE=1 CONFORMANCE_ACK_DEADLINE=1
expect_nogo "stub EventBus, BREAK=5, deadline 1" "case5 "
# A message that is not the suite's, on the bus before it starts: case 0, and
# the suite leaves it where it is.
foreign='{"ticket":"0001","step":"assign"}'
reset
(cd "$root" && sh adapters/stub-bus/publish.sh "$foreign")
suite_run "$root" eventbus-conformance CONFORMANCE=1 EVENT_BUS=stub-bus
expect_nogo "stub EventBus, a message already on the bus" 'case0*the bus is not idle'
foreign_only "$foreign" || nogo "the suite touched a message that was not its own after a case 0 NO-GO"
# Another's message that shows up behind the suite's own, with a bus that hands
# out a leased message again: the clean-up pulls it and must not ack it, and
# must stop pulling.
reset
suite_run "$root" eventbus-conformance CONFORMANCE=1 EVENT_BUS=stub-bus BREAK=3 ALSO="$foreign"
expect_nogo "stub EventBus, BREAK=3 and another's message behind" "case2 "
foreign_only "$foreign" || nogo "the suite's clean-up acked a message that was not its own, or left one of its own"

# --- b, judged ---
wait "$bpid" || :
bpid=""
rc=$(cat "$tmp/b/rc" 2>/dev/null || echo 1)
lines=$(awk 'END{print NR}' "$tmp/b/out")
line=$(cat "$tmp/b/out")
cp "$tmp/b/err" "$tmp/err"
suite=eventbus-conformance
expect_go "b: spool" '*6 cases'

# --- d: cold ---
for s in statestore-conformance eventbus-conformance; do
  suite_run "$repo" "$s"
  expect_nogo "cold $s, no store set" 'set CONFORMANCE=1'
done
reset
suite_run "$root" statestore-conformance STATE_STORE=stub-state
expect_nogo "cold statestore-conformance, a store set" 'set CONFORMANCE=1'
empty "cold statestore-conformance, a store set" state json
suite_run "$root" eventbus-conformance EVENT_BUS=stub-bus
expect_nogo "cold eventbus-conformance, a bus set" 'set CONFORMANCE=1'
empty "cold eventbus-conformance, a bus set" bus msg

go
