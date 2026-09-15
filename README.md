# lights-out

Six agents ship it. One human turns the lights back on.

Six agent roles take a ticket to production on a Google stack. At every step, a gate answers GO or NO-GO. The last gate is human: the flight readiness poll before the canary goes to 100%.

## Status

Milestone M5 of 10. What runs today:

| Stage | Milestone | Real |
|---|---|---|
| ci | M0 | ✓ |
| engine-compat | M2 | ✓ host-side, selected engine |
| up | M2 | ✓ L0 plane, 8 services beside the app |
| smoke | M2 | ✓ a meetup created through Envoy |
| verify | M1 | ✓ metric shape at M1, canary vs stable at M3 |
| deploy | M3 | ✓ staging → 5% → 25%, held for human gate |
| rollback | M3 | ✓ automatic on verify NO-GO, triggered by `./go demo-rollback` |
| PR gates | M4 | ✓ six fixture PRs prove risk, SAST, deps, test, mutation, secrets |
| ticket → PR | M5 | ✓ crew driver, six roles, one real run recorded, replay at L0 |
| e2e | M6 | NOT YET |

| | |
|---|---|
| **Frontend** | No tests until M10. TypeScript type-check in the image build is the only frontend check at M1. |

A green `./go demo` reaches automatic rollback: the failing version (same image, `waitlist` targeted on) clears staging, fails verify at 5%, rolls back to 100/0 on its own, and exits nonzero. Promotion to 100% is the M6 human gate.

The PR gates (`./go demo-gates`) run on six committed fixture patches and prove both verdicts: risk scoring, dependency scanning, SAST, test failure, mutation inadequacy, and secrets. `./go demo-crew` proves the ticket→PR pipeline: the crew container runs the dev-worker role on ticket 0001, opening a PR that passes `make gates`. At L0 the fixture is replayed; at L1 a real run against the Gemini API is recorded.

## Quick start

Prerequisites: podman (rootless), git, a POSIX shell. Nothing else.

On macOS, podman runs inside `podman machine`, a VM. The docker CLI is compatible but not the documented path; use `CONTAINER_ENGINE=docker` if needed.

```sh
git clone <this repository>
cd lights-out
./go demo
```

Then explore:

```sh
./go up              # start the L0 plane and wait for it
./go smoke           # create a meetup through Envoy
./go engine-compat   # host-side engine gate: versions, then up and smoke
./go down            # stop the plane
./go test            # run backend tests
./go verify          # check the metric shape
./go demo-rollback   # release the failing version and prove automatic rollback
./go demo-hold       # release the same version with kill switch on and prove it holds at 25%
./go demo-gates      # run all six PR gate fixtures and prove both verdicts
./go assign          # turn a ticket into a PR: TICKET=<id> [ROLE=dev-worker]
./go demo-crew       # prove ticket 0001 becomes a PR that passes the M4 gates (L0 replay)
./go record          # run a ticket for real at L1 and save the fixture: TICKET=<id> [ROLE=dev-worker]
./go mutation-baseline # measure baseline mutation score on the whole package
./go kill-switch     # turn off waitlist for all versions (manual flag edit)
./go freeze          # stop launchpad from deploying or shifting (manual flag edit)
./go unfreeze        # re-enable launchpad after freeze
./go help            # list all targets
./go shell           # interactive shell inside workbench
./go clean           # remove the workbench image
```

The first run builds the workbench image (about 1 GB on disk, 350–400 MB download, 3–6 minutes depending on connection speed). The plane pulls about 840 MB (amd64) / 720 MB (arm64) of images on the first run, the emulators image being more than half (measured 2026-09-14, ADR 0012). The image includes gcloud and terraform, although nothing uses them before M8.

## Levels

