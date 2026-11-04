# Handoff: M22 "ops without the plane", 2026-11-04, branch `claude/nostalgic-engelbart-1820af`, not pushed, not merged

The owner reviews. Plan: `docs/PLAN.md` §16 M22 (status note added); decision: `docs/adr/0044-incident-in-postmortem-out.md` (proposed). The branch was fast-forwarded to `main` (06047b8) before work: it had been cut before M18/M20.

## The gap, first

`./go demo-postmortem` does **not** print GO yet, and cannot from this session: the ops-triage recording of the post mortem needs your Gemini key and there is no `.env` with a key in the worktree. It prints, honestly:

```
NO-GO: demo-postmortem — no recording of the ops-triage role for fixtures/incidents/demo-rollback.json; at L0 it replays fixtures/adk/ops-triage, record it with ./go record-postmortem PROFILE=l1
```

What is missing is one command from you, with `GEMINI_API_KEY` in `.env`: `./go record-postmortem PROFILE=l1`. It writes `adapters/adk/agents/ops_triage/evals/postmortem.evalset.json` from `fixtures/incidents/*.json`, records through `record-evals ROLES=ops_triage` (which also re-records the three alert cases under the new prompt), and keeps the evalset only if the eval passes. Commit the evalset and the new `fixtures/adk/ops-triage/*.json`; then `./go demo-postmortem` should print `GO: demo-postmortem` with a fix ticket (never run against a real recording: the GO path is proved by `ci/postmortem.sh` with a stub harness, not by the demo). The incident it replays is real: `fixtures/incidents/demo-rollback.json`, built by `./go incident` from the release record of a real `./go demo-rollback` run (README in that folder has the provenance). No model output is hand-written anywhere.

## Acceptance, run for real

Full clone of the branch at `<worktree>/.crew/m22b`, `APP_PORT=9000`, warm images, a host that was under load (see "Found" 3).

```
./go demo          → GO: demo, milestone M9, 590s to rollback (budget 900s, plan §2); it runs ./go ci first:
                     30 checks GO, among them roles (six), prompts, evals (four tools), postmortem, metrics, contract
./go demo-postmortem → NO-GO: demo-postmortem — no recording … ./go record-postmortem PROFILE=l1   (exit 1, as designed)
./go verify METRICS_URL=http://host.containers.internal:9090 CANARY_VERSION=0.2.0-waitlist STABLE_VERSION=0.1.0-m2
                   → NO-GO: slo — error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000 delta=1.000 max=0.010
                     the same line launchpad recorded for the 5% stage of the run just before (release.json stages[0].verdict, via the prometheus adapter)
./go verify        → metric-shape, unchanged; ./go verify METRICS_URL=… with no versions → NO-GO: slo — CANARY_VERSION and STABLE_VERSION must both be set
```

The verify comparison was made once, right after a `demo-rollback`, inside slo.promql's `[1m]` window; a second try during a live stage did not happen (the image tag moved with the clone's HEAD and `up` had to be redone).

`ci/postmortem.sh` and `ci/metrics.sh` were written by the gate-writer from the ADR, before the implementation existed; against it they first failed on several points (error-message wording, the "Found by" line, `postmortem.json` keys, missing-variable handling, `put.sh` usage), all in the implementation, none in the checks.

## What changed

- `adapters/promql/query.sh` (`METRICS_URL`, `METRICS_AUTH_HEADER` via curl stdin); `adapters/prometheus/query.sh` is its case at `$PLANE_HOST:9090` and ignores an ambient `METRICS_URL`; `./go verify METRICS_URL=…` runs `verify/slo.sh`, otherwise metric-shape as before; `./go demo` passes `METRICS_URL=`.
- `adapters/file/put.sh`: the Tracker's write verb (next id, `- Origin:` makes a re-run file nothing, no `## Perimeter`).
- `ops-triage` gains `file_postmortem` (same role, same prompt; `roles/ops-triage/prompt.md` has an incident section); `core/incident.sh`, `core/postmortem.sh`, `core/postmortem.py`: `./go incident`, `./go postmortem`, anchored timeline (ids the document holds, evidence printed beside each claim), NO-GO P1–P10, tickets through the Tracker.
- `./go demo-postmortem`, `./go record-postmortem`, `fixtures/incidents/`; ci checks `postmortem` and `metrics`; ADR 0044; README, `docs/reference.md`, `docs/ARCHITECTURE.md`, `docs/PLAN.md` (§4 rows, §16 status note).

## Found (contradicts the plan or the brief)

1. The plan's `METRICS_URL=http://prometheus:9090` cannot work for a host-side `./go`: that is a compose name the workbench does not resolve. The plane's case is `http://$PLANE_HOST:9090`.
2. Decisions of mine for you to veto: (a) the evalset lands with the recording, so `./go ci` stays green; (b) `demo-postmortem` writes its tickets to a copy of `tickets/` under `.crew/demo-postmortem/` and runs twice to prove idempotency, instead of into `tickets/` as the done-when says (an untracked `0014.md` per run would take your next number); `./go postmortem` itself writes to `tickets/`.
3. This machine's podman VM is fragile under several sessions: `./go up` failed twice (the backend gave up on flagd at load average ~150), then the machine stopped and I ran `podman machine start`. Nothing else was touched; I `./go down`ed only the planes I started.
4. A fix ticket has no `## Perimeter` (the role never saw the code): `core/perimeter.sh` refuses it until a human adds one. That is the deliberate stop, and "re-enters the tower" means it is a valid ticket, nothing more.
5. An anchored timeline is not a true one: the rule stops invented releases and PRs, not a wrong story about real ones (ADR consequences).
6. `roles/ops-triage/prompt.md` changed, so the three alert recordings replay with a "recorded under a different prompt" line on stderr until re-recorded (the same `record-postmortem` run does it).
7. Attached repositories: `METRICS_URL` and `METRICS_AUTH_HEADER` are `env -u`'d in `ci/attach.sh`.

## First thing the next milestone should look at

The recording (above), then M21/M23 can use `put.sh` and `promql` as they are. If you merge before recording, nothing else is needed; the demo is not a `./go demo` stage.
