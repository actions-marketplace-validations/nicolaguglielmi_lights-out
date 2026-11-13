#!/bin/sh
# delete <collection> <id>: gone; an absent document is not an error.
set -eu
rm -f "${JSON_FILES_DIR:-.crew/json-files}/$1/$2.json"
