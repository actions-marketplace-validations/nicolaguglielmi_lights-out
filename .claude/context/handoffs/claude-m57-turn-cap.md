# Handoff — M57 amendment: a turn cap on every ADK role (ADR 0090, amendment A1–A5)

Branch `claude/m57-turn-cap`, cut from `origin/claude/m57-intake-6ec974`
(2e6b092, which the coordinator lands through `land/m57`). Not merged. Merge
`origin/main` into it once M57 has landed.

## Acceptance

- Tests written first by the gate-writer from the amendment (92a3464 carries
  them). **On fa857be (before the fix):** 46 new ADK tests fail (test_roles,
  test_agent, test_replay's RecordingOverCap, test_run_cap's live and replay
  cases, test_find_files), 10 of 16 in `core/tests/test_steprun.py`, and
  `ci/intake.sh` is `NO-GO: intake — an architect recording over
  ADK_MAX_TURNS was replayed: the perimeter step succeeded`. **After:** ADK
  suite 67/67 OK, test_steprun 16/16 OK, `GO: intake`.
- Planted live overrun (`test_run_cap`, and by hand in the workbench): a
  model that never stops, cap 3 → exactly 3 model calls, exit 1,
  `harness-adk: loop: TurnCapReached: ADK_MAX_TURNS=3 reached`, run.json
  `turns: 3`, tokens 30/6/36, `stop: "ADK_MAX_TURNS=3"`.
- `./go ci` GO from a full clone (`.crew/cap`), 92a3464, 398 s.
- **Final head 895233d** (main 238bc0c merged as first parent, tree equal to
  6e3524a, whose `./go ci` from a full clone is GO in 347 s): ci 43624023412
  (`GO: demo, milestone M9, 757s to rollback`), stranger 43624023454 (798 s),
  self 43624023464, podman 43624023439, package 43624023451, all green; site
  not triggered (no site path changed). Earlier: 92a3464's ci had
  `NO-GO: demo — … 907s > 900s`, b0eb01a's self had test-proof NO-GO
  (only a pure-arithmetic core test changed); both fixed, see below.

## What changed

- `ADK_MAX_TURNS` in every ADK role's `role.env`, with provenance: product
  16, architect 10, ops-triage 4, release 4; `load_role` refuses a role
  without it.
- `cap_callback` (before-model) stops a run before the turn over its cap;
  `run.py` keeps the turns and tokens spent and writes `stop`; a replay of a
  recording longer than the cap is refused whole (`RecordingOverCap`).
- `STEP_RUN`: a failing step hands the tower the run it made; the tower
  appends it to `spend` with `failed` = its stop. Written by `core/intake.py`
  (interview, perimeter) and `core/spec.py` (clarify/answer).
- The architect's `find_files` takes a list of up to 10 queries (40 paths
  each); `perimeter.md` asks for one search.
- The 74-turn architect recording removed: at L0 the demo intake's
  perimeters are not consulted (tutorial updated with a real L0 run).

## The re-recording (owner-approved in this session, ≤ $0.77): stopped at the cap

`./go intake TICKET=0101 … PROFILE=l1 ADK_RECORD=extend` and two `./go
answer`, from a fresh clone of 92a3464. The product's six turns were
replayed from the committed recording (no call, the fixture unchanged). The
architect ran live and **hit `ADK_MAX_TURNS=10`**: ten `find_files` calls of
2–10 queries each, never a `propose_perimeter`. It drifted into lights-out's
own files (`roles/architect`, `fixtures/logbook`, `core/perimeter`) because
the map covers this whole repository. The cap held as designed: step
`perimeter` failed, state `drafted`, history `step exited 1: the architect
role failed: harness-adk: architect: TurnCapReached: ADK_MAX_TURNS=10
reached`, and the run is in the ledger with `failed: ADK_MAX_TURNS=10`.
Not retried; the partial recording is not committed.

| | turns | input | cached | output incl. thinking | list price | cached rate |
|---|---|---|---|---|---|---|
| this attempt | 10 | 59,753 | 37,163 | 3,139 | **$0.057** | $0.032 |
| first recording (M57) | 80 | 1,502,166 | 1,305,937 | 26,774 | $1.23 | $0.35 |

