#!/bin/sh
# shellcheck disable=SC2034 # every var here is for the sourcing script
# SPDX-License-Identifier: Apache-2.0
#
# github-env: the user's repository on GitHub as the code host (docs/adr/
# 0043). Sourced, not executed, by every verb in this directory. Reads
# GITHUB_TOKEN and GITHUB_REPO from the environment (.env, which the
# Makefile includes after the profile); refuses, naming .env, when either
# is unset or still the .env.example placeholder. The token is never put
# in a URL, an argv or a .git/config (docs/adr/0043 §2): curl reads the
# Authorization header from its config on stdin (github_api below), git
# from the credential helper next to this file.
: "${GITHUB_API:=https://api.github.com}"
: "${GITHUB_URL:=https://github.com}"
case "${GITHUB_TOKEN:-}" in
  '' | replace-me)
    printf 'github: GITHUB_TOKEN is not set; put a token for %s in .env (see .env.example, docs/adr/0043 §1)\n' "${GITHUB_REPO:-GITHUB_REPO}" >&2
    exit 1 ;;
esac
case "${GITHUB_REPO:-}" in
  '' | replace-me/replace-me)
    printf 'github: GITHUB_REPO is not set; put owner/name of your repository in .env (see .env.example, docs/adr/0043 §1)\n' >&2
    exit 1 ;;
  */*/* | /* | */) printf 'github: GITHUB_REPO=%s is not owner/name\n' "$GITHUB_REPO" >&2; exit 1 ;;
  */*) : ;;
  *) printf 'github: GITHUB_REPO=%s is not owner/name\n' "$GITHUB_REPO" >&2; exit 1 ;;
esac
GITHUB_REPO_API="$GITHUB_API/repos/$GITHUB_REPO"
# Anonymous clone URL: what a workspace's .git/config may hold (docs/adr/
# 0017 §4). A private repository is reached through the credential helper.
GITHUB_CLONE_URL="$GITHUB_URL/$GITHUB_REPO.git"

# github_api METHOD PATH OUT [JSON]: one REST call, the response body in
# OUT, the HTTP status on stdout (000 when curl got no answer). The token
# travels in curl's config, read from stdin (-K -), never in argv.
github_api() {
  set -- "$1" "$2" "$3" "${4:-}"
  if [ -n "$4" ]; then
    set -- "$1" "$2" "$3" -H 'Content-Type: application/json' --data-binary "$4"
  else
    set -- "$1" "$2" "$3"
  fi
  _method=$1 _path=$2 _out=$3
  shift 3
  _code=$(printf 'header = "Authorization: Bearer %s"\n' "$GITHUB_TOKEN" \
    | curl -sS -K - --connect-timeout 5 --max-time 30 -o "$_out" -w '%{http_code}' \
        -X "$_method" -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2022-11-28' \
        "$@" "$GITHUB_API$_path") || _code=000
  printf '%s' "${_code:-000}"
}

# github_git ARGS...: git with this directory's credential helper and no
# other (the empty value resets any inherited helper), for the pushes and
# fetches the driver makes (docs/adr/0043 §2).
github_git() {
  git -c credential.helper= -c "credential.helper=!sh '$here/adapters/github/credential.sh'" "$@"
}
