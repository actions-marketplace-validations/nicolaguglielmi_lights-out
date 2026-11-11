#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-range: proves docs/adr/0074 cold: no network, no engine, no gh login.
# .github/range.sh runs in temp git repositories with a fake `gh` first on
# PATH that serves one JSON file of check runs per sha and logs its calls;
# gates/mutation.sh runs from a temp directory against a temp git repository
# as the workload, with TOOLCHAIN_IMAGE=workbench and a fake MUTATION_CMD that
# writes its MUTATION_LINES to a file.
#   (a) the frontier (§1, §2): the base is the nearest first-parent ancestor
#       of HEAD (HEAD^1 first, HEAD itself never) whose most recent
#       `lights-out gates` check from github-actions is a success whose
#       record names that commit as its head; a red one, one with no check,
#       one whose most recent check is red whatever its older ones, a green
#       from another app and a green whose record names another head are
#       skipped; a grandfathered green (empty external_id) is a base; the
#       walk is first-parent, so a side branch's green is never a base; none
#       within 100 first-parent commits, or no parent at all, is one
#       `NO-GO: gates — ...` line and exit 1.
#   (b) the judged trees (§3, §4): for each merge on the first-parent path
#       base..HEAD, HEAD included, the nearest commit of the second parent's
#       first-parent chain, stopping before the merge-base, whose most
#       recent github-actions check is a green record, if its record chain
#       reaches an ancestor-or-self of the base before an unrecorded commit
#       or 100 steps; a grandfathered green that is not an ancestor of the
#       base is not sound. Written to $GITHUB_OUTPUT as base= and judged=.
#   (c) the mutation lines (§3, §4): with JUDGED, the lines mutated are the
#       intersection of the `+` sides of the diffs against the base and
#       against every tree, so a merge's own resolution line is mutated and
#       a judged side's lines are not; every line judged means the command
#       does not run and the gate is a GO; a JUDGED sha that is no commit or
#       no ancestor of HEAD is one NO-GO line; the GO line says how many
#       lines were skipped and at which short shas; empty or unset JUDGED is
#       today's lines and today's GO line.
#   (d) the checks can fail: (a) and (b) run against stand-ins for
#       .github/range.sh that take HEAD^1 as the base, always refuse, or
#       take any commit with a check; (c) against copies of gates/mutation.sh
#       that ignore JUDGED, or never run. Each must be reported.
# Written from the ADR, not from the implementation.
set -eu
name=range
. ci/lib.sh

for f in ci/lib.sh .github/range.sh gates/mutation.sh core/toolchain.sh core/policy.py \
  policy/merge.env .lights-out/workload.env; do
  [ -f "$f" ] || nogo "$f not found"
done
for c in git jq python3 awk; do
  command -v "$c" >/dev/null 2>&1 || nogo "$c is not installed"
done

repo=$(pwd)
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
mismatch=""
fail_case() {
  printf 'ci-range: %s: %s\n' "$1" "$2" >&2
  [ -n "$mismatch" ] || mismatch="$1"
}

# A git of our own: no user config, no signing, no editor.
GIT_CONFIG_GLOBAL=/dev/null
GIT_CONFIG_NOSYSTEM=1
GIT_AUTHOR_NAME=t
GIT_AUTHOR_EMAIL=t@example.invalid
GIT_COMMITTER_NAME=t
GIT_COMMITTER_EMAIL=t@example.invalid
GIT_MERGE_AUTOEDIT=no
export GIT_CONFIG_GLOBAL GIT_CONFIG_NOSYSTEM GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL \
  GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL GIT_MERGE_AUTOEDIT

