# Handoff: M2 closed on 2026-09-14

## Acceptance

Cold run: plane images, app images and app base images (postgres, python, node) removed first; workbench image already built (same convention as M1); rootless podman 5.7.1 on macOS (podman machine, arm64):

```
$ ./go demo
GO: engine-compat
[demo] ci (M2): running
GO: secrets
GO: lint
GO: shell
GO: help
GO: readme
GO: gitea-compat
GO: profiles
GO: compose
GO: contract
GO: ci
GO: metric-shape
GO: demo, milestone M2. Green means the repo is coherent and the L0 plane answers; canary and rollback are not real yet.
./go demo: 258 s total, cold (M1 baseline was 66 s with only the app)
```

Stderr timeline of that run (seconds from start): flagd pulled 28, gitea 40, zot 42, emulators image 102, postgres 125; runner image built 137, app images built 170, envoy 191, prometheus 194; readiness: gitea 212→217 (API up and runner registered), envoy 217→221, prometheus 221→226, flagd/zot/pubsub/firestore instant, plane up at 227; smoke at 228 (meetup created through Envoy, venue_lat=45.4641); the second `up` inside `make demo` (cache check of six builds) 228→251; verify 258. Readiness total: 15 s. `READY_TIMEOUT` default set to 60 s from that (4× measured, = M1's backend wait).

Warm `./go demo`: 24 s.

Acceptance checks run by hand after `./go up`, all from the host:
```
$ ./go smoke
smoke: meetup 1 created through Envoy at http://host.containers.internal:8080 (venue_lat=45.4641)
$ curl -fsS localhost:3000/api/v1/version
{"version":"1.27.3"}
$ curl -fsS -G localhost:9090/api/v1/query --data-urlencode 'query=up{job="backend"}'
{"status":"success","data":{"resultType":"vector","result":[{"metric":{"__name__":"up","instance":"backend:8000","job":"backend"},"value":[1789403687.202,"1"]}]}}
$ curl -fsS localhost:8080/healthz
{"status":"ok","version":"0.1.0-m2"}
$ curl -fsS -X POST -H 'Content-Type: application/json' -d '{"context":{}}' localhost:8016/ofrep/v1/evaluate/flags/waitlist
{"value":false,"key":"waitlist","reason":"STATIC","variant":"off","metadata":{}}
$ curl -fsS localhost:5050/v2/ -o /dev/null -w 'zot %{http_code}\n'
zot 200
$ curl -fsS localhost:8085/; curl -fsS localhost:8086/
Ok
Ok
$ podman logs lights-out-runner-1 | grep -i registered
level=info msg="Runner registered successfully."
level=info msg="runner: lights-out-l0, with version: v3.4.2, with labels: [ubuntu-latest], declare successfully"
```
`./go test`: 25 passed. `./go verify`: GO: metric-shape (through Envoy). `./go ci`: all ten gates GO (new: compose).

## What changed

- compose.yaml: eight plane services beside the app (Envoy takes :8080, backend no longer published; flagd in-process sync; one bind mount app/flags → flagd).
- adapters/<name>/: Envoy, Prometheus and runner Containerfiles + configs (validated at build), seven ready.sh pollers; app/smoke.sh creates a meetup through Envoy.
- Makefile/go: `up` waits per adapter, new `smoke`, `./go engine-compat` host-side gate is the first stage of `./go demo`, WORKBENCH_IMAGE exported; ci gains `compose`.
- ADR 0012 (layout, COPY-into-image, host-mode runner, Envoy 100/0, readiness, ports, 5 s scrape, fixed token); ADR 0003/0004 amended.
- README/ARCHITECTURE: L0 plane table, ports, trusted-network line, rootless notes (no :z), tree.

## Found while building, contradicting or missing from docs/PLAN.md

1. Plan §6 puts Envoy under `delivery/envoy/` while §4 and profiles/l0.env name adapters as directories under `adapters/`. ADR 0012 §1 follows §4: everything under `adapters/<name>/`, `delivery/` not created. §6 should be corrected.
2. ADR 0004 §2 (docker-mode runner with `docker_host: "-"`) and §4 (engine-compat "wired into make ci") were both unimplementable as written: `make ci` runs in workbench without an engine. Amended by ADR 0012 §3/§5 (host-mode runner built FROM the workbench image; engine-compat runs from ./go).
3. The Gitea runner image was renamed: `docker.gitea.com/runner` (binary `gitea-runner`), `act_runner` tags are mirrors of the same index. Plan and README wording "act runner" now means this image.
4. `:z` on bind mounts (ADR 0004 §5 seed list, README rootless notes) does not work on podman machine's virtiofs (podman #26465/#21269); replaced by `security_opt: label=disable` on the one bind-mounted service.
5. The Envoy image's entrypoint chowns /dev/stdout as root and dies under rootless podman; the service runs with `user: envoy` (compose.yaml comment).
6. The emulators image (`google-cloud-cli:584.0.0-emulators`, 447 MB amd64 / 356 MB arm64) is more than half of the plane's pulls and took 60 s of the 258 s cold run on this connection. It is the lever if M3's 900 s ceiling is threatened (ADR 0012 golden-rule check).
7. App: a venue not in the geocoder contract makes the fake return 404 and the backend answer 500 (not the 502 ADR 0006 documents for 5xx/timeouts). Not fixed at M2; the smoke uses `Milano, Duomo`. Filed as **`tickets/0001.md`** (Given/When/Then, labelled M4 for the contract test): the candidate first real task for a worker at M5, small and self-contained.
8. `make demo` runs `up` twice (once inside engine-compat on the host, once inside workbench): the second costs ~25 s of build-cache checks. Accepted by ADR 0012; if M3's timing gate is tight, `demo` can skip the second `up`.
9. Plan §6 corrected (dated note in PLAN.md): `delivery/` removed, `tickets/` added.

## First thing M3 should look at

- Envoy weights: `weighted_clusters` with `runtime_key_prefix` + an admin runtime layer lets the delivery adapter shift 5%/25%/100% via the admin API without restart; file-based xDS is a trap (no inotify on virtiofs). The admin port is not published yet — M3 publishes it or shells through `docker-compose exec`.
- The canary cluster is STATIC with no endpoints; M3 gives it a second backend revision (a second compose service or a compose profile) and Prometheus a second scrape job so `verify/slo.promql` can be evaluated per `job`/`version` (ADR 0011 consequences).
- **The label that tells canary from stable must be the same concept at L0 and on Managed Prometheus, or `slo.promql` diverges between levels — the constraint the whole comparison rests on.** At L0 Prometheus can stamp anything (`job`, a static `version` label per scrape target); on Cloud Run the Managed Prometheus collector stamps its own labels (`revision_name`, resource labels) and does not read compose. Pick a label the app itself emits (`service.version` → `APP_VERSION`, already on the OTel resource as `target_info`, and the value every flag evaluation carries) or one the M3 ADR defines as a relabel rule on both sides; never a label only compose or only Cloud Run can produce. The selector goes into `slo.promql` once, with an ADR, and the M8 hash test then guarantees it never forks.
- flagd file edits are live (fileinfo poller): the kill switch is an edit of `app/flags/flags.json` from workbench.
- The M3 timing gate measures `./go demo` to rollback against 900 s; today's cold baseline is 258 s.
