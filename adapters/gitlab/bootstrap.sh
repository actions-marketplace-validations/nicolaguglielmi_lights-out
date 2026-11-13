#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# bootstrap-gitlab: creates the public project root/workload and force-pushes
# the workload repository's HEAD to its main (docs/adr/0043 §3: afterwards the
# default branch is at the workload's HEAD). CODE_HOST_KEEP_MAIN leaves main
# as it is, as adapters/gitea/bootstrap.sh does. GitLab protects a project's
# default branch against force pushes; the protection is removed before and
# after the push, since a mirror of the local clone is all main is here.
# Idempotent. Adapter convention (docs/adr/0012 §6): silent on success, one
# stderr line and exit 1 on failure.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/gitlab/env.sh
. "$here/env.sh"
die() { printf 'bootstrap-gitlab: %s\n' "$*" >&2; exit 1; }

# 1. The project, public. 201 created, 400 "has already been taken".
tmp=$(mktemp)
code=$(api -o "$tmp" -w '%{http_code}' -X POST "$GITLAB_API/projects" \
  -d "name=$GITLAB_REPO" -d "path=$GITLAB_REPO" -d visibility=public -d initialize_with_readme=false) || code=000
body=$(cat "$tmp"); rm -f "$tmp"
case "$code:$body" in
  201:* | 400:*"has already been taken"*) ;;
  *) die "create project returned $code: $body" ;;
esac

unprotect() { api -o /dev/null -X DELETE "$GITLAB_PROJECT/protected_branches/main" || :; }

# 2. main, a mirror of the workload repository's HEAD.
if [ -z "${CODE_HOST_KEEP_MAIN:-}" ]; then
  unprotect
  git -C "${WORKLOAD:-.}" push --force "$GITLAB_PUSH_URL" HEAD:refs/heads/main >&2 || die "push to main failed"
  unprotect
fi

# 3. GitLab takes the push in the background: wait until the project has a
# repository and main is where the push left it.
want=$(git -C "${WORKLOAD:-.}" rev-parse HEAD)
: "${READY_TIMEOUT:=60}"
i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  got=$(api -f "$GITLAB_PROJECT/repository/branches/main" 2>/dev/null | jq -r '.commit.id // empty' 2>/dev/null) || got=""
  if [ -n "$got" ] && { [ -n "${CODE_HOST_KEEP_MAIN:-}" ] || [ "$got" = "$want" ]; }; then
    exit 0
  fi
  i=$((i + 1)); sleep 1
done
die "main is at [${got:-nothing}] ${READY_TIMEOUT}s after the push, want $want"
