# Handoff: M19 "claude-code and codex harnesses", 2026-11-04, branch `claude/xenodochial-chaum-7241fa`, not pushed, not merged

The owner reviews. Plan: `docs/PLAN.md` §16 M19 (status note added); decision: `docs/adr/0041-claude-code-and-codex-harnesses.md`. The branch starts with a fast-forward to local `main` at 06047b8 (M18 and M20 merged); the session's worktree had been cut before them.

## Acceptance, run for real

All on 2026-11-04 from a full clone of the branch at `<worktree>/.crew/m19` (`./go` cannot drive git from a `.claude/worktrees` checkout), on the owner's machine (podman machine, aarch64, 4 GiB), with the shared plane empty (M22's demo had finished; the plane this session started was taken down after).

```
./go harness-conformance → GO: harness-conformance — claude-code codex gemini-cli, against a
                           scripted model, 144 s (2:55 with the image builds warm)
                           preceded by GO: harness-conformance-proof (the suite refuses 17 broken fakes)
                           per harness, cases 0-8; the budget cases print
                           over MAX_TURNS (2) / over TOKEN_BUDGET (2500) / over TIMEOUT_S (30 s)
./go ci                  → GO: ci, 87 s, 29 checks, harness-shape and the 132-run hooks among them
./go demo                → GO: demo, milestone M9, 422s to rollback (budget 900s, plan §2), clean clone,
                           APP_PORT=9000 in .env, no key
./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=claude-code MODEL_PROVIDER=anthropic \
    MODEL=claude-sonnet-5-5 MODEL_BASE_URL=http://example.invalid
                         → NO-GO: record — MODEL_BASE_URL is set: a run against a scripted or proxied
                           endpoint is never a fixture (docs/adr/0041 §7)
```

Each harness also ran alone first (`CONFORMANCE_HARNESS=claude-code` 59 s, `codex` 76 s); both failed once and were fixed (findings 5 and 6). Codex passed case 3's code-mode JS read: the second canary never reached the scripted model, so the Fable task ADR 0041 §3 reserved was not needed.

## What changed

