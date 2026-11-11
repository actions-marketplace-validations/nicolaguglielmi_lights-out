#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-assign (docs/adr/0019 §1): ticket → PR through core/crew.sh, then
# the record: the PR, the range, which harness and model produced it, and
# the spec as the harness read it (sha256 and first line of the ticket
# text). Re-runnable: crew.sh wipes .crew/<ticket> and reclones. Prints
# the fields to merge into the document; next state pr-opened, attempt 1
# (core/steps/rework.sh counts the next ones, docs/adr/0038).
# Two preconditions first (docs/adr/0053 §5-§6), each refusing with one
# line on stderr and exit 1, so the ticket waits at `opened` for `./go
# resume`: no open ticket holds a file of its perimeter, and an attached
# repository's base is green.
set -eu
: "${TICKET:?TICKET not set}"
: "${ROLE:=dev-worker}"

python3 core/assign.py "$TICKET"
# On an attached repository the code host is bootstrapped first, so the
# base judged is the commit core/crew.sh's own bootstrap leaves there and
# the worker clones, and a fresh plane has something to fetch (ci/assign.sh
# case h). Idempotent: crew.sh bootstraps again.
if [ -n "${WORKLOAD_ATTACHED:-}" ]; then
  sh "adapters/$CODE_HOST/bootstrap.sh" >&2 || { printf '[assign] %s bootstrap failed\n' "$CODE_HOST" >&2; exit 1; }
  sh core/base-gates.sh
fi

crew_dir=".crew/$TICKET"
TICKET="$TICKET" ROLE="$ROLE" sh core/crew.sh >&2

# shellcheck disable=SC1090,SC1091 # written by crew.sh just now
. "$crew_dir/pr-opened.env"
# Who ran it and what it cost (docs/adr/0047 §2, P1), from run.json.
task=$(python3 core/tower.py task "$crew_dir/out/run.json")
spec_sha=$(sha256sum "$crew_dir/ticket.md" | cut -d' ' -f1)
spec_title=$(head -n1 "$crew_dir/ticket.md" | sed 's/^# *//')

jq -cn --arg n "$PR_NUMBER" --arg url "$PR_URL" --arg base "$BASE_SHA" --arg head "$HEAD_SHA" \
  --arg role "$ROLE" \
  --arg sha "$spec_sha" --arg title "$spec_title" --argjson task "$task" \
  '{state: "pr-opened", attempt: 1,
    pr: {number: ($n | tonumber), url: $url, base_sha: $base, head_sha: $head},
    task: ({role: $role} + $task),
    spec: {sha256: $sha, title: $title}}'
