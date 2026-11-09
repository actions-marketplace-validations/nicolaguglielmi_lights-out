#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The plan job of ci, stranger, self, podman and package (docs/adr/0065).
#   sh .github/plan.sh classify   changed paths on stdin: `docs` when every
#                                 one is documentation (§3), else `code`
#   sh .github/plan.sh            in a job: writes run= and full= to
#                                 $GITHUB_OUTPUT, the reason to the summary
# run=false only on a push to main whose commit a run of this workflow,
# pushed to another branch, already judged green (§2). full=false only on
# a push whose every changed path is documentation (§3). Needs gh, jq and
# GH_TOKEN with actions: read.
set -eu

classify() {
  n=0
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    n=$((n + 1))
    case "$p" in
      tickets/*|roles/*|workloads/*|.lights-out/*|fixtures/*|docs/assets/*) echo code; return ;;
      docs/*|site/*|.claude/*|actions/*/README.md|console/README.md) ;;
      */*) echo code; return ;;
      *.md) ;;
      *) echo code; return ;;
    esac
  done
  if [ "$n" -gt 0 ]; then echo docs; else echo code; fi
}

if [ "${1:-}" = classify ]; then
  classify
  exit 0
fi

: "${GITHUB_OUTPUT:?run this in a GitHub Actions job}"
summary=${GITHUB_STEP_SUMMARY:-/dev/null}
run=true full=true

if [ "$GITHUB_EVENT_NAME" = push ] && [ "$GITHUB_REF" = refs/heads/main ]; then
  judged=$(gh api "repos/$GITHUB_REPOSITORY/actions/runs?head_sha=$GITHUB_SHA&status=success&event=push&per_page=100" \
    --jq "[.workflow_runs[] | select(.name == \"$GITHUB_WORKFLOW\" and .head_branch != \"main\") | .html_url] | first // empty" 2>/dev/null || :)
  if [ -n "$judged" ]; then
    run=false
    printf 'This commit was judged green on another branch: %s (docs/adr/0065 §2)\n' "$judged" >> "$summary"
  fi
fi

before=${PUSH_BEFORE:-}
if [ "$run" = true ] && [ "$GITHUB_EVENT_NAME" = push ] && [ -n "$before" ] \
   && [ "$before" != 0000000000000000000000000000000000000000 ]; then
  if files=$(gh api "repos/$GITHUB_REPOSITORY/compare/$before...$GITHUB_SHA" \
      --jq 'if (.files | length) < 300 then .files[].filename else error("300 files or more") end' 2>/dev/null) \
     && [ "$(printf '%s\n' "$files" | classify)" = docs ]; then
    full=false
    printf 'Documentation only, %s path(s): the demo and the heavy jobs skip (docs/adr/0065 §3)\n' \
      "$(printf '%s\n' "$files" | grep -c .)" >> "$summary"
  fi
fi

printf 'run=%s\nfull=%s\n' "$run" "$full" >> "$GITHUB_OUTPUT"
printf 'plan: run=%s full=%s\n' "$run" "$full"
