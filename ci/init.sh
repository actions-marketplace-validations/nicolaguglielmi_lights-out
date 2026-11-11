#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-init: proves docs/adr/0042 §1, §6, §9 and Resolved 4, 7 and 8 cold: no
# engine, no network, no key. The real core/init.py drafts the gates half of
# .lights-out/ for throwaway repositories built in a temp dir (never this
# checkout's workloads/ in place), and the draft is read back.
#   (a) a python repository (§6): STACK=python, a workload.env of exactly
#       the twelve keys (§1; docs/adr/0053 §1), each under a "# Provenance," comment, the
#       baseline empty (§6: measured later), the lockfile and the mutation
#       scope inferred, three non-empty commands without `$` or `#`
#       (Resolved 2), worker.md with `## Scope` and `## Tests`, a
#       policy.env, and runners/ copied from stacks/python/runners/.
#   (b) the toolchain follows the declared runtime (Resolved 8): a
#       requires-python the workbench's Python 3.13 satisfies gives
#       `workbench`, one it does not gives astral's uv image for a Python
#       it does; the comment saying so.
#   (c) a javascript repository (§6): the same, from package.json and
#       package-lock.json, with engines.node in place of requires-python.
#   (d) a repository init cannot draft (§6): exit 1 and one stdout line
#       naming what was looked for, for no stack and for a lockfile missing.
#   (e) the source repository is byte-identical after (ADR 0037 §1): the
#       draft lands in --out only.
#   (f) --set-baseline (§6) writes MUTATION_BASELINE with its provenance and
#       leaves the other ten keys; the measured draft passes ci/workloads.sh.
#   (g) workloads/minimal-js/.lights-out/runners/ is byte-identical to
#       stacks/javascript/runners/ (§9).
#   (h) a committed contract's plane keys are kept in the clone's draft,
#       "kept" (Resolved 4); its other keys are overwritten (§6).
#   (i) ci/workloads.sh's key parsing (§1, §2, §7) rejects, on a gates-only
#       contract (no compose.yaml, so no docker-compose call): a `$` or
#       `#` in a command, an empty command, a compose: toolchain with no
#       compose.yaml, an unknown toolchain form, a twelfth key and a
#       missing one; and accepts workloads/minimal-js's own.
#   (j) the checks can fail: (a)'s reader is run on a draft that lost a
#       provenance line, got a twelfth key, a `$`, or a baseline.
#   (k) lights-out's own runners (docs/adr/0049 §1, amendment 2026-11-11):
#       what is committed at HEAD is judged, because the image's entrypoint
#       puts the base's .lights-out/runners back into the working tree
#       (docs/adr/0033, 0045 §3) and `self` runs these checks there. GO when
#       HEAD's .lights-out/runners equals HEAD's stacks/python/runners
#       (self-checks.sh aside) and the working tree's stacks/python/runners
#       is HEAD's, or equals the working tree's .lights-out/runners (an
#       uncommitted edit made to both); NO-GO when HEAD's two copies differ,
#       or when stacks/python/runners has an edit .lights-out/runners lacks.
#       Run on five throwaway repositories, then on this checkout as (g).
# Written from the ADR, not from core/init.py; ci/attach.sh's shape.
set -eu
name=init
. ci/lib.sh

for f in ci/lib.sh ci/workloads.sh core/init.py stacks/python/runners stacks/javascript/runners \
  workloads/minimal-js/.lights-out/workload.env workloads/minimal-js/.lights-out/runners; do
  [ -e "$f" ] || nogo "$f not found"
done

t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
mismatch=""
fail_case() {
  printf 'ci-init: %s: %s\n' "$1" "$2" >&2
  [ -n "$mismatch" ] || mismatch="$1"
}

# runners_drift <repository> <scratch dir>: why lights-out's own runners
# are out of step (case k's rule), nothing when they are not.
runners_drift() {
  rm -rf "$2" && mkdir -p "$2"
  git -C "$1" archive HEAD stacks/python/runners .lights-out/runners | tar -x -C "$2" \
    || { echo "could not read the runners committed at HEAD"; return 0; }
  diff -r -x self-checks.sh "$2/stacks/python/runners" "$2/.lights-out/runners" >/dev/null 2>&1 \
    || { echo "at HEAD, .lights-out/runners differs from stacks/python/runners"; return 0; }
  diff -r "$1/stacks/python/runners" "$2/stacks/python/runners" >/dev/null 2>&1 && return 0
  diff -r -x self-checks.sh "$1/stacks/python/runners" "$1/.lights-out/runners" >/dev/null 2>&1 && return 0
  echo "stacks/python/runners has an uncommitted edit that .lights-out/runners does not have"
}

