# ADR 0010 — One root `compose.yaml`; `./go test` runs pytest in the app image against the compose Postgres; `demo` gains the app at M1; `ci` unchanged

- Status: accepted (amends ADR 0003 stage `up`)
- Date: 2026-09-14
- Milestone: M1

## Context

M1 acceptance: `./go up` starts the app in compose, `./go test` passes.
Workbench runs `docker-compose 5.5.1` over the podman socket (ADR 0004);
it is a container on the engine's default network, not on the compose
network, so it cannot reach an unpublished Postgres by service name. M2
adds a dozen services to the same `up`. Testcontainers is M4.

## Decision

1. **Layout.** One `compose.yaml` at the repo root, `name: lights-out`.
   Services at M1: `postgres` (`docker.io/library/postgres:17-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73`,
   index 2026-08-16, 117 MB, named volume, **no `ports:`**), `migrate` and
   `backend` (build `context: ./app`, `dockerfile: backend/Containerfile`,
   `target: runtime`; ADR 0008), `geocoder` (build
   `fakes/geocoder/Containerfile`, no `ports:`), and `backend-test`
   (`target: test`, `profiles: [test]`, `depends_on: postgres`). No bind
   mounts, no healthchecks, no `privileged`; the only compose features
   beyond the basics are `depends_on` long syntax and `profiles`.
2. **Ports.** Backend listens on 8000 in the container, published as
   `8080:8000`. `http://localhost:8080` is the URL the README prints at M1
   and the one Envoy takes over at M2 (backend `ports:` removed then).
   Geocoder on 8001, Postgres on 5432, both compose-internal.
3. **Env.** The Makefile already includes and exports the profile and
   `.env` (ADR 0001); compose interpolates from the process environment,
   so no `--env-file`. `DATABASE_URL`, `GEOCODER_URL`, `FLAGD_*`,
   `APP_VERSION` are set in `compose.yaml` with fake-but-valid values; the
   Postgres password is `meetups` in the file, which is not a secret
   because the port is not published. The Makefile sets
   `DOCKER_BUILDKIT=0`: compose over the podman socket builds through the
   classic `/build` API, and pinning that avoids compose trying to spawn a
   buildkitd container. Containerfiles stay classic-syntax (ADR 0005).
4. **`./go test`** is `docker-compose --profile test run --rm --build
   backend-test`, which starts Postgres, builds the `test` stage (runtime +
   dev deps + `tests/`, `contracts/`, `fakes/`) and runs `pytest`. Tests
   that need the DB create and migrate `meetups_test` on that Postgres via
   the runner (ADR 0008) and truncate between tests; `./go up` data is
   untouched. Unit and contract tests (ADR 0006) run in the same
   invocation. `test` joins the socket list in `go`.
5. **`demo` at M1** (ADR 0003 stage list): `ci`, then `up`, then a smoke
   check with curl from workbench through the published port
   (`/healthz` 200, `/metrics` contains
   `http_server_request_duration_seconds`), then leaves the app running and
   prints the URL. The stage prints `[demo] up: app only, plane at M2`.
   `test` is not in `demo`; it is the milestone acceptance and M4's gate.
6. **`ci` gets nothing new at M1.** `ci-shell` already covers `go`,
   `ci/*.sh`; M1 adds no `.sh` file (smoke is a Makefile recipe with curl).
   `docker-compose config -q` joins `ci` at M2 as ADR 0002 planned; `uv
   lock --check`, ruff, `npm audit` belong to M4's gates.

## Alternatives rejected

- `app/compose.yaml` included from the root with `include:`: one more file
  and a project-name split to save nothing at M1; M3 reshapes the app
  services (two revisions, images from Zot) anyway.
- `uv run pytest` inside workbench: needs the compose Postgres published on
  a host port and reached via `host.containers.internal`, the exact
  bind-mount-and-gateway territory ADR 0004 postpones to M2; and it
  installs the dependency tree a second time, outside the image we ship.
- Publish Postgres on `127.0.0.1:5432`: solves the above, but host-IP
  binding is another feature to prove, and an unpublished DB is the simplest
  true statement the README can make about attack surface.
- Bind-mount `app/` into `backend-test` for a faster edit loop: `:z` on a
  virtiofs mount is unproven until M2; `run --build` with layer cache costs
  ~10 s.
- A `test` stage-less image with pytest inside runtime: ships test deps to
  Cloud Run.

## Consequences

- Even a pure unit test needs the engine socket and a Postgres start
  (~5 s). M4's CI runs the same command, so nothing is faster locally than
  in CI; that is the desired property.
- `demo` now needs the socket at M1, which `go` already grants it. A green
  `demo` on a clean machine now proves images pull and build: the first
  real measurement of the 5-minute plane budget happens at M1 close, and the
  number goes in HANDOFF.
- Pull + build estimate for `./go up`: python 46 MB, postgres 117 MB, node
  81 MB, ~30 MB of wheels, ~100 MB of npm, about 375 MB and ~3.5 min at
  20 Mbit/s. That leaves M2 ~1.5 min for Gitea, Envoy, Prometheus, flagd,
  Zot and two emulators, which will not fit: publishing the app image is
  the planned fix (ADR 0009), and M2 must re-budget.
- `DOCKER_BUILDKIT=0` is a global switch for every compose build in the
  repo; if a future Containerfile needs BuildKit, this ADR is revisited,
  not overridden per service.
- `profiles: [test]` means `./go down` does not remove a leftover
  `backend-test` container unless `--profile test` is passed; `down`
  passes it.

## Golden-rule check

`./go up` from a clean clone: socket, three pulls, two builds, no key, no
account. ~3.5 min on a slow line, inside the 5-minute plane budget at M1,
with the budget breach at M2 named above. Passes, with that caveat.
