#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-intake: the intake interview before the ticket (docs/adr/0090 §1-§6),
# cold: no plane, no socket, no key. Written from that ADR, not from
# core/intake.py or the steps. File-backed StateStore and EventBus stubs,
# the role on its own harness at L0 (replay), a temp root.
#   a. `core/intake.py new` writes tickets/<id>.intake.md byte for byte with
#      one final newline, refuses an id whose <id>.md or <id>.intake.md
#      exists, and empty text; core/spec.py's next id skips an intake's id.
#   b. `core/tower.sh intake` writes the document at `intake` (INTAKE_BY and
#      INTAKE_VIA default to unauthenticated and cli), one history entry,
#      requests `interview`; a missing file or an existing document is refused.
#   c. At L0, an intake nobody recorded (the fixture's words plus one line):
#      the `interview` step fails, the state stays `intake`, the failure
#      names the missing recording, and `resume` requests `interview` again.
#      Then the fixture intake (fixtures/intake/request.md); with its
#      recording, the whole flow:
#      interview, every question answered, proposal, perimeter,
#      confirmation, each confirmed ticket through the unchanged spec gate.
#      stderr says which of the two was proved.
#   g. The turn cap (docs/adr/0090, Amendment 2026-11-14): a planted
#      architect recording longer than ADK_MAX_TURNS for a drafted intake's
#      proposal makes `perimeter` fail, the state stays `drafted`, the
#      failure names ADK_MAX_TURNS and nothing is proposed or published;
#      a planted recording at the cap proposes. The plants live in a copy
#      of fixtures/adk (ADK_FIXTURES), never under the repo's.
#   h. The scope (docs/adr/0090, Amendment 2026-11-14, second): the perimeter
#      step needs WORKLOAD, the directory the architect may search: with it
#      unset, on a drafted intake, the step fails, the state stays `drafted`
#      and the failure names WORKLOAD. Every other call that reaches the
#      perimeter step passes WORKLOAD=$repo/app, inside the repository.
#   d. The table: `perimeter` on an intake not at `drafted` is ignored;
#      `answer` on an intake at `intake-questions` records who, how and when
#      and requests `intake-answer`; on a ticket at `questions` it still
#      requests `answer`.
#   e. `intake-confirm` (§5): confirm, drop, edit -> two ticket files with
#      the next free ids, two documents at `spec-ready` with `spec`
#      requested, the intake `confirmed` with each decision; refused with
#      nothing written or published: wrong length, unknown entry, wrong state.
#   i. The perimeter asked file by file (docs/adr/0091 §6): PERIMETER_BY=decide
#      wins over the role's default (search); a stub Decide adapter fixes the
#      perimeter, the uncertain paths and the one request; exit 3 and more than
#      1000 questions fall back to the search, any other failure fails the step.
#   f. A step that exits 1 and writes no STEP_WHY is recorded `step exited 1`
#      exactly; one that writes a line there, `step exited 1: <line>` (§6).
set -eu
name=intake
. ci/lib.sh

for f in core/intake.py core/spec.py core/tower.sh gates/spec.sh fixtures/intake/request.md; do
  [ -f "$f" ] || nogo "$f not found"
done

