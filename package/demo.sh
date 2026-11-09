#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The M23 acceptance (docs/adr/0045 §8) and M31's (docs/adr/0057 §3, §5),
# `./go demo-package`, on the host because its subject is the wrapper a
# stranger runs there. Builds the gates image (or takes LIGHTS_OUT_IMAGE
# as given), measures it, turns workloads/minimal into a fresh repository
# outside the checkout, and runs the wrapper on it the way a developer
# would. Its committed .lights-out/ stays (its tests read the flag file
# there) and names compose:backend-test, which the image refuses without
# the socket; init drafts the workbench form over it:
#
#   lights-out gates              NO-GO: compose:backend-test needs the socket
#   lights-out init               the draft lands in LIGHTS_OUT_OUT, not in the repository
#   (copy the draft in, commit; then a change to the code and its test, committed)
#   lights-out gates              GO on the change, in workbench, judged by the draft at its
#                                 base; init plus gates timed against the budget; the
#                                 summary has one GO line per gate
#   lights-out test-proof         GO: the new test fails on the base
#   lights-out test-integrity     GO: no test weakened, the changed lines' mutants killed
#   (a code change with a test that already passes on the base, committed)
#   lights-out test-proof         NO-GO at test-proof
#   (an assertion removed, committed)
#   lights-out test-integrity     NO-GO at test-weakening
#   lights-out gates STAGED=1     a staged change that breaks a test: NO-GO at test,
#                                 what a hook before a commit sees
#
# Then, outside the timed part, the first run (docs/adr/0064), each on a
# repository of its own:
#
#   no workload.env committed     gates, test-proof, test-integrity, each the first-run NO-GO
#                                 under its own name (also with one commit, and with STAGED=1)
#   a commit that removes it      NO-GO: gates, a change cannot remove the contract that judges it
#   lights-out init HEAD=<c>      drafts from <c>, an older commit: workload.env names <c>
#   lights-out init HEAD=<junk>   NO-GO: init, HEAD= is not a commit of the repository
#   init/summary.md               the heading, init's line, the three files, one line per file
#                                 under runners/ with its bytes, no /tmp/ and no output path
#   init, no pyproject.toml       NO-GO: init, and the summary says no draft is offered
#
# INIT_BUDGET_SECONDS: plan §16's second golden-rule measure, 300 s, an
# owner decision (2026-11-03); 0 disables the verdict.
set -eu
name=demo-package
. ci/lib.sh

engine=${CONTAINER_ENGINE:?CONTAINER_ENGINE not set; run this via ./go demo-package}
budget=${INIT_BUDGET_SECONDS:-300}
here=$(pwd -P)
if [ -z "${LIGHTS_OUT_IMAGE:-}" ]; then
  LIGHTS_OUT_IMAGE=localhost/lights-out-gates:dev
  PACKAGE_FLAVOUR=gates sh package/build.sh "$engine" "$LIGHTS_OUT_IMAGE" >&2 || nogo "the gates image did not build (see above)"
fi
export LIGHTS_OUT_IMAGE CONTAINER_ENGINE
# The measure ADR 0057 §3 records: the image as unpacked on this engine.
bytes=$("$engine" image inspect --format '{{.Size}}' "$LIGHTS_OUT_IMAGE" 2>/dev/null) || bytes=0
size="$((bytes / 1000000)) MB unpacked"
printf '[demo-package] image %s, %s\n' "$LIGHTS_OUT_IMAGE" "$size" >&2

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
repo=$work/minimal
export LIGHTS_OUT_OUT="$work/out"
mkdir -p "$repo"
cp -R workloads/minimal/. "$repo/"
commit() { git -C "$repo" -c user.name=lights-out-demo -c user.email=demo@lights-out.invalid -c commit.gpgsign=false commit -q "$@"; }
git -C "$repo" init -q -b main
git -C "$repo" add -A
commit -m "workloads/minimal, as a repository of its own"
printf '[demo-package] %s: workloads/minimal as a repository of its own, image %s\n' "$repo" "$LIGHTS_OUT_IMAGE" >&2

lo() { (cd "$repo" && sh "$here/lights-out" "$@"); }

out=$(lo gates) && nogo "gates on compose:backend-test passed without the engine socket: $out"
case "$out" in *"needs the engine socket"*) ;; *) nogo "gates on compose:backend-test did not name the socket: $out" ;; esac
printf '[demo-package] committed contract, no socket: %s\n' "$out" >&2

