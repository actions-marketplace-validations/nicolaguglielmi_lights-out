#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# get-file: prints tickets/<id>.md, the Tracker=file port (docs/adr/0017
# §4). `core/` never spells `tickets/` directly — this two-line script is
# the boundary a `github-issues` or `linear` Tracker adapter would replace.
# Not a gate.
set -eu
id=${1:?usage: get.sh <ticket-id>}
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
file="$here/tickets/$id.md"
[ -f "$file" ] || { printf 'get-file: no such ticket: tickets/%s.md\n' "$id" >&2; exit 1; }
cat "$file"