# ---------------------------------------------------------------- fake gh
mkdir -p "$t/bin"
cat > "$t/bin/gh" <<'GH'
#!/bin/sh
# Serves $GH_DIR/<sha>.json for `gh api repos/o/r/commits/<sha>/check-runs?...`
# and nothing else; logs every call to $GH_LOG.
printf '%s\n' "$*" >> "${GH_LOG:?}"
[ "${1:-}" = api ] || { echo "fake gh: not an api call: $*" >&2; exit 1; }
shift
path=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -H|--header) shift ;;
    -*) echo "fake gh: option $1 is not served (no --jq, parse with jq)" >&2; exit 1 ;;
    *) [ -z "$path" ] || { echo "fake gh: two paths" >&2; exit 1; }; path=$1 ;;
  esac
  shift
done
q='?check_name=lights-out%20gates&filter=all&per_page=100'
case "$path" in
  repos/o/r/commits/*/check-runs"$q") ;;
  *) echo "fake gh: unexpected path $path" >&2; exit 1 ;;
esac
sha=${path#repos/o/r/commits/}
sha=${sha%%/*}
case "$sha" in
  *[!0-9a-f]*|'') echo "fake gh: $sha is not a sha" >&2; exit 1 ;;
esac
[ "${#sha}" -eq 40 ] || { echo "fake gh: $sha is not a full sha" >&2; exit 1; }
if [ -f "$GH_DIR/$sha.json" ]; then
  cat "$GH_DIR/$sha.json"
else
  printf '{"total_count":0,"check_runs":[]}\n'
fi
GH
chmod +x "$t/bin/gh"

# ---------------------------------------------------------- range fixtures
cases=""
rid=0
g() { git -C "$d" "$@"; }
newcase() {  # ID: an empty repository on main, and its check-run store
  cid=$1
  cdir=$t/case/$cid
  mkdir -p "$cdir/gh"
  d=$cdir/repo
  git init -q "$d"
  g symbolic-ref HEAD refs/heads/main
  cases="$cases $cid"
}
cm() {  # NAME...: an empty commit per name, each tagged with its name
  for n in "$@"; do
    g commit -q --allow-empty -m "$n"
    g tag "$n"
  done
}
sha() { g rev-parse "$1^{commit}"; }
ext() {  # "A..B" by names -> full shas; "" stays empty
  case $1 in
    '') ;;
    *..*) printf '%s..%s' "$(sha "${1%%..*}")" "$(sha "${1#*..}")" ;;
  esac
}
rec() {  # NAME ID CONCLUSION EXT [APP]: one check run on NAME
  s=$(sha "$1")
  e=$(ext "$4")
  jq -nc --arg s "$s" --argjson id "$2" --arg c "$3" --arg e "$e" --arg a "${5:-github-actions}" \
    '{id:$id,head_sha:$s,conclusion:$c,external_id:$e,app:{slug:$a}}' >> "$cdir/gh/$s.runs"
}
green() {  # NAME BASE: a green record on NAME of BASE..NAME
  rid=$((rid + 1))
  rec "$1" "$rid" success "$2..$1"
}
chain() {  # PREFIX FROM N: PREFIX1..PREFIXN on the current branch, each a green record of its parent
  prev=$2
  i=1
  while [ "$i" -le "$3" ]; do
    cm "$1$i"
    green "$1$i" "$prev"
    prev=$1$i
    i=$((i + 1))
  done
}
want_go() {  # BASE [TREE...]: the expectation, by names
  {
    printf 'kind=go\nbase=%s\n' "$(sha "$1")"
    shift
    j=""
    for n in "$@"; do j="$j $(sha "$n")"; done
    # shellcheck disable=SC2086 # word splitting is the point
    printf 'judged=%s\n' "$(printf '%s\n' $j | sort | tr '\n' ' ')"
  } > "$cdir/want"
}
want_nogo() { printf 'kind=nogo\n' > "$cdir/want"; }
want_nogo_100() {
  printf 'kind=nogo\nmsg=NO-GO: gates — no green ancestor within 100 first-parent commits of %s\n' \
    "$(g rev-parse HEAD)" > "$cdir/want"
}
done_case() {
  for f in "$cdir"/gh/*.runs; do
    [ -e "$f" ] || continue
    jq -s '{total_count:length,check_runs:.}' "$f" > "${f%.runs}.json"
  done
}
side() { g checkout -q -b "$1" "$2"; }  # NAME FROM: a branch off FROM, checked out
merge() {  # NAME BRANCH: merge BRANCH into the checked-out main, tagged NAME
  g merge -q --no-ff -m "$1" "$2" >&2
  g tag "$1"
}

# (a) the frontier, linear history r0..r6, HEAD r6
lin() {  # ID: r0..r6 on main
  newcase "$1"
  cm r0 r1 r2 r3 r4 r5 r6
}
lin f-nearest
green r5 r4; green r3 r2; want_go r5; done_case
lin f-skip-red
rec r5 1 failure "r4..r5"; green r4 r3; want_go r4; done_case
lin f-skip-nocheck
green r3 r2; want_go r3; done_case
lin f-red-after-green-a
rec r5 10 success "r4..r5"; rec r5 20 failure "r4..r5"; green r4 r3; want_go r4; done_case
lin f-red-after-green-b
rec r5 20 failure "r4..r5"; rec r5 10 success "r4..r5"; green r4 r3; want_go r4; done_case
lin f-green-after-red-a
rec r5 10 failure "r4..r5"; rec r5 20 success "r4..r5"; green r4 r3; want_go r5; done_case
lin f-green-after-red-b
rec r5 20 success "r4..r5"; rec r5 10 failure "r4..r5"; green r4 r3; want_go r5; done_case
lin f-other-app
rec r5 1 success "r4..r5" some-other-app; green r4 r3; want_go r4; done_case
lin f-other-head
rec r5 1 success "r2..r3"; green r4 r3; want_go r4; done_case
lin f-grandfathered
rec r5 1 success ""; want_go r5; done_case
lin f-grandfathered-older
rec r5 1 failure "r4..r5"; rec r4 1 success ""; want_go r4; done_case
lin f-head-never
green r6 r5; green r4 r3; want_go r4; done_case
lin f-cancelled
rec r5 1 cancelled "r4..r5"; green r4 r3; want_go r4; done_case

# first-parent only: a green on a side branch is never a base
newcase f-first-parent
cm p0 p1; green p0 p0
side side p0; cm s1; green s1 p0
g checkout -q main; cm m1
merge hd side
want_go p0 s1
done_case

# 100 first-parent commits: 102 commits, HEAD the last
newcase f-past-100
i=0
while [ "$i" -le 101 ]; do cm "c$i"; i=$((i + 1)); done
green c0 c0
want_nogo_100
done_case
newcase f-edge-100
i=0
while [ "$i" -le 101 ]; do cm "c$i"; i=$((i + 1)); done
green c1 c0
want_go c1
done_case

newcase f-no-parent
cm only
want_nogo
done_case

# (b) the judged trees. main p0, p1; side branch s1, s2; main m1; HEAD the merge.
jt() {  # ID: p0, p1 (a green record of p0..p1), side s1 s2 off p1, m1
  newcase "$1"
  cm p0 p1
  green p1 p0
  side side p1
  cm s1 s2
  g checkout -q main
  cm m1
}
jt j-tip
green s2 p1; merge hd side; want_go p1 s2; done_case
jt j-unrecorded
merge hd side; want_go p1; done_case
jt j-ancestor
green s1 p1; merge hd side; want_go p1 s1; done_case
jt j-two-step
green s1 p1; green s2 s1; merge hd side; want_go p1 s2; done_case
jt j-chain-red
rec s1 1 failure "p1..s1"; green s2 s1; merge hd side; want_go p1; done_case
jt j-chain-unrecorded
green s2 s1; merge hd side; want_go p1; done_case
jt j-pr-check
rec s2 1 success "p1..p0"; green s1 p1; merge hd side; want_go p1 s1; done_case
jt j-red-after-green
rec s2 1 success "p1..s2"; rec s2 2 failure "p1..s2"; green s1 p1; merge hd side; want_go p1 s1; done_case
jt j-other-app
rec s2 1 success "p1..s2" some-other-app; merge hd side; want_go p1; done_case

# the walk stops before the merge-base: the side's only record is the merge-base itself
newcase j-merge-base-only
cm p0 p1
green p1 p0
side side p0
cm s1
green p0 p0
g checkout -q main
cm m1
merge hd side
want_go p1
done_case

# a record built on a grandfathered green: sound only if that green is an ancestor-or-self of the base
newcase j-grandfather-bad
cm p0 p1
green p1 p0
side side p0
cm g
rec g 1 success ""
cm s1
green s1 g
g checkout -q main
cm m1
merge hd side
want_go p1
done_case
newcase j-grandfather-ok
cm p0 p1
green p1 p0
side side p0
cm s1
rec p0 1 success ""
green s1 p0
g checkout -q main
cm m1
merge hd side
want_go p1 s1
done_case

# the 100 steps
newcase j-long-chain
cm p0 p1
green p1 p0
side side p1
chain k p1 110
g checkout -q main
cm m1
merge hd side
want_go p1
done_case
newcase j-short-chain
cm p0 p1
green p1 p0
side side p1
chain k p1 5
g checkout -q main
cm m1
merge hd side
want_go p1 k5
done_case

# two merges on the path, each with a recorded side
newcase j-two-merges
cm p0 p1
green p1 p0
side sa p1
cm a1
green a1 p1
side sb p1
cm b1
green b1 p1
g checkout -q main
cm m1
merge mrg1 sa
cm m2
merge hd sb
want_go p1 a1 b1
done_case

# a merge below the head, not HEAD itself
newcase j-merge-below-head
cm p0 p1
green p1 p0
side sa p1
cm a1
green a1 p1
g checkout -q main
cm m1
merge mrg1 sa
cm m2
want_go p1 a1
done_case

# check_range SCRIPT: the flaws (one line each) of SCRIPT against every case
check_range() {
  script=$1
  for cid in $cases; do
    cdir=$t/case/$cid
    d=$cdir/repo
    rm -f "$t/gho" "$t/gh.log" "$t/rout" "$t/rerr"
    : > "$t/gh.log"
    (
      cd "$d" &&
      env -i PATH="$t/bin:$PATH" HOME="$t" GITHUB_REPOSITORY=o/r GITHUB_OUTPUT="$t/gho" \
        GITHUB_STEP_SUMMARY="$t/gsum" GH_DIR="$cdir/gh" GH_LOG="$t/gh.log" sh "$script"
    ) >"$t/rout" 2>"$t/rerr" && rrc=0 || rrc=$?
    kind=$(sed -n 's/^kind=//p' "$cdir/want")
    headsha=$(git -C "$d" rev-parse HEAD)
    if [ "$kind" = go ]; then
      [ "$rrc" -eq 0 ] || { printf '%s: exit %s, want 0: %s\n' "$cid" "$rrc" "$(tr '\n' '|' <"$t/rerr")"; continue; }
      case "$(cat "$t/rout")" in
        *NO-GO*) printf '%s: a success that says NO-GO on stdout\n' "$cid"; continue ;;
      esac
      [ -f "$t/gho" ] || { printf '%s: nothing written to GITHUB_OUTPUT\n' "$cid"; continue; }
      nb=$(awk '/^base=/{n++} END{print n+0}' "$t/gho")
      nj=$(awk '/^judged=/{n++} END{print n+0}' "$t/gho")
      [ "$nb" -eq 1 ] && [ "$nj" -eq 1 ] || { printf '%s: GITHUB_OUTPUT has %s base= and %s judged= lines, want one each\n' "$cid" "$nb" "$nj"; continue; }
      gb=$(sed -n 's/^base=//p' "$t/gho")
      gj=$(sed -n 's/^judged=//p' "$t/gho")
      # shellcheck disable=SC2086 # word splitting is the point
      gj=$(printf '%s\n' $gj | sort | tr '\n' ' ')
      wb=$(sed -n 's/^base=//p' "$cdir/want")
      wj=$(sed -n 's/^judged=//p' "$cdir/want")
      [ "$gb" = "$wb" ] || { printf '%s: base=%s, want %s\n' "$cid" "$gb" "$wb"; continue; }
      [ "$gj" = "$wj" ] || { printf '%s: judged=[%s], want [%s]\n' "$cid" "$gj" "$wj"; continue; }
      if awk -v h="$headsha" 'index($0, "commits/" h "/") {f=1} END{exit !f}' "$t/gh.log"; then
        printf '%s: HEAD itself was asked about; it is never the base\n' "$cid"
        continue
      fi
    else
      [ "$rrc" -eq 1 ] || { printf '%s: exit %s, want 1\n' "$cid" "$rrc"; continue; }
      [ "$(awk 'END{print NR}' "$t/rout")" -eq 1 ] || { printf '%s: stdout has %s lines, want 1\n' "$cid" "$(awk 'END{print NR}' "$t/rout")"; continue; }
      msg=$(sed -n 's/^msg=//p' "$cdir/want")
      if [ -n "$msg" ]; then
        [ "$(cat "$t/rout")" = "$msg" ] || { printf '%s: stdout is [%s], want [%s]\n' "$cid" "$(cat "$t/rout")" "$msg"; continue; }
      else
        case "$(cat "$t/rout")" in
          "NO-GO: gates — "?*) ;;
          *) printf '%s: stdout is [%s], want NO-GO: gates — ...\n' "$cid" "$(cat "$t/rout")"; continue ;;
        esac
      fi
      if [ "$cid" = f-past-100 ]; then
        calls=$(awk 'END{print NR}' "$t/gh.log")
        [ "$calls" -le 100 ] || { printf '%s: %s gh calls, want at most 100 (one per commit)\n' "$cid" "$calls"; continue; }
      fi
    fi
  done
}

# GITHUB_STEP_SUMMARY is optional: one run without it
d=$t/case/f-nearest/repo
cdir=$t/case/f-nearest
: > "$t/gh.log"
(
  cd "$d" &&
  env -i PATH="$t/bin:$PATH" HOME="$t" GITHUB_REPOSITORY=o/r GITHUB_OUTPUT="$t/gho-nosum" \
    GH_DIR="$cdir/gh" GH_LOG="$t/gh.log" sh "$repo/.github/range.sh"
) >"$t/rout" 2>"$t/rerr" && rrc=0 || rrc=$?
{ [ "$rrc" -eq 0 ] && [ "$(sed -n 's/^base=//p' "$t/gho-nosum" 2>/dev/null)" = "$(git -C "$d" rev-parse r5)" ]; } \
  || fail_case a-no-summary "GITHUB_STEP_SUMMARY unset: exit $rrc: $(tr '\n' '|' <"$t/rerr")"

# (a) and (b) against the real script
out=$(check_range "$repo/.github/range.sh")
if [ -n "$out" ]; then
  printf '%s\n' "$out" >&2
  fail_case ab-range "$(printf '%s\n' "$out" | awk 'END{print NR}') case(s) of .github/range.sh failed, first: $(printf '%s\n' "$out" | sed -n 1p)"
fi

# (d) the same cases against stand-ins that must fail them
cat > "$t/naive.sh" <<'S'
printf 'base=%s\n' "$(git rev-parse HEAD^1)" >> "$GITHUB_OUTPUT"
printf 'judged=\n' >> "$GITHUB_OUTPUT"
S
cat > "$t/refuse.sh" <<'S'
printf 'NO-GO: gates — refused\n'
exit 1
S
cat > "$t/gh-blind.sh" <<'S'
# takes the first first-parent ancestor with any check, red or not
for c in $(git rev-list --first-parent HEAD^1); do
  n=$(gh api "repos/$GITHUB_REPOSITORY/commits/$c/check-runs?check_name=lights-out%20gates&filter=all&per_page=100" | jq '.total_count')
  if [ "$n" -gt 0 ]; then
    printf 'base=%s\njudged=\n' "$c" >> "$GITHUB_OUTPUT"
    exit 0
  fi
done
exit 1
S
for broken in naive refuse gh-blind; do
  [ -n "$(check_range "$t/$broken.sh")" ] || fail_case d-range "the cases of (a) and (b) accepted a stand-in that is $broken"
done

# ------------------------------------------------------- mutation fixtures
# The gate runs from a directory of its own (it writes .crew/ under the
# current directory) that sees this repository's gate, lib, policy and core.
lo=$t/lo
mkdir -p "$lo"
for x in ci core policy gates; do ln -s "$repo/$x" "$lo/$x"; done

w=$t/wl
mkdir -p "$w/pkg"
git init -q "$w"
git -C "$w" symbolic-ref HEAD refs/heads/main
wg() { git -C "$w" "$@"; }
setline() {  # N TEXT
  awk -v n="$1" -v s="$2" 'NR==n{print s; next} {print}' "$w/pkg/m.py" > "$w/pkg/m.py.new"
  mv "$w/pkg/m.py.new" "$w/pkg/m.py"
}
wc_commit() {
  wg add -A
  wg commit -q -m "$1"
  wg tag "$1"
}
i=1
while [ "$i" -le 30 ]; do
  printf 'l%02d = 1\n' "$i"
  i=$((i + 1))
done > "$w/pkg/m.py"
wc_commit B0
setline 2 'main_change = 1'
wc_commit M1
# S: two hunks and an appended line, off B0; merged into M1 clean (MG) and
# with a resolution line of the merge's own (MGR)
wg checkout -q -b br-s B0
setline 18 'side18 = 1'
setline 22 'side22 = 1'
printf 'side_tail = 1\n' >> "$w/pkg/m.py"
wc_commit S
wg checkout -q -b br-mg M1
wg merge -q --no-ff -m MG S >&2
wg tag MG
wg checkout -q -b br-mgr M1
wg merge -q --no-ff --no-commit S >&2
printf 'resolved = 1\n' >> "$w/pkg/m.py"
wc_commit MGR
# X: never merged
wg checkout -q -b br-x B0
setline 10 'orphan10 = 1'
wc_commit X
# two sides off B0, merged one after the other into M1, the second with a resolution line
wg checkout -q -b br-sa B0
setline 5 'sidea5 = 1'
wc_commit SA
wg checkout -q -b br-sb B0
setline 25 'sideb25 = 1'
wc_commit SB
wg checkout -q -b br-ma M1
wg merge -q --no-ff -m MA SA >&2
wg tag MA
wg checkout -q -b br-mb MA
wg merge -q --no-ff --no-commit SB >&2
printf 'resolved2 = 1\n' >> "$w/pkg/m.py"
wc_commit MB

# shellcheck disable=SC2016 # the $ is the command's, expanded when it runs
fake_cmd="printf '%s' \"\$MUTATION_LINES\" > '$t/lines'; echo '{\"total\":1,\"killed\":1,\"survived\":0,\"score\":1.0}'"
# mut_run GATE BASE HEAD [JUDGED=...]: stdout $t/mout, stderr $t/merr, exit $mrc, MUTATION_LINES $t/lines
mut_run() {
  gate=$1
  mb=$2
  mh=$3
  shift 3
  rm -f "$t/lines"
  rm -rf "$t/gout"
  (
    cd "$lo" &&
    env -i PATH="$PATH" HOME="$t" WORKLOAD="$w" WORKLOAD_CONTRACT="$repo/.lights-out" \
      WORKLOAD_MUTATION_SCOPE=pkg WORKLOAD_TEST_ROOT= TOOLCHAIN_IMAGE=workbench GATES_OUT="$t/gout" \
      MUTATION_CMD="$fake_cmd" BASE="$(wg rev-parse "$mb")" HEAD="$(wg rev-parse "$mh")" "$@" sh "$gate"
  ) >"$t/mout" 2>"$t/merr" && mrc=0 || mrc=$?
}
one_line() {  # a flaw if stdout is not one line
  [ "$(awk 'END{print NR}' "$t/mout")" -eq 1 ] \
    || printf 'stdout has %s lines, want 1: %s' "$(awk 'END{print NR}' "$t/mout")" "$(tr '\n' '|' <"$t/mout")"
}
# judged_line N TREE...: a flaw unless stdout is GO: mutation — in workbench, N lines judged at <short of each TREE>
judged_line() {
  want_n=$1
  shift
  one_line
  got=$(sed -n 's/^GO: mutation — in workbench, \([0-9][0-9]*\) lines judged at \([0-9a-f ]*\)$/\1 \2/p' "$t/mout")
  [ -n "$got" ] || { printf 'stdout is [%s], want GO: mutation — in workbench, %s lines judged at <short shas>' "$(cat "$t/mout")" "$want_n"; return; }
  [ "${got%% *}" = "$want_n" ] || { printf 'the GO line says %s lines judged, want %s: %s' "${got%% *}" "$want_n" "$(cat "$t/mout")"; return; }
  toks=${got#* }
  # shellcheck disable=SC2086 # word splitting is the point
  ntok=$(printf '%s\n' $toks | awk 'END{print NR}')
  [ "$ntok" -eq "$#" ] || { printf 'the GO line names %s shas, want %s: %s' "$ntok" "$#" "$(cat "$t/mout")"; return; }
  for tree in "$@"; do
    full=$(wg rev-parse "$tree^{commit}")
    ok=""
    for tok in $toks; do
      [ "${#tok}" -ge 7 ] || continue
      case "$full" in "$tok"*) ok=1 ;; esac
    done
    [ -n "$ok" ] || { printf 'the GO line does not name %s (%s) by a short sha: %s' "$tree" "$full" "$(cat "$t/mout")"; return; }
  done
}

# mut_flaws GATE: the first flaw of GATE against the cases of (c), or nothing
mut_flaws() {
  gate=$1
  # empty or unset JUDGED: today's lines, today's line
  for form in unset empty; do
    if [ "$form" = unset ]; then mut_run "$gate" M1 MGR; else mut_run "$gate" M1 MGR JUDGED=; fi
    [ "$mrc" -eq 0 ] || { printf 'JUDGED %s: exit %s: %s' "$form" "$mrc" "$(tr '\n' '|' <"$t/merr")"; return; }
    [ "$(cat "$t/lines" 2>/dev/null)" = "pkg/m.py=18-18,22-22,31-32" ] \
      || { printf 'JUDGED %s: MUTATION_LINES is [%s], want pkg/m.py=18-18,22-22,31-32' "$form" "$(cat "$t/lines" 2>/dev/null)"; return; }
    [ "$(cat "$t/mout")" = "GO: mutation — in workbench" ] \
      || { printf 'JUDGED %s: stdout is [%s], want GO: mutation — in workbench' "$form" "$(cat "$t/mout")"; return; }
  done
  # a judged side: its lines are not mutated, the merge's own line is
  mut_run "$gate" M1 MGR JUDGED="$(wg rev-parse S)"
  [ "$mrc" -eq 0 ] || { printf 'JUDGED=S: exit %s: %s' "$mrc" "$(tr '\n' '|' <"$t/merr")"; return; }
  [ "$(cat "$t/lines" 2>/dev/null)" = "pkg/m.py=32-32" ] \
    || { printf 'JUDGED=S on a merge with a resolution line: MUTATION_LINES is [%s], want pkg/m.py=32-32' "$(cat "$t/lines" 2>/dev/null)"; return; }
  flaw=$(judged_line 3 S)
  [ -z "$flaw" ] || { printf 'JUDGED=S: %s' "$flaw"; return; }
  # two trees: only what neither judged
  mut_run "$gate" M1 MB JUDGED="$(wg rev-parse SA) $(wg rev-parse SB)"
  [ "$mrc" -eq 0 ] || { printf 'JUDGED=SA SB: exit %s: %s' "$mrc" "$(tr '\n' '|' <"$t/merr")"; return; }
  [ "$(cat "$t/lines" 2>/dev/null)" = "pkg/m.py=31-31" ] \
    || { printf 'JUDGED=SA SB: MUTATION_LINES is [%s], want pkg/m.py=31-31' "$(cat "$t/lines" 2>/dev/null)"; return; }
  flaw=$(judged_line 2 SA SB)
  [ -z "$flaw" ] || { printf 'JUDGED=SA SB: %s' "$flaw"; return; }
  # everything judged: the command does not run, GO
  mut_run "$gate" M1 MG JUDGED="$(wg rev-parse S)"
  [ "$mrc" -eq 0 ] || { printf 'JUDGED=S on a clean merge: exit %s, want 0: %s' "$mrc" "$(tr '\n' '|' <"$t/merr")"; return; }
  [ ! -e "$t/lines" ] || { printf 'JUDGED=S on a clean merge: MUTATION_CMD ran with [%s]; every line was judged' "$(cat "$t/lines")"; return; }
  flaw=$(one_line)
  [ -z "$flaw" ] || { printf 'JUDGED=S on a clean merge: %s' "$flaw"; return; }
  case "$(cat "$t/mout")" in
    "GO: mutation — "?*) ;;
    *) printf 'JUDGED=S on a clean merge: stdout is [%s], want GO: mutation — ...' "$(cat "$t/mout")"; return ;;
  esac
  # a JUDGED that is no commit, or no ancestor of HEAD: one NO-GO line
  blob=$(wg rev-parse B0:pkg/m.py)
  for bad in "0000000000000000000000000000000000000000" nonsense "$blob" "$(wg rev-parse X)" \
    "$(wg rev-parse S) $(wg rev-parse X)" "$(wg rev-parse S) nonsense"; do
    mut_run "$gate" M1 MGR JUDGED="$bad"
    [ "$mrc" -eq 1 ] || { printf 'JUDGED=[%s]: exit %s, want 1' "$bad" "$mrc"; return; }
    [ ! -e "$t/lines" ] || { printf 'JUDGED=[%s]: MUTATION_CMD ran' "$bad"; return; }
    flaw=$(one_line)
    [ -z "$flaw" ] || { printf 'JUDGED=[%s]: %s' "$bad" "$flaw"; return; }
    case "$(cat "$t/mout")" in
      "NO-GO: mutation — "?*) ;;
      *) printf 'JUDGED=[%s]: stdout is [%s], want NO-GO: mutation — ...' "$bad" "$(cat "$t/mout")"; return ;;
    esac
  done
}

flaw=$(mut_flaws "$repo/gates/mutation.sh")
[ -z "$flaw" ] || fail_case c-mutation "$flaw"

# (d) stand-ins for the gate that must fail (c)
awk '{print} /^set -eu$/ && !d {print "unset JUDGED"; d=1}' gates/mutation.sh > "$t/blind-mutation.sh"
cat > "$t/always-go.sh" <<'S'
printf 'GO: mutation\n'
S
for broken in blind-mutation always-go; do
  [ -n "$(mut_flaws "$t/$broken.sh")" ] || fail_case d-mutation "the cases of (c) accepted a gate that is $broken"
done

[ -z "$mismatch" ] || nogo "case $mismatch failed; see stderr"

go
