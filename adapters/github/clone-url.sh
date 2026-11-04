#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# clone-url-github: prints the anonymous https clone URL of GITHUB_REPO
# (docs/adr/0017 §4: what a workspace's .git/config may hold; docs/adr/
# 0043 §2 for how a private repository is reached). Not a gate.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/github/env.sh
. "$here/adapters/github/env.sh"
printf '%s\n' "$GITHUB_CLONE_URL"