| | L0 · Replay | L1 · Local | L2 · Cloud | L3 · Platform |
|---|---|---|---|---|
| **Needs** | podman rootless (podman machine on macOS) | + Gemini API key | + GCP project with billing | + Agent Engine quota |
| **Models** | Recorded responses (fixtures) | Gemini API, `gemini-3.5-flash` (Gemini CLI v0.59.0 serves 3.5 not 3.8) | Gemini Enterprise Agent Platform, `gemini-3.8-flash` | idem + thinking level per role |
| **Harness worker** | Replay from `fixtures/` | Gemini CLI headless in compose | Gemini CLI on Cloud Run Job | + adapter Antigravity SDK |
| **Git and PR** | Gitea in compose | Gitea | GitHub real | GitHub real |
| **CI** | Gitea Actions (act runner) | Gitea Actions | GitHub Actions or Cloud Build | idem |
| **Registry** | Zot local | Zot | Artifact Registry + Binary Authorization | idem |
| **Canary** | Envoy weighted cluster | Envoy | Cloud Deploy → Cloud Run | + option GKE |
| **Metrics** | Prometheus | Prometheus | Managed Prometheus + Cloud Monitoring | idem |
| **Flags** | flagd (file) | flagd | flagd on Cloud Run or Unleash | idem |
| **Events and state** | Pub/Sub emulator + Firestore emulator | idem | Pub/Sub + Firestore | + adapter Cloud Workflows |
| **Agent ADK** | Stub | ADK local (`adk web`) | ADK on Cloud Run | Agent Engine + BigQuery analytics |
| **Time to first rollback** | < 15 min | < 20 min | ~45 min (terraform apply) | ~90 min |

*Note: Google renamed Vertex AI to Gemini Enterprise Agent Platform in April–May 2026. The endpoints, `GOOGLE_GENAI_USE_VERTEXAI` environment variable, and `aiplatform.googleapis.com` remain unchanged; `vertex` still appears in env vars and Terraform.*

*Note: since June 18, 2026 Gemini CLI no longer serves Google AI Pro/Ultra, Gemini Code Assist for individuals, or the free login with Google. The documented path is a Gemini API key (free tier: about 250 requests per day, Flash models only) or Gemini Enterprise Agent Platform. Whether a free-tier key still works with Gemini CLI is verified at M5.*

Only L0 exists today. Levels L1–L3 describe the plan.

## The app

A meetup RSVP platform: FastAPI backend (`app/backend/`), Postgres database, React frontend (`app/frontend/`). After `./go up` it answers behind Envoy at `http://localhost:8080` on the host or `http://host.containers.internal:8080` from inside workbench. Three auth-free endpoints list meetups, two auth routes signup and login, one create route, one RSVP route. Geocodes venues through a fake `GEOCODER_URL`. Feature-flagged partial waitlist (evaluates but returns 501 at M1).

Test and verify commands:
- `./go test` — Run the backend test suite against compose Postgres (pytest, 25 tests).
- `./go verify` — Check `verify/slo.promql` against the live app (metric shape only; evaluation at M3).

## PR gates

Six gates run in order on a git range (two commits or more, measured by `git merge-base`), with both verdicts proven by committed fixture patches. Run with `./go demo-gates` on the six fixtures, or `./go gates BASE=<ref> HEAD=<ref>` on your own range.

**Order:** risk (rules-based classification from path and size), secrets (gitleaks history and working tree), deps (osv-scanner on both lockfiles, a time bomb by design), SAST (bandit on `app/backend/meetups/` only), test (pytest, one failing assertion proves it works), mutation (cosmic-ray on changed lines, scored against a measured baseline).

**Risk levels:** `low` → `auto-merge`; `medium` or `high` → review. The risk classifier reads five signals: auth, payments, migrations, platform (gates/ci/verify/policy/core and the toolchain), and diff size. Policy lives in `policy/merge.env`, readable by sh and Python.

**Six fixtures:** `honest-fix` (ticket 0001 resolved, every gate GO, risk low); `fake-test` (same fix, inadequate test, mutation NO-GO); `migration` (adds a schema column, every gate GO, risk high); `sast-finding` (one bandit issue); `vulnerable-dep` (a known advisory); `failing-test` (one assertion fails). Each fixture is a git-format-patch `.patch` file applied in a worktree, with expected verdicts and JSON data recorded in `expect`.

