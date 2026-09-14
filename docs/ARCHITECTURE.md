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
| verify | M1 | Check metric shape only; evaluation at M3 |
| deploy | M3 | Release to canary stage |
| rollback | M3 | Automatic rollback on NO-GO |
| e2e | M6 | Full path: ticket → PR → CI → canary → rollback |

See [ADR 0003](adr/0003-make-demo-before-m3.md).

## L0 plane

Eight services in `compose.yaml`:

| Service | Host port | What |
|---|---|---|
| Envoy | 8080 | The app's only entrance; stable 100%, canary 0% with no upstream until M3 |
| Gitea | 3000 | Rootless, sqlite; the Actions runner registers on start in host mode |
| Prometheus | 9090 | Scrapes the backend every 5 s |
| Zot | 5050 | OCI registry, empty until M3; 5000 is macOS AirPlay |
| flagd | 8016 | OFREP; serves app/flags/flags.json, the one bind mount |
| Pub/Sub emulator | 8085 | Unused until M6 |
| Firestore emulator | 8086 | Unused until M6 |

Vendor config lives in `adapters/<name>/`, copied into images at build; one bind mount (`app/flags/`) into flagd. Readiness: `adapters/<name>/ready.sh`, run by `make up` for the adapters the profile selects.

See [ADR 0012](adr/0012-l0-plane-layout-runner-envoy-readiness.md).

## Status

M2 — app + L0 plane in compose; no `core/`, no control plane, no agents yet.
