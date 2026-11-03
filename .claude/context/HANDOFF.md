# Handoff: M20 "gates anywhere", 2026-11-03, branch `claude/vibrant-dubinsky-a82fa0`, not pushed, not merged

The owner reviews. Plan: `docs/PLAN.md` §16 M20 (status note added); decision: `docs/adr/0042-gates-anywhere-init-and-the-toolchain-contract.md` (0042, not the 0041 the brief said: 0039 was taken, main's commit 1d5098f renumbered the arc).

## Acceptance, run for real

All runs on 2026-11-03/04 from a full clone of the branch at `<worktree>/.crew/m20-run` (left in place, gitignored) (`./go` cannot drive git from a `.claude/worktrees` checkout, M13's finding 1), cold uv and npm caches in that clone, warm workbench and plane images, on the owner's machine (podman machine, aarch64).

```
./go demo-init  → GO: demo-init — minimal 40s in workbench (committed contract: risk high, review,
                  in compose:backend-test), minimal-js 8s in workbench (committed contract: risk high,
                  review, in docker.io/library/node:24@sha256:e7add2a4…)
                  per example: attach → GO: attached → gates on the committed contract through the
                  engine → GO: init (python: baseline 1.0, 8/8 mutants, 25s; javascript: baseline
                  0.9375, 30/32 mutants, 5s) → gates on the draft with DOCKER_HOST aimed at a path
                  that does not exist → GO: gates — risk high, review, in workbench
./go ci         → GO: ci, 74 s, 26 checks, ci/toolchain.sh and ci/init.sh among them
./go demo-gates → GO: demo-gates, 302 s, the app's six fixtures as recorded, every gate line
                  ending "in compose:backend-test": failing-test (test), fake-test (mutation
                  0.500 < 0.666), honest-fix (GO, low, auto-merge), migration (GO, high, review),
                  sast-finding (sast, 1 finding), vulnerable-dep (deps, 4 new advisories)
./go demo-seam  → GO: demo-seam, 133 s: workloads/minimal copied into a new repository, attached,
                  GO: attached, up, smoke, GO: metric-shape, rollback on error_rate
                  canary(0.2.0-outage)=1.000 stable(0.1.0-minimal)=0.000, honest-fix GO (risk low,
                  auto-merge, in compose:backend-test), down
./go demo       → GO: demo, milestone M9, 379 s to rollback (budget 900 s, plan §2): rollback on
                  error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000, then e2e GO
```

The 300 s of plan §16 (second golden-rule measure, owner decision, "to be re-measured at the first run"): measured 40 s and 8 s for `init` plus `gates`, cold caches. It holds for small suites: `init` measures the baseline over the whole scope, and the bundled app's whole-package run took 792 s (`app/workload.env`).

By hand, from the worktree: `./go init <path>` on a single-commit copy of `workloads/minimal` → `GO: init — python, draft in .attached/.lights-out, baseline 1.0 (8/8 mutants killed, 14s, in workbench)`; `./go gates` → `GO: gates — risk low, auto-merge, in workbench` in 4.6 s on the following commit, `risk high, review` on a root commit (`.lights-out/*` is platform risk, as ADR 0037 §5 says). The harness image built on `docker.io/library/python:3.13-slim-trixie` runs `gemini --version` (0.61.0-preview.0), `python3 --version` (3.13.18), git and jq, with no `node` on PATH. Not run at L1 (no key in this session).

`ci/toolchain.sh` and `ci/init.sh` were written by the gate-writer from the ADR, not from the code; it broke the implementation in six places on purpose and each break was caught. `core/tests/test_init.py` (the version matchers and the renderer) likewise.

## What changed

- **The runner contract** (ADR 0042 §1–§3): `workload.env` has eleven keys, the four new being `TOOLCHAIN_IMAGE`, `TEST_CMD`, `SAST_CMD`, `MUTATION_CMD`. `core/toolchain.sh` runs a declared command where the toolchain says: `workbench` (in-process, no engine; isolated in a throwaway workbench image under `TOOLCHAIN_ISOLATE=1`, which the tower's CI step sets), `compose:<service>` (the bundled app and `workloads/minimal` keep `compose:backend-test`), an image reference (a throwaway image `FROM <ref>; COPY . /work` built through compose, nothing bind-mounted). `gates/test.sh`, `gates/sast.sh`, `gates/mutation.sh` run through it and say where on their line (`go_with` in `ci/lib.sh`; `ci/contract.sh` and `make gates` accept the detail form; CLAUDE.md's contract paragraph says so). The sast and mutation gates read the runner's last stdout line.
- **No plane, no socket, no range** (§4–§5): `./go` mounts the socket for `gates`, `init`, `mutation-baseline`, `demo-init` only when it exists; `make gates` with no `BASE`/`HEAD` judges the last commit, the empty tree being a root commit's base (`require_range` takes a tree); `make up` refuses a contract without `compose.yaml`; `ci/secrets.sh` on an attached range scans history only, with `ci/gitleaks-attached.toml` and `--ignore-gitleaks-allow`.
- **`./go init [<path>]`** (§6): `core/attach.sh` accepts a repository without a contract (and refuses to overwrite an uncopied draft); `core/init.py` infers python (`pyproject.toml` + `uv.lock`) or javascript (`package.json` + `package-lock.json`) and drafts `workload.env` (a provenance comment over every value), `worker.md`, `policy.env` and `runners/` into `.attached/.lights-out/`; `core/init.sh` measures `MUTATION_BASELINE` through `core/mutation-baseline.sh` (also `./go mutation-baseline`, now toolchain-aware) and runs the contract check. `ci/workloads.sh` checks the eleven keys, the forms, `$`/`#` in a command, and the plane half only when `compose.yaml` exists (§7).
- **Two stacks** (§6, §9): `stacks/python/runners/` (cosmic-ray 8.7.0 and bandit 1.9.4 from `uv.lock`, synced into their own environment) and `stacks/javascript/runners/` (StrykerJS 10.1.1, eslint 10.14.0, eslint-plugin-security 4.2.1 from `package-lock.json`, `npm ci` into a temporary prefix; a node scorer). `workloads/minimal-js/` is the javascript example, gates half only, `node:24` by digest as its committed toolchain, baseline 0.9375 measured (two equivalent boundary mutants). `workbench/Containerfile` gains `procps` (Stryker's command runner needs `ps`). `workloads/minimal` re-locked (no advisory left; OpenTelemetry 1.45.1 / 0.66b1) and its conftest sets `OTEL_SEMCONV_STABILITY_OPT_IN` itself.
- **The dev-worker on the toolchain** (§8): `adapters/gemini-cli/Containerfile` takes `HARNESS_BASE_IMAGE` (the Makefile exports it from `TOOLCHAIN_IMAGE`), copies its own node from the workbench stage under `/opt/harness`, installs git and jq with apt when missing, wraps `gemini` to the resolved `bundle/gemini.js`.
- **Checks and docs**: `ci/toolchain.sh`, `ci/init.sh`, `core/tests/test_init.py`; `ci/attach.sh`'s refusal case rewritten to the new attach rule; `ci/app-free.sh`, `ci/prompts.sh`, `ci/shell.sh` widened; `ci/secrets.sh` allowlists the gitignored `.crew/cache/`; `gates/deps.sh` reads osv-scanner's "no package sources" exit as clean; `.github/workflows/ci.yml` gains the `init` job. README, `docs/use-on-your-repo.md` (rewritten around init first, then the plane), `docs/reference.md`, `docs/ARCHITECTURE.md`, `docs/PLAN.md` §16.

## Found (contradicts the plan or the brief)

1. **The plan's "same image" for the dev-worker holds for the image form only.** A `compose:` toolchain is a service, not an image the harness can build on; the worker stays on the workbench there (ADR 0042 Consequences). The bundled app is that case.
2. **No semgrep.** Plan §16 names it as the workbench-binary SAST example; the SAST command already runs in the workbench through the stack's own tools, so no third binary was added (ADR 0042, alternatives).
3. **`node:*-slim` cannot run Stryker's command runner** (tree-kill needs `ps`), nor could the workbench until `procps` was added. The example names `node:24`, not slim, and `init` drafts the full node image for a non-admitted runtime.
4. **A test suite that only passes inside its image.** `workloads/minimal`'s metrics test relied on an env var its Containerfile sets; outside the image it failed. Expect more of this on real repositories: `init`'s NO-GO names the command and keeps the draft.
5. **The 300 s is a small-suite number.** `init` measures the whole scope; on the bundled app that is 792 s. The README and the ADR say so.
6. **`deps` on a root commit judges the lockfile whole.** `workloads/minimal` carried 18 inherited advisories (aiohttp, gitpython, certifi, opentelemetry-api) that would have failed its first `./go gates`; re-locked clean today, and it will rot again (ADR 0015's time bomb, now on a user's first run).
7. **The ADR numbering** shifted after the brief: 0042, per main's 1d5098f.

## Not done, and open decisions for the owner

- The dev-worker on a toolchain image is built and probed, not run at L1 with a key.
- `node_admits` matches a major only (`~24.1`, `>=24.5` read as not admitted although the workbench has 24.21.0); the gate-writer left it unasserted.
- `init` writes image tags, not digests (it has no engine to resolve one); the comment says to pin before committing.
- `workloads/minimal-js` has no `fixtures/gates/` (the port asks for at least one for `demo-gates`; nothing runs `demo-gates` on it yet).
- Every `./go gates` through an image form rebuilds a throwaway image (a `COPY` layer per run); old `lo-toolchain-toolchain` images accumulate until pruned.
- Expect merge conflicts with the M18 branch (`claude/bold-bouman-b4b874`) on `Makefile`, `README.md`, `compose.yaml` (the gemini-cli service's build args), `docs/PLAN.md` §16 and `docs/reference.md`.

## First thing M21 should look at

`core/toolchain.sh`'s image form and `HARNESS_BASE_IMAGE` are what the release of an attached merge will build on: the merge commit's image is `FROM` the repository's `Containerfile` or `TOOLCHAIN_IMAGE` (plan §16 M21), and `ci/workloads.sh`'s two halves say when a repository has a plane to release to at all.
