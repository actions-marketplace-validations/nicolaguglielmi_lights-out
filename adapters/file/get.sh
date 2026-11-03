#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# get-file: prints tickets/<id>.md, the Tracker=file port (docs/adr/0017
# §4). `core/` never spells `tickets/` directly — this two-line script is
# the boundary a `github-issues` or `linear` Tracker adapter would replace.
# Not a gate.
set -eu
id=${1:?usage: get.sh <ticket-id>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# TICKETS_DIR (docs/adr/0036 §2): the Makefile's, relative to the
# checkout; tickets/ when nothing sets it.
dir=${TICKETS_DIR:-tickets}
case "$dir" in
  /*) file="$dir/$id.md" ;;
  *) file="$here/$dir/$id.md" ;;
esac
[ -f "$file" ] || { printf 'get-file: no such ticket: %s/%s.md\n' "$dir" "$id" >&2; exit 1; }
cat "$file"
