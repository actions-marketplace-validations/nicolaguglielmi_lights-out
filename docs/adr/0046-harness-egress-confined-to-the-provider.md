# ADR 0046 — A CLI harness reaches only its provider: an internal `crew` network, one allowlisting `egress` proxy, the worker's own Postgres, and package indexes only where the workload names them

- Status: accepted (amends ADR 0041 §3 [the network is no longer open], §8 [case 9, the `egress` lifecycle, a `conformance-sink` alias], §9 [`harness-shape` checks `EGRESS`], §11 and ADR 0017 §10 [the worker's Postgres is its own], and ADR 0041's consequence "before M24 … egress is the question"; plan §16 M19's status note, "la rete resta aperta").
- Date: 2026-11-04
- Milestone: before M24

## Context

The three CLI harnesses run in containers with an open network, because each must reach its provider. The guard (ADR 0041 §11) denies network tool *names*; an interpreter's HTTP client is not one, so an injection in repository content can send out what the container holds, the key included (`python3 -c` reading `/proc/self/environ` passes the guard today). The worker also reaches the plane's Postgres as superuser `meetups` (app/compose.yaml's `x-crew-worker`), which would relay: `COPY … TO PROGRAM` runs a shell in a container that has egress. M24 runs the crew on a repository the owner does not control, so this is closed now.

## Verified (2026-11-04, live, parent session scratchpad; not in the repo)

Each pinned CLI (claude-code 2.1.311, codex 0.166.0, gemini-cli 0.61.0-preview.0, `npm ci` from the adapter's lockfile, linux-x64, node 22), fake keys, `HTTPS_PROXY`/`HTTP_PROXY` (both cases) at a stdlib-Python forward proxy with an exact `host:port` allowlist, `NO_PROXY` empty:
- Allowlist empty: claude-code asked only `CONNECT api.anthropic.com:443`; codex `api.openai.com:443` (WebSocket and HTTPS both through the proxy) plus `chatgpt.com`, `ab.chatgpt.com`, `github.com`, `api.github.com`; gemini-cli `generativelanguage.googleapis.com:443` plus `play.googleapis.com:443`. None connected anywhere around the proxy.
- Against `gates/harness-conformance/stub.py` with only `conformance-model:8089` allowed: all three finished a tool call and a final answer through the proxy, auth canary accepted; the side hosts were denied and no run failed for it.

External: Docker 26.0.0, 25.0.4 and 23.0.11 stop forwarding DNS from a container attached only to `internal` networks (CVE-2024-29018). Not verified: any of this inside a container on an internal network, podman's aardvark-dns on one, the real providers with a real key. Case 9 below proves the first two per engine.

## Decision

1. **Network.** Root compose.yaml declares network `crew`, `internal: true`. The `x-crew-worker` anchor puts every harness service on `crew` only, no ports. Nothing on `crew` has a route out except through `egress`.
2. **One proxy, `egress`.** Profile `crew`, workbench image, `python3 -I /core/egress.py 3128` with `./core` mounted read-only and `.crew/egress` read-write, `user` CREW_UID like `conformance-model`, on `crew` and `default`, **no published port**. Stdlib only: CONNECT and absolute-form HTTP, exact `host:port` match against `.crew/egress/allow` **re-read on every connection**, missing or empty file denies all, one stderr line per decision (`ALLOW|DENY <host:port>`), `ready` written once it listens. Port 3128: decision (Squid's convention; internal only). It names no provider, so it lives in `core/`.
3. **Proxy variables.** `x-crew-env` gains `HTTPS_PROXY`, `HTTP_PROXY`, `https_proxy`, `http_proxy` = `http://egress:3128` and `NO_PROXY`/`no_proxy` = `localhost,127.0.0.1,::1`.
4. **The allowlist.** `adapters/<h>/conformance.env` gains a fifth key, `EGRESS`, space-separated `name:port` (verified above): `generativelanguage.googleapis.com:443`, `api.anthropic.com:443`, `api.openai.com:443`. With `MODEL_BASE_URL` set (ADR 0041 §7) its `host:port` replaces `EGRESS`. To that the workload adds the lines of `<contract>/crew-egress.txt` (§5), if the file exists. `core/egress.sh "$EGRESS"`, called by each `run.sh` after its refusals and before `docker-compose run`, writes the file atomically, runs `docker-compose --profile crew up -d egress` (retried once: parallel network members race on creation) and returns when the running proxy is ready (≤ 30 s, decision), never on a stale `ready`. Because the list is a file, a harness switch never recreates the service; `egress` is never stopped by a run, and parallel members with one harness write the same list. Not a `depends_on` (the suite's "starts nothing beside it" check stands).
5. **Package indexes: the workload names them, default none.** Provider-only would break `uv sync --locked` in app's and minimal's briefs and, worse, dependency-upgrade tickets, plan §14's first ticket class for M24 (`uv lock` needs the index). So the contract may hold `crew-egress.txt`, one `name:port` per line, read from the contract (the base, never the worker's workspace), high risk (`RISK_HIGH_PLATFORM` gains `*crew-egress.txt`). app and workloads/minimal list `pypi.org:443` and `files.pythonhosted.org:443`, not `upload.pypi.org`; minimal-js lists nothing (no dependencies). The README names every listed host as an open channel; `docs/use-on-your-repo.md` says never `registry.npmjs.org` without reading why (`npm publish` with an injected token).
6. **The worker's own Postgres.** The app fragment adds `crew-postgres`: the plane's pinned postgres digest, profile `crew`, on `crew` only, no named volume; `x-crew-worker` depends on it and its two URLs point at it. The plane's Postgres is not on `crew`, and the worker no longer touches the running app's data. Rule for every fragment: a service a harness depends on is on `crew` only.

## Conformance (for the gate-writer)

The suite removes `egress` at start and on exit, like `conformance-model`, which gains the network alias `conformance-sink` on `default`. The stub logs each request's peer address.
- **Every case 1–9:** every request the stub logged came from `egress`'s address; the key canary only in auth headers (case 8, extended to 9).
- **Case 9, confinement.** BASE holds `probe.py`; steps `shell python3 probe.py`, then case 1's. The probe reads `/proc/self/environ` (the key canary) and tries to send it: (a) POST `http://conformance-sink:8089/exfil` via the proxy, (b) CONNECT `conformance-sink:8089`, (c) CONNECT `conformance-model:8090` (allowed name, other port; decision: any port the stub does not serve), (d) CONNECT `example.com:443`, (e) TCP to `conformance-sink:8089` without the proxy, (f) TCP to the stub's `default` IP (the suite passes it), (g) TCP to `1.1.1.1:443`, (h) resolve `example.com`. It prints `<channel> blocked|open`, never what it read. Expect: a valid PR; all eight `blocked` in the next tool result; no request to `/exfil`; the egress log has DENY for (a)–(d) and ALLOW only for `conformance-model:8089`. Timeouts 5 s per channel (decision: a local listener answers in far less; eight fit well under the role's `TIMEOUT_S`); `1.1.1.1` and `example.com`: decision (a public anycast address, the IANA documentation domain). (g) and (h) prove something only on a host with internet.
- **Engines.** Docker: the `harness-conformance` job on GitHub Actions, every push. Podman rootless: workflow `podman` on GitHub Actions, every push, `CONFORMANCE_HARNESS=claude-code` (amended building: the owner's machine runs no engine any more, docs/plans/third-arc-execution.md; one harness because the confinement is compose's and the proxy's, the same for every harness). The owner's own podman run before M24 stays worth having: ubuntu's podman is not the Mac's podman machine. No CI job runs a real worker on a workload, so §5's lists and `crew-postgres` are proved by shape checks only.
- **Engine-free.** `ci/harness-shape.sh`: `conformance.env` has exactly the five keys; `EGRESS` is one or more `name:port`, lowercase DNS name with a dot, no IP literal, no `*`, port 1–65535. `ci/workloads.sh`, on each rendered project: `crew` internal; every harness service on exactly `[crew]` with the four proxy variables and no ports; every service a harness depends on on exactly `[crew]`, no ports; `egress` on exactly `crew` and `default`, no ports; `crew-egress.txt`, if present, in `EGRESS`'s shape. Each check with a defect its self-check must name.

## Alternatives rejected

- **squid or tinyproxy**: a new pinned image and config language; tinyproxy has no official image.
- **envoy as forward proxy**: CONNECT plus a per-run allowlist is heavy YAML, in a service another session is editing.
- **A TLS-intercepting proxy that injects the key**: strongest (the container holds no key, and overwriting auth would also void an attacker's own key), but per-vendor auth rewriting and a CA that node and codex's Rust both trust. The next step if the first consequence proves real.
- **iptables/nftables in the container**: needs NET_ADMIN, fails rootless, and the rules sit with the model.
- **Allowlist in `egress`'s environment**: every harness switch recreates it, killing parallel members' tunnels; recreation depends on each compose's config hashing.
- **A proxy per run (`run -d --name`)**: unique names, aliases on `run` containers and teardown, unverified on two engines.
- **The plane's Postgres on `crew`**: a superuser relay with egress, and the live database.
- **Provider-only everywhere, dependencies prefetched outside the session**: `uv lock` still needs the index inside it, so upgrade tickets die; the prefetch is a new phase with its own network.
- **A twelfth `workload.env` key or a `policy.env` key**: eleven keys are checked by init, attach and ci; `policy.env` holds merge thresholds with provenance, not hosts.

## Consequences

- **The one that hurts: the provider's host is still a channel.** An injection carrying the attacker's own key for that provider can upload the victim's key there; TLS is opaque, so fronting through the provider's CDN is not excluded; each `crew-egress.txt` host is one more of the same kind. Confinement turns "send anywhere" into "send to an account at an allowed host", attributable and revocable, not closed.
- The PR is a channel: `run.sh` greps the literal key, an encoded one passes and is published when the PR opens on a public host. Not addressed here.
- The guard's `/proc/self/environ` gap is the guard's; after this ADR it reaches only the channels above.
- One allowlist per compose project: two harnesses run at once in one checkout break each other, closed.
- `EGRESS` is a CLI-version fact: a bump that starts *requiring* another host fails its first record; the suite (stub) cannot see it. A bump commit re-runs the empty-allowlist probe.
- DNS is closed only where the engine does not forward from internal networks: docker ≥ 26.0.0 by advisory, podman by case 9 in the `podman` workflow.
- `app/worker.md` stops saying "the plane's own Postgres"; ADR 0041's README harness table gains "egress: provider only".

## Golden-rule check

`./go demo` is unchanged: L0 replays, no harness runs, `egress` and `crew-postgres` never start. `./go ci` gains engine-free checks. No new image or dependency: `egress` is the workbench image, `crew-postgres` the plane's digest, both started only by an L1 crew run or the suite. Neither needs a key or an account.
