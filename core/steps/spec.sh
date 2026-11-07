#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-spec (docs/adr/0055 §4): the request with the confirmed criteria is
# the spec, written to .crew/<ticket>/spec.md and judged by gates/spec.sh.
# GO opens the ticket; NO-GO sends it back to `questions` with the gate's
# reason as the question.
set -eu
: "${TICKET:?TICKET not set}"
: "${DOC_FILE:?DOC_FILE not set}"

spec=".crew/$TICKET/spec.md"
mkdir -p ".crew/$TICKET"
python3 core/spec.py compose "${TICKETS_DIR:-tickets}/$TICKET.md" "$DOC_FILE" > "$spec"
line=$(sh gates/spec.sh "$spec") || :
printf '%s\n' "$line" >&2
python3 core/spec.py gated "$DOC_FILE" "$line"
