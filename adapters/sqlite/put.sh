#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# put-sqlite: writes the JSON object on stdin as the whole document
# <collection>/<id>, creating or replacing it (docs/adr/0019 §2). Silent
# on success; one stderr line and exit 1 when stdin is not a JSON object or
# the file cannot be written, the stored document untouched.
# The logic is store.py's (docs/adr/0060 §1); this file is the port's verb
# (docs/adr/0024, docs/adr/0052 §1). Not a gate.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 -I "$here/store.py" put "$@"
