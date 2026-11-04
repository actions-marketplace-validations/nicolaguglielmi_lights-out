#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-github: `./go up` waits on every adapter the profile names (docs/
# adr/0012 §6); GitHub is not a plane service, so ready means the API
# answers for GITHUB_REPO with this token. Polls up to READY_TIMEOUT
# seconds, every 5: one stderr line and exit 1 if it never does.
set -eu
: "${READY_TIMEOUT:=60}"
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/github/env.sh
. "$here/adapters/github/env.sh"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
start=$(date +%s)
code=000
while [ $(( $(date +%s) - start )) -lt "$READY_TIMEOUT" ]; do
  code=$(github_api GET "/repos/$GITHUB_REPO" "$tmp")
  case "$code" in
    200) exit 0 ;;
    401 | 403 | 404) break ;;
  esac
  sleep 5
done
printf 'ready: github: GET %s/repos/%s returned %s\n' "$GITHUB_API" "$GITHUB_REPO" "$code" >&2
exit 1
