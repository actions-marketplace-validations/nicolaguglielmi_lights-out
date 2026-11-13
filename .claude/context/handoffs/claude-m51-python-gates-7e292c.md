# Handoff: M51, `gates/` under the shell boundary (ADR 0084), 2026-11-13

Branch `claude/m51-python-gates-7e292c`, cut from `main` at d1390ba. Pushed, no pull request, nothing merged: the coordinator lands it.

## What changed

- **ADR 0084** puts `gates/` under ADR 0052's rule (ADR 0052 §6 amended to point at it). What stays shell: the gate wrapper (guards, `require_range`, `toolchain_preflight`, the one line), the process glue, adapter verbs, `./go` and `lights-out`. The logic moves to a package, `core/gates/`, run as `python3 -m core.gates.<x>` from the repository root; under `core/` so the self gate mutates and scans it (ADR 0049), a package of its own so the `lights-out-gates` wheel (top of `core/` only) does not ship it.
- **`verdict MODULE [ARG...]`** in `ci/lib.sh`: exit 0 is GO (first stdout line the detail), exit 1 NO-GO (first line the reason, the rest details, so `$NOGO_DETAILS` still gets them), anything else a NO-GO naming the module.
- **`core/gates/__init__.py`**: `NoGo`, `main`, `say`, `proc` (the package's one excused process call), `adapter(dir)` (a port's verbs) and `run_id()`.
- **`core/toolchain-run.sh`**: `sh core/toolchain-run.sh CMD` runs a workload command through `core/toolchain.sh` for a gate's Python; `--preflight` prints `$toolchain_where` or the preflight's reason (test-proof checks no toolchain before a GO by absence of subject, as before).
- **Gates moved** (each wrapper keeps path, arguments, environment, stdout line, `$GATES_OUT` files and the stderr lines `ci/` reads):

  | gate | module | wrapper code lines, before → after |
  |---|---|---|
  | production-readiness | `readiness.py` (also `adapter_hash`, held equal to `ci/lib.sh`'s by a test over every adapter) | 60 → 4 |
  | deps | `deps.py` | 97 → 5 |
  | mutation | `mutation.py` | 159 → 10 |
  | sast | `sast.py` (calls `core/sastdiff.py`'s new `diff()`, `main` unchanged) | 90 → 8 |
  | test-proof | `testproof.py` | 34 → 5 |
  | risk | `risk.py` (the inline Python heredoc gone) | 25 → 8 |
  | statestore-conformance | `statestore.py` | 134 → 7 |
  | eventbus-conformance | `eventbus.py` | 156 → 7 |
  | codehost-conformance | `codehost.py`; the wrapper reads the secrets case 10 looks for, since `core/` may name no vendor (`ci/vendor-free.sh`) | 234 → 15 |
  | delivery-conformance | `delivery.py` (writes the conformance record with `readiness.adapter_hash`) | 200 → 7 |
  | test-weakening | `core.testdiff` through `verdict` | 21 → 11 |

  `spec.sh` (7) and `test.sh` (22) unchanged.
- **Not moved, on the debt list:** `gates/harness-conformance.sh` 693 and `gates/harness-conformance/proof.sh` 738 code lines. Only `./go harness-conformance` on a real engine proves a rewrite of them: the next slice.
- **`ci/shell-boundary.sh`** scans `core/` and `gates/`; its probe plants a `gates/` file over 30, a `gates/` debt grown and one shrunk. Shown on the real tree: a planted `gates/planted.sh` of 31 code lines and one line added to `proof.sh` are both NO-GO.
- **Tests**: 103 new `unittest` cases in `core/tests/test_gates_*.py` (+ `gitrepo.py`, a scratch-repository helper), written from the gates' headers and ADRs. The suites take a fake port in Python, broken one behaviour at a time; each break must be a NO-GO naming its case.
- **Callers**: `ci/store-bus.sh` links `core/` into its temp tree (one line). Nothing else changes.
- **Docs**: `docs/PLAN.md` (section M51), README's shell-boundary line, `CONTRIBUTING.md` (where code goes), `docs/reference.md` layout.

## Line counts (tracked files, `.sh`; code = non-blank, not a comment)

| directory | lines before | lines after | code before | code after |
|---|---|---|---|---|
| gates/ | 4,074 | 2,489 | 2,670 | 1,539 |
| core/ | 2,107 | 2,135 | 1,206 | 1,220 (+`toolchain-run.sh`) |
| ci/ | 17,043 | 17,088 | 12,745 | 12,778 (`verdict`, the ratchet's probe) |
| adapters/ | 4,730 | 4,730 | 2,722 | 2,722 |
| all `.sh` | 31,175 | 29,663 | | |

Python: `core/gates/` 1,943 lines, its tests 1,494; all `.py` 33,035 → 36,475.

## Verified

- **`./go ci` GO** from a full clone at `.crew/m51` (e0e6db3), 448 s, `contract` included. Three earlier runs caught what host runs could not: shellcheck on `core/toolchain-run.sh`'s computed source paths, `ci/vendor-free.sh` (the codehost suite named Gitea and GitHub inside `core/`: the wrapper now reads those secrets, ADR 0084 §2), `ci/model-free.sh` (a test key name), and `ci/tower.sh`'s hand-built host tree, which lacked `core/gates/`.
- **GitHub Actions on e0e6db3, all five workflows green**: ci 43459416602 (engine-compat `GO: demo, milestone M9, 856s` and, rerun, `841s`; `GO: codehost-conformance — gitea, PR #1 merged`; `GO: statestore-conformance — firestore-emulator, 8 cases`; `GO: eventbus-conformance — pubsub-emulator, 5 cases`; argo's delivery suite and `production-readiness` GO on its record; `GO: harness-conformance — antigravity-cli claude-code codex gemini-cli, 393 s`), self 43459416461 (`GO: gates — risk high, review, in workbench`: mutation and bandit on the new `core/gates/` lines), stranger 43459416453 (a fresh runner's `./go demo`), package 43459416590, podman 43459416668.
- **Demo time.** Main's engine-compat demos on Actions fall on two runner profiles: 696 s and 719 s (fast), 826 s (slow, run 43401715906). Both branch runs landed on the slow one. Check by check against that run, the only consistent difference is `core-tests`, +4 to 6 s for the 103 new unit tests; the end-to-end part that runs the moved gates (`audit`, `launchpad`) is within ±3 s. Locally `./go demo` reached the rollback in 1,235 s, over the 900 s budget, on a VM that had just recovered from a hang with other projects' containers and an M32 run beside it; a second local run was not possible (another session took the plane slot). Main's last local figure is 660 s (e86d52f, quiet machine).
- On the host: 1,294 unit tests OK; `ci/readiness.sh`, `ci/store-bus.sh`, `ci/shell-boundary.sh`, `ci/vendor-free.sh`, `ci/app-free.sh`, `ci/model-free.sh`, `ci/prompts.sh`, `ci/plugin.sh`, `ci/gates-light.sh` GO; docs-drift GO with `MAP_EXCLUDE='docs/PLAN.md docs/plans/* .claude/*'`.
- The ratchet fails on a planted `gates/planted.sh` of 31 code lines and on one line added to `gates/harness-conformance/proof.sh`, then is GO again.

## Next

- The harness pair: move `check_*`, `prepare`, the canaries and the case table into `core/gates/harness.py`, keep compose in a thin shell, and prove it with `./go harness-conformance` per harness. Then `core/toolchain.sh` (126), then `ci/`.
- Expect conflicts with M32 on `ci/lib.sh`, the `gates/*-conformance.sh` bodies, `docs/PLAN.md`, `README.md`, `docs/reference.md`, `CONTRIBUTING.md`.
