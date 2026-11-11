#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-sast-diff: proves docs/adr/0072 §1 cold: no engine, no network, no key.
# Written from the ADR's decision 1 (and its line wording), not from
# gates/sast.sh. It drives the real gate, `sh gates/sast.sh`, on throwaway
# git repositories with a stub runner (TOOLCHAIN_IMAGE=workbench, so the
# runner runs in this container), in a clean environment per run.
#   (a) a clean base and a change that adds a finding: NO-GO, one new.
#   (b) the base has a finding; the change inserts lines above it and
#       renames its file: GO, one inherited, and sast.json names the new path.
#   (c) the base has a finding; the change re-indents its line: GO.
#   (d) the base has a finding; the change adds an identical second line in
#       the same file: NO-GO, one new (duplicates count).
#   (e) HEAD is clean and the base had findings: GO, and the runner never
#       ran on the base.
#   (f) the empty tree as the base: every finding is new.
#   (g) a workload in a subdirectory with a test root: the inherited and the
#       new paths in sast.json carry the repository prefix.
#   (h) an old runner (no items) on both sides: HEAD is judged whole, the
#       line says so, and stderr says the runner prints no items; with a
#       clean HEAD the old runner is a plain GO.
#   (i) a runner that prints items at HEAD and an old one at the base (the
#       runner is a file in the repository, changed by the commit): HEAD is
#       judged whole.
#   (j) every gate stdout of every case above is exactly one line with no
#       ANSI escape, and exits 0 on GO and 1 on NO-GO.
#   (l) a runner line that is not JSON is a NO-GO; no BASE and HEAD is the
#       one-line NO-GO of require_range.
#   (k) the checks can fail: the comparison helpers are run against planted
#       wrong expectations (a GO expected where the gate NO-GOes, a wrong
#       count in sast.json, two lines or an escape on stdout, a base scan
#       that the runner log shows) and must report each.
set -eu
name=sast-diff
. ci/lib.sh

[ -f gates/sast.sh ] || nogo "gates/sast.sh not found"

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY
lo=$(pwd)
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
mismatch=""
fail_case() {
  printf 'ci-sast-diff: %s: %s\n' "$1" "$2" >&2
  [ -n "$mismatch" ] || mismatch="$1"
}
esc=$(printf '\033')

