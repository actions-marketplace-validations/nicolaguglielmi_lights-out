#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-contract: meta-gate. Runs every other gate with stdout captured and
# stderr discarded, and fails unless each one honours the output contract in
# ci/lib.sh: exactly one stdout line, "GO: <name>" (optionally followed by
# " — <detail>", docs/adr/0042 §3) with exit 0 or "NO-GO: <name> — <reason>"
# with exit 1, no ANSI escape sequences. The gate's
# own verdict does not matter here, only its shape. Scans ci/, gates/ and
# verify/ (docs/adr/0011 §4), skipping directories that do not exist yet;
# gate basenames must be unique across the three. It also checks the lib's
# own side of the contract (docs/adr/0038 §5): `nogo` may leave its details
# in the file $NOGO_DETAILS names, and stdout stays the one line.
set -eu
name=contract
. ci/lib.sh

esc=$(printf '\033')
bad=""
stdout_file=$(mktemp)
probe=$(mktemp -d)
trap 'rm -rf "$stdout_file" "$probe"' EXIT

files=""
seen=""
dupes=""
for dir in ci gates verify; do
  [ -d "$dir" ] || continue
  for f in "$dir"/*.sh; do
    [ -e "$f" ] || continue
    case "$f" in ci/lib.sh|ci/contract.sh) continue ;; esac
    gate=$(basename "$f" .sh)
    case " $seen " in
      *" $gate "*) dupes="$dupes $gate" ;;
      *) seen="$seen $gate" ;;
    esac
    files="$files $f"
  done
done

[ -z "$dupes" ] || nogo "duplicate gate basename(s) across ci/gates/verify:$dupes"

for f in $files; do
  gate=$(basename "$f" .sh)

  # stdout only, exit code preserved without tripping set -e.
  # Counted from a file, not from $(...), which strips trailing newlines and
  # would let a blank line after the verdict pass (ticket 0010).
  sh "$f" >"$stdout_file" 2>/dev/null && rc=0 || rc=$?
  lines=$(awk 'END{print NR}' "$stdout_file")
  out=$(cat "$stdout_file")
  if [ "$lines" -ne 1 ]; then
    bad="$bad $gate(lines=$lines)"
    printf '%s: stdout has %s lines, want 1:\n%s\n' "$gate" "$lines" "$out" >&2
    continue
  fi

  case "$out" in
    *"$esc"*) bad="$bad $gate(ansi)"; printf '%s: ANSI escape in stdout\n' "$gate" >&2; continue ;;
  esac

  case "$out" in
    "GO: $gate"|"GO: $gate — "?*)
      [ "$rc" -eq 0 ] || { bad="$bad $gate(GO,exit=$rc)"; printf '%s: GO with exit %s\n' "$gate" "$rc" >&2; } ;;
    "NO-GO: $gate — "?*)
      [ "$rc" -eq 1 ] || { bad="$bad $gate(NO-GO,exit=$rc)"; printf '%s: NO-GO with exit %s\n' "$gate" "$rc" >&2; } ;;
    *)
      bad="$bad $gate(format)"; printf '%s: malformed line: %s\n' "$gate" "$out" >&2 ;;
  esac
done

# nogo with $NOGO_DETAILS (docs/adr/0038 §5). A throwaway gate sources the
# lib under test and rejects with a reason and two detail lines. Wanted:
# one stdout line and exit 1, the two lines in the file and still on stderr;
# with no details, the same one line and no file required; with
# NOGO_DETAILS unset, which is every caller but `make gates`, the same.
cat > "$probe/with-details.sh" <<'GATE'
set -eu
name=probe
. "$PROBE_LIB"
nogo "the reason" "first detail" "second detail"
GATE
cat > "$probe/no-details.sh" <<'GATE'
set -eu
name=probe
. "$PROBE_LIB"
nogo "the reason"
GATE
printf 'first detail\nsecond detail\n' > "$probe/want"
shape() {  # RC: the stdout in $probe/out is the one contract line and RC is 1
  [ "$1" -eq 1 ] && [ "$(awk 'END{print NR}' "$probe/out")" -eq 1 ] \
    && [ "$(cat "$probe/out")" = "NO-GO: probe — the reason" ]
}
details_flaw() {  # LIB: what is wrong with LIB's nogo, or nothing
  rm -f "$probe/details" "$probe/none"  # a file an earlier lib left proves nothing
  PROBE_LIB=$1 NOGO_DETAILS="$probe/details" sh "$probe/with-details.sh" >"$probe/out" 2>"$probe/err" && rc=0 || rc=$?
  shape "$rc" || { printf 'with details: not one contract line and exit 1'; return; }
  cmp -s "$probe/want" "$probe/details" 2>/dev/null || { printf 'NOGO_DETAILS does not hold the two detail lines'; return; }
  { grep -qx 'first detail' "$probe/err" && grep -qx 'second detail' "$probe/err"; } || { printf 'the details left stderr'; return; }
  PROBE_LIB=$1 NOGO_DETAILS="$probe/none" sh "$probe/no-details.sh" >"$probe/out" 2>/dev/null && rc=0 || rc=$?
  shape "$rc" || { printf 'without details: not one contract line and exit 1'; return; }
  (unset NOGO_DETAILS; PROBE_LIB=$1 sh "$probe/with-details.sh" >"$probe/out" 2>/dev/null) && rc=0 || rc=$?
  shape "$rc" || { printf 'NOGO_DETAILS unset: not one contract line and exit 1'; return; }
}
flaw=$(details_flaw ci/lib.sh)
[ -z "$flaw" ] || { bad="$bad lib.sh(nogo: $flaw)"; printf 'lib.sh: nogo: %s\n' "$flaw" >&2; }
# The check must be able to fail: each of these libs breaks one clause.
cat > "$probe/bad-stdout.sh" <<'LIB'
nogo() { printf 'NO-GO: %s — %s\n' "$name" "$1"; shift; printf '%s\n' "$@"; printf '%s\n' "$@" > "${NOGO_DETAILS:-/dev/null}"; exit 1; }
LIB
cat > "$probe/bad-nofile.sh" <<'LIB'
nogo() { printf 'NO-GO: %s — %s\n' "$name" "$1"; shift; printf '%s\n' "$@" >&2; exit 1; }
LIB
cat > "$probe/bad-unset.sh" <<'LIB'
nogo() { printf 'NO-GO: %s — %s\n' "$name" "$1"; shift; printf '%s\n' "$@" >&2; [ -z "$NOGO_DETAILS" ] || printf '%s\n' "$@" > "$NOGO_DETAILS"; exit 1; }
LIB
for broken in bad-stdout bad-nofile bad-unset; do
  flaw=$(details_flaw "$probe/$broken.sh")
  [ -n "$flaw" ] || { bad="$bad contract($broken.sh accepted)"; printf 'contract: the nogo check accepted %s\n' "$broken" >&2; }
done

[ -z "$bad" ] || nogo "gate(s) violate the output contract:$bad"

go