- **Two adapters** (ADR 0041 §1–§6): `adapters/claude-code/` (Claude Code 2.1.311, the npm `stable` tag) and `adapters/codex/` (Codex 0.166.0), gemini-cli's shape: lockfile pinning every platform's native binary, Containerfile on `HARNESS_BASE_IMAGE`, entrypoint, `run.sh`, `thinking.env` (`--effort`, `model_reasoning_effort`), `conformance.env`, `hooks/guard.sh` (byte-identical to gemini-cli's) and a budget hook each. One provider per harness; `run.json` carries the served model (Claude: the assistant messages' `model`; codex: `response.completed` from a trace that never enters `OUT`).
- **gemini-cli first**: the worker mounts only its run directory (OUT's parent) and the uv cache, never `.crew/`; the guard's deny-list is the union of three vendors plus key files and `*_API_KEY`; budget hooks write `OUT/stop` and every `run.sh` prints `over MAX_TURNS|TOKEN_BUDGET|TIMEOUT_S (<n>)`; `MODEL_BASE_URL` is the one seam the suite sets; compose.yaml's three worker services share `x-crew-worker`, as does `app/compose.yaml`'s Postgres fragment; `RISK_HIGH_PLATFORM` gains `.claude/*`, `.codex/*`, `CLAUDE.md`, `AGENTS.md`.
- **The suite** (written by the gate-writer from the ADR, not the adapters): `gates/harness-conformance.sh` (nine cases), `gates/harness-conformance/stub.py` (one scripted model, three wire protocols, `<requested>-conformance` served), `proof.sh`, compose service `conformance-model`; `./go harness-conformance [CONFORMANCE_HARNESS=]`; a GitHub job. `./go ci` gets `ci/harness-shape.sh` and `ci/hooks.sh` in three input shapes.
- **Record**: `record` and `record-review` take any CLI harness; a non-gemini harness writes `fixtures/<ticket>/<role>/<harness>/`; both refuse `replay` and a set `MODEL_BASE_URL`.
- **Docs**: README "Coding harnesses" (table: guard in the hook, boundary the container, codex's sandbox off), `docs/reference.md`, `docs/ARCHITECTURE.md`, `docs/PLAN.md` §4 and §16 status note, `docs/use-on-your-repo.md`, `.env.example`, `ROADMAP.md`.

## Found (contradicts the plan or the brief)

1. **All three CLIs have hooks that fire headless**, so the plan's "where a vendor has no hooks, the guard is the container" never applies; the network stays open for all three (each must reach its provider) and closing egress is open before M24 runs on a repository the owner does not control (ADR 0041 §3).
2. **Codex's own sandbox cannot start in rootless podman** (bubblewrap, three ways tried); codex runs `danger-full-access` with the container as its sandbox.
3. **The suite is not inside `./go ci`**: `ci` has no engine socket and the suite builds three CLI images. `ci` runs the engine-free half; the full suite is `./go harness-conformance` and a workflow job (ADR 0041 §9).
4. **Three guard bypasses, older than M19, closed**: a repository's `.env` pointed gemini-cli's `GOOGLE_GEMINI_BASE_URL`, key included, at another host (now always set); a repository's `.claude/settings.json` with `disableAllHooks` and its `.codex/config.toml` with `[features] hooks = false` each switched the guard off (now `--setting-sources user` and `--enable hooks`; conformance case 4 proves it); the worker mounted `.crew/` with the release signing key `.crew/cosign.key`.
5. **Claude Code's session file lags the run**: a token budget read from `transcript_path` stopped three requests late; the hook now reads the stream-json output on PreToolUse.
6. **Codex 0.166.0 sends no top-level `tools`**: they ride in an `additional_tools` input item, in namespaces; the stub reads them there.
7. **gemini-cli refuses a workspace `.env` by itself** ("Path not in workspace") before its BeforeTool hook; case 3 counts such a refusal as stopped, the canary checks unchanged.
8. **The record command must name provider and model** (`MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5`, `openai gpt-6.1-sol`), M18's finding again; and `compose.yaml` alone is not a loadable project, so the suite runs with `workloads/minimal`'s fragment (ADR 0041 §8 corrected).
9. Claude Code refuses `--dangerously-skip-permissions` as root, and the crew service is uid 0 under rootless podman: the adapter uses `--tools`/`--allowedTools` instead (verified as uid 0).

## Not done, and open decisions for the owner

- **The owner's item:** no Claude or OpenAI recording exists. `./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=claude-code MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5` and `./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=codex MODEL_PROVIDER=openai MODEL=gpt-6.1-sol` are implemented and documented, not run: they spend your keys. They write `fixtures/0001/dev-worker/<harness>/`; replay does not read those yet. Their `run.json`s are the first measurement of `MAX_TURNS` and `TOKEN_BUDGET` outside Gemini (the first run may stop on a Gemini-measured budget) and of the per-run cost the README still owes.
- gemini-cli's BeforeTool matcher covers `run_shell_command|write_file|replace|read_file` only; `read_many_files`, `grep_search`, `glob` and `list_directory` reach files without the guard (the gate-writer's finding). Older than M19; matcher `.*` or excluding those tools, with a hook case, is a short follow-up.
- The guard is a deny-list on strings: `grep -r SECRET .` reads a key file without naming it. The container (only the run directory mounted) is the boundary; egress is the open question.
- `ROADMAP.md` still lists M18 and M20 under "Next".
- `.github/workflows/ci.yml`'s `harness-conformance` job has not run on GitHub (nothing pushed).
- Expect conflicts with M22's branch on `compose.yaml`, `Makefile`, `README.md`, `docs/reference.md` and `docs/PLAN.md` §16.

## First thing the next milestone should look at

M24 needs the two recordings above before anything else: run them, read `run.json`'s `tokens`, `turns` and `model`, and re-measure the budgets in `roles/` per provider (ADR 0041 §5). For M21, `adapters/*/run.sh`'s mount of the run directory is the pattern a GitHub token must follow: never in `.crew/`, never in the worker's view.

---

# Handoff: M20 "gates anywhere", 2026-11-03, branch `claude/vibrant-dubinsky-a82fa0`, not pushed, not merged

---

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
