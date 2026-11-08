#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-sqlite: creates the store file (STATE_FILE, default
# .crew/state.sqlite) and its table (docs/adr/0012 §6: not a gate, silent on
# success, one stderr line and exit 1 on failure).
# The logic is store.py's (docs/adr/0060 §1); this file is the port's verb
# (docs/adr/0024, docs/adr/0052 §1).
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 -I "$here/store.py" ready "$@"
