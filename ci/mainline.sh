#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-mainline: proves docs/adr/0056 on the real steps, cold: no plane, no
# engine. The real core/tower.sh drives the real core/steps/merge.sh and
# core/steps/mainline.sh over a temp root: stub StateStore, EventBus,
# CodeHost and Tracker verbs, a bare repository as the code host, and a
# stub workload whose `gates` target is a script. The stub judge calls a
# tree red when a `call NAME` line under src/ has no `def NAME` line, so
# two diffs that each pass alone can fail together, and the verdict is a
# function of the tree. The other three steps (assign, rework, release) are
# stubs: ADR 0056 §5 is about the tower refusing them, not about what they
# do. core/tests/test_mainline.py holds the rest of §7's cases, in process,
# because the self gate measures core/ with the unit suite alone; this
# gate keeps the shell seam honest (the step scripts, the transition
# table, the refusal). Written from the ADR, not from the scripts.
set -eu
name=mainline
. ci/lib.sh

for f in core/mainline.py core/tower.sh core/steps/merge.sh core/steps/mainline.sh policy/mainline.env; do
  [ -f "$f" ] || nogo "$f not found"
done
for tool in git jq make python3; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool is not installed"
done

repo=$(pwd)
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/home" "$root/steps" "$root/template" "$root/adapters/stub-state" "$root/adapters/stub-bus" \
  "$root/adapters/stub-tracker" "$root/adapters/stub-codehost"
ln -s "$repo/core" "$root/core"
ln -s "$repo/policy" "$root/policy"

# Nothing of the machine's git configuration reaches the steps, and no
# identity is guessed: a commit the tower makes must name its own author.
export HOME="$root/home" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=user.useConfigOnly GIT_CONFIG_VALUE_0=true
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL EMAIL

# --- stub StateStore, EventBus, Tracker ---
cat > "$root/adapters/stub-state/get.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
f="$d/state/$1.$2.json"
[ -f "$f" ] || exit 1
cat "$f"
STUB
cat > "$root/adapters/stub-state/put.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
jq -c . > "$d/state/$1.$2.json"
STUB
cat > "$root/adapters/stub-bus/publish.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
printf '%s\n' "$1" >> "$d/bus.log"
STUB
cat > "$root/adapters/stub-tracker/get.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
f="$d/tickets/$1.md"
[ -f "$f" ] || exit 1
cat "$f"
STUB

# --- stub CodeHost: the Gitea verbs' contracts over a bare repository ---
# push forces HEAD to the branch; open-pr refuses a pr.json with no title and
# prints "<number> <url>"; merge makes a merge commit while the PR's head is
# the one given, and prints "<merge sha> <head sha>" again for a PR already
# merged. A PR is a directory under world/ (branch, head, merge_sha).
cat > "$root/adapters/stub-codehost/clone-url.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
printf '%s\n' "$d/host.git"
STUB
cat > "$root/adapters/stub-codehost/push.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
git -C "$1" push -q --force "$d/host.git" "HEAD:refs/heads/$2" >&2
STUB
cat > "$root/adapters/stub-codehost/open-pr.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
[ -s "$2" ] || { printf 'stub-codehost: %s is missing or empty\n' "$2" >&2; exit 1; }
[ -n "$(jq -r '.title // ""' "$2")" ] || { printf 'stub-codehost: %s has no title\n' "$2" >&2; exit 1; }
tip=$(git -C "$d/host.git" rev-parse --verify -q "refs/heads/$1") \
  || { printf 'stub-codehost: no branch %s\n' "$1" >&2; exit 1; }
