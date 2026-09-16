#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# put-firestore-emulator: writes the plain JSON object on stdin as the
# whole document <collection>/<id>, creating or replacing it (docs/adr/
# 0019 §2: no update mask, the tower rewrites the whole document). Not a
# gate: silent on success, one stderr line and exit 1 on failure.
set -eu
collection=${1:?usage: put.sh <collection> <id> < document.json}
id=${2:?usage: put.sh <collection> <id> < document.json}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/firestore-emulator/lib.sh
. "$here/lib.sh"

body=$(jq -c "$FS_ENCODE") || { printf 'put-firestore-emulator: stdin is not a JSON object\n' >&2; exit 1; }
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
code=$(curl -sS --connect-timeout 2 --max-time 10 -o "$tmp" -w '%{http_code}' \
  -X PATCH -H 'Content-Type: application/json' -d "$body" \
  "$FIRESTORE_URL/$collection/$id") || code=000
[ "$code" = 200 ] || {
  printf 'put-firestore-emulator: PATCH %s/%s returned %s: %s\n' "$collection" "$id" "$code" "$(cat "$tmp")" >&2
  exit 1
}
