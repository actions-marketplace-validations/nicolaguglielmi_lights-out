#!/bin/sh
# Sourced by every gate: `. ci/lib.sh` after setting `name`.
# shellcheck disable=SC2154 # name is set by the sourcing gate
#
# Gate output contract (CLAUDE.md, "Contratto di output dei gate"):
#   - stdout carries exactly one line: "GO: <name>" or "NO-GO: <name> — <reason>"
#   - no colour when stdout is not a TTY: NO_COLOR is set here, and each tool
#     gets its own no-colour flag where it has one
#   - everything a tool prints goes to stderr; details for a NO-GO go to stderr
#   - GO exits 0, NO-GO exits 1
# ci/contract.sh verifies this on every gate.
NO_COLOR=1
export NO_COLOR

go() {
  printf 'GO: %s\n' "$name"
  exit 0
}

# nogo REASON [DETAILS...]: one contract line on stdout, details on stderr.
nogo() {
  reason=$1
  shift
  printf 'NO-GO: %s — %s\n' "$name" "$reason"
  for line in "$@"; do
    printf '%s\n' "$line" >&2
  done
  exit 1
}