# The stub runners. A finding is a line holding the marker FINDING- and a
# rule id, say FINDING-R1; the marker is written as a character class here
# so that the stub does not flag itself. It scans the current directory and
# prints items with `file` relative to it; the report goes to stderr. With
# STUB_LOG set it records where it ran.
cat > "$t/stub-new.sh" <<'STUB'
[ -z "${STUB_LOG:-}" ] || pwd -P >> "$STUB_LOG"
echo "stub: scanned $(pwd -P)" >&2
find . -type f ! -path './.git' ! -path './.git/*' -exec awk '
  /FINDIN[G]-[A-Za-z0-9]+/ {
    match($0, /FINDIN[G]-[A-Za-z0-9]+/)
    f = FILENAME; sub(/^\.\//, "", f)
    print substr($0, RSTART + 8, RLENGTH - 8) "\t" f "\t" FNR
  }' {} + | awk -F '\t' '
  { n++; it = it (n > 1 ? ", " : "") "{\"rule\": \"" $1 "\", \"file\": \"" $2 "\", \"line\": " $3 "}" }
  END { printf "{\"findings\": %d, \"items\": [%s]}\n", n, it }'
STUB
cat > "$t/stub-old.sh" <<'STUB'
[ -z "${STUB_LOG:-}" ] || pwd -P >> "$STUB_LOG"
echo "stub: scanned $(pwd -P)" >&2
find . -type f ! -path './.git' ! -path './.git/*' -exec awk '
  /FINDIN[G]-[A-Za-z0-9]+/ { print FILENAME }' {} + | awk '
  { n++ }
  END { printf "{\"findings\": %d}\n", n }'
STUB
printf 'echo "not json at all"\n' > "$t/stub-bad.sh"
new="sh $t/stub-new.sh"
old="sh $t/stub-old.sh"

# mkrepo NAME: a fresh repository, in $r. commit MSG: everything in the
# working tree, the new commit's id on stdout. pad: ten filler lines, so
# that a rename keeps enough of its file to be detected as one.
mkrepo() {
  r=$t/$1
  mkdir -p "$r"
  git -C "$r" init -q
}
commit() {
  git -C "$r" add -A
  git -C "$r" -c user.name=t -c user.email=t@example.invalid -c commit.gpgsign=false commit -q -m "$1"
  git -C "$r" rev-parse HEAD
}
pad() { for i in 1 2 3 4 5 6 7 8 9 10; do printf 'filler line %s of the file\n' "$i"; done; }

# run BASE HEAD WORKLOAD TESTROOT SAST_CMD [VAR=value...]: the real gate, from
# this repository's root, in an environment of its own. stdout in $t/out,
# stderr in $t/err, the exit code in $prc, GATES_OUT in $gout.
run() {
  b=$1 h=$2 w=$3 tr=$4 cmd=$5
  shift 5
  gout=$(mktemp -d "$t/gout.XXXXXX")
  (
    cd "$lo" &&
    env -i PATH="$PATH" HOME="$HOME" BASE="$b" HEAD="$h" WORKLOAD="$w" WORKLOAD_TEST_ROOT="$tr" \
      TOOLCHAIN_IMAGE=workbench SAST_CMD="$cmd" GATES_OUT="$gout" "$@" sh gates/sast.sh
  ) >"$t/out" 2>"$t/err" && prc=0 || prc=$?
}

# The lines of ADR 0072 §1, where being `workbench`.
line_none() { printf 'GO: sast — in workbench, none new (%s inherited)' "$1"; }
line_new() { printf 'NO-GO: sast — in workbench: this diff introduces %s finding(s); list on stderr' "$1"; }
line_whole() { printf "NO-GO: sast — in workbench: %s SAST finding(s) in the workload's scope" "$1"; }

# flaw_of WANT_RC WANT_LINE [ALT_LINE]: what is wrong with the last run, or
# nothing. Also the contract (j): one line, no escape. Never calls nogo.
flaw_of() {
  [ "$prc" -eq "$1" ] || { printf 'exit %s, want %s' "$prc" "$1"; return; }
  n=$(awk 'END{print NR}' "$t/out")
  [ "$n" -eq 1 ] || { printf 'stdout has %s lines, want 1' "$n"; return; }
  line=$(cat "$t/out")
  [ -n "$line" ] || { printf 'stdout is an empty line'; return; }
  case "$line" in *"$esc"*) printf 'stdout has an ANSI escape: %s' "$line"; return ;; esac
  [ "$line" = "$2" ] && return
  if [ -n "${3:-}" ] && [ "$line" = "$3" ]; then return; fi
  printf 'stdout is "%s", want "%s"' "$line" "$2"
}
# check LABEL WANT_RC WANT_LINE [ALT_LINE]
check() {
  flaw=$(flaw_of "$2" "$3" "${4:-}")
  [ -z "$flaw" ] || {
    fail_case "$1" "$flaw"
    sed 's/^/  gate stderr: /' "$t/err" >&2
  }
}

# json_flaw FILE FILTER WANT: nothing when jq's raw output of FILTER is WANT.
json_flaw() {
  got=$(jq -r "$2" "$1" 2>/dev/null) || got="(jq failed or $1 missing)"
  [ "$got" = "$3" ] || printf '%s of %s is "%s", want "%s"' "$2" "$1" "$got" "$3"
}
# jcheck LABEL FILE FILTER WANT
jcheck() {
  flaw=$(json_flaw "$2" "$3" "$4")
  [ -z "$flaw" ] || fail_case "$1" "$flaw"
}
# err_flaw WANT: nothing when stderr of the last run names WANT.
err_flaw() { grep -qF -- "$1" "$t/err" || printf 'stderr does not name "%s"' "$1"; }
# log_flaw LOG DIR: nothing when the runner ran, and only in DIR.
log_flaw() {
  [ -s "$1" ] || { printf 'the runner never ran'; return; }
  while IFS= read -r l; do
    [ "$l" = "$2" ] || { printf 'the runner also ran in %s' "$l"; return; }
  done < "$1"
}

