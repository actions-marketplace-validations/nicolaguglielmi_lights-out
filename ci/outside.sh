#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-outside: docs/adr/0058 proved cold, no engine, no network.
#   (a) an adapter outside the repository, fixtures/outside-adapters/
#       json-files copied out of the checkout, set as STATE_STORE=outside/
#       json-files: make refuses any goal in one line before anything runs;
#       `make statestore-conformance` says GO and registers it; then make
#       admits it, linked at adapters/outside/json-files; one changed byte
#       is refused again; a broken copy fails the suite, is not registered
#       and stays refused; a symlink inside the tree is refused; outside/ on
#       a port with no suite (TRACKER) is refused; AGENT_HARNESS, wired to
#       no trial, is refused naming its suite; a suite beside another goal
#       on one command line tries nothing; no trial record outlives a suite.
#   (b) other CIs are surfaces, never judges (§6): the Jenkins recipe runs
#       the lights-out wrapper, posts its line under its own status context,
#       and that context is none the tower posts or awaits; success only on
#       a GO line.
# Everything runs in a scratch root that links this checkout's files, with
# a real adapters/ of its own, so no link lands in this checkout.
# shellcheck disable=SC2016 # the patterns grep for the Jenkinsfile's own $-expressions
set -eu
name=outside
. ci/lib.sh

for tool in make python3 jq; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool is not on PATH; run this via ./go ci"
done
repo=$(pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# --- the scratch root: every top-level entry linked, adapters/ copied as links ---
root=$tmp/root
mkdir -p "$root/adapters"
for f in "$repo"/* "$repo"/.env.example; do
  b=$(basename "$f")
  case "$b" in adapters | .crew | .attached) continue ;; esac
  ln -s "$f" "$root/$b"
done
for d in "$repo"/adapters/*/; do
  b=$(basename "$d")
  [ "$b" != outside ] || continue
  ln -s "$repo/adapters/$b" "$root/adapters/$b"
done
ext=$tmp/ext
mkdir -p "$ext"
cp -R fixtures/outside-adapters/json-files "$ext/json-files"
export JSON_FILES_DIR="$tmp/store"
reg=$tmp/register

# m GOAL VAR=VALUE...: make in the scratch root; stdout in $out, stderr in
# $err, exit code in $rc.
m() {
  goal=$1
  shift
  if (cd "$root" && make -s --no-print-directory "$goal" WORKLOAD=app WORKLOAD_CONTRACT=app WORKLOAD_ATTACHED= \
      ADAPTERS_PATH="$ext" ADAPTERS_REGISTER="$reg" "$@") \
      >"$tmp/out" 2>"$tmp/err" </dev/null; then rc=0; else rc=$?; fi
  out=$(cat "$tmp/out")
  err=$(cat "$tmp/err")
}
# refused LABEL PATTERN...: make stopped before any goal, one stderr line
# holding every PATTERN, nothing on stdout.
refused() {
  label=$1
  shift
  [ "$rc" -ne 0 ] || nogo "a: $label: make ran the goal (exit 0)"
  [ -z "$out" ] || nogo "a: $label: make printed on stdout before refusing: [$out]"
  [ "$(printf '%s\n' "$err" | awk 'END { print NR }')" -eq 1 ] || nogo "a: $label: want one refusal line, got: [$err]"
  for p do
    case "$err" in *"$p"*) ;; *) nogo "a: $label: the refusal does not say [$p]: [$err]" ;; esac
  done
}
admitted() {
  [ "$rc" -eq 0 ] || nogo "a: $1: refused: [$err]"
}

ss="STATE_STORE=outside/json-files"
m help "$ss"
refused "no proof" "$ss is refused" "statestore-conformance GO" "./go statestore-conformance $ss"
[ ! -e "$root/adapters/outside" ] || nogo "a: no proof: the refusal linked the adapter anyway"

m statestore-conformance "$ss"
[ "$rc" -eq 0 ] || nogo "a: statestore-conformance on the outside adapter: exit $rc, [$out]" "$err"
case "$out" in "GO: statestore-conformance"*) ;; *) nogo "a: statestore-conformance printed [$out]" ;; esac
[ "$(printf '%s\n' "$out" | awk 'END { print NR }')" -eq 1 ] || nogo "a: statestore-conformance printed more than one line: [$out]"
digest=$(python3 core/adapters.py hash "$ext/json-files")
awk -F'\t' -v d="$digest" '$1 == "STATE_STORE" && $2 == "json-files" && $3 == d && index($4, "statestore-conformance@") == 1 { f = 1 } END { exit !f }' "$reg" 2>/dev/null \
  || nogo "a: the GO registered no line for sha256 $digest" "$(cat "$reg" 2>/dev/null)"

