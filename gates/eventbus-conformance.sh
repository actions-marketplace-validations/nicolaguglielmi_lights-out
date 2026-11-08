#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-eventbus-conformance: the EventBus port's conformance suite
# (docs/adr/0060 §4, in the shape of docs/adr/0026 and gates/codehost-
# conformance.sh; the contract is docs/adr/0019 §3). Written from the ADRs,
# never from an adapter. It drives whichever EVENT_BUS is set, only through
# `sh adapters/$EVENT_BUS/{publish,pull,ack}.sh`, from the current directory.
# `pull` prints "<ackId> <data>" on one line, or nothing; the line is split
# at its first space. Cases, in this order, the first disagreement a NO-GO
# naming the case:
#   0 the first pull prints nothing: a bus with a message of someone else's
#     on it is a NO-GO "the bus is not idle", and the suite does not ack it
#   1 publish, then pull: one "<ackId> <data>" line, the data byte for byte
#     what was published (a JSON line with spaces, a double quote, a
#     backslash and a non-ASCII character), the ackId non-empty, no
#     whitespace in it
#   2 while that message is leased, a second pull prints nothing
#   3 ack exits 0, and the next pull prints nothing
#   4 three messages are pulled and acked as exactly that set (no order is
#     promised), then a pull prints nothing
#   5 only when CONFORMANCE_ACK_DEADLINE gives the adapter's ack deadline,
#     a positive integer of seconds: a message pulled and not acked comes
#     back after it, one that was acked does not. Unset, the GO line says
#     case 5 did not run (a redelivery takes the deadline to prove).
#
# It consumes nothing that is not its own. Every message it publishes carries
# its run id (date and random hex, as codehost-conformance makes it) in the
# data. On any exit it acks the ackIds it was handed for its own messages,
# then drains the bus for any of its own still queued and acks only those; a
# pull that returns a message without its run id during that clean-up is
# left alone (it returns after the adapter's deadline). The drain stops at
# the first empty pull or after 8 pulls, a decision of this suite: it
# publishes six messages at most.
#
# The numbers are decisions of this suite, none a measurement: case 5 waits
# the deadline plus one second, so a lease that ends at the deadline has
# ended whatever the adapter's clock granularity.
#
# Lives in gates/, so ci/contract.sh cold-runs it inside `make ci` with no
# CONFORMANCE set and no bus: the guard below must be the first thing that
# runs. `./go eventbus-conformance` is the only caller that sets
# CONFORMANCE=1, never a bare `sh gates/...` (CLAUDE.md). ci/store-bus.sh
# proves this suite can fail, on stub buses broken one behaviour at a time.
set -eu
name=eventbus-conformance
. ci/lib.sh

# Instant NO-GO, before anything touches a bus (docs/adr/0026 §4).
if [ "${CONFORMANCE:-}" != "1" ]; then
  nogo "set CONFORMANCE=1: this suite publishes messages on the event bus and pulls them (./go eventbus-conformance)"
fi

[ -n "${EVENT_BUS:-}" ] || nogo "EVENT_BUS is not set; a profile sets it: run this via ./go eventbus-conformance"
eb=adapters/$EVENT_BUS
for v in publish pull ack; do
  [ -f "$eb/$v.sh" ] || nogo "$eb/$v.sh is missing: an event bus ships publish, pull and ack (docs/adr/0019 §3)"
done
deadline=${CONFORMANCE_ACK_DEADLINE:-}
case "$deadline" in
  '') ;;
  0*|*[!0-9]*) nogo "CONFORMANCE_ACK_DEADLINE is [$deadline], want a positive integer of seconds without a leading zero: the adapter's ack deadline" ;;
esac
for tool in od date awk tr sort head; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool is not on PATH; run this via ./go eventbus-conformance"
done

run_id=$(date -u +%Y%m%d-%H%M%S)-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')
mark=conf-$run_id
published=0

work=$(mktemp -d)
out=$work/out
err=$work/err
: > "$work/pulled"
# Never prints to stdout: the one line this gate owns is already out when it
# runs. Acks are repeated for ackIds already acked: an ack of an ackId that
# leases nothing is success (docs/adr/0060 §2) and errors are ignored here.
# shellcheck disable=SC2329 # invoked by name via `trap` below, not called directly
cleanup() {
  ec=$?
  trap - EXIT INT TERM
  if [ "$published" -eq 1 ]; then
    while IFS= read -r id; do
      sh "$eb/ack.sh" "$id" >/dev/null 2>&1 </dev/null || :
    done < "$work/pulled"
    i=0
    while [ "$i" -lt 8 ]; do
      i=$((i + 1))
      sh "$eb/pull.sh" >"$work/drain" 2>/dev/null </dev/null || break
      [ -s "$work/drain" ] || break
      line=$(head -n 1 "$work/drain")
      case "$line" in
        *"$mark"*) sh "$eb/ack.sh" "${line%% *}" >/dev/null 2>&1 </dev/null || : ;;
      esac
    done
  fi
  rm -rf "$work"
  exit "$ec"
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Helpers. None of these may be called inside a $(...) capture that is not a
# plain read: a nogo inside one would only exit the subshell (POSIX sh).
# ---------------------------------------------------------------------------

