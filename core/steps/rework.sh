#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-rework (docs/adr/0038): a head the gates or the reviewer rejected
# goes back to dev-worker with the verdict. Reads the document only: the
# attempt number, and who rejected — mainline.verdict NO-GO is the tower
# checking main (docs/adr/0056 §6: judge `base` or `main`), then
# ci.verdict NO-GO is the gates, otherwise review.verdict
# changes-requested is the reviewer; anything
# else is no verdict to rework, a step failure. Appends the verdict to
# `rework` (one entry per rejected attempt, so the next attempt's ci and
# review fields cannot erase it). At policy/rework.env's cap, read from
# this checkout and never from the PR, prints needs-human and runs
# nothing. Otherwise writes the verdict document — the NO-GO line and the
# gate's own details, or the reviewer's verdict and reason; never a
# transcript — and runs core/crew.sh for the next attempt from the head
# that was judged: same ticket, same perimeter, same PR, new head — or,
# for the tower's two judges, from main's head (REWORK_FRESH). Prints
# pr-opened with ci and review cleared, so merge and audit can only read
# the new attempt's verdicts. A crew failure exits 1: the tower strands
# the ticket at ci-failed for ./go resume (docs/adr/0034), not an attempt.
set -eu
: "${TICKET:?TICKET not set}"
: "${DOC_FILE:?DOC_FILE not set; run this via core/tower.sh, not directly}"
: "${ROLE:=dev-worker}"

# shellcheck disable=SC1091 # policy/rework.env is this checkout's own
. policy/rework.env
: "${REWORK_MAX_ATTEMPTS:?policy/rework.env sets no REWORK_MAX_ATTEMPTS}"

attempt=$(jq -r '.attempt // 1' "$DOC_FILE")
judged=$(jq -r '.pr.head_sha // empty' "$DOC_FILE")
[ -n "$judged" ] || { printf 'step-rework: %s has no pr.head_sha\n' "$DOC_FILE" >&2; exit 1; }

entry=$(jq -c --argjson n "$attempt" --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
  if .mainline.verdict == "NO-GO" or .ci.verdict == "NO-GO" then (if .mainline.verdict == "NO-GO" then .mainline else .ci + {judge: "gates"} end) as $v |
    {attempt: $n, judge: $v.judge, failed: ($v.failed // null), head_sha: .pr.head_sha, line: $v.line, details: ($v.details // []), sast: ($v.sast // null), lines: .ci.lines, at: $at}
  elif .review.verdict == "changes-requested" then
    {attempt: $n, judge: "review", failed: null, sast: null, head_sha: .pr.head_sha,
     line: "CHANGES-REQUESTED — \(.review.role)", details: (.review.reason // "" | split("\n")), lines: .ci.lines, at: $at}
  else empty end' "$DOC_FILE")
[ -n "$entry" ] || {
  printf 'step-rework: ticket %s is at ci-failed with neither a gates NO-GO nor a changes-requested review\n' "$TICKET" >&2
  exit 1
}
rework=$(jq -c --argjson e "$entry" '(.rework // []) + [$e]' "$DOC_FILE")

if [ "$attempt" -ge "$REWORK_MAX_ATTEMPTS" ]; then
  printf '[rework] ticket %s: attempt %s of %s rejected (%s); a human is needed\n' \
    "$TICKET" "$attempt" "$REWORK_MAX_ATTEMPTS" "$(printf '%s' "$entry" | jq -r .line)" >&2
  jq -cn --argjson rework "$rework" '{state: "needs-human", rework: $rework}'
  exit 0
fi

next=$((attempt + 1))
verdict=$(mktemp)
trap 'rm -f "$verdict"' EXIT
printf '%s' "$entry" | jq -r --argjson next "$next" --argjson max "$REWORK_MAX_ATTEMPTS" '
  "## Rework: attempt \($next) of \($max)\n",
  "Your previous attempt (head \(.head_sha)) was not accepted. The verdict",
  "below is everything the \({gates: "gates", review: "reviewer"}[.judge] // "tower") said about it. Your workspace \(if .judge == "base" or .judge == "main" then "starts" else "already" end)",
  (if .judge == "base" or .judge == "main" then "from the head of main, without that attempt: redo the ticket on it, addressing every point the verdict raises," else "holds that attempt: change it to address every point the verdict raises," end),
  "within the ticket above, and nothing else.\n",
  "Verdict:\n",
  "    \(.line)",
  (if (.details | length) > 0 then "\nDetails:\n", (.details[] | "    \(.)") else empty end)' > "$verdict"

printf '[rework] ticket %s: attempt %s rejected by the %s; attempt %s of %s\n' \
  "$TICKET" "$attempt" "$(printf '%s' "$entry" | jq -r .judge)" "$next" "$REWORK_MAX_ATTEMPTS" >&2
crew_dir=".crew/$TICKET"
TICKET="$TICKET" ROLE="$ROLE" ATTEMPT="$next" REWORK_FILE="$verdict" REWORK_HEAD="$judged" REWORK_FRESH="$(printf '%s' "$entry" | jq -r 'select(.judge == "base" or .judge == "main") | "1"')" \
  sh core/crew.sh >&2

# shellcheck disable=SC1090,SC1091 # written by crew.sh just now
. "$crew_dir/pr-opened.env"
# Who ran it and what it cost (docs/adr/0047 §2, P1), from run.json.
task=$(python3 core/tower.py task --patch "$crew_dir/out/run.json")

jq -cn --argjson next "$next" --argjson rework "$rework" --arg n "$PR_NUMBER" --arg url "$PR_URL" \
  --arg base "$BASE_SHA" --arg head "$HEAD_SHA" --arg role "$ROLE" --argjson task "$task" \
  '{state: "pr-opened", attempt: $next, rework: $rework, ci: null, review: null, mainline: null,
    pr: {number: ($n | tonumber), url: $url, base_sha: $base, head_sha: $head},
    task: ({role: $role} + $task)}'
