#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-codehost-conformance: the CodeHost port's conformance suite (docs/adr/
# 0043 §5, in the shape of docs/adr/0026 and 0041). Written from the ADR and
# the port's contract, never from an adapter. It drives whichever CODE_HOST
# is set, only through adapters/$CODE_HOST/*.sh, plus plain git for the
# commits it makes and for the clones it reads back. Ten cases, in this
# order, the first disagreement a NO-GO naming the case:
#   1 bootstrap, then its postcondition: the host's default branch is at the
#     workload's HEAD
#   2 clone-url.sh, a clone of it, and a .git/config with no credential
#   3 push.sh of conformance/<run id>, one commit adding one file
#   4 open-pr.sh twice, which must return the same PR number
#   5 status.sh pending, then a 200-character success, then await.sh -> success
#   6 pr.sh: open, not merged, the head as pushed, merge_sha null
#   7 a second commit is pushed; a merge at the old head must exit 1 and
#     leave the PR unmerged
#   8 a merge at the new head prints "<merge> <head>"; pr.sh agrees, and the
#     merge commit's second parent is that head (docs/adr/0019 §5)
#   9 the same merge again prints the same line
#  10 no secret appears in anything the suite captured from the adapters
#
# It writes to a real repository: a branch, a PR, a status and a merge commit
# that adds one file to the default branch. Point it at a throwaway one only;
# the nightly does (.github/workflows/nightly-github.yml). Cleanup is the
# suite's temporary directory and nothing else: no verb deletes a branch or
# closes a PR, and a merged PR cannot be deleted, so every run leaves its
# conformance/<run id> branch, its PR and its merge commit behind (a failed
# run leaves the PR open). The branch name is date and random, so runs never
# collide.
#
# Where it runs: ci.yml's `launch` job against Gitea with the plane up
# (CODE_HOST=gitea; Gitea's bootstrap pushes this checkout's HEAD to main),
# and the nightly against an attached throwaway repository on GitHub
# (CODE_HOST=github). A red nightly with a green launch points at the GitHub
# adapter, not the suite.
#
# Case 10 reads what the suite captured: the stdout and stderr of every verb
# and of every git command it ran. It looks for GITHUB_TOKEN when that is set,
# and for the Gitea adapter's password when CODE_HOST=gitea. That password is
# a published, low-entropy constant (adapters/gitea/env.sh); the case still
# proves that git's own output, which redacts the userinfo of a URL it prints,
# and the adapter's messages never carry it. Before it looks, the scan is
# shown to find a secret it is handed.
#
# The numbers are decisions of this suite, none a measurement: a branch on the
# host is awaited 60 s (30 polls, 2 s apart) before the second commit counts
# as pushed; a merge that the host does not accept at once is tried 3 times,
# 5 s apart, because a host computes mergeability after a push, and any other
# answer is final; await.sh gets 2 s for the pending status, which must not
# end it, and 60 s for the success. 200 characters is ADR 0043 §5's: longer
# than the 140 GitHub accepts (§3).
#
# Lives in gates/, so ci/contract.sh cold-runs it inside `make ci` with no
# CONFORMANCE set and no plane: the guard below must be the first thing that
# runs. `make codehost-conformance` is the only caller that sets
# CONFORMANCE=1; the acceptance commands are `./go codehost-conformance`
# (Gitea, plane up) and `./go codehost-conformance CODE_HOST=github`, never a
# bare `sh gates/...` (CLAUDE.md).
set -eu
name=codehost-conformance
. ci/lib.sh

# Instant NO-GO, before anything touches a host (docs/adr/0026 §4).
if [ "${CONFORMANCE:-}" != "1" ]; then
  nogo "set CONFORMANCE=1: this suite pushes a branch, opens a PR and merges it on the code host (./go codehost-conformance)"
fi

[ -n "${CODE_HOST:-}" ] || nogo "CODE_HOST is not set; a profile sets it: run this via ./go codehost-conformance"
ch=adapters/$CODE_HOST
for v in bootstrap clone-url push open-pr status await pr merge; do
  [ -f "$ch/$v.sh" ] || nogo "$ch/$v.sh is missing: a code host ships the eight verbs (docs/adr/0043 §5)"
done
[ -n "${WORKLOAD:-}" ] || nogo "WORKLOAD is not set; run this via ./go codehost-conformance"
for tool in git jq od date awk; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool is not on PATH; run this via ./go codehost-conformance"
done