**Declared limits:** SAST scans only the shipped package at `app/backend/meetups/`; tests and fakes are not scanned. Dependency scan covers both dev and runtime dependencies in the app and workbench (cosmic-ray and other test tools are included) and is live-validated against the OSV database over the network; `adapters/gemini-cli/package-lock.json` (the Gemini CLI platform toolchain) is declared and not scanned, like workbench's own pinned binaries; the same commit can go from GO to NO-GO overnight with no code change when a new advisory lands (the fix is a version bump or an `osv-scanner.toml` ignore entry with a reason). The migration fixture's column lands in the shared `postgres-data` named volume (the same one `./go up` and `./go test` use) and stays there across runs, harmless to every current test (they use explicit column lists, never `SELECT *`); `./go down` does not remove it, only `docker-compose --profile test --profile canary down -v` from inside `./go shell` does, or a fresh clone. At M4 the Gitea runner has no engine socket; the `gates` CI job runs only on GitHub (`if: github.server_url == 'https://github.com'`). At M6 the socket arrives under three conditions: the runner is the only service with it, jobs run only on refs the workbench user pushed, and the README's L0 trusted-network line extends to say the runner controls your engine.

**Model reality check:** Plan §5 commits to `gemini-3.8-flash` for every role. The model exists and is reachable, but Gemini CLI v0.59.0 silently serves `gemini-3.5-flash` instead, with no warning or error. The fixture at `fixtures/0001/dev-worker/` is recorded against what actually runs (`gemini-3.5-flash`), not what was requested. See ADR 0017 for details and the consequences when the CLI version changes.

## The L0 plane

Eight services run beside the app in `compose.yaml`. `./go up` returns only after each adapter's `adapters/<name>/ready.sh` answered.

| Service | Host port | What |
|---|---|---|
| Envoy | 8080 | The app's only entrance; shifts traffic between `stable` and `canary` via weighted clusters, admin API on 9901 |
| Envoy admin | 9901 | Runtime config: `GET /runtime` reads weights, `POST /runtime_modify` shifts traffic between stable and canary |
| backend | implicit | Stable revision, answering at port 8000 inside compose |
| backend-canary | implicit | Canary revision (started on-demand by deploy, same image as backend); answering at port 8000 inside compose |
| Gitea | 3000 | Rootless, sqlite; bootstrap creates a fixed admin user (`lights-out` / `lights-out-local-not-a-secret`) and a public `lights-out/lights-out` repo with Actions disabled; the runner registers on start in host mode |
| Prometheus | 9090 | Scrapes both backends every 5 s; canary and stable tell apart by the `service_version` label reached via `target_info` join |
| Zot | 5050 | OCI registry, empty until a merged PR is built into an image (M5 at the earliest); 5000 is macOS AirPlay |
| flagd | 8016 | OFREP; serves `app/flags/flags.json`, the one bind mount; edit the file and the flag flips within seconds |
| Pub/Sub emulator | 8085 | Unused until M6 |
| Firestore emulator | 8086 | Unused until M6 |

`./go smoke` signs up, logs in and creates a meetup through Envoy.

**L0 assumes a trusted network**: every port is unauthenticated on every interface, the runner registration token in compose.yaml is public by design, and anyone on the LAN can register a runner or push to Zot.

At L0 the canary revision reuses the same image as stable, with the `waitlist` feature flag targeted at the version string `0.2.0-waitlist`: the failing version is the same code, different flag targeting. The first real code diff arrives with the M5 worker.

## Release controller

`core/launchpad.sh` is the production release flow at every level. It stages a canary through four phases: `staging` (app readiness), `5%`, `25%`, then holds for the human gate (M6 `go-for-launch`). At each phase except staging it evaluates `verify/slo.sh`, comparing the canary against stable on three metrics: `traffic`, `error_rate`, and `latency_p95`. A NO-GO at any stage rolls back automatically to 100/0 on stable.

The controller itself generates no load; the Makefile starts `app/load.sh` beside it (one user looping through registration POSTs), stopping when the controller exits.

At L0, the release is a manual Makefile target (`./go release` with `CANARY_VERSION`). Two proof commands demonstrate the two branches:

