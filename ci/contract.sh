#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-contract: meta-gate. Runs every other gate with stdout captured and
# stderr discarded, and fails unless each one honours the output contract in
# ci/lib.sh: exactly one stdout line, "GO: <name>" with exit 0 or
# "NO-GO: <name> — <reason>" with exit 1, no ANSI escape sequences. The gate's
# own verdict does not matter here, only its shape.
set -eu
name=contract
. ci/lib.sh

esc=$(printf '\033')
bad=""

for f in ci/*.sh; do
  case "$f" in ci/lib.sh|ci/contract.sh) continue ;; esac
  gate=$(basename "$f" .sh)

  # stdout only, exit code preserved; `|| true` keeps set -e out of the way.
  out=$(sh "$f" 2>/dev/null) && rc=0 || rc=$?

  lines=$(printf '%s' "$out" | awk 'END{print NR}')
  if [ "$lines" -ne 1 ]; then
    bad="$bad $gate(lines=$lines)"
    printf '%s: stdout has %s lines, want 1:\n%s\n' "$gate" "$lines" "$out" >&2
    continue
  fi

  case "$out" in
    *"$esc"*) bad="$bad $gate(ansi)"; printf '%s: ANSI escape in stdout\n' "$gate" >&2; continue ;;
  esac

  case "$out" in
    "GO: $gate")
      [ "$rc" -eq 0 ] || { bad="$bad $gate(GO,exit=$rc)"; printf '%s: GO with exit %s\n' "$gate" "$rc" >&2; } ;;
    "NO-GO: $gate — "?*)
      [ "$rc" -eq 1 ] || { bad="$bad $gate(NO-GO,exit=$rc)"; printf '%s: NO-GO with exit %s\n' "$gate" "$rc" >&2; } ;;
    *)
      bad="$bad $gate(format)"; printf '%s: malformed line: %s\n' "$gate" "$out" >&2 ;;
  esac
done

[ -z "$bad" ] || nogo "gate(s) violate the output contract:$bad"

go
