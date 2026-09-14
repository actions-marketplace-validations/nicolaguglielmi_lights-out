# ADR 0012 — L0 plane at M2: vendor config lives in `adapters/<name>/` and is copied into images; the runner is host mode on the workbench image; Envoy is 100/0; `./go up` waits on per-adapter readiness; engine-compat runs from `./go`, not `make ci`

- Status: accepted (amends ADR 0004 §2, §4, §5; reorders the ADR 0003 stage list; ADR 0011 hostname note)
- Date: 2026-09-14
- Milestone: M2

## Context

M2 (plan §7) adds Gitea + runner, Zot, Envoy with two weighted clusters,
Prometheus, flagd, and the Pub/Sub and Firestore emulators to the one root
`compose.yaml` (ADR 0010). Done when `./go up` raises everything, Gitea
opens on localhost, the app answers behind Envoy, Prometheus scrapes it.
ADR 0004 §2 promised a docker-mode runner and §4 promised engine-compat
"wired into `make ci`"; both collide with the fact that `make ci` runs in
workbench without an engine. Images, digests and sizes below were verified
by registry and API queries on 2026-09-14. The M1 cold `./go demo` is 66 s
(HANDOFF); per HANDOFF decision A no numeric budget applies before M3, M2
records its measurement. No git remote exists: no workflow has ever run.

## Decision

1. **Config home is `adapters/<adapter-name>/`, names from `profiles/*.env`.**
   `adapters/envoy-canary/` (Containerfile, `envoy.yaml`),
   `adapters/prometheus/` (Containerfile, `prometheus.yml`),
   `adapters/gitea/runner/` (Containerfile, `config.yaml`). Gitea itself is
   configured only through `GITEA__section__KEY` env in compose (sqlite3, the
   rootless image default; `INSTALL_LOCK=true`, `actions.ENABLED=true`). Zot
   ships a usable `/etc/zot/config.json`; flagd takes `--uri` on the command
   line; the emulators take `--host-port`. A directory exists only when it
   holds a file, so at M2 every selected adapter directory holds at least
   `ready.sh` (point 6). **Plan §6 contradiction reported:** §6 lists
   `delivery/ # envoy/ e clouddeploy/`, which duplicates `adapters/envoy-canary`
   and `adapters/cloud-deploy` from §4. §4 and the profile comment win
   ("vendor-specific concepts stay inside their adapter"); `delivery/` is
   not created and the README tree line for it goes.
2. **Static config is `COPY`ed over the pinned upstream digest; one bind
   mount, `app/flags/` into flagd.** `adapters/envoy-canary/Containerfile`:
   `FROM docker.io/envoyproxy/envoy:v1.39.1@sha256:57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4`
   (73/70 MB), `COPY envoy.yaml`, `RUN envoy --mode validate -c ...` so a
   bad config fails the build, not the demo. Prometheus:
   `quay.io/prometheus/prometheus:v3.14.0@sha256:5ce7540c3c00ef4ab0c9d2c995c6a5b9c421f44b4a115d97a2c7af3b1c21cbb0`
   (109/100 MB), `COPY prometheus.yml`, `RUN promtool check config`. Runner:
   point 3. This is the M1 `flags.json` pattern; it has no mount semantics
   to prove and it is the shape L2 needs anyway (no bind mounts on Cloud
   Run). flagd (`ghcr.io/open-feature/flagd:v0.16.3@sha256:a11ae82ec6e40e89edae4327392a1e4ffc03e211f1b724879bb35b2e4f271bb3`,
   48/44 MB, `flagd start --uri file:/flags/flags.json`) gets
   `./app/flags:/flags:ro` plus `security_opt: [label=disable]`. `:ro` is
   enough for access; **`:z` is rejected**: podman #26465/#21269 show the
   relabel failing on podman machine's virtiofs because macOS refuses
   `setfattr`, and M1 proved an unlabelled virtiofs mount is readable there.
   `label=disable` is what `./go` already uses for the socket, is valid on
   both engines, is a no-op without SELinux, and keeps Fedora/RHEL rootless
   hosts working. The backend switches to `FLAGD_RESOLVER=in-process
   FLAGD_HOST=flagd FLAGD_SYNC_PORT=8015` (ADR 0007 §3). The mount exists
   now, not at M3, so the readiness check proves it on the selected engine
   today; flagd's default `file` sync outside Kubernetes is the `fileinfo`
   poller (flagd.dev/reference/sync-configuration), so M3's kill switch can
   edit the file from workbench and needs no inotify and no restart.
