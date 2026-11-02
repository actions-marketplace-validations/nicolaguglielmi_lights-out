#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-tower: proves core/tower.sh, adapters/inproc/run.sh and core/audit.sh
# (docs/adr/0019 §1, §2, §6, §9; docs/adr/0034) on stub adapters, cold: no plane, no
# engine, milliseconds. The ci/harness.sh shape. A temp root holds
# file-backed stubs for the StateStore, EventBus and CodeHost ports plus a
# TOWER_STEPS directory of stub steps — except `merge`, which is the real
# core/steps/merge.sh over the stub CodeHost, because the crash case (§9 d)
# is about that seam. Case (g) runs the real core/steps/ci.sh on a real git
# range: a PR is judged by the base's gates, policy and perimeter, not by
# its own (docs/adr/0033). Written from the ADRs, not from the scripts.
set -eu
name=tower
. ci/lib.sh

for f in core/tower.sh core/audit.sh core/steps/merge.sh core/steps/ci.sh adapters/inproc/run.sh; do
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
cat > "$root/steps/review.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
printf 'review\n' >> "$d/effects.log"
case "${STUB_REVIEW:-approve}" in
  approve) printf '%s\n' '{"state":"ci-passed","review":{"role":"test-reviewer","verdict":"approved","reason":"stub approved"}}' ;;
  reject) printf '%s\n' '{"state":"ci-failed","review":{"role":"test-reviewer","verdict":"changes-requested","reason":"stub rejected"}}' ;;
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
# (a') ci-failed (a gate's own NO-GO) is terminal: no merge, nothing
# published.
if [ -z "$mismatch" ]; then
  reset
  if ! sh core/tower.sh open 0001 2>"$log" || ! STUB_CI=fail sh adapters/inproc/run.sh 2>"$log"; then
    fail_case a-fail "run failed"
  fi
  [ "$(doc | jq -r .state)" = ci-failed ] || fail_case a-fail "state $(doc | jq -r .state), want ci-failed"
  [ "$(effects)" = "assign,ci," ] || fail_case a-fail "effects: $(effects)"
  [ "$(queue)" = 0 ] || fail_case a-fail "an event was published after a terminal state"
fi

# (a'') review (docs/adr/0021 §1): a GO+review PR reaches the review step,
# whose own verdict decides ci-passed or ci-failed — never review itself,
# which is no longer terminal. approve continues on to merge/release
# exactly like the golden path (a); reject is terminal, same as a gate's
# NO-GO.
if [ -z "$mismatch" ]; then
  reset
  if ! sh core/tower.sh open 0001 2>"$log" || ! STUB_CI=review STUB_REVIEW=approve sh adapters/inproc/run.sh 2>"$log"; then
    fail_case a-review-approve "run failed"
  fi
  [ "$(doc | jq -r .state)" = rolled-back ] || fail_case a-review-approve "final state $(doc | jq -r .state), want rolled-back"
  [ "$(effects)" = "assign,ci,review,merge performed 1,release," ] || fail_case a-review-approve "effects: $(effects)"
  [ "$(queue)" = 0 ] || fail_case a-review-approve "queue not empty after the run"
  [ "$(doc | jq -r .review.verdict)" = approved ] || fail_case a-review-approve "review.verdict not recorded"
fi
if [ -z "$mismatch" ]; then
  reset
  if ! sh core/tower.sh open 0001 2>"$log" || ! STUB_CI=review STUB_REVIEW=reject sh adapters/inproc/run.sh 2>"$log"; then
    fail_case a-review-reject "run failed"
  fi
  [ "$(doc | jq -r .state)" = ci-failed ] || fail_case a-review-reject "state $(doc | jq -r .state), want ci-failed"
  [ "$(effects)" = "assign,ci,review," ] || fail_case a-review-reject "effects: $(effects)"
  [ "$(queue)" = 0 ] || fail_case a-review-reject "an event was published after ci-failed"
fi

# (b) the same event twice: applied once.
if [ -z "$mismatch" ]; then
  reset
  if ! sh core/tower.sh open 0001 2>"$log" || ! sh adapters/inproc/run.sh 2>"$log"; then fail_case b "run failed"; fi
  before=$(doc) || fail_case b "no document after the run"
  sh adapters/stub-bus/publish.sh '{"ticket":"0001","step":"ci"}' || fail_case b "could not publish the duplicate"
  sh adapters/inproc/run.sh 2>"$log" || fail_case b "second run exited $?"
  grep -q 'ci already applied' "$log" || fail_case b "no 'already applied' line on a duplicate event"
  [ "$(effects)" = "assign,ci,merge performed 1,release," ] || fail_case b "duplicate event had an effect: $(effects)"
  [ "$(doc)" = "$before" ] || fail_case b "duplicate event changed the document"
fi

