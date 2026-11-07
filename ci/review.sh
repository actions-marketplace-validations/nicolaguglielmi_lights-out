#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-review: proves core/steps/review.sh (docs/adr/0021 §2, §3) cold, no
# plane, no real model. A temp root gets a stub CODE_HOST (clone-url.sh
# points at a real local git repo carrying a real `ticket/<id>` branch,
# so fetch/clone/checkout/diff all run for real; status.sh only logs), a
# stub TRACKER (fixed ticket text), a stub AgentHarness whose final.md and
# run.json the test controls per case, and the real roles/test-reviewer
# prompt.md/role.env (ADR 0021 gives the reviewer no other adapter). Cases:
# APPROVED, CHANGES-REQUESTED, a garbage first line, an empty reason, a
# missing final.md, a replay-shaped harness whose recorded input_sha256
# does not match the freshly-built input.md (a warning field, not a
# NO-GO — docs/adr/0021 §9's rejected alternative), and the FETCH_HEAD !=
# HEAD_SHA guard (ci.sh's own six lines, reused). Written from the ADR,
# checked against the actual script only for the exact wording asserted.
set -eu
name=review
. ci/lib.sh

step=core/steps/review.sh
[ -f "$step" ] || nogo "$step not found"

repo=$(pwd)
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT

mkdir -p "$root/adapters/stub-codehost" "$root/adapters/stub-tracker" \
  "$root/adapters/stub-harness" "$root/adapters/replay"
ln -s "$repo/roles" "$root/roles"
ln -s "$repo/core" "$root/core"

# --- a real upstream repo, standing in for the code host, with a real
# ticket/<id> branch two commits ahead of base ---
upstream="$root/upstream"
git init -q "$upstream"
git -C "$upstream" -c user.name=lights-out-tests -c user.email=tests@lights-out.invalid \
  commit -q --allow-empty -m base
base_sha=$(git -C "$upstream" rev-parse HEAD)
git -C "$upstream" checkout -q -b ticket/review-test
printf 'line\n' > "$upstream/file.txt"
git -C "$upstream" add -A
git -C "$upstream" -c user.name=lights-out-tests -c user.email=tests@lights-out.invalid \
  commit -q -m change
head_sha=$(git -C "$upstream" rev-parse HEAD)

