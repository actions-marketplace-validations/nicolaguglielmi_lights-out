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

## First thing M2 should look at

**Pull+build budget:** M1's base images total ~250 MB (python 46 MB + postgres 117 MB + node 81 MB) plus wheels and npm ≈ 375 MB download. At the measured 66s for a full cold build, ~3.5 min is base image pulls and builds, leaving ~1.5 min of the 5-minute budget for M2's six new services (Gitea, act runner, Zot, Envoy, Prometheus, flagd, Pub/Sub + Firestore emulators). The only path forward is ADR 0009's fix: publish the app image by digest with build fallback, the same mechanism ADR 0004 point 3 planned for workbench. Without that, `./go up` will exceed budget before M2's acceptance command runs. Do not discover this mid-milestone.
