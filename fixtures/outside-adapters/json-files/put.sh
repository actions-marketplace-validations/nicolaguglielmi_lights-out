#!/bin/sh
# put <collection> <id>: the JSON object on stdin replaces the document;
# anything else is refused and the stored document stays as it was.
set -eu
d="${JSON_FILES_DIR:-.crew/json-files}/$1"
mkdir -p "$d"
tmp=$(mktemp "$d/.put.XXXXXX")
cat > "$tmp"
if ! jq -e 'type == "object"' "$tmp" >/dev/null 2>&1; then
  rm -f "$tmp"
  printf 'json-files: put %s %s: not one JSON object\n' "$1" "$2" >&2
  exit 1
fi
mv "$tmp" "$d/$2.json"
