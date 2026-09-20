#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# await-gitea: polls the commit statuses on <sha> for <context> until it
# leaves pending, and prints the state it left at — success, failure or
# error (docs/adr/0025 §5). Statuses append, never replace
# (adapters/gitea/status.sh's own header), so this reads the newest entry
# for <context>, which Gitea's API returns first. Not a gate (docs/adr/
# 0012 §6): one stderr line and exit 1 on timeout, naming the context and
# the state it was stuck at.
set -eu
sha=${1:?usage: await.sh <sha> <context>}
context=${2:?usage: await.sh <sha> <context>}
: "${AWAIT_TIMEOUT:=300}"
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/gitea/env.sh
. "$here/adapters/gitea/env.sh"

i=0
state=""
while [ "$i" -lt "$AWAIT_TIMEOUT" ]; do
  state=$(curl -fsS -u "$GITEA_USER:$GITEA_PASSWORD" \
      "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO/commits/$sha/statuses" 2>/dev/null \
    | jq -r --arg c "$context" '[.[] | select(.context == $c)] | .[0].state // empty')
  case "$state" in
    success | failure | error)
      printf '%s\n' "$state"
      exit 0
      ;;
  esac
  i=$((i + 1))
  sleep 1
done
printf 'await-gitea: %s on %s still %s after %ss\n' "$context" "$sha" "${state:-pending}" "$AWAIT_TIMEOUT" >&2
exit 1
