# ADR 0002 — Repo self-CI is `make ci`, run in pinned containers

- Status: accepted. Amended by ADR 0004: tools are binaries in the workbench image, no `docker run` per tool, no `/repo` mount, act_runner consequence superseded.
- Date: 2026-09-14
- Milestone: M0

## Context

The plan (section 3) requires the same workflow YAML to run on Gitea Actions
(act_runner, L0/L1) and on GitHub Actions (L2/L3). Section 9 requires a
secret-scan check in CI, pinned versions, and a README that tells the truth.
Gitea Actions supports only the simple `runs-on: xyz` form, ignores
`jobs.<id>.environment`, has no `id-token` scope and supports `always()` as
the only status function (verified on docs.gitea.com, 2026-09-14).

## Decision

The workflow does exactly two things: checkout (`fetch-depth: 0`) and
`make ci`. One file, `.github/workflows/ci.yml`, read by both GitHub and
Gitea; no `.gitea/` copy. All logic lives in the Makefile so that a laptop,
act_runner and GitHub produce the same result.

`make ci` runs each check as `docker run --rm -v "$(CURDIR)":/repo -w /repo
<image>`. Images are pinned by tag in one variable block at the top of the
Makefile, all from Docker Hub (one registry). Tags verified to exist on
2026-09-14:

| Check | Tool | Image |
|---|---|---|
| (a) secret scan, full history | gitleaks | `zricethezav/gitleaks:v8.30.1` |
| (b1) workflow lint + shell in `run:` steps | actionlint (bundles shellcheck) | `rhysd/actionlint:1.7.12` |
| (b2) standalone `*.sh` and scripts under `gates/`, `verify/` | shellcheck | `koalaman/shellcheck:v0.11.0` |
| (c) `make help` exits 0 | make | none, runs in place |
| (d) README truth: every `make <target>` in README appears in `make help` | grep + diff, inline in Makefile | none |
| (e) Gitea compatibility: workflows contain no `environment:`, `id-token`, `success()`, `failure()`, `cancelled()`, no map-form `runs-on` | grep, inline in Makefile | none |

Three images, about 80 MB total. Check (e) exists because actionlint checks
GitHub semantics only and would not flag the constructs Gitea ignores.
`make ci` does not read the profile and must pass on an empty repo.
`.env.example` fake values must not look like secrets; no gitleaks allowlist
at M0.

## Alternatives rejected

- trufflehog: larger image, verifies candidates against live APIs by default,
  so the result depends on network and time. gitleaks is deterministic.
- detect-secrets: needs a committed baseline file to maintain, and Python.
- yamllint: no maintained pinned image (cytopia stale since 2023,
  pipelinecomponents publishes commit-hash tags only). Workflow YAML is
  parsed by actionlint; compose YAML is validated by `docker compose config`
  from M2; other YAML is validated by whatever consumes it.
- checkmake: no container image. `make help` succeeding is the Makefile
  check that matters.
- super-linter / MegaLinter: one image, but multi-GB, and pins a hundred
  tools we do not use. Breaks the 15-minute cold clone.
- Running tools from GitHub Actions marketplace steps: does not run on a
  laptop, and most actions are untested on act_runner.

## Consequences

- `make ci` needs a Docker socket wherever it runs. On act_runner the job
  container does not have one, and a bind mount of `$(CURDIR)` refers to a
  path the host daemon cannot see. M2 must register the runner in host mode
  (`label:host`) with make, git and docker CLI available, or mount the socket
  and use `--volumes-from`. This is the M2 problem this ADR creates.
- Dependabot does not parse Makefiles: image bumps are manual, dedicated
  commits, as section 9 already requires.
- Pinning by tag, not digest. Tags on Docker Hub are mutable; if it ever
  matters, switch the variable block to `image@sha256:...` without touching
  the workflow.
- Docker Hub anonymous pulls are rate-limited per IP; three pulls per run is
  fine, but a classroom on one NAT could hit it.

## Golden-rule check

Nothing to install, nothing to authenticate, three small pulls. Passes.
