#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# await-gitlab: polls the statuses on <sha> named <context> until the newest
# leaves pending or running, and prints success or failure (docs/adr/0025 §5;
# GitLab's failed and canceled are both failure, docs/adr/0058 §8). Not a
# gate: one stderr line and exit 1 on timeout.
set -eu
sha=${1:?usage: await.sh <sha> <context>}
context=${2:?usage: await.sh <sha> <context>}
: "${AWAIT_TIMEOUT:=300}"
: "${AWAIT_INTERVAL:=1}"
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/gitlab/env.sh
. "$here/env.sh"
start=""
state=""
while :; do
  state=$(api -f -G "$GITLAB_PROJECT/repository/commits/$sha/statuses" --data-urlencode all=true --data-urlencode per_page=100 2>/dev/null \
    | jq -r --arg c "$context" '[.[] | select(.name == $c)] | max_by(.id) | .status // empty' 2>/dev/null) || state=""
  case "$state" in
    success) printf 'success\n'; exit 0 ;;
    failed | canceled) printf 'failure\n'; exit 0 ;;
  esac
  now=$(date +%s)
  [ -n "$start" ] || start=$now
  [ $((now - start)) -lt "$AWAIT_TIMEOUT" ] || break
  sleep "$AWAIT_INTERVAL"
done
printf 'await-gitlab: %s on %s still %s after %ss\n' "$context" "$sha" "${state:-pending}" "$AWAIT_TIMEOUT" >&2
exit 1
