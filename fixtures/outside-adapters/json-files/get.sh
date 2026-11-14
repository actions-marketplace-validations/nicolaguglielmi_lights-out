#!/bin/sh
# json-files: a StateStore adapter kept outside lights-out (docs/adr/0058
# §5), the test subject of ci/outside.sh, which copies it out of the
# checkout first. One JSON file per document under JSON_FILES_DIR.
# get <collection> <id>: the document on stdout, or exit 1 and nothing.
set -eu
f="${JSON_FILES_DIR:-.crew/json-files}/$1/$2.json"
[ -f "$f" ] || exit 1
cat "$f"