# core/ is run by path: no bytecode written into it.
export PYTHONDONTWRITEBYTECODE=1

# The twelve keys (docs/adr/0030 §2, 0042 §1 and 0053 §1), sorted, as one line.
want_keys=$(printf '%s\n' CANARY_VERSION MUTATION_BASELINE WORKLOAD_KILL_SWITCH WORKLOAD_SAMPLE_PATH \
  WORKLOAD_LOCKFILES WORKLOAD_MUTATION_SCOPE WORKLOAD_TEST_ROOT WORKLOAD_TEST_PATHS TOOLCHAIN_IMAGE TEST_CMD SAST_CMD \
  MUTATION_CMD | LC_ALL=C sort | tr '\n' ' ')

# mk_py DIR [REQUIRES]: a python repository, as small as the ADR says init reads.
mk_py() {
  mkdir -p "$1/demo" "$1/tests"
  {
    printf '[project]\nname = "demo"\nversion = "0.1.0"\n'
    [ -z "${2:-}" ] || printf 'requires-python = "%s"\n' "$2"
  } > "$1/pyproject.toml"
  printf 'version = 1\n' > "$1/uv.lock"
  printf 'def add(a, b):\n    return a + b\n' > "$1/demo/__init__.py"
  printf 'from demo import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n' > "$1/tests/test_demo.py"
}

# mk_js DIR [ENGINES]: a javascript repository.
mk_js() {
  mkdir -p "$1/src" "$1/test"
  if [ -n "${2:-}" ]; then
    printf '{"name": "demo", "version": "1.0.0", "scripts": {"test": "node --test"}, "engines": {"node": "%s"}}\n' "$2" > "$1/package.json"
  else
    printf '{"name": "demo", "version": "1.0.0", "scripts": {"test": "node --test"}}\n' > "$1/package.json"
  fi
  printf '{"name": "demo", "version": "1.0.0", "lockfileVersion": 3, "packages": {}}\n' > "$1/package-lock.json"
  printf 'export const add = (a, b) => a + b;\n' > "$1/src/add.js"
  printf "import test from 'node:test';\ntest('add', () => {});\n" > "$1/test/add.test.js"
}

# run_init REPO OUT [ARG...]: core/init.py as its docstring gives it; stdout
# in $t/out, stderr in $t/err, exit code in $irc.
run_init() {
  r=$1
  o=$2
  shift 2
  python3 core/init.py --repo "$r" --out "$o" --stacks stacks --commit abc1234 --today 2026-11-03 "$@" \
    >"$t/out" 2>"$t/err" && irc=0 || irc=$?
}

# val FILE KEY: the first KEY=VALUE outside comments.
val() { grep -v '^[[:space:]]*#' "$1" | sed -n "s/^$2=//p" | head -1; }

# above FILE KEY: the comment block directly above KEY's line.
above() {
  awk -v k="$2" '/^#/ { blk = blk $0 "\n"; next } { if (index($0, k "=") == 1) { printf "%s", blk; exit } blk = "" }' "$1"
}

# env_flaw FILE: what is wrong with a drafted workload.env's shape, or
# nothing: exactly the twelve keys, once each, a "# Provenance," line in the
# comment block directly above every one, and three commands that are
# non-empty and free of `$` and `#`.
env_flaw() {
  f=$1
  keys=$(grep -v '^[[:space:]]*#' "$f" | grep -v '^[[:space:]]*$' | sed 's/=.*//' | LC_ALL=C sort | tr '\n' ' ')
  [ "$keys" = "$want_keys" ] || { printf 'the keys are: %s' "$keys"; return; }
  bare=$(awk '/^#/ { if ($0 ~ /^# Provenance,/) p = 1; next } /^[[:space:]]*$/ { p = 0; next } { if (!p) printf "%s ", substr($0, 1, index($0, "=") - 1); p = 0 }' "$f")
  [ -z "$bare" ] || { printf 'no "# Provenance," line directly above: %s' "$bare"; return; }
  for k in TEST_CMD SAST_CMD MUTATION_CMD; do
    v=$(val "$f" "$k")
    [ -n "$v" ] || { printf '%s is empty' "$k"; return; }
    case "$v" in
      *'$'* | *'#'*) printf '%s holds a $ or a #: %s' "$k" "$v"; return ;;
    esac
  done
}

