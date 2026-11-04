#!/bin/sh
# shellcheck disable=SC2034 # every var here is for the sourcing script
# SPDX-License-Identifier: Apache-2.0
#
# github-env: the user's repository on GitHub as the code host (docs/adr/
# 0043). Sourced, not executed, by every verb in this directory, after the
# verb has set `here`. Reads GITHUB_TOKEN and GITHUB_REPO as make hands
# them down from .env (§2: never a host's or a runner's ambient token) and
# refuses, naming .env, with no network call, when either is unset. The
# token is never put in a URL, an argv or a .git/config: curl reads the
# Authorization header on stdin (github_api below, ADR 0044 §8's
# mechanism), git asks credential.sh, which the Makefile hands to git as
# environment-scoped config.
if [ -z "${GITHUB_TOKEN:-}" ] || [ "$GITHUB_TOKEN" = replace-me ]; then
  printf 'github: GITHUB_TOKEN is empty; put a token for your repository in .env (see .env.example, docs/adr/0043)\n' >&2
  exit 1
fi
case "${GITHUB_REPO:-}" in
  '') printf 'github: GITHUB_REPO is empty; put <owner>/<name> of your repository in .env (see .env.example, docs/adr/0043)\n' >&2; exit 1 ;;
  */*/* | /* | */) printf 'github: GITHUB_REPO=%s is not <owner>/<name>\n' "$GITHUB_REPO" >&2; exit 1 ;;
  */*) : ;;
  *) printf 'github: GITHUB_REPO=%s is not <owner>/<name>\n' "$GITHUB_REPO" >&2; exit 1 ;;
esac
GITHUB_API=https://api.github.com
# Anonymous clone URL: all a workspace's .git/config ever holds (docs/adr/
# 0017 §4). A private repository is reached through the credential helper.
GITHUB_CLONE_URL="https://github.com/$GITHUB_REPO.git"

# github_api METHOD PATH OUT [JSON]: one REST call, the response body in
# OUT, the HTTP status on stdout (000 when curl got no answer). The
# Authorization header is read from stdin (-H @-), never from argv.
github_api() {
  _method=$1 _path=$2 _out=$3 _json=${4:-}
  if [ -n "$_json" ]; then
    set -- -H 'Content-Type: application/json' --data-binary "$_json"
  else
    set --
  fi
  _code=$(printf 'Authorization: Bearer %s\n' "$GITHUB_TOKEN" \
    | curl -sS --connect-timeout 5 --max-time 30 -o "$_out" -w '%{http_code}' -H @- \
        -X "$_method" -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2022-11-28' \
        "$@" "$GITHUB_API$_path") || _code=000
  printf '%s' "${_code:-000}"
}
