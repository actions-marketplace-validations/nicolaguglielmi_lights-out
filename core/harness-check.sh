#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-harness-check: the harness-independent invariant (docs/adr/0017 §1):
# exit 0 alone is not success. Runs after every adapters/$AGENT_HARNESS/
# run.sh, independent of which harness ran -- the documented failure mode
# where a headless coding-agent CLI exits 0 having produced nothing. Not a
# gate: no GO/NO-GO line, no ci/lib.sh; exit 1 with one stderr line on
# failure, silent exit 0 otherwise, a driver-internal check core/crew.sh
# calls, matching core/launchpad.sh's own helper style where it does not
# go through go/nogo. ci/harness.sh proves each failure mode plus the
# valid case on stub OUT/WORKSPACE directories.
#
#   sh core/harness-check.sh <OUT_DIR> <WORKSPACE_DIR> <BASE_SHA>
set -eu

out_dir=${1:?usage: sh core/harness-check.sh OUT_DIR WORKSPACE_DIR BASE_SHA}
workspace=${2:?usage: sh core/harness-check.sh OUT_DIR WORKSPACE_DIR BASE_SHA}
base_sha=${3:?usage: sh core/harness-check.sh OUT_DIR WORKSPACE_DIR BASE_SHA}

fail() {
  printf 'core-harness-check: %s\n' "$1" >&2
  exit 1
}

# 1. An empty or missing patch: the worker produced no change.
[ -s "$out_dir/patch" ] || fail "$out_dir/patch is missing or empty"

# 2. No commit over BASE in the workspace, regardless of what the patch
# file (possibly stale, possibly hand-edited) claims.
commits=$(git -C "$workspace" rev-list --count "$base_sha..HEAD" 2>/dev/null) \
  || fail "git -C $workspace rev-list --count $base_sha..HEAD failed"
[ "$commits" -gt 0 ] || fail "$workspace has no commits over $base_sha"

# 3. pr.json missing, not valid JSON, or an empty/null title.
[ -f "$out_dir/pr.json" ] || fail "$out_dir/pr.json is missing"
jq -e . "$out_dir/pr.json" >/dev/null 2>&1 || fail "$out_dir/pr.json is not valid JSON"
title=$(jq -r '.title // empty' "$out_dir/pr.json" 2>/dev/null) || fail "$out_dir/pr.json: could not read .title"
[ -n "$title" ] || fail "$out_dir/pr.json: .title is empty or null"

exit 0
