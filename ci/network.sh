#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-network: proves the `network` AgentHarness adapter (docs/adr/0036
# §2-§5), cold: throwaway git repositories, a copy of the adapter and of
# the two core checks it calls in a scratch root, and a stub member
# harness written here. No model, no plane. Written from ADR 0036, not
# from adapters/network/. Both directions:
#   a. a ticket without `## Network` reaches the member harness unchanged
#   b. two members: both commits integrated in the declared order, each
#      member saw only the base and only its own part, the artefacts pass
#      core/harness-check.sh, run.json lists the members
#   c. a member outside its own part (inside the ticket's) is refused,
#      naming member and path; nothing integrated
#   d. one path changed by two members is refused; nothing integrated
#   e. overlapping perimeters are refused before any member runs
#   f. a failed member is refused, naming it; nothing integrated
#   g. five members are refused before any member runs
#   h. AGENT_HARNESS=network is refused before any member runs
set -eu
name=network
. ci/lib.sh

[ -f adapters/network/run.sh ] || nogo "adapters/network/run.sh not found"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

root="$work/root"
mkdir -p "$root/adapters/network" "$root/adapters/stub" "$root/core" "$root/workload"
cp adapters/network/run.sh "$root/adapters/network/run.sh"
cp core/perimeter.sh core/harness-check.sh "$root/core/"

# The stub member: STUB_PLAN holds "<id> <path>" lines; the member whose
# TICKET is <ticket>/<id> writes and commits each of its paths. It records
# what it was given (its input document, the files its workspace had, its
# commit count over BASE) and appends its TICKET to STUB_CALLS. A member
# listed in STUB_FAIL exits 1 after leaving complete artefacts: its exit
# code alone must refuse it.
cat > "$root/adapters/stub/run.sh" <<'EOF'
set -eu
printf '%s\n' "$TICKET" >> "$STUB_CALLS"
id=${TICKET#*/}
mkdir -p "$OUT"
cp "$TICKET_FILE" "$OUT/seen.md"
git -C "$WORKSPACE" ls-files > "$OUT/seen-files"
git -C "$WORKSPACE" rev-list --count "$BASE..HEAD" > "$OUT/seen-commits"
printf '%s\n' "${STUB_PLAN:-}" | while read -r who path; do
  [ "$who" = "$id" ] || continue
  mkdir -p "$WORKSPACE/$(dirname "$path")"
  printf '%s by %s\n' "$path" "$id" > "$WORKSPACE/$path"
done
git -C "$WORKSPACE" add -A
git -C "$WORKSPACE" -c user.name=stub -c user.email=stub@lights-out.invalid commit -q -m "stub $id" || true
git -C "$WORKSPACE" format-patch --stdout "$BASE..HEAD" > "$OUT/patch"
printf '{"title":"stub %s","body":"body of %s"}\n' "$id" "$id" > "$OUT/pr.json"
printf '{"harness":"stub","model":"stub-model"}\n' > "$OUT/run.json"
case " ${STUB_FAIL:-} " in *" $id "*) printf 'stub: %s told to fail\n' "$id" >&2; exit 1 ;; esac
EOF

# new_case NAME TICKET_BODY: a fresh workspace (a base commit, branch
# ticket/T checked out, as crew leaves it), the ticket file, OUT, and an
# empty call log. Sets ws, out, tf, calls, base.
new_case() {
  d="$work/$1"
  ws="$d/workspace"; out="$d/out"; tf="$d/ticket.md"; calls="$d/calls"
  mkdir -p "$ws" "$out"
  : > "$calls"
  git init -q "$ws"
  printf 'base\n' > "$ws/README"
  git -C "$ws" add -A
  git -C "$ws" -c user.name=t -c user.email=t@lights-out.invalid commit -q -m base
  base=$(git -C "$ws" rev-parse HEAD)
  git -C "$ws" checkout -q -b ticket/T
  printf '%s\n' "$2" > "$tf"
}

# run_network AGENT_HARNESS STUB_PLAN [STUB_FAIL]: the adapter with crew's
# environment, from the scratch root. Sets rc; stderr in $d/err.
run_network() {
  rc=0
  (cd "$root" && AGENT_HARNESS="$1" STUB_PLAN="$2" STUB_FAIL="${3:-}" WORKLOAD=workload \
    ROLE=dev-worker TICKET=T TICKET_FILE="$tf" WORKSPACE="$ws" BASE="$base" OUT="$out" \
    THINKING=low MAX_TURNS=1 TIMEOUT_S=1 TOKEN_BUDGET=1 STUB_CALLS="$calls" \
    sh adapters/network/run.sh) >/dev/null 2>"$d/err" || rc=$?
}

commits() { git -C "$ws" rev-list --count "$base..HEAD"; }

two='# T: a two-member ticket

Spec text both members read.

## Perimeter