# The secrets case 10 looks for.
gitea_password=""
if [ "$CODE_HOST" = gitea ]; then
  # shellcheck source=adapters/gitea/env.sh
  gitea_password=$(. adapters/gitea/env.sh; printf '%s' "$GITEA_PASSWORD") \
    || nogo "adapters/gitea/env.sh could not be read for the password case 10 looks for"
fi
[ -n "${GITHUB_TOKEN:-}" ] || [ -n "$gitea_password" ] \
  || nogo "CODE_HOST=$CODE_HOST: no secret is known for case 10 to look for (GITHUB_TOKEN is empty and the suite knows no password of this host); the case would prove nothing"

# A prompt would hang a CI job; an identity is needed for the commits only.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY
export GIT_TERMINAL_PROMPT=0
export GIT_AUTHOR_NAME=conformance GIT_AUTHOR_EMAIL=conformance@localhost GIT_COMMITTER_NAME=conformance GIT_COMMITTER_EMAIL=conformance@localhost

run_id=$(date -u +%Y%m%d-%H%M%S)-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')
branch=conformance/$run_id

work=$(mktemp -d)
# Never prints to stdout: the one line this gate owns is already out when it
# runs.
# shellcheck disable=SC2329 # invoked by name via `trap` below, not called directly
cleanup() {
  ec=$?
  rm -rf "$work"
  exit "$ec"
}
trap cleanup EXIT INT TERM

captured=$work/captured
: > "$captured"
clone=$work/clone

# ---------------------------------------------------------------------------
# Helpers. None of these may be called inside a $(...) capture: a nogo inside
# one would only exit the subshell the capture runs in (POSIX sh).
# ---------------------------------------------------------------------------

say() { printf '[codehost-conformance] %s\n' "$*" >&2; }

# run LABEL CMD...: CMD with no stdin, its stdout in the file $out and its
# stderr in $err, both appended to $captured (case 10 reads it) and the stderr
# shown, labelled. The exit code is in $rc; run itself never fails.
n=0
run() {
  label=$1
  shift
  n=$((n + 1))
  out=$work/out.$n
  err=$work/err.$n
  printf '%s %s\n' "$n" "$label" >> "$work/labels"
  if "$@" >"$out" 2>"$err" </dev/null; then rc=0; else rc=$?; fi
  cat "$out" "$err" >> "$captured"
  while IFS= read -r l || [ -n "$l" ]; do
    printf '  [%s] %s\n' "$label" "$l" >&2
  done < "$err"
}
verb() {  # VERB ARGS...: adapters/$CODE_HOST/VERB.sh
  verb_name=$1
  shift
  run "$verb_name" sh "$ch/$verb_name.sh" "$@"
}
# local_git ARGS...: git in the suite's clone, for the commits it makes. Its
# output is not an adapter's and is not captured; a failure is the suite's own.
local_git() {
  git -C "$clone" "$@" >/dev/null 2>"$work/local.err" \
    || nogo "git $* failed in the suite's own clone" "$(cat "$work/local.err")"
}
lines_of() { awk 'END{print NR}' "$1"; }

# leaked FILE: succeeds when FILE holds a secret.
leaked() {
  if [ -n "${GITHUB_TOKEN:-}" ] && grep -qF -- "$GITHUB_TOKEN" "$1"; then return 0; fi
  if [ -n "$gitea_password" ] && grep -qF -- "$gitea_password" "$1"; then return 0; fi
  return 1
}

# wait_pr_head NUMBER SHA: polls until the host reports SHA as the PR's head.
# A host updates it after a push, not during: a merge "at the old head" before
# that would be a merge at the head. pr.sh is the port's answer; the host's
# refs/pull/<n>/head (both GitHub and Gitea advertise it) is what a merge
# checks the sha against on Gitea and can lag behind pr.sh, so when the host
# shows one it must agree too. A host that shows none is not waited on.
wait_pr_head() {
  i=0
  while [ "$i" -lt 30 ]; do
    verb pr "$1"
    pr_head=""
    if [ "$rc" -eq 0 ]; then pr_head=$(jq -r '.head_sha // empty' "$out" 2>/dev/null) || pr_head=""; fi
    if [ "$pr_head" = "$2" ]; then
      run ls-remote git ls-remote "$url" "refs/pull/$1/head"
      pull_head=$(cut -f1 "$out" | head -n1)
      if [ -z "$pull_head" ] || [ "$pull_head" = "$2" ]; then return 0; fi
    fi
    i=$((i + 1))
    sleep 2
  done
  return 1
}

