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

go_with "init and gates ${elapsed}s in workbench (budget ${budget}s), test-proof and test-integrity GO and NO-GO, a staged break NO-GO at test, image $LIGHTS_OUT_IMAGE, $size"