say() { printf '[eventbus-conformance] %s\n' "$*" >&2; }
relay() { while IFS= read -r l || [ -n "$l" ]; do printf '  [%s] %s\n' "$1" "$l" >&2; done < "$err"; }
snip() { head -c 200 "$out" | tr '\n' ' '; }

# publish DATA: stdout in $out, exit code in $rc.
publish() {
  published=1
  if sh "$eb/publish.sh" "$1" >"$out" 2>"$err" </dev/null; then rc=0; else rc=$?; fi
  relay publish
}

# pull: exit code in $rc, the lines it printed in $nlines, and for one line
# its $ackid and $data (everything after the first space). The ackId of a
# message that carries the run id is kept for the clean-up.
pull() {
  if sh "$eb/pull.sh" >"$out" 2>"$err" </dev/null; then rc=0; else rc=$?; fi
  relay pull
  nlines=$(awk 'END{print NR}' "$out")
  line=$(cat "$out")
  ackid=${line%% *}
  case "$line" in *' '*) data=${line#* } ;; *) data="" ;; esac
  if [ "$nlines" -eq 1 ]; then
    case "$data" in *"$mark"*) printf '%s\n' "$ackid" >> "$work/pulled" ;; esac
  fi
}

# ack ACKID: exit code in $rc.
ack() {
  if sh "$eb/ack.sh" "$1" >"$out" 2>"$err" </dev/null; then rc=0; else rc=$?; fi
  relay ack
}

# want_nothing CASE WHAT: a pull that exits 0 and prints nothing, or the NO-GO.
want_nothing() {
  pull
  { [ "$rc" -eq 0 ] && [ ! -s "$out" ]; } \
    || nogo "$1: $2, pull exited $rc and printed [$(snip)], want exit 0 and nothing"
}

# want_message CASE WHAT: a pull that exits 0 and prints one line with a
# space in it, or the NO-GO.
want_message() {
  pull
  [ "$rc" -eq 0 ] || nogo "$1: $2, pull exited $rc"
  [ "$nlines" -ge 1 ] || nogo "$1: $2, pull printed nothing: the message is lost"
  [ "$nlines" -eq 1 ] || nogo "$1: $2, pull printed $nlines lines [$(snip)], want one '<ackId> <data>' line"
  case "$line" in *' '*) ;; *) nogo "$1: $2, pull printed [$(snip)], want '<ackId> <data>': there is no space after the ackId" ;; esac
}

say "run $run_id on EVENT_BUS=$EVENT_BUS"

# ---------------------------------------------------------------------------
# Case 0: the bus is idle. Not acked if it is not: it is not the suite's.
# ---------------------------------------------------------------------------
pull
[ "$rc" -eq 0 ] || nogo "case0 idle: pull exited $rc on a bus the suite has not written to"
if [ -s "$out" ]; then
  nogo "case0 idle: the bus is not idle, the first pull printed [$(snip)]; the suite did not ack it, it is not the suite's and returns after the adapter's deadline"
fi
say "case 0 the bus is idle: GO"

# ---------------------------------------------------------------------------
# Case 1: publish, pull, the data byte for byte. The data is one JSON line
# with a space, a double quote, a backslash and a non-ASCII character, which
# is what an adapter that quotes badly or decodes as ASCII gets wrong.
# ---------------------------------------------------------------------------
want='{"ticket":"'"$mark"'","step":"a b","note":"q\"uote back\\slash ü"}'
publish "$want"
[ "$rc" -eq 0 ] || nogo "case1 roundtrip: publish exited $rc"
want_message "case1 roundtrip" "after a publish"
case "$ackid" in
  ''|*[[:space:]]*) nogo "case1 roundtrip: the ackId [$ackid] is empty or holds whitespace" ;;
esac
[ "$data" = "$want" ] \
  || nogo "case1 roundtrip: pull printed data [$data], published [$want] (or the ackId holds whitespace, so the line was split in the wrong place)"
