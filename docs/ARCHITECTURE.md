# Architecture

## Ports and Adapters

The core knows no vendor. Every integration sits behind a port with at least two implementations.

| Port | Adapter | Note |
|---|---|---|
| `Workload` | `app`, any repository attached with `./go attach <path>` (`workloads/minimal` is one), or the gates half alone, drafted by `./go init` | What the platform operates on; chosen by `WORKLOAD=<dir>` (default the attached clone, else `app`), not by profile; an attached repository keeps its contract in `.lights-out/`, with a `worker.md` and an optional `policy.env` (ADR 0037); defines compose services, environment keys, /healthz and /metrics on :8000, flags, smoke/load/test scripts, fixtures; unnamed in core/, gates/, verify/, adapters/ (verified by ci/app-free.sh); proven by ./go demo-seam (ADR 0030) |
| `AgentHarness` | `replay`, `gemini-cli`, `claude-code`, `codex`, `antigravity-sdk`, `adk` | `replay`: copies fixture files from `fixtures/<ticket>/<role>/`; `gemini-cli`: runs a Gemini CLI container session with role prompt and budgets, records transcript and events; `claude-code` and `codex`: the same contract with Claude Code 2.1.311 (provider `anthropic`) or Codex 0.166.0 (provider `openai`), one provider per harness, the guard in the CLI's `PreToolUse` hook and the container as the boundary (ADR 0041); coding roles produce `OUT/patch`, `pr.json`, `run.json`; review roles produce `OUT/final.md` (first line APPROVED or CHANGES-REQUESTED, rest reason), `input_sha256` (sha256 of the document), `run.json`; `adk`: no workspace; `INPUT` file → `OUT/calls.json`, `final.md`, `run.json`; a role selects it with `HARNESS=adk` in its role.env (ADR 0020 §1); review roles use `HARNESS=gemini-cli` (ADR 0021 §3) |
| `CodeHost` | `gitea`, `github` | `gitea`: bootstrap (admin user, repo, Actions off), clone-url, push, open-pr, status, merge, pr; `github`: branch, PR, comments, merge |
| `Tracker` | `file`, `github-issues`, `linear` | `file`: reads `tickets/<id>.md`; others read from external service |
| `EventBus` | `pubsub-emulator`, `pubsub` | Verbs: `publish`, `pull`, `ack` |
| `StateStore` | `firestore-emulator`, `firestore` | Verbs: `get`, `put`, `delete` |
| `Orchestrator` | `inproc`, `cloud-workflows` | Verbs: `inproc/run.sh` |
| `Delivery` | `envoy-canary`, `cloud-deploy` | Stages, promote, rollback |
| `Metrics` | `prometheus`, `managed-prometheus` | Same PromQL query |
| `Flags` | `flagd`, `unleash` | OpenFeature SDK unchanged |
| `Registry` | `zot`, `artifact-registry` | Sign and verify |

**Rule: an adapter cannot introduce concepts into the core.** If Cloud Deploy has a concept that Envoy does not, either model it abstractly or keep it inside the adapter.

*Amended 2026-09-20 (ADR 0024, 0025, 0026) — decided, built in M8.* `ci/vendor-free.sh` proves the rule for the `Delivery` column by grepping `core/` for vendor names, comments included; its word list grows to `flagd|unleash`, now that the freeze check reads `adapters/$FLAGS/evaluate.sh` instead of a hardcoded flagd URL in `core/launchpad.sh`. The port contracts M8 changes:

| Port | Verbs after M8 | Note |
|---|---|---|
| `Delivery` | `deploy.sh <version> <image>`, `shift.sh <pct>`, `rollback.sh`, `status.sh` | four verbs. `ready.sh` is **not** one of them: every adapter in `PLANE_ADAPTERS` owes `make up` a readiness probe whatever its port (ADR 0012 §6), and the conformance suite never calls it. `status.sh` prints one JSON object with exactly three keys — `stable` (string), `canary` (string or `null`), `weight` (integer 0–100) — and nothing else (ADR 0026 §2) |
| `Registry` | `publish.sh <tag>`, `verify.sh <tag-or-ref>` | `publish.sh` builds the current checkout, pushes it under `sha-<commit>` and signs it, printing the immutable `repo@sha256:…`; `verify.sh` verifies the signature and prints the digest it verified, which is the digest that gets deployed (ADR 0025 §1) |
| `Flags` | `evaluate.sh <flag> [version]`, `set.sh <flag> <variant>` | the launchpad's freeze check and the `freeze`/`unfreeze`/`kill-switch` targets go through the port, so the same conformance case runs at L0 and L2 (ADR 0026 §3) |
| `CodeHost` | `await.sh <sha> <context>` | waits for a commit status the tower did not produce — the image build job — and prints its state (ADR 0025 §5) |