repo=$(pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

root="$tmp/root"
mkdir -p "$root/adapters/stub-state" "$root/adapters/stub-bus" "$root/state" "$root/tickets" \
  "$root/tickets-e" "$root/fixtures"
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
: > "$root/bus.log"

TD=tickets
# tower ARGS...: in the temp root, the person-facing variables cleared so a
# default is a default.
tower() {
  (cd "$root" && env -u INTAKE_BY -u INTAKE_VIA -u CONFIRM_BY -u CONFIRM_VIA -u ANSWER -u ANSWER_BY -u DECISIONS -u WORKLOAD -u INTAKE_SCOPE -u PERIMETER_BY -u DECIDE_RECORD \
    DECIDE=replay DECIDE_FIXTURES="$tmp/no-decisions" STATE_STORE=stub-state EVENT_BUS=stub-bus TOWER_STEPS=core/steps TICKETS_DIR="$TD" \
    AGENT_HARNESS=replay WORKLOAD_REPO="$repo" "$@") 2>>"$tmp/tower.err"
}
doc() { cat "$root/state/tickets.$1.json"; }
last_published() { tail -n 1 "$root/bus.log"; }
bus_n() { awk 'END{print NR}' "$root/bus.log"; }
# want ID JQ-EXPR REASON: the document satisfies the expression.
want() {
  id=$1
  expr=$2
  shift 2
  doc "$id" | jq -e "$expr" >/dev/null || nogo "$*" "$(doc "$id" | jq -c .)"
}
# refused WHAT CMD...: the command fails, the bus and the tickets directory
# are as they were. The caller compares the document.
refused() {
  what=$1
  shift
  before=$(bus_n)
  files=$(find "$root/$TD" -type f | wc -l)
  if tower "$@"; then
    nogo "$what was accepted"
  fi
  [ "$(bus_n)" -eq "$before" ] || nogo "$what was refused but published $(last_published)"
  [ "$(find "$root/$TD" -type f | wc -l)" -eq "$files" ] || nogo "$what was refused but wrote a file"
}
has_line() { awk -v l="$2" '$0 == l { f = 1 } END { exit !f }' "$1"; }
step_of() { printf '{"ticket":"%s","step":"%s"}' "$1" "$2"; }
# run ID: apply the step the bus asked for last.
run() {
  step=$(last_published | jq -r .step)
  tower env WORKLOAD="$repo/app" sh core/tower.sh step "$1" "$step" || :
}
seed() { printf '%s\n' "$2" > "$root/state/tickets.$1.json"; printf 'a raw request\n' > "$root/$TD/$1.intake.md"; }

# --- a. the file --------------------------------------------------------------
new() { (cd "$root" && python3 core/intake.py new "$@") 2>>"$tmp/tower.err"; }
printf 'We need  seats back.\n\n  Second paragraph, no final newline' > "$tmp/raw.txt"
{ cat "$tmp/raw.txt"; printf '\n'; } > "$tmp/want.txt"
new "$tmp/raw.txt" tickets 0200 >/dev/null || nogo "core/intake.py new failed on a plain request" "$(tail -n 5 "$tmp/tower.err")"
cmp -s "$root/tickets/0200.intake.md" "$tmp/want.txt" || nogo "the intake file is not the text byte for byte with one final newline"
printf 'x\n' > "$root/tickets/0201.md"
if new "$tmp/raw.txt" tickets 0201 >/dev/null; then nogo "new accepted an id whose ticket exists"; fi
[ ! -e "$root/tickets/0201.intake.md" ] || nogo "new wrote an intake beside an existing ticket"
if new "$tmp/raw.txt" tickets 0200 >/dev/null; then nogo "new accepted an id whose intake exists"; fi
cmp -s "$root/tickets/0200.intake.md" "$tmp/want.txt" || nogo "a refused new changed the existing intake"
: > "$tmp/empty.txt"
if new "$tmp/empty.txt" tickets 0202 >/dev/null; then nogo "new accepted empty text"; fi
[ ! -e "$root/tickets/0202.intake.md" ] || nogo "new wrote a file for empty text"
mkdir "$tmp/ids"
: > "$tmp/ids/0001.md"
: > "$tmp/ids/0002.intake.md"
[ "$(python3 -c 'import sys; from core import spec; print(spec.next_id(sys.argv[1]))' "$tmp/ids")" = 0003 ] \
  || nogo "core/spec.py's next id does not skip an id taken by an .intake.md"
rm -f "$root/tickets/0200.intake.md" "$root/tickets/0201.md"

# --- b. the intake state ------------------------------------------------------
printf 'People cannot cancel.\n' > "$root/tickets/0210.intake.md"
tower sh core/tower.sh intake 0210 || nogo "core/tower.sh intake failed" "$(tail -n 5 "$tmp/tower.err")"
want 0210 '.id == "0210" and .kind == "intake" and .state == "intake"
  and .intake.by == "unauthenticated" and .intake.via == "cli" and (.intake.at | test("Z$"))
  and (.history | length) == 1 and .history[0].step == "intake" and .history[0].state == "intake"' \
  "the intake document is not {kind intake, state intake, intake {by, via, at}} with one history entry"
[ "$(last_published)" = "$(step_of 0210 interview)" ] || nogo "intake published '$(last_published)', want interview"
printf 'Another.\n' > "$root/tickets/0211.intake.md"
tower env INTAKE_BY=ci INTAKE_VIA=console sh core/tower.sh intake 0211 || nogo "core/tower.sh intake failed with INTAKE_BY"
want 0211 '.intake.by == "ci" and .intake.via == "console"' "INTAKE_BY and INTAKE_VIA are not recorded"
before=$(bus_n)
if tower sh core/tower.sh intake 0299; then nogo "intake accepted an id with no file"; fi
if tower sh core/tower.sh intake 0210; then nogo "intake accepted an id that has a document"; fi
[ "$(bus_n)" -eq "$before" ] || nogo "a refused intake published $(last_published)"
[ ! -f "$root/state/tickets.0299.json" ] || nogo "a refused intake wrote a document"

# --- d. the table -------------------------------------------------------------
before=$(bus_n)
snapshot=$(doc 0210)
tower sh core/tower.sh step 0210 perimeter || :
[ "$(doc 0210)" = "$snapshot" ] || nogo "perimeter on an intake at state intake changed the document"
[ "$(bus_n)" -eq "$before" ] || nogo "perimeter on an intake at state intake published $(last_published)"

seed 0221 '{"id":"0221","kind":"intake","state":"intake-questions","intake":{"by":"ci","via":"cli","at":"2026-11-14T10:00:00Z"},"questions":[{"question":"Who cancels?","from":"product","asked_at":"2026-11-14T10:00:00Z"}],"history":[{"step":"interview","state":"intake-questions","at":"2026-11-14T10:00:00Z","by":"ci","via":"cli"}]}'
tower env ANSWER="Members cancel their own seat." ANSWER_BY=ci sh core/tower.sh answer 0221 \
  || nogo "core/tower.sh answer failed on an intake with an open question" "$(tail -n 5 "$tmp/tower.err")"
want 0221 '.questions[-1] | .answer == "Members cancel their own seat." and .answered_by == "ci" and .answered_via == "cli" and (.answered_at | test("Z$"))' \
  "the answer to an intake is not recorded with who, how and when"
[ "$(last_published)" = "$(step_of 0221 intake-answer)" ] || nogo "an answer on an intake published '$(last_published)', want intake-answer"

cp fixtures/spec/go.md "$root/tickets/0222.md"
printf '%s\n' '{"id":"0222","state":"questions","questions":[{"question":"Which seat?","from":"product","asked_at":"2026-11-14T10:00:00Z"}],"history":[{"step":"clarify","state":"questions","at":"2026-11-14T10:00:00Z","by":"ci","via":"cli"}]}' > "$root/state/tickets.0222.json"
tower env ANSWER="The first." sh core/tower.sh answer 0222 || nogo "core/tower.sh answer failed on a ticket at questions"
[ "$(last_published)" = "$(step_of 0222 answer)" ] || nogo "an answer on a ticket published '$(last_published)', want answer"

# --- e. confirmation ----------------------------------------------------------
gwt='Given a member with a seat, when they cancel it, then the seat count of the meetup goes up by one'
prop3=$(jq -cn --arg c "$gwt" '[
  {n:1,title:"Give a seat back",problem:"A member cannot give a seat back.",criteria:[$c],feature:"waitlist",priority:"P1",perimeter:["app/meetups.py"],check:"GO: spec"},
  {n:2,title:"Dropped one",problem:"p",criteria:[$c],feature:null,priority:null,perimeter:["app/y.py"],check:"GO: spec"},
  {n:3,title:"Show who is coming",problem:"The organiser cannot see who is coming.",criteria:[$c],feature:null,priority:null,perimeter:[],check:"NO-GO: spec — Perimeter declares no path"}]')
proposed() {
  jq -cn --argjson p "$prop3" --arg id "$1" --arg st "$2" \
    '{id:$id,kind:"intake",state:$st,intake:{by:"ci",via:"cli",at:"2026-11-14T10:00:00Z"},proposal:$p,
      history:[{step:"perimeter",state:"proposed",at:"2026-11-14T10:00:00Z",by:"ci",via:"cli"}]}'
}
TD=tickets-e
: > "$root/$TD/0229.md"
seed 0230 "$(proposed 0230 proposed)"
before=$(bus_n)
tower env DECISIONS='["confirm","drop",{"edit":{"perimeter":["app/x.py"]}}]' sh core/tower.sh intake-confirm 0230 \
  || nogo "core/tower.sh intake-confirm failed" "$(tail -n 8 "$tmp/tower.err")"