# --- stub CodeHost: a real clone URL, a status.sh that only logs ---
cat > "$root/adapters/stub-codehost/clone-url.sh" <<EOF
#!/bin/sh
set -eu
printf '%s\n' "$upstream"
EOF
cat > "$root/adapters/stub-codehost/status.sh" <<EOF
#!/bin/sh
set -eu
printf '%s\n' "\$*" >> "$root/status.log"
EOF
chmod +x "$root/adapters/stub-codehost"/*.sh

# --- stub Tracker: fixed ticket text, the ticket id is not read ---
cat > "$root/adapters/stub-tracker/get.sh" <<'EOF'
#!/bin/sh
set -eu
printf 'Ticket %s: stub ticket text for ci/review.sh.\n' "$1"
EOF
chmod +x "$root/adapters/stub-tracker/get.sh"

# --- stub AgentHarness: writes $OUT/final.md and $OUT/run.json from env
# the test sets before calling review.sh (STUB_FINAL, STUB_NO_FINAL). ---
cat > "$root/adapters/stub-harness/run.sh" <<'EOF'
#!/bin/sh
set -eu
mkdir -p "$OUT"
if [ "${STUB_NO_FINAL:-0}" != 1 ]; then
  printf '%s\n' "$STUB_FINAL" > "$OUT/final.md"
fi
jq -n --arg h stub-harness '{harness: $h, model: "stub-model"}' > "$OUT/run.json"
EOF
chmod +x "$root/adapters/stub-harness/run.sh"

# --- a second stub, named `replay` (the adapter name IS the harness name
# review.sh checks), for the recorded-input-mismatch case only. ---
cat > "$root/adapters/replay/run.sh" <<'EOF'
#!/bin/sh
set -eu
mkdir -p "$OUT"
printf '%s\n' "$STUB_FINAL" > "$OUT/final.md"
jq -n --arg sha "$STUB_RECORDED_SHA" \
  '{harness: "replay", model: null, recorded: {input_sha256: $sha}}' > "$OUT/run.json"
EOF
chmod +x "$root/adapters/replay/run.sh"

# --- git needs $root itself to be a repo: review.sh's `git fetch` runs in
# the workload's repository (docs/adr/0037 §3), which the cases below make
# $root itself with WORKLOAD=. after they cd there. ---
git init -q "$root"

work=$(mktemp -d)
trap 'rm -rf "$root" "$work"' EXIT
mismatch=""

# run_review NAME WANT_RC HEAD [more env...]: runs core/steps/review.sh
# from $root with the shared TICKET/PR_NUMBER/BASE_SHA/CODE_HOST/TRACKER,
# HEAD_SHA overridable per case, captures stdout/stderr/exit.
run_review() {
  case_name=$1
  want_rc=$2
  head=$3
  shift 3
  rc=0
  ( cd "$root" && \
    env TICKET=review-test PR_NUMBER=1 BASE_SHA="$base_sha" HEAD_SHA="$head" \
      CODE_HOST=stub-codehost TRACKER=stub-tracker ROLE=test-reviewer WORKLOAD=. "$@" \
      sh "$repo/core/steps/review.sh" \
  ) >"$work/$case_name.out" 2>"$work/$case_name.err" || rc=$?
  if [ "$rc" != "$want_rc" ]; then
    printf 'ci-review: %s: want exit %s, got %s\n' "$case_name" "$want_rc" "$rc" >&2
    cat "$work/$case_name.err" >&2
    mismatch="$case_name(want exit $want_rc, got $rc)"
  fi
}

# (a) APPROVED: ci-passed, verdict approved, a harness that is not
# `replay` always reports input_matches_recorded true.
run_review approved 0 "$head_sha" \
  AGENT_HARNESS=stub-harness STUB_FINAL='APPROVED
Looks correct and in scope.'
if [ -z "$mismatch" ]; then
  out=$(cat "$work/approved.out")
  [ "$(printf '%s' "$out" | jq -r .state)" = ci-passed ] || mismatch="approved(state: $out)"
  [ "$(printf '%s' "$out" | jq -r .review.verdict)" = approved ] || mismatch="approved(verdict: $out)"
  [ "$(printf '%s' "$out" | jq -r .review.input_matches_recorded)" = true ] || mismatch="approved(input_matches_recorded: $out)"
fi

# (b) CHANGES-REQUESTED: ci-failed, verdict changes-requested.
if [ -z "$mismatch" ]; then
  run_review changes-requested 0 "$head_sha" \
    AGENT_HARNESS=stub-harness STUB_FINAL='CHANGES-REQUESTED
Missing coverage for the empty-input case.'
  out=$(cat "$work/changes-requested.out")
  [ "$(printf '%s' "$out" | jq -r .state)" = ci-failed ] || mismatch="changes-requested(state: $out)"
  [ "$(printf '%s' "$out" | jq -r .review.verdict)" = changes-requested ] || mismatch="changes-requested(verdict: $out)"
fi

# (c) a third/garbage first line: exit 1, no stdout, no default verdict.
if [ -z "$mismatch" ]; then
  run_review garbage 1 "$head_sha" \
    AGENT_HARNESS=stub-harness STUB_FINAL='MAYBE
some reason'
  [ -s "$work/garbage.out" ] && mismatch="garbage(unexpected stdout: $(cat "$work/garbage.out"))"
fi

# (d) an empty reason (nothing after the verdict line): exit 1, no stdout.
if [ -z "$mismatch" ]; then
  run_review empty-reason 1 "$head_sha" \
    AGENT_HARNESS=stub-harness STUB_FINAL='APPROVED'
  [ -s "$work/empty-reason.out" ] && mismatch="empty-reason(unexpected stdout: $(cat "$work/empty-reason.out"))"
fi

# (e) a missing final.md entirely: exit 1.
if [ -z "$mismatch" ]; then
  run_review missing-final 1 "$head_sha" \
    AGENT_HARNESS=stub-harness STUB_NO_FINAL=1 STUB_FINAL=unused
  [ -s "$work/missing-final.out" ] && mismatch="missing-final(unexpected stdout: $(cat "$work/missing-final.out"))"
fi

# (f) a replay-shaped harness whose recorded input_sha256 does not match
# the freshly-built input.md: still a success, input_matches_recorded is
# false (docs/adr/0021 §9's rejected alternative: a prose edit to the
# ticket must not block the tower by itself).
if [ -z "$mismatch" ]; then
  run_review replay-mismatch 0 "$head_sha" \
    AGENT_HARNESS=replay STUB_FINAL='APPROVED
Fine, but the record predates this diff.' STUB_RECORDED_SHA=0000000000000000000000000000000000000000000000000000000000000000
  out=$(cat "$work/replay-mismatch.out")
  [ "$(printf '%s' "$out" | jq -r .state)" = ci-passed ] || mismatch="replay-mismatch(state: $out)"
  [ "$(printf '%s' "$out" | jq -r .review.input_matches_recorded)" = false ] || mismatch="replay-mismatch(input_matches_recorded: $out)"
fi

# (g) the FETCH_HEAD != HEAD_SHA guard (ci.sh's own six lines, reused): a
# stale HEAD_SHA argument fails before any clone or harness run, naming
# the mismatch on stderr, nothing on stdout.
if [ -z "$mismatch" ]; then
  stale=0000000000000000000000000000000000dead
  run_review stale-head 1 "$stale" \
    AGENT_HARNESS=stub-harness STUB_FINAL='APPROVED
unused'
  [ -s "$work/stale-head.out" ] && mismatch="stale-head(unexpected stdout: $(cat "$work/stale-head.out"))"
  if [ -z "$mismatch" ]; then
    grep -q "$stale" "$work/stale-head.err" || mismatch="stale-head(stderr does not name $stale: $(cat "$work/stale-head.err"))"
  fi
fi

[ -z "$mismatch" ] || nogo "stub case $mismatch disagrees with docs/adr/0021"

go