Every `Delivery` adapter must pass `gates/delivery-conformance.sh` to count as one: five cases, driven only through `core/launchpad.sh` and `core/promote.sh` (ADR 0024 §2, ADR 0026).

## Levels and Profiles

Four integration levels, each a profile (`profiles/l0.env` … `profiles/l3.env`). The Makefile selects one with `PROFILE ?= l0` and exports it. Adapter choices come from environment variables named after the ports above, except for the `Workload` port: it is chosen by `WORKLOAD=<dir>` (default `app`), not by the profile — it is the same workload at every level. See [ADR 0001](adr/0001-profiles-and-single-makefile.md) and [ADR 0030](adr/0030-workload-port.md).

*Amended 2026-09-20 (ADR 0022, 0028).* L0 and L1 are the whole product: every capability, no account, no key. L2 and L3 replace containers with managed services and add nothing the local plane lacks. `profiles/l2.env` and `profiles/l3.env` also carry `WORKBENCH_FLAVOUR=cloud`, which makes `./go` build `workbench/cloud/Containerfile` (gcloud and terraform) on top of the base workbench image; L0 and L1 never download either.

## Invariants

1. **One PromQL file:** `verify/slo.promql` is the only query that decides if the canary passes. It runs identically on Prometheus local (L0/L1) and on Managed Prometheus (L2/L3). This is the line that prevents L0 and L2 from diverging. At L2 this means Cloud Deploy's own `verify` stanza stays off: `core/launchpad.sh` decides at every level (ADR 0027 §3).

2. **One workflow YAML:** the same `.github/workflows/ci.yml` runs on Gitea Actions (L0/L1, where only the `image` job runs, [ADR 0039](adr/0039-the-gitea-runner-runs-only-the-image-job.md)) and GitHub Actions (L2/L3). The syntax is GitHub Actions. Gitea unsupported features are isolated in steps and skipped with conditions, never duplicated. See [ADR 0002](adr/0002-self-ci-is-make-ci.md).

3. **Nothing reaches staging unsigned:** the `Registry` port signs what it publishes and `core/launchpad.sh` verifies the signature before the first traffic, at every level — a local key pair at L0/L1, a KMS key at L2, the same cosign command. An unsigned image is `NO-GO: launchpad — unsigned image`. See [ADR 0022](adr/0022-local-first-cloud-optional.md) and [ADR 0025](adr/0025-release-artefact-build-sign-verify.md).

## Toolchain and Entrypoint

`./go <cmd>` is a POSIX sh script (the only host entrypoint). It:

1. Picks an engine (`CONTAINER_ENGINE`, else podman, else docker)
2. Builds or reuses the `workbench` image from `workbench/Containerfile`
3. Runs `make <cmd>` inside it with the repo mounted at the same absolute path
4. Passes the socket for targets that need it (`up`, `down`, `test`, `demo`, `release`, `demo-rollback`, `demo-seam`, `demo-hold`, `demo-launch`, `e2e`, `shell`, `gates`, `demo-gates`, `mutation-baseline`, `assign`, `demo-crew`, `record`, `triage`, `demo-triage`, `promote`, `record-evals`)
5. Runs without the socket for targets that do not (`ci`, `engine-compat`)

For `engine-compat` and `demo`, `./go` runs `ci/engine-compat.sh` on the host first.

See [ADR 0004](adr/0004-containerised-toolchain.md).

## Human gate

`core/launchpad.sh` writes `RELEASE_RECORD` (`.crew/release.json`) with the release outcome and metrics at each stage. `core/promote.sh` is go-for-launch: it reads the record, checks that the canary is held (not rolled back), runs the release role (at L1+) or renders the brief from the record (at L0), prints it, and asks for a human answer: `GO_FOR_LAUNCH=GO|NO-GO` if set, else one line from the terminal, else NO-GO. `GO` shifts the canary to 100% of traffic; `NO-GO` rolls it back. `demo-launch` proves this flow mechanically and runs on every push in the `launch` CI job. See [ADR 0020](docs/adr/0020-adk-agents-and-go-for-launch-at-m7.md) §4.