n=$(cat "$d/world/.seq" 2>/dev/null || printf 100)
n=$((n + 1))
printf '%s' "$n" > "$d/world/.seq"
mkdir -p "$d/world/pr-$n"
printf '%s\n' "$1" > "$d/world/pr-$n/branch"
printf '%s\n' "$tip" > "$d/world/pr-$n/head"
printf '%s %s\n' "$1" "$(jq -r .title "$2")" >> "$d/prs.log"
printf '%s stub://pr/%s\n' "$n" "$n"
STUB
cat > "$root/adapters/stub-codehost/merge.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
p="$d/world/pr-$1"
[ -d "$p" ] || { printf 'stub-codehost: no PR #%s\n' "$1" >&2; exit 1; }
if [ ! -f "$p/merge_sha" ]; then
  branch=$(cat "$p/branch")
  tip=$(git -C "$d/host.git" rev-parse "refs/heads/$branch")
  [ "$tip" = "$2" ] || { printf 'stub-codehost: PR #%s head is %s, not %s\n' "$1" "$tip" "$2" >&2; exit 1; }
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  git clone -q "$d/host.git" "$tmp/m" 2>/dev/null
  git -C "$tmp/m" -c user.name=host -c user.email=host@lights-out.invalid -c commit.gpgsign=false \
    merge -q --no-ff -m "Merge PR #$1" "origin/$branch" >/dev/null 2>&1 \
    || { printf 'stub-codehost: PR #%s does not merge\n' "$1" >&2; exit 1; }
  git -C "$tmp/m" push -q origin HEAD:refs/heads/main 2>/dev/null
  git -C "$tmp/m" rev-parse HEAD > "$p/merge_sha"
  printf 'merge performed %s\n' "$1" >> "$d/effects.log"
fi
printf '%s %s\n' "$(cat "$p/merge_sha")" "$(cat "$p/head")"
STUB

# --- the three steps that are not under test: stubs that log themselves ---
for s in assign rework release; do
  cat > "$root/steps/$s.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
basename "$0" .sh >> "$d/effects.log"
printf '%s\n' '{"state":"held"}'
STUB
done
ln -s "$repo/core/steps/merge.sh" "$root/steps/merge.sh"
ln -s "$repo/core/steps/mainline.sh" "$root/steps/mainline.sh"