3. **Runner: host mode, image built `FROM` the workbench image.**
   `adapters/gitea/runner/Containerfile`: `ARG WORKBENCH_IMAGE`,
   `FROM ${WORKBENCH_IMAGE}`, `COPY --from=docker.gitea.com/runner:3.4.2@sha256:50c352f0506b1878be93f2e9e97353cd6261cd2e7f7bfe70fcd968d00874f9f9`
   the runner binary (18 MB image; classic multi-stage), `RUN gitea-runner
   --version` so a non-static binary fails the build. `config.yaml`:
   `runner.labels: ["ubuntu-latest:host"]`, `host.workdir_parent: /data/work`.
   Env: `GITEA_INSTANCE_URL=http://gitea:3000`,
   `GITEA_RUNNER_REGISTRATION_TOKEN` (point 9), `restart: on-failure`
   because the upstream entrypoint gives up after 10 × 5 s (run.sh) and a
   slow laptop can take longer to boot Gitea. `./go` exports
   `WORKBENCH_IMAGE=$image` into every workbench run; compose interpolates
   it with `:?set by ./go` so raw `make` fails loudly. The job runs inside
   the runner container, which is the workbench plus one binary, with
   `LIGHTS_OUT_WORKBENCH=1`: `./go ci` execs `make ci`; `actions/checkout`
   finds node 24. No engine socket reaches the runner. **Amends ADR 0004
   §2.** At M2 nothing is pushed to Gitea and no workflow runs (M5's
   CodeHost adapter); M2 proves registration only, and the README says so.
4. **Envoy at M2: one listener on 8080, one route, `weighted_clusters`
   `stable=100` → STRICT_DNS `backend:8000`, `canary=0` → STATIC cluster
   with an empty `load_assignment`.** Nothing is faked and an empty static
   cluster does no DNS. The backend's `ports:` goes (ADR 0010 §2);
   `APP_URL` now hits Envoy, so `verify/metric-shape.sh` runs through it
   unchanged. No admin listener, nothing else published. Note for M3, not
   built now: `runtime_key_prefix` on the weighted clusters plus an admin
   runtime layer changes weights through the admin API without restart;
   file-based xDS is a trap because Envoy's file watcher is inotify and
   virtiofs does not deliver it.
5. **engine-compat runs from `./go`, never from `make ci`.** `./go
   engine-compat` runs `ci/engine-compat.sh` on the host with
   `CONTAINER_ENGINE` set to the engine `./go` selected. The script: prints
   every engine version found (stderr), marks docker a shim when
   `docker --version` does not start with `Docker version` (NO-GO if that
   shim is the selected engine), then `./go up` and `./go smoke` (point 6)
   on the selected engine only; leaves the plane running. GO when the
   selected engine ran green. Inside workbench (`LIGHTS_OUT_WORKBENCH=1`) it
   NO-GOs immediately, "host-side gate, run ./go engine-compat", which is
   what `ci/contract.sh` sees. `./go demo` = `engine-compat` on the host,
   then `make demo` whose stage list becomes `engine-compat` (line: done on
   the host), `ci`, `up` (idempotent here), `smoke`, `verify`, `deploy`
   NOT YET (M3), `rollback` NOT YET (M3), `e2e` NOT YET (M6); the inline
   `/healthz` curl of ADR 0010 §5 is subsumed by `smoke`. The Makefile
   `ci-engine-compat` help line goes; `engine-compat` joins `shell` and
   `clean` in the "host side, via ./go only" help block so `ci-readme` stays
   true. Workflow: one added job `engine-compat`, `runs-on: ubuntu-latest`,
   job-level `if: github.server_url == 'https://github.com'` (job-level
   `if` cannot read `env`; Gitea fills `github.server_url` with its own
   URL), `CONTAINER_ENGINE=docker`, `run: ./go engine-compat`. No podman leg
   on GitHub at M2 (needs a socket-enabling step nobody can run until a
   remote exists; the laptop covers podman). The job is lint-checked by
   actionlint and `gitea-compat`; its first execution is the day a remote
   exists and the README does not claim it green before then. `make ci`
   gains `compose` (`ci/compose.sh`: `docker-compose config -q`, offline),
   the M2 item ADR 0002 and ADR 0010 §6 planned. **Amends ADR 0004 §4.**
