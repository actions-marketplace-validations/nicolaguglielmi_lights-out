#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-dora: the four delivery measures over the last WINDOW_DAYS days
# (default 30), from the logbook (docs/adr/0082). Writes the logbook first,
# its line on stderr, unless DORA_LOGBOOK names one already written; then
# core/dora.py writes DORA_OUT (default .crew/dora.json) and one line per
# measure on stderr. Stdout is one line of the gate contract: `GO: dora —
# <file>, <n> of 4 measured over <w> days`, or `NO-GO: dora — <why>`. A
# measure the record cannot give is printed as not measured, with the
# reason, never estimated: that is a GO.
set -eu
name=dora
. ci/lib.sh

: "${DORA_OUT:=.crew/dora.json}"
: "${WINDOW_DAYS:=30}"
book=${DORA_LOGBOOK:-}
if [ -z "$book" ]; then
  sh core/logbook.sh >&2 || nogo "the logbook could not be written; see stderr"
  book=${LOGBOOK_FILE:-.crew/logbook.json}
fi
n=$(python3 core/dora.py --logbook "$book" --window-days "$WINDOW_DAYS" --out "$DORA_OUT") \
  || nogo "${n:-core/dora.py failed without a reason; see stderr}"
go_with "$DORA_OUT, $n of 4 measured over $WINDOW_DAYS days"
