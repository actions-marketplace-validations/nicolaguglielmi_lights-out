# lights-out

Six agents ship it. One human turns the lights back on.

Six agent roles take a ticket to production on a Google stack. At every step, a gate answers GO or NO-GO. The last gate is human: the flight readiness poll before the canary goes to 100%.

## Status

Milestone M2 of 10. What runs today:

| Stage | Milestone | Real |
|---|---|---|
| ci | M0 | ✓ |
| engine-compat | M2 | ✓ host-side, selected engine |
| up | M2 | ✓ L0 plane, 8 services beside the app |
| smoke | M2 | ✓ a meetup created through Envoy |
| verify | M1 | ✓ metric shape only, evaluation at M3 |
| deploy | M3 | NOT YET |
| rollback | M3 | NOT YET |
| e2e | M6 | NOT YET |

| | |
|---|---|
| **Frontend** | No tests until M10. TypeScript type-check in the image build is the only frontend check at M1. |

Until M3, a green `./go demo` means the repo is coherent and the L0 plane answers; canary and rollback are not real yet.

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
./go up             # start the L0 plane and wait for it
./go smoke          # create a meetup through Envoy
./go engine-compat  # host-side engine gate: versions, then up and smoke
./go down           # stop the plane
./go test           # run backend tests
./go verify         # check the metric shape
./go help           # list all targets
./go shell          # interactive shell inside workbench
./go clean          # remove the workbench image
```

The first run builds the workbench image (about 1 GB on disk, 350–400 MB download, 3–6 minutes depending on connection speed). The plane pulls about 840 MB (amd64) / 720 MB (arm64) of images on the first run, the emulators image being more than half (measured 2026-09-14, ADR 0012). The image includes gcloud and terraform, although nothing uses them before M8.

## Levels

| | L0 · Replay | L1 · Local | L2 · Cloud | L3 · Platform |
|---|---|---|---|---|
| **Needs** | podman rootless (podman machine on macOS) | + Gemini API key | + GCP project with billing | + Agent Engine quota |
| **Models** | Recorded responses (fixtures) | Gemini API, `gemini-3.8-flash` | Gemini Enterprise Agent Platform, `gemini-3.8-flash` | idem + thinking level per role |
| **Harness worker** | Replay | Gemini CLI headless in container | Gemini CLI on Cloud Run Job | + adapter Antigravity SDK |
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

## The L0 plane

Eight services run beside the app in `compose.yaml`. `./go up` returns only after each adapter's `adapters/<name>/ready.sh` answered.

| Service | Host port | What |
|---|---|---|
| Envoy | 8080 | The app's only entrance; `stable` 100% → backend, `canary` 0% with no upstream until M3 |
| Gitea | 3000 | Rootless, sqlite, no users yet; the Actions runner registers on start in host mode |
| Prometheus | 9090 | Scrapes the backend every 5 s |
| Zot | 5050 | OCI registry, empty until M3; 5000 is macOS AirPlay |
| flagd | 8016 | OFREP; serves `app/flags/flags.json`, the one bind mount; edit the file and the flag flips within seconds |
| Pub/Sub emulator | 8085 | Unused until M6 |
| Firestore emulator | 8086 | Unused until M6 |

`./go smoke` signs up, logs in and creates a meetup through Envoy.

**L0 assumes a trusted network**: every port is unauthenticated on every interface, the runner registration token in compose.yaml is public by design, and anyone on the LAN can register a runner or push to Zot.

At M2 the canary cluster has no members and Envoy sends 100% to stable: nothing is faked. The runner is registered but nothing is pushed to Gitea and no workflow runs until M5.

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

This is the same socket path for the Gitea runner and Testcontainers.

Rootless podman usage:

- All published ports must be above 1024.
- Bind mounts get no `:z` (relabelling fails on podman machine's virtiofs, podman #26465/#21269); the one bind-mounted service (flagd) uses `security_opt: label=disable`.
- Use `host.containers.internal` instead of `host.docker.internal`.
- Prefer compose network aliases over any `host.*.internal` name.
- Testcontainers rootless needs `TESTCONTAINERS_RYUK_DISABLED=true` (verify at M4).

Only the docker-compose features proven by `./go engine-compat` are allowed; proven at M2 on podman: `build` with `args`, `depends_on` long syntax, `profiles`, `ports`, `user`, `restart`, `security_opt`, a read-only bind mount.

## Repository

```
lights-out/
  LICENSE                   # Apache 2.0 license
  NOTICE                    # copyright
  README.md                 # this file
  Makefile                  # targets: help, ci, ci-*, demo, up, smoke, down, test, verify, demo-rollback, e2e
  go                        # host entrypoint, POSIX sh
  .env.example              # template for secrets (gitignored)
  .gitignore

  workbench/
    Containerfile           # the toolchain: make, gcloud, terraform, tools
    fetch.sh                # script for verifying downloads

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

  verify/                   # SLO verification; shape-checked at M1, evaluated at M3
    slo.promql               # error_rate and latency_p95, the production queries
    metric-shape.sh           # checks them against one live /metrics scrape

  app/                      # the target application (docs/adr/0005-0010)
    backend/                 # FastAPI + psycopg, meetups/, migrations/, tests/
    frontend/                # React + Vite + TypeScript, built into the backend image
    fakes/geocoder/          # the external-service dependency, stdlib only
    contracts/geocoder/      # the fake's committed example-pair contract
    flags/                   # flagd file-resolver flag definitions
    smoke.sh                 # signup, login, meetup through Envoy

  compose.yaml               # the L0 plane: app + Gitea, runner, Zot, Envoy, Prometheus, flagd, emulators

  adapters/                 # one directory per adapter named in profiles/*.env
    envoy-canary/           # Containerfile, envoy.yaml, ready.sh
    prometheus/             # Containerfile, prometheus.yml, ready.sh
    gitea/                  # ready.sh, runner/Containerfile, runner/config.yaml
    flagd/                  # ready.sh
    zot/                    # ready.sh
    pubsub-emulator/        # ready.sh
    firestore-emulator/     # ready.sh

  core/                     # from M3: vendor-free core
  roles/                    # from M5: agent role definitions
  policy/                   # from M4: policy-as-code
  tickets/                  # project tickets, one per file; 0001 is the first bug found
  gates/                    # from M4: PR gates, identical at every level
  design/                   # from M10: Stitch artifacts
  infra/                    # from M8: Terraform for GCP
  fixtures/                 # from M5: recorded agent responses
  e2e/                      # from M6: golden path test
```

## Docs

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — the port/adapter pattern, how levels compose
- [docs/adr/](docs/adr/) — architecture decision records
- [PLAN.md](docs/PLAN.md) — the working plan (Italian)
- [app/README.md](app/README.md) — the target application: routes, auth, migrations, metrics, flags

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
