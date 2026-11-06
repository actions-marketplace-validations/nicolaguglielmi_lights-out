#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-audit: `./go audit TICKET=<id>` (docs/adr/0019 §6). core/audit.py
# rebuilds the chain deploy → merge → PR → ticket → spec from the ticket's
# document, checks it against the code host, and prints it on stderr
# (docs/adr/0052 §3); this prints the one line: GO: audit, or NO-GO: audit
# — <what is missing or disagrees>. Needs no engine socket.
#
# Not scanned by ci/contract.sh (core/, not ci/ gates/ verify/), but reuses
# ci/lib.sh's go/nogo for the same GO:/NO-GO: line shape.
set -eu
name=audit
. ci/lib.sh

reason=$(python3 core/audit.py) || nogo "${reason:-core/audit.py failed without a reason; see stderr}"
go