# (c) out of order: merge on an opened document is dropped.
if [ -z "$mismatch" ]; then
  reset
  sh core/tower.sh open 0001 2>"$log" || fail_case c "open exited $?"
  sh core/tower.sh step 0001 merge 2>"$log" || fail_case c "out-of-order step exited $?"
  [ -z "$(effects)" ] || fail_case c "out-of-order merge had an effect"
  [ "$(doc | jq -r .state)" = opened ] || fail_case c "state moved"
fi

# (d) the crash case: the merge happened, the state was not written.
if [ -z "$mismatch" ]; then
  reset
  printf '%s\n' '{"number":1,"state":"closed","merged":true,"head_sha":"head1","merge_sha":"X"}' > world/pr-1.json
  printf '%s\n' '{"id":"0001","state":"ci-passed","history":[],"pr":{"number":1,"head_sha":"head1"},"ci":{"head_sha":"head1"}}' \
    | sh adapters/stub-state/put.sh tickets 0001 || fail_case d "could not seed the document"
  sh core/tower.sh step 0001 merge 2>"$log" || fail_case d "merge retry exited $?"
  [ -z "$(effects)" ] || fail_case d "a second merge was performed: $(effects)"
  [ "$(doc | jq -r .state)" = merged ] || fail_case d "state $(doc | jq -r .state), want merged"
  [ "$(doc | jq -r .merge.sha)" = X ] || fail_case d "merge.sha $(doc | jq -r .merge.sha), want the host's X"
  [ "$(doc | jq -r .merge.head_sha)" = head1 ] || fail_case d "merge.head_sha not the host's head"
  [ "$(queue)" = 1 ] && [ "$(sh adapters/stub-bus/pull.sh | jq -r .step 2>/dev/null || cat bus/*.msg | jq -r .step)" = release ] \
    || fail_case d "release was not requested after the recovered merge"
fi

