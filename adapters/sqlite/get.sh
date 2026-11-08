#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# get-sqlite: prints the document <collection>/<id> as plain JSON on stdout
# (docs/adr/0019 §2). Exit 1, silent, when it does not exist; one stderr
# line and exit 2 on any other failure.
# The logic is store.py's (docs/adr/0060 §1); this file is the port's verb
# (docs/adr/0024, docs/adr/0052 §1). Not a gate.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 -I "$here/store.py" get "$@"