## Demo Stages

`./go demo` runs a fixed list of stages. A stage that exists runs for real. A stage that does not yet exist prints one line and does not fail:

```
[demo] rollback: NOT YET (M3)
```

| Stage | Milestone | What |
|---|---|---|
| engine-compat | M2 | Host-side, the selected engine: versions, `up`, `smoke` |
| ci | M0 | Repo self-checks |
| up | M2 | Start the L0 plane in compose, per-adapter readiness |
| smoke | M2 | Create a meetup through Envoy |
| verify | M1 | Check metric shape at M1; canary vs stable evaluation at M3 |
| deploy | M3 | Staging → 5% → 25%, held for human gate |
| rollback | M3 | Automatic on verify NO-GO, or manual trigger |
| e2e | M6 | Full path through the tower: ticket → PR → CI → merge → canary → verify NO-GO → rollback, audited |

`demo-launch` is not a stage of `./go demo` (ADR 0020 §4); it runs in the `launch` CI job to prove go-for-launch on every push. Neither is `delivery-conformance` (ADR 0026 §4).

See [ADR 0003](adr/0003-make-demo-before-m3.md).

## PR gates

Six gates run on a git range in order from cheap to expensive: `risk` (rules-not-points classifier), `secrets` (gitleaks), `deps` (osv-scanner), `sast` (bandit), `test` (pytest), `mutation` (cosmic-ray on changed lines against a measured baseline). Each gate exits with a single line: `GO: <name>`, optionally followed by ` — <detail>` (where a toolchain gate ran, ADR 0042 §3), or `NO-GO: <name> — <reason>`. The gates read the active workload's configuration (`WORKLOAD_MUTATION_SCOPE`, `WORKLOAD_LOCKFILES`, `WORKLOAD_KILL_SWITCH`, `MUTATION_BASELINE`) from its `workload.env` instead of hardcoding paths; the gates and the core/ platform code are guaranteed never to name a specific workload by `ci/app-free.sh` (ADR 0030). `sast`, `test` and `mutation` run the workload's declared command (`SAST_CMD`, `TEST_CMD`, `MUTATION_CMD`) where its `TOOLCHAIN_IMAGE` says, and say so on their GO line (ADR 0042).

The `risk` gate is unique: it always GO when it classifies (the verdict is the classification itself — `low` = auto-merge, `medium` or `high` = review). A NO-GO from `risk` means "could not classify" (bad input, missing policy file), not "found something bad". The classifier reads five signals from the diff: migrations, auth, payments, platform (gates/ci/verify/policy/core and the toolchain), and diff size. Policy is data, not code: `policy/merge.env` holds globs, thresholds, and the auto-merge decision, readable by both sh and Python without a parser.

Six committed fixture PRs prove both verdicts on real gate failures: `honest-fix` and `fake-test` resolve the same bug (ticket 0001) with adequate and inadequate tests; `migration`, `sast-finding`, `vulnerable-dep`, and `failing-test` each trigger a different gate. Fixtures are git-format-patch patches applied in detached worktrees, with expected JSON outcomes recorded in `expect` files; `./go demo-gates` runs them all and asserts success.

See [ADR 0015](adr/0015-pr-gates-at-m4.md) and [ADR 0016](adr/0016-risk-model-and-merge-policy.md).

## Crew flow

The ticket→PR pipeline at M5: `core/crew.sh` clones the repo, sources the role's budgets, runs the `AgentHarness` adapter on the ticket, commits the result with the crew identity, pushes to `CodeHost`, and opens a PR. The harness returns a patch, PR title and body, transcript, and metadata (model, tokens, duration). At L0, `replay` copies the fixture into the output directory and applies the committed patch; at L1, `gemini-cli` runs the role live and records the session. Both produce identical artifacts (except the harness name and model field). The PR branch passes through the same gate pipeline as a hand-written PR: `make gates BASE=<initial> HEAD=<harness-commit>`. `demo-crew` proves the flow on ticket 0001 and asserts both the PR and the gates are GO.

## Control plane

