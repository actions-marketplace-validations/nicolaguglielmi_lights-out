# Handoff: M0 closed on 2026-09-14

## Acceptance

`./go help` lists the targets; `./go ci` is the CI (the workflow only runs it);
the README-truth check is `ci/readme.sh`. Fresh clone, workbench image removed
first, rootless podman 5.7.1 on macOS (podman machine, arm64):

```
$ git clone <repo> && cd lights-out && ./go demo
[demo] ci (M0): running
GO: secrets
GO: lint
GO: shell
GO: help
GO: readme
GO: gitea-compat
GO: profiles
GO: ci
[demo] engine-compat: NOT YET (M2)
[demo] up: NOT YET (M2)
[demo] deploy: NOT YET (M3)
[demo] verify: NOT YET (M3)
[demo] rollback: NOT YET (M3)
[demo] e2e: NOT YET (M6)
GO: demo, milestone M0. Green means the repo is coherent, not that the platform works yet.
./go demo  1:03.17 total   (cold build with no layer cache measured at 1:28; image 1.07 GB)
```

`sh ci/engine-compat.sh` on this host: prints `podman version 5.7.1`, marks
`docker` as a podman shim (not tested), exits 1 `NO-GO: nothing to check
before M2`, by design. `./go up`, `./go e2e`, `./go demo-rollback` exit 1
with `NO-GO: <target> arrives with M<n>`.

Not proven: a green run on GitHub Actions. The repo has no remote yet. First
push will tell; `ubuntu-latest` has docker, so `./go` takes the docker branch.

## What changed

- `go` (POSIX sh) is the only host entrypoint; it builds `workbench/Containerfile` (debian trixie-slim by digest, 8 tools by version and sha256 per arch) and runs `make` inside.
- `Makefile`: `help`, `ci` (7 checks in `ci/*.sh`), `demo` (ADR 0003 stage list), stubs that fail loudly. Profiles `l0..l3.env` select adapters by port name.
- `.github/workflows/ci.yml`: checkout + `./go ci`, Gitea-compatible subset only.
- README, `docs/ARCHITECTURE.md`, ADR 0001-0004, LICENSE (Apache-2.0 verbatim), NOTICE, SPDX headers on `go`, `Makefile`, `Containerfile`, `fetch.sh`, `ci/*.sh`.
- `docs/PLAN.md` and `CLAUDE.md` updated: `./go` replaces `make` in every criterion; toolchain-in-container and SPDX rules added; Vertex AI renamed in the L2 row.

## Found while building, contradicting or missing from docs/PLAN.md

- `podman info` returns the socket path with a `unix://` prefix, and the podman machine VM enforces SELinux: socket mounts need `--security-opt label=disable`. `go` does both. Any container that gets the socket sees every compose project on the machine (verified: `docker-compose ls` inside workbench listed an unrelated project). The README states the consequence.
- On this host `docker` is podman's shim, so `ci-engine-compat` can never test real docker here; M2 needs a real docker host (GitHub runner) for that leg.
- PLAN §5 still says Antigravity Managed Agents are billed per run; the Gemini API docs say per token plus tools, sandbox compute free during preview. Not changed, the owner's call.
- PLAN §5 says Antigravity SDK is public preview; PyPI ships `google-antigravity` 0.1.16, Apache-2.0, with a closed compiled runtime in the wheel, usable with a plain `GEMINI_API_KEY`. The `antigravity-sdk` adapter is cheaper than the plan assumes.
- The gcloud tarball bundles its own Python (3.14.7); `CLOUDSDK_PYTHON=/usr/bin/python3` in the Containerfile is therefore only a fallback. Harmless, could be dropped.
- ADR 0004 estimates 3-6 min for the workbench build; measured 1:28 cold on a fast line. The 6-minute budget holds with margin.

## First thing M1 should look at

M1 adds the target app under `app/`. Its tests run inside workbench (uv, node are there), so the first question is how `./go` and the Makefile expose an app-level `test` target without the app's toolchain leaking to the host. Also check `docs/adr/0004` point 5: the app's compose file must stay in the subset `ci-engine-compat` will prove at M2, and it must use ports above 1024.