# draft_flaw FILE: env_flaw, plus the baseline empty (§6: measured after).
draft_flaw() {
  flaw=$(env_flaw "$1")
  [ -z "$flaw" ] || { printf '%s' "$flaw"; return; }
  [ -z "$(val "$1" MUTATION_BASELINE)" ] || printf 'MUTATION_BASELINE is %s, want it empty' "$(val "$1" MUTATION_BASELINE)"
}

# tree_state DIR: every path and every file's checksum.
tree_state() { (cd "$1" && find . | LC_ALL=C sort && find . -type f -exec cksum {} + | LC_ALL=C sort); }

# (a) a python repository.
py="$t/py"
mk_py "$py" '==3.13.*'
tree_state "$py" > "$t/py.before"
run_init "$py" "$t/py-out"
[ "$irc" -eq 0 ] && [ "$(cat "$t/out")" = STACK=python ] \
  || fail_case a-stack "a python repository: exit $irc, stdout '$(cat "$t/out")', want STACK=python and 0; stderr: $(cat "$t/err")"
if [ -f "$t/py-out/workload.env" ]; then
  flaw=$(draft_flaw "$t/py-out/workload.env")
  [ -z "$flaw" ] || fail_case a-workload-env "$flaw"
  [ "$(val "$t/py-out/workload.env" WORKLOAD_LOCKFILES)" = uv.lock ] \
    || fail_case a-lockfiles "WORKLOAD_LOCKFILES=$(val "$t/py-out/workload.env" WORKLOAD_LOCKFILES), want uv.lock"
  [ "$(val "$t/py-out/workload.env" WORKLOAD_MUTATION_SCOPE)" = demo/ ] \
    || fail_case a-scope "WORKLOAD_MUTATION_SCOPE=$(val "$t/py-out/workload.env" WORKLOAD_MUTATION_SCOPE), want demo/"
else
  fail_case a-workload-env "no $t/py-out/workload.env"
fi
for h in '## Scope' '## Tests'; do
  grep -qx "$h" "$t/py-out/worker.md" 2>/dev/null || fail_case a-worker "worker.md has no '$h' line"
done
[ -f "$t/py-out/policy.env" ] || fail_case a-policy "no policy.env"
diff -r stacks/python/runners "$t/py-out/runners" >"$t/diff" 2>&1 \
  || { fail_case a-runners "runners/ differs from stacks/python/runners/"; cat "$t/diff" >&2; }

# (e) for the python repository: untouched.
tree_state "$py" > "$t/py.after"
cmp -s "$t/py.before" "$t/py.after" || fail_case e-python "init changed the source repository"

# (b) the toolchain follows requires-python.
for req in '==3.13.*' '>=3.11'; do
  rm -rf "$t/b" "$t/b-out"
  mk_py "$t/b" "$req"
  run_init "$t/b" "$t/b-out"
  got=$(val "$t/b-out/workload.env" TOOLCHAIN_IMAGE 2>/dev/null || true)
  [ "$got" = workbench ] || fail_case b-workbench "requires-python '$req': TOOLCHAIN_IMAGE=$got, want workbench"
  above "$t/b-out/workload.env" TOOLCHAIN_IMAGE 2>/dev/null | grep -q 'requires-python' \
    || fail_case b-comment "requires-python '$req': the comment above TOOLCHAIN_IMAGE does not mention requires-python"
