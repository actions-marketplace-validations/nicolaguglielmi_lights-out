# ADR 0004 — The toolchain lives in a `workbench` container; `./go` is the only host entrypoint

- Status: accepted (amends ADR 0002 and ADR 0003). Amended by ADR 0012: §2 the runner is host mode on an image built from workbench, not docker mode; §4 engine-compat runs from `./go` on the selected engine and never joins `make ci`; §5 `:z` leaves the seed list, replaced by `security_opt: label=disable` on the one bind-mounted service. Amended by ADR 0015: Testcontainers rootless facts are void as of M4 (integration tests remain on compose Postgres per ADR 0010).
- Date: 2026-09-14
- Milestone: M0

## Context

The project owner fixed the host prerequisites to podman, git and a POSIX
shell. Podman rootless is the reference engine; docker stays supported.
Make is no longer a host prerequisite, so ADR 0002's `docker run` per tool
and ADR 0003's `make demo` need a container that carries make and the tools,
and a script that gets a stranger into it. On macOS podman runs inside
`podman machine` (a VM); bind mounts and sockets are resolved by the engine
inside that VM, not by the host. Facts verified on 2026-09-14 are cited
inline.

## Decision

`./go <cmd>` is a dependency-free POSIX sh script that picks an engine,
builds or reuses the `workbench` image from `Containerfile`, and runs
`make <cmd>` inside it with the repo bind-mounted at the same absolute path
as on the host (`-v "$PWD:$PWD" -w "$PWD"`). Inside workbench
(`LIGHTS_OUT_WORKBENCH=1` set by the Containerfile) `./go` execs `make`
directly, so the CI workflow step is `./go ci` everywhere and the Makefile is
unchanged in spirit. Engine: `CONTAINER_ENGINE` if set, else podman, else
docker, else exit 1 with a message naming both. Acceptance criteria read
`./go X` from now on.

1. **Base image: `docker.io/library/debian:trixie-slim`, pinned by index
   digest.** `FROM docker.io/library/debian:trixie-slim@sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132`
   (index updated 2026-08-25, 29.8 MB amd64, 30.2 MB arm64). The index
   digest, not a per-arch one, so one line serves Intel and Apple silicon.
   Every tool is a versioned release archive with its published sha256 per
   arch in `ARG`s at the top of the Containerfile, one `TARGETARCH` case
   block: gcloud 584.0.0 from the versioned tarball
   (`google-cloud-cli-<ver>-linux-{x86_64,arm}.tar.gz`, 87/52 MB, checksums
   published, needs Python 3.10–3.14; trixie has 3.13), terraform 1.16.2
   (zip + `SHA256SUMS`), node 24 LTS, uv, docker-compose v5 standalone
   binary, gitleaks 8.30.1, actionlint 1.7.12, shellcheck 0.11.0. Expected
   image: about 1.0 GB on disk, 350–400 MB downloaded, of which gcloud is
   roughly half. Rejected: `ubuntu:24.04` (same size, no `-slim`, faster
   digest churn; a coin flip, debian wins on cadence); the official
   `google-cloud-cli` image as base (1 GB+ before we add anything); apt repo
   for gcloud (adds a key and a repo to pin a version the tarball pins in one
   line).
2. **`make ci` needs no engine: gitleaks, actionlint and shellcheck are
   binaries in workbench.** I agree with the owner's reading. `./go ci` runs
   workbench *without* the socket, so the laptop proves the property CI
   relies on. Rejected: (a) socket into workbench for ci: makes a lint step
   engine-privileged, and on act_runner the job container's `$PWD` is a path
   the engine cannot see, so nested `docker run -v` breaks anyway; (c) ci
   tool containers from the host side: puts logic back into `./go`, which
   must stay a launcher. Correction to the premise: act_runner's default
   `docker_host: ""` *does* mount the socket into job containers; `"-"`
   withholds it (docs.gitea.com/runner/configuration). Superseded by ADR 0012 §3: M2 runs the runner in host mode (`ubuntu-latest:host`) inside an image built `FROM` the workbench image with the runner binary copied from the pinned upstream image, so no socket reaches the runner and `./go ci` still collapses to `make ci` there and on GitHub.
   Targets that need the engine (`up`, `demo`, `e2e`, `shell`, from M2) get
   the socket mounted at the path reported by
   `podman info --format '{{.Host.RemoteSocket.Path}}'` (engine-side path,
   correct inside `podman machine` too) with `DOCKER_HOST` pointing at it,
   and drive it with the docker-compose binary in workbench. Mounting the
   socket hands workbench full control of the engine; the README says so.