# (a) a clean base, a change that adds one.
mkrepo a
pad > "$r/a.py"
base=$(commit base)
printf 'danger FINDING-R1 here\n' > "$r/b.py"
head=$(commit add)
run "$base" "$head" "$r" "" "$new" STUB_LOG="$t/log-a"
check a-adds 1 "$(line_new 1)"
jcheck a-json "$gout/sast.json" '.new | length' 1
jcheck a-json "$gout/sast.json" '.inherited | length' 0
jcheck a-json "$gout/sast.json" '.new[0].file' b.py
flaw=$(err_flaw R1)
[ -z "$flaw" ] || fail_case a-stderr "$flaw"
flaw=$(err_flaw b.py)
[ -z "$flaw" ] || fail_case a-stderr "$flaw"

# (k) first part, on (a)'s run: planted wrong expectations must be reported.
[ -n "$(flaw_of 0 "$(line_none 0)")" ] || fail_case k-gate "a GO was accepted for a run that NO-GOed"
[ -n "$(flaw_of 1 "$(line_new 2)")" ] || fail_case k-count "a wrong count in the line was accepted"
[ -n "$(json_flaw "$gout/sast.json" '.new | length' 0)" ] || fail_case k-json "a wrong count in sast.json was accepted"
[ -n "$(json_flaw "$gout/missing.json" '.new | length' 1)" ] || fail_case k-json "a missing sast.json was accepted"
[ -n "$(err_flaw NOT-ON-STDERR)" ] || fail_case k-stderr "a name that stderr lacks was accepted"
# Both sides ran in this case: a log check that wants only the head must say so.
[ -n "$(log_flaw "$t/log-a" "$(cd "$r" && pwd -P)")" ] || fail_case k-log "a base scan went unnoticed by the log check"
cp "$t/out" "$t/out.real"
prc=0
printf 'GO: sast\nGO: sast\n' > "$t/out"
[ -n "$(flaw_of 0 'GO: sast')" ] || fail_case k-lines "two lines on stdout were accepted"
printf 'GO: sast \033[0m\n' > "$t/out"
[ -n "$(flaw_of 0 "GO: sast ${esc}[0m")" ] || fail_case k-ansi "an escape on stdout was accepted"
printf '\n' > "$t/out"
[ -n "$(flaw_of 0 '')" ] || fail_case k-empty "an empty line on stdout was accepted"

# (b) the base has one; lines inserted above it and its file renamed.
mkrepo b
{ pad; printf 'call FINDING-R1 here\n'; } > "$r/old.py"
base=$(commit base)
git -C "$r" mv old.py new.py
{ printf '# header one\n# header two\n'; cat "$r/new.py"; } > "$r/tmp.py"
mv "$r/tmp.py" "$r/new.py"
head=$(commit move)
run "$base" "$head" "$r" "" "$new"
check b-moved 0 "$(line_none 1)"
jcheck b-json "$gout/sast.json" '.inherited | length' 1
jcheck b-json "$gout/sast.json" '.new | length' 0
jcheck b-json "$gout/sast.json" '.inherited[0].file' new.py

# (c) the base has one; its line is re-indented.
mkrepo c
printf 'x = 1\nFINDING-R1 call(a, b)\n' > "$r/a.py"
base=$(commit base)
printf 'x = 1\n    FINDING-R1\tcall( a,b )   \n' > "$r/a.py"
head=$(commit reindent)
run "$base" "$head" "$r" "" "$new"
check c-reindent 0 "$(line_none 1)"

# (d) the base has one; the change adds an identical second line.
mkrepo d
printf 'FINDING-R1 call(a)\n' > "$r/a.py"
base=$(commit base)
printf 'FINDING-R1 call(a)\nx = 1\nFINDING-R1 call(a)\n' > "$r/a.py"
head=$(commit twice)
run "$base" "$head" "$r" "" "$new"
check d-count 1 "$(line_new 1)"
jcheck d-json "$gout/sast.json" '.new | length' 1
jcheck d-json "$gout/sast.json" '.inherited | length' 1

# (e) HEAD is clean, the base had findings: GO, and the base was never scanned.
mkrepo e
printf 'FINDING-R1 call(a)\nFINDING-R2 call(b)\n' > "$r/a.py"
base=$(commit base)
printf 'x = 1\n' > "$r/a.py"
head=$(commit fix)
rm -f "$t/log-e"
run "$base" "$head" "$r" "" "$new" STUB_LOG="$t/log-e"
# The ADR words a GO with nothing new; a clean HEAD is also the whole-tree
# GO of an old runner. Either line is a GO here.
check e-clean 0 "$(line_none 0)" "GO: sast — in workbench"
flaw=$(log_flaw "$t/log-e" "$(cd "$r" && pwd -P)")
[ -z "$flaw" ] || fail_case e-base-scanned "$flaw"

# (f) the empty tree as the base: every finding is new.
mkrepo f
printf 'FINDING-R1 call(a)\n' > "$r/a.py"
printf 'FINDING-R2 call(b)\n' > "$r/b.py"
head=$(commit all)
empty=$(git -C "$r" hash-object -t tree /dev/null)
run "$empty" "$head" "$r" "" "$new"
check f-empty-tree 1 "$(line_new 2)"
jcheck f-json "$gout/sast.json" '.new | length' 2
jcheck f-json "$gout/sast.json" '.inherited | length' 0

# (g) a workload in a subdirectory with a test root: paths carry the prefix.
mkrepo g
mkdir -p "$r/svc/src"
{ pad; printf 'call FINDING-R1 here\n'; } > "$r/svc/src/old.py"
printf 'FINDING-R9 outside the scan\n' > "$r/outside.txt"
base=$(commit base)
git -C "$r" mv svc/src/old.py svc/src/new.py
printf 'FINDING-R2 fresh\n' > "$r/svc/src/fresh.py"
head=$(commit change)
run "$base" "$head" "$r/svc" "src/" "$new"
check g-prefix 1 "$(line_new 1)"
jcheck g-json "$gout/sast.json" '.inherited[0].file' svc/src/new.py
jcheck g-json "$gout/sast.json" '.new[0].file' svc/src/fresh.py
jcheck g-json "$gout/sast.json" '.new | length' 1
jcheck g-json "$gout/sast.json" '.inherited | length' 1

# (h) an old runner on both sides: HEAD judged whole.
mkrepo h
printf 'FINDING-R1 call(a)\n' > "$r/a.py"
base=$(commit base)
printf 'x = 1\nFINDING-R1 call(a)\n' > "$r/a.py"
head=$(commit shift)
run "$base" "$head" "$r" "" "$old"
check h-whole 1 "$(line_whole 1)"
flaw=$(err_flaw items)
[ -z "$flaw" ] || fail_case h-stderr "$flaw"
printf 'x = 1\n' > "$r/a.py"
head=$(commit fix)
run "$base" "$head" "$r" "" "$old"
check h-clean 0 "GO: sast — in workbench"

# (i) items at HEAD, an old runner at the base: HEAD judged whole.
mkrepo i
cp "$t/stub-old.sh" "$r/stub.sh"
printf 'FINDING-R1 call(a)\n' > "$r/a.py"
base=$(commit base)
cp "$t/stub-new.sh" "$r/stub.sh"
printf 'x = 1\nFINDING-R1 call(a)\n' > "$r/a.py"
head=$(commit upgrade)
run "$base" "$head" "$r" "" "sh stub.sh"
check i-mixed 1 "$(line_whole 1)"
flaw=$(err_flaw items)
[ -z "$flaw" ] || fail_case i-stderr "$flaw"

# (l) a runner line that is not JSON; no range at all.
mkrepo l
printf 'FINDING-R1 call(a)\n' > "$r/a.py"
base=$(commit base)
printf 'x = 1\nFINDING-R1 call(a)\n' > "$r/a.py"
head=$(commit shift)
run "$base" "$head" "$r" "" "sh $t/stub-bad.sh"
{ [ "$prc" -eq 1 ] && [ "$(awk 'END{print NR}' "$t/out")" -eq 1 ]; } || fail_case l-bad-json "exit $prc and stdout '$(cat "$t/out")', want a one-line NO-GO"
case "$(cat "$t/out")" in
  "NO-GO: sast — "?*) : ;;
  *) fail_case l-bad-json "stdout is '$(cat "$t/out")', want NO-GO: sast — <reason>" ;;
esac
(
  cd "$lo" &&
  env -i PATH="$PATH" HOME="$HOME" WORKLOAD="$r" TOOLCHAIN_IMAGE=workbench SAST_CMD="$new" GATES_OUT="$t" sh gates/sast.sh
) >"$t/out" 2>"$t/err" && prc=0 || prc=$?
check l-no-range 1 "NO-GO: sast — BASE and HEAD must both be set"

[ -z "$mismatch" ] || nogo "case $mismatch failed; see stderr"

go
