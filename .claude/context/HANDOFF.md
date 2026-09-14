# Handoff: M1 closed on 2026-09-14

## Acceptance

App base images removed first (python, postgres, node — workbench image itself already built from M0), rootless podman 5.7.1 on macOS (podman machine, arm64):

```
$ git clone <repo> && cd lights-out && ./go demo
[demo] ci (M1): running
GO: secrets
GO: lint
GO: shell
GO: help
GO: readme
GO: gitea-compat
GO: profiles
GO: contract
GO: ci
[demo] engine-compat: NOT YET (M2)
[demo] up: app only, plane at M2
[demo] smoke: http://host.containers.internal:8080/healthz ok
[demo] verify: metric shape only, evaluation at M3
[demo] deploy: NOT YET (M3)
[demo] rollback: NOT YET (M3)
[demo] e2e: NOT YET (M6)
lights-out: app running at http://host.containers.internal:8080
GO: demo, milestone M1. Green means the repo is coherent and the app answers; canary and rollback are not real yet.
./go demo: 66s total (base images removed first: python, postgres, node repulled; workbench image itself was warm)
```

Tests and verify with a warm compose:

```
$ ./go test
.........................                                                [100%]
25 passed, 2 warnings in 8.99s
```

```
$ ./go verify
GO: metric-shape
[stderr] checking query/app agreement against one live /metrics scrape
[stderr] rate() and histogram_quantile() need a real TSDB — Prometheus at M2, canary vs stable comparison at M3
```

## What changed

- `app/` now holds the backend (FastAPI + psycopg + stdlib auth), the frontend (React + Vite + TypeScript), the fake geocoder (http.server), and the contract and flag files.
- Makefile gains `test` (backend pytest on compose Postgres) and `verify` (metric-shape gate on the live app).
- Compose has five services: postgres, migrate (forward-only SQL runner), geocoder fake, backend, backend-test (profiles: ["test"]).
- `verify/metric-shape.sh` gate checks that `slo.promql` queries reference metrics the app actually emits.

## Found while building, contradicting or missing from docs/PLAN.md

1. **ADR 0007 correction (already noted in the file, 2026-09-14):** the flagd file watcher's poll interval is `FLAGD_DEADLINE_MS` (default 500 ms), not a fixed 5 s as first assumed. Verified in `openfeature-provider-flagd` 0.5.2 source.

2. **Backend flags initialization:** `app/backend/meetups/flags.py` was corrected from `api.set_provider(FlagdProvider())` to `api.set_provider_and_wait(FlagdProvider())`, because `openfeature-sdk` 0.10.0 initializes the flagd resolver on a background thread. Any flag evaluation before that thread finishes silently returns the SDK's built-in default rather than the file's value. Was invisible at M1 only because the flag's own default is `off` (matching the file), but this is a correctness fix for all future flags.

3. **Testcontainers / Ryuk in rootless podman:** still unresolved and deferred to M4 by deliberate choice. M1 deliberately chose the stdlib fake-geocoder-in-a-thread approach (ADR 0006) specifically to avoid Testcontainers at this milestone. The remaining rootless podman integration testing infrastructure will arrive with M4's gates, not discovered mid-milestone.

## First thing M2 should look at: the pull+build budget — decided (Option A), 2026-09-14

Two numbers were being conflated in an earlier draft of this section. Separate them:

- **15 min (900 s)** is the golden rule (plan §2, plan §3's "Tempo al primo rollback" row, CLAUDE.md "Regola d'oro"): `./go demo` reaching an automatic canary rollback at L0, no API key. All three sources tie this figure to the *same* command, once it exists — M3+.
- **5 min** was not from the plan or CLAUDE.md. ADR 0010 §Consequences had invented it as a self-imposed sub-budget for "the plane" (pull+build only, no deploy/rollback), assuming a 20 Mbit/s connection, with no documented source. **Cancelled** (ADR 0010, corrected 2026-09-14): not traceable to a measurement, an external constraint, or a decision anyone made.

**Decision (A): the 900 s ceiling stays exactly as written, and it measures `./go demo` through to rollback — not today's `./go up`/`./go demo`.** No new sub-budget replaces the cancelled one. The timing gate that enforces 900 s is built at **M3**, on `demo-rollback` (wall-clock timing, `NO-GO` past 900 s), once rollback exists to time. M2 gets no new gate and no budget arithmetic from this decision; its plan §7 acceptance criterion is unchanged, M2 stays intact as planned.

**Baseline, recorded so M2/M3 show drift instead of guessing it:** `./go demo` cold (python/postgres/node images removed, workbench already built) = **66 s**, measured at M1 close on this machine's connection (see Acceptance above). Compare each future milestone's `./go demo` time against this 66 s, not against ADR 0010's retired 3.5 min estimate.

M2 (plan §7) adds **eight** services: Gitea, act runner, registry Zot, Envoy (two weighted clusters), Prometheus, flagd, Pub/Sub emulator, Firestore emulator. None of their image sizes are verified against a pinned tag yet — that verification happens at M2 start, the same "verify before writing" pass ADR 0005-0010 did for M1. M2's own acceptance criterion (one `./go up` raises everything) is unchanged by this decision; if M2's real measured time threatens the 900 s rollback ceiling, that surfaces at M3 when the timing gate is built, not as a guess now.
