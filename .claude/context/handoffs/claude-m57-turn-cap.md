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
- GitHub Actions: RUNS_PENDING

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

## Findings, each a decision for the owner

1. **The batched search alone does not make the architect stop.** It
   searched ten times, each a list, and proposed nothing. Options:
   (a) a search budget in the tool: after two calls `find_files` answers
   "propose now" (deterministic, cheap); (b) give the architect only the
   workload's tree (the map's paths under the workload directory), not
   lights-out's whole repository; (c) both. Either needs one more live
   recording, ≈ $0.06 expected, ≤ $0.06 here measured per 10 turns.
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
