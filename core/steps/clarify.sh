#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-clarify (docs/adr/0055 §2, §3), also step-answer: the product role
# reads the request, with every answer given so far as a later turn of the
# same conversation, and asks one question or confirms the criteria. Its
# harness is the role's (roles/product/role.env). core/spec.py turns the
# run into the step's result: `questions` or `spec-ready`; at L0, with no
# recording for this request, `spec-ready` with the request's own criteria
# and `product.consulted: false`, never an invented answer.
set -eu
: "${TICKET:?TICKET not set}"
: "${DOC_FILE:?DOC_FILE not set}"
: "${AGENT_HARNESS:?AGENT_HARNESS not set; run this via ./go, not directly}"

request="${TICKETS_DIR:-tickets}/$TICKET.md"
[ -f "$request" ] || { printf 'step-clarify: no request %s\n' "$request" >&2; exit 1; }
dir=".crew/$TICKET/product"
rm -rf "$dir"
mkdir -p "$dir/out"
python3 core/spec.py answers "$DOC_FILE" > "$dir/answers.json"

# shellcheck disable=SC1091 # the role's budgets and harness
. roles/product/role.env
rc=0
ROLE=product INPUT="$request" ANSWERS="$dir/answers.json" OUT="$dir/out" \
  THINKING="${THINKING:-medium}" TIMEOUT_S="${TIMEOUT_S:-900}" \
  sh "adapters/${HARNESS:-$AGENT_HARNESS}/run.sh" 2>"$dir/run.err" || rc=$?
cat "$dir/run.err" >&2
python3 core/spec.py clarify "$request" "$DOC_FILE" "$dir" "$rc"
