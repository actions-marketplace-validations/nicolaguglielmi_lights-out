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
4. Passes the socket for targets that need it (`up`, `down`, `demo`, `e2e`, `shell`)
5. Runs without the socket for targets that do not (`ci`)

See [ADR 0004](adr/0004-containerised-toolchain.md).

## Demo Stages

`./go demo` runs a fixed list of stages. A stage that exists runs for real. A stage that does not yet exist prints one line and does not fail:

```
[demo] rollback: NOT YET (M3)
```

| Stage | Milestone | What |
|---|---|---|
| ci | M0 | Repo self-checks |
| engine-compat | M2 | Verify container engines (podman / docker) |
| up | M2 | Start the local plane in compose |
| deploy | M3 | Release to canary stage |
| verify | M3 | Run `verify/slo.promql` against canary and stable |
| rollback | M3 | Automatic rollback on NO-GO |
| e2e | M6 | Full path: ticket → PR → CI → canary → rollback |

See [ADR 0003](adr/0003-make-demo-before-m3.md).

## Milestone M0

At M0 only the skeleton exists: `go`, `Makefile`, profiles, `workbench/Containerfile`, and the repo self-checks in `ci/`. No `core/`, no `adapters/`, no application.

`./go demo` runs `make ci` and declares every other stage NOT YET.