done
for req in '==3.11.*' '<3.13'; do
  rm -rf "$t/b" "$t/b-out"
  mk_py "$t/b" "$req"
  run_init "$t/b" "$t/b-out"
  got=$(val "$t/b-out/workload.env" TOOLCHAIN_IMAGE 2>/dev/null || true)
  case "$got" in
    ghcr.io/astral-sh/uv:python3.*) : ;;
    *) fail_case b-image "requires-python '$req': TOOLCHAIN_IMAGE=$got, want ghcr.io/astral-sh/uv:python3.<minor>-trixie-slim" ;;
  esac
  above "$t/b-out/workload.env" TOOLCHAIN_IMAGE 2>/dev/null | grep -q 'requires-python' \
    || fail_case b-comment "requires-python '$req': the comment above TOOLCHAIN_IMAGE does not mention requires-python"
  flaw=$(draft_flaw "$t/b-out/workload.env" 2>/dev/null || true)
  [ -z "$flaw" ] || fail_case b-image "requires-python '$req': $flaw"
done
rm -rf "$t/b" "$t/b-out"
mk_py "$t/b" '==3.11.*'
run_init "$t/b" "$t/b-out"
case "$(val "$t/b-out/workload.env" TOOLCHAIN_IMAGE)" in
  ghcr.io/astral-sh/uv:python3.11-*) : ;;
  *) fail_case b-minor "requires-python '==3.11.*': TOOLCHAIN_IMAGE=$(val "$t/b-out/workload.env" TOOLCHAIN_IMAGE), want python3.11" ;;
esac
# No requires-python: nothing excludes the workbench (Resolved 8).
rm -rf "$t/b" "$t/b-out"
mk_py "$t/b"
run_init "$t/b" "$t/b-out"
[ "$(val "$t/b-out/workload.env" TOOLCHAIN_IMAGE)" = workbench ] \
  || fail_case b-none "no requires-python: TOOLCHAIN_IMAGE=$(val "$t/b-out/workload.env" TOOLCHAIN_IMAGE), want workbench"

# (c) a javascript repository.
js="$t/js"
mk_js "$js"
tree_state "$js" > "$t/js.before"
run_init "$js" "$t/js-out"
[ "$irc" -eq 0 ] && [ "$(cat "$t/out")" = STACK=javascript ] \
  || fail_case c-stack "a javascript repository: exit $irc, stdout '$(cat "$t/out")', want STACK=javascript and 0; stderr: $(cat "$t/err")"
if [ -f "$t/js-out/workload.env" ]; then
  flaw=$(draft_flaw "$t/js-out/workload.env")
  [ -z "$flaw" ] || fail_case c-workload-env "$flaw"
  [ "$(val "$t/js-out/workload.env" WORKLOAD_LOCKFILES)" = package-lock.json ] \
    || fail_case c-lockfiles "WORKLOAD_LOCKFILES=$(val "$t/js-out/workload.env" WORKLOAD_LOCKFILES), want package-lock.json"
  [ "$(val "$t/js-out/workload.env" WORKLOAD_MUTATION_SCOPE)" = src/ ] \
    || fail_case c-scope "WORKLOAD_MUTATION_SCOPE=$(val "$t/js-out/workload.env" WORKLOAD_MUTATION_SCOPE), want src/"
  [ "$(val "$t/js-out/workload.env" TOOLCHAIN_IMAGE)" = workbench ] \
    || fail_case c-workbench "no engines.node: TOOLCHAIN_IMAGE=$(val "$t/js-out/workload.env" TOOLCHAIN_IMAGE), want workbench"
else
  fail_case c-workload-env "no $t/js-out/workload.env"
fi
for h in '## Scope' '## Tests'; do
  grep -qx "$h" "$t/js-out/worker.md" 2>/dev/null || fail_case c-worker "worker.md has no '$h' line"
done
[ -f "$t/js-out/policy.env" ] || fail_case c-policy "no policy.env"
diff -r stacks/javascript/runners "$t/js-out/runners" >"$t/diff" 2>&1 \
  || { fail_case c-runners "runners/ differs from stacks/javascript/runners/"; cat "$t/diff" >&2; }
