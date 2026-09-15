#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# push-gitea: force-pushes <workspace>'s HEAD to <branch> on the
# bootstrapped L0 repo, authenticated, the URL passed as a command
# argument only — never written to a .git/config (docs/adr/0017 §4: the
# model never holds this credential; only the driver calls this, from
# workbench, after the harness has run). Not a gate.
set -eu
workspace=${1:?usage: push.sh <workspace> <branch>}
branch=${2:?usage: push.sh <workspace> <branch>}
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/gitea/env.sh
. "$here/adapters/gitea/env.sh"
git -C "$workspace" push --force "$GITEA_PUSH_URL" "HEAD:refs/heads/$branch" >&2
