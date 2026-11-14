#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-scoreboard: `./go scoreboard` (docs/adr/0088). core/scoreboard.py
# reads the curated dataset SCOREBOARD_DATA (default docs/scoreboard/
# m24-tenacity.json, every row naming its handoff and run) and the run
# logbooks in SCOREBOARD_LOGBOOKS (none by default), groups the rows per
# provider, harness and model, prints one line per group on stderr and
# writes the page to SCOREBOARD_OUT (default .crew/scoreboard/index.html).
# Stdout is one line: GO: scoreboard — <g> groups run, <n> not run, <t>
# tickets; <page>, or NO-GO: scoreboard — <why>.
set -eu
name=scoreboard
. ci/lib.sh

: "${SCOREBOARD_DATA:=docs/scoreboard/m24-tenacity.json}"
: "${SCOREBOARD_OUT:=.crew/scoreboard/index.html}"
set -- --data "$SCOREBOARD_DATA" --html "$SCOREBOARD_OUT"
for book in ${SCOREBOARD_LOGBOOKS:-}; do set -- "$@" --logbook "$book"; done
out=$(python3 core/scoreboard.py "$@") || nogo "${out:-core/scoreboard.py failed without a reason; see stderr}"
groups=$(printf '%s' "$out" | cut -f1)
missing=$(printf '%s' "$out" | cut -f2)
tickets=$(printf '%s' "$out" | cut -f3)
go_with "$groups groups run, $missing not run, $tickets tickets; $SCOREBOARD_OUT"
