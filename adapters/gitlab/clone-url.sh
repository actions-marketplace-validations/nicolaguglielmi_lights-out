#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# clone-url-gitlab: the anonymous clone URL of the workload's project
# (docs/adr/0017 §4: the worker clones with no credential). Not a gate.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/gitlab/env.sh
. "$here/env.sh"
printf '%s\n' "$GITLAB_CLONE_URL"