tree_state "$js" > "$t/js.after"
cmp -s "$t/js.before" "$t/js.after" || fail_case e-javascript "init changed the source repository"
for eng in '>=20' '>=22'; do
  rm -rf "$t/c" "$t/c-out"
  mk_js "$t/c" "$eng"
  run_init "$t/c" "$t/c-out"
  [ "$(val "$t/c-out/workload.env" TOOLCHAIN_IMAGE)" = workbench ] \
    || fail_case c-engines "engines.node '$eng': TOOLCHAIN_IMAGE=$(val "$t/c-out/workload.env" TOOLCHAIN_IMAGE), want workbench"
done
rm -rf "$t/c" "$t/c-out"
mk_js "$t/c" '^20'
run_init "$t/c" "$t/c-out"
case "$(val "$t/c-out/workload.env" TOOLCHAIN_IMAGE)" in
  docker.io/library/node:*) : ;;
  *) fail_case c-image "engines.node '^20': TOOLCHAIN_IMAGE=$(val "$t/c-out/workload.env" TOOLCHAIN_IMAGE), want docker.io/library/node:<major>" ;;
esac
above "$t/c-out/workload.env" TOOLCHAIN_IMAGE 2>/dev/null | grep -q 'engines.node' \
  || fail_case c-comment "engines.node '^20': the comment above TOOLCHAIN_IMAGE does not mention engines.node"
flaw=$(draft_flaw "$t/c-out/workload.env" 2>/dev/null || true)
[ -z "$flaw" ] || fail_case c-image "engines.node '^20': $flaw"

# (d) a repository init cannot draft: one stdout line, exit 1.
undraftable() {  # CASE REPO WANT...: exit 1, one stdout line naming each WANT
  c=$1
  r=$2
  shift 2
  run_init "$r" "$t/d-out"
  [ "$irc" -eq 1 ] || { fail_case "$c" "exit $irc, want 1; stdout: $(cat "$t/out")"; return; }
  [ "$(awk 'END{print NR}' "$t/out")" -eq 1 ] || { fail_case "$c" "stdout has $(awk 'END{print NR}' "$t/out") lines, want 1: $(cat "$t/out")"; return; }
  for want in "$@"; do
    grep -qF -- "$want" "$t/out" || fail_case "$c" "the line does not name $want: $(cat "$t/out")"
  done
}
mkdir -p "$t/empty"
printf 'nothing to see\n' > "$t/empty/README.md"
undraftable d-no-stack "$t/empty" pyproject.toml package.json
mk_py "$t/nolock-py" '==3.13.*'
rm -f "$t/nolock-py/uv.lock"
undraftable d-no-uv-lock "$t/nolock-py" uv.lock
mk_js "$t/nolock-js"
rm -f "$t/nolock-js/package-lock.json"
undraftable d-no-package-lock "$t/nolock-js" package-lock.json

# (f) --set-baseline.
python3 core/init.py --set-baseline "$t/py-out/workload.env" 0.8125 "measured by the test: 12 mutants" >"$t/out" 2>"$t/err" \
  && irc=0 || irc=$?
[ "$irc" -eq 0 ] || fail_case f-exit "--set-baseline exited $irc: $(cat "$t/out" "$t/err")"
grep -v '^[[:space:]]*#' "$t/py-out/workload.env" | grep -v '^MUTATION_BASELINE=' > "$t/after.keys"
# The draft's other ten keys, read from a second, untouched run.
run_init "$py" "$t/py-again"
grep -v '^[[:space:]]*#' "$t/py-again/workload.env" | grep -v '^MUTATION_BASELINE=' > "$t/before.keys"
cmp -s "$t/before.keys" "$t/after.keys" || fail_case f-keys "--set-baseline changed a key other than MUTATION_BASELINE"
[ "$(val "$t/py-out/workload.env" MUTATION_BASELINE)" = 0.8125 ] \
  || fail_case f-baseline "MUTATION_BASELINE=$(val "$t/py-out/workload.env" MUTATION_BASELINE), want 0.8125"
[ "$(above "$t/py-out/workload.env" MUTATION_BASELINE | tail -n 1)" = "# Provenance, measurement: measured by the test: 12 mutants" ] \
  || fail_case f-provenance "the line above MUTATION_BASELINE is '$(above "$t/py-out/workload.env" MUTATION_BASELINE | tail -n 1)'"
