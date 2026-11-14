#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# status-gitlab: posts a commit status on <sha> (docs/adr/0019 §4). <state>
# is pending, success, failure or error; GitLab has one failed state, so
# both of the last two post as failed (docs/adr/0058 §8). <context> is the
# status's name. The description is cut to 255 characters, the longest
# GitLab stores (its commit status description column). Not a gate: silent
# on success, one stderr line and exit 1 on failure.
set -eu
sha=${1:?usage: status.sh <sha> <state> <context> <description>}
state=${2:?usage: status.sh <sha> <state> <context> <description>}
context=${3:?usage: status.sh <sha> <state> <context> <description>}
description=${4:?usage: status.sh <sha> <state> <context> <description>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/gitlab/env.sh
. "$here/env.sh"
case "$state" in
  pending | success) ;;
  failure | error) state=failed ;;
  *) printf 'status-gitlab: state %s is not pending, success, failure or error\n' "$state" >&2; exit 1 ;;
esac
payload=$(jq -cn --arg s "$state" --arg c "$context" --arg d "$description" \
  '{state: $s, name: $c, description: ($d | .[0:255])}')
tmp=$(mktemp)
code=$(api -o "$tmp" -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d "$payload" \
  "$GITLAB_PROJECT/statuses/$sha") || code=000
body=$(cat "$tmp"); rm -f "$tmp"
case "$code" in
  2??) ;;
  *) printf 'status-gitlab: POST status %s on %s returned %s: %s\n' "$state" "$sha" "$code" "$body" >&2; exit 1 ;;
esac