[ -f "$root/$TD/0231.md" ] && [ -f "$root/$TD/0232.md" ] || nogo "the two kept tickets are not tickets 0231 and 0232 (the next free ids)" "$(ls "$root/$TD")"
[ ! -e "$root/$TD/0233.md" ] || nogo "the dropped ticket was written"
t1="$root/$TD/0231.md"
t2="$root/$TD/0232.md"
[ "$(sed -n 1p "$t1")" = "# 0231 — Give a seat back" ] || nogo "ticket 0231 does not start with '# 0231 — <title>': $(sed -n 1p "$t1")"
# shellcheck disable=SC2016 # backticks and $STEP_WHY are literal text here
for l in '- Status: open' '- Intake: 0230' '- Feature: waitlist' '- Priority: P1' '## Problem' '## Acceptance criteria' '## Perimeter' '- `app/meetups.py`' "$gwt"; do
  has_line "$t1" "$l" || nogo "ticket 0231 has no line '$l'" "$(cat "$t1")"
done
[ "$(sed -n 1p "$t2")" = "# 0232 — Show who is coming" ] || nogo "ticket 0232 does not start with '# 0232 — <title>'"
# shellcheck disable=SC2016 # backticks and $STEP_WHY are literal text here
has_line "$t2" '- `app/x.py`' || nogo "the edit's perimeter is not in ticket 0232" "$(cat "$t2")"
has_line "$t2" '- Intake: 0230' || nogo "ticket 0232 has no '- Intake: 0230'"
awk '/^- (Feature|Priority):/ { f = 1 } END { exit f }' "$t2" || nogo "ticket 0232 has a Feature or Priority line it was not given"
for t in 0231 0232; do
  want "$t" '.state == "spec-ready" and .intake == "0230" and .spec.by == "intake" and (.spec.criteria | length) > 0
    and (.history | length) == 1 and .history[0].step == "request" and .history[0].state == "spec-ready"
    and .history[0].intake == "0230" and (.history[0].by | length) > 0 and (.history[0].via | length) > 0 and (.history[0].at | test("Z$"))' \
    "confirmed ticket $t is not at spec-ready with spec.by intake and its one history entry"
done
[ "$(bus_n)" -eq $((before + 2)) ] || nogo "confirmation published $(( $(bus_n) - before )) events, want the two spec requests"
[ "$(tail -n 2 "$root/bus.log" | LC_ALL=C sort | tr '\n' ' ')" = "$(step_of 0231 spec) $(step_of 0232 spec) " ] \
  || nogo "confirmation did not request spec for 0231 and 0232: $(tail -n 2 "$root/bus.log" | tr '\n' ' ')"
