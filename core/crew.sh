#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-crew: the ticket-to-PR driver (docs/adr/0017 §4). Vendor-free: it
# only calls the TRACKER, CODE_HOST and AGENT_HARNESS adapter scripts the
# profile names, plus core/harness-check.sh's harness-independent success
# check (docs/adr/0017 §1 owner addition: exit 0 alone is not success). No
# Gitea or Gemini word appears below. The model never holds a credential:
# bootstrap and push run here, in workbench, with the authenticated URL
# passed as a command argument, never written to a .git/config.
#
# Not scanned by ci/contract.sh (core/, not ci/ gates/ verify/), but reuses
# ci/lib.sh's go/nogo for the same GO:/NO-GO: line shape.
set -eu
name=crew
. ci/lib.sh

: "${TICKET:?TICKET not set; run this via ./go assign TICKET=<id>}"
: "${ROLE:=dev-worker}"
: "${AGENT_HARNESS:?AGENT_HARNESS not set; run this via ./go, not directly}"
: "${CODE_HOST:?CODE_HOST not set; run this via ./go, not directly}"
: "${TRACKER:?TRACKER not set; run this via ./go, not directly}"

# A role without a prompt has no run at M5 (docs/adr/0017 §7): the reason
# is whichever milestone's ROLE.md names, not re-derived here.
if [ ! -f "roles/$ROLE/prompt.md" ]; then
  reason=$(head -n1 "roles/$ROLE/ROLE.md" 2>/dev/null || printf 'no roles/%s/prompt.md and no ROLE.md' "$ROLE")
  nogo "role $ROLE has no prompt yet" "$reason"
fi
# shellcheck disable=SC1091 # role.env's path is built from $ROLE
. "roles/$ROLE/role.env"

here=$(pwd)
crew_dir="$here/.crew/$TICKET"
rm -rf "$crew_dir"
mkdir -p "$crew_dir"

sh "adapters/$CODE_HOST/bootstrap.sh" >&2 || nogo "$CODE_HOST bootstrap failed"

sh "adapters/$TRACKER/get.sh" "$TICKET" > "$crew_dir/ticket.md" \
  || nogo "no such ticket: $TICKET"

git clone -q "$(sh "adapters/$CODE_HOST/clone-url.sh")" "$crew_dir/workspace" >&2 \
  || nogo "clone from $CODE_HOST failed"
base=$(git -C "$crew_dir/workspace" rev-parse HEAD)
git -C "$crew_dir/workspace" checkout -q -b "ticket/$TICKET" >&2

mkdir -p "$crew_dir/out"

printf '[crew] ticket %s: role %s, harness %s\n' "$TICKET" "$ROLE" "$AGENT_HARNESS" >&2

ROLE="$ROLE" TICKET="$TICKET" TICKET_FILE="$crew_dir/ticket.md" \
WORKSPACE="$crew_dir/workspace" BASE="$base" OUT="$crew_dir/out" \
THINKING="$THINKING" MAX_TURNS="$MAX_TURNS" TIMEOUT_S="$TIMEOUT_S" TOKEN_BUDGET="$TOKEN_BUDGET" \
  sh "adapters/$AGENT_HARNESS/run.sh" >&2 \
  || nogo "$AGENT_HARNESS run failed for ticket $TICKET"

sh core/harness-check.sh "$crew_dir/out" "$crew_dir/workspace" "$base" \
  || nogo "worker produced no change or an incomplete artefact"

sh "adapters/$CODE_HOST/push.sh" "$crew_dir/workspace" "ticket/$TICKET" >&2 \
  || nogo "push to $CODE_HOST failed"

pr_line=$(sh "adapters/$CODE_HOST/open-pr.sh" "ticket/$TICKET" "$crew_dir/out/pr.json") \
  || nogo "open-pr on $CODE_HOST failed"
pr_number=${pr_line%% *}
pr_url=${pr_line#* }

{
  printf 'PR_NUMBER=%s\n' "$pr_number"
  printf 'PR_URL=%s\n' "$pr_url"
} > "$crew_dir/pr-opened.env"

printf '[crew] ticket %s: PR #%s %s\n' "$TICKET" "$pr_number" "$pr_url" >&2
go