# --- the repository every world starts from: a root commit and a base ---
src="$root/template/src"
mkdir -p "$src/gates" "$src/src" "$src/docs"
cat > "$src/Makefile" <<'FILE'
GATES ?= sast test
GATES_OUT ?= .gates-out
.PHONY: gates
gates: ; @sh gates/run.sh "$(BASE)" "$(HEAD)" "$(GATES)" "$(GATES_OUT)"
FILE
cat > "$src/gates/run.sh" <<'FILE'
set -eu
base=$1 head=$2 gates=$3 out=$4
mkdir -p "$out"
printf '%s %s %s\n' "$base" "$head" "$gates" >> "$RUNS_LOG"
defs=$(cat src/*.txt | sed -n 's/^def //p' | tr '\n' ' ')
bad=""
: > "$out/test.details"
for name in $(cat src/*.txt | sed -n 's/^call //p'); do
  case " $defs " in
    *" $name "*) ;;
    *) bad="$bad $name"; printf 'undefined call: %s\n' "$name" >> "$out/test.details" ;;
  esac
done
if [ -n "$bad" ]; then
  printf 'GATES=NO-GO\nFAILED=test\n' > "$out/verdict.env"
  printf 'NO-GO: gates — test: undefined call(s)%s in %s\n' "$bad" "$head"
  exit 0
fi
printf 'GATES=GO\n' > "$out/verdict.env"
printf 'GO: gates\n'
FILE
printf 'def foo\n' > "$src/src/lib.txt"
printf '# callers\n' > "$src/src/use.txt"
for x in a b c d e; do
  printf '%s1\n%s2\n%s3\n%s4\n%s5\n' "$x" "$x" "$x" "$x" "$x" > "$src/src/$x.txt"
done
printf 'notes\n' > "$src/docs/notes.txt"
tmpl() { git -C "$src" -c user.name=ci -c user.email=ci@lights-out.invalid -c commit.gpgsign=false "$@"; }
if ! { git init -q -b main "$src" && tmpl add -A && tmpl commit -q -m initial \
  && printf 'base\n' >> "$src/docs/notes.txt" && tmpl commit -q -a -m base \
  && git clone -q --bare "$src" "$root/template/host.git"; }; then
  nogo "could not build the template repository"
fi

cd "$root"
export STATE_STORE=stub-state EVENT_BUS=stub-bus CODE_HOST=stub-codehost TRACKER=stub-tracker \
  WORKLOAD=work WORKLOAD_CONTRACT=work WORKLOAD_ATTACHED='' TOWER_STEPS="$root/steps" RUNS_LOG="$root/runs.log"

log="$root/run.log"
mismatch=""
fail_case() {
  [ -z "$mismatch" ] || return 0
  mismatch="$1"; printf 'ci-mainline: %s: %s\n' "$1" "$2" >&2; cat "$log" >&2
}
must() { "$@" || nogo "setup failed: $*"; }

# --- the world: the code host, an author's clone, the workload's clone ---
au() { git -C author -c user.name=author -c user.email=author@lights-out.invalid -c commit.gpgsign=false "$@"; }
hostref() { git -C host.git rev-parse --verify -q "$1" 2>/dev/null || :; }
world() {
  rm -rf host.git author work state world tickets bus.log runs.log effects.log prs.log
  mkdir state world tickets
  : > runs.log; : > effects.log; : > prs.log
  cp -R template/host.git host.git && git clone -q host.git author && git clone -q host.git work || return 1
  base=$(hostref refs/heads/main)
}
append() { mkdir -p "$(dirname "$1")" && printf '%s\n' "$2" >> "$1"; }  # FILE LINE, in the author's checkout
edit_first() { { printf '%s\n' "$2"; tail -n +2 "$1"; } > "$1.new" && mv "$1.new" "$1"; }
rename_foo() { sed 's/^def foo$/def bar/' src/lib.txt > src/lib.new && mv src/lib.new src/lib.txt; }
edit_kept() { sed 's/^# kept$/# kept (edited by hand)/' src/use.txt > src/use.new && mv src/use.new src/use.txt; }
drop_call() { sed '/^call foo$/d' src/use.txt > src/use.new && mv src/use.new src/use.txt; }
sync() { au fetch -q origin && au checkout -q -f -B main origin/main; }
outside() {  # CMD...: a commit on main made by a person, with no ticket
  sync && ( cd author && "$@" ) && au add -A && au commit -q --allow-empty -m outside \
    && au push -q origin HEAD:refs/heads/main
}
propose() {  # N FILE CMD...: ticket N holds FILE; its PR is two commits off the base; CI passed it
  n=$1; file=$2; shift 2
  id=$(printf '%04d' "$n")
  # shellcheck disable=SC2016 # the backticks are the ticket's markdown, not a command substitution
  printf '# %s - stub ticket\n\n## Perimeter\n\n- `%s`\n' "$id" "$file" > "tickets/$id.md" || return 1
  au checkout -q -f -B "ticket/$id" "$base" && ( cd author && "$@" ) && au add -A \
    && au commit -q -m "ticket $id" || return 1
  ( cd author && append "$file" "# $id follow-up" ) && au commit -q -a -m "ticket $id: follow-up" \
    && au push -q -f origin "HEAD:refs/heads/ticket/$id" || return 1
  head=$(au rev-parse HEAD)
  mkdir "world/pr-$n" && printf 'ticket/%s\n' "$id" > "world/pr-$n/branch" && printf '%s\n' "$head" > "world/pr-$n/head" || return 1
  jq -cn --arg id "$id" --argjson n "$n" --arg b "$base" --arg h "$head" \
    '{id: $id, state: "ci-passed", attempt: 1, history: [], pr: {number: $n, base_sha: $b, head_sha: $h},
      ci: {verdict: "GO", risk_level: "low", decision: "auto-merge", head_sha: $h}}' \
    | sh adapters/stub-state/put.sh tickets "$id"
}
seed() {  # N STATE: a ticket document the tower can act on
  jq -cn --arg id "$(printf '%04d' "$1")" --arg s "$2" '{id: $id, state: $s, attempt: 1, history: []}' \
    | sh adapters/stub-state/put.sh tickets "$(printf '%04d' "$1")"
}

# --- the real tower, and what it left behind ---
step() { rc=0; sh core/tower.sh step "$(printf '%04d' "$1")" "$2" >/dev/null 2>"$log" || rc=$?; }  # N STEP
dget() { jq -r "$2" "state/tickets.$(printf '%04d' "$1").json" 2>/dev/null || :; }  # N JQ
mget() { jq -r "$1" state/mainline.main.json 2>/dev/null || :; }  # JQ
lastbus() { tail -n 1 bus.log 2>/dev/null | jq -r .step 2>/dev/null || :; }
nruns() { wc -l < runs.log | tr -d ' '; }
merged() { [ -f "world/pr-$1/merge_sha" ]; }  # N: did the code host merge PR N
effect() { grep -cx "$1" effects.log 2>/dev/null || :; }  # NAME: how many times
short() { printf '%s' "$1" | cut -c1-7; }

# (a) the golden path: a merge onto an unmoved main is green after a fetch,
# not a gate run (the ./go demo ticket); the table is merge -> mainline ->
# release, and the ticket carries the green commit it ships.
world || fail_case a-setup "could not build the world"
if [ -z "$mismatch" ]; then
  must propose 1 src/a.txt append src/a.txt a6
  step 1 merge
  [ "$rc" = 0 ] || fail_case a-merge "merge exited $rc"
  [ "$(dget 1 .state)" = merged ] || fail_case a-merge "state $(dget 1 .state), want merged"
  [ "$(lastbus)" = mainline ] || fail_case a-merge "merge requested '$(lastbus)', want mainline"
  step 1 mainline
  [ "$rc" = 0 ] || fail_case a-mainline "mainline exited $rc"
  m1=$(dget 1 .merge.sha)
  [ "$(dget 1 .state)" = main-green ] || fail_case a-mainline "state $(dget 1 .state), want main-green"
  [ "$(dget 1 .mainline.green)" = "$m1" ] || fail_case a-mainline "mainline.green $(dget 1 .mainline.green), want the merge $m1"
  [ "$(lastbus)" = release ] || fail_case a-mainline "mainline requested '$(lastbus)', want release"
  [ "$(nruns)" = 0 ] || fail_case a-gates "$(nruns) gate run(s) for a merge whose tree CI judged, want 0"
  [ "$(mget .state)" = green ] && [ "$(mget .green)" = "$m1" ] && [ "$(mget .green)" = "$(hostref refs/heads/main)" ] \
    || fail_case a-document "mainline/main is $(jq -c . state/mainline.main.json 2>/dev/null)"
fi

# (b) main moved outside the perimeter: merged onto the moved main, no gate
# run at merge; the main check then judges the result, once, for both.
if [ -z "$mismatch" ]; then
  world || fail_case b-setup "could not build the world"
  must propose 1 src/a.txt append src/a.txt a6
  must propose 2 src/b.txt append src/b.txt b6
  step 1 merge
  must outside edit_first src/e.txt "e1 by hand"
  by_hand=$(hostref refs/heads/main)
  step 2 merge
  [ "$rc" = 0 ] || fail_case b-merge "merge exited $rc"
  [ "$(dget 2 .state)" = merged ] || fail_case b-merge "state $(dget 2 .state), want merged"
  [ "$(hostref refs/heads/main^1)" = "$by_hand" ] || fail_case b-merge "the host did not merge onto the moved main"
  [ "$(nruns)" = 0 ] || fail_case b-merge "a gate ran at merge time"
  step 1 mainline
  [ "$rc" = 0 ] || fail_case b-mainline "mainline exited $rc"
  [ "$(nruns)" = 1 ] || fail_case b-mainline "$(nruns) gate runs for one group, want 1"
  [ "$(awk '{print $1 " " $2 " " $3 " " $4}' runs.log)" = "$base $(dget 2 .merge.sha) sast test" ] \
    || fail_case b-mainline "the run was: $(cat runs.log) (want the tree gates at the group's newest commit, against the base)"
  step 2 mainline
  [ "$(dget 1 .state) $(dget 2 .state)" = "main-green main-green" ] || fail_case b-mainline "states $(dget 1 .state) $(dget 2 .state)"
  [ "$(nruns)" = 1 ] || fail_case b-mainline "the second ticket paid for a gate run"
fi

# (c) main moved under the perimeter: ci-failed, judge base, the line names
# the path and the commit, the host did not merge, rework is requested.
if [ -z "$mismatch" ]; then
  world || fail_case c-setup "could not build the world"
  must propose 1 src/a.txt append src/a.txt a6
  must outside edit_first src/a.txt "a1 by hand"
  by_hand=$(hostref refs/heads/main)
  step 1 merge
  [ "$rc" = 0 ] || fail_case c "merge exited $rc"
  [ "$(dget 1 .state)" = ci-failed ] || fail_case c "state $(dget 1 .state), want ci-failed"
  [ "$(dget 1 .mainline.verdict) $(dget 1 .mainline.judge)" = "NO-GO base" ] \
    || fail_case c "mainline: $(dget 1 .mainline)"
  [ "$(dget 1 .mainline.head_sha)" = "$(dget 1 .ci.head_sha)" ] || fail_case c "mainline.head_sha is not the head CI judged"
  line=$(dget 1 .mainline.line)
  printf '%s\n' "$line" | grep -Eq "^NO-GO: base — main moved under the perimeter since $(short "$base")[0-9a-f]*: src/a\.txt by $(short "$by_hand")[0-9a-f]*$" \
    || fail_case c "line: $line"
  merged 1 && fail_case c "the code host merged the PR"
  [ "$(hostref refs/heads/main)" = "$by_hand" ] || fail_case c "main moved"
  [ "$(effect 'merge performed 1')" = 0 ] || fail_case c "merge.sh of the adapter ran"
  [ "$(lastbus)" = rework ] || fail_case c "requested '$(lastbus)', want rework"
  [ "$(nruns)" = 0 ] || fail_case c "a gate ran"
fi

# (d) the base was rewritten away: the step fails, nothing is merged.
if [ -z "$mismatch" ]; then
  world || fail_case d-setup "could not build the world"
  must propose 1 src/a.txt append src/a.txt a6
  must sync
  must au commit -q --amend --allow-empty -m "history rewritten"
  must au push -q -f origin HEAD:refs/heads/main
  step 1 merge
  [ "$rc" = 1 ] || fail_case d "merge exited $rc, want 1"
  [ "$(dget 1 .state)" = ci-passed ] || fail_case d "state $(dget 1 .state), want ci-passed"
  [ "$(dget 1 '.history[-1].error')" = "step exited 1" ] || fail_case d "no failed attempt recorded"
  merged 1 && fail_case d "the code host merged the PR"
  [ "$(effect 'merge performed 1')" = 0 ] || fail_case d "merge.sh of the adapter ran"
fi

# (e) a red group: three tickets merged without a second judgment, the
# second calls what the first renamed, the third is innocent and merges
# after it. The main check judges the group once, bisects it (the culprit is
# not the newest commit), reverts the culprit's merge through the code host,
# and main is green again with the innocent ticket still on it; the
# culprit's ticket is sent back with the verdict, the others are main-green
# and ship a commit that was judged.
if [ -z "$mismatch" ]; then
  world || fail_case e-setup "could not build the world"
  must propose 1 src/lib.txt rename_foo
  must propose 2 src/use.txt append src/use.txt "call foo"
  must propose 3 src/b.txt append src/b.txt b6
  for n in 1 2 3; do step "$n" merge; [ "$rc" = 0 ] || fail_case e-merge "merge of $n exited $rc"; done
  bad=$(dget 2 .merge.sha); last=$(dget 3 .merge.sha)
  bad12=$(printf '%s' "$bad" | cut -c1-12)
  step 1 mainline
  [ "$rc" = 0 ] || fail_case e-mainline "mainline exited $rc"
  head=$(hostref refs/heads/main)
  [ "$head" != "$last" ] || fail_case e-revert "main did not move: nothing was reverted"
  [ -n "$(hostref "refs/heads/revert/$bad12")" ] || fail_case e-revert "no branch revert/<12 of the culprit>"
  [ "$(hostref "refs/heads/revert/$bad12^")" = "$last" ] || fail_case e-revert "the revert branch does not start at main's head"
  git -C host.git merge-base --is-ancestor "$bad" "$head" || fail_case e-revert "the culprit left main's history: a force push"
  [ "$(effect 'merge performed 101')" = 1 ] || fail_case e-revert "the revert PR was not merged by the host"
  [ "$(wc -l < prs.log | tr -d ' ')" = 1 ] || fail_case e-revert "$(wc -l < prs.log | tr -d ' ') revert PRs opened, want 1"
  git -C host.git show refs/heads/main:src/use.txt | grep -q 'call foo' && fail_case e-revert "the call is still on main"
  git -C host.git show refs/heads/main:src/lib.txt | grep -q 'def bar' || fail_case e-revert "the rename was reverted with it"
  git -C host.git show refs/heads/main:src/b.txt | grep -q 'b6' || fail_case e-revert "the innocent ticket was reverted with it"
  [ "$(mget .state) $(mget .green) $(mget '.reverted | length') $(mget '.reverted[0].merge')" = "green $head 1 $bad" ] \
    || fail_case e-document "mainline/main is $(jq -c 'del(.at)' state/mainline.main.json 2>/dev/null)"
  [ "$(nruns)" -le 4 ] || fail_case e-gates "$(nruns) gate runs for three merges, a bisection and a revert (at most 4)"
  [ "$(dget 1 .state)" = main-green ] || fail_case e-ticket "ticket 1: $(dget 1 .state), want main-green"
  [ "$(lastbus)" = release ] || fail_case e-ticket "ticket 1's step requested '$(lastbus)', want release"
  green1=$(dget 1 .mainline.green)
  if [ "$green1" = "$bad" ] || [ "$green1" = "$last" ] || ! git -C host.git merge-base --is-ancestor "$green1" "$head"; then
    fail_case e-ticket "ticket 1 ships $green1, which is not a commit that was judged"
  fi
  step 2 mainline
  [ "$rc" = 0 ] || fail_case e-culprit "mainline of the culprit's ticket exited $rc"
  [ "$(dget 2 .state) $(dget 2 .mainline.verdict) $(dget 2 .mainline.judge)" = "ci-failed NO-GO main" ] \
    || fail_case e-culprit "ticket 2: $(dget 2 .state) $(dget 2 .mainline)"
  case "$(dget 2 .mainline.line)" in "NO-GO"*"$(short "$bad")"*) : ;; *) fail_case e-culprit "line: $(dget 2 .mainline.line)" ;; esac
  [ "$(lastbus)" = rework ] || fail_case e-culprit "requested '$(lastbus)', want rework"
  step 3 mainline
  [ "$(dget 3 .state)" = main-green ] || fail_case e-ticket "ticket 3: $(dget 3 .state), want main-green"
fi

# (f) a revert that does not apply: main stays red with the reason, the step
# fails, and the tower refuses assign, rework and release (not mainline, the
# step that lifts it) until a fix lands; then every step runs again.
if [ -z "$mismatch" ]; then
  world || fail_case f-setup "could not build the world"
  must propose 1 src/a.txt append src/a.txt a6
  step 1 merge
  must outside rename_foo
  must outside append src/use.txt "call foo"
  must outside append src/use.txt "# kept"
  must outside edit_kept
  stuck=$(hostref refs/heads/main)
  step 1 mainline
  [ "$rc" = 1 ] || fail_case f-mainline "mainline exited $rc, want 1"
  [ "$(dget 1 .state)" = merged ] || fail_case f-mainline "state $(dget 1 .state), want merged"
  [ "$(dget 1 '.history[-1].step') $(dget 1 '.history[-1].error')" = "mainline step exited 1" ] \
    || fail_case f-mainline "history: $(dget 1 '.history[-1]')"
  [ "$(mget .state) $(mget .green)" = "red $base" ] || fail_case f-document "mainline/main is $(jq -c . state/mainline.main.json 2>/dev/null)"
  [ "$(hostref refs/heads/main)" = "$stuck" ] || fail_case f-mainline "main moved"
  [ -z "$(git -C host.git for-each-ref refs/heads/revert)" ] || fail_case f-mainline "a revert branch was pushed"
  seed 7 main-green; seed 8 ci-failed
  sh core/tower.sh open 0009 >/dev/null 2>"$log" || fail_case f-open "open exited $?"
  for refused in "9 assign opened" "8 rework ci-failed" "7 release main-green"; do
    # shellcheck disable=SC2086 # three words
    set -- $refused
    step "$1" "$2"
    [ "$rc" = 1 ] || fail_case "f-$2" "$2 exited $rc on a red main, want 1"
    [ "$(dget "$1" .state)" = "$3" ] || fail_case "f-$2" "state moved to $(dget "$1" .state)"
    case "$(dget "$1" '.history[-1].error')" in "main is NO-GO since $base"*) : ;; *) fail_case "f-$2" "error: $(dget "$1" '.history[-1].error')" ;; esac
    [ "$(effect "$2")" = 0 ] || fail_case "f-$2" "the $2 step ran on a red main"
  done
  # A person fixes main; the stranded steps run.
  must outside drop_call
  fixed=$(hostref refs/heads/main)
  step 1 mainline
  [ "$rc" = 0 ] || fail_case f-fix "mainline exited $rc after the fix"
  [ "$(dget 1 .state) $(dget 1 .mainline.green)" = "main-green $fixed" ] \
    || fail_case f-fix "ticket 1: $(dget 1 .state) $(dget 1 .mainline.green), want main-green $fixed"
  [ "$(mget .state) $(mget .green)" = "green $fixed" ] || fail_case f-fix "mainline/main is $(jq -c . state/mainline.main.json 2>/dev/null)"
  for lifted in "9 assign" "8 rework" "7 release"; do
    # shellcheck disable=SC2086 # two words
    set -- $lifted
    step "$1" "$2"
    [ "$rc" = 0 ] || fail_case "f-$2-lifted" "$2 exited $rc on a green main"
    [ "$(effect "$2")" = 1 ] || fail_case "f-$2-lifted" "the $2 step did not run"
  done
fi

[ -z "$mismatch" ] || nogo "case $mismatch disagrees with docs/adr/0056"
go
