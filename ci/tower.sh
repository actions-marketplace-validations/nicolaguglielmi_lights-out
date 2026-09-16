#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-tower: proves core/tower.sh, adapters/inproc/run.sh and core/audit.sh
# (docs/adr/0019 §1, §2, §6, §9) on stub adapters, cold: no plane, no
# engine, milliseconds. The ci/harness.sh shape. A temp root holds
# file-backed stubs for the StateStore, EventBus and CodeHost ports plus a
# TOWER_STEPS directory of stub steps — except `merge`, which is the real
# core/steps/merge.sh over the stub CodeHost, because the crash case (§9 d)
# is about that seam. Written from the ADR, not from the scripts.
set -eu
name=tower
. ci/lib.sh

for f in core/tower.sh core/audit.sh core/steps/merge.sh adapters/inproc/run.sh; do
  [ -f "$f" ] || nogo "$f not found"
done

repo=$(pwd)
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/adapters/stub-state" "$root/adapters/stub-bus" "$root/adapters/stub-codehost" \
  "$root/steps" "$root/state" "$root/bus" "$root/world"
ln -s "$repo/core" "$root/core"
ln -s "$repo/ci" "$root/ci"
ln -s "$repo/adapters/inproc" "$root/adapters/inproc"

# --- stub StateStore: one file per <collection>/<id> ---
cat > "$root/adapters/stub-state/get.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
f="$d/state/$1.$2.json"
[ -f "$f" ] || exit 1
cat "$f"
STUB
cat > "$root/adapters/stub-state/put.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
jq -c . > "$d/state/$1.$2.json"
STUB
cat > "$root/adapters/stub-state/delete.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
rm -f "$d/state/$1.$2.json"
STUB

