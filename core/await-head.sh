#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-await-head: await-head.sh <repository> <seconds>. Exits 0 once git
# resolves HEAD in <repository>, 1 if it does not within <seconds>. The gates
# image runs it on /repo before calling the directory "not a git repository
# with a commit".
#
# Why it waits: on a podman machine (macOS, libkrun), a file git replaced on
# the host by a rename is missing in the bind mount for a few seconds:
# .git/HEAD after git switch, the branch's ref after a commit. Measured on
# 2026-11-20, podman 6.1.4: 4 to 5 s. The image's caller passes 15, three
# times that (a decision, not a measure).
#
# No wait where none can help: a directory with no .git directory, or one
# whose .git/objects holds no file (git init, no commit yet), is answered at
# once. Not a gate: one stderr line while it waits, nothing on stdout.
set -u
repo=${1:?usage: await-head.sh <repository> <seconds>}
secs=${2:?usage: await-head.sh <repository> <seconds>}

resolves() { git -C "$repo" rev-parse -q --verify HEAD >/dev/null 2>&1; }

resolves && exit 0
[ -d "$repo/.git/objects" ] || exit 1
[ -n "$(find "$repo/.git/objects" -type f 2>/dev/null | head -n 1)" ] || exit 1
printf '[lights-out] git does not resolve HEAD in the repository yet (a podman machine shows a file git just replaced a few seconds late); waiting up to %ss\n' "$secs" >&2
end=$(( $(date +%s) + secs ))
while [ "$(date +%s)" -lt "$end" ]; do
  sleep 1
  resolves && exit 0
done
exit 1