# (e) a failing step: exit 1, nothing published, state and fields
# untouched; the history gains exactly one entry, the failed attempt
# (docs/adr/0034 §1).
if [ -z "$mismatch" ]; then
  reset
  sh core/tower.sh open 0001 2>"$log" || fail_case e "open exited $?"
  rm -f bus/*.msg
  sh core/tower.sh step 0001 assign 2>"$log" >/dev/null || fail_case e "assign exited $?"
  rm -f bus/*.msg
  before=$(doc) || fail_case e "no document after assign"
  if STUB_CI=crash sh core/tower.sh step 0001 ci 2>"$log"; then fail_case e "a failing step exited 0"; fi
  [ "$(doc | jq -c 'del(.history)')" = "$(printf '%s' "$before" | jq -c 'del(.history)')" ] \
    || fail_case e "a failing step changed the document beyond its history"
  [ "$(doc | jq -c '.history[:-1]')" = "$(printf '%s' "$before" | jq -c '.history')" ] \
    || fail_case e "a failing step rewrote earlier history entries"
  [ "$(doc | jq -r '.history[-1] | "\(.step) \(.state) \(.error != null)"')" = "ci pr-opened true" ] \
    || fail_case e "last history entry is $(doc | jq -c '.history[-1]'), want a failed ci at pr-opened"
  [ "$(queue)" = 0 ] || fail_case e "a failing step published an event"
fi

# (f) the audit: GO on the complete chain, NO-GO on each broken link.
audit() { TICKET=0001 sh core/audit.sh 2>"$log"; }
if [ -z "$mismatch" ]; then
  reset
  if ! sh core/tower.sh open 0001 2>"$log" || ! sh adapters/inproc/run.sh 2>"$log"; then fail_case f "run failed"; fi
  complete=$(doc) || fail_case f "no document after the run"
  out=$(audit) || true
  [ "$out" = "GO: audit" ] || fail_case f-go "audit on a complete chain: $out"
  expect_nogo() {  # NAME WORD: the audit must NO-GO and name WORD
    out=$(audit) && fail_case "f-$1" "audit passed: $out" || true
    case "$out" in "NO-GO: audit — "*"$2"*) : ;; *) fail_case "f-$1" "audit said: $out (want a NO-GO naming '$2')" ;; esac
  }
  printf '%s' "$complete" | jq 'del(.merge.sha)' | sh adapters/stub-state/put.sh tickets 0001 \
    || fail_case f-missing-link "could not write the document"
  expect_nogo missing-link missing
  printf '%s' "$complete" | jq '.ci.head_sha = "other"' | sh adapters/stub-state/put.sh tickets 0001 \
    || fail_case f-sha-mismatch "could not write the document"
  expect_nogo sha-mismatch other
  # docs/adr/0021 §9: ci.decision=review past the review step must carry
  # review.verdict/review.reason — a reviewed merge with no review on the
  # record is exactly what an audit exists to catch.
  printf '%s' "$complete" | jq '.ci.decision = "review"' | sh adapters/stub-state/put.sh tickets 0001 \
    || fail_case f-review-missing "could not write the document"
  expect_nogo review-missing review.verdict
  printf '%s' "$complete" | sh adapters/stub-state/put.sh tickets 0001 || fail_case f-host-open "could not write the document"
  printf '%s\n' '{"number":1,"state":"open","merged":false,"head_sha":"head1","merge_sha":null}' > world/pr-1.json
  expect_nogo host-open open
  printf '%s\n' '{"number":1,"state":"closed","merged":true,"head_sha":"head1","merge_sha":"other-merge"}' > world/pr-1.json
  expect_nogo host-merge-sha other-merge
  rm -f world/pr-1.json
  expect_nogo host-down unreachable
fi

# (g) resume (docs/adr/0034): a ticket whose ci step failed is stranded
# at pr-opened with nothing queued; resume requests ci again, the run
# reaches the next states to the end, the history keeps the failed
# attempt, the resume and the new attempt, and the audit still passes.
if [ -z "$mismatch" ]; then
  reset
  sh core/tower.sh open 0001 2>"$log" || fail_case g-resume "open exited $?"
  if STUB_CI=crash sh adapters/inproc/run.sh 2>"$log"; then fail_case g-resume "a run with a failing step exited 0"; fi
  [ "$(doc | jq -r .state)" = pr-opened ] || fail_case g-resume "stranded at $(doc | jq -r .state), want pr-opened"
  [ "$(queue)" = 0 ] || fail_case g-resume "something was queued after the failed step"
  sh core/tower.sh resume 0001 2>"$log" || fail_case g-resume "resume of a stranded ticket exited $?"
  [ "$(queue)" = 1 ] || fail_case g-resume "resume queued $(queue) events, want 1"
  sh adapters/inproc/run.sh 2>"$log" || fail_case g-resume "the resumed run exited $?"
  [ "$(doc | jq -r .state)" = rolled-back ] || fail_case g-resume "final state $(doc | jq -r .state), want rolled-back"
  [ "$(effects)" = "assign,ci,ci,merge performed 1,release," ] || fail_case g-resume "effects: $(effects)"
  steps=$(doc | jq -r '[.history[] | .step + (if .error then "!" else "" end)] | join(",")')
  [ "$steps" = "open,assign,ci!,resume,ci,merge,release" ] || fail_case g-resume "history steps: $steps"
  out=$(audit) || true
  [ "$out" = "GO: audit" ] || fail_case g-resume-audit "audit after a resumed run: $out"
fi
# (g') resume refuses a ticket that is not stranded: one whose last
# history entry did not fail, mid-flight (assign queued) or terminal.
if [ -z "$mismatch" ]; then
  expect_refused() {  # NAME: resume must exit non-zero, say why, change and publish nothing
    before=$(doc) || fail_case "$1" "no document"
    queued=$(queue)
    if sh core/tower.sh resume 0001 2>"$log"; then fail_case "$1" "resume of a ticket that is not stranded exited 0"; fi
    grep -q 'not stranded' "$log" || fail_case "$1" "no 'not stranded' line on the refusal"
    [ "$(doc)" = "$before" ] || fail_case "$1" "a refused resume changed the document"
    [ "$(queue)" = "$queued" ] || fail_case "$1" "a refused resume published an event"
  }
  reset
  sh core/tower.sh open 0001 2>"$log" || fail_case g-refuse-open "open exited $?"
  expect_refused g-refuse-in-flight
  sh adapters/inproc/run.sh 2>"$log" || fail_case g-refuse-terminal "run exited $?"
  expect_refused g-refuse-terminal
fi

cd "$repo"

# (h) docs/adr/0033, ticket 0007: the real core/steps/ci.sh on a real git
# range, a stub CodeHost and a stub Tracker. The base is this checkout's
# own judges, with GATES narrowed to risk (the one gate that routes; the
# other five need an engine or the network). The PR only loosens
# policy/merge.env so that every level auto-merges.
#   h1: the ticket's perimeter holds the diff. The PR's own policy would
#       auto-merge it; the CI step must classify it high (platform) with the
#       base's policy and send it to review.
#   h2: the same diff under a ticket whose perimeter does not hold it:
#       ci-failed, NO-GO on the perimeter, no gate run, whoever wrote it.
if [ -z "$mismatch" ]; then
  g="$root/g"
  mkdir -p "$g/host/gates" "$g/host/ci" "$g/host/core/steps" "$g/host/policy" "$g/host/app" "$g/tickets"
  sed 's/^GATES := .*/GATES := risk/' Makefile > "$g/host/Makefile"
  cp -R profiles "$g/host/profiles"
  cp app/workload.env "$g/host/app/workload.env"
  cp gates/risk.sh "$g/host/gates/"
  cp ci/lib.sh "$g/host/ci/"
  cp core/risk.py core/perimeter.sh "$g/host/core/"
  cp core/steps/ci.sh "$g/host/core/steps/"
  cp policy/merge.env "$g/host/policy/"
  (
    export GIT_AUTHOR_NAME=ci GIT_AUTHOR_EMAIL=ci@localhost GIT_COMMITTER_NAME=ci GIT_COMMITTER_EMAIL=ci@localhost
    cd "$g/host"
    git init -q -b main . && git add -A && git -c commit.gpgsign=false commit -q -m base
    sed 's/^RISK_AUTO_MERGE_LEVELS=.*/RISK_AUTO_MERGE_LEVELS=low:medium:high/' policy/merge.env > policy/merge.env.new
    mv policy/merge.env.new policy/merge.env
    git checkout -q -b ticket/0001 && git -c commit.gpgsign=false commit -q -am 'every level auto-merges'
    git branch ticket/0002
  ) >"$log" 2>&1 || fail_case g-setup "could not build the host repo"
