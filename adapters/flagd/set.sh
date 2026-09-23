#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# set-flagd: sets <flag>'s default variant, clearing any targeting rule so
# the new default is unconditional for every context (docs/adr/0026 §3 —
# generalises the inline jq that kill-switch, freeze and unfreeze used
# before M8). Writes FLAGS_FILE in place: jq's output captured
# in a shell variable, then `>` truncates and rewrites the same path,
# never a temp-file-plus-rename. Reproduced live 2026-09-14 on flagd
# v0.16.3: a workbench container and the flagd container each bind-mount
# the flags directory separately (docs/adr/0012 §2); a `mv`/`rename(2)` onto the
# watched path gives it a new inode, and flagd's fileinfo poller, seen
# from the *other* container's mount of the same host directory,
# intermittently keeps serving the pre-rename evaluation with no error.
# An in-place truncate+write (same inode throughout) reproduced correctly
# every time; that is the only reason this does not use the usual
# write-temp-then-rename pattern. Even same-inode, flagd's own poll
# interval means a write is not visible instantly: this waits for
# evaluate.sh to agree before returning, the same confirmation kill-switch
# already polled for inline before M8, now inside the port for every
# caller. Not a gate (docs/adr/0012 §6): silent on success, one stderr
# line and exit 1 on failure or on timeout waiting for the write to show.
#
# FLAGS_FILE has no hardcoded default (docs/adr/0030 §5): this adapter must
# not name a workload, and the Makefile always exports FLAGS_FILE (derived
# from $WORKLOAD) before this script can run.
set -eu
flag=${1:?usage: set.sh <flag> <variant>}
variant=${2:?usage: set.sh <flag> <variant>}
: "${FLAGS_FILE:?FLAGS_FILE not set; run this via ./go, not directly}"
: "${READY_TIMEOUT:=60}"
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

jq -e --arg f "$flag" '.flags | has($f)' "$FLAGS_FILE" >/dev/null \
  || { printf 'set-flagd: no such flag %s in %s\n' "$flag" "$FLAGS_FILE" >&2; exit 1; }

content=$(jq --arg f "$flag" --arg v "$variant" \
  'del(.flags[$f].targeting) | .flags[$f].defaultVariant = $v' "$FLAGS_FILE")
expect=$(printf '%s' "$content" | jq -r --arg f "$flag" --arg v "$variant" '.flags[$f].variants[$v]')
printf '%s\n' "$content" > "$FLAGS_FILE"

i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  got=$(sh "$here/evaluate.sh" "$flag" 2>/dev/null) || got=""
  [ "$got" = "$expect" ] && exit 0
  i=$((i + 1))
  sleep 1
done
printf 'set-flagd: %s still evaluates %s after %ss, want %s\n' "$flag" "${got:-no answer}" "$READY_TIMEOUT" "$expect" >&2
exit 1
