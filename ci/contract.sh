#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-contract: meta-gate. Judges every other gate, and the light tier's
# entry point (docs/adr/0061), on its stdout alone, and fails unless each
# one honours the output contract in
# ci/lib.sh: exactly one stdout line, "GO: <name>" (optionally followed by
# " — <detail>", docs/adr/0042 §3) with exit 0 or "NO-GO: <name> — <reason>"
# with exit 1, no ANSI escape sequences. The gate's
# own verdict does not matter here, only its shape. Scans ci/, gates/ and
# verify/ (docs/adr/0011 §4), skipping directories that do not exist yet;
# gate basenames must be unique across the three. A ci/ check that this
# `./go ci` has already run is judged on the record of that run, the
# stdout and exit code `record_check` left in $CI_RECORDS, and not run a
# second time (docs/adr/0062 §3); every gate with no usable record, which
# is every gate when ci-contract runs alone, is run cold: stdout captured,
# stderr discarded. It also checks the lib's
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

# usable GATE: this run left a record of GATE that can be judged
# (docs/adr/0062 §3): GATE.out a readable regular file, GATE.rc one too,
# holding one line of one to three digits, 0 to 255. Anything else is no
# record: the gate is run cold.
usable() {
  [ -n "${CI_RECORDS:-}" ] || return 1
  { [ -f "$CI_RECORDS/$1.out" ] && [ -r "$CI_RECORDS/$1.out" ]; } || return 1
  { [ -f "$CI_RECORDS/$1.rc" ] && [ -r "$CI_RECORDS/$1.rc" ]; } || return 1
  [ "$(awk 'END{print NR}' "$CI_RECORDS/$1.rc")" -eq 1 ] || return 1
  case "$(cat "$CI_RECORDS/$1.rc")" in
    ''|*[!0-9]*|????*) return 1 ;;
  esac
  [ "$(cat "$CI_RECORDS/$1.rc")" -le 255 ]
}

