#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-assign: proves the tower's `assign` preconditions (docs/adr/0053 §5,
# §6) cold: no plane, no engine, no key. The real core/tower.sh, the real
# core/steps/assign.sh, core/assign.py and core/base-gates.sh run in a temp
# root on file-backed stub StateStore, EventBus, Tracker and CodeHost ports
# (ci/tower.sh's shape), with core/crew.sh and `make` stubbed: the worker
# and the gates are not what is judged here. Written from the ADR:
#   (a) a ticket whose perimeter no open ticket holds is assigned;
#   (b) one that overlaps an open ticket's is refused before any work, the
#       document stays `opened` with the failed attempt in its history,
#       and the line names both tickets and both globs;
#   (c) a disjoint ticket is assigned beside the holder;
#   (d) once the holder is on a green main (docs/adr/0056), `resume` and the step assign the
#       waiting ticket: it waited, it was not discarded;
#   (e) a ticket with no `## Perimeter` is refused;
#   (f) on the bundled app the base check never runs;
#   (g) on an attached repository a red base refuses the ticket, judged by
#       `test` alone on the empty range at the code host's HEAD (`sast`
#       judges the diff, docs/adr/0072 §1),
#       isolated, and nothing is cached; a green one lets it through and
#       is cached, so the next ticket on that commit runs no gates.
set -eu
name=assign
. ci/lib.sh

for f in core/tower.sh core/tower.py core/assign.py core/base-gates.sh core/steps/assign.sh; do
  [ -f "$f" ] || nogo "$f not found"
done

repo=$(pwd)
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/adapters/stub-state" "$root/adapters/stub-bus" "$root/adapters/stub-tracker" \
  "$root/adapters/stub-codehost" "$root/state" "$root/bus" "$root/tickets" "$root/core" "$root/bin"