start=$(date +%s)
out=$(lo init) || nogo "lights-out init: $out"
printf '[demo-package] %s\n' "$out" >&2
[ -f "$LIGHTS_OUT_OUT/.lights-out/workload.env" ] || nogo "init left no draft in LIGHTS_OUT_OUT"
[ -z "$(git -C "$repo" status --porcelain)" ] || nogo "init wrote into the repository"
grep -q '^TOOLCHAIN_IMAGE=workbench$' "$LIGHTS_OUT_OUT/.lights-out/workload.env" || nogo "the draft's toolchain is not the workbench"
mkdir -p "$repo/.lights-out" && cp -R "$LIGHTS_OUT_OUT/.lights-out/." "$repo/.lights-out/"
git -C "$repo" add .lights-out
commit -m "the lights-out contract, the gates half drafted by lights-out init"
# A change, judged by the contract its base holds (docs/adr/0045 §3): the draft.
printf '\n\n@app.get("/version")\ndef version():\n    return {"version": APP_VERSION}\n' >> "$repo/minimal/app.py"
printf '\n\ndef test_version_returns_the_app_version(client):\n    assert client.get("/version").json() == {"version": APP_VERSION}\n' >> "$repo/tests/test_app.py"
git -C "$repo" add -A
commit -m "a /version route, and its test"
out=$(lo gates) || nogo "lights-out gates on a change: $out"
elapsed=$(( $(date +%s) - start ))
printf '[demo-package] %s (%ss for init and gates)\n' "$out" "$elapsed" >&2
case "$out" in "GO: gates — "*", in workbench") ;; *) nogo "gates did not run in the workbench: $out" ;; esac
if [ "$budget" -gt 0 ] && [ "$elapsed" -gt "$budget" ]; then
  nogo "init and gates took ${elapsed}s, over the ${budget}s budget (plan §16)"
fi
# The summary the Action posts (docs/adr/0057 §6): one GO line per gate.
summary=$LIGHTS_OUT_OUT/gates/summary.md
per_gate=$(grep -c '^- `GO: ' "$summary" 2>/dev/null) || per_gate=0
[ "$per_gate" = 8 ] || nogo "the summary has $per_gate GO lines for the eight gates" "$(cat "$summary" 2>/dev/null)"

# The two standalone commands on the same change (docs/adr/0057 §5).
out=$(lo test-proof) || nogo "lights-out test-proof on a change and its new test: $out"
case "$out" in "GO: test-proof — "*) ;; *) nogo "test-proof did not name itself: $out" ;; esac
printf '[demo-package] %s\n' "$out" >&2
out=$(lo test-integrity) || nogo "lights-out test-integrity on a change and its new test: $out"
case "$out" in "GO: test-integrity — "*) ;; *) nogo "test-integrity did not name itself: $out" ;; esac
printf '[demo-package] %s\n' "$out" >&2

# A code change with a test that passes on the base too: it proves nothing.
printf '\n# healthz answers the version the image was built with.\n' >> "$repo/minimal/app.py"
printf '\n\ndef test_healthz_answers_ok_again(client):\n    assert client.get("/healthz").status_code == 200\n' >> "$repo/tests/test_app.py"
git -C "$repo" add -A
commit -m "a comment, and a test that already passed"
out=$(lo test-proof) && nogo "a test that passes on the base passed test-proof: $out"
case "$out" in "NO-GO: test-proof — test-proof: "*) ;; *) nogo "test-proof did not stop at test-proof: $out" ;; esac
printf '[demo-package] %s\n' "$out" >&2

# An assertion removed: the suite is weaker.
grep -v 'assert resp.json() == {"ok": True}' "$repo/tests/test_app.py" > "$work/t.py"
cp "$work/t.py" "$repo/tests/test_app.py"
git -C "$repo" add -A
commit -m "one assertion fewer"
out=$(lo test-integrity) && nogo "a removed assertion passed test-integrity: $out"
case "$out" in "NO-GO: test-integrity — test-weakening: "*) ;; *) nogo "test-integrity did not stop at test-weakening: $out" ;; esac
printf '[demo-package] %s\n' "$out" >&2

