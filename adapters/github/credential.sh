#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# credential-github: a git credential helper (gitcredentials(7)) that
# answers `get` with GITHUB_TOKEN from the environment, so the token is
# never in a URL, an argv or a .git/config (docs/adr/0043 §2). `store` and
# `erase` are ignored: nothing is written anywhere. Given to git only as
# per-command or environment-scoped config, never with `git config`.
[ "${1:-}" = get ] || exit 0
[ -n "${GITHUB_TOKEN:-}" ] || exit 0
printf 'username=x-access-token\npassword=%s\n' "$GITHUB_TOKEN"