flaw=$(env_flaw "$t/py-out/workload.env")
[ -z "$flaw" ] || fail_case f-shape "after --set-baseline: $flaw"
# A second measurement replaces the first, with its provenance.
python3 core/init.py --set-baseline "$t/py-out/workload.env" 0.5 "re-measured by the test" >/dev/null 2>&1 || :
{ [ "$(grep -c '^MUTATION_BASELINE=' "$t/py-out/workload.env")" -eq 1 ] \
  && [ "$(val "$t/py-out/workload.env" MUTATION_BASELINE)" = 0.5 ] \
  && [ "$(above "$t/py-out/workload.env" MUTATION_BASELINE | tail -n 1)" = "# Provenance, measurement: re-measured by the test" ] \
  && ! grep -q 'measured by the test: 12 mutants' "$t/py-out/workload.env"; } \
  || fail_case f-again "a second --set-baseline did not replace the first value and its provenance"

# (g) the committed examples do not drift from what init copies: minimal-js,
# and lights-out's own contract (docs/adr/0049), whose one extra runner is
# its TEST_CMD.
diff -r stacks/javascript/runners workloads/minimal-js/.lights-out/runners >"$t/diff" 2>&1 \
  || { fail_case g-runners "workloads/minimal-js/.lights-out/runners differs from stacks/javascript/runners"; cat "$t/diff" >&2; }
why=$(runners_drift . "$t/self")
[ -z "$why" ] || fail_case g-self "lights-out's own runners: $why"

# (k) the rule (g-self) applies, on throwaway repositories.
k=$t/k
mkdir -p "$k/stacks/python/runners" "$k/.lights-out/runners"
kgit() { git -C "$k" -c user.name=ci -c user.email=ci@localhost.invalid -c commit.gpgsign=false "$@"; }
kgit init -q
printf 'one\n' > "$k/stacks/python/runners/score.py"
cp "$k/stacks/python/runners/score.py" "$k/.lights-out/runners/score.py"
printf 'exec make ci\n' > "$k/.lights-out/runners/self-checks.sh"
kgit add -A && kgit commit -q -m one
k_one=$(kgit rev-parse HEAD)
[ -z "$(runners_drift "$k" "$t/k1")" ] || fail_case k-equal "equal committed copies were refused: $(runners_drift "$k" "$t/k1")"
printf 'two\n' > "$k/stacks/python/runners/score.py"
cp "$k/stacks/python/runners/score.py" "$k/.lights-out/runners/score.py"
[ -z "$(runners_drift "$k" "$t/k2")" ] || fail_case k-both-uncommitted "an uncommitted edit made to both copies was refused"
kgit add -A && kgit commit -q -m two
kgit restore --source="$k_one" --worktree -- .lights-out/runners
[ -z "$(runners_drift "$k" "$t/k3")" ] || fail_case k-base-contract "the base's contract put back by the entrypoint was refused: $(runners_drift "$k" "$t/k3")"
kgit restore --worktree -- .lights-out/runners
printf 'three\n' > "$k/stacks/python/runners/score.py"
[ -n "$(runners_drift "$k" "$t/k4")" ] || fail_case k-stack-uncommitted "an uncommitted stack edit the contract lacks was accepted"
kgit add -A && kgit commit -q -m three
[ -n "$(runners_drift "$k" "$t/k5")" ] || fail_case k-stack-committed "a commit changing the stack and not the contract was accepted"

# (h) a committed contract: the plane keys are kept, the rest is the draft's.
hr="$t/committed"
mk_py "$hr" '==3.13.*'
mkdir -p "$hr/.lights-out"
cat > "$hr/.lights-out/workload.env" <<'ENV'
CANARY_VERSION=x
MUTATION_BASELINE=0.9
WORKLOAD_KILL_SWITCH=ks
WORKLOAD_SAMPLE_PATH=/sample
WORKLOAD_LOCKFILES=old.lock
WORKLOAD_MUTATION_SCOPE=old/
WORKLOAD_TEST_ROOT=
TOOLCHAIN_IMAGE=workbench
TEST_CMD=echo old tests
SAST_CMD=echo old sast
MUTATION_CMD=echo old mutation
ENV
tree_state "$hr" > "$t/hr.before"
run_init "$hr" "$t/hr-out"
[ "$irc" -eq 0 ] && [ "$(cat "$t/out")" = STACK=python ] \
  || fail_case h-stack "a repository with a committed contract: exit $irc, stdout '$(cat "$t/out")'"