# A staged change that breaks the suite: what a hook sees before a commit.
commits=$(git -C "$repo" rev-list --count HEAD)
printf '\n\ndef test_staged_break():\n    assert False, "staged by demo-package"\n' >> "$repo/tests/test_app.py"
git -C "$repo" add tests/test_app.py
staged=$(lo gates STAGED=1) && nogo "a staged change that breaks a test passed: $staged"
printf '[demo-package] staged, breaking a test: %s\n' "$staged" >&2
case "$staged" in "NO-GO: gates — test: "*) ;; *) nogo "STAGED=1 did not stop at the test gate: $staged" ;; esac
[ "$(git -C "$repo" rev-list --count HEAD)" = "$commits" ] && [ -n "$(git -C "$repo" diff --cached --name-only)" ] || nogo "STAGED=1 committed into the repository"

# --- the first run (docs/adr/0064), outside the timed part ----------------------------
# A fresh repository from workloads/minimal, one commit. mk DIR [--no-contract]
gitc() { d=$1; shift; git -C "$d" -c user.name=lights-out-demo -c user.email=demo@lights-out.invalid -c commit.gpgsign=false "$@"; }
mk() {
  mkdir -p "$1" && cp -R workloads/minimal/. "$1/"
  [ "${2:-}" != --no-contract ] || rm "$1/.lights-out/workload.env"
  git -C "$1" init -q -b main
  git -C "$1" add -A
  gitc "$1" commit -q -m "workloads/minimal"
}
# more DIR: a second commit
more() {
  printf '\nA line, so that there is a second commit.\n' >> "$1/README.md"
  gitc "$1" commit -q -am "a README line"
}
# lor DIR OUT ARGS...: the wrapper on DIR with its own output directory.
lor() { d=$1; o=$2; shift 2; (cd "$d" && LIGHTS_OUT_OUT=$o sh "$here/lights-out" "$@"); }
first_run="the repository has no .lights-out/workload.env committed; lights-out init drafts one"

# No contract at the head or the base: each gate says so under its own name.
nc=$work/nocontract
mk "$nc" --no-contract
more "$nc"
for g in gates test-proof test-integrity; do
  out=$(lor "$nc" "$work/out-nc" "$g") && nogo "$g on a repository with no workload.env passed: $out"
  [ "$out" = "NO-GO: $g — $first_run" ] || nogo "$g on a repository with no workload.env did not print the first-run line under its own name: $out"
done
printf '[demo-package] no contract committed: %s\n' "$out" >&2
# One commit, so no base at all: the same line.
solo=$work/solo
mk "$solo" --no-contract
out=$(lor "$solo" "$work/out-solo" gates) && nogo "gates on a single commit with no workload.env passed: $out"
[ "$out" = "NO-GO: gates — $first_run" ] || nogo "gates on a single commit with no workload.env did not print the first-run line: $out"
# STAGED=1: the repository's HEAD lacking it gives the same line.
printf '\nA staged line.\n' >> "$nc/README.md"
git -C "$nc" add README.md
out=$(lor "$nc" "$work/out-nc" gates STAGED=1) && nogo "a staged change on a repository with no workload.env passed: $out"
[ "$out" = "NO-GO: gates — $first_run" ] || nogo "STAGED=1 on a repository with no workload.env did not print the first-run line: $out"

# A change that removes the contract its base has: refused, no draft.
rmr=$work/removal
mk "$rmr"
git -C "$rmr" rm -q .lights-out/workload.env
gitc "$rmr" commit -q -m "remove the contract"
out=$(lor "$rmr" "$work/out-rm" gates) && nogo "a change that removes workload.env passed: $out"
want="NO-GO: gates — the change removes .lights-out/workload.env, which its base has; a change cannot remove the contract that judges it"
[ "$out" = "$want" ] || nogo "the removal of workload.env did not print the removal line: $out"
printf '[demo-package] removal: %s\n' "$out" >&2