- `./go demo-rollback` releases the failing version (waitlist on), expects NO-GO at 5%, and asserts the rollback (weights.canary=0, traffic on stable). This is now `./go demo`'s last stage.
- `./go demo-hold` releases the same failing version with the kill switch thrown first (waitlist off), expects GO all the way, and asserts the canary is held at 25% (not silently rolled back), then rolls back itself for clean state. A reader can step through the stages or let it run end-to-end (~140 s warm).

Both are manual, optional; only `./go demo` (which includes `demo-rollback`) is on the critical path.

**Kill switch and freeze** are feature-flag edits in the committed `app/flags/flags.json`, live within seconds through flagd's file poller, no deploy:
- `./go kill-switch` turns `waitlist` off for every version: the canary stops producing 501s.
- `./go freeze` / `./go unfreeze` toggle the `release-freeze` flag: `on` stops launchpad from deploying or shifting.

**Timing budget**: plan §2 requires `./go demo` to reach automatic rollback in under 900 s on a fresh container (cold pulls included). M3 measured this at 92 s warm (images already present); with the baseline 258 s cold from M2, a reasoned estimate is roughly 350 s total, well under budget. (Caveat: the 350 s figure is an estimate, not a fresh cold measurement this session, because forcing a safe cold re-pull of ~50 host images was not performed here.)

## How it runs

`./go <target>` builds `workbench/Containerfile` and runs `make <target>` inside it with the repo mounted at the same absolute path as on the host. The workbench image carries make, git, gcloud, terraform, and all verification tools, so the host needs only a container engine and a shell.

Profiles: `./go demo PROFILE=l2` selects `profiles/l2.env`. Secrets go in `.env` (gitignored, template `.env.example`). L0 needs no `.env`.

### Engine socket

Targets `up`, `down`, `test`, `demo`, `demo-rollback`, `e2e`, and `shell` mount the engine's API socket into workbench, which gives the container full control of the engine. It can start privileged containers, read any volume, and delete images.

The `ci` target never gets the socket. `engine-compat` is the one gate that runs on the host itself, before workbench starts: `./go engine-compat` and `./go demo` both begin with `ci/engine-compat.sh`.

### Rootless notes

The engine socket is `unix:///run/user/$(id -u)/podman/podman.sock`. Enable it with:

```sh
systemctl --user enable --now podman.socket
```

(On macOS, `podman machine` enables it automatically.)

This is the same socket path for the Gitea runner.

Rootless podman usage:

