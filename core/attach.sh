#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-attach (docs/adr/0037 §1): clones a repository of the user's into
# <dest>, the directory the Makefile then selects as the workload. Runs on
# the host under `./go attach`, with git and sh only, and inside workbench
# under demo-seam. The source is only read: every worktree and fetch the
# platform makes happens in the clone. Refuses a repository without
# .lights-out/workload.env committed at HEAD: the contract is read from
# there and nowhere else. Not a gate: one stderr line and exit 1 on
# failure, one stderr line on success.
set -eu
src=${1:?usage: attach.sh <repository> <dest>}
dest=${2:?usage: attach.sh <repository> <dest>}

top=$(git -C "$src" rev-parse --show-toplevel 2>/dev/null) \
  || { printf 'attach: %s is not a git repository\n' "$src" >&2; exit 1; }
git -C "$top" cat-file -e HEAD:.lights-out/workload.env 2>/dev/null \
  || { printf 'attach: %s has no .lights-out/workload.env committed at HEAD; docs/use-on-your-repo.md says what .lights-out/ holds\n' "$top" >&2; exit 1; }
# Only a clone of ours is ever replaced.
if [ -e "$dest" ] && [ ! -d "$dest/.git" ]; then
  printf 'attach: %s exists and is not a clone lights-out made; not touching it\n' "$dest" >&2
  exit 1
fi
[ -z "$(git -C "$top" status --porcelain)" ] \
  || printf 'attach: %s has uncommitted changes; lights-out attaches its HEAD, not them\n' "$top" >&2

rm -rf "$dest"
git clone -q "$top" "$dest" \
  || { printf 'attach: git clone %s %s failed\n' "$top" "$dest" >&2; exit 1; }
printf 'attach: %s at %s is the workload (clone: %s)\n' "$top" "$(git -C "$dest" rev-parse --short HEAD)" "$dest" >&2