want 0230 '.state == "confirmed"
  and .proposal[0].decision == "confirm" and .proposal[0].ticket == "0231"
  and .proposal[1].decision == "drop" and .proposal[1].ticket == null
  and .proposal[2].decision == "edit" and .proposal[2].ticket == "0232"
  and .confirmation.by == "unauthenticated" and .confirmation.via == "cli" and (.confirmation.at | test("Z$"))
  and (.tickets | length) == 2 and .history[-1].step == "confirm" and .history[-1].state == "confirmed"' \
  "the intake is not confirmed with each decision, its tickets and who confirmed"

# CONFIRM_BY, CONFIRM_VIA and DECISIONS=@file; dropping everything is a confirmation.
seed 0240 "$(proposed 0240 proposed)"
printf '["drop","drop","drop"]\n' > "$tmp/decisions.json"
before=$(bus_n)
files=$(find "$root/$TD" -type f | wc -l)
tower env DECISIONS="@$tmp/decisions.json" CONFIRM_BY=ci CONFIRM_VIA=console sh core/tower.sh intake-confirm 0240 \
  || nogo "intake-confirm failed with DECISIONS=@file" "$(tail -n 5 "$tmp/tower.err")"
want 0240 '.state == "confirmed" and .confirmation.by == "ci" and .confirmation.via == "console" and (.tickets | length) == 0
  and ([.proposal[] | select(.decision == "drop" and .ticket == null)] | length) == 3' \
  "dropping every ticket is not a confirmation with no ticket, or CONFIRM_BY and CONFIRM_VIA are not recorded"
[ "$(bus_n)" -eq "$before" ] || nogo "dropping every ticket published $(last_published)"
[ "$(find "$root/$TD" -type f | wc -l)" -eq "$files" ] || nogo "dropping every ticket wrote a ticket"

# Refused: nothing written, nothing published.
seed 0250 "$(proposed 0250 proposed)"
snapshot=$(doc 0250)
refused "a decisions list of the wrong length" env DECISIONS='["confirm","confirm"]' sh core/tower.sh intake-confirm 0250
refused "an unknown decision" env DECISIONS='["confirm","confirm","keep"]' sh core/tower.sh intake-confirm 0250
[ "$(doc 0250)" = "$snapshot" ] || nogo "a refused confirmation changed the intake"
seed 0251 "$(proposed 0251 drafted)"
snapshot=$(doc 0251)
refused "a confirmation of an intake at drafted" env DECISIONS='["confirm","confirm","confirm"]' sh core/tower.sh intake-confirm 0251
[ "$(doc 0251)" = "$snapshot" ] || nogo "a refused confirmation changed the intake at drafted"
TD=tickets

# --- f. a step may name its reason --------------------------------------------
mkdir "$tmp/steps-f"
printf '#!/bin/sh\nprintf "boom\\n" >&2\nexit 1\n' > "$tmp/steps-f/interview.sh"
# shellcheck disable=SC2016 # backticks and $STEP_WHY are literal text here
printf '#!/bin/sh\nprintf "because the stub says so\\n" > "$STEP_WHY"\nexit 1\n' > "$tmp/steps-f/interview-why.sh"
printf 'A request.\n' > "$root/tickets/0260.intake.md"
tower sh core/tower.sh intake 0260 || nogo "core/tower.sh intake failed on 0260"
tower env TOWER_STEPS="$tmp/steps-f" sh core/tower.sh step 0260 interview || :
want 0260 '.state == "intake" and .history[-1].error == "step exited 1"' \
  "a step that exits 1 without STEP_WHY is not recorded as exactly 'step exited 1'"
printf 'A request.\n' > "$root/tickets/0261.intake.md"
tower sh core/tower.sh intake 0261 || nogo "core/tower.sh intake failed on 0261"
cp "$tmp/steps-f/interview-why.sh" "$tmp/steps-f/interview.sh"
tower env TOWER_STEPS="$tmp/steps-f" sh core/tower.sh step 0261 interview || :
want 0261 '.state == "intake" and .history[-1].error == "step exited 1: because the stub says so"' \
  "a step that writes STEP_WHY is not recorded as 'step exited 1: <line>'"

# --- c. the fixture intake at L0 ----------------------------------------------
key=$(python3 - "$repo/fixtures/intake/request.md" <<'PY'
import hashlib, sys
text = "# Intake request\n\n" + open(sys.argv[1], encoding="utf-8").read()
print(hashlib.sha256(text.strip().encode()).hexdigest())
PY
)
recording="$repo/fixtures/adk/product/$key.json"

# The refusal holds for any intake nobody recorded, whether or not the
# fixture's own recording exists: the fixture's words with one more line.
{ cat fixtures/intake/request.md; printf 'This line was never recorded.\n'; } > "$root/tickets/0401.intake.md"
tower sh core/tower.sh intake 0401 || nogo "core/tower.sh intake failed on an unrecorded intake" "$(tail -n 5 "$tmp/tower.err")"
tower sh core/tower.sh step 0401 interview || :
want 0401 '.state == "intake"' "an intake with no recording left state intake: it is not stranded at intake"
want 0401 '.history[-1].error | startswith("step exited 1: ")' \
  "the failed interview is not recorded as 'step exited 1: <reason>'"
