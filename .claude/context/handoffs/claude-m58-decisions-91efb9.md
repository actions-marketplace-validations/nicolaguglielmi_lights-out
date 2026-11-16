# Handoff — M58, closed decisions: the perimeter and the injection screen (ADR 0091)

Branch `claude/m58-decisions-91efb9`, on origin/main b4b1590. Not merged; the
coordinator lands it (`--no-ff`).

## Acceptance

- `./go ci` from a full clone under `.crew/m58-record`: **GO**, 55 checks,
  449 s, on 4ed34d0 (848 s on 65072dc, the VM shared). Among them:
  `GO: decide` (the port and both adapters' conformance on loopback stubs),
  `GO: screen` (`labelled set, injection: stop 12 flag 0 pass 0`,
  `labelled set, benign: stop 0 flag 0 pass 12`), `GO: intake` (`the demo
  intake perimeter replayed fixtures/decide`, and the M57 full conversation),
  `GO: logbook` (1.8, the hand checks and their planted failures),
  `GO: app-free`, `GO: model-free`, `GO: shell-boundary`. The commit after
  4ed34d0 is this file only.
- `./go demo`: **not run locally**. The one plane slot was held by another
  session (`lights-out-*` and a `lights-out-demo-ci-*` workbench on the
  rootful connection; rootless empty), so the demo is proven by the push
  workflows below.
- GitHub Actions on 4ed34d0, all five push workflows **green**: ci
  43853268214 (`GO: demo, milestone M9, 770s to rollback` in engine-compat,
  `GO: console-ui` with section `ai`, `GO: demo-console`), stranger
  43853268382 (`GO: demo … 684s`), self 43853268273 (`GO: gates — risk
  high, review, in workbench`: the mutation gate passes with the unit
  tests), package 43853268172, podman 43853268468. On 65072dc the demo took
  846 s and 862 s on the same runners: worth watching against the 900 s
  budget; the screen adds one replayed decision (under a second) to
  `clarify`.
- `site` on 66abf73 (43841430413): **green**. It renders the stills over
  golden-1.8; nothing in the site's paths changed after it.
- `ci/console-ui.py` locally (`localhost/m17-pw:dev`): one run stopped at
  "the page drew no main h1 for #overview in 5000 ms" while `./go ci` and the
  recording loaded the VM. The CI job above is the proof, section `ai`
  included.
- The self gate first failed on 65072dc: mutation 31/1238 on the changed lines
  (0.025 < 0.293), because the new core code had only shell suites. A
  gate-writer then wrote unit tests from the ADR: `core/tests/test_decide.py`,
  `test_screen.py`, `test_record_decisions.py` and additions to `test_intake.py`
  and `test_tower.py`, 1676 tests in all. Measured locally, `decide.py` and
  `screen.py` score 636/700. The tests found one real defect, now fixed: a
  question key with a trailing newline passed the `$` regex, against ADR §1.

## The comparison (ADR 0091, "Measured")

Recorded and measured 2026-11-16, owner-approved (≤ $0.40), from a clone at
af6600e: 109 measured calls plus 27 recordings (and 24 re-recorded with the
intake file's final newline), none failed. **Spend about $0.13 at list
price**: `gemini-decision-1` ~128k input tokens ($0.013), `structured` on
gemini-3.8-flash 29k in / 5k out ($0.039), the search path once 23k / 15k
($0.073). The raw log is in the notes folder, `m58-measure.jsonl`.

| perimeter of the demo intake | turns | tokens in / out | cost | time | ticket 1 | ticket 2 |
|---|---|---|---|---|---|---|
| search (live) | 4 | 23,451 / 14,654 | $0.073 | 115 s | 6 paths | the same 6 |
| `gemini-decisions`, 0.7 | 1 request, 150 questions | 21,235 / 0 | $0.002 | 1.0 s | 5 in, 5 uncertain | 4 in, 8 uncertain |
| `gemini-decisions`, 0.8 | the same | the same | $0.002 | 1.0 s | 3 in, 19 uncertain | 4 in, 18 uncertain |
| `structured` | 1 request | 16,278 / 3,130 | $0.024 | 24.8 s | 5 in | the same 5 |

- Determinism: all 27 requests, four times each, gave identical
  probabilities, the 150-question perimeter included.
- Screen latency: `gemini-decisions` median 0.42 s for the HTTP call, 0.62 s
  through the port; `structured` median 10.9 s.
- Labelled set: 12/12 injections stop (p 0.970–0.990), 12/12 benign pass
  (p 0.010), on both adapters. Nothing fell in the uncertain band.

## What changed

- `Decide` port: `core/decide.py` (request and answer contract, replay, record),
  `adapters/gemini-decisions` (REST with urllib: `client.decisions` needs
  google-genai ≥ 3.2, and google-adk 2.14.x requires < 3), `adapters/structured`
  (litellm, JSON schema, any provider), `DECIDE` in the four profiles,
  `gemini-decision-1` in prices.json, `ci/decide.sh`.
- Pilot B: `core/screen.py`, `roles/product/screen.md`, the screen in
  `interview`/`intake-answer`/`clarify`/`answer`, `./go screen-clear`,
  `policy/decide.env`, `fixtures/screen/labelled.json`, `ci/screen.sh`.
- Pilot A: `PERIMETER_BY` (default `search`), `core/intake.py
  decide-perimeter`, `ci/intake.sh` section i plus a replay of the real
  recording.
- `./go record-decisions` (`MEASURE`, `DECIDE_COMPARE`, `MEASURE_SEARCH`);
  27 recordings in `fixtures/decide/`.
- Logbook 1.8 (additions only), golden-1.8, the console's screen mark, line
  and uncertain paths, `ci/console-ui.py` section `ai`; reference, tutorial,
  plan §4 and M58.

## The owner's decisions in this session

1. Spend: approved ≤ $0.40; spent about $0.13.
2. `PERIMETER_CONFIDENCE=0.7` from the measure, and `PERIMETER_BY` stays
   `search`. **Correction:** the question said that at 0.7 ticket 1 gets 6 paths
   in and 4 uncertain. Recomputed exactly, it is 5 in and 5 uncertain: `api.ts`
   is at p 0.6996. Ticket 2 gets 4 in and 8 uncertain. The ADR and plan carry
   the exact numbers; the owner may want to revisit.

## Against the plan or the brief

- The SDK named in the brief cannot sit beside the ADK (see above); the API
  itself is as described.
- Hive Commons' "61/63 blocked" was not found in a public source on
  2026-11-16. The ADR cites hivecommons/hive#6685, #6708 and v5.0.0 (17/43
  missed) for the families it takes.
- The tests' `tower()` in `ci/intake.sh` unset `DECIDE`. Every profile sets it,
  and an unset `DECIDE` is a refusal, so the helper now sets `DECIDE=replay`
  with an empty fixtures dir. `ci/screen.sh` 0502 asserted that a failed step
  stores the screen; ADR 0091 §7 stores it only in a step's result, so that
  assertion was relaxed. Both edits were made in session; the tests were
  written by gate-writer.
- The screen's verdict on a step that later fails (no product recording at
  L0) is not stored, so it is asked again on resume. That is cheap, but say it
  if it matters.

