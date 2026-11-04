#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# put-file: files a ticket, the Tracker=file port's second verb
# (docs/adr/0044 §6). `put.sh <title> <origin>` with the body on stdin
# writes TICKETS_DIR/<id>.md and prints the id alone. The id is the
# highest numeric basename plus one, four digits. A ticket that already
# carries the line `- Origin: <origin>` is reused: its id is printed and
# nothing is written, so a re-run files nothing twice. Once filed, a
# ticket belongs to the Tracker and is never rewritten. Not a gate:
# silent but for the id, one stderr line and exit 1 on failure.
set -eu
title=${1:?usage: put.sh <title> <origin> < body}
origin=${2:?usage: put.sh <title> <origin> < body}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
dir=${TICKETS_DIR:-tickets}
case "$dir" in
  /*) ;;
  *) dir="$here/$dir" ;;
esac
mkdir -p "$dir"

for f in "$dir"/*.md; do
  [ -f "$f" ] || continue
  if grep -qxF -- "- Origin: $origin" "$f"; then
    basename "$f" .md
    exit 0
  fi
done

max=0
for f in "$dir"/*.md; do
  [ -f "$f" ] || continue
  n=$(basename "$f" .md)
  case "$n" in *[!0-9]* | '') continue ;; esac
  n=$(printf '%s' "$n" | sed 's/^0*//')
  [ "${n:-0}" -le "$max" ] || max=$n
done
id=$(printf '%04d' $((max + 1)))

tmp=$(mktemp "$dir/.put.XXXXXX")
trap 'rm -f "$tmp"' EXIT
{
  printf '# %s — %s\n\n- Status: open\n- Origin: %s\n\n' "$id" "$title" "$origin"
  cat
} > "$tmp" || { printf 'put-file: could not write %s\n' "$tmp" >&2; exit 1; }
mv "$tmp" "$dir/$id.md" || { printf 'put-file: could not write %s/%s.md\n' "$dir" "$id" >&2; exit 1; }
trap - EXIT
printf '%s\n' "$id"