say "run $run_id on CODE_HOST=$CODE_HOST, branch $branch"

# ---------------------------------------------------------------------------
# Case 1: bootstrap, then its postcondition (docs/adr/0043 §3): afterwards the
# host's default branch is at the workload's HEAD, however it got there.
# ---------------------------------------------------------------------------
verb bootstrap
[ "$rc" -eq 0 ] || nogo "case1 bootstrap: adapters/$CODE_HOST/bootstrap.sh exited $rc"
workload_head=$(git -C "$WORKLOAD" rev-parse HEAD 2>/dev/null) \
  || nogo "case1 bootstrap: git -C $WORKLOAD rev-parse HEAD failed; WORKLOAD is not a repository"
verb clone-url
[ "$rc" -eq 0 ] && [ "$(lines_of "$out")" -eq 1 ] \
  || nogo "case1 bootstrap: clone-url.sh exited $rc and printed $(lines_of "$out") lines, want exit 0 and one line"
url=$(cat "$out")
run ls-remote git ls-remote "$url" HEAD
[ "$rc" -eq 0 ] || nogo "case1 bootstrap: git ls-remote of clone-url.sh's URL failed"
remote_head=$(cut -f1 "$out" | head -n1)
[ "$remote_head" = "$workload_head" ] \
  || nogo "case1 bootstrap: the host's default branch is at [$remote_head], the workload's HEAD is $workload_head"
say "case 1 bootstrap: GO"

# ---------------------------------------------------------------------------
# Case 2: the clone, and what it keeps in .git/config (docs/adr/0017 §4,
# 0043 §2): a URL, never a credential.
# ---------------------------------------------------------------------------
run clone git clone -q "$url" "$clone"
[ "$rc" -eq 0 ] || nogo "case2 clone: git clone of clone-url.sh's URL failed"
cfg=$clone/.git/config
if grep -qE '://[^/[:space:]]*@' "$cfg"; then
  nogo "case2 clone: the clone's .git/config holds a URL with user information in it"
fi
if leaked "$cfg" || grep -qiE 'extraheader|password|\[credential' "$cfg"; then
  nogo "case2 clone: the clone's .git/config holds a credential"
fi
base=$(git -C "$clone" symbolic-ref --short HEAD 2>/dev/null) \
  || nogo "case2 clone: the clone has no branch checked out; the host's default branch is not a branch"
say "case 2 clone-url and a clone without a credential: GO"

# ---------------------------------------------------------------------------
# Case 3: push conformance/<run id>, one commit adding one file.
# ---------------------------------------------------------------------------
file=conformance-$run_id.txt
local_git checkout -q -b "$branch"
printf 'conformance run %s, first commit\n' "$run_id" > "$clone/$file"
local_git add -- "$file"
local_git -c commit.gpgsign=false commit -q -m "conformance $run_id: first commit"
head1=$(git -C "$clone" rev-parse HEAD) || nogo "case3 push: git rev-parse HEAD failed in the suite's own clone"
verb push "$clone" "$branch"
[ "$rc" -eq 0 ] || nogo "case3 push: adapters/$CODE_HOST/push.sh exited $rc"
run ls-remote git ls-remote "$url" "refs/heads/$branch"
[ "$rc" -eq 0 ] && [ "$(cut -f1 "$out" | head -n1)" = "$head1" ] \
  || nogo "case3 push: $branch on the host is not at the pushed head $head1"
say "case 3 push: GO"

# ---------------------------------------------------------------------------
# Case 4: open-pr twice, the same PR.
# ---------------------------------------------------------------------------
printf '{"title":"conformance %s","body":"Opened by gates/codehost-conformance.sh on a throwaway repository; safe to ignore."}\n' "$run_id" > "$work/pr.json"
verb open-pr "$branch" "$work/pr.json"
[ "$rc" -eq 0 ] || nogo "case4 open-pr: exit $rc on the first call"
line1=$(cat "$out")
case "$line1" in
  [0-9]*' '?*) ;;
  *) nogo "case4 open-pr: stdout was [$line1], want '<number> <url>'" ;;
esac
number=${line1%% *}
case "$number" in
  *[!0-9]*) nogo "case4 open-pr: [$number] is not a PR number" ;;
esac
verb open-pr "$branch" "$work/pr.json"
[ "$rc" -eq 0 ] || nogo "case4 open-pr: exit $rc on the second call"
line2=$(cat "$out")
[ "${line2%% *}" = "$number" ] \
  || nogo "case4 open-pr: the second call returned [$line2], the first PR $number: a retried ticket would open a second PR"