At M6, the tower is a state machine over a JSON document per ticket in the state store, driven by step events on the event bus. States are `opened` → `pr-opened` → `ci-passed` | `ci-failed` | `review` → `merged` → `rolled-back` | `held`; since M15 `ci-failed` requests `rework`, which goes back to `pr-opened` with the verdict for the worker or, at the cap, ends at `needs-human` (ADR 0038). Step events carry `{"ticket","step"}`. Idempotency: an event whose precondition does not match the current state is dropped and acked; effects are re-runnable. The merge seam is the CodeHost adapter: `merge.sh <pr> <head sha>` merges only at the head CI judged (`ci.head_sha`), and a head that moved fails the step (ADR 0019, amended 2026-11-02); at L0, `ci` is the gates run by the tower and posted as a commit status, not a runner job. The artefact document holds `pr`, `task`, `spec`, `ci`, `merge`, `release`, and `history` fields. `./go audit` rebuilds the chain and compares the state store against the code host (two NO-GO kinds: missing link or divergence).

## L0 plane

Eight services in `compose.yaml`:

| Service | Host port | What |
|---|---|---|
| Envoy | 8080 | The app's only entrance; shifts traffic between stable and canary via weighted clusters and admin API |
| Envoy admin | 9901 | Runtime config: `GET /runtime` reads weights, `POST /runtime_modify` shifts traffic |
| backend | implicit | Stable revision at port 8000 inside compose |
| backend-canary | implicit | Canary revision (started on-demand by deploy); at port 8000 inside compose |
| Gitea | 3000 | Rootless, sqlite; the Actions runner registers on start in host mode |
| Prometheus | 9090 | Scrapes both backends every 5 s; canary and stable tell apart by `service_version` label via `target_info` join |
| Zot | 5050 | OCI registry, empty until a merged PR is built into an image (M5 at the earliest); 5000 is macOS AirPlay |
| flagd | 8016 | OFREP; serves the active workload's `flags/flags.json` (`$WORKLOAD/flags/flags.json`, bind-mounted dynamically), the one bind mount |
| Pub/Sub emulator | 8085 | Event bus for the tower's step events (topic `tower`, subscription `tower-inproc`) |
| Firestore emulator | 8086 | State store: one JSON document per ticket (`tickets/<id>`) |

