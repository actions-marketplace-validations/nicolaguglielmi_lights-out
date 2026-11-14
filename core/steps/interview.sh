#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-interview (docs/adr/0090 §2, §4), also step-intake-answer: the
# product role reads the client's words with its agenda, every answer so
# far as a later turn of the same conversation, and asks one question or
# proposes the tickets. Its harness is the role's (roles/product/role.env).
# core/intake.py turns the run into the step's result: `intake-questions`
# or `drafted`; at L0, with no recording of this interview, a refusal that
# names how to record it, never an invented proposal.
set -eu
: "${TICKET:?TICKET not set}"
: "${DOC_FILE:?DOC_FILE not set}"
: "${AGENT_HARNESS:?AGENT_HARNESS not set; run this via ./go, not directly}"

dir=".crew/$TICKET/intake/product"
rm -rf "$dir"
mkdir -p "$dir/out"
python3 core/intake.py first "$DOC_FILE" "${TICKETS_DIR:-tickets}" > "$dir/input.md"
python3 core/intake.py answers "$DOC_FILE" > "$dir/answers.json"

# shellcheck disable=SC1091 # the role's budgets and harness
. roles/product/role.env
rc=0
ROLE=product INPUT="$dir/input.md" ANSWERS="$dir/answers.json" OUT="$dir/out" \
  THINKING="${THINKING:-medium}" TIMEOUT_S="${TIMEOUT_S:-900}" \
  sh "adapters/${HARNESS:-$AGENT_HARNESS}/run.sh" 2>"$dir/run.err" || rc=$?
cat "$dir/run.err" >&2
python3 core/intake.py interview "$DOC_FILE" "$dir" "$rc"