if [ -f "$t/hr-out/workload.env" ]; then
  [ "$(val "$t/hr-out/workload.env" CANARY_VERSION)" = x ] \
    || fail_case h-canary "CANARY_VERSION=$(val "$t/hr-out/workload.env" CANARY_VERSION), want the committed x"
  [ "$(val "$t/hr-out/workload.env" WORKLOAD_KILL_SWITCH)" = ks ] \
    || fail_case h-kill-switch "WORKLOAD_KILL_SWITCH=$(val "$t/hr-out/workload.env" WORKLOAD_KILL_SWITCH), want the committed ks"
  [ "$(val "$t/hr-out/workload.env" WORKLOAD_SAMPLE_PATH)" = /sample ] \
    || fail_case h-sample "WORKLOAD_SAMPLE_PATH=$(val "$t/hr-out/workload.env" WORKLOAD_SAMPLE_PATH), want the committed /sample"
  above "$t/hr-out/workload.env" CANARY_VERSION | tail -n 1 | grep -q '^# Provenance, kept' \
    || fail_case h-provenance "the line above CANARY_VERSION is not '# Provenance, kept…': $(above "$t/hr-out/workload.env" CANARY_VERSION | tail -n 1)"
  flaw=$(env_flaw "$t/hr-out/workload.env")
  [ -z "$flaw" ] || fail_case h-shape "$flaw"
  [ "$(val "$t/hr-out/workload.env" WORKLOAD_MUTATION_SCOPE)" = demo/ ] \
    || fail_case h-overwrite "WORKLOAD_MUTATION_SCOPE=$(val "$t/hr-out/workload.env" WORKLOAD_MUTATION_SCOPE), want the draft's demo/, not the committed old/"
  [ -z "$(val "$t/hr-out/workload.env" MUTATION_BASELINE)" ] \
    || fail_case h-baseline "the committed MUTATION_BASELINE survived into the draft: $(val "$t/hr-out/workload.env" MUTATION_BASELINE)"
else
  fail_case h-stack "no draft for a repository with a committed contract"
fi
tree_state "$hr" > "$t/hr.after"
cmp -s "$t/hr.before" "$t/hr.after" || fail_case e-committed "init changed a repository with a committed contract"
# Without a committed contract the plane keys are empty and say why.
[ -z "$(val "$t/py-again/workload.env" CANARY_VERSION)" ] || fail_case h-empty "CANARY_VERSION is not empty with no committed contract"
above "$t/py-again/workload.env" CANARY_VERSION | grep -q 'plane half' \
  || fail_case h-empty "the comment above CANARY_VERSION does not say the plane half is not drafted"

# (f, continued) a measured draft passes ci/workloads.sh; used by (i) too.
# gates_only_check DIR CONTRACT: ci/workloads.sh on a gates-only contract.
gates_only_check() {
  env -i PATH="$PATH" WORKLOAD_CONTRACT="$2" WORKBENCH_IMAGE=x sh ci/workloads.sh "$1" >"$t/out" 2>"$t/err" && wrc=0 || wrc=$?
}
python3 core/init.py --set-baseline "$t/py-again/workload.env" 0.75 "measured by the test" >/dev/null 2>&1 || :
gates_only_check "$py" "$t/py-again"
{ [ "$wrc" -eq 0 ] && [ "$(cat "$t/out")" = "GO: workloads" ]; } \
  || fail_case f-contract "ci/workloads.sh on the measured python draft: exit $wrc, $(cat "$t/out"); $(cat "$t/err")"
run_init "$js" "$t/js-again"
python3 core/init.py --set-baseline "$t/js-again/workload.env" 0.75 "measured by the test" >/dev/null 2>&1 || :
gates_only_check "$js" "$t/js-again"
{ [ "$wrc" -eq 0 ] && [ "$(cat "$t/out")" = "GO: workloads" ]; } \
  || fail_case f-contract "ci/workloads.sh on the measured javascript draft: exit $wrc, $(cat "$t/out"); $(cat "$t/err")"

