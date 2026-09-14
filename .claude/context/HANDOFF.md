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

## First thing M2 should look at: the pull+build budget — open decision, not resolved here

Two numbers were being conflated in an earlier draft of this section. Separate them first:

- **15 min** is the golden rule (plan §2, plan §3's "Tempo al primo rollback" row, CLAUDE.md "Regola d'oro"): `./go demo` reaching an automatic canary rollback at L0, no API key. All three sources tie this figure to the *same* command, once it exists — M3+. **No gate checks it today.** Nothing currently times `./go demo`/`./go up` or fails past a threshold.
- **5 min** is not from the plan or CLAUDE.md. ADR 0010 §Consequences invented it as a self-imposed sub-budget for "the plane" (pull+build only, no deploy/rollback), assuming a 20 Mbit/s connection. Where that split comes from is not documented anywhere else — it is ADR 0010's own assumption, not a decision anyone made.

Real M1 number, just measured: `./go demo` cold (python/postgres/node images removed, workbench already built) = **66s** on this machine's connection, roughly 3x faster than ADR 0010's 20 Mbit/s estimate (~3.5 min for the same pull+build). Measured against the actual 15-minute (900s) golden-rule ceiling — not ADR 0010's invented 5-minute one — M1 alone leaves **~834s (~13.9 min) of headroom** on a fast connection, or **~690s (~11.5 min)** under ADR 0010's pessimistic assumption, before M2 adds anything and before M3's real release-cycle-to-rollback time lands on top. That is a very different picture from "1.5 min left." The ADR 0010 budget crisis may not be real, or may be much smaller than stated — needs re-measuring with real M2 image sizes, not re-deriving from the old estimate.

M2 (plan §7) adds **eight** services, not six as an earlier draft of this note said: Gitea, act runner, registry Zot, Envoy (two weighted clusters), Prometheus, flagd, Pub/Sub emulator, Firestore emulator. None of their image sizes are verified against a pinned tag yet — that has to happen at M2 start, the same "verify before writing" pass ADR 0005-0010 did for M1, before either option below can be costed for real.

### Option A — raise the ceiling: 15 min covers first rollback, not today's `./go demo`

M2's `./go up`/`./go demo` (no deploy/canary/rollback exists until M3) isn't the thing the golden rule measures yet — plan §2/§3 and CLAUDE.md tie the 15 minutes to the command *once it reaches rollback*.

- No numeric change to the 15-minute figure itself; it stays as written in plan §2/§3 and CLAUDE.md's Regola d'oro.
- What changes: `./go demo`/`./go up` at M1/M2 gets no artificial ceiling of its own — only the full path once M3 lands (clone → up → deploy → verify → rollback) has to fit in 15 min.
- Cost: a gate to check the *real* ceiling doesn't exist yet and would need to — wall-clock timing wired into `demo-rollback` at M3, printing elapsed time and NO-GO past 15 min. That's M3 work, not M2's; M2 gets no new gate under this option.
- Risk: doesn't remove the constraint, only moves the measurement point from "now" to "M3." If the real release cycle (5%→25%→100%, verify, rollback) adds more than a minute or two, that comes out of whatever M1+M2 already spent.

### Option B — split M2: canary plane vs. full L0 plane

- `./go demo` (and plain `./go up`) raises only the minimal canary path: Envoy, Prometheus, flagd — the request-path-plus-canary story the golden rule is actually about.
- Gitea, act runner and Zot move to a second group, raised only by an explicit `./go up --full` (or a second compose profile) — needed for the PR/CI half of the golden path (plan §8), not for canary/rollback.
- Cost: changes M2's own acceptance criterion as written in plan §7 ("`./go up` alza tutto, apri Gitea su localhost…" assumes one `up` that raises everything) — needs its own ADR at M2 start to redefine what "M2 done" means, plus two Makefile targets or compose profiles, plus README/PLAN wording updates.
- Benefit: `./go demo` only ever pays the minimal-group cost, not Gitea+act-runner+Zot's. The full L0 experience (open Gitea, watch a PR go through CI) still costs the same total time when `--full` is invoked — this reorders when the cost is paid, it does not remove it.
- Unmeasured: Envoy/Prometheus/flagd image sizes aren't verified against any pinned tag yet, so the minimal-group budget can't be given a real number today.

Decide at M2 start. A keeps one `./go demo`/`./go up` for the whole L0 plane and defers the real constraint to M3's rollback gate (not yet built). B keeps `./go demo` fast now but changes M2's plan §7 acceptance criterion and needs real Envoy/Prometheus/flagd image-size numbers before it can be evaluated.
