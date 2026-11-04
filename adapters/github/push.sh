#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# push-github: force-pushes <workspace>'s HEAD to <branch> on GITHUB_REPO,
# authenticated through the credential helper (adapters/github/
# credential.sh) given as per-command config, the URL anonymous: the token
# is never in an argv or a .git/config (docs/adr/0017 §4, 0043 §2). Only
# the driver calls this, from workbench, after the harness has run. Refuses
# the repository's default branch: a ticket's work goes to ticket/<id>,
# the user's main moves only by a merge the gates allowed. Not a gate.
set -eu
workspace=${1:?usage: push.sh <workspace> <branch>}
branch=${2:?usage: push.sh <workspace> <branch>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/github/env.sh
. "$here/adapters/github/env.sh"

case "$branch" in
  ticket/*) : ;;
  *) printf 'push-github: refusing to push %s: lights-out pushes only ticket/<id> branches to your repository\n' "$branch" >&2; exit 1 ;;
esac
github_git -C "$workspace" push --force "$GITHUB_CLONE_URL" "HEAD:refs/heads/$branch" >&2
