#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# clone-url-gitea: prints the anonymous clone URL of the bootstrapped L0
# repo (docs/adr/0017 §4: the worker clones with no credential). Not a gate.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/gitea/env.sh
. "$here/adapters/gitea/env.sh"
printf '%s\n' "$GITEA_CLONE_URL"
