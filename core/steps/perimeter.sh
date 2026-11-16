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

# The workload's directory inside its repository (docs/adr/0090 second
# amendment A6): the architect searches only there, never lights-out's own
# tree. An attached repository is all workload: the prefix is empty.
scope=$(git -C "${WORKLOAD:-/nonexistent}" rev-parse --show-prefix 2>/dev/null) \
  || { printf 'WORKLOAD=%s is not a directory of a git repository: no workload to search\n' "${WORKLOAD:-}" > "${STEP_WHY:-/dev/null}"; exit 1; }
scope=${scope%/}

dir=".crew/$TICKET/intake/architect"
rm -rf "$dir"
mkdir -p "$dir/out"
python3 core/intake.py proposal "$DOC_FILE" > "$dir/input.json"
# The paths are what find_files reads; no ./go target is needed, so none
# is listed (an empty --targets file, never `make help` from here).
: > "$dir/targets"
python3 core/map.py build --repo "${WORKLOAD_REPO:-.}" --targets "$dir/targets" --out "$dir/map.sqlite" >&2 \
  || { printf 'could not build the project map of %s\n' "${WORKLOAD_REPO:-.}" > "${STEP_WHY:-/dev/null}"; exit 1; }

# PERIMETER_BY from the environment wins over the role's (docs/adr/0091 §6).
by=${PERIMETER_BY:-}
# shellcheck disable=SC1091 # the role's budgets
. roles/architect/role.env
PERIMETER_BY=${by:-${PERIMETER_BY:-search}}

# Asked file by file (docs/adr/0091 §6): one Decide request, no turns. Over
# the port's limit, or at L0 with no recording, the architect searches as
# before and says so; any other failure fails the step.
if [ "$PERIMETER_BY" = decide ]; then
  if python3 core/intake.py perimeter-request "$DOC_FILE" "$dir/map.sqlite" "$scope" > "$dir/request.json" 2>"$dir/decide.err"; then
    drc=0
    python3 core/decide.py ask < "$dir/request.json" > "$dir/answer.json" 2>"$dir/decide.err" || drc=$?
    if [ "$drc" -eq 0 ]; then
      exec python3 core/intake.py perimeter-decided "$DOC_FILE" "$dir/request.json" "$dir/answer.json"
    fi
    line=$(tail -n 1 "$dir/decide.err")
    if [ "$drc" -ne 3 ]; then
      printf 'perimeter: %s\n' "$line" >&2
      printf "the architect's decision failed: %s\n" "${line#decide: }" > "${STEP_WHY:-/dev/null}"
      exit 1
    fi
    printf 'perimeter: the decision is not recorded at L0 (%s); the architect searches instead\n' "${line#decide: }" >&2
  else
    printf 'perimeter: %s; the architect searches instead\n' "$(tail -n 1 "$dir/decide.err")" >&2
  fi
fi
rc=0
ROLE=architect INPUT="$dir/input.json" OUT="$dir/out" INTAKE_MAP="$dir/map.sqlite" INTAKE_SCOPE="$scope" \
  THINKING="${THINKING:-high}" TIMEOUT_S="${TIMEOUT_S:-900}" \
  sh adapters/adk/run.sh 2>"$dir/run.err" || rc=$?
cat "$dir/run.err" >&2
python3 core/intake.py perimeter "$DOC_FILE" "$dir" "$rc"
