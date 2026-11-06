#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-triage: an alert in, an incident out (docs/adr/0020 §3; plan §8
# step 7). Runs the ops-triage role on ALERT through its harness; core/
# triage.py judges the role's tool calls and writes .crew/triage/<name>/
# incident.json: the alert, a title, the ordered hypotheses and the
# proposal (docs/adr/0052 §3). The role proposes; nothing here acts on the
# proposal, and the role has no tool that could. Vendor-free: only the
# harness adapter the role names is called. Reuses ci/lib.sh's go/nogo.
set -eu
name=triage
. ci/lib.sh

: "${ALERT:?ALERT not set; ./go triage ALERT=<file>}"
: "${AGENT_HARNESS:?AGENT_HARNESS not set; run this via ./go, not directly}"
: "${TRIAGE_OUT:=.crew/triage}"

[ -f "$ALERT" ] || nogo "no alert at $ALERT"
reason=$(python3 core/triage.py alert "$ALERT") || nogo "$reason"

[ -f roles/ops-triage/role.env ] || nogo "roles/ops-triage/role.env not found"
# shellcheck disable=SC1091 # the role's budgets
. roles/ops-triage/role.env
harness=${HARNESS:-$AGENT_HARNESS}
[ -f "adapters/$harness/run.sh" ] || nogo "adapters/$harness/run.sh not found for the ops-triage role"

out="$TRIAGE_OUT/$(basename "$ALERT" .json)"
rm -rf "$out"
mkdir -p "$out/out"
ROLE=ops-triage INPUT="$ALERT" OUT="$out/out" \
  THINKING="${THINKING:-low}" TIMEOUT_S="${TIMEOUT_S:-900}" \
  sh "adapters/$harness/run.sh" >&2 || nogo "the ops-triage role did not finish ($harness)"

reason=$(python3 core/triage.py check "$ALERT" "$out/out" "$out/incident.json") || nogo "$reason"
go
