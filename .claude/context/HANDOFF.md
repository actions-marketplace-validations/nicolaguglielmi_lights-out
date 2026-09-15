# Handoff: M5 closed on 2026-09-15

## Acceptance

`./go demo-crew` (warm, podman rootless on macOS, no key, no account) — bootstraps a fresh Gitea, replays `fixtures/0001/dev-worker/`'s recorded patch as `ticket/0001`, pushes, opens the PR, fetches it back into a throwaway worktree, judges it with `make gates`, diffs the verdict against `fixtures/0001/dev-worker/expect`:

```
SURVIVOR meetups/geocoder_client.py:24 core/ReplaceComparisonOperator_NotEq_Gt
score: 203 mutant(s) excluded from the population (skipped, no-test, or incompetent)
[crew-run] gates: GO: gates — risk low, auto-merge
GO: demo-crew
```

97s wall time (`time ./go demo-crew`). This is plan §7 M5's criterion directly: at L0, with no key, the same ticket produces the same PR from the recorded fixture. `./go ci`: all twelve checks GO, including the two new ones — `hooks` (31 cases, `adapters/gemini-cli/hooks/guard.sh`'s BeforeTool deny-list, proven to fail on a bad case, not just pass) and `harness` (`core/harness-check.sh`'s harness-independent "exit 0 is not success" invariant, proven on four stub scenarios).

`./go record TICKET=0001 PROFILE=l1` (the L1 half of the criterion — a real Gemini API key, run once this session): six real attempts, five real bugs found and fixed between them (below), attempt 6 recorded. `fixtures/0001/dev-worker/run.json`:

```json
{"harness":"gemini-cli","model":"gemini-3.5-flash","thinking":"high","turns":1,
 "tokens":{"input":892202,"output":3651,"total":915022},"duration_s":303,"exit_code":0}
```

`./go demo` (the whole-repo proof, M3's stage list, unchanged by M5):

```
GO: demo, milestone M3, 113s to rollback (budget 900s, plan §2)
```

## What changed

- `AgentHarness` port (`adapters/$AGENT_HARNESS/run.sh`, env contract: `ROLE TICKET TICKET_FILE WORKSPACE BASE OUT` + budgets; success = a commit over `BASE` plus `OUT/{patch,pr.json,run.json}`). `replay`: copies a recorded fixture, `git am`s it, never claims tokens it did not spend. `gemini-cli`: a compose service, no engine socket, `FROM ${WORKBENCH_IMAGE}` + `npm ci` of a pinned `@google/gemini-cli@0.59.0`; the adapter — not the model — commits, builds the patch, and refuses to record anything if the API key leaks into the artefacts.
- `core/crew.sh` drives ticket → PR (bootstrap → clone → harness → push → open-pr), the model never holding a credential; `core/harness-check.sh` enforces "exit 0 is not success" independent of which harness ran. `Makefile`: `assign`, `demo-crew`, `record`, internal `crew-run`.
- `adapters/gitea/{env,bootstrap,clone-url,push,open-pr}.sh`: a fixed low-entropy admin user and a public `lights-out/lights-out` repo, Actions off (a job nobody consults before M6 is noise). `adapters/file/get.sh`: the Tracker=file port.
- `roles/`: six directories. `dev-worker` has a real prompt and budgets (the only role with a run at M5); the other five have `role.env` (THINKING from plan §5) and a `ROLE.md` naming which milestone gives them a run — a prompt nobody has run is a hypothesis, not written here. `adapters/gemini-cli/hooks/`: `guard.sh` (BeforeTool deny-list) and two budget hooks (BeforeModel/AfterModel, live token accounting).
- `fixtures/0001/dev-worker/`: the one real recording, replayed at L0 forever after.
- `policy/merge.env`: `RISK_HIGH_PLATFORM` gains `roles/*:fixtures/*:.gemini/*`. `gates/mutation.sh` + `mutation-baseline`: `.env` clobbering fixed (`-p lo-mutation(-baseline)`, no more `printf > .env`).

## Contradicts docs/PLAN.md — the most important line in this file

**Plan §5 commits to `gemini-3.8-flash` for every role. It is not the model that runs.** `gemini-3.8-flash` is real and reachable with this project's key — confirmed directly against `GET https://generativelanguage.googleapis.com/v1beta/models`, which lists it. But **Gemini CLI v0.59.0 (the pinned version, npm-published 2026-09-08) silently serves `gemini-3.5-flash` instead**, no matter how the model is requested — `-m gemini-3.8-flash`, the fully-qualified `-m models/gemini-3.8-flash`, and `settings.json`'s `model.name` were all tried, on three separate invocations including two minimal non-agentic probe calls outside the crew harness entirely, and all three produced a `result` event whose `stats.models` key is `gemini-3.5-flash`. No warning anywhere, on any channel. Most likely explanation: 0.59.0 predates this CLI's own support for a model ID that reached GA about a week after that release. Not fixed here: a version bump is its own dedicated commit under CLAUDE.md's pinning rule ("rinnovi solo con un commit dedicato che fa passare gli eval"), and the newest tag at record time was a nightly (`v0.61.0-nightly.20260915`), not a stable release worth pinning to under that same rule. `fixtures/0001/dev-worker/run.json`'s `"model"` field says `"gemini-3.5-flash"`, honestly — the adapter now reads `stats.models`' own key rather than echoing back the requested string, because the two have already been observed to differ once and might again. **M6 (or whoever bumps the CLI pin next) should check the models list first**, the same way this session did, before assuming a version bump alone fixes it.

Full detail, including the exact bundle code read to confirm the `result` event's real shape (no `response` field in `--output-format stream-json`, flat `stats`, a `transcript_path` on every single hook call that made the first hooks implementation deny everything): `docs/adr/0017-agent-runtime-at-m5.md`, "Contradicts the plan" section and the closed "Verify at L1" list, item by item.

## The six real attempts — the worker's reliability number, with a caveat that matters

`record`'s own rule: a NO-GO or over-budget run is refused and kept under `.crew/<ticket>` for study, never silently retried. This session ran it six times to reach one recorded fixture — **six stays the reference number**, but it is not a measurement of the model. Five of the six failures below were bugs in *this repo's own harness, hooks, or prompt*, not shortcomings of the model or a case for a different one; only the sixth attempt ran against code that no longer had any of those five bugs in its way, and it succeeded. Owner note (2026-09-15, before M6): this number is not an eval yet, because it was measured while the code under test was still changing between attempts. Re-measure it at M9, on code that has been stable for a while, and only then does six-attempts-or-whatever-it-becomes mean anything as a reliability eval rather than a debugging log.

1. Exit 55, no model call made (near-zero cost): Gemini CLI refuses a headless run in a workspace it has never seen unless `--skip-trust` is passed — undocumented as "disabled by default" (that page describes the interactive dialog only). Fixed: `entrypoint.sh` adds `--skip-trust`.
2. Exit 0, empty transcript's worth of real work: the recorded worker's own `.gates-out/verdict.env` from an unrelated earlier mechanics test was read as a false `GATES=GO` by `record`, because `crew-run`'s failure was swallowed by a bare `;` instead of an exit-code check. Caught before a bogus fixture was committed. Fixed: `crew-run` now clears `verdict.env` before it starts (absence, not staleness, is the failure mode of a future oversight), and `record` checks `crew-run`'s exit code explicitly.
3. Every single tool call denied, always for the same reason (`.gemini/`): `guard.sh`'s original `[.. | strings]` joined the *entire* hook payload, and every `BeforeTool` call carries a `transcript_path` field pointing into the CLI's own `~/.gemini/tmp/...` recording file — so the `.gemini/` deny rule matched unconditionally, on `ls`, on reading `geocoder_client.py`, on everything. The model, quite reasonably, spent its budget trying workarounds (`env -i`, absolute paths, alternate directories) before giving up confused. Fixed: scoped the join to `.tool_input` only.
4. Clean run, budget correctly enforced (4,040,294 ≥ 4,000,000), no PR: most of the budget went to the model discovering `adapters/gemini-cli/hooks/guard.sh` in its own repo clone and grep-searching it to understand why calls were denied — a real, if unproductive, behaviour once (3) no longer made every call an unexplained mystery. Fixed: `prompt.md` now scopes exploration to `app/` explicitly and says a denial is expected, not a puzzle.
5. Clean run, 29 correct tool calls across every file the ticket needed, budget denied the model's *next* call right after its last successful edit, with no turn left to write the PR text. `run.sh` exited on the missing response *before* attempting to commit, so that real, correct, on-topic work was silently discarded — found only by inspecting the still-dirty workspace directly. Fixed: commit first, always (a WIP placeholder amended to the real message if one arrives), and `TOKEN_BUDGET` raised from 4,000,000 to 5,000,000 with this measurement as its provenance.
6. Recorded. The model chose the 502 ("geocoder unavailable") resolution to ticket 0001 — a valid alternative to `honest-fix`'s 201/null-coordinates choice under the ticket's own either/or acceptance criteria. Six files touched correctly, all six gates GO, one surviving mutant (still above threshold), 3,887,754 tokens accumulated (comfortably under the raised budget).

Read together: every one of these is a bug in the harness, hooks, or prompt this session wrote — never a shortcoming that needed a second model or a different approach. A future re-record, on a repo that already has these fixes, should need far fewer attempts; that number, whatever it turns out to be, is worth recording again the next time this fixture is regenerated.

## Other things found, not fixed here

- **Pre-existing debt, not M5's**: `gates/mutation.sh` never runs `docker-compose down` for its own `lo-mutation` project. Its Postgres container (and, separately, `mutation-baseline`'s and a stray `lo-mutation-measure`'s) linger indefinitely after every mutation gate run. This session found three such lingering containers at the very start, from earlier (M4-era) sessions, still running — and they are the leading suspect for a `./go demo` failure this session hit twice in a row (`ready: envoy-canary not ready after 60s`, root-caused to `openfeature.exception.ProviderNotReadyError` on the backend, itself a flagd-connect race that gets worse under host load). The user flagged this connection directly mid-session: `READY_TIMEOUT=150` (used to get `./go demo` green under a load average of 39–78 on this machine) is **not a value to promote to any default** — it was a one-time accommodation for local resource contention, not evidence the plane's own timing changed.
- A transient `open-pr on gitea failed` (~11s, before any real work) was observed once, immediately after a fresh `./go demo` teardown/rebuild cycle; an immediate retry passed. Most likely Gitea's API not fully warm right after bootstrap on a cold plane. Not chased further — no other run in the session (six real L1 attempts, three L0 mechanics runs) hit it.
- `run.sh`'s "turns" field is not a real measurement: the stream-json `result` event reports no turn count anywhere, and the `role:"user"`-message-count proxy always reads `1` for a headless `-p` session (there is exactly one user message per session, regardless of how many internal agent-loop iterations happen). `MAX_TURNS` is still enforced correctly server-side (exit 53); this repo just cannot observe the count it enforced against. Worth a real fix only if a future milestone needs that number for something.

## First thing M6 should look at

- **The Gitea runner socket and the first real Gitea Actions job, per ADR 0015 §7's three conditions, land at M6** — ADR 0017 §5 amends the ADR 0015 consequence that said "M5 is not closed while the runner lacks it": no Gitea job runs at M5, so that consequence is void. `demo-crew`'s own CI leg judges the PR range with `make gates` from workbench directly, the `demo-gates` mechanism, not a Gitea job.
- **The gemini-3.8-flash / gemini-3.5-flash question already has a ticket and a decision**: `tickets/0002.md` and the ADR it produced (numbered after 0017 — check `docs/adr/` for the exact file, written between M5's close and M6's start) record the root cause (a real, already-merged CLI bug, `google-gemini/gemini-cli#29252`), a live-verified fix in the nightly line, and the chosen option. Read that ADR before touching the pin or the plan yourself; do not re-derive the finding.
- **`roles/architect/ROLE.md` and `roles/test-reviewer/ROLE.md` say this port runs them starting M6** — real prompts for those two roles are M6's first job on `roles/`, written against a real run the same way `dev-worker/prompt.md` now is, not guessed in advance.
- **The mutation-gate cleanup debt above** is cheap to fix (a `docker-compose -p lo-mutation down -v` somewhere in `gates/mutation.sh`'s own flow, or a documented manual step) and directly reduces the kind of host-load flakiness this session hit twice.
