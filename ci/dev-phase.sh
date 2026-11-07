#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-dev-phase: the three states before the ticket and the spec gate
# (docs/adr/0055 §1-§4), cold: no plane, no socket, no key. Written from
# that ADR, not from core/spec.py or the steps.
#   a. gates/spec.sh on three committed specs: fixtures/spec/go.md is
#      `GO: spec`; vague.md (a Then that says "works correctly") and
#      no-perimeter.md are `NO-GO: spec — <reason>` naming the vague word
#      and the missing section. One stdout line each, exit 0 and 1.
#   b. The state table, through core/tower.sh and the real clarify, answer
#      and spec steps, with file-backed StateStore and EventBus stubs and
#      the product role on its own harness at L0 (replay):
#      - the product role's recorded request without criteria (its text
#        read from the recording, never retyped): requested → questions
#        with the recorded question; ./go answer's tower command records
#        who answered and requests `answer`; the recorded criteria make it
#        spec-ready; the spec gate says NO-GO (the recording declares no
#        perimeter) and the ticket is back at questions with the reason;
#      - a request nobody recorded, with its own criteria and perimeter:
#        clarify records product.consulted false and the reason, the spec
#        gate says GO, the ticket is opened and `assign` is requested;
#      - an answer with no open question records and requests nothing.
set -eu
name=dev-phase
. ci/lib.sh

for f in gates/spec.sh core/spec.py core/steps/clarify.sh core/steps/answer.sh core/steps/spec.sh \
  fixtures/spec/go.md fixtures/spec/vague.md fixtures/spec/no-perimeter.md; do
  [ -f "$f" ] || nogo "$f not found"
done

repo=$(pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# --- a. the gate --------------------------------------------------------------
# gate CASE WANT_RC WANT_PREFIX: one stdout line, the exit code, the line.
gate() {
  rc=0
  sh gates/spec.sh "fixtures/spec/$1.md" >"$tmp/out" 2>"$tmp/err" || rc=$?
  [ "$(awk 'END{print NR}' "$tmp/out")" -eq 1 ] || nogo "gates/spec.sh on $1.md printed $(awk 'END{print NR}' "$tmp/out") stdout lines, want 1" "$(cat "$tmp/out")"
  [ "$rc" -eq "$2" ] || nogo "gates/spec.sh on $1.md exited $rc, want $2" "$(cat "$tmp/out")"
  case "$(cat "$tmp/out")" in
    "$3"*) : ;;
    *) nogo "gates/spec.sh on $1.md said '$(cat "$tmp/out")', want '$3…'" ;;
  esac
}
gate go 0 "GO: spec"
[ "$(cat "$tmp/out")" = "GO: spec" ] || nogo "the GO case printed '$(cat "$tmp/out")', want exactly 'GO: spec'"
gate vague 1 "NO-GO: spec — "
grep -q '"works"' "$tmp/out" || nogo "the vague case does not name the vague word: $(cat "$tmp/out")"
gate no-perimeter 1 "NO-GO: spec — "
grep -q 'Perimeter' "$tmp/out" || nogo "the missing-perimeter case does not name the section: $(cat "$tmp/out")"

# --- b. the state table -------------------------------------------------------
root="$tmp/root"
mkdir -p "$root/adapters/stub-state" "$root/adapters/stub-bus" "$root/state" "$root/tickets" "$root/fixtures"
for d in core ci gates roles; do ln -s "$repo/$d" "$root/$d"; done
ln -s "$repo/adapters/adk" "$root/adapters/adk"
ln -s "$repo/fixtures/adk" "$root/fixtures/adk"
cat > "$root/adapters/stub-state/get.sh" <<'STUB'
set -eu
f="state/$1.$2.json"
[ -f "$f" ] || exit 1
cat "$f"
STUB
cat > "$root/adapters/stub-state/put.sh" <<'STUB'
set -eu
cat > "state/$1.$2.json"
STUB
cat > "$root/adapters/stub-bus/publish.sh" <<'STUB'
set -eu
printf '%s\n' "$1" >> bus.log
STUB

recording=$(python3 - "$repo/fixtures/adk/product" <<'PY'
import json, pathlib, sys
for p in sorted(pathlib.Path(sys.argv[1]).glob("*.json")):
    r = json.loads(p.read_text())
    if len(r["responses"]) == 4:
        print(p)
        break
PY
)
[ -n "$recording" ] || nogo "fixtures/adk/product holds no four-turn recording of the product role (docs/adr/0055 §3)"
jq -r '.input' "$recording" > "$root/tickets/0101.md"
cp fixtures/spec/go.md "$root/tickets/0102.md"
asked=$(jq -r '[.responses[].content.parts[]? | .function_call | select(. != null and .name == "ask_product_owner")][0].args.question' "$recording")

