#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# await-github: polls the commit statuses on <sha> for <context> until it
# leaves pending, and prints the state it left at: success, failure or
# error (docs/adr/0025 §5, 0043 §3). Commit statuses only, the protocol
# the tower itself writes (status.sh); GitHub returns them newest first,
# so the first entry for <context> is the current one. Polls every
# AWAIT_INTERVAL seconds, not every second as on Gitea: GitHub's API is
# rate-limited per token (docs/adr/0043 §3). The deadline is read after a
# poll, never before the first, so every run asks at least once (as
# ready.sh). Not a gate: one stderr line and exit 1 on timeout, naming the
# context and the state it was stuck at.
set -eu
sha=${1:?usage: await.sh <sha> <context>}
context=${2:?usage: await.sh <sha> <context>}
: "${AWAIT_TIMEOUT:=300}"
: "${AWAIT_INTERVAL:=5}"
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/github/env.sh
. "$here/adapters/github/env.sh"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
start=$(date +%s)
state=""
while :; do
  code=$(github_api GET "/repos/$GITHUB_REPO/commits/$sha/statuses?per_page=100" "$tmp")
  if [ "$code" = 200 ]; then
    state=$(jq -r --arg c "$context" '[.[] | select(.context == $c)] | .[0].state // empty' "$tmp")
    case "$state" in
      success | failure | error)
        printf '%s\n' "$state"
        exit 0
        ;;
    esac
  fi
  [ $(( $(date +%s) - start )) -lt "$AWAIT_TIMEOUT" ] || break
  sleep "$AWAIT_INTERVAL"
done
printf 'await-github: %s on %s still %s after %ss\n' "$context" "$sha" "${state:-pending}" "$AWAIT_TIMEOUT" >&2
exit 1
