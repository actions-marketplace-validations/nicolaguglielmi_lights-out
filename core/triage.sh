#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-triage: an alert in, an incident out (docs/adr/0020 §3; plan §8
# step 7). Runs the ops-triage role on ALERT through its harness and
# turns the role's tool calls into .crew/triage/<name>/incident.json:
# the alert, a title, the ordered hypotheses and the proposal. The role
# proposes; nothing here acts on the proposal, and the role has no tool
# that could. NO-GO when the incident is not one: fewer than two ranked
# hypotheses, a proposal without an incident before it, or a rollback of
# a version the alert did not name. Vendor-free: only the harness adapter
# the role names is called. Reuses ci/lib.sh's go/nogo.
set -eu
name=triage
. ci/lib.sh

: "${ALERT:?ALERT not set; ./go triage ALERT=<file>}"
: "${AGENT_HARNESS:?AGENT_HARNESS not set; run this via ./go, not directly}"
: "${TRIAGE_OUT:=.crew/triage}"

[ -f "$ALERT" ] || nogo "no alert at $ALERT"
alert=$(jq -c . "$ALERT" 2>/dev/null) || nogo "$ALERT is not JSON"
alert_version=$(printf '%s' "$alert" | jq -r '.version // empty')
[ -n "$alert_version" ] || nogo "$ALERT names no version"
case_name=$(basename "$ALERT" .json)

[ -f roles/ops-triage/role.env ] || nogo "roles/ops-triage/role.env not found"
# shellcheck disable=SC1091 # the role's budgets
. roles/ops-triage/role.env
harness=${HARNESS:-$AGENT_HARNESS}
[ -f "adapters/$harness/run.sh" ] || nogo "adapters/$harness/run.sh not found for the ops-triage role"

out="$TRIAGE_OUT/$case_name"
rm -rf "$out"
mkdir -p "$out/out"
ROLE=ops-triage INPUT="$ALERT" OUT="$out/out" \
  THINKING="${THINKING:-low}" TIMEOUT_S="${TIMEOUT_S:-900}" \
  sh "adapters/$harness/run.sh" >&2 || nogo "the ops-triage role did not finish ($harness)"

calls="$out/out/calls.json"
[ -f "$calls" ] || nogo "the ops-triage role left no calls.json"
# The order matters: the incident must be filed before anything is proposed.
sequence=$(jq -r '[.[].name] | join(" ")' "$calls")
case "$sequence" in
  "file_incident propose_rollback"|"file_incident propose_hold") ;;
  *) nogo "expected file_incident then one proposal, got: ${sequence:-nothing}" ;;
esac
hypotheses=$(jq -c '[.[] | select(.name == "file_incident")][0].args.hypotheses // []' "$calls")
count=$(printf '%s' "$hypotheses" | jq 'length')
[ "$count" -ge 2 ] || nogo "an incident needs at least two ranked hypotheses, got $count"
ranked=$(printf '%s' "$hypotheses" | jq '[.[] | .rank] | (length == (unique | length)) and all(. != null)')
[ "$ranked" = true ] || nogo "hypotheses are not uniquely ranked"
proposal=$(jq -c '[.[] | select(.name == "propose_rollback" or .name == "propose_hold")][0]
  | {action: (if .name == "propose_rollback" then "rollback" else "hold" end), version: .args.version, reason: .args.reason}' "$calls")
action=$(printf '%s' "$proposal" | jq -r .action)
if [ "$action" = rollback ]; then
  proposed=$(printf '%s' "$proposal" | jq -r '.version // empty')
  [ "$proposed" = "$alert_version" ] || nogo "rollback proposed for \"$proposed\", the alert is about $alert_version"
fi

jq -n --argjson alert "$alert" --argjson hypotheses "$hypotheses" --argjson proposal "$proposal" \
  --arg title "$(jq -r '[.[] | select(.name == "file_incident")][0].args.title // ""' "$calls")" \
  --argjson run "$(cat "$out/out/run.json")" \
  '{alert: $alert, title: $title, hypotheses: ($hypotheses | sort_by(.rank)), proposal: $proposal, run: $run}' \
  > "$out/incident.json"
{
  printf '[triage] %s: incident "%s"\n' "$case_name" "$(jq -r .title "$out/incident.json")"
  jq -r '.hypotheses[] | "         \(.rank). \(.cause) — \(.evidence)"' "$out/incident.json"
  printf '         proposal: %s %s — %s\n' "$action" "$(printf '%s' "$proposal" | jq -r '.version // ""')" \
    "$(printf '%s' "$proposal" | jq -r .reason)"
  printf '         written to %s/incident.json\n' "$out"
} >&2
go