# --- stub EventBus: a FIFO of files, ackId = file name ---
cat > "$root/adapters/stub-bus/publish.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
n=$(cat "$d/bus/.seq" 2>/dev/null || printf 0); n=$((n + 1)); printf '%s' "$n" > "$d/bus/.seq"
printf '%s\n' "$1" > "$d/bus/$(printf '%06d' "$n").msg"
STUB
cat > "$root/adapters/stub-bus/pull.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
for f in "$d"/bus/*.msg; do
  [ -e "$f" ] || exit 0
  printf '%s %s\n' "$(basename "$f")" "$(cat "$f")"
  exit 0
done
STUB
cat > "$root/adapters/stub-bus/ack.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
rm -f "$d/bus/$1"
STUB

# --- stub CodeHost: a world file per PR, the gitea merge/pr contracts ---
cat > "$root/adapters/stub-codehost/pr.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
f="$d/world/pr-$1.json"
[ -f "$f" ] || { printf 'stub-codehost: no PR #%s\n' "$1" >&2; exit 1; }
cat "$f"
STUB
cat > "$root/adapters/stub-codehost/merge.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
f="$d/world/pr-$1.json"
[ -f "$f" ] || { printf 'stub-codehost: no PR #%s\n' "$1" >&2; exit 1; }
if [ "$(jq -r .merged "$f")" != true ]; then
  printf 'merge performed %s\n' "$1" >> "$d/effects.log"
  new=$(jq -c '.merged = true | .state = "closed" | .merge_sha = "merge-of-" + .head_sha' "$f")
  printf '%s\n' "$new" > "$f"
fi
jq -r '"\(.merge_sha) \(.head_sha)"' "$f"
STUB

# --- stub steps; `merge` is the real one ---
cat > "$root/steps/assign.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
printf 'assign\n' >> "$d/effects.log"
printf '%s\n' '{"state":"pr-opened","pr":{"number":1,"url":"stub://pr/1","base_sha":"base","head_sha":"head1"},"task":{"role":"dev-worker","harness":"stub","model":null},"spec":{"sha256":"abc","title":"0001 — stub ticket"}}'
STUB
cat > "$root/steps/ci.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
printf 'ci\n' >> "$d/effects.log"
case "${STUB_CI:-pass}" in
  pass) printf '%s\n' '{"state":"ci-passed","ci":{"verdict":"GO","risk_level":"low","decision":"auto-merge","head_sha":"head1"}}' ;;
  review) printf '%s\n' '{"state":"review","ci":{"verdict":"GO","risk_level":"high","decision":"review","head_sha":"head1"}}' ;;
  fail) printf '%s\n' '{"state":"ci-failed","ci":{"verdict":"NO-GO","failed":"test","risk_level":"low","decision":"auto-merge","head_sha":"head1"}}' ;;
  crash) exit 1 ;;
esac
STUB
cat > "$root/steps/release.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
printf 'release\n' >> "$d/effects.log"
printf '%s\n' '{"state":"rolled-back","release":{"version":"0.2.0-waitlist","verdict":"NO-GO: launchpad — 5%: stub","numbers":["slo: stub"],"image":"stub"}}'
STUB
ln -s "$repo/core/steps/merge.sh" "$root/steps/merge.sh"

export STATE_STORE=stub-state EVENT_BUS=stub-bus CODE_HOST=stub-codehost TOWER_STEPS="$root/steps"
cd "$root"

reset() {
  rm -f state/* bus/* bus/.seq world/* effects.log
  printf '%s\n' '{"number":1,"state":"open","merged":false,"head_sha":"head1","merge_sha":null}' > world/pr-1.json
}
effects() { cat effects.log 2>/dev/null | tr '\n' ',' ; }
doc() { cat "state/tickets.0001.json"; }
queue() { find bus -name '*.msg' | wc -l | tr -d ' '; }
log="$root/run.log"
mismatch=""
fail_case() {
  [ -z "$mismatch" ] || return 0
  mismatch="$1"; printf 'ci-tower: %s: %s\n' "$1" "$2" >&2; cat "$log" >&2
}

# (a) the transition table, driven by the inproc loop.
reset
sh core/tower.sh open 0001 2>"$log" || fail_case a-open "open exited $?"
[ "$(doc | jq -r .state)" = opened ] || fail_case a-open "open did not write state opened"
[ "$(queue)" = 1 ] || fail_case a-open "open published $(queue) events, want 1 (assign)"
if [ -z "$mismatch" ]; then
  sh adapters/inproc/run.sh 2>"$log" || fail_case a-run "inproc run exited $?"
  [ "$(doc | jq -r .state)" = rolled-back ] || fail_case a-final "final state $(doc | jq -r .state), want rolled-back"
  [ "$(effects)" = "assign,ci,merge performed 1,release," ] || fail_case a-effects "effects: $(effects)"
  [ "$(queue)" = 0 ] || fail_case a-queue "queue not empty after the run"
  [ "$(doc | jq '.history | length')" = 5 ] || fail_case a-history "history has $(doc | jq '.history | length') entries, want 5"
  [ "$(doc | jq -r .merge.sha)" = merge-of-head1 ] || fail_case a-merge "merge.sha not recorded from the code host"
fi
# (a') review and ci-failed are terminal: no merge, nothing published.
for variant in review fail; do
  [ -z "$mismatch" ] || break
  reset
  if ! sh core/tower.sh open 0001 2>"$log" || ! STUB_CI=$variant sh adapters/inproc/run.sh 2>"$log"; then
    fail_case "a-$variant" "run failed"
  fi
  case "$variant" in review) want=review ;; fail) want=ci-failed ;; esac
  [ "$(doc | jq -r .state)" = "$want" ] || fail_case "a-$variant" "state $(doc | jq -r .state), want $want"
  [ "$(effects)" = "assign,ci," ] || fail_case "a-$variant" "effects: $(effects)"
  [ "$(queue)" = 0 ] || fail_case "a-$variant" "an event was published after a terminal state"
done

# (b) the same event twice: applied once.
if [ -z "$mismatch" ]; then
  reset
  if ! sh core/tower.sh open 0001 2>"$log" || ! sh adapters/inproc/run.sh 2>"$log"; then fail_case b "run failed"; fi
  before=$(doc)
  sh adapters/stub-bus/publish.sh '{"ticket":"0001","step":"ci"}'
  sh adapters/inproc/run.sh 2>"$log" || fail_case b "second run exited $?"
  grep -q 'ci already applied' "$log" || fail_case b "no 'already applied' line on a duplicate event"
  [ "$(effects)" = "assign,ci,merge performed 1,release," ] || fail_case b "duplicate event had an effect: $(effects)"
  [ "$(doc)" = "$before" ] || fail_case b "duplicate event changed the document"
fi

# (c) out of order: merge on an opened document is dropped.
if [ -z "$mismatch" ]; then
  reset
  sh core/tower.sh open 0001 2>"$log"
  sh core/tower.sh step 0001 merge 2>"$log" || fail_case c "out-of-order step exited $?"
  [ -z "$(effects)" ] || fail_case c "out-of-order merge had an effect"
  [ "$(doc | jq -r .state)" = opened ] || fail_case c "state moved"
fi

# (d) the crash case: the merge happened, the state was not written.
if [ -z "$mismatch" ]; then
  reset
  printf '%s\n' '{"number":1,"state":"closed","merged":true,"head_sha":"head1","merge_sha":"X"}' > world/pr-1.json
  printf '%s\n' '{"id":"0001","state":"ci-passed","history":[],"pr":{"number":1,"head_sha":"head1"},"ci":{"head_sha":"head1"}}' \
    | sh adapters/stub-state/put.sh tickets 0001
  sh core/tower.sh step 0001 merge 2>"$log" || fail_case d "merge retry exited $?"
  [ -z "$(effects)" ] || fail_case d "a second merge was performed: $(effects)"
  [ "$(doc | jq -r .state)" = merged ] || fail_case d "state $(doc | jq -r .state), want merged"
  [ "$(doc | jq -r .merge.sha)" = X ] || fail_case d "merge.sha $(doc | jq -r .merge.sha), want the host's X"
  [ "$(doc | jq -r .merge.head_sha)" = head1 ] || fail_case d "merge.head_sha not the host's head"
  [ "$(queue)" = 1 ] && [ "$(sh adapters/stub-bus/pull.sh | jq -r .step 2>/dev/null || cat bus/*.msg | jq -r .step)" = release ] \
    || fail_case d "release was not requested after the recovered merge"
fi

# (e) a failing step: document untouched, exit 1, nothing published.
if [ -z "$mismatch" ]; then
  reset
  sh core/tower.sh open 0001 2>"$log"
  rm -f bus/*.msg
  STUB_CI=crash sh core/tower.sh step 0001 assign 2>"$log" >/dev/null || true
  rm -f bus/*.msg
  before=$(doc)
  if STUB_CI=crash sh core/tower.sh step 0001 ci 2>"$log"; then fail_case e "a failing step exited 0"; fi
  [ "$(doc)" = "$before" ] || fail_case e "a failing step changed the document"
  [ "$(queue)" = 0 ] || fail_case e "a failing step published an event"
fi

# (f) the audit: GO on the complete chain, NO-GO on each broken link.
audit() { TICKET=0001 sh core/audit.sh 2>"$log"; }
if [ -z "$mismatch" ]; then
  reset
  if ! sh core/tower.sh open 0001 2>"$log" || ! sh adapters/inproc/run.sh 2>"$log"; then fail_case f "run failed"; fi
  complete=$(doc)
  out=$(audit) || true
  [ "$out" = "GO: audit" ] || fail_case f-go "audit on a complete chain: $out"
  expect_nogo() {  # NAME WORD: the audit must NO-GO and name WORD
    out=$(audit) && fail_case "f-$1" "audit passed: $out" || true
    case "$out" in "NO-GO: audit — "*"$2"*) : ;; *) fail_case "f-$1" "audit said: $out (want a NO-GO naming '$2')" ;; esac
  }
  printf '%s' "$complete" | jq 'del(.merge.sha)' | sh adapters/stub-state/put.sh tickets 0001
  expect_nogo missing-link missing
  printf '%s' "$complete" | jq '.ci.head_sha = "other"' | sh adapters/stub-state/put.sh tickets 0001
  expect_nogo sha-mismatch other
  printf '%s' "$complete" | sh adapters/stub-state/put.sh tickets 0001
  printf '%s\n' '{"number":1,"state":"open","merged":false,"head_sha":"head1","merge_sha":null}' > world/pr-1.json
  expect_nogo host-open open
  printf '%s\n' '{"number":1,"state":"closed","merged":true,"head_sha":"head1","merge_sha":"other-merge"}' > world/pr-1.json
  expect_nogo host-merge-sha other-merge
  rm -f world/pr-1.json
  expect_nogo host-down unreachable
fi

cd "$repo"
[ -z "$mismatch" ] || nogo "stub case $mismatch disagrees with docs/adr/0019"
go
