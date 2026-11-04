#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# bootstrap-github: on GitHub the repository is the user's own, so
# bootstrap creates and pushes nothing (docs/adr/0043 §3). It checks what
# the run needs and refuses, naming the fix: the workload is an attached
# repository (the bundled app's release waits on the Gitea `image` job,
# docs/adr/0039); the token reaches GITHUB_REPO with push permission; and
# the attached clone's HEAD is the default branch's head on GitHub — the
# stable image `./go up` published is built from that HEAD, and the PR is
# based on the default branch, so the two must be one commit. Idempotent.
# Adapter convention (docs/adr/0012 §6): not a gate, silent on success,
# one stderr line and exit 1 on failure.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/github/env.sh
. "$here/adapters/github/env.sh"

[ -n "${WORKLOAD_ATTACHED:-}" ] \
  || { printf 'bootstrap-github: CODE_HOST=github serves an attached repository (./go attach <path>); the bundled app runs on Gitea (docs/adr/0043 §3)\n' >&2; exit 1; }

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
code=$(github_api GET "/repos/$GITHUB_REPO" "$tmp")
case "$code" in
  200) : ;;
  401) printf 'bootstrap-github: GitHub refused GITHUB_TOKEN (401); check the token in .env\n' >&2; exit 1 ;;
  404) printf 'bootstrap-github: %s not found with this token (404): check GITHUB_REPO, and that the token is granted this repository\n' "$GITHUB_REPO" >&2; exit 1 ;;
  *) printf 'bootstrap-github: GET %s returned %s\n' "$GITHUB_REPO" "$code" >&2; exit 1 ;;
esac
[ "$(jq -r '.permissions.push // false' "$tmp")" = true ] \
  || { printf 'bootstrap-github: the token cannot push to %s; it needs Contents, Pull requests and Commit statuses read and write (docs/adr/0043 §1)\n' "$GITHUB_REPO" >&2; exit 1; }
base=$(jq -r '.default_branch // empty' "$tmp")
[ -n "$base" ] || { printf 'bootstrap-github: %s reports no default branch\n' "$GITHUB_REPO" >&2; exit 1; }

code=$(github_api GET "/repos/$GITHUB_REPO/branches/$base" "$tmp")
[ "$code" = 200 ] || { printf 'bootstrap-github: GET branch %s of %s returned %s\n' "$base" "$GITHUB_REPO" "$code" >&2; exit 1; }
remote=$(jq -r '.commit.sha // empty' "$tmp")
local=$(git -C "${WORKLOAD:?WORKLOAD not set; run this via ./go}" rev-parse HEAD)
[ "$remote" = "$local" ] \
  || { printf 'bootstrap-github: %s on %s is %s, the attached clone is at %s; push or pull your repository so the two agree, then ./go attach it again\n' "$base" "$GITHUB_REPO" "$remote" "$local" >&2; exit 1; }
