#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-spool: creates the spool file (SPOOL_FILE, default
# .crew/spool.sqlite) and its table (docs/adr/0012 §6: silent on success,
# one stderr line and exit 1 on failure).
# The logic is spool.py's (docs/adr/0060 §2); this file is the port's verb
# (docs/adr/0024, docs/adr/0052 §1).
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 -I "$here/spool.py" ready "$@"
