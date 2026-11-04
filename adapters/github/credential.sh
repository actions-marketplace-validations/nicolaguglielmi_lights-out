#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# credential-github: a git credential helper (gitcredentials(7)). On `get`
# for https://github.com it answers with GITHUB_TOKEN from the
# environment, so the token is never in a URL, an argv or a .git/config
# (docs/adr/0043 §2); for any other host, and on `store` or `erase`, it
# prints nothing. The Makefile hands it to git as environment-scoped config
# (GIT_CONFIG_KEY_1), never with `git config`.
[ "${1:-}" = get ] || exit 0
protocol="" host=""
while IFS= read -r line; do
  [ -n "$line" ] || break
  case "$line" in
    protocol=*) protocol=${line#protocol=} ;;
    host=*) host=${line#host=} ;;
  esac
done
[ "$protocol" = https ] && [ "$host" = github.com ] || exit 0
[ -n "${GITHUB_TOKEN:-}" ] || exit 0
printf 'username=x-access-token\npassword=%s\n' "$GITHUB_TOKEN"