fi
if [ -z "$mismatch" ]; then
  base_sha=$(git -C "$g/host" rev-parse main)
  head_sha=$(git -C "$g/host" rev-parse ticket/0001)
  # The PR would route itself if its own policy judged it: without this
  # the case could pass for the wrong reason.
  git -C "$g/host" show "$head_sha:policy/merge.env" > "$g/pr-merge.env"
  own=$(git -C "$g/host" diff --no-renames --numstat "$base_sha" "$head_sha" \
    | python3 core/risk.py --policy "$g/pr-merge.env" | jq -r .decision)
  [ "$own" = auto-merge ] || fail_case g-premise "the PR's own policy says $own, want auto-merge"
  git clone -q "$g/host" "$g/tower" >"$log" 2>&1 || fail_case g-setup "could not clone the host repo"
fi
if [ -z "$mismatch" ]; then
  mkdir -p "$g/tower/adapters/stub-codehost" "$g/tower/adapters/stub-tracker"
  cat > "$g/tower/adapters/stub-codehost/clone-url.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
printf '%s\n' "$d/host"
STUB
  cat > "$g/tower/adapters/stub-codehost/status.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
printf '%s %s\n' "$1" "$2" >> "$d/status.log"
STUB
  cat > "$g/tower/adapters/stub-tracker/get.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
cat "$d/tickets/$1.md"
STUB
  cat > "$g/tickets/0001.md" <<'TICKET'
# 0001 - loosen the merge policy

## Perimeter

- `policy/merge.env`
TICKET
  cat > "$g/tickets/0002.md" <<'TICKET'
# 0002 - docs only

## Perimeter

- `docs/*`
TICKET
  step_ci() {  # TICKET: runs the real CI step from the tower clone, JSON on stdout
    (cd "$g/tower" && TICKET=$1 PR_NUMBER=1 BASE_SHA=$base_sha HEAD_SHA=$head_sha \
      CODE_HOST=stub-codehost TRACKER=stub-tracker WORKLOAD=app GATES_OUT=.gates-out \
      sh core/steps/ci.sh) 2>"$log"
  }
  got=$(step_ci 0001) || fail_case h1 "the CI step exited $?"
  [ "$(printf '%s' "$got" | jq -r '.state + " " + .ci.verdict + " " + .ci.risk_level + " " + .ci.decision')" = "review GO high review" ] \
    || fail_case h1 "a PR loosening policy/merge.env: $got (want review GO high review)"
  [ "$(cat "$g/status.log")" = "$head_sha success" ] || fail_case h1 "status posted: $(cat "$g/status.log")"
fi
if [ -z "$mismatch" ]; then
  rm -f "$g/status.log"
  got=$(step_ci 0002) || fail_case h2 "the CI step exited $?"
  [ "$(printf '%s' "$got" | jq -r '.state + " " + .ci.verdict + " " + .ci.failed')" = "ci-failed NO-GO perimeter" ] \
    || fail_case h2 "a PR outside its ticket's perimeter: $got (want ci-failed NO-GO perimeter)"
  case "$(printf '%s' "$got" | jq -r .ci.line)" in
    "NO-GO: perimeter — policy/merge.env is outside"*) : ;;
    *) fail_case h2 "line does not name the file: $(printf '%s' "$got" | jq -r .ci.line)" ;;
  esac
  ! grep -q '^risk: ' "$log" || fail_case h2 "a gate ran on a diff outside the perimeter"
  [ "$(cat "$g/status.log")" = "$head_sha failure" ] || fail_case h2 "status posted: $(cat "$g/status.log")"
fi

[ -z "$mismatch" ] || nogo "case $mismatch disagrees with docs/adr/0019, 0033 or 0034"
go