## For the coordinator

- Expected conflicts: `Makefile` CI_CHECKS (`decide screen`), PLAN (§4 row,
  the "Sprint 2026-11-16" heading I created), `profiles/*.env` and
  `prices.json` with M59, `core/spend.py` RUN_FIELDS, the logbook 1.8 bump if
  another branch bumps too.
- M59 (GLM): `adapters/structured` calls litellm with
  `f"{MODEL_PROVIDER}/{MODEL}"` and the key from
  `lights_out_adk.model.provider_from_env`, as the ADK's LiteLlm path does.
  GLM works there exactly when it works for the ADK roles; if M59 maps the
  provider to another litellm prefix, apply it in `adapters/structured/decide.py`
  too.
- **Site text** (not edited; `site/index.html` is not mine): the stills note
  cites `fixtures/logbook/golden-1.7.json`, still a file in the repo, but the
  stills now render over `golden-1.8.json`. Suggested line for the list of what
  is true: "Before an agent reads a client's words or a ticket body, one closed
  question through the Gemini Decisions API (or your own model) asks whether it
  holds instructions aimed at an AI agent: on a labelled set of 24, it stopped
  all 12 injections and none of the 12 ordinary requests. It is a screen, not a
  gate: a person reads what it stops."

## First thing for the next milestone

Measure a second intake before switching `PERIMETER_BY` to `decide`. On this
one, asking per file is 60× cheaper and 100× faster, but it misses the README
and leaves 5 to 8 paths to the person.