say "case 4 open-pr is idempotent (PR #$number): GO"

# ---------------------------------------------------------------------------
# Case 5: statuses. A pending status is not an answer; a success is, and a
# description longer than GitHub accepts is the adapter's to cut (§3).
# ---------------------------------------------------------------------------
long=$(awk 'BEGIN{for (i = 0; i < 20; i++) printf "0123456789"}')
verb status "$head1" pending conformance "waiting for the suite"
[ "$rc" -eq 0 ] || nogo "case5 status: status.sh pending exited $rc"
run await env AWAIT_TIMEOUT=2 AWAIT_INTERVAL=1 sh "$ch/await.sh" "$head1" conformance
[ "$rc" -eq 1 ] || nogo "case5 await: await.sh exited $rc while the only status was pending, want it to wait and exit 1"
verb status "$head1" success conformance "$long"
[ "$rc" -eq 0 ] || nogo "case5 status: status.sh exited $rc on a 200-character success description"
run await env AWAIT_TIMEOUT=60 AWAIT_INTERVAL=2 sh "$ch/await.sh" "$head1" conformance
[ "$rc" -eq 0 ] && [ "$(cat "$out")" = success ] \
  || nogo "case5 await: after pending then success, await.sh exited $rc and printed [$(cat "$out")], want exit 0 and success"
say "case 5 status and await: GO"

# ---------------------------------------------------------------------------
# Case 6: the PR as the host sees it, before any merge (docs/adr/0019 §6).
# ---------------------------------------------------------------------------
verb pr "$number"
[ "$rc" -eq 0 ] || nogo "case6 pr: pr.sh exited $rc"
# shellcheck disable=SC2016 # the jq program is single-quoted on purpose; $n and $h are jq's
if ! jq -e --argjson n "$number" --arg h "$head1" \
    '(keys | sort) == ["head_sha","merge_sha","merged","number","state"]
     and .number == $n and .state == "open" and .merged == false and .head_sha == $h and .merge_sha == null' \
    "$out" >/dev/null 2>&1; then
  nogo "case6 pr: pr.sh printed [$(cat "$out")], want exactly number, state, merged, head_sha and merge_sha: PR $number open, not merged, head $head1, merge_sha null"
fi
say "case 6 pr before the merge: GO"

# ---------------------------------------------------------------------------
# Case 7: the head moves; a merge of the head CI judged is refused.
# ---------------------------------------------------------------------------
printf 'conformance run %s, second commit\n' "$run_id" >> "$clone/$file"
local_git add -- "$file"
local_git -c commit.gpgsign=false commit -q -m "conformance $run_id: second commit"
head2=$(git -C "$clone" rev-parse HEAD) || nogo "case7: git rev-parse HEAD failed in the suite's own clone"
[ "$head2" != "$head1" ] || nogo "case7: the second commit did not change the head"
verb push "$clone" "$branch"
[ "$rc" -eq 0 ] || nogo "case7 push: adapters/$CODE_HOST/push.sh exited $rc on the second commit"
wait_pr_head "$number" "$head2" \
  || nogo "case7 stale-merge: after 60 s the host still reports another head for PR $number than the pushed $head2"
verb merge "$number" "$head1"
[ "$rc" -eq 1 ] || nogo "case7 stale-merge: merge.sh at the old head $head1 exited $rc, want 1"
[ ! -s "$out" ] || nogo "case7 stale-merge: merge.sh refused the old head and still printed [$(cat "$out")] on stdout"
verb pr "$number"
# shellcheck disable=SC2016 # the jq program is single-quoted on purpose; $h is jq's
if [ "$rc" -ne 0 ] || ! jq -e --arg h "$head2" '.merged == false and .merge_sha == null and .head_sha == $h' "$out" >/dev/null 2>&1; then
  nogo "case7 stale-merge: after the refused merge pr.sh printed [$(cat "$out")], want the PR unmerged, merge_sha null, head $head2"
fi
say "case 7 a merge at a stale head is refused: GO"

