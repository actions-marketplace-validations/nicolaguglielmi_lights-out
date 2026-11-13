# ADR 0084 — `gates/` under the shell boundary: the wrapper stays shell, the logic moves to `core/gates/`, the ratchet holds both

- Status: proposed (M51)
- Date: 2026-11-13

## Context

ADR 0052 put `core/` under a rule: a shell file has at most 30 code
lines, logic goes to Python, a ratchet in `./go ci` holds the debt and
only lets it go down. Its §6 named `gates/` as a later slice. The first
outside feedback (2026-11-06) named the shell as a weak spot, and on
2026-11-13 the owner asked for less shell and mostly Python.

Measured on 2026-11-13 over tracked files: 31,175 lines of `.sh`
(`ci/` 17,043, `adapters/` 4,730, `gates/` 4,074, `core/` 2,107) and
33,035 of Python. `gates/` held 18 files and 2,670 code lines of shell
(non-blank, not a comment), 916 lines of Python (the harness suite's
stub and probe, which run inside containers). What the shell held,
besides wrappers: two Python programs inside heredocs (`mutation.sh`,
`risk.sh`), `jq` filters over adapter output, an advisory diff with
`comm`, and four port conformance suites (`statestore`, `eventbus`,
`codehost`, `delivery`) written as `sh` sequences of verb calls and
checks. None of it had a unit test; the self gate (ADR 0049) mutates and
scans `core/` only, so it saw none of it.

## Decision

