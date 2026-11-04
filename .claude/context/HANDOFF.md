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

---

# Handoff: M18 "the model is a choice", 2026-11-03, branch `claude/bold-bouman-b4b874`, not pushed, not merged

The owner reviews. Plan: `docs/PLAN.md` §16 M18 (status note added); decision: `docs/adr/0040-the-model-is-a-choice.md` (0039 was taken the same day by the Gitea-runner ADR; §16's numbers after it shift by one).

## Acceptance, run for real

All runs from a full clone of the branch at `<worktree>/.crew/m18-run` (a worktree cannot drive git through the workbench, M13's finding 1), `.env` holding only `APP_PORT=9000`, no key of any provider, warm images, other sessions sharing the host.

```
./go ci          → GO: ci, 25 checks in 73 s, ci/model-free.sh among them (GO: model-free);
                   evals ran the 23 ADK unit tests (replay, model, offline LiteLLM transformation) in the workbench
./go demo        → GO: demo, milestone M9, 359s to rollback (budget 900s, plan §2)
./go demo-triage → GO: demo-triage, three alerts replayed at L0; each incident.json's run says
                   provider null, model null, source fixtures/adk, recorded {provider gemini, model gemini-3.8-flash}
```

By hand: `sh ci/model-free.sh` → `GO: model-free`; with a planted `# gemini-3.8-flash` under `roles/` → `NO-GO: model-free — core/, gates/, verify/ or roles/ names a model or a key`, the hit on stderr. `adapters/gemini-cli/run.sh` refuses, before any container, `MODEL_PROVIDER=anthropic` (names the M19 harnesses), an empty `MODEL`, a placeholder `GEMINI_API_KEY`, and a `THINKING` outside its `thinking.env`. Offline, with litellm 1.106.6: `reasoning_effort` low/medium/high reaches Claude as `thinking {type: adaptive}` + `output_config.effort <same>` and OpenAI as `reasoning_effort <same>`; the map is 1:1 (`adapters/adk/lights_out_adk/tests/test_model.py`).

Measured: workbench image 1.56 GB → 1.75 GB with litellm (+190 MB); a from-scratch `uv sync` of the new lock took 6 s on this line.

## What changed

- `MODEL_PROVIDER` (gemini|anthropic|openai) and `MODEL` in `profiles/l1..l3.env` (gemini, gemini-3.8-flash), empty in `l0.env`, overridable in `.env`; `.env.example` gains `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and commented pairs (`claude-sonnet-5-5`, `gpt-6.1-sol`); gitleaks allowlists the three key lines in `.env`.
- Thinking maps `adapters/adk/thinking.env` and `adapters/gemini-cli/thinking.env`, one line per provider and level with its source; roles keep `THINKING` and budgets only.
- `adapters/adk/lights_out_adk/model.py`: Gemini through ADK's `Gemini` plus the planner; Claude and OpenAI through `LiteLlm(model="<provider>/<id>", reasoning_effort=…, api_key=…)` with no planner (LiteLlm ignores `thinking_config`), imported only on that branch so L0 never loads litellm; `RecordingLlm`/`ReplayLlm` unchanged in shape, recordings gain `provider`; `run.json` of both harnesses carries `provider` and the served `model` (null at L0, the fixture's under `recorded`).
- `adapters/gemini-cli`: `-m "$MODEL"` and the alias keyed on it, Gemini only until M19.
- `ci/model-free.sh` in `CI_CHECKS`; `record-evals` scans each set provider key; `litellm==1.106.6` pinned in `workbench/pyproject.toml` and `uv.lock`, `LITELLM_LOCAL_MODEL_COST_MAP=True` set by the adk adapter so litellm fetches nothing at import.
- README, `docs/reference.md`, `docs/ARCHITECTURE.md`, `docs/PLAN.md` §16 updated.

## Found (contradicts the plan or the brief)

1. Plan §16 numbers M18 as ADR 0039; 0039 went to the Gitea-runner ADR the same day. M18 is 0040 and M19–M23 shift to 0041–0045 (PLAN.md headings renumbered).
2. The done-when command `./go record-evals PROFILE=l1 MODEL_PROVIDER=anthropic` cannot work alone: the profile's `MODEL=gemini-3.8-flash` would still apply. The ADR rejects a default id per provider, so the command names both: `MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5` (PLAN.md amended).
3. ADK 2.9.1's `LiteLlm` does not read the planner's `thinking_config`: a planner beside it is a lever that looks wired and is not (ADR 0018's bug shape). The level travels as `reasoning_effort`; the test asserts no planner on those providers.
4. `record-evals` grepped the fixtures for `$GEMINI_API_KEY`; with that key empty (an Anthropic-only `.env`) the grep matches every file and would have deleted a valid recording. Fixed in the Makefile.
5. Subagents started from this session get an isolated worktree cut from the committed HEAD: the gate-writer could not act on uncommitted work and the gate and tests were written here from the ADR; the architect and doc-scribe wrote by absolute path and were fine.

## Not done, and open decisions for the owner

- **The one item left to you:** no non-Gemini recording exists. `./go record-evals PROFILE=l1 MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5` and the same with `MODEL_PROVIDER=openai MODEL=gpt-6.1-sol` are implemented and documented, not run: they spend your keys. After a run, `fixtures/adk/<role>/*.json` carry `"provider": "anthropic"`, and `./go demo-triage` at L0 shows it under `recorded`. The plan's done-when stays open on that point until then.
- At L1 with `anthropic|openai` the three ADK roles run but the crew step refuses (gemini-cli is Gemini only), so `./go e2e PROFILE=l1` stops at dev-worker until M19.
- `MAX_TURNS` and `TOKEN_BUDGET` in `roles/` are Gemini measurements; other tokenizers count differently. They bind only gemini-cli for now; re-measure per provider in M19.
- `docs/reference.md` still says "Only L0 exists today. Levels L1–L3 describe the plan." under the levels table, which predates L1; not touched here.

## First thing M19 should look at

`adapters/gemini-cli/run.sh`'s provider refusal and `docs/adr/0040` §4: the `claude-code` and `codex` harnesses take `MODEL_PROVIDER`, `MODEL` and the provider's key from the same profile, map `THINKING` in their own `thinking.env`, and write `provider` and the served `model` into `run.json` like the two harnesses do now; the conformance suite should assert exactly that.
