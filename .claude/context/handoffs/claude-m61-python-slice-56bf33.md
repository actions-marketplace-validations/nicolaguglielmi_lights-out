# M61 — the second Python slice (handoff)

Branch `claude/m61-python-slice-56bf33`, main 5f42b22 (M58, M59, M60, M62)
merged in with main as first parent. Not merged to main.

## What changed

- **ADR 0084, amendment of 2026-11-16 (A1–A5)** for the harness pair and the
  toolchain: the boundary over `core/` and `gates/` does not move.
  **ADR 0094** for `ci/`: a `ci/` check's Python lives in `ci/checks/`, its
  tests in `ci/tests/` (run by `ci/core-tests.sh`), outside `core/` and the
  self gate's scope; `ci/` enters the ratchet after M58–M63 land; §4 lists
  its 47 files over 30 code lines, measured at the merged head.
- **The harness suite** is `core/gates/harness.py` behind `verdict`;
  `gates/harness-conformance.sh` keeps its guards (18 code lines). The cases
  are a table, `CASES`; a provider is one row of `PROVIDERS` (the order case 0
  offers them, and the harness a refusal names when none is discovered); a
  harness is discovered, and runs once per conformance file (ADR 0092 §2).
  **M59's `zai`** (landed first in shell) is carried in: the `zai` row, one
  run per `conformance.<provider>.env`, `<harness> (<provider>): case <n>:`,
  directories `<harness>/<provider>/<case>` for a further provider,
  `tokens.cached` (ADR 0092 §6).
- **The proof** is `core/gates/harness_proof.py` (`DEFECTS`, 62 rows of which
  3 good; `PROBES`); `proof.sh` keeps two guards (9 code lines). fake-cli
  (`run.sh` one `exec` into `run.py`), the stand-in `docker-compose` (Python),
  the notes server, the agents shim, `egress_wrap.py` and netshim are files
  under `gates/harness-conformance/fake/`, out of the self gate's scope like
  `stub.py` and `probe.py`.
- **The toolchain** is `core/gates/toolchain.py`; `core/toolchain.sh` keeps
  `toolchain_preflight` and `run_in_toolchain` (11 code lines), run with
  `python3 -P` and `PYTHONPATH=$toolchain_root` (default the caller's
  directory); CMD gets the caller's PYTHONPATH back; `core/toolchain-run.sh`
  calls the module directly.
- **`ci/contract.sh`** (225 code lines → 4) is `verdict ci.checks.contract`;
  its planted tree (10 rejected and 2 accepted records, three broken `nogo`s,
  a broken `record_check`) is the same, run by the same check.
- **Ratchet:** `core/toolchain.sh` and the harness pair (709 and 767 on main
  after M59) leave the debt list; each is now ≤ 30 code lines.

## Line counts, tracked `.sh`, main 5f42b22 → this branch

| dir | lines | code lines |
|---|---|---|
| gates/ | 2,594 → 626 | 1,598 → 183 |
| core/ | 2,554 → 2,386 | 1,509 → 1,388 |
| ci/ | 19,536 → 19,278 | 14,721 → 14,510 |
| adapters/ | 5,747 → 5,747 | unchanged |
| all `.sh` | 34,274 → 31,880 | 23,643 → 21,896 |

From the sprint's base b4b1590 (before the merge): gates/ 2,515 → 626,
core/ 2,254 → 2,086, ci/ 17,965 → 17,707, all 31,274 → 28,959.

Python added: `core/gates/harness.py`, `harness_proof.py`, `toolchain.py`,
`ci/checks/contract.py`; 95 unit tests (`test_gates_harness.py` 45,
`test_gates_harness_proof.py` 15, `test_gates_toolchain.py` 21,
`ci/tests/test_contract.py` 14), the fixtures' `run.py` and `docker-compose`.

## Proof, before and after

- **The suite's proof, before the merge:** shell GO (316 s) and Python GO in
  the workbench; all 57 verdict lines identical once random ports, run ids and
  temp paths are normalised.
- **After the merge:** main's shell proof (5f42b22) and this branch's Python
  proof, both GO in the workbench, give the same 62 verdict lines
  (`.crew/m61-logs/mb.txt`, `ma.txt`).
- **The real suite, Python, before the merge (93b9005):** GO on all four
  harnesses on docker, 365 s (ci run 43838234963, job harness-conformance),
  and on claude-code on rootless podman (podman run 43838234853).
- **`ci/toolchain.sh`:** GO before and after; planted in the real module, a
  socket test that accepts anything (`b-no-socket`) and a form test that
  accepts anything (`c-form`) are each refused.
- **`ci/contract.sh`:** GO cold, its planted proof included.
- **93b9005, before the merge:** ci 43838234963, podman 43838234853, package
  43838234819, stranger 43838234989 (`./go demo` from a clean runner) green;
  self 43838235097 superseded by the merge.
- **`./go ci` from `.crew/m61` on the merged head a2d2299:** GO, 396 s, 56 checks.
- **Actions on the merged head:** the runs on this branch's head after the push of 2026-11-16 (ids in the report to the landing session).

## Found on the way

- The Makefile's count of the proof's wrong harnesses was stale (fifty-four,
  then fifty-nine after M59); it now says fifty-nine and three good runs, and
  names the table.
- The workbench form's venv directory is now named by `zlib.crc32` of the
  workload's real path, not `cksum`: an existing `.crew/cache/venv/<n>` is
  unused once, then rebuilt.
- A missing `WORKLOAD` in the toolchain preflight used to abort the shell
  (`${WORKLOAD:?}`, no contract line); it is now a NO-GO line.
- `ci/store-bus.sh` (M51's eventbus suite on a stub bus, 1 s deadline) failed
  once in a 1,010 s `./go ci` on a loaded VM, then passed twice alone: a load
  flake in code this branch does not touch.
- `ci/tests/test_contract.py`'s `bad-unset` lib is caught by dash (the
  workbench's `sh`) and not by macOS's bash-as-sh; the shell check had the
  same blind spot.

## `ci/` scripts this branch changes (conflicts at landing)

`ci/contract.sh` (body replaced), `ci/core-tests.sh` (one line),
`ci/shell-boundary.sh` (three debt lines removed), `ci/toolchain.sh` (probe
by checkout root, flaws planted in the module); new `ci/__init__.py`,
`ci/checks/`, `ci/tests/`. Next candidates by code and branching lines:
`logbook`, `tower`, `plugin`, `attach`, `postmortem` (ADR 0094 §4).

## Site text (for the session that owns `site/index.html`)

"The gates' logic is Python with unit tests: since 0.7.0 the CLI-harness
conformance suite, its proof and the toolchain moved too, and `gates/` is down
to 183 lines of shell code, the guards and the one line."
