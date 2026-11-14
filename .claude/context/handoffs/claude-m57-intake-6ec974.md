# Handoff — M57, the intake interview (ADR 0090)

Branch `claude/m57-intake-6ec974`, on `land/sprint-1114` (3924ebf, = origin/main
at push time). Not merged; the coordinator lands it.

## Acceptance

- `./go ci` from a full clone under `.crew/m57`: **GO**, 53 checks, 334 s, on
  a95689d (the commits after it touch docs, the Makefile's `intake` id and
  site/render.py's golden path only; `ci-shell`, `ci-help`, `ci-docs-drift` re-run
  green on them).
- `ci/intake.sh`: `GO: intake`, proving the **L0 refusal** (no recording yet):
  `intake: no recording of the fixture intake (766129b5…): proved the L0 refusal`.
- `ci/console-ui.py` (local, `localhost/m17-pw:dev`): all sections through ag
  GO, and the new **ah** GO (intake cards, keyboard, AA both themes, the
  decisions POST intercepted on a simulated live console).
- `./go demo` **locally: not run to the end.** `./go up` stopped at "gitea not
  ready after 180s": host port 3000 was held by a Python static server started
  15:36 from `~/Dev/NicolaGuglielmiWebsite` (not this session's; left alone).
  The plane was checked free on both connections before and downed after.
  The demo is proven by the push workflows below.
- GitHub Actions on 9fe74ff, all six push workflows **green**: ci
  43606198813 (`GO: demo, milestone M9, 659s to rollback` in engine-compat;
  `GO: console-ui`, ah included), stranger 43606198773 (`GO: demo … 657s`),
  self 43606199016, site 43606198760 (the kanban still shows the intake
  cards), podman 43606198759, package 43606198851. Shell, help, plan and
  docs-drift re-run green locally on 9fe74ff.

- **With the recording**, on 9c117d7: `./go ci` GO from a fresh full clone
  (342 s; `intake: the recording of the fixture intake exists: proved the full
  conversation`), and the six push workflows green: ci 43611591662 (`GO: demo, milestone M9, 840s to rollback`,
  `GO: console-ui`), stranger 43611591625 (`GO: demo … 718s`), self
  43611591683, site 43611591643, podman 43611591604, package 43611591669.
  **Watch the demo's margin:** 840 s against the 900 s budget on
  engine-compat (659 s on 9fe74ff). `ci-intake` inside the demo's ci stage
  took 14 s on that runner (15:47:39 → 15:47:53), so most of the jump is
  the runner, but the margin is one minute.

## What changed

- **ADR 0090** (amends 0055, 0059 §4, 0023 §2, 0034 §1) and PLAN "M57 — Il
  colloquio di intake" with criteria written before the code.
- **Tower**: `intake` (doc `kind: intake`), steps `interview`, `intake-answer`,
  `perimeter`; states `intake`, `intake-questions`, `drafted`, `proposed`,
  `confirmed`; `answer` also answers an intake; `intake-confirm` writes kept
  tickets at `spec-ready` (`spec.by: intake`, `intake: <id>`). `STEP_WHY`: a failed
  step may name its reason (`step exited 1: <line>`), every old record unchanged.
- **Roles**: `product` gains the agenda and `propose_ticket` (one call per
  ticket); `architect` gets an ADK agent (`find_files` over the project map,
  `propose_perimeter`) with `roles/architect/perimeter.md`. No seventh role,
  no model id outside profiles/adapters.
- **`ADK_RECORD=extend`**: replays held turns, records new ones — for
  recording an interactive interview turn by turn.
- **Logbook 1.7** (additions only): `intakes`, `tickets[].intake`; golden 1.7,
  1.6 kept as an old fixture; stub gains intakes 0011 (confirmed → 0009) and
  0013 (open question). Spend and roles count an intake's runs when it has a
  ledger; `architect` joins spend's run fields.
- **Console**: intake cards above the kanban, `#intake/<id>`, "Describe the
  need"; writes `/v1/intake`, `/v1/intake-confirm` (five writes in all); actor
  `architect` in the tower-machine table.
- Docs: reference, tutorial (real L0 output), console README,
  use-on-your-repo §4, site "what is real", board table, site stills on 1.7.

## Deviations

1. `propose_ticket` called once per ticket instead of `propose_tickets(list)`:
   only str and list[str] arguments, the shape every provider's function
   declarations accept (ADR §2, alternatives).
2. **The recording is missing.** Needs a live call; nothing spent. Plan and
   estimate below.
3. Edited tickets in the console are judged by the spec gate after the
   confirmation (at `spec-ready`), not live while typing.
4. `ci/console-ui.py`'s section ah was written in session from ADR 0090 §8,
   not by the gate-writer (it needs a browser and the console's DOM).
5. The architect's `NoRecording` text ends with "record them with ./go
   record-evals" (the replay model's own line); the intake's refusal line that
   follows names the right command.

## The recording (done 2026-11-14, owner-approved)

Approved by the owner through the coordinator ("Sì, registra": Gemini only,
≤ $1) and again in this session ("Yes, record it"). Run from a full clone
with `PROFILE=l1 ADK_RECORD=extend`: `./go intake TICKET=0101`, then two
`./go answer`; the answers were written by this session as the client.
Committed in 16c97e7 after grepping both files for the Gemini and Anthropic
keys and any `AIza…` string (none):

- `fixtures/adk/product/766129b5….json`: 6 model turns, 2 questions, 2
  `propose_ticket` (both `- Feature: rsvp-cancellation`, `- Priority: P1`).
- `fixtures/adk/architect/cd449eef….json`: 74 model turns, 72 `find_files`,
  2 `propose_perimeter` (six paths each), 308.9 s.

**Tokens and cost**, summed once per turn from the recordings' own
`usage_metadata` (each turn's prompt is billed once):

| role | turns | input | of which cached | output (incl. thinking) |
|---|---|---|---|---|
| product | 6 | 19,837 | 6,819 | 4,712 |
| architect | 74 | 1,482,329 | 1,299,118 | 22,062 |
| **total** | 80 | **1,502,166** | **1,305,937** | **26,774** |

- At the cached-input rate M24 used ($0.075/M cached, $0.75/M uncached,
  $3.75/M out): **≈ $0.35**.
- At list price with no input cached: **≈ $1.23**, over the $1 approval.
- Google AI Studio's billing is not visible from here: the owner should
  check which of the two was charged.
- `./go spend` over the recording's own tower document would overstate it:
  under `ADK_RECORD=extend` the run's `run.json` counts the turns it only
  replayed (the product's three runs count turns 1–2 three times).

**The overrun, and what it shows:** the estimate assumed 8–10 architect
turns; it took 74, because nothing caps the turns of an ADK role (the
architect's `MAX_TURNS=60` and `TOKEN_BUDGET` in `role.env` are its
coding harness's, not the ADK path's). It could not be stopped mid-run. The
replay is unaffected (17 s in `ci/intake.sh`), but a live intake at L1 can
spend without bound: **the perimeter step needs a turn cap, with its
provenance, in an amendment of ADR 0090** (proposed, not done).

## Screenshots

Shared notes `m57-shots/`: `intake-cards-{light,dark}.png`,
`intake-0011-{light,dark}.png`, `describe-the-need-{light,dark}.png`, over the
1.7 golden in snapshot mode.

## For the next one

- Once recorded, `ci/intake.sh` drives the intake end to end; consider adding
  the intake to `./go demo-console` rather than `./go demo` (900 s budget).
- The worker still reads `tickets/<id>.md`; an intake-born ticket has its
  criteria there, so this is fine for M57, but ADR 0055's open item stands.
