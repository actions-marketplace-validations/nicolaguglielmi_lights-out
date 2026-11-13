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
  | test-weakening | `core.testdiff` through `verdict` | 21 → 12 |

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

- On the host: `python3 -m unittest discover -s core/tests -t .`: 1,294 tests OK. `sh ci/readiness.sh`, `sh ci/store-bus.sh` (sqlite and spool adapters for real, every stub break), `sh ci/shell-boundary.sh`: GO. `core/tests/test_gate_range.py` drives `gates/test-proof.sh` end to end through `core/toolchain-run.sh`: OK.
- Not yet on this machine: `./go ci` and `./go demo` from `.crew/m51`. The podman VM hung at about 16:45 (an M32 GitLab run beside an emulated build); see the commit or PR notes for the Actions runs that stand in.

## Next

- The harness pair: move `check_*`, `prepare`, the canaries and the case table into `core/gates/harness.py`, keep compose in a thin shell, and prove it with `./go harness-conformance` per harness. Then `core/toolchain.sh` (126), then `ci/`.
- Expect conflicts with M32 on `ci/lib.sh`, the `gates/*-conformance.sh` bodies, `docs/PLAN.md`, `README.md`, `docs/reference.md`, `CONTRIBUTING.md`.
