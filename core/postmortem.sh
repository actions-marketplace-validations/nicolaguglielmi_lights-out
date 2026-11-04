#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-postmortem: an incident document in, a post mortem and its tickets
# out (docs/adr/0044 §5). Runs the ops-triage role on INCIDENT through its
# harness; the role's one tool call, file_postmortem, becomes
# .crew/postmortem/<name>/postmortem.md and .json, and each action item a
# ticket through the Tracker port. NO-GO, in this order, when the
# document is not an incident or its release has no verdict; the role
# does not finish or answers with anything but exactly one file_
# postmortem; a timeline anchor names something the document does not
# hold, or none names the release or the chain's PR; the post mortem has
# no cause, no action or an empty field; an action cannot be filed.
# Nothing is written to the output directory unless the answer is GO.
# Vendor-free: only the harness and Tracker adapters named are called.
# Reuses ci/lib.sh's go_with/nogo.
set -eu
name=postmortem
. ci/lib.sh

: "${INCIDENT:?INCIDENT not set; ./go postmortem INCIDENT=<file>}"
: "${AGENT_HARNESS:?AGENT_HARNESS not set; run this via ./go, not directly}"
: "${TRACKER:?TRACKER not set; run this via ./go, not directly}"
: "${POSTMORTEM_OUT:=.crew/postmortem}"

[ -f "$INCIDENT" ] || nogo "no incident at $INCIDENT"
reason=$(python3 core/postmortem.py validate "$INCIDENT") || nogo "$reason"
incident=$(jq -r .name "$INCIDENT")
release=$(jq -r .release.version "$INCIDENT")
verdict=$(jq -r .release.verdict "$INCIDENT")
# A NO-GO leaves no post mortem of an earlier run standing in its place.
rm -rf "${POSTMORTEM_OUT:?}/$incident"

[ -f roles/ops-triage/role.env ] || nogo "roles/ops-triage/role.env not found"
# shellcheck disable=SC1091 # the role's budgets
. roles/ops-triage/role.env
harness=${HARNESS:-$AGENT_HARNESS}
[ -f "adapters/$harness/run.sh" ] || nogo "adapters/$harness/run.sh not found for the ops-triage role"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/out"
ROLE=ops-triage INPUT="$INCIDENT" OUT="$work/out" \
  THINKING="${THINKING:-low}" TIMEOUT_S="${TIMEOUT_S:-900}" \
  sh "adapters/$harness/run.sh" >&2 || nogo "the ops-triage role did not finish ($harness)"

calls="$work/out/calls.json"
[ -f "$calls" ] || nogo "the ops-triage role left no calls.json"
sequence=$(jq -r '[.[].name] | join(" ")' "$calls")
[ "$sequence" = file_postmortem ] || nogo "expected exactly file_postmortem, got: ${sequence:-nothing}"

reason=$(python3 core/postmortem.py check "$INCIDENT" "$calls" "$work/checked.json") || nogo "$reason"

# The tickets, only now that nothing else can fail: each action is filed
# under an origin, so a re-run finds its tickets and files none.
echo '{}' > "$work/tickets.json"
count=$(jq '.actions | length' "$work/checked.json")
n=1
while [ "$n" -le "$count" ]; do
  title=$(jq -r --argjson n "$n" '.actions[] | select(.n == $n) | .title' "$work/checked.json")
  body=$(jq -r --argjson n "$n" --arg i "$incident" --arg v "$release" --arg d "$verdict" '
    .actions[] | select(.n == $n)
    | "## Problem\n\n\(.problem)\n\nFound by the post mortem of incident `\($i)` (release `\($v)`, \($d)).\n\n## Acceptance criteria\n\n\(.acceptance)\n\n## Notes\n\nWritten by the ops-triage role from the incident document alone. It has not seen the code, so this ticket declares no perimeter: a human adds one before it is assigned."' \
    "$work/checked.json")
  id=$(printf '%s\n' "$body" | sh "adapters/$TRACKER/put.sh" "$title" "postmortem $incident action $n" 2>"$work/put.err") \
    || nogo "action $n has no ticket: $(tail -n1 "$work/put.err")"
  jq --arg n "$n" --arg id "$id" '. + {($n): $id}' "$work/tickets.json" > "$work/tickets.tmp"
  mv "$work/tickets.tmp" "$work/tickets.json"
  n=$((n + 1))
done

dest="$POSTMORTEM_OUT/$incident"
mkdir -p "$dest"
cp -R "$work/out" "$dest/out"
python3 core/postmortem.py render "$work/checked.json" "$work/tickets.json" "$work/out/run.json" "$dest"
printf '[postmortem] %s written to %s/postmortem.md\n' "$incident" "$dest" >&2
go_with "$count action item(s): tickets $(jq -r '[.[]] | join(" ")' "$work/tickets.json")"