# (i) ci/workloads.sh's key parsing, on a gates-only copy of minimal-js's contract.
variant() {  # NAME: a fresh copy of the committed gates-only contract in $t/w/NAME
  rm -rf "$t/w/$1"
  mkdir -p "$t/w/$1"
  cp -R workloads/minimal-js/.lights-out "$t/w/$1/.lights-out"
}
set_key() {  # NAME KEY VALUE: replace KEY's line
  awk -v k="$2" -v v="$3" 'index($0, k "=") == 1 { print k "=" v; next } { print }' "$t/w/$1/.lights-out/workload.env" > "$t/w/env.new"
  mv "$t/w/env.new" "$t/w/$1/.lights-out/workload.env"
}
rejects() {  # NAME WANT...: ci/workloads.sh says one NO-GO line naming each WANT
  n=$1
  shift
  gates_only_check "$t/w/$n" "$t/w/$n/.lights-out"
  if [ "$wrc" -ne 1 ] || [ "$(awk 'END{print NR}' "$t/out")" -ne 1 ]; then
    fail_case "i-$n" "want exit 1 and one NO-GO line, got exit $wrc: $(cat "$t/out")"
    return
  fi
  case "$(cat "$t/out")" in
    "NO-GO: workloads — "?*) : ;;
    *) fail_case "i-$n" "not a NO-GO line: $(cat "$t/out")"; return ;;
  esac
  for want in "$@"; do
    grep -qF -- "$want" "$t/out" || fail_case "i-$n" "the line does not name $want: $(cat "$t/out")"
  done
}
mkdir -p "$t/w"
variant good
gates_only_check "$t/w/good" "$t/w/good/.lights-out"
{ [ "$wrc" -eq 0 ] && [ "$(cat "$t/out")" = "GO: workloads" ]; } \
  || fail_case i-good "workloads/minimal-js's gates-only contract: exit $wrc, $(cat "$t/out"); $(cat "$t/err")"
variant dollar
# shellcheck disable=SC2016 # the $ is the point: a value make's include would expand
set_key dollar TEST_CMD 'echo $HOME'
rejects dollar TEST_CMD
variant hash
set_key hash SAST_CMD 'sh sast.sh # comment'
rejects hash SAST_CMD
variant empty
set_key empty MUTATION_CMD ''
rejects empty MUTATION_CMD
variant compose
set_key compose TOOLCHAIN_IMAGE compose:backend-test
rejects compose compose.yaml
variant form
set_key form TOOLCHAIN_IMAGE 'Not An Image'
rejects form 'Not An Image'
variant twelfth
printf 'EXTRA_KEY=1\n' >> "$t/w/twelfth/.lights-out/workload.env"
rejects twelfth EXTRA_KEY
variant missing
grep -v '^SAST_CMD=' "$t/w/missing/.lights-out/workload.env" > "$t/w/env.new"
mv "$t/w/env.new" "$t/w/missing/.lights-out/workload.env"
rejects missing SAST_CMD

# (j) the checks can fail: draft_flaw on a draft with one clause broken.
run_init "$py" "$t/j-out"
good_env="$t/j-out/workload.env"
[ -z "$(draft_flaw "$good_env")" ] || fail_case j-control "the control draft is not clean: $(draft_flaw "$good_env")"
awk '{ l[NR] = $0 } END { for (i = 1; i <= NR; i++) if (!(l[i] ~ /^# Provenance/ && l[i + 1] ~ /^TEST_CMD=/)) print l[i] }' "$good_env" > "$t/no-prov.env"
{ cat "$good_env"; printf '# Provenance, test: extra\nEXTRA_KEY=1\n'; } > "$t/twelfth.env"
# shellcheck disable=SC2016 # the $ is the point
sed 's/^TEST_CMD=.*/TEST_CMD=echo $HOME/' "$good_env" > "$t/dollar.env"
sed 's/^MUTATION_BASELINE=.*/MUTATION_BASELINE=0.5/' "$good_env" > "$t/baseline.env"
for broken in no-prov twelfth dollar baseline; do
  [ -n "$(draft_flaw "$t/$broken.env")" ] || fail_case "j-$broken" "the draft check accepted a draft broken by $broken"
done

[ -z "$mismatch" ] || nogo "case $mismatch failed; see stderr"

go