Vendor config lives in `adapters/<name>/`, copied into images at build; one bind mount (the active workload's `flags/`) into flagd. Readiness: `adapters/<name>/ready.sh`, run by `make up` for the adapters the profile selects.

The canary revision is the same image as stable, with the workload's kill-switch flag (for the app, `waitlist`) targeted at its canary version (for the app, `0.2.0-waitlist`); the Workload port generalizes this (ADR 0030). The controller `core/launchpad.sh` shifts traffic through Envoy's admin API and evaluates `verify/slo.sh` at each stage. Automatic rollback on verify NO-GO.

See [ADR 0012](adr/0012-l0-plane-layout-runner-envoy-readiness.md), [ADR 0013](adr/0013-launchpad-canary-verify-rollback-at-l0.md), [ADR 0014](adr/0014-prove-the-go-branch-with-demo-hold.md).

## Status

M20 — Gates anywhere (ADR 0042): `workload.env` has eleven keys. The three toolchain gates (`test`, `sast`, `mutation`) run the workload's declared command where `TOOLCHAIN_IMAGE` says (`workbench`, `compose:<service>` or an image) and name it on their line. `./go init [<path>]` drafts the gates half of `.lights-out/` in the clone, with a measured `MUTATION_BASELINE`, and `./go gates` needs no engine socket on the workbench form. `./go demo-init` proves attach, init and gates on `workloads/minimal` and `workloads/minimal-js` without the plane. The 300 s budget is proven for small suites only.

M18 — The model is a choice (ADR 0040): `MODEL_PROVIDER` and `MODEL` in `profiles/` or `.env`, roles keep `THINKING` and budgets; the thinking map lives in `adapters/<harness>/thinking.env` with a source per line; the ADK roles select Claude and OpenAI through ADK's `LiteLlm` with `reasoning_effort` and no planner, Gemini through ADK's own model and planner; `RecordingLlm`/`ReplayLlm` wrap either and the recordings carry `provider`; `run.json` of both harnesses reports `provider` and the served `model`, null at L0 with the fixture's under `recorded`; `ci/model-free.sh` keeps model ids and key names out of `core/`, `gates/`, `verify/`, `roles/`; `litellm==1.106.6` pinned in the workbench (+190 MB image); the non-Gemini recording path (`./go record-evals PROFILE=l1 MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5`) is implemented, not yet run.

M19 — `claude-code` and `codex` harnesses (ADR 0041): two adapters in `gemini-cli`'s shape, each pinned by `package-lock.json`, one provider each; the same `guard.sh` copied byte-identical into the CLI's pre-tool hook (gemini `BeforeTool`, Claude and Codex `PreToolUse`), the container as the boundary, codex's own sandbox off because it cannot start in rootless podman, the network open; the worker mounts its run directory, not `.crew`; budgets read from each vendor's signal; `MODEL_BASE_URL` as the one seam; `./go harness-conformance` runs every CLI harness against a scripted model (`gates/harness-conformance/stub.py`, nine cases, no key: plumbing, not a model's ability), with `harness-shape` and the extended `hooks` in `./go ci`; recording with another harness is `./go record … AGENT_HARNESS=claude-code|codex` into `fixtures/<ticket>/<role>/<harness>/`, implemented, not yet run, and replay does not read it.

M15 — The rework loop (ADR 0038): a gates NO-GO or a CHANGES-REQUESTED review no longer ends the ticket. `ci-failed` requests a `rework` step that runs dev-worker again from its own PR head with the ticket and the verdict (NO-GO line and the gate's details, or the reviewer's reason) as input; the new head meets the same judges. `policy/rework.env` caps a ticket at four attempts, then `needs-human`. Every history entry carries its attempt; `./go demo-rework` proves it at L0 on hand-written fixtures.

M12 — The Workload port (ADR 0030): the platform no longer operates on a hardcoded app but on any workload — a directory that owns a `workload.env` with seven keys, three compose services, health and metrics endpoints, one flag file, smoke/load/test scripts, and gate fixtures. `WORKLOAD=<path>` (default `app`) selects it; the app is one workload, `workloads/minimal/` is a second minimal workload that proves the seam. Every gate and the core platform read the active workload's configuration instead of hardcoding paths, verified by `ci/app-free.sh`. `./go demo-seam` is the acceptance test: runs the platform on `workloads/minimal` and asserts the release record's failing stage was specifically an `error_rate` NO-GO (proving both workloads' metrics were compared). `ci/workloads.sh` validates every workload's contract; `./go ci` swaps `compose` for `workloads` and gains `app-free`. Targets `demo-hold`, `demo-launch`, `demo-rollback`, `demo-gates`, and `delivery-conformance` remain unchanged; they now read the active workload's variables instead of the app's hardcoded ones.

M9 — Review: test-reviewer and architect roles with prompts on the existing gemini-cli harness (no ADK, these are reading roles); a `review` step in `core/tower.sh` (precondition `review`, next `ci-passed` or `ci-failed`), inserted where the risk classifier already routes medium/high PRs; review roles produce a second artefact contract with `final.md` (verdict and reason) and `input_sha256` (input document hash); ticket 0003's perimeter rule declares which files a ticket may change, checked in `core/perimeter.sh` before PR opens; two dev-worker `record` runs fix the token budget (ADR 0020 §9 measured 2.6M, down from provisional 12M) and validate ticket 0004's rewritten prompt; three new ci checks (`perimeter`, `review`, `tower` updated); medium-risk fixtures recorded at L1 and replayed at L0.

M7 — ADK agents and go-for-launch: product, ops-triage, release on ADK 2.9.1 with prompt.md and recorded model responses at L0 (`fixtures/adk/`), replay at L0 and live at L1+; adk eval suite with the ambiguous question and two misleading alerts; three new ci checks (`prompts`, `evals`, `promote`); `core/promote.sh` is go-for-launch reading `RELEASE_RECORD`, composing the brief (live at L1+, rendered from record at L0), and asking the human: GO_FOR_LAUNCH=GO|NO-GO; `./go promote` and `./go demo-launch` on every push; at L0 the promotion is Envoy weight 100 on the canary cluster, the canary does not become the stable image (M8).

M6 — Control plane: tower state machine in `core/tower.sh` with four step scripts in `core/steps/`, event bus (Pub/Sub emulator) and state store (Firestore emulator) adapters, `inproc` orchestrator, audit log that rebuilds deploy→PR→ticket→spec and cross-checks the code host, `./go e2e` runs the full path ticket→PR→CI→merge→canary→verify NO-GO→rollback with automated gates posted as commit status.
