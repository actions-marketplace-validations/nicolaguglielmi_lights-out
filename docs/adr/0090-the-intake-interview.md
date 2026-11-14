# ADR 0090 — The intake interview: a raw request, a guided conversation with `product`, proposed tickets with a perimeter from `architect`, and a person who confirms each one

- Status: proposed (M57)
- Date: 2026-11-14
- Milestone: M57 (docs/PLAN.md, "M57 — Il colloquio di intake (ADR 0090)")
- Amends: ADR 0055 §1 (the tower's table gains four states and three
  steps before `requested`; `answer` also answers an intake), §2 (the
  `product` role gains an agenda and a third decision), §3 (at L0 an
  intake without a recording is refused, not passed through), §6 (the
  logbook goes to 1.7); ADR 0059 §4 and ADR 0023 §2 (the console gains two
  writes, the intake and its confirmation, under the same checks); ADR
  0034 §1 (a failing step may name its reason).

## Context

Read in this checkout on 2026-11-14 (`land/sprint-1114`, 3924ebf):

- A ticket enters the tower at `requested` (ADR 0055), from `./go
  request` or from the console's editor (ADR 0059 §4). Either way a person
  has already written a ticket: a title, a Problem, Given/When/Then
  criteria and a `## Perimeter`. The `product` role reads that ticket,
  asks one question per turn (`ask_product_owner`) or confirms the
  criteria (`confirm_acceptance`). The spec gate (`gates/spec.sh`,
  `core/spec.py check`) judges the result, with no model.
- A client does not write tickets. A client writes "we need people to be
  able to leave a meetup they signed up for, and the organiser should
  know". Turning that into tickets is the work this harness does not
  record today. Four gaps:
  1. it starts from a drafted ticket, not from a raw request;
  2. one request is one ticket: nothing splits a request into several
     tickets with `- Feature:` and `- Priority:` (ADR 0055 §7);
  3. the person writes the perimeter by hand, although the project map
     (ADR 0054, `core/map.py`, 786 files on this repository at 3924ebf,
     built in 1.2 s) knows every path;
  4. at L0 only ticket 0005's conversation is recorded (two recordings,
     `fixtures/adk/product/`, 2026-09-16, Gemini).
- The replay model is keyed by the first user message and indexed by the
  model turns already in the conversation (ADR 0020 §2). The tool results
  are not part of the key: a replayed tool call runs the real tool, and
  the next recorded response follows whatever it returned.
- `RecordingLlm` (ADR 0020 §2) starts a fresh recording at model turn 0.
  The tower sends the whole conversation again on every run (ADR 0055
  §2). A live interview re-run under `ADK_RECORD=1` would call the model
  again for every earlier turn, and the model could ask a different first
  question from the one the person answered.
- The measured 0005 conversation (four model turns, Gemini 3.8 Flash,
  medium thinking) used 37,905 tokens in total; the first turn carried
  7,905 thinking tokens (`usage_metadata` of its recording).

## Decision