tower() {
  (cd "$root" && env STATE_STORE=stub-state EVENT_BUS=stub-bus TOWER_STEPS=core/steps TICKETS_DIR=tickets \
    AGENT_HARNESS=replay "$@") 2>>"$tmp/tower.err"
}
doc() { cat "$root/state/tickets.$1.json"; }
last_published() { tail -n 1 "$root/bus.log" 2>/dev/null; }
trail() { doc "$1" | jq -r '[.history[] | "\(.step)>\(.state)"] | join(",")'; }
# run TICKET: apply the step the bus asked for last.
run() {
  step=$(last_published | jq -r .step)
  tower sh core/tower.sh step "$1" "$step" || nogo "the $step step failed on ticket $1" "$(tail -n 20 "$tmp/tower.err")"
}

tower sh core/tower.sh request 0101 || nogo "core/tower.sh request failed" "$(cat "$tmp/tower.err")"
[ "$(doc 0101 | jq -r .state)" = requested ] || nogo "request did not write state requested"
[ "$(last_published)" = '{"ticket":"0101","step":"clarify"}' ] || nogo "request published '$(last_published)', want clarify"
run 0101
[ "$(doc 0101 | jq -r .state)" = questions ] || nogo "the recorded request without criteria ended clarify at $(doc 0101 | jq -r .state), want questions"
[ "$(doc 0101 | jq -r '.questions[-1].question')" = "$asked" ] || nogo "the open question is not the recorded one" "$(doc 0101 | jq -c .questions)"
[ "$(doc 0101 | jq -r '.product.consulted')" = true ] || nogo "the product role ran from its recording, but product.consulted is not true"
before=$(wc -l < "$root/bus.log")
[ "$(last_published | jq -r .step)" = clarify ] || nogo "questions requested a step: $(last_published); it waits for a person"
tower env ANSWER="Yes: the first on the list takes the seat." ANSWER_BY=ci sh core/tower.sh answer 0101 \
  || nogo "core/tower.sh answer failed on an open question" "$(tail -n 5 "$tmp/tower.err")"
[ "$(wc -l < "$root/bus.log")" -eq $((before + 1)) ] && [ "$(last_published | jq -r .step)" = answer ] \
  || nogo "answer did not request the answer step: $(last_published)"
doc 0101 | jq -e '.questions[-1] | .answer == "Yes: the first on the list takes the seat." and .answered_by == "ci" and .answered_via == "cli" and (.answered_at | test("Z$"))' >/dev/null \
  || nogo "the answer is not recorded with who, how and when" "$(doc 0101 | jq -c '.questions[-1]')"
run 0101
[ "$(doc 0101 | jq -r .state)" = spec-ready ] || nogo "the answered conversation ended at $(doc 0101 | jq -r .state), want spec-ready"
[ "$(doc 0101 | jq -r '.spec.by')" = product ] && [ "$(doc 0101 | jq '.spec.criteria | length')" -gt 0 ] \
  || nogo "spec-ready without the product role's criteria" "$(doc 0101 | jq -c .spec)"
[ "$(last_published | jq -r .step)" = spec ] || nogo "spec-ready requested '$(last_published)', want spec"
run 0101
[ "$(doc 0101 | jq -r .state)" = questions ] || nogo "a spec with no perimeter ended at $(doc 0101 | jq -r .state), want questions"
doc 0101 | jq -e '.spec.verdict == "NO-GO" and (.spec.line | startswith("NO-GO: spec — ")) and .questions[-1].from == "spec" and (.questions[-1].question | test("Perimeter"))' >/dev/null \
  || nogo "the spec gate's NO-GO is not the open question with its reason" "$(doc 0101 | jq -c '{spec, q: .questions[-1]}')"
want="request>requested,clarify>questions,answered>questions,answer>spec-ready,spec>questions"
[ "$(trail 0101)" = "$want" ] || nogo "ticket 0101's history is $(trail 0101), want $want"

tower sh core/tower.sh request 0102 || nogo "core/tower.sh request failed on 0102"
run 0102
doc 0102 | jq -e '.state == "spec-ready" and .product.consulted == false and (.product.why | length > 0) and .spec.by == "request"' >/dev/null \
  || nogo "a request with no recording at L0 is not spec-ready with product.consulted false and why" "$(doc 0102 | jq -c '{state, product, spec}')"
run 0102
[ "$(doc 0102 | jq -r .state)" = opened ] || nogo "a testable spec with a perimeter ended at $(doc 0102 | jq -r .state), want opened"
[ "$(doc 0102 | jq -r .spec.line)" = "GO: spec" ] || nogo "the spec step recorded '$(doc 0102 | jq -r .spec.line)', want GO: spec"
[ "$(last_published)" = '{"ticket":"0102","step":"assign"}' ] || nogo "opened requested '$(last_published)', want assign"
want="request>requested,clarify>spec-ready,spec>opened"
[ "$(trail 0102)" = "$want" ] || nogo "ticket 0102's history is $(trail 0102), want $want"

before=$(wc -l < "$root/bus.log")
if tower env ANSWER="late" sh core/tower.sh answer 0102; then
  nogo "an answer on an opened ticket was accepted"
fi
[ "$(wc -l < "$root/bus.log")" -eq "$before" ] || nogo "a refused answer published $(last_published)"
doc 0102 | jq -e '[.questions // [] | .[] | select(.answer == "late")] | length == 0' >/dev/null || nogo "a refused answer was recorded"

go