# init HEAD=<c> drafts from c, an older commit, and writes the summary.
ih=$work/initheadat
mk "$ih"
c1=$(git -C "$ih" rev-parse HEAD)
c1s=$(git -C "$ih" rev-parse --short HEAD)
more "$ih"
c2s=$(git -C "$ih" rev-parse --short HEAD)
[ "$c1s" != "$c2s" ] || nogo "the two commits share a short sha ($c1s)"
o=$work/out-ih
line=$(lor "$ih" "$o" init "HEAD=$c1") || nogo "lights-out init HEAD=<an older commit>: $line"
case "$line" in "GO: init"*) ;; *) nogo "init HEAD=<an older commit> was not GO: $line" ;; esac
draft=$o/.lights-out
grep -qF "$c1s" "$draft/workload.env" || nogo "init HEAD=$c1s drafted a workload.env that does not name $c1s"
! grep -qF "$c2s" "$draft/workload.env" || nogo "init HEAD=$c1s drafted a workload.env that names HEAD's $c2s"
printf '[demo-package] init HEAD=%s (HEAD is %s): %s\n' "$c1s" "$c2s" "$line" >&2
sm=$o/init/summary.md
[ -s "$sm" ] || nogo "init left no init/summary.md in LIGHTS_OUT_OUT"
grep -qxF "### lights-out init, drafted from $c1s" "$sm" || nogo "init/summary.md lacks the heading '### lights-out init, drafted from $c1s'" "$(head -n 5 "$sm")"
# init's line, with no path of this machine (ADR 0064 §3): the draft is .lights-out.
want=$(printf '%s\n' "$line" | sed 's|draft in [^,]*/\.lights-out|draft in .lights-out|')
grep -qF -- "$want" "$sm" || nogo "init/summary.md does not hold init's line: $want"
for f in workload.env policy.env worker.md; do
  [ -s "$draft/$f" ] || nogo "the draft has no $f"
  while IFS= read -r l || [ -n "$l" ]; do
    grep -qxF -- "$l" "$sm" || nogo "init/summary.md does not hold $f: the line '$l' is missing"
  done < "$draft/$f"
done
rn=0
for f in $(cd "$draft" && find runners -type f | LC_ALL=C sort); do
  rn=$((rn + 1))
  n=$(wc -c < "$draft/$f" | tr -d ' ')
  grep -F -- "$f" "$sm" | grep -qw -- "$n" || nogo "init/summary.md has no line for $f with its $n bytes"
done
[ "$rn" -gt 0 ] || nogo "the draft has no runners/ for the summary to list"
! grep -qF /tmp/ "$sm" || nogo "init/summary.md names a /tmp/ path" "$(grep -F /tmp/ "$sm" | head -n 3)"
! grep -qF -- "$o" "$sm" || nogo "init/summary.md names the output directory" "$(grep -F -- "$o" "$sm" | head -n 3)"

# init HEAD=<not a commit>.
out=$(lor "$ih" "$work/out-bad" init HEAD=not-a-commit) && nogo "init HEAD=not-a-commit passed: $out"
want="NO-GO: init — HEAD=not-a-commit is not a commit of the repository (a shallow checkout? fetch-depth: 0)"
[ "$out" = "$want" ] || nogo "init HEAD=not-a-commit did not print the unknown-commit line: $out"

# No stack (no pyproject.toml, no package.json): NO-GO, and the summary offers no draft.
ns=$work/nostack
mkdir -p "$ns"
printf '# nothing to infer from\n' > "$ns/README.md"
git -C "$ns" init -q -b main
git -C "$ns" add -A
gitc "$ns" commit -q -m "a README"
out=$(lor "$ns" "$work/out-ns" init) && nogo "init on a repository with no stack passed: $out"
case "$out" in "NO-GO: init — "*) ;; *) nogo "init on a repository with no stack did not print a NO-GO: init line: $out" ;; esac
[ "$(printf '%s\n' "$out" | awk 'END{print NR}')" = 1 ] || nogo "init on a repository with no stack printed more than one line: $out"
nsm=$work/out-ns/init/summary.md
[ -s "$nsm" ] || nogo "init on a repository with no stack left no init/summary.md"
grep -qF -- "$out" "$nsm" || nogo "init/summary.md does not hold the NO-GO line: $out"
grep -qF "no draft is offered" "$nsm" || nogo "init/summary.md does not say that no draft is offered"
printf '[demo-package] no stack: %s\n' "$out" >&2

go_with "init and gates ${elapsed}s in workbench (budget ${budget}s), test-proof and test-integrity GO and NO-GO, a staged break NO-GO at test, the first run (no contract, a removal, init HEAD=, its summary, no stack), image $LIGHTS_OUT_IMAGE, $size"
