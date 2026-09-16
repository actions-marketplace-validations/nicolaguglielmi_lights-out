#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# delete-firestore-emulator: removes <collection>/<id>; deleting a document
# that does not exist is success (docs/adr/0019 §7: e2e replays from a
# clean document). Not a gate: silent on success, one stderr line and
# exit 1 when the store did not answer 200.
set -eu
collection=${1:?usage: delete.sh <collection> <id>}
id=${2:?usage: delete.sh <collection> <id>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/firestore-emulator/lib.sh
. "$here/lib.sh"

code=$(curl -sS --connect-timeout 2 --max-time 10 -o /dev/null -w '%{http_code}' \
  -X DELETE "$FIRESTORE_URL/$collection/$id") || code=000
[ "$code" = 200 ] || { printf 'delete-firestore-emulator: DELETE %s/%s returned %s\n' "$collection" "$id" "$code" >&2; exit 1; }