## Second round (owner: "Sì, tutto" for the fixes; "Yes, record once" for ≤ $0.10)

- **Fixes** (ADR 0090 second amendment A6–A7, ADR 0083 amendment): the
  architect searches the workload only (`INTAKE_SCOPE` from `git -C
  $WORKLOAD rev-parse --show-prefix`, `app` here, empty for an attached
  repository; no `WORKLOAD` → the step refuses naming it), at most two
  searches (the third answers "propose now"); an ADK run's output counts its
  thinking tokens.
- **Tests first** (gate-writer, from the amendments). On 0073afa: 7 failures
  and 1 error in the ADK suite (scope, budget, `_tokens`), `ci/intake.sh`
  `NO-GO: intake — the perimeter step succeeded with WORKLOAD unset`. After:
  ADK 77/77, `GO: intake`. Plus `core/tests/test_perimeter_step.py` (written
  in session from A6, so `self`'s test-proof, which reads `core/tests/*.py`
  only, has a changed core test that fails on the base: 2 failures on
  529d561's step, OK after).
- **The ledger moves up.** ADK costs shown in the console, the role matrix
  and `./go spend` rise by each run's thinking tokens from the next live run
  on: the measured run is $0.046 before, $0.057 after (`core/tests/
  test_spend.py`, `test_run.Tokens`). Runs already in a ledger keep their
  number.
- **The re-recording succeeded at the first attempt** (b413d39), Gemini 3.8
  Flash, the product's six turns replayed (fixture unchanged):

  | turns | input | cached | output incl. thinking | list | cached rate |
  |---|---|---|---|---|---|
  | 4 (2 `find_files`, 2 `propose_perimeter` in one turn, the sentence) | 18,888 | 3,461 | 9,808 | **$0.051** | $0.049 |

  Six `app/` paths per ticket (`app/README.md`, `app/backend/meetups/app.py`,
  `app/backend/meetups/db.py`, `app/backend/tests/test_meetups.py`,
  `app/frontend/src/App.tsx`, `app/frontend/src/api.ts`), both `GO: spec` as
  drafts. The ledger's own entry: $0.050946 (thinking now counted). No key
  or `AIza…` in the file.
- **Total spent on the turn-cap branch:** $0.057 (stopped attempt) + $0.051
  = **$0.108 at list price**.
- **The demo's margin.** 92a3464's ci workflow: `NO-GO: demo — rollback
  reached, but 907s > 900s budget`; the demo's ci stage had grown from 4m52s
  (9fe74ff) to 7m52s (evals +38 s, core-tests +32 s, intake +26 s, logbook
  +24 s on the runner). `test_run_cap` now runs each scenario once (nine ADK
  subprocesses → five). b0eb01a: `GO: demo … 817s` (ci) and 805 s
  (stranger). Under budget, with a margin of 83 s.

## Findings, each a decision for the owner (first round, now done)

1. **The batched search alone does not make the architect stop.** It
   searched ten times, each a list, and proposed nothing. Options:
   (a) a search budget in the tool: after two calls `find_files` answers
   "propose now" (deterministic, cheap); (b) give the architect only the
   workload's tree (the map's paths under the workload directory), not
   lights-out's whole repository; (c) both. Either needs one more live
   recording: at most about $0.06 even if capped again (this attempt: $0.057 for ten turns).
2. **The ADK ledger undercounts output.** `run.py`'s `_tokens` takes
   `candidates_token_count` as output and drops `thoughts_token_count`,
   which Gemini bills as output: this attempt's ledger entry says 443 output
   tokens and $0.046, the recording's own usage 3,139 and $0.057. Every ADK
   run's ledger entry is low by its thinking tokens. A one-line fix with a
   test; not done here without a word, because it changes every ADK cost
   shown.

## For the next one

- Merge `origin/main` after M57 lands; re-run `./go ci` from a full clone.
- The demo intake at L0 now confirms with a perimeter the person writes
  (tutorial); with an architect recording it would be proposed again.
