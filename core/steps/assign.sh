#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-assign (docs/adr/0019 §1): ticket → PR through core/crew.sh, then
# the record: the PR, the range, which harness and model produced it, and
# the spec as the harness read it (sha256 and first line of the ticket
# text). Re-runnable: crew.sh wipes .crew/<ticket> and reclones. Prints
# the fields to merge into the document; next state pr-opened.
set -eu
: "${TICKET:?TICKET not set}"
: "${ROLE:=dev-worker}"

crew_dir=".crew/$TICKET"
TICKET="$TICKET" ROLE="$ROLE" sh core/crew.sh >&2

# shellcheck disable=SC1090,SC1091 # written by crew.sh just now
. "$crew_dir/pr-opened.env"
harness=$(jq -r '.harness // "unknown"' "$crew_dir/out/run.json")
# replay records the model of the run it replays, never one of its own.
model=$(jq -r '.model // .recorded.model // null' "$crew_dir/out/run.json")
spec_sha=$(sha256sum "$crew_dir/ticket.md" | cut -d' ' -f1)
spec_title=$(head -n1 "$crew_dir/ticket.md" | sed 's/^# *//')

jq -cn --arg n "$PR_NUMBER" --arg url "$PR_URL" --arg base "$BASE_SHA" --arg head "$HEAD_SHA" \
  --arg harness "$harness" --arg model "$model" --arg role "$ROLE" \
  --arg sha "$spec_sha" --arg title "$spec_title" \
  '{state: "pr-opened",
    pr: {number: ($n | tonumber), url: $url, base_sha: $base, head_sha: $head},
    task: {role: $role, harness: $harness, model: (if $model == "null" then null else $model end)},
    spec: {sha256: $sha, title: $title}}'