6. **Readiness is per adapter, `adapters/<name>/ready.sh`; the smoke is
   the app's, `app/smoke.sh`; neither is a gate.** `make up` =
   `docker-compose up -d --build` then, for each of `CODE_HOST DELIVERY
   METRICS FLAGS REGISTRY EVENT_BUS STATE_STORE` from the profile,
   `sh adapters/$X/ready.sh`; a missing file is an error, so L2 adapters
   must ship one at M8. Each script polls its own endpoint every 1 s from
   workbench via `PLANE_HOST` (Makefile, default `host.containers.internal`;
   `APP_URL` now derives from it, the ADR 0011 "one place" moves here),
   exits 0 silently or exits 1 after `READY_TIMEOUT` (default 120 s,
   provenance: decision, twice M1's 60 s backend wait because two new
   services are JVMs; the measured startup goes in HANDOFF at M2 close and
   replaces this default). Checks: gitea `GET /api/v1/version` 200 and
   `docker-compose exec -T runner test -f /data/.runner` (the file the
   entrypoint writes only after registration succeeds); envoy-canary
   `GET $APP_URL/healthz` 200 (listener, route, stable cluster and backend
   in one request; no Envoy-specific health endpoint); prometheus
   `/api/v1/query?query=up{job="backend"}` value `1`; flagd OFREP
   `POST :8016/ofrep/v1/evaluate/flags/waitlist` → `value:false` (proves
   the bind mount was read); zot `GET /v2/` 200; pubsub-emulator and
   firestore-emulator `GET /` → `Ok`. Readiness is side-effect free.
   `app/smoke.sh` (Makefile target `smoke`) signs up, logs in, creates a
   meetup through Envoy and asserts 201 with non-null `venue_lat`, which is
   the geocoder-in-compose proof ADR 0006 asked of M2. These scripts are
   not gates: no GO/NO-GO line, because the contract is for verdicts and
   `ci/contract.sh` would otherwise run seven pollers to their timeout on
   every `ci`. `ci/shell.sh` adds `adapters/*/ready.sh` and `app/smoke.sh`.
   No named volume for any plane service: Gitea, runner, Zot, Prometheus
   and emulator state is per `up`, so a runner token can never outlive the
   Gitea that issued it; `postgres-data` (ADR 0010) stays.
7. **Published host ports, all > 1024, all on every interface:** 8080 Envoy,
   3000 Gitea, 9090 Prometheus, 5050 Zot (5000 is macOS AirPlay Receiver),
   8016 flagd OFREP, 8085 Pub/Sub, 8086 Firestore. Nothing dropped: each
   is either human-facing (3000, 9090, 8080) or the only way workbench and
   the M3/M6 runners reach the service (5050, 8016, 8085, 8086). Not
   published: Gitea SSH (HTTP push, M5), Envoy admin, Postgres, flagd
   8013/8014/8015, geocoder. Not bound to 127.0.0.1: ADR 0010 called
   host-IP binding unproven and workbench reaches the plane through
   `host.containers.internal`, which on podman machine may not see a
   loopback-only listener.
8. **Prometheus `scrape_interval: 5s`.** Provenance: decision. Reason:
   `verify/slo.promql` (ADR 0011) uses `rate()`, which needs at least two
   samples per window, and M3's verify window must fit inside the 900 s
   demo (plan §2); at the Prometheus default of 15 s (Prometheus docs) a
   30 s window holds two samples, at 5 s six. One target, one job
   `backend` → `backend:8000/metrics`. No rules, no retention change.