1. **`gates/` joins `core/` under ADR 0052.** What stays shell is what
   is a contract or the host: the gate wrapper, which sources `ci/lib.sh`
   and prints the one `GO`/`NO-GO` line (CLAUDE.md, "Contratto di output
   dei gate"); the glue that runs other processes in order
   (`require_range`, `effective_policy`, `core/toolchain.sh`); adapter
   verbs (ADR 0024); and the host entry points, `./go` and `lights-out`,
   because the host has only podman, git and a POSIX shell (CLAUDE.md,
   "Toolchain nel container"). Everything else in a gate (parsing,
   decisions, a suite's cases, JSON) is Python.
2. **The logic lives in a package, `core/gates/`**, one module per gate,
   standard library only, run as `python3 -m core.gates.<x>` from the
   repository root, where every gate already runs (it sources `ci/lib.sh`
   by a relative path). Under `core/` because the self gate's
   `MUTATION_CMD` and `SAST_CMD` scope is `core/` (ADR 0049): this is
   what puts the gates' logic under mutation and bandit. A package of its
   own, not `core/*.py`, because `pyproject.toml` ships the top level of
   `core/` as the `lights-out-gates` wheel (ADR 0061), the light tier;
   these modules need an engine, a plane or a code host and stay out of
   it. Tests in `core/tests/test_gates_<x>.py`, `unittest`, written from
   the gate's header and the ADRs it cites, never by translating the
   shell.
   - `core/gates/__init__.py` holds the two things every module shares,
     and nothing else: `NoGo(reason, *details)` and `main(judge)`, which
     prints the verdict (a GO detail, or the reason and then one detail a
     line) and returns 0 or 1; and `proc(argv, ...)`, the package's one
     process call, an argument list, never a shell line, excused for
     bandit (B404, B603, B607) on that line and the import with its
     reason, as `core/tower.py`'s `sh()` is (ADR 0052 §3). A second
     process call elsewhere in the package is a finding again.
   - A suite drives its port through a `verb` callable it is given; the
     default runs `sh adapters/<name>/<verb>.sh` through `proc`. The
     tests hand it a fake port in Python, broken one behaviour at a time,
     so a suite is proved to fail without an engine or a subprocess.
3. **The wrapper is `verdict`**, one function added to `ci/lib.sh`:
   `verdict MODULE [ARG...]` runs `python3 -m MODULE ARG...`; exit 0 is
   `go`, or `go_with` the first stdout line when there is one; exit 1 is
   `nogo` with the first line as the reason and each further line as a
   detail (so `$NOGO_DETAILS` still gets them, ADR 0038 §5); any other
   exit, or a 1 with nothing on stdout (an uncaught exception), is a
   NO-GO naming the module. A gate's `.sh` keeps its path, arguments,
   environment, the `CONFORMANCE` guard and `require_range` first (what
   a cold `ci/contract.sh` run sees, ADR 0026 §4, ADR 0015 §2), then
   calls `verdict`. The guards stay shell so that the cold run starts no
   Python.
4. **A gate that runs the workload's command** (`sast`, `mutation`,
   `test-proof`) still has its toolchain checked by the wrapper
   (`toolchain_preflight`), and its module runs the command through
   `sh core/toolchain-run.sh CMD`: an entry point of a few lines that
   sources `core/toolchain.sh` and calls `run_in_toolchain`, its exit
   CMD's or 125, a contract error a line on stderr and 125, never a
   contract line on stdout. `core/toolchain.sh` stays shell, on
   ADR 0052's debt list, its own slice.
5. **The ratchet, `ci/shell-boundary.sh`, scans `core/` and `gates/`**
   with ADR 0052 §4's rule unchanged: at most **30 code lines** per shell
   file (provenance: the owner's decision of 2026-11-06, ADR 0052 §4;
   checked again 2026-11-13: every wrapper this slice leaves is 7 to 26
   code lines), files over it named with their exact count, NO-GO when a
   listed file grows, shrinks without its entry lowered, or is gone, and
   when an unlisted file is over. The check's own proof on a temp tree
   gains a planted `gates/` file over the limit and a `gates/` entry
   raised, so it is shown to fail in the new directory too.
6. **This slice** moves `production-readiness`, `deps`, `sast`,
   `mutation`, `test-proof`, `risk` and the four port suites
   (`statestore`, `eventbus`, `codehost`, `delivery`). Callers do not
   change: same paths, arguments, environment, stdout line, files in
   `$GATES_OUT`, and the stderr lines the `ci/` suites read. `spec`,
   `test` and `test-weakening` were already under 30. The harness suite,
   `gates/harness-conformance.sh` and `gates/harness-conformance/proof.sh`
   (693 and 738 code lines on 2026-11-13, a measurement), stays on the
   debt list with its exact count: it drives compose, a scripted model,
   the egress proxy and a made-up harness, and only `./go
   harness-conformance` on a real engine proves a rewrite of it, a slice
   of its own.

## Alternatives rejected

- **Python in `gates/` beside the wrapper.** Outside the self gate's
  mutation and SAST scope (`core/`), which is half of why ADR 0052 moved
  logic at all; widening that scope to `gates/` would also mutate the
  harness suite's stub and probe, which run in containers and have no
  unit tests.
- **The modules at the top of `core/`.** They would ship in the
  `lights-out-gates` wheel, whose promise is the gates that need only git
  and Python (ADR 0061); a conformance suite for a code host is not one.
- **Each wrapper splitting the module's stdout itself**, as
  `test-weakening.sh` did. Ten copies of the same twelve lines, each a
  place to get the contract wrong; one function in the library every
  gate already sources.
- **Rewriting `core/toolchain.sh` in Python in the same change.** It is
  sourced by `gates/test.sh` and `core/init.sh` too and has its own
  engine paths (compose, throwaway image); a separate slice keeps this
  one provable by `./go ci` and `./go demo`.
- **The harness suite in this slice.** 1,431 code lines whose only proof
  is a full engine run per harness; moved without that run it would be a
  rewrite trusted on faith, the opposite of this ADR.

## Consequences

- The gates' rules have unit tests and are mutated and scanned by the
  self gate on every push (ADR 0049); a rule a test does not reach is a
  surviving mutant on the change that wrote it.
- `ci/lib.sh` gains `verdict`; `core/` gains `core/gates/` and
  `core/toolchain-run.sh`.
- The cold `ci/` suites that build a tree of symlinks to run a gate from
  (`ci/store-bus.sh`) link `core/` too.
- A change to a harness suite file must keep or lower its count and
  update the entry when it lowers it, as for `core/`'s debt.
- The numbers before and after this slice are in the M51 handoff.

## Golden-rule check

`./go demo` runs the gates (`demo-gates` and the tower's CI step) through
the same `gates/*.sh` paths; `python3` is in the workbench and gates
images the demo already builds. No key, no account, no new image layer.