want 0401 '.history[-1].error | test("no recording")' "the failure does not name the missing recording"
want 0401 '[.proposal // [] | .[]] | length == 0' "an intake with no recording was proposed tickets"
tower sh core/tower.sh resume 0401 || nogo "core/tower.sh resume failed on the stranded intake" "$(tail -n 5 "$tmp/tower.err")"
[ "$(last_published)" = "$(step_of 0401 interview)" ] || nogo "resume published '$(last_published)', want interview"

# --- g. the turn cap ----------------------------------------------------------
# A drafted intake whose proposal has one ticket; the architect's replay key is
# the canonical sha256 of what `core/intake.py proposal` prints for it, the key
# the step itself computes (adapters/adk/lights_out_adk/replay.py).
fx="$tmp/adk-fixtures"
mkdir -p "$fx"
cp -R "$repo/fixtures/adk/." "$fx/"
rm -rf "${fx:?}/architect"
mkdir -p "$fx/architect"
drafted() {
  jq -cn --arg id "$1" --arg title "$2" --arg c "$gwt" \
    '{id:$id,kind:"intake",state:"drafted",intake:{by:"ci",via:"cli",at:"2026-11-14T10:00:00Z"},
      proposal:[{n:1,title:$title,problem:"A member cannot give a seat back.",criteria:[$c],feature:null,priority:null}],
      history:[{step:"interview",state:"drafted",at:"2026-11-14T10:00:00Z",by:"ci",via:"cli"}]}'
}
# plant ID TURNS: an architect recording of TURNS responses for ID's proposal;
# the last is text, the one before it proposes ticket 1's perimeter, the
# others search the map: a conversation that really runs TURNS turns.
plant() {
  (cd "$root" && python3 core/intake.py proposal "state/tickets.$1.json") > "$tmp/proposal-$1.json"
  python3 - "$tmp/proposal-$1.json" "$fx/architect" "$2" "$repo/adapters/adk" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[4])
from lights_out_adk.replay import canonical, key_for
text = open(sys.argv[1], encoding="utf-8").read()
turns = int(sys.argv[3])
call = {"function_call": {"name": "propose_perimeter", "args": {"ticket": 1, "paths": ["app/meetups.py"]}}}
search = {"function_call": {"name": "find_files", "args": {"queries": ["meetups"]}}}
responses = [{"content": {"role": "model", "parts": [search]}} for _ in range(turns)]
responses[-2:] = [{"content": {"role": "model", "parts": [call]}}, {"content": {"role": "model", "parts": [{"text": "done"}]}}]
rec = {"input": canonical(text), "model": "planted", "provider": "gemini", "responses": responses}
with open(f"{sys.argv[2]}/{key_for(text)}.json", "w", encoding="utf-8") as fh:
    fh.write(json.dumps(rec))
PY
}
seed 0410 "$(drafted 0410 "Over the cap")"
plant 0410 11
before=$(bus_n)
snapshot=$(doc 0410)
if tower env WORKLOAD="$repo/app" ADK_FIXTURES="$fx" sh core/tower.sh step 0410 perimeter; then
  nogo "an architect recording over ADK_MAX_TURNS was replayed: the perimeter step succeeded"
fi
want 0410 '.state == "drafted"' "a recording over its cap moved the intake out of drafted"
want 0410 '.history[-1] | .step == "perimeter" and (.error | test("ADK_MAX_TURNS"))' \
  "the failure of an over-cap recording does not name ADK_MAX_TURNS"
want 0410 '[.proposal[] | select(has("check") or has("perimeter"))] | length == 0' "an over-cap recording proposed a perimeter"
want 0410 '.architect == null' "an over-cap recording was recorded as the architect's answer"
[ "$(doc 0410 | jq -c .proposal)" = "$(printf '%s' "$snapshot" | jq -c .proposal)" ] || nogo "an over-cap recording changed the proposal"
[ "$(bus_n)" -eq "$before" ] || nogo "an over-cap recording published $(last_published)"
# The same step over a recording at the cap proposes: the gate can pass.
seed 0411 "$(drafted 0411 "Under the cap")"
plant 0411 10
tower env WORKLOAD="$repo/app" ADK_FIXTURES="$fx" sh core/tower.sh step 0411 perimeter \
  || nogo "an architect recording at ADK_MAX_TURNS=10 was refused" "$(tail -n 5 "$tmp/tower.err")"
want 0411 '.state == "proposed" and .architect.consulted == true and .proposal[0].perimeter == ["app/meetups.py"]' \
  "a recording at the cap did not propose its perimeter"

# --- h. the scope -------------------------------------------------------------
seed 0420 "$(drafted 0420 "No workload")"
before=$(bus_n)
if tower sh core/tower.sh step 0420 perimeter; then
  nogo "the perimeter step succeeded with WORKLOAD unset"
fi
want 0420 '.state == "drafted"' "the perimeter step with WORKLOAD unset moved the intake out of drafted"
want 0420 '.history[-1] | .step == "perimeter" and (.error | test("WORKLOAD"))' \
  "the failure of the perimeter step with WORKLOAD unset does not name WORKLOAD"
[ "$(bus_n)" -eq "$before" ] || nogo "the perimeter step with WORKLOAD unset published $(last_published)"

