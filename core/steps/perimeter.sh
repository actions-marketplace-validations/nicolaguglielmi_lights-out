#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-perimeter (docs/adr/0090 §3): the architect role proposes each
# proposed ticket's `## Perimeter` from the project map of WORKLOAD_REPO
# at HEAD, built here; the map is read through the role's find_files tool
# (INTAKE_MAP), never sent in the message. core/intake.py checks each
# ticket with gates/spec.sh and writes the step's result, `proposed`; at
# L0 with no recording, the architect is not consulted and every
# perimeter is empty, for the person to write.
set -eu
: "${TICKET:?TICKET not set}"
: "${DOC_FILE:?DOC_FILE not set}"
: "${AGENT_HARNESS:?AGENT_HARNESS not set; run this via ./go, not directly}"

dir=".crew/$TICKET/intake/architect"
rm -rf "$dir"
mkdir -p "$dir/out"
python3 core/intake.py proposal "$DOC_FILE" > "$dir/input.json"
# The paths are what find_files reads; no ./go target is needed, so none
# is listed (an empty --targets file, never `make help` from here).
: > "$dir/targets"
python3 core/map.py build --repo "${WORKLOAD_REPO:-.}" --targets "$dir/targets" --out "$dir/map.sqlite" >&2 \
  || { printf 'could not build the project map of %s\n' "${WORKLOAD_REPO:-.}" > "${STEP_WHY:-/dev/null}"; exit 1; }

# shellcheck disable=SC1091 # the role's budgets
. roles/architect/role.env
rc=0
ROLE=architect INPUT="$dir/input.json" OUT="$dir/out" INTAKE_MAP="$dir/map.sqlite" \
  THINKING="${THINKING:-high}" TIMEOUT_S="${TIMEOUT_S:-900}" \
  sh adapters/adk/run.sh 2>"$dir/run.err" || rc=$?
cat "$dir/run.err" >&2
python3 core/intake.py perimeter "$DOC_FILE" "$dir" "$rc"
