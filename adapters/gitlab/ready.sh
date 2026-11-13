#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ready-gitlab: polls the API with the seeded token, not a gate (docs/adr/
# 0012 §6): silent on success, one stderr line and exit 1 on timeout. The
# API answers before the token exists only with 401, which is not ready.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/gitlab/env.sh
. "$here/env.sh"
: "${READY_TIMEOUT:=60}"
i=0
while :; do
  if curl -fsS --connect-timeout 1 --max-time 5 -H "PRIVATE-TOKEN: $GITLAB_TOKEN" "$GITLAB_API/version" >/dev/null 2>&1; then
    exit 0
  fi
  i=$((i + 1))
  [ "$i" -lt "$READY_TIMEOUT" ] || break
  sleep 1
done
printf 'ready: gitlab not ready after %ss: GET %s/version\n' "$READY_TIMEOUT" "$GITLAB_API" >&2
exit 1