# --- i. the perimeter asked file by file (docs/adr/0091 §6) -------------------
# PERIMETER_BY=decide in the environment wins over roles/architect/role.env
# (search). A stub Decide adapter answers each yes_no question from the path
# quoted in backticks in its instructions: app/backend/meetups/app.py 0.95,
# app/backend/tests/test_meetups.py 0.6, any other 0.05 (policy/decide.env:
# PERIMETER_CONFIDENCE=0.7: 0.6 is uncertain, 0.95 and 0.05 are not).
mkdir -p "$root/adapters/stub-decide" "$root/ctl" "$root/fixtures/decide"
ln -s "$repo/policy" "$root/policy"
[ ! -d "$repo/profiles" ] || ln -s "$repo/profiles" "$root/profiles"
cat > "$root/adapters/stub-decide/decide.sh" <<'STUB'
set -eu
cat > ctl/last.json
echo call >> ctl/calls
mode=ok
[ ! -f ctl/mode ] || mode=$(cat ctl/mode)
case "$mode" in
  exit1) echo "stub decide failed" >&2; exit 1 ;;
  exit3) echo "no recording of this decision at L0 (fixtures/decide/stub.json); record it at L1 with DECIDE_RECORD=1" >&2; exit 3 ;;
esac
exec python3 adapters/stub-decide/answer.py < ctl/last.json
STUB
cat > "$root/adapters/stub-decide/answer.py" <<'STUB'
import json, re, sys
req = json.load(sys.stdin)
answers = {}
for k, q in req["questions"].items():
    m = re.search(r"`([^`]+)`", q["instructions"])
    path = m.group(1) if m else ""
    if path == "app/backend/meetups/app.py":
        p = 0.95
    elif path == "app/backend/tests/test_meetups.py":
        p = 0.6
    else:
        p = 0.05
    answers[k] = {"type": "yes_no", "p_yes": p, "confidence": max(p, 1 - p)}
print(json.dumps({"answers": answers, "adapter": "stub-decide", "provider": "stub", "model": "stub",
                  "tokens": {"input": 100, "output": 0}, "duration_s": 0.01}))
STUB
: > "$root/ctl/calls"
dcalls() { awk 'END{print NR}' "$root/ctl/calls"; }
dmode() { printf '%s' "$1" > "$root/ctl/mode"; }
drafted_n() { # ID N: a drafted intake proposing N tickets
  jq -cn --arg id "$1" --argjson n "$2" --arg c "$gwt" \
    '{id:$id,kind:"intake",state:"drafted",intake:{by:"ci",via:"cli",at:"2026-11-14T10:00:00Z"},
      proposal:[range($n) | {n:(.+1),title:"Ticket \(.+1)",problem:"A member cannot give a seat back.",criteria:[$c],feature:null,priority:null}],
      history:[{step:"interview",state:"drafted",at:"2026-11-14T10:00:00Z",by:"ci",via:"cli"}]}'
}
decided() { tower env WORKLOAD="$repo/app" PERIMETER_BY=decide DECIDE=stub-decide "$@"; }

dmode ok
seed 0430 "$(drafted_n 0430 2)"
before=$(bus_n)
n0=$(dcalls)
decided sh core/tower.sh step 0430 perimeter \
  || nogo "the perimeter step with PERIMETER_BY=decide failed" "$(tail -n 8 "$tmp/tower.err")"
perimeter_ok='.state == "proposed" and .architect.by == "decide" and .architect.consulted == true
  and (.proposal | length) == 2
  and all(.proposal[]; (.perimeter | index("app/backend/meetups/app.py") != null)
    and (.perimeter | index("app/backend/tests/test_meetups.py") == null)
    and (.uncertain | index("app/backend/tests/test_meetups.py") != null)
    and (.uncertain | index("app/backend/meetups/app.py") == null)
    and ([.perimeter[] | select(. != "app/backend/meetups/app.py")] | length) == 0)'
want 0430 "$perimeter_ok" \
  "PERIMETER_BY=decide did not propose each ticket's perimeter from the 0.95 path and list the 0.6 path as uncertain"
[ "$(dcalls)" -eq $((n0 + 1)) ] || nogo "the perimeter step made $(( $(dcalls) - n0 )) Decide requests, want exactly 1"
python3 - "$root/ctl/last.json" <<'PY' || nogo "the perimeter's Decide request is not one yes_no question t<n>-f<i> per ticket and file"
import json, re, sys
req = json.load(open(sys.argv[1], encoding="utf-8"))
keys = list(req["questions"])
ok = (len(keys) > 2 and all(re.fullmatch(r"t[12]-f[0-9]+", k) for k in keys)
      and all(q["type"] == "yes_no" for q in req["questions"].values())
      and any(k.startswith("t1-") for k in keys) and any(k.startswith("t2-") for k in keys))
sys.exit(0 if ok else 1)
PY
# The check can fail: a planted proposal where an 0.6 path sits in the perimeter, or a missing uncertain.
rejects_i() { if printf '%s' "$1" | jq -e "$perimeter_ok" > /dev/null 2>&1; then nogo "the check for '$2' accepts a planted wrong proposal"; fi; }
rejects_i "$(doc 0430 | jq -c '.proposal[0].perimeter += ["app/backend/tests/test_meetups.py"]')" "an uncertain path in the perimeter"
rejects_i "$(doc 0430 | jq -c '.proposal[1].uncertain = []')" "no uncertain path"
rejects_i "$(doc 0430 | jq -c '.architect.by = "search"')" "architect.by search"