9. **Fixed runner token in `compose.yaml`, ≥ 32 chars (Gitea
   `services/actions/init.go`), chosen with low entropy so `ci-secrets`
   (gitleaks, no allowlist per ADR 0002) cannot flag it:
   `lights-out-local-runner-token-not-a-secret-0000`; the fix for a
   false positive is a duller string, never an allowlist.** Acceptable at
   L0 because the Gitea it belongs to has no users and is itself
   unauthenticated on the same published port; the token protects nothing
   that is not already open. Named risk: anyone on the LAN can register a
   runner with it and receive dispatched jobs (the repo's public source)
   and post results back. Same class as the unauthenticated Zot on 5050,
   where a LAN neighbour can overwrite a tag M3 deploys. The README says:
   L0 assumes a trusted network.

## Alternatives rejected

- Top-level `plane/` (or `delivery/` + `plane/`): an L0-only concept as a
  top-level directory, and Envoy config split from the Envoy adapter M3
  writes; L2's plane is `infra/`.
- Bind mounts for every config: `:z` fails on podman machine (issues cited);
  unlabelled mounts break SELinux Linux hosts; nothing to validate at build.
- Zero bind mounts, flagd rebuilt on every flag flip: uniform, but M3's
  "seconds, no deploy" story becomes a container restart, and the mount
  semantics later milestones need (M4, M5) stay unproven one more time.
- Docker-mode runner (ADR 0004 §2): the engine socket in a long-running
  compose service, `label=disable`, the socket path and workbench image name
  interpolated from `./go`, and the runner pulling a `localhost/` image;
  four moving parts to get the same job in the same image.
- A canary cluster pointed at the stable backend with weight 0: a fake
  second upstream, exactly the hidden mock the rule forbids.
- Envoy admin listener now: a port nobody uses until M3.
- engine-compat as a `CI_CHECKS` entry: it cannot see an engine from inside
  workbench, so it would NO-GO in every `ci`, including the one in `demo`.
- engine-compat over every engine found: two VMs on one laptop, double the
  time, and docker on a podman laptop is usually a shim anyway.
- Podman leg in the GitHub matrix at M2: a job that cannot be run before a
  remote exists and is expected to need a socket step nobody has tested; a
  red job that teaches people to ignore red (ADR 0003).
- Compose `healthcheck` + `up --wait`: half the images (Zot, flagd, Envoy)
  have no shell or curl for an in-container check, and rootless podman
  schedules healthchecks through systemd, which is absent on some hosts.
- One monolithic readiness script: an `if $LEVEL` ladder at M8, the L0/L2
  divergence plan §11 names.
- Readiness under the GO/NO-GO contract: they are waits, not verdicts, and
  `contract.sh` would run them cold.
- Ports bound to `127.0.0.1`: unproven reachability from workbench on podman
  machine; a hardening item for whichever milestone first runs the demo on
  a conference network.
- Building the emulators onto the workbench image (JRE + gcloud components,
  reusing the 1 GB already local): plausibly saves ~300 MB of pull, but no
  budget applies before M3 and it is a second image to pin. Named as the
  lever, not pulled.
- Named volumes for Gitea and the runner: a runner volume without a Gitea
  volume (or vice versa) yields a registration Gitea does not know, fixed
  only by `down -v`; both or neither, and neither is fewer lines.

## Consequences

- Host mode gives jobs no engine. `./go test` and M4's gates need one, and
  the day CI runs them the socket goes into the runner container, which is
  the job's container: that is M4's security decision, not deferred by
  accident. Docker mode would have faced the same choice.
- Jobs run as root (host user under rootless podman) in the runner's own
  filesystem, consecutively, with no isolation between them. A demo runner;
  the README says so. Runner state per `up` means a rebuilt runner
  container re-registers and leaves a stale runner record in Gitea.
- The runner image rebuilds whenever the workbench Containerfile changes,
  `FROM` by cksum tag; `./go up` sees the change and rebuilds. Running
  `make` outside `./go` now fails at `docker-compose config`, by design.
- `actions/checkout` at M5 needs Gitea's actions mirror reachable from the
  runner.
- Every published port is unauthenticated on every interface. On a
  conference Wi-Fi that is an exposure; the README carries one line.
- engine-compat leaves the plane running and `demo` repeats `up`; the second
  `up` is a no-op plus seven fast polls. `demo` now starts the plane before
  `ci`, reordering ADR 0003's list.
- `READY_TIMEOUT` 120 s was a placeholder until M2 close measured startup.
  **Measured 2026-09-14 (HANDOFF M2):** on a cold plane the seven pollers
  took 15 s in total (gitea 5 s including runner registration, envoy 4 s,
  prometheus 5 s to its first scrape, the rest already up). The default is
  now 60 s, four times the measurement and equal to M1's backend wait.
- 5 s scrapes make the TSDB grow 3× faster than default; one target, no
  volume, irrelevant until someone leaves the plane up for weeks.
- flagd runs with `label=disable`; it reads one JSON file and serves gRPC.
- The GitHub job is unexecuted code until a remote exists.
- ADR 0011's "one place for the hostname" is now `PLANE_HOST`; `APP_URL`
  derives from it.

## Golden-rule check

Stranger with podman, git, sh; no key, no account. Plane pulls verified
today: Gitea 68/65 MB, runner 18 MB, Zot 75/68 MB, Envoy 73/70 MB,
Prometheus 109/100 MB, flagd 48/44 MB, emulators 447/356 MB (one image,
both services) — about 838 MB amd64 / 721 MB arm64, the emulators more than
half. At ADR 0004's 20 Mbit/s line that is ~5.6 / ~4.8 min; at 100 Mbit/s
~67 / ~58 s. On top: the 66 s M1 baseline (HANDOFF), three small image
builds (seconds; the runner build reuses local workbench layers), and
readiness (unmeasured, ≤ 120 s by the placeholder). Per HANDOFF decision A
no ceiling binds before M3; the 900 s figure (plan §2, CLAUDE.md) is
measured on `demo-rollback` at M3, and the two levers if it fails are
already named: publish workbench by digest (ADR 0004 §3) and an emulator
image derived from workbench. M2 records its cold `./go demo` time in
HANDOFF next to the 66 s. Passes, with the emulator image as the number to
watch.
