#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-ci (docs/adr/0019 §1, §4): the CI leg at L0. Fetches ticket/<id>
# from the code host (proves the branch exists there, not in .crew/),
# asserts it is the head the PR was opened with, re-checks the ticket's
# `## Perimeter` on the PR's diff, judges the range with `make gates` in a
# throwaway worktree — the M4 mechanism demo-gates and demo-crew use —
# posts the verdict as the `gates` commit status, leaves
# $GATES_OUT/verdict.env at the repo root, and prints the fields for the
# document. Next state: ci-passed on GO + auto-merge, review on GO +
# review (core/steps/review.sh picks it up from there, docs/adr/0021),
# ci-failed on NO-GO. Called by the tower (PR_NUMBER, BASE_SHA,
# HEAD_SHA from the document) and by the Makefile's crew-run (from
# .crew/<id>/pr-opened.env): one code path for both.
#
# A PR is never judged by its own judges (docs/adr/0033): the worktree
# holds the PR's head, but the Makefile and what it includes, gates/,
# ci/, core/ and policy/ are the base's; the ticket comes from the
# Tracker and the perimeter check from this checkout, never from the PR.
set -eu
: "${TICKET:?TICKET not set}"
: "${PR_NUMBER:?PR_NUMBER not set}"
: "${BASE_SHA:?BASE_SHA not set}"
: "${HEAD_SHA:?HEAD_SHA not set}"
: "${CODE_HOST:?CODE_HOST not set; run this via ./go, not directly}"
: "${TRACKER:?TRACKER not set; run this via ./go, not directly}"
: "${WORKLOAD:?WORKLOAD not set; run this via ./go, not directly}"
: "${GATES_OUT:=.gates-out}"

branch="ticket/$TICKET"
clone_url=$(sh "adapters/$CODE_HOST/clone-url.sh")
git fetch -q "$clone_url" "$branch" \
  || { printf 'step-ci: could not fetch %s from %s\n' "$branch" "$CODE_HOST" >&2; exit 1; }
fetched=$(git rev-parse FETCH_HEAD)
[ "$fetched" = "$HEAD_SHA" ] \
  || { printf 'step-ci: %s on %s is %s, the PR was opened at %s\n' "$branch" "$CODE_HOST" "$fetched" "$HEAD_SHA" >&2; exit 1; }

tmp=$(mktemp -d)
wt=$tmp/wt
trap 'git worktree remove --force "$wt" >/dev/null 2>&1 || true; rm -rf "$tmp"' EXIT

# docs/adr/0033 §2: the ticket's perimeter again, on the PR's own changes
# (from the merge-base, as the code host shows them and the gates'
# require_range sees them), whoever produced the diff.
merge_base=$(git merge-base "$BASE_SHA" "$HEAD_SHA") \
  || { printf 'step-ci: no merge-base between %s and %s\n' "$BASE_SHA" "$HEAD_SHA" >&2; exit 1; }
sh "adapters/$TRACKER/get.sh" "$TICKET" > "$tmp/ticket.md" \
  || { printf 'step-ci: %s has no ticket %s\n' "$TRACKER" "$TICKET" >&2; exit 1; }
perimeter=$(git diff --no-renames --name-only "$merge_base" "$HEAD_SHA" \
  | sh core/perimeter.sh "$tmp/ticket.md" 2>&1) && perimeter_rc=0 || perimeter_rc=$?

mkdir -p "$GATES_OUT"
if [ "$perimeter_rc" -ne 0 ]; then
  out="NO-GO: perimeter — $(printf '%s' "$perimeter" | tr '\n' ' ')"
  printf 'GATES=NO-GO\nFAILED=perimeter\nRISK_LEVEL=unknown\nRISK_DECISION=unknown\n' > "$GATES_OUT/verdict.env"
else
  git worktree add --detach "$wt" FETCH_HEAD >/dev/null 2>&1 \
    || { printf 'step-ci: git worktree add failed\n' >&2; exit 1; }
  # docs/adr/0033 §1: the code under test is the PR's; what judges it is
  # the base's. restore is no-overlay: a judge the PR adds is removed too.
  judges="Makefile profiles gates ci core policy $WORKLOAD/workload.env"
  # shellcheck disable=SC2086 # $judges is a list of paths, split on purpose
  git -C "$wt" restore --source="$BASE_SHA" --staged --worktree -- $judges \
    || { printf 'step-ci: could not take %s from the base %s\n' "$judges" "$BASE_SHA" >&2; exit 1; }
  out=$( (cd "$wt" && make --no-print-directory gates BASE="$BASE_SHA" HEAD="$HEAD_SHA") ) || true
  cp "$wt/$GATES_OUT/verdict.env" "$GATES_OUT/verdict.env" 2>/dev/null || : > "$GATES_OUT/verdict.env"
fi
printf '[ci] gates: %s\n' "$out" >&2

verdict=$(grep '^GATES=' "$GATES_OUT/verdict.env" | cut -d= -f2) || verdict=""
[ -n "$verdict" ] || { printf 'step-ci: gates left no verdict\n' >&2; exit 1; }
level=$(grep '^RISK_LEVEL=' "$GATES_OUT/verdict.env" | cut -d= -f2) || level=unknown
decision=$(grep '^RISK_DECISION=' "$GATES_OUT/verdict.env" | cut -d= -f2) || decision=unknown
failed=$(grep '^FAILED=' "$GATES_OUT/verdict.env" | cut -d= -f2) || failed=""

case "$verdict/$decision" in
  GO/auto-merge) state=ci-passed; status=success ;;
  GO/*) state=review; status=success ;;
  *) state=ci-failed; status=failure ;;
esac
sh "adapters/$CODE_HOST/status.sh" "$HEAD_SHA" "$status" gates "$out" \
  || { printf 'step-ci: could not post the status\n' >&2; exit 1; }
[ "$state" != review ] || printf '[ci] risk %s: review requested; test-reviewer picks it up next (docs/adr/0021)\n' "$level" >&2

jq -cn --arg state "$state" --arg verdict "$verdict" --arg failed "$failed" \
  --arg level "$level" --arg decision "$decision" --arg head "$HEAD_SHA" --arg line "$out" \
  '{state: $state, ci: {verdict: $verdict, failed: (if $failed == "" then null else $failed end),
    risk_level: $level, decision: $decision, head_sha: $head, line: $line}}'