# The environment wins over the role's default; with it unset the step searches (no Decide call).
seed 0431 "$(drafted_n 0431 1)"
plant 0431 10
n0=$(dcalls)
tower env WORKLOAD="$repo/app" DECIDE=stub-decide ADK_FIXTURES="$fx" sh core/tower.sh step 0431 perimeter \
  || nogo "the default perimeter step (search) failed with a planted recording" "$(tail -n 5 "$tmp/tower.err")"
[ "$(dcalls)" -eq "$n0" ] || nogo "the perimeter step asked Decide without PERIMETER_BY=decide"
want 0431 '.architect.by != "decide"' "the perimeter step was by decide without PERIMETER_BY=decide"

# Exit 3 (no recording at L0): the step searches as before and says so.
dmode exit3
seed 0432 "$(drafted_n 0432 1)"
plant 0432 10
n0=$(dcalls)
err0=$(wc -c < "$tmp/tower.err")
decided env ADK_FIXTURES="$fx" sh core/tower.sh step 0432 perimeter \
  || nogo "the perimeter step did not fall back to search when Decide had no recording" "$(tail -n 5 "$tmp/tower.err")"
tail -c +"$((err0 + 1))" "$tmp/tower.err" > "$tmp/run-i.err"
[ "$(dcalls)" -eq $((n0 + 1)) ] || nogo "the perimeter step did not ask Decide before falling back"
want 0432 '.state == "proposed" and .architect.consulted == true and .architect.by != "decide" and .proposal[0].perimeter == ["app/meetups.py"]' \
  "after exit 3 the step did not propose what the search found"
awk 'tolower($0) ~ /search/ && tolower($0) ~ /(decide|record)/ { f = 1 } END { exit !f }' "$tmp/run-i.err" \
  || nogo "the fallback to search after exit 3 is not said on stderr" "$(cat "$tmp/run-i.err")"

# Any other failure fails the step, with its line; the state stays drafted.
dmode exit1
seed 0433 "$(drafted_n 0433 1)"
plant 0433 10
before=$(bus_n)
if decided env ADK_FIXTURES="$fx" sh core/tower.sh step 0433 perimeter; then
  nogo "the perimeter step succeeded although the Decide adapter failed"
fi
want 0433 '.state == "drafted" and (.history[-1].error | startswith("step exited 1: "))' "a failed Decide did not leave the intake at drafted with 'step exited 1: <line>'"
want 0433 '.history[-1].error | contains("stub decide failed")' "the failure line of the Decide adapter is not recorded"
want 0433 '.architect == null' "a failed Decide was recorded as the architect's answer"
[ "$(bus_n)" -eq "$before" ] || nogo "a failed Decide published $(last_published)"

# More than 1000 questions (60 tickets x the map's files): no call, the search.
dmode ok
seed 0434 "$(drafted_n 0434 60)"
plant 0434 10
n0=$(dcalls)
err0=$(wc -c < "$tmp/tower.err")
decided env ADK_FIXTURES="$fx" sh core/tower.sh step 0434 perimeter \
  || nogo "the perimeter step did not search when the questions exceed 1000" "$(tail -n 5 "$tmp/tower.err")"
tail -c +"$((err0 + 1))" "$tmp/tower.err" > "$tmp/run-i.err"
[ "$(dcalls)" -eq "$n0" ] || nogo "the perimeter step asked Decide with more than 1000 questions"
want 0434 '.state == "proposed" and .architect.by != "decide"' "with more than 1000 questions the step did not search as before"
awk 'tolower($0) ~ /search/ { f = 1 } END { exit !f }' "$tmp/run-i.err" \
  || nogo "the fallback to search over the 1000-question limit is not said on stderr" "$(cat "$tmp/run-i.err")"

cp fixtures/intake/request.md "$root/tickets/0400.intake.md"
# At L0 the demo intake's perimeter replays its recording (docs/adr/0091 §5):
# the proposal the architect's recording holds, the questions over this
# checkout's app/, DECIDE=replay on the repository's fixtures/decide. The
# recording holds every candidate path: a file added to or removed from app/
# changes its key, and this case then says so and proves the fallback.
python3 - "$repo/fixtures/adk/architect" > "$tmp/demo-proposal.json" <<'PY'
import glob, json, sys
recs = sorted(glob.glob(sys.argv[1] + "/*.json"))
print(json.dumps(json.loads(json.load(open(recs[0], encoding="utf-8"))["input"])))
PY
seed 0435 "$(jq -c '{id:"0435",kind:"intake",state:"drafted",intake:{by:"ci",via:"cli",at:"2026-11-16T10:00:00Z"},
  proposal:., history:[{step:"interview",state:"drafted",at:"2026-11-16T10:00:00Z",by:"ci",via:"cli"}]}' "$tmp/demo-proposal.json")"
: > "$tmp/run-r.err"
tower env WORKLOAD="$repo/app" PERIMETER_BY=decide DECIDE=replay DECIDE_FIXTURES="$repo/fixtures/decide" \
  sh core/tower.sh step 0435 perimeter 2> "$tmp/run-r.err" \
  || nogo "the demo intake's perimeter did not replay at L0" "$(tail -n 5 "$tmp/run-r.err")"
