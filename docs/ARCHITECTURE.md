# Architecture

## Ports and Adapters

The core knows no vendor. Every integration sits behind a port with at least two implementations.

| Port | Adapter | Note |
|---|---|---|
| `AgentHarness` | `replay`, `gemini-cli`, `antigravity-sdk`, `adk` | Executes a role on a workspace, returns artifacts |
| `CodeHost` | `gitea`, `github` | Branch, PR, comments, merge |
| `Tracker` | `file`, `github-issues`, `linear` | The ticket is the work source |
| `EventBus` | `pubsub-emulator`, `pubsub` | Same code, different endpoint |
| `StateStore` | `firestore-emulator`, `firestore` | Workflow state, idempotence |
| `Orchestrator` | `inproc`, `cloud-workflows` | Ticket lifecycle state machine |
| `Delivery` | `envoy-canary`, `cloud-deploy` | Stages, promote, rollback |
| `Metrics` | `prometheus`, `managed-prometheus` | Same PromQL query |
| `Flags` | `flagd`, `unleash` | OpenFeature SDK unchanged |
| `Registry` | `zot`, `artifact-registry` | Sign and verify |

**Rule: an adapter cannot introduce concepts into the core.** If Cloud Deploy has a concept that Envoy does not, either model it abstractly or keep it inside the adapter.

## Levels and Profiles

Four integration levels, each a profile (`profiles/l0.env` … `profiles/l3.env`). The Makefile selects one with `PROFILE ?= l0` and exports it. Adapter choices come from environment variables named after the ports above. See [ADR 0001](adr/0001-profiles-and-single-makefile.md).

## Invariants

1. **One PromQL file:** `verify/slo.promql` is the only query that decides if the canary passes. It runs identically on Prometheus local (L0/L1) and on Managed Prometheus (L2/L3). This is the line that prevents L0 and L2 from diverging.

2. **One workflow YAML:** the same `.github/workflows/ci.yml` runs on Gitea Actions (L0/L1) and GitHub Actions (L2/L3). The syntax is GitHub Actions. Gitea unsupported features are isolated in steps and skipped with conditions, never duplicated. See [ADR 0002](adr/0002-self-ci-is-make-ci.md).

## Toolchain and Entrypoint

`./go <cmd>` is a POSIX sh script (the only host entrypoint). It:

1. Picks an engine (`CONTAINER_ENGINE`, else podman, else docker)
2. Builds or reuses the `workbench` image from `workbench/Containerfile`
3. Runs `make <cmd>` inside it with the repo mounted at the same absolute path
4. Passes the socket for targets that need it (`up`, `down`, `test`, `demo`, `demo-rollback`, `e2e`, `shell`)
5. Runs without the socket for targets that do not (`ci`, `engine-compat`)

For `engine-compat` and `demo`, `./go` runs `ci/engine-compat.sh` on the host first.

See [ADR 0004](adr/0004-containerised-toolchain.md).

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
| e2e | M6 | Full path: ticket → PR → CI → canary → rollback |

See [ADR 0003](adr/0003-make-demo-before-m3.md).

## PR gates

Six gates run on a git range in order from cheap to expensive: `risk` (rules-not-points classifier), `secrets` (gitleaks), `deps` (osv-scanner), `sast` (bandit), `test` (pytest), `mutation` (cosmic-ray on changed lines against a measured baseline). Each gate exits with a single line: `GO: <name>` or `NO-GO: <name> — <reason>`.

The `risk` gate is unique: it always GO when it classifies (the verdict is the classification itself — `low` = auto-merge, `medium` or `high` = review). A NO-GO from `risk` means "could not classify" (bad input, missing policy file), not "found something bad". The classifier reads five signals from the diff: migrations, auth, payments, platform (gates/ci/verify/policy/core and the toolchain), and diff size. Policy is data, not code: `policy/merge.env` holds globs, thresholds, and the auto-merge decision, readable by both sh and Python without a parser.

Six committed fixture PRs prove both verdicts on real gate failures: `honest-fix` and `fake-test` resolve the same bug (ticket 0001) with adequate and inadequate tests; `migration`, `sast-finding`, `vulnerable-dep`, and `failing-test` each trigger a different gate. Fixtures are git-format-patch patches applied in detached worktrees, with expected JSON outcomes recorded in `expect` files; `./go demo-gates` runs them all and asserts success.

See [ADR 0015](adr/0015-pr-gates-at-m4.md) and [ADR 0016](adr/0016-risk-model-and-merge-policy.md).

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
| flagd | 8016 | OFREP; serves app/flags/flags.json, the one bind mount |
| Pub/Sub emulator | 8085 | Unused until M6 |
| Firestore emulator | 8086 | Unused until M6 |

Vendor config lives in `adapters/<name>/`, copied into images at build; one bind mount (`app/flags/`) into flagd. Readiness: `adapters/<name>/ready.sh`, run by `make up` for the adapters the profile selects.

The canary revision is the same image as stable, with `waitlist` targeted at the version string `0.2.0-waitlist`. The controller `core/launchpad.sh` shifts traffic through Envoy's admin API and evaluates `verify/slo.sh` at each stage. Automatic rollback on verify NO-GO.

See [ADR 0012](adr/0012-l0-plane-layout-runner-envoy-readiness.md), [ADR 0013](adr/0013-launchpad-canary-verify-rollback-at-l0.md), [ADR 0014](adr/0014-prove-the-go-branch-with-demo-hold.md).

## Status

M4 — PR gates in `gates/` with policy in `policy/merge.env` (risk scoring, dependency scan, SAST, test, mutation with threshold); six fixtures prove both verdicts; still no agents yet.