for f in $files; do
  gate=$(basename "$f" .sh)
  case "$f" in
    ci/*)
      if usable "$gate"; then
        cat "$CI_RECORDS/$gate.out" > "$stdout_file"
        shape "$gate" "$(cat "$CI_RECORDS/$gate.rc")"
        continue
      fi
      [ -z "${CI_RECORDS:-}" ] || printf '%s: no usable record in %s, run cold\n' "$gate" "$CI_RECORDS" >&2 ;;
  esac
  # stdout only, exit code preserved without tripping set -e.
  # Counted from a file, not from $(...), which strips trailing newlines and
  # would let a blank line after the verdict pass (ticket 0010).
  sh "$f" >"$stdout_file" 2>/dev/null && rc=0 || rc=$?
  shape "$gate" "$rc"
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

# The records proof (docs/adr/0062 §5). A planted tree holds copies of this
# lib and this script, one gate per case of the ADR's table, and a planted
# record per case; its own contract.sh is run on it, the path a real
# ./go ci takes, and the one line it prints must name each rejected case with
# its reason and none of the accepted ones. Where a record decides, the gate's
# cold run prints the opposite of the verdict wanted, so only the record can
# explain the outcome. A run on a planted tree does not prove itself again.
if [ -z "${CONTRACT_PLANTED:-}" ]; then
  tree=$probe/tree
  recs=$probe/records
  mkdir -p "$tree/ci" "$recs"
  cp ci/lib.sh ci/contract.sh "$tree/ci/"
  plant() {  # CASE LINES: gate ci/CASE.sh whose cold run prints LINES lines, exit 0
    { printf 'set -eu\nname=%s\n. ci/lib.sh\n' "$1"
      [ "$2" -eq 1 ] || printf 'echo "a second line"\n'
      printf 'go\n'; } > "$tree/ci/$1.sh"
  }
  for id in two-lines ansi go-exit-1 nogo-exit-0 wrong-name blank-after; do plant "$id" 1; done
  for id in good good-nogo no-rc bad-rc never-run; do plant "$id" 2; done
  printf 'GO: two-lines\nGO: two-lines\n' > "$recs/two-lines.out"
  printf 'GO: ansi — %s[31mred\n' "$esc" > "$recs/ansi.out"
  printf 'GO: go-exit-1\n' > "$recs/go-exit-1.out"
  printf 'NO-GO: nogo-exit-0 — planted\n' > "$recs/nogo-exit-0.out"
  printf 'GO: someone-else\n' > "$recs/wrong-name.out"
  printf 'GO: blank-after\n\n' > "$recs/blank-after.out"
  printf 'GO: no-rc\n' > "$recs/no-rc.out"
  printf 'GO: bad-rc\n' > "$recs/bad-rc.out"
  printf 'GO: good — planted\n' > "$recs/good.out"
  printf 'NO-GO: good-nogo — planted\n' > "$recs/good-nogo.out"
  for id in two-lines ansi nogo-exit-0 wrong-name blank-after good; do printf '0\n' > "$recs/$id.rc"; done
  for id in go-exit-1 good-nogo; do printf '1\n' > "$recs/$id.rc"; done
  printf 'zero\n' > "$recs/bad-rc.rc"

  # record_check on a gate that prints two lines and exits 1, in a shell of its
  # own that sources the planted lib: unset CI_RECORDS first (nothing written
  # anywhere in the tree), then set (the record the planted run will judge).
  printf 'printf "GO: rc-check\\nsecond line\\n"\nexit 1\n' > "$tree/ci/rc-check.sh"
  printf 'GO: rc-check\nsecond line\n' > "$probe/rc-want"
  printf '1\n' > "$probe/rc-want-rc"
  cat > "$probe/rc-run.sh" <<'GATE'
cd "$1"
. ./ci/lib.sh
record_check ci/rc-check.sh rc-check && rc=0 || rc=$?
echo "$rc" > "$2"
GATE
  record_flaw() {  # what is wrong with the planted lib's record_check, or nothing
    find "$tree" "$recs" | sort > "$probe/before"
    (unset CI_RECORDS; sh "$probe/rc-run.sh" "$tree" "$probe/rc-code" >"$probe/rc-stdout" 2>/dev/null) || :
    cmp -s "$probe/rc-want" "$probe/rc-stdout" && [ "$(cat "$probe/rc-code" 2>/dev/null)" = 1 ] \
      || { printf 'CI_RECORDS unset: not both lines on stdout and return 1'; return; }
    find "$tree" "$recs" | sort | cmp -s "$probe/before" - || { printf 'CI_RECORDS unset: wrote something'; return; }
    (CI_RECORDS='' sh "$probe/rc-run.sh" "$tree" "$probe/rc-code" >"$probe/rc-stdout" 2>/dev/null) || :
    cmp -s "$probe/rc-want" "$probe/rc-stdout" && [ "$(cat "$probe/rc-code" 2>/dev/null)" = 1 ] \
      || { printf 'CI_RECORDS empty: not both lines on stdout and return 1'; return; }
    find "$tree" "$recs" | sort | cmp -s "$probe/before" - || { printf 'CI_RECORDS empty: wrote something'; return; }
    (CI_RECORDS=$recs sh "$probe/rc-run.sh" "$tree" "$probe/rc-code" >"$probe/rc-stdout" 2>/dev/null) || :
    cmp -s "$probe/rc-want" "$probe/rc-stdout" && [ "$(cat "$probe/rc-code" 2>/dev/null)" = 1 ] \
      || { printf 'CI_RECORDS set: not both lines on stdout and return 1'; return; }
    cmp -s "$probe/rc-want" "$recs/rc-check.out" 2>/dev/null || { printf 'NAME.out does not hold both lines'; return; }
    cmp -s "$probe/rc-want-rc" "$recs/rc-check.rc" 2>/dev/null || { printf 'NAME.rc is not the line 1'; return; }
  }
  flaw=$(record_flaw)
  [ -z "$flaw" ] || { bad="$bad contract(record_check: $flaw)"; printf 'contract: record_check: %s\n' "$flaw" >&2; }

  (cd "$tree" && CI_RECORDS=$recs CONTRACT_PLANTED=1 sh ci/contract.sh) >"$probe/planted.out" 2>"$probe/planted.err" || :
  planted=$(cat "$probe/planted.out")
  proved=$bad
  # Rejected as CASE:WHY (a case run cold prints two lines). The rest of the
  # planted line (gates-light, gates: the tree has no core/) is not ours.
  for pair in two-lines:lines=2 ansi:ansi go-exit-1:GO,exit=1 nogo-exit-0:NO-GO,exit=0 \
      wrong-name:format blank-after:lines=2 no-rc:lines=2 bad-rc:lines=2 never-run:lines=2 rc-check:lines=2; do
    id=${pair%%:*}
    want=${pair#*:}
    case " $planted" in
      *" $id("*)
        got=${planted#*" $id("}
        got=${got%%)*}
        [ -z "$want" ] || [ "$got" = "$want" ] || {
          bad="$bad contract(record $id wrong-why)"
          printf 'contract: record %s was rejected as %s, want %s\n' "$id" "$got" "$want" >&2; } ;;
      *) bad="$bad contract(record $id accepted)"
         printf 'contract: record %s should be rejected and was accepted\n' "$id" >&2 ;;
    esac
  done
  for id in good good-nogo; do
    case " $planted" in
      *" $id("*) bad="$bad contract(record $id rejected)"
                 printf 'contract: record %s should be accepted and was rejected\n' "$id" >&2 ;;
    esac
  done
  [ "$bad" = "$proved" ] || printf 'contract: the planted run said: %s\n' "$planted" >&2
fi

[ -z "$bad" ] || nogo "gate(s) violate the output contract:$bad"

go