if doc 0435 | jq -e '.architect.by == "decide"' > /dev/null; then
  want 0435 '.state == "proposed" and .architect.replayed == true and (.architect.tokens.input == 0)
    and ([.proposal[] | .perimeter | index("app/backend/meetups/app.py")] | all(. != null))
    and ([.proposal[] | .uncertain | length > 0] | all)
    and ([.proposal[] | (.perimeter | length) as $n | $n > 0 and $n < 10] | all)' \
    "the replayed perimeter is not app.py in each ticket's perimeter with an uncertain list, replayed and costing nothing"
  printf 'intake: the demo intake perimeter replayed fixtures/decide (docs/adr/0091 §6)\n' >&2
else
  awk '/not recorded/ { f = 1 } END { exit !f }' "$tmp/run-r.err" \
    || nogo "the demo intake's perimeter neither replayed nor said why it searched" "$(cat "$tmp/run-r.err")"
  printf 'intake: the demo intake perimeter is not recorded for this app/ (its file list changed): proved the fallback\n' >&2
fi

tower sh core/tower.sh intake 0400 || nogo "core/tower.sh intake failed on the fixture intake" "$(tail -n 5 "$tmp/tower.err")"

if [ ! -f "$recording" ]; then
  printf 'intake: no recording of the fixture intake (%s): proved the L0 refusal only (docs/adr/0090 §4)\n' "$key" >&2
  go
fi

tower sh core/tower.sh step 0400 interview || :
asked_n=$(jq '[.responses[].content.parts[]? | .function_call | select(. != null and .name == "ask_product_owner")] | length' "$recording")
n=0
while [ "$(doc 0400 | jq -r .state)" = intake-questions ]; do
  n=$((n + 1))
  [ "$n" -le 5 ] || nogo "the interview asked more than five questions"
  q=$(doc 0400 | jq -r '.questions[-1].question')
  [ -n "$q" ] || nogo "the interview is waiting on an empty question"
  tower env ANSWER="Answer $n to: $q" ANSWER_BY=ci sh core/tower.sh answer 0400 \
    || nogo "core/tower.sh answer failed on the interview's question $n" "$(tail -n 5 "$tmp/tower.err")"
  want 0400 '.questions[-1] | .answered_by == "ci" and .answered_via == "cli" and (.answered_at | test("Z$"))' "answer $n is not recorded with who, how and when"
  [ "$(last_published)" = "$(step_of 0400 intake-answer)" ] || nogo "answer $n published '$(last_published)', want intake-answer"
  run 0400
done
[ "$n" -eq "$asked_n" ] || nogo "the interview asked $n questions, the recording holds $asked_n" "$(doc 0400 | jq -c '{state, error: .history[-1].error}')"
want 0400 '.state == "drafted" and (.proposal | length) > 0 and (.proposal | all(.title != "" and .problem != "" and (.criteria | length) > 0))' \
  "the interview did not end at drafted with a proposal of tickets with title, problem and criteria"
[ "$(last_published)" = "$(step_of 0400 perimeter)" ] || nogo "drafted published '$(last_published)', want perimeter"
run 0400
want 0400 '.state == "proposed" and (.proposal | all((.perimeter | type) == "array" and (.check | test("^(GO: spec|NO-GO: spec — )"))))' \
  "the perimeter step did not end at proposed with a perimeter and a check line on each ticket"
total=$(doc 0400 | jq '.proposal | length')
decisions=$(doc 0400 | jq -c '[.proposal[] | "confirm"]')
before=$(bus_n)
TD=tickets
tower env DECISIONS="$decisions" CONFIRM_BY=ci sh core/tower.sh intake-confirm 0400 \
  || nogo "core/tower.sh intake-confirm failed on the recorded proposal" "$(tail -n 8 "$tmp/tower.err")"
want 0400 '.state == "confirmed" and (.tickets | length) == (.proposal | length)' "the recorded proposal was not confirmed into one ticket each"
[ "$(bus_n)" -eq $((before + total)) ] || nogo "confirmation published $(( $(bus_n) - before )) events, want $total spec requests"
for t in $(doc 0400 | jq -r '.proposal[].ticket'); do
  want "$t" '.state == "spec-ready" and .spec.by == "intake" and .intake == "0400"' "confirmed ticket $t is not at spec-ready from the intake"
  tower sh core/tower.sh step "$t" spec || :
  line=$(doc "$t" | jq -r '.spec.line // ""')
  gate=$(cd "$root" && sh gates/spec.sh "tickets/$t.md" 2>/dev/null || :)
  [ "$line" = "$gate" ] || nogo "ticket $t's recorded spec line '$line' is not the gate's '$gate'"
  case "$line" in
    "GO: spec"*) want "$t" '.state == "opened"' "ticket $t passed the gate but is not opened" ;;
    "NO-GO: spec — "*) want "$t" '.state == "questions"' "ticket $t failed the gate but is not back at questions" ;;
    *) nogo "ticket $t has no spec verdict: '$line'" ;;
  esac
done
printf 'intake: the recording of the fixture intake exists: proved the full conversation (docs/adr/0090 §4)\n' >&2
go
