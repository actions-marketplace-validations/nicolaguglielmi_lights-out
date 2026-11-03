#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-crew: the ticket-to-PR driver (docs/adr/0017 §4). Vendor-free: it
# only calls the TRACKER, CODE_HOST and AGENT_HARNESS adapter scripts the
# profile names, plus core/harness-check.sh's harness-independent success
# check (docs/adr/0017 §1 owner addition: exit 0 alone is not success). No
# Gitea word appears below, and one Gemini word: the key a user needs at L1
# (docs/adr/0037 §8). The model never holds a credential:
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
: "${WORKLOAD:?WORKLOAD not set; run this via ./go, not directly}"

# A role without a prompt has no run at M5 (docs/adr/0017 §7): the reason
# is whichever milestone's ROLE.md names, not re-derived here.
if [ ! -f "roles/$ROLE/prompt.md" ]; then
  reason=$(head -n1 "roles/$ROLE/ROLE.md" 2>/dev/null || printf 'no roles/%s/prompt.md and no ROLE.md' "$ROLE")
  nogo "role $ROLE has no prompt yet" "$reason"
fi
# shellcheck disable=SC1090,SC1091 # role.env's path is built from $ROLE
. "roles/$ROLE/role.env"
# A role may name its own harness (docs/adr/0020 §1); the profile's is the default.
harness=${HARNESS:-$AGENT_HARNESS}

# docs/adr/0037 §8: fixtures/ holds this checkout's runs on its own
# tickets. An attached repository has none, so at L0 there is nothing to
# replay: say so before anything is bootstrapped, never a fake success.
if [ -n "${WORKLOAD_ATTACHED:-}" ] && [ "$harness" = replay ]; then
  nogo "the attached repository $(git -C "$WORKLOAD" remote get-url origin 2>/dev/null || printf '%s' "$WORKLOAD") has no recordings to replay at L0; run the crew at L1: PROFILE=l1 and GEMINI_API_KEY in .env (see .env.example)"
fi
: "${WORKLOAD_CONTRACT:?WORKLOAD_CONTRACT not set; run this via ./go, not directly}"
# The workload's brief for the dev-worker (docs/adr/0037 §6): where its
# code is and how its tests run. Checked before any work starts.
brief="$WORKLOAD_CONTRACT/worker.md"
[ -f "$brief" ] || nogo "$brief is missing; the worker would start from no brief (docs/adr/0037 §6)"

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

# A workload may need its checked-out workspace prepared before the
# harness starts on it — a layout its test suite assumes but a plain
# checkout does not provide (docs/adr/0030 §3). Optional: a workload
# without one skips this silently.
if [ -f "$WORKLOAD_CONTRACT/crew-prepare.sh" ]; then
  sh "$WORKLOAD_CONTRACT/crew-prepare.sh" "$crew_dir/workspace"
fi

# The harness's input (docs/adr/0037 §6, review's precedent in ADR 0021
# §3): the ticket, then the workload's brief. ticket.md stays the ticket
# alone, for the perimeter check below.
{
  cat "$crew_dir/ticket.md"
  printf '\n---\n\n'
  cat "$brief"
} > "$crew_dir/input.md"

mkdir -p "$crew_dir/out"

printf '[crew] ticket %s: role %s, harness %s\n' "$TICKET" "$ROLE" "$harness" >&2

ROLE="$ROLE" TICKET="$TICKET" TICKET_FILE="$crew_dir/input.md" \
WORKSPACE="$crew_dir/workspace" BASE="$base" OUT="$crew_dir/out" \
THINKING="$THINKING" MAX_TURNS="$MAX_TURNS" TIMEOUT_S="$TIMEOUT_S" TOKEN_BUDGET="$TOKEN_BUDGET" \
  sh "adapters/$harness/run.sh" >&2 \
  || nogo "$harness run failed for ticket $TICKET"

sh core/harness-check.sh "$crew_dir/out" "$crew_dir/workspace" "$base" \
  || nogo "worker produced no change or an incomplete artefact"

# Ticket 0003 (docs/adr/0021 §5): the diff must stay inside the ticket's
# declared perimeter, checked before a PR ever exists so a bad fixture is
# never written and the demo's own PRs are checked the same way.
perimeter_out=$(git -C "$crew_dir/workspace" diff --no-renames --name-only "$base"..HEAD \
  | sh core/perimeter.sh "$crew_dir/ticket.md" 2>&1) && perimeter_rc=0 || perimeter_rc=$?
[ "$perimeter_rc" -eq 0 ] || nogo "$perimeter_out"

sh "adapters/$CODE_HOST/push.sh" "$crew_dir/workspace" "ticket/$TICKET" >&2 \
  || nogo "push to $CODE_HOST failed"

pr_line=$(sh "adapters/$CODE_HOST/open-pr.sh" "ticket/$TICKET" "$crew_dir/out/pr.json") \
  || nogo "open-pr on $CODE_HOST failed"
pr_number=${pr_line%% *}
pr_url=${pr_line#* }

# BASE_SHA and HEAD_SHA: the range the gates judge and the tower records
# (docs/adr/0019 §1); HEAD_SHA is what the code host now holds on the branch.
{
  printf 'PR_NUMBER=%s\n' "$pr_number"
  printf 'PR_URL=%s\n' "$pr_url"
  printf 'BASE_SHA=%s\n' "$base"
  printf 'HEAD_SHA=%s\n' "$(git -C "$crew_dir/workspace" rev-parse HEAD)"
} > "$crew_dir/pr-opened.env"

printf '[crew] ticket %s: PR #%s %s\n' "$TICKET" "$pr_number" "$pr_url" >&2
go