- src/*
- tests/*

## Network

### impl

Write the code.

- src/*

### tests

Write the tests from the spec.

- tests/*

## Notes

After the network.'

# a.
new_case a '# T: an ordinary ticket

## Perimeter

- src/*'
run_network stub 'T src/x'
[ "$rc" -eq 0 ] || nogo "a: a ticket without ## Network failed" "$(cat "$d/err")"
[ "$(cat "$calls")" = T ] || nogo "a: the member harness was not called once with TICKET=T" "$(cat "$calls")"
cmp -s "$tf" "$out/seen.md" || nogo "a: the member did not get the ticket file unchanged"
[ "$(jq -r .harness "$out/run.json")" = stub ] || nogo "a: run.json is not the member's own"
[ "$(commits)" -eq 1 ] || nogo "a: want 1 commit over base, got $(commits)"

# b.
new_case b "$two"
run_network stub 'impl src/code.py
tests tests/test_code.py'
[ "$rc" -eq 0 ] || nogo "b: two disjoint members failed" "$(cat "$d/err")"
[ "$(sort "$calls" | tr '\n' ' ')" = "T/impl T/tests " ] || nogo "b: members called: $(tr '\n' ' ' < "$calls")"
[ "$(git -C "$ws" log --reverse --format=%s "$base..HEAD" | tr '\n' ',')" = "stub impl,stub tests," ] \
  || nogo "b: integrated commits are not impl then tests" "$(git -C "$ws" log --oneline "$base..HEAD")"
[ "$(git -C "$ws" branch --show-current)" = ticket/T ] || nogo "b: the workspace left ticket/T"
for m in impl tests; do
  seen=$(find "$work/b" -path "*/$m/out/seen.md" | head -1)
  [ -n "$seen" ] || nogo "b: no input document recorded for member $m"
  mdir=$(dirname "$seen")
  [ "$(cat "$mdir/seen-commits")" -eq 0 ] || nogo "b: member $m started above the base"
  [ "$(cat "$mdir/seen-files")" = README ] || nogo "b: member $m saw files beyond the base" "$(cat "$mdir/seen-files")"
  grep -q 'Spec text both members read.' "$seen" || nogo "b: member $m did not get the ticket text"
  grep -q 'After the network.' "$seen" || nogo "b: member $m lost the sections after ## Network"
  globs=$(awk '/^## Perimeter/{f=1;next} f&&/^## /{exit} f&&/^- /{print}' "$seen" | tr -d '`' | tr '\n' ' ')
  [ "$globs" = "- $(if [ "$m" = impl ]; then echo src; else echo tests; fi)/* " ] \
    || nogo "b: member $m's first ## Perimeter is not its own part" "$globs"
done
grep -q 'Write the code.' "$(find "$work/b" -path '*/impl/out/seen.md')" || nogo "b: impl did not get its brief"
grep -q 'Write the code.' "$(find "$work/b" -path '*/tests/out/seen.md')" && nogo "b: tests got impl's brief"
sh core/harness-check.sh "$out" "$ws" "$base" 2>"$d/check" || nogo "b: the artefacts fail core/harness-check.sh" "$(cat "$d/check")"
[ "$(jq -r .title "$out/pr.json")" = "T: a two-member ticket" ] || nogo "b: pr.json title is $(jq -r .title "$out/pr.json")"
[ "$(jq -r .harness "$out/run.json")" = network ] || nogo "b: run.json harness is not network"
[ "$(jq -r '[.members[].id] | join(",")' "$out/run.json")" = impl,tests ] || nogo "b: run.json members" "$(cat "$out/run.json")"
[ "$(jq -r .model "$out/run.json")" = stub-model ] || nogo "b: members agreeing on a model, run.json model is $(jq -r .model "$out/run.json")"
[ -s "$out/final.md" ] || nogo "b: no final.md"

# c.
new_case c "$two"
run_network stub 'impl src/code.py
tests tests/test_code.py
tests src/code_peek.py'
[ "$rc" -ne 0 ] || nogo "c: a test-writer that edits the code was not refused"
if ! grep -q tests "$d/err" || ! grep -q 'src/code_peek.py' "$d/err"; then
  nogo "c: the refusal does not name the member and the path" "$(cat "$d/err")"
fi
[ "$(commits)" -eq 0 ] || nogo "c: a refused network integrated $(commits) commit(s)"

# d.
new_case d '# T: two members, one path

## Perimeter

- src/*

## Network

### one

- src/*.py

### two

- src/a*'
run_network stub 'one src/a.py
two src/a.py'
[ "$rc" -ne 0 ] || nogo "d: one path changed by two members was not refused"
if ! grep -q 'src/a.py' "$d/err" || ! grep -q 'two members' "$d/err"; then
  nogo "d: the refusal does not name the path as changed by two members" "$(cat "$d/err")"
fi
[ "$(commits)" -eq 0 ] || nogo "d: a refused network integrated $(commits) commit(s)"

# e.
new_case e '# T: overlapping parts

## Perimeter

- src/*

## Network

### one

- src/*

### two

- src/x.py'
run_network stub ''
[ "$rc" -ne 0 ] || nogo "e: overlapping perimeters were not refused"
[ ! -s "$calls" ] || nogo "e: a member ran before the overlap was refused"

# f.
new_case f "$two"
run_network stub 'impl src/code.py
tests tests/test_code.py' tests
[ "$rc" -ne 0 ] || nogo "f: a failed member was not refused"
grep -q tests "$d/err" || nogo "f: the refusal does not name the failed member" "$(cat "$d/err")"
[ "$(commits)" -eq 0 ] || nogo "f: a refused network integrated $(commits) commit(s)"

# g.
five='# T: five members

## Perimeter

- *

## Network'
for m in m1 m2 m3 m4 m5; do
  five="$five

### $m

- $m/*"
done
new_case g "$five"
run_network stub ''
[ "$rc" -ne 0 ] || nogo "g: five members were not refused"
[ ! -s "$calls" ] || nogo "g: a member ran before five members were refused"

# h.
new_case h "$two"
run_network network ''
[ "$rc" -ne 0 ] || nogo "h: AGENT_HARNESS=network was not refused"
[ ! -s "$calls" ] || nogo "h: a member ran under AGENT_HARNESS=network"

go
