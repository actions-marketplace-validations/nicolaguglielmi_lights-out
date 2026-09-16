#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-ci (docs/adr/0019 §1, §4): the CI leg at L0. Fetches ticket/<id>
# from the code host (proves the branch exists there, not in .crew/),
# asserts it is the head the PR was opened with, judges the range with
# `make gates` in a throwaway worktree — the M4 mechanism demo-gates and
# demo-crew use — posts the verdict as the `gates` commit status, leaves
# $GATES_OUT/verdict.env at the repo root, and prints the fields for the
# document. Next state: ci-passed on GO + auto-merge, review on GO +
# review, ci-failed on NO-GO. Called by the tower (PR_NUMBER, BASE_SHA,
# HEAD_SHA from the document) and by the Makefile's crew-run (from
# .crew/<id>/pr-opened.env): one code path for both.
set -eu
: "${TICKET:?TICKET not set}"
: "${PR_NUMBER:?PR_NUMBER not set}"
: "${BASE_SHA:?BASE_SHA not set}"
: "${HEAD_SHA:?HEAD_SHA not set}"
: "${CODE_HOST:?CODE_HOST not set; run this via ./go, not directly}"
: "${GATES_OUT:=.gates-out}"

branch="ticket/$TICKET"
clone_url=$(sh "adapters/$CODE_HOST/clone-url.sh")
git fetch -q "$clone_url" "$branch" \
  || { printf 'step-ci: could not fetch %s from %s\n' "$branch" "$CODE_HOST" >&2; exit 1; }
fetched=$(git rev-parse FETCH_HEAD)
[ "$fetched" = "$HEAD_SHA" ] \
  || { printf 'step-ci: %s on %s is %s, the PR was opened at %s\n' "$branch" "$CODE_HOST" "$fetched" "$HEAD_SHA" >&2; exit 1; }

wt=$(mktemp -d)/wt
git worktree add --detach "$wt" FETCH_HEAD >/dev/null 2>&1 \
  || { printf 'step-ci: git worktree add failed\n' >&2; exit 1; }
trap 'git worktree remove --force "$wt" >/dev/null 2>&1 || true' EXIT

out=$( (cd "$wt" && make --no-print-directory gates BASE="$BASE_SHA" HEAD="$HEAD_SHA") ) || true
printf '[ci] gates: %s\n' "$out" >&2
mkdir -p "$GATES_OUT"
cp "$wt/$GATES_OUT/verdict.env" "$GATES_OUT/verdict.env" 2>/dev/null || : > "$GATES_OUT/verdict.env"

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
[ "$state" != review ] || printf '[ci] risk %s: review requested, and nobody reviews until the review milestone after M8 (docs/adr/0020 §9) — terminal\n' "$level" >&2

jq -cn --arg state "$state" --arg verdict "$verdict" --arg failed "$failed" \
  --arg level "$level" --arg decision "$decision" --arg head "$HEAD_SHA" --arg line "$out" \
  '{state: $state, ci: {verdict: $verdict, failed: (if $failed == "" then null else $failed end),
    risk_level: $level, decision: $decision, head_sha: $head, line: $line}}'
