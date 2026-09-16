#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# get-firestore-emulator: prints the document <collection>/<id> as plain
# JSON on stdout (docs/adr/0019 §2). Exit 1, silent, when the document
# does not exist; one stderr line and exit 2 on any other failure, so a
# caller can tell "absent" from "the store is down". Not a gate.
set -eu
collection=${1:?usage: get.sh <collection> <id>}
id=${2:?usage: get.sh <collection> <id>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/firestore-emulator/lib.sh
. "$here/lib.sh"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
code=$(curl -sS --connect-timeout 2 --max-time 10 -o "$tmp" -w '%{http_code}' \
  "$FIRESTORE_URL/$collection/$id") || code=000
case "$code" in
  200) jq "$FS_DECODE" "$tmp" ;;
  404) exit 1 ;;
  *) printf 'get-firestore-emulator: GET %s/%s returned %s\n' "$collection" "$id" "$code" >&2; exit 2 ;;
esac