- All published ports must be above 1024.
- Bind mounts get no `:z` (relabelling fails on podman machine's virtiofs, podman #26465/#21269); the one bind-mounted service (flagd) uses `security_opt: label=disable`.
- Use `host.containers.internal` instead of `host.docker.internal`.
- Prefer compose network aliases over any `host.*.internal` name.

Only the docker-compose features proven by `./go engine-compat` are allowed; proven at M2 on podman: `build` with `args`, `depends_on` long syntax, `profiles`, `ports`, `user`, `restart`, `security_opt`, a read-only bind mount.

## Repository

```
lights-out/
  LICENSE                   # Apache 2.0 license
  NOTICE                    # copyright
  README.md                 # this file
  Makefile                  # targets: help, ci, ci-*, demo, up, smoke, down, test, verify, demo-rollback, demo-hold, kill-switch, freeze, unfreeze, e2e
  go                        # host entrypoint, POSIX sh
  .env.example              # template for secrets (gitignored)
  .gitignore

  workbench/
    Containerfile           # the toolchain: make, gcloud, terraform, tools
    fetch.sh                # script for verifying downloads

  core/
    launchpad.sh            # release controller: stages, verify gates, automatic rollback
    risk.py                 # risk classifier: rules-based PR scoring
    tests/                  # unit tests for risk.py

  policy/
    merge.env               # policy-as-code: risk levels, mutation baseline and margin

  gates/                    # PR gates: risk, secrets, deps, sast, test, mutation
    *.sh                    # individual gate scripts
    fixtures/               # six committed example PRs with expected verdicts
      <name>/
        *.patch             # git-format-patch applied in worktrees
        expect              # expected gate outcomes and JSON data

  profiles/
    l0.env                  # L0: podman, no key, no account
    l1.env                  # L1: + Gemini API key
    l2.env                  # L2: + GCP project
    l3.env                  # L3: + Agent Engine quota

  ci/                       # repo self-checks; each prints one line, GO or NO-GO
    lib.sh                  # go / nogo helpers, the output contract
    contract.sh             # meta-gate: every gate honours the contract
    secrets.sh              # gitleaks, history and working tree
    lint.sh                 # actionlint on the workflow
    shell.sh                # shellcheck on every sh script
    help.sh                 # make help exits 0
    readme.sh               # every ./go X in README exists
    gitea-compat.sh         # workflow uses only what Gitea Actions supports
    profiles.sh             # profiles are plain KEY=value, same keys
    compose.sh              # docker-compose config -q
    engine-compat.sh        # host side, runs first in ./go (ADR 0012)

  docs/
    ARCHITECTURE.md         # ports and adapters
    PLAN.md                 # working plan (Italian)
    adr/                    # architecture decision records
      0001-profiles-and-single-makefile.md
      0002-self-ci-is-make-ci.md
      0003-make-demo-before-m3.md
      0004-containerised-toolchain.md
      0005-backend-stack-and-auth.md
      0006-external-service-geocoder-fake-and-contract.md
      0007-metrics-and-feature-flags.md
      0008-sql-migrations-expand-contract.md
      0009-frontend-built-into-backend-image.md
      0010-compose-layout-and-app-tests.md
      0011-slo-queries-and-metric-shape-gate-at-m1.md
      0012-l0-plane-layout-runner-envoy-readiness.md
      0013-launchpad-canary-verify-rollback-at-l0.md
      0014-prove-the-go-branch-with-demo-hold.md

  verify/                   # SLO verification; shape-checked at M1, evaluated at M3
    slo.promql               # traffic, error_rate and latency_p95, canary vs stable via target_info join
    metric-shape.sh         # checks them against one live /metrics scrape
    slo.sh                  # verifies canary metrics against stable, the release gate

  app/                      # the target application (docs/adr/0005-0010)
    backend/                 # FastAPI + psycopg, meetups/, migrations/, tests/
    frontend/                # React + Vite + TypeScript, built into the backend image
    fakes/geocoder/          # the external-service dependency, stdlib only
    contracts/geocoder/      # the fake's committed example-pair contract
    flags/                   # flagd file-resolver flag definitions
    load.sh                  # load generator: loops registration POSTs through Envoy
    smoke.sh                 # signup, login, meetup through Envoy

  compose.yaml               # the L0 plane: app + Gitea, runner, Zot, Envoy, Prometheus, flagd, emulators

  adapters/                 # one directory per adapter named in profiles/*.env
    envoy-canary/           # Containerfile, envoy.yaml, ready.sh, deploy.sh, shift.sh, rollback.sh
    prometheus/             # Containerfile, prometheus.yml, ready.sh, query.sh
    gitea/                  # ready.sh, runner/Containerfile, runner/config.yaml
    flagd/                  # ready.sh
    zot/                    # ready.sh
    pubsub-emulator/        # ready.sh
    firestore-emulator/     # ready.sh

  roles/                    # M5: agent role definitions (dev-worker with prompt and budgets)
  policy/                   # from M4: policy-as-code
  tickets/                  # project tickets, one per file; 0001 is the first bug found
  gates/                    # from M4: PR gates, identical at every level
  fixtures/                 # M5: recorded agent responses at L1, replayed at L0
  .crew/                    # M5: per-ticket workspace and output directory (gitignored)
  design/                   # from M10: Stitch artifacts
  infra/                    # from M8: Terraform for GCP
  e2e/                      # from M6: golden path test
```

## Docs

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — the port/adapter pattern, how levels compose
- [docs/adr/](docs/adr/) — architecture decision records
- [PLAN.md](docs/PLAN.md) — the working plan (Italian)
- [app/README.md](app/README.md) — the target application: routes, auth, migrations, metrics, flags

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
