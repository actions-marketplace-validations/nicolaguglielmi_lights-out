#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-contract: meta-gate. Runs every other gate, and the light tier's
# entry point (docs/adr/0061), with stdout captured and stderr discarded,
# and fails unless each one honours the output contract in
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

# shape GATE RC: the stdout in $stdout_file is GATE's one contract line and
# RC agrees with it; otherwise GATE and why join $bad.
shape() {
  gate=$1
  rc=$2
  lines=$(awk 'END{print NR}' "$stdout_file")
  out=$(cat "$stdout_file")
  if [ "$lines" -ne 1 ]; then
    bad="$bad $gate(lines=$lines)"
    printf '%s: stdout has %s lines, want 1:\n%s\n' "$gate" "$lines" "$out" >&2
    return
  fi

  case "$out" in
    *"$esc"*) bad="$bad $gate(ansi)"; printf '%s: ANSI escape in stdout\n' "$gate" >&2; return ;;
  esac

  case "$out" in
    "GO: $gate"|"GO: $gate — "?*)
      [ "$rc" -eq 0 ] || { bad="$bad $gate(GO,exit=$rc)"; printf '%s: GO with exit %s\n' "$gate" "$rc" >&2; } ;;
    "NO-GO: $gate — "?*)
      [ "$rc" -eq 1 ] || { bad="$bad $gate(NO-GO,exit=$rc)"; printf '%s: NO-GO with exit %s\n' "$gate" "$rc" >&2; } ;;
    *)
      bad="$bad $gate(format)"; printf '%s: malformed line: %s\n' "$gate" "$out" >&2 ;;
  esac
}

for f in $files; do
  # stdout only, exit code preserved without tripping set -e.
  # Counted from a file, not from $(...), which strips trailing newlines and
  # would let a blank line after the verdict pass (ticket 0010).
  sh "$f" >"$stdout_file" 2>/dev/null && rc=0 || rc=$?
  shape "$(basename "$f" .sh)" "$rc"
done

# The light tier's entry point (docs/adr/0061 §5) is no ci/, gates/ or
# verify/ file: run by name, cold, from this checkout (PYTHONSAFEPATH: the
# checkout's core/, never a cwd's), in its three shapes: this checkout's
# last commit judged, an argument it does not take, and `gates` without
# --light, which is named `gates` and may only be a NO-GO.
light() {
  PYTHONSAFEPATH=1 PYTHONPATH=. python3 -m core "$@" >"$stdout_file" 2>/dev/null
}
light gates --light && rc=0 || rc=$?
shape gates-light "$rc"
light gates --light NOT_AN_ARGUMENT=1 && rc=0 || rc=$?
shape gates-light "$rc"
[ "$rc" -eq 1 ] || bad="$bad gates-light(an unknown argument passed)"
light gates && rc=0 || rc=$?
shape gates "$rc"
[ "$rc" -eq 1 ] || bad="$bad gates(the light package printed GO: gates)"

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