1. **An intake state before `requested`, in the tower's one table.**
   - `./go intake TICKET=<id> TEXT=<free text>` or `INTAKE_FILE=<path>`,
     with `INTAKE_BY` (default `unauthenticated`) and `INTAKE_VIA`
     (default `cli`), ADR 0047's rule. Without `TICKET`, the next free id.
   - `core/intake.py new <text file> <tickets dir> [<id>]` writes the raw
     text, byte for byte with one final newline, to
     `TICKETS_DIR/<id>.intake.md`, with an exclusive create. It refuses
     an id whose `<id>.md` or `<id>.intake.md` exists, and empty text.
     `core/spec.py`'s `next_id` counts `<id>.intake.md` too, so a request
     and an intake never take the same id. The file is the client's
     words; nothing else is written in it.
   - `core/tower.sh intake <id>` writes the document
     `{id, kind: "intake", state: "intake", intake: {by, via, at}, history:
     [{step: "intake", state: "intake", at, by, via}]}` and publishes
     `interview`. It refuses when the file is missing or a document with
     that id exists.
   - The steps, each with the one state it starts from (ADR 0019 §1):

     | step | from | to |
     |---|---|---|
     | `interview` | `intake` | `intake-questions` or `drafted` |
     | `intake-answer` | `intake-questions` | `intake-questions` or `drafted` |
     | `perimeter` | `drafted` | `proposed` |

     `NEXT` gains `intake → interview` and `drafted → perimeter`.
     `intake-questions` and `proposed` request nothing: they wait for a
     person. `confirmed` is terminal. The board's embedded table follows
     (ADR 0035, `ci/board.sh`).
   - The logic is Python (ADR 0084's direction): `core/intake.py`. The
     three step scripts (`core/steps/interview.sh`, `intake-answer.sh`,
     `perimeter.sh`) only run the role's harness and hand its output to
     it.

2. **The interview is the `product` role with an agenda, not a new
   role.**
   - The step sends `# Intake request`, a blank line and the raw text as
     the first user message, and every answer so far as a later user turn
     of the same conversation (ADR 0055 §2's mechanism). The key of a
     recording is then the raw text alone: neither the id nor who asked
     enters it.
   - `roles/product/prompt.md` gains the agenda, in this order: who uses
     it; the main scenario; what is out of scope; how we know it works;
     constraints. The role skips a topic the request already answers,
     asks one question per turn with `ask_product_owner`, and stops asking
     as soon as the request is clear.
   - **The cap: five questions.** Provenance, decision: this ADR's, one
     question per topic of the agenda. With five questions answered, the
     fifth answer is sent with one more sentence, "That was the last
     question this interview allows: propose the tickets now." A sixth
     `ask_product_owner` fails the step (§6): the cap is enforced by
     `core/intake.py`, not by the prompt.
   - **A third decision, `propose_ticket(title, problem, criteria,
     feature, priority)`**, called once per ticket, beside
     `confirm_acceptance`. Each argument is a string, but `criteria`, a
     list of strings, one Given/When/Then each: the shape the two
     existing tools have, which every provider's function declarations
     accept. `feature` and `priority` may be empty. One call per ticket,
     not one call with a list of objects: a list of objects needs a
     declared object schema per provider, a structure no role here has
     yet.
   - The run decides as ADR 0055 §2 does, by its calls: the
     `propose_ticket` calls after the last `ask_product_owner` are the
     proposal, in order, and the state becomes `drafted`; otherwise the
     last decision is `ask_product_owner`, appended to `questions` as
     `{question, from: "product", asked_at}`, and the state becomes
     `intake-questions`. A `confirm_acceptance` in an intake, no decision
     at all, an empty question, a proposed ticket without a title, a
     problem or a criterion: the step fails (§6).
   - `./go answer TICKET=<id> ANSWER=<text>` answers an intake as it
     answers a ticket: it also accepts `intake-questions`, records the
     same `{answer, answered_by, answered_via, answered_at}`, and
     publishes `intake-answer` instead of `answer`. The console's answer
     box does the same, under ADR 0055 §2's checks, against the open
     question the logbook shows on the intake.

3. **The perimeter is the `architect` role's proposal, from the map.**
   - The `perimeter` step builds the project map of `WORKLOAD_REPO` at
     HEAD into `.crew/<id>/intake/map.sqlite` (`core/map.py build`, ADR
     0054) and runs the `architect` role on the ADK harness with the
     proposal as its first message: a JSON list of `{n, title, problem,
     criteria}`, so the recording's key follows from the product's
     recording.
   - Two tools: `find_files(query)` returns at most 40 paths of the map's
     files, tests, pages and ADRs whose path contains `query`,
     case-insensitive; `propose_perimeter(ticket, paths)` names the paths
     of ticket `n`. The map is read through the tool, never in the
     message: a map in the message would change the key on every commit.
     Under replay the tool runs on today's map; the recorded paths are a
     proposal the person edits, and the spec gate only asks for one entry.
   - The architect's instruction for this is `roles/architect/
     perimeter.md`, beside its review prompt; `ci/prompts.sh` reads it as
     it reads every prompt. The role keeps its coding harness for the
     review (ADR 0021); proposing a perimeter is a conversation over the
     map, the shape of the ADK roles (ADR 0020 §1). The ADK agent is
     `adapters/adk/agents/architect`.
   - For each proposed ticket, the last `propose_perimeter` call naming
     it wins; a ticket no call names gets an empty perimeter. Each ticket
     is then composed as the draft it would become (§5) and checked by
     `gates/spec.sh`, the gate itself, before it is shown: its one line is
     `check` on the proposed ticket. The state becomes `proposed`.
   - At L0 with no recording for this proposal, the step does not fail:
     `architect: {consulted: false, why}`, every perimeter empty, every
     `check` the gate's NO-GO for a perimeter with no path. The person
     writes the paths at confirmation. ADR 0055 §3's rule, applied to the
     perimeter.

4. **At L0 an intake replays a recorded conversation, or is refused.**
   - With `AGENT_HARNESS=replay` and no recording of the interview, the
     `interview` step fails with one line: `no recording of this intake's
     interview at L0 (fixtures/adk/product); record it at L1 with ./go
     intake ... ADK_RECORD=extend, then ./go resume TICKET=<id>`. Nothing
     is proposed: unlike a ticket (ADR 0055 §3), a raw request has no
     criteria of its own to fall back on. `./go intake` prints `NO-GO:
     intake — ` and that line, and the intake stays at `intake`, stranded
     and resumable (ADR 0034 §2).
   - **`ADK_RECORD=extend`**, the recording mode of an interactive
     conversation: a model turn already in the recording is replayed, a
     new one is called live and appended. `ADK_RECORD=1` is unchanged
     (`./go record-evals` re-records from turn 0). Each turn of a live
     interview is then paid once, and the person always answers the
     question the recording holds.
   - **One recorded intake** in `fixtures/intake/request.md`: a raw
     request on the bundled meetup app that splits into two or three
     tickets. Its recordings are made by the owner (plan §7's rule, the
     M18 precedent: a fixture is never written by hand), with:

     ```
     ./go intake TICKET=<id> INTAKE_FILE=fixtures/intake/request.md PROFILE=l1 ADK_RECORD=extend
     ./go answer TICKET=<id> ANSWER=<text> PROFILE=l1 ADK_RECORD=extend   # once per question
     ```

     The cost estimate is in the M57 handoff; nothing is spent without
     the owner.
   - `./go ci` (`ci/intake.sh`) drives that intake through the tower
     when its recording exists, without a key: interview, every recorded
     question answered, proposal, perimeter, confirmation, and each
     confirmed ticket through the unchanged spec gate. Until the
     recording lands, it proves the refusal instead, and says on stderr
     which of the two it proved.

5. **A person confirms, edits or drops each proposed ticket.**
   - `./go intake-confirm TICKET=<id> DECISIONS=<json>` (or
     `DECISIONS=@<file>`), with `CONFIRM_BY` and `CONFIRM_VIA`. DECISIONS
     is a JSON list with one entry per proposed ticket, in order:
     `"confirm"`, `"drop"`, or `{"edit": {...}}`, where the object
     replaces any of `title`, `problem`, `criteria`, `perimeter`,
     `feature`, `priority`. A list of another length, an unknown entry or
     a state other than `proposed`: refused, nothing written.
   - Each kept ticket takes the next free id and is written to
     `TICKETS_DIR/<new id>.md`, exclusive create, in the shape of every
     committed ticket: `# <id> — <title>`, `- Status: open`, `- Intake:
     <intake id>`, `- Feature:` and `- Priority:` when set, `## Problem`,
     `## Acceptance criteria` (one paragraph per criterion) and `##
     Perimeter` (one `` - `path` `` per path).
   - Its tower document starts at `spec-ready`, never past it:
     `{id, state: "spec-ready", intake: <intake id>, spec: {criteria, by:
     "intake"}, history: [{step: "request", state: "spec-ready", at, by,
     via, intake}]}`, and `spec` is published. The criteria were proposed
     by `product` and confirmed by a person; running `clarify` again would
     replay nothing at L0 and say "not consulted", which is not what
     happened. From there the spec gate, unchanged, opens the ticket or
     sends it back to `questions` (ADR 0055 §4).
   - The intake becomes `confirmed`: each proposed ticket gains
     `decision` (`confirm`, `edit` or `drop`) and `ticket` (its id, or
     null when dropped), the intake gains `confirmation: {by, via, at}`
     and `tickets`, its history `{step: "confirm", state: "confirmed", at,
     by, via}`. Dropping every ticket is a confirmation too: the intake
     ends with no ticket.
   - Nothing opens without a person: no step reaches `requested`,
     `spec-ready` or `opened` from an intake but `intake-confirm`.

6. **A failing step may name its reason.** The tower gives every step
   `STEP_WHY`, a file path. A step that fails and has written a line there
   is recorded as `step exited <n>: <line>`; a step that writes nothing
   keeps `step exited <n>`, so every existing record and check stays as
   it is. The intake steps use it for every refusal of §2-§4.

7. **Records: logbook 1.7, additions only.**
   - `intakes`: one entry per `TICKETS_DIR/*.intake.md` the tower holds,
     `{id, state, text, by, via, at, questions, product, architect,
     proposal, confirmation, tickets, history, stranded}`. `proposal`
     is the list of proposed tickets, each `{n, title, problem, criteria,
     feature, priority, perimeter, check, decision, ticket}`; `stranded`
     is the last history entry when it failed, `{step, error, at}`, else
     null. The reader adds nothing it did not read.
   - Each ticket gains `intake`, the intake it came from, or null.
   - `tickets` and `kanban` keep only tickets: an intake is never a card
     in a state column. Each `*.intake.md` is skipped by the ticket
     reader.
   - The spend ledger counts the `architect` run of an intake as it
     counts the `product` run (ADR 0083 §3), not when it was not
     consulted, and the logbook's spend reads the intakes' documents too.
   - `core/logbook/1.7.schema.json`, `fixtures/logbook/golden-1.7.json`
     from the stub with one intake added; 1.0 to 1.6 stay, and the 1.7
     golden validates against every one of them (ADR 0047 §2's minor
     rule).

8. **The console: "Describe the need", and one intake card that fans out
   to its tickets.**
   - The request screen gains "Describe the need": one text area and one
     button. `POST /v1/intake {text}` runs `make intake` with the text as
     `INTAKE_FILE` (the recipe's `core/intake.py new` takes the next free
     id), the console's identity and `INTAKE_VIA=console`. Refused in a snapshot and with
     `CONSOLE_AUTH=public`, under ADR 0047 §3's checks (JSON content type,
     Origin, Host, one press at a time).
   - The kanban screen shows the intakes above the columns, one card
     each: id, state, the first words of the request, how many questions
     were asked and answered, and its tickets as links to their cards.
     The card opens `#intake/<id>`: the request, the questions and
     answers with the answer box on the open one, the proposed tickets
     with their perimeter and their `check` line, and, at `proposed`, a
     confirm, edit or drop choice per ticket with one confirm button,
     `POST /v1/intake-confirm {intake, decisions}`, which runs `make
     intake-confirm` with the console's identity and `CONFIRM_VIA=console`
     under the same checks, and only when the logbook shows the intake at
     `proposed` with that many tickets.
   - Keyboard: every control is reachable with Tab and has a label; the
     card opens with Enter. WCAG AA in both themes, measured by
     `ci/console-ui.py` (`.impeccable/config.json`).
   - The console now has five writes: go-for-launch, the answer, the
     request, the intake and its confirmation. Each records who pressed
     and `via: console`.

9. **No seventh role, no model id, no rule of the gate changed.**
   `product` and `architect` are two of the six; `ci/roles.sh` is
   unchanged. No id of a model enters `core/`, `gates/`, `verify/` or
   `roles/`. The spec gate's rules (ADR 0055 §4, §7) are unchanged: it
   judges the drafts and the confirmed tickets with the same code.

## Alternatives rejected

- **A seventh role, an "analyst".** Six is a decided limit (ADR 0020),
  and the conversation is the one `product` already has with the owner.
- **The interview as a form of fixed questions, no model.** It cannot
  skip what the request already says, nor split a request into tickets.
- **Decomposition by the spec gate or by a rule.** The gate judges
  whether a test can be written; it has no opinion on what a ticket is.
- **One `propose_tickets(tickets)` with a list of objects.** The brief's
  first suggestion. A list of objects needs a declared object schema that
  each provider's function declarations accept differently; one call per
  ticket uses only the shapes the role's two tools already have.
- **The map's file list in the architect's first message.** The replay
  key would change on every commit of the workload; the tool keeps the
  key on the proposal.
- **A perimeter computed from the map by a rule** (files whose path
  shares a word with the title). A number with no record behind it
  dressed as a proposal; at L0 without a recording the perimeter is
  empty and the person writes it.
- **Confirmed tickets at `requested`.** `clarify` would run `product`
  again on criteria it proposed itself, and at L0 record "not consulted".
- **An L0 intake without a recording that passes through**, as a ticket
  does (ADR 0055 §3). A raw request has no criteria to pass through.
- **A hand-written recording for the demo intake.** Forbidden (plan §7).
- **Intakes as cards in new kanban columns.** A confirmed intake would
  sit in a column forever; the card above the board fans out to the
  tickets, which keep the columns they have.
- **`ADK_RECORD=1` for the interview.** Every run would call the model
  again from turn 0 and could ask another first question than the one
  answered.

## Consequences

- An intake costs two role runs where a ticket costs one: the interview
  and the perimeter. Both enter the spend ledger.
- Until the owner records the demo intake, `./go ci` proves the refusal,
  not the conversation; the console shows an intake only where one was
  recorded or run live.
- Under replay the answers' text is not compared with the recording (ADR
  0055 §2): another answer replays the same proposal.
- `./go demo` does not change: it carries ticket 0001 from `requested`,
  as before. The intake is proven in `./go ci`.
- `make intake-confirm` runs the orchestrator after writing: at L0 the
  confirmed tickets pass the spec gate and stop at `assign` when no
  dev-worker recording exists for them, as any new ticket does today.

## Golden-rule check

`./go demo` gains no image, no key and no stage. `./go ci` runs the
intake on the workbench's Python and the ADK replay model, no key.
Passes.