3. **At M0 `./go` builds workbench locally; publishing comes later, as a
   pull-by-digest with build fallback.** No registry account, no CI job, no
   trust decision needed to clone. Build measured on a clean machine:
   3 min at 100 Mbit/s, about 6 min at 20 Mbit/s (download-bound; gcloud's
   `install.sh` adds about a minute). Hard budget: 6 min, re-measured at
   every milestone close. When a CI runner exists (M2 at the earliest) a
   workflow publishes `ghcr.io/<owner>/lights-out-workbench` from the same
   Containerfile, and `./go` pulls the digest recorded in `workbench.lock`,
   building only if the pull fails. Rejected: publish at M0 (nothing to
   publish from); build cache tricks in the workflow (two-step workflow rule,
   ADR 0002).
4. **`ci-engine-compat` is a host-side POSIX sh gate, run once per engine
   found.** It is the one gate that does not run in a container, because its
   subject is the host engine. It prints `podman --version` and
   `docker --version` separately, and treats docker as a shim (not tested,
   said so) when the output does not start with `Docker version` or the
   binary resolves to podman. At M0 the script exists,
   prints the versions and exits 1: `NO-GO: nothing to check before M2`.
   Superseded by ADR 0012 §5: from M2 `./go engine-compat` runs the script on the host against the engine `./go` selected, printing every engine version found and marking a docker shim untested (NO-GO if the shim is the selected engine); it does `./go up` and `./go smoke` and leaves the plane running. It is the first stage of `./go demo`, never part of `make ci` (which has no engine), and CI runs it as one docker job on GitHub, skipped on Gitea by a job-level `if`.
5. **The repo targets Compose v2 (`docker-compose` binary in workbench)
   over the podman socket, never `podman-compose`.** Podman docs make
   `podman compose` a wrapper that prefers `docker-compose` when present;
   we remove the choice by shipping the binary, so the host needs no compose
   provider at all. Subset rule: a compose feature is allowed only if
   `ci-engine-compat` proves it on both engines; seed list from the owner:
   ports above 1024, `security_opt: label=disable` on the one bind-mounted service (`:z` rejected by ADR 0012 §2: podman #26465/#21269 show it failing on podman machine's virtiofs), network aliases instead of
   `host.docker.internal`, no `privileged`. Rejected: `podman-compose`
   (Python reimplementation, its own gaps, and docker users would run a
   different program than podman users).

## Consequences

- The image is 1 GB for a repo that is empty at M0; gcloud and terraform
  serve nobody before M8. Accepted by owner decision; if the 6-minute build
  budget breaks, the fix is publishing (point 3), not a second image.
- `$PWD:$PWD` requires the repo under a path the VM mounts (`/Users` on
  macOS by default). Cloning to a mounted volume fails; README states it.
- Under docker, files created in the bind mount are root-owned; `./go`
  passes `--user "$(id -u):$(id -g)"` only for docker. Rootless podman maps
  container root to the host user, no flag. Two engine-specific branches in
  `./go` are the ceiling; a third means this ADR is wrong.
- Per-tool, per-arch checksums: seven tools, fourteen hashes, bumped by hand
  in dedicated commits. Dependabot does not read Containerfile `ARG`s.
- Rootless facts the README must carry: socket
  `unix:///run/user/$(id -u)/podman/podman.sock` enabled via
  `systemctl --user enable --now podman.socket`, same value for the Gitea
  runner and Testcontainers; Testcontainers rootless needs
  `TESTCONTAINERS_RYUK_DISABLED=true` (docs say the `_PRIVILEGED` variant
  is for rootful and obsolete since 1.19; verify at M4); SELinux volume
  labels; `host.containers.internal`.
- ADR 0002: `docker run` per tool, the `/repo` mount and its act_runner
  consequence are replaced by this ADR. ADR 0003: `make demo` is `./go
  demo`; the two-minute M0 estimate becomes the numbers below.

## Golden-rule check

Stranger with podman, git, sh: `./go demo` = workbench build 3–6 min, plus
at M2+ the L0 plane pulls (budget 5 min; the Pub/Sub and Firestore emulator
images are the known risk, M2 must measure them), plus the demo itself
(budget 3 min). 11–14 min worst case on a 20 Mbit/s line, no account, no
key. Passes, with two minutes of margin and the emulator images unmeasured.