# ---------------------------------------------------------------------------
# Case 8: the merge at the head CI judged. The host may need a moment after
# the push to compute mergeability: the verb's exit 1 is retried, 3 tries.
# ---------------------------------------------------------------------------
attempt=1
while :; do
  verb merge "$number" "$head2"
  [ "$rc" -ne 0 ] || break
  [ "$attempt" -lt 3 ] || nogo "case8 merge: merge.sh at the new head $head2 exited $rc after $attempt attempts"
  say "case 8 merge: exit $rc on attempt $attempt of 3, trying again in 5 s"
  attempt=$((attempt + 1))
  sleep 5
done
merge_line=$(cat "$out")
[ "$(lines_of "$out")" -eq 1 ] || nogo "case8 merge: merge.sh printed $(lines_of "$out") lines, want exactly '<merge> <head>'"
merge_sha=${merge_line%% *}
judged=${merge_line#* }
case "$merge_sha" in
  *[!0-9a-f]*) nogo "case8 merge: [$merge_sha] is not a commit id" ;;
esac
[ "${#merge_sha}" -eq 40 ] || nogo "case8 merge: [$merge_sha] is not a 40-character commit id"
[ "$judged" = "$head2" ] || nogo "case8 merge: merge.sh printed head [$judged], want the merged head $head2"
verb pr "$number"
# shellcheck disable=SC2016 # the jq program is single-quoted on purpose; $m and $h are jq's
if [ "$rc" -ne 0 ] || ! jq -e --arg m "$merge_sha" --arg h "$head2" '.merged == true and .merge_sha == $m and .head_sha == $h' "$out" >/dev/null 2>&1; then
  nogo "case8 merge: pr.sh printed [$(cat "$out")] after the merge, want merged, merge_sha $merge_sha, head $head2"
fi
run fetch git -C "$clone" fetch -q origin
[ "$rc" -eq 0 ] || nogo "case8 merge: git fetch origin failed after the merge"
parents=$(git -C "$clone" rev-list --parents -n 1 "$merge_sha" 2>/dev/null) \
  || nogo "case8 merge: the merge commit $merge_sha is not in a fetch of the host"
# shellcheck disable=SC2086 # word-splitting is deliberate: a commit and its parents
set -- $parents
[ "$#" -eq 3 ] || nogo "case8 merge: the merge commit $merge_sha has $(($# - 1)) parents, want 2: ADR 0019 §5 needs a merge commit, never a squash or a rebase"
[ "$3" = "$head2" ] || nogo "case8 merge: the merge commit's second parent is $3, want the judged head $head2 (docs/adr/0019 §5)"
git -C "$clone" merge-base --is-ancestor "$merge_sha" "origin/$base" \
  || nogo "case8 merge: the merge commit $merge_sha is not on origin/$base after the merge"
say "case 8 merge at the judged head (merge ${merge_sha}): GO"

# ---------------------------------------------------------------------------
# Case 9: the same merge again is the same answer, not an error (docs/adr/
# 0019 §9).
# ---------------------------------------------------------------------------
verb merge "$number" "$head2"
[ "$rc" -eq 0 ] || nogo "case9 re-merge: merge.sh on the merged PR exited $rc, want 0"
[ "$(cat "$out")" = "$merge_line" ] \
  || nogo "case9 re-merge: merge.sh printed [$(cat "$out")], the first merge printed [$merge_line]"
say "case 9 a merge twice is one merge: GO"

# ---------------------------------------------------------------------------
# Case 10: no secret in anything captured. The scan is shown to find a
# secret first, so that an empty result means something.
# ---------------------------------------------------------------------------
[ -s "$captured" ] || nogo "case10: the suite captured no adapter output; the scan would prove nothing"
if [ -n "${GITHUB_TOKEN:-}" ]; then
  printf 'before %s after\n' "$GITHUB_TOKEN" > "$work/probe"
  leaked "$work/probe" || nogo "case10: the scan did not find GITHUB_TOKEN in a file that holds it"
fi
if [ -n "$gitea_password" ]; then
  printf 'before %s after\n' "$gitea_password" > "$work/probe"
  leaked "$work/probe" || nogo "case10: the scan did not find the Gitea password in a file that holds it"
fi
printf 'nothing to see\n' > "$work/probe"
if leaked "$work/probe"; then nogo "case10: the scan found a secret in a file that holds none"; fi
if leaked "$captured"; then
  where=""
  for f in "$work"/out.* "$work"/err.*; do
    if leaked "$f"; then where="$where $(sed -n "s/^${f##*.} //p" "$work/labels")"; fi
  done
  nogo "case10: a secret appears in the output of:$where"
fi
say "case 10 no secret in the captured output: GO"

go_with "$CODE_HOST, PR #$number merged"
