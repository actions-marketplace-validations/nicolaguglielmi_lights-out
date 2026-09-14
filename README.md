# lights-out

Six agents ship it. One human turns the lights back on.

Six agent roles take a ticket to production on a Google stack. At every step, a gate answers GO or NO-GO. The last gate is human: the flight readiness poll before the canary goes to 100%.

## Status

Milestone M0 of 10. What runs today:

| Stage | Milestone | Real |
|---|---|---|
| ci | M0 | ✓ |
| engine-compat | M2 | NOT YET |
| up | M2 | NOT YET |
| deploy | M3 | NOT YET |
| verify | M3 | NOT YET |
| rollback | M3 | NOT YET |
| e2e | M6 | NOT YET |

Until M3, a green `./go demo` means the repo is coherent, not that the platform works.

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
./go help           # list the targets
./go ci             # run repo self-checks
./go shell          # interactive shell inside workbench
./go clean          # remove the workbench image
```

The first run builds the workbench image (about 1 GB on disk, 350–400 MB download, 3–6 minutes depending on connection speed). The image includes gcloud and terraform, although nothing uses them before M8.

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

## How it runs

`./go <target>` builds `workbench/Containerfile` and runs `make <target>` inside it with the repo mounted at the same absolute path as on the host. The workbench image carries make, git, gcloud, terraform, and all verification tools, so the host needs only a container engine and a shell.

Profiles: `./go demo PROFILE=l2` selects `profiles/l2.env`. Secrets go in `.env` (gitignored, template `.env.example`). L0 needs no `.env`.

### Engine socket

Targets `up`, `down`, `demo`, `demo-rollback`, `e2e`, and `shell` mount the engine's API socket into workbench, which gives the container full control of the engine. It can start privileged containers, read any volume, and delete images.

The `ci` target never gets the socket.

### Rootless notes

The engine socket is `unix:///run/user/$(id -u)/podman/podman.sock`. Enable it with:

```sh
systemctl --user enable --now podman.socket
```

(On macOS, `podman machine` enables it automatically.)

This is the same socket path for the Gitea runner and Testcontainers.

Rootless podman usage:

- All published ports must be above 1024.
- Bind-mount volumes get `:z` when SELinux is present (check `/sys/fs/selinux`). `./go` adds it automatically.
- Use `host.containers.internal` instead of `host.docker.internal`.
- Prefer compose network aliases over any `host.*.internal` name.
- Testcontainers rootless needs `TESTCONTAINERS_RYUK_DISABLED=true` (verify at M4).

Only the docker-compose features proven by `ci-engine-compat` on both podman and docker are allowed.

## Repository

```
lights-out/
  LICENSE                   # Apache 2.0 license
  NOTICE                    # copyright
  README.md                 # this file
  Makefile                  # targets: help, ci, ci-*, demo, up, down, demo-rollback, e2e
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
    engine-compat.sh        # host side, podman and docker separately (joins ci at M2)

  docs/
    ARCHITECTURE.md         # ports and adapters
    PLAN.md                 # working plan (Italian)
    adr/                    # architecture decision records
      0001-profiles-and-single-makefile.md
      0002-self-ci-is-make-ci.md
      0003-make-demo-before-m3.md
      0004-containerised-toolchain.md

  core/                     # from M3: vendor-free core
  adapters/                 # from M3: one directory per adapter
  roles/                    # from M5: agent role definitions
  policy/                   # from M4: policy-as-code
  gates/                    # from M4: PR gates, identical at every level
  verify/                   # from M3: SLO verification
  delivery/                 # from M3: deployment orchestration
  design/                   # from M10: Stitch artifacts
  app/                      # from M1: the target application
  infra/                    # from M8: Terraform for GCP
  fixtures/                 # from M5: recorded agent responses
  e2e/                      # from M6: golden path test
```

## Docs

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — the port/adapter pattern, how levels compose
- [docs/adr/](docs/adr/) — architecture decision records
- [PLAN.md](docs/PLAN.md) — the working plan (Italian)

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