for f in "$repo"/core/*; do
  [ "$(basename "$f")" = crew.sh ] || ln -s "$f" "$root/core/$(basename "$f")"
done
ln -s "$repo/ci" "$root/ci"

cat > "$root/adapters/stub-state/get.sh" <<'STUB'
set -eu
f="state/$1.$2.json"
[ -f "$f" ] || exit 1
cat "$f"
STUB
cat > "$root/adapters/stub-state/put.sh" <<'STUB'
set -eu
jq -c . > "state/$1.$2.json"
STUB
cat > "$root/adapters/stub-bus/publish.sh" <<'STUB'
set -eu
printf '%s\n' "$1" >> bus/log
STUB
cat > "$root/adapters/stub-tracker/get.sh" <<'STUB'
set -eu
[ -f "tickets/$1.md" ] || exit 1
cat "tickets/$1.md"
STUB
cat > "$root/adapters/stub-codehost/clone-url.sh" <<'STUB'
set -eu
printf '%s\n' "$(pwd)/origin"
STUB
# The worker: what core/steps/assign.sh reads back from core/crew.sh.
cat > "$root/core/crew.sh" <<'STUB'
set -eu
d=".crew/$TICKET"
mkdir -p "$d/out"
printf '# %s\n' "$TICKET" > "$d/ticket.md"
printf '{"harness":"stub","model":null}\n' > "$d/out/run.json"
printf 'PR_NUMBER=1\nPR_URL=stub\nBASE_SHA=b\nHEAD_SHA=h\n' > "$d/pr-opened.env"
touch "crew-ran.$TICKET"
STUB
# make: logs its arguments and answers what make-verdict says, in the
# shape `make gates` leaves (verdict.env in GATES_OUT).
cat > "$root/bin/make" <<'STUB'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$ROOT/make.log"
out=""
for a in "$@"; do case "$a" in GATES_OUT=*) out=${a#GATES_OUT=} ;; esac; done
mkdir -p "$out"
if [ "$(cat "$ROOT/make-verdict")" = GO ]; then
  printf 'GATES=GO\n' > "$out/verdict.env"; printf 'GO: gates — risk unknown, unknown\n'
else
  printf 'GATES=NO-GO\nFAILED=test\n' > "$out/verdict.env"; printf 'NO-GO: gates — test: NO-GO: test — red\n'; exit 1
fi
STUB
chmod +x "$root/bin/make"
: > "$root/make.log"

ticket() {  # ticket ID [GLOB...], each glob quoted by the caller
  t=$1; shift
  # shellcheck disable=SC2016 # the backticks are the ticket's markdown
  { printf '# %s — a ticket\n\n## Problem\n\n- `not/a/glob.py`\n\n' "$t"
    if [ $# -gt 0 ]; then printf '## Perimeter\n\n'; for g in "$@"; do printf -- '- `%s`\n' "$g"; done; printf '\n'; fi
  } > "$root/tickets/$t.md"
}

mismatch=""
fail() { [ -n "$mismatch" ] || mismatch=$1; }

# tower ARGS...: the real tower in the temp root; stderr to $root/err.
tower() {
  (cd "$root" && ROOT="$root" PATH="$root/bin:$PATH" STATE_STORE=stub-state EVENT_BUS=stub-bus \
    TRACKER=stub-tracker CODE_HOST=stub-codehost TOWER_STEPS=core/steps \
    sh core/tower.sh "$@") 2>"$root/err"
}
state() { jq -r .state "$root/state/tickets.$1.json"; }
assigned() { tower open "$1" && tower step "$1" assign; }

# (a)
ticket 0001 'app/backend/tests/test_geocoder_*.py' app/backend/meetups/geocoder_client.py
assigned 0001 || fail "a(assign refused: $(cat "$root/err"))"
[ "$(state 0001)" = pr-opened ] || fail "a(state $(state 0001))"
[ -f "$root/crew-ran.0001" ] || fail "a(the worker never ran)"

# (b)
ticket 0002 app/backend/tests/test_geocoder_client.py
if assigned 0002; then fail "b(an overlapping ticket was assigned)"; fi
[ "$(state 0002)" = opened ] || fail "b(state $(state 0002), want opened)"
[ ! -f "$root/crew-ran.0002" ] || fail "b(the worker ran)"
err=$(cat "$root/err")
for want in "0002 waits" "0001" "app/backend/tests/test_geocoder_client.py" "app/backend/tests/test_geocoder_*.py" pr-opened; do
  case "$err" in *"$want"*) ;; *) fail "b(stderr lacks '$want': $err)" ;; esac
done
[ "$(jq -r '.history[-1].error // empty' "$root/state/tickets.0002.json")" != "" ] \
  || fail "b(no failed attempt in the history)"

# (c)
ticket 0003 'docs/*'
assigned 0003 || fail "c(a disjoint ticket was refused: $(cat "$root/err"))"

# (d)
jq -c '.state = "main-green"' "$root/state/tickets.0001.json" > "$root/m" && mv "$root/m" "$root/state/tickets.0001.json"
tower resume 0002 || fail "d(resume refused: $(cat "$root/err"))"
tower step 0002 assign || fail "d(still refused with the holder on a green main: $(cat "$root/err"))"
[ "$(state 0002)" = pr-opened ] || fail "d(state $(state 0002))"
held=$(jq -r '.tickets | keys | join(",")' "$root/state/perimeters.held.json")
[ "$held" = 0002,0003 ] || fail "d(held by [$held], want 0002,0003: a holder on a green main is dropped)"

# (e)
ticket 0004
if assigned 0004; then fail "e(a ticket without a perimeter was assigned)"; fi
case "$(cat "$root/err")" in *"## Perimeter"*) ;; *) fail "e(stderr does not name ## Perimeter)" ;; esac

# (f)
[ ! -s "$root/make.log" ] || fail "f(the bundled app ran the base gates: $(cat "$root/make.log"))"

# (g)
git init -q "$root/origin"
git -C "$root/origin" -c user.name=ci -c user.email=ci@lights-out.invalid commit -q --allow-empty -m base
git clone -q "$root/origin" "$root/work"
sha=$(git -C "$root/origin" rev-parse HEAD)
WORKLOAD="$root/work" WORKLOAD_ATTACHED=1
export WORKLOAD WORKLOAD_ATTACHED
echo NO-GO > "$root/make-verdict"
ticket 0005 src/a.py
if assigned 0005; then fail "g(a red base let the ticket through)"; fi
[ "$(state 0005)" = opened ] || fail "g(state $(state 0005) on a red base)"
[ ! -f "$root/crew-ran.0005" ] || fail "g(the worker ran on a red base)"
case "$(cat "$root/err")" in *"base $sha is red at test"*) ;; *) fail "g(stderr: $(cat "$root/err"))" ;; esac
[ ! -f "$root/state/bases.$sha.json" ] || fail "g(a red base was cached)"
for want in 'GATES=test' "BASE=$sha" "HEAD=$sha" TOOLCHAIN_ISOLATE=1; do
  grep -q "$want" "$root/make.log" || fail "g(make was not given $want: $(cat "$root/make.log"))"
done
awk '/GATES=[^ ]*sast/ { found = 1 } END { exit !found }' "$root/make.log" \
  && fail "g(the base check still runs sast: $(cat "$root/make.log"))"
echo GO > "$root/make-verdict"
if ! tower resume 0005 || ! tower step 0005 assign; then fail "g(a green base was refused: $(cat "$root/err"))"; fi
[ -f "$root/state/bases.$sha.json" ] || fail "g(a green base was not cached)"
runs=$(wc -l < "$root/make.log")
ticket 0006 src/b.py
assigned 0006 || fail "g(a second ticket on a green base was refused)"
[ "$(wc -l < "$root/make.log")" -eq "$runs" ] || fail "g(the cached base was judged again)"

[ -z "$mismatch" ] || nogo "$mismatch"
go
