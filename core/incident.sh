#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-incident: a release record, a time window and a log excerpt in, one
# incident document out (docs/adr/0044 §1, §2), for `./go postmortem` to
# hand the ops-triage role. core/incident.py builds and writes it (docs/
# adr/0052 §3); this prints the one line: GO: incident — <path>, or NO-GO:
# incident — <reason>. Only TICKET=<id> touches anything beyond files.
#
#   ./go incident NAME=<slug> FROM=<utc> TO=<utc> [LOGS=<file>] [TICKET=<id>]
set -eu
name=incident
. ci/lib.sh

out=$(python3 core/incident.py) || nogo "${out:-core/incident.py failed without a reason; see stderr}"
go_with "$out"