m help "$ss"
admitted "after its suite"
[ -L "$root/adapters/outside/json-files" ] || nogo "a: admitted but not linked at adapters/outside/json-files"
[ "$(readlink "$root/adapters/outside/json-files")" = "$ext/json-files" ] || nogo "a: the link points at $(readlink "$root/adapters/outside/json-files")"

printf '\n' >> "$ext/json-files/delete.sh"
m help "$ss"
refused "one changed byte" "$ss is refused"

# A broken copy: put accepts a JSON array (case 5 of the suite).
cp -R fixtures/outside-adapters/json-files "$ext/json-broken"
awk '{ sub(/type == "object"/, "type == \"object\" or type == \"array\""); print }' \
  fixtures/outside-adapters/json-files/put.sh > "$ext/json-broken/put.sh"
cmp -s "$ext/json-broken/put.sh" fixtures/outside-adapters/json-files/put.sh && nogo "a: the broken copy is not broken"
before=$(cat "$reg")
m statestore-conformance STATE_STORE=outside/json-broken
[ "$rc" -ne 0 ] || nogo "a: a put that accepts an array passed statestore-conformance: [$out]"
case "$out" in "NO-GO: statestore-conformance — "*) ;; *) nogo "a: the broken copy's suite printed [$out]" ;; esac
[ "$(cat "$reg")" = "$before" ] || nogo "a: a NO-GO registered the broken copy"
m help STATE_STORE=outside/json-broken
refused "a broken copy" "STATE_STORE=outside/json-broken is refused"

cp -R fixtures/outside-adapters/json-files "$ext/json-linked"
ln -s /etc/hostname "$ext/json-linked/extra.sh"
m help STATE_STORE=outside/json-linked
refused "a symlink in the tree" "STATE_STORE=outside/json-linked is refused" "symlink"

m help TRACKER=outside/json-files
refused "a port with no suite" "TRACKER=outside/json-files is refused" "no conformance suite"

m help AGENT_HARNESS=outside/json-files
refused "an outside harness, left (§1)" "AGENT_HARNESS=outside/json-files is refused" "harness-conformance"

# A goal beside a suite is not a trial: it is admitted, or refused, first.
m statestore-conformance STATE_STORE=outside/json-broken help
refused "a suite with another goal" "STATE_STORE=outside/json-broken is refused"
[ ! -e "$tmp/trial-STATE_STORE" ] || nogo "a: a suite that ended left its trial record behind"

# --- b: a surface is never a judge (§6) -------------------------------------------
jf=surfaces/jenkins/Jenkinsfile
[ -f "$jf" ] || nogo "b: $jf not found"
# The contexts the tower posts: the third argument of every status.sh call in core/.
tower=$(awk '!/^[[:space:]]*#/ && /adapters\/\$CODE_HOST\/status\.sh"/ {
    for (i = 1; i <= NF; i++) if ($i == "\"$status\"") { print $(i + 1); break }
  }' core/*.sh core/steps/*.sh | sort -u)
[ -n "$tower" ] || nogo "b: found no context the tower posts in core/; the check reads nothing"
# The tower reads no commit status at all: no core file awaits one. The
# conformance suites in core/gates/ drive await.sh to prove it, and are not
# the tower (docs/adr/0084); nor are the tests.
readers=$(grep -rlE 'await\.sh|/statuses' core --include='*.sh' --include='*.py' \
  --exclude-dir=gates --exclude-dir=tests --exclude-dir=__pycache__ 2>/dev/null || :)
[ -z "$readers" ] || nogo "b: core/ reads commit statuses, where a surface's verdict could become the tower's: $readers"
ctx=$(sed -n 's/.*"context":"\([^"]*\)".*/\1/p' "$jf" | sort -u)
[ "$ctx" = lights-out/jenkins ] || nogo "b: $jf posts under [$ctx], want lights-out/jenkins only"
for t in $tower; do
  [ "$t" != "$ctx" ] || nogo "b: $jf posts under $t, a context the tower posts"
done
grep -qE '^line=\$\(lights-out gates "\$@"\)' "$jf" || nogo "b: $jf does not take its line from the lights-out wrapper's gates"
grep -qE '^case "\$line" in GO:\*\) state=success ;; \*\) state=failure ;; esac$' "$jf" \
  || nogo "b: $jf does not post success on a GO line only"

go_with "an outside StateStore refused, proven, admitted, refused again on one byte; Jenkins posts under lights-out/jenkins, the tower under $(printf '%s' "$tower" | tr '\n' ' ' | sed 's/ $//')"