lease_ack=$ackid
say "case 1 publish and pull, the data byte for byte: GO"

# ---------------------------------------------------------------------------
# Case 2: a message that is leased is not handed out again.
# ---------------------------------------------------------------------------
want_nothing "case2 lease" "the message is leased and not acked"
say "case 2 a leased message is not handed out again: GO"

# ---------------------------------------------------------------------------
# Case 3: ack exits 0, and the message is gone.
# ---------------------------------------------------------------------------
ack "$lease_ack"
[ "$rc" -eq 0 ] || nogo "case3 ack: ack exited $rc on the ackId that pull printed"
want_nothing "case3 ack" "after the ack"
say "case 3 ack: GO"

# ---------------------------------------------------------------------------
# Case 4: three messages, each pulled and acked, as exactly that set. Pulled
# and acked one at a time: the lease only has to outlast one step.
# ---------------------------------------------------------------------------
: > "$work/sent"
: > "$work/got"
for k in m1 m2 m3; do
  d='{"ticket":"'"$mark"'","step":"'"$k"'"}'
  publish "$d"
  [ "$rc" -eq 0 ] || nogo "case4 set: publish exited $rc for $k"
  printf '%s\n' "$d" >> "$work/sent"
done
for k in 1 2 3; do
  pull
  [ "$rc" -eq 0 ] || nogo "case4 set: pull $k of 3 exited $rc"
  [ "$nlines" -ge 1 ] || nogo "case4 set: pull $k of 3 printed nothing: a published message was lost"
  [ "$nlines" -eq 1 ] || nogo "case4 set: pull $k of 3 printed $nlines lines [$(snip)], want one message"
  printf '%s\n' "$data" >> "$work/got"
  ack "$ackid"
  [ "$rc" -eq 0 ] || nogo "case4 set: ack exited $rc on message $k of 3"
done
[ "$(sort "$work/got")" = "$(sort "$work/sent")" ] \
  || nogo "case4 set: the three pulls returned [$(tr '\n' ' ' < "$work/got")], the three published were [$(tr '\n' ' ' < "$work/sent")]"
want_nothing "case4 set" "all three are acked"
say "case 4 three messages are pulled and acked as that set: GO"

# ---------------------------------------------------------------------------
# Case 5: redelivery after the deadline, and only of what was not acked.
# ---------------------------------------------------------------------------
if [ -n "$deadline" ]; then
  msg_a='{"ticket":"'"$mark"'","step":"redelivery-A"}'
  msg_b='{"ticket":"'"$mark"'","step":"redelivery-B"}'
  publish "$msg_a"
  [ "$rc" -eq 0 ] || nogo "case5 redelivery: publish exited $rc for A"
  want_message "case5 redelivery" "pulling A"
  [ "$data" = "$msg_a" ] || nogo "case5 redelivery: pulling A printed [$data], want [$msg_a]"
  ack "$ackid"
  [ "$rc" -eq 0 ] || nogo "case5 redelivery: ack exited $rc on A"
  publish "$msg_b"
  [ "$rc" -eq 0 ] || nogo "case5 redelivery: publish exited $rc for B"
  want_message "case5 redelivery" "pulling B"
  [ "$data" = "$msg_b" ] || nogo "case5 redelivery: pulling B printed [$data], want [$msg_b]"
  say "case 5: A acked, B pulled and not acked; waiting $((deadline + 1)) s for B's lease to end"
  sleep $((deadline + 1))
  pull
  [ "$rc" -eq 0 ] || nogo "case5 redelivery: pull exited $rc after the deadline"
  [ "$nlines" -ge 1 ] || nogo "case5 redelivery: B was pulled and not acked, and did not come back $((deadline + 1)) s later (the deadline is ${deadline} s)"
  [ "$data" != "$msg_a" ] || nogo "case5 redelivery: A came back after it was acked"
  [ "$nlines" -eq 1 ] && [ "$data" = "$msg_b" ] \
    || nogo "case5 redelivery: after the deadline pull printed [$(snip)], want B ($msg_b): a message that was acked came back, or B did not alone"
  ack "$ackid"
  [ "$rc" -eq 0 ] || nogo "case5 redelivery: ack exited $rc on B's redelivery"
  want_nothing "case5 redelivery" "B's redelivery is acked"
  say "case 5 redelivery after the deadline, of the unacked message only: GO"
  go_with "$EVENT_BUS, 6 cases"
fi

go_with "$EVENT_BUS, 5 cases; case 5 (redelivery) not run: CONFORMANCE_ACK_DEADLINE unset"
