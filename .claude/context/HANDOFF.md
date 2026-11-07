# Handoff: M27, tests that prove something and tickets that wait (ADR 0053), 2026-11-07, branch `claude/m27-test-proof-f96c5b`

Not merged: the parent session decides landing after the five workflows are green on the pushed head. Rebased onto main 9fcf23a (M28 landed); `./go ci` and the counts below are on the rebased head, `demo-gates` on the pre-rebase head bc9782d (M28 touches no gate or fixture).

## Acceptance

Local, from a clean clone of the branch (`.crew/m27`, `git clone --no-hardlinks`):

```
./go ci          → GO: ci (37 checks, `assign` new; unit tests 298 → 368, on top of M28)
./go demo-gates  → GO: demo-gates, 1619 s on the shared 4 GiB VM
  assertion-removed:   NO-GO: gates — test-weakening: NO-GO: test-weakening — 1 test file finding that no ## Removes tests in the ticket declares: app/backend/tests/test_meetups.py: loses 1 assertion; details on stderr
  failing-test:        NO-GO at test        (unchanged)
  fake-test:           NO-GO at mutation    (unchanged: 4/8, 0.500 < 0.666)
  honest-fix:          GO, risk low, auto-merge (test-proof ran: its test fails on the base)
  migration:           GO, risk high, review (unchanged)
  sast-finding:        NO-GO at sast        (unchanged)
  test-edited:         GO: gates — risk low, auto-merge, in compose:backend-test
  test-passes-on-base: NO-GO: gates — test-proof: NO-GO: test-proof — in compose:backend-test: the changed tests pass on the base … too, so they do not prove the change
  vulnerable-dep:      NO-GO at deps        (unchanged)
```

`./go demo` was not run locally: on 2026-11-07 the owner moved the engine-heavy acceptance to GitHub Actions (`engine-compat` runs `./go demo`, `gates` runs `./go demo-gates`, `seam` and `init` exercise the new gates on attached repositories) because four sessions share one VM, which stopped twice that evening. The demo's e2e PR (ticket 0001's replay) changes the client and adds two tests, so `test-proof` runs once more inside the demo: the 900 s budget is judged by `engine-compat`.

## What changed

- **ADR 0053.** `WORKLOAD_TEST_PATHS`, the twelfth key, names the tests; `ci/workloads.sh`, `core/init.py` (stack defaults with provenance), `ci/init.sh` and the four contracts carry it.
- **`gates/test-weakening.sh`** over `core/testdiff.py weakening`: per test file, deleted or renamed away, net lost assertions, net lost test definitions, net added skip/xfail/todo/only, Python and JavaScript patterns; a ticket's `## Removes tests` excuses its files; the tower's CI step passes the ticket as `GATES_TICKET`.
- **`gates/test-proof.sh`** over `core/testdiff.py subject`: the changed test files restored from HEAD onto a worktree of the base, `TEST_CMD` through `core/toolchain.sh`; exit 0 there is NO-GO. Absence: no test changed, only tests changed, empty-tree base. `GATES` order puts it after `mutation` so `fake-test` still proves mutation's NO-GO.
- **The `assign` step**: `core/assign.py` (perimeter lease in `perimeters/held`, held from `pr-opened` until `merged`), then on an attached repository `core/base-gates.sh` (`make gates GATES="sast test"` on the code host's HEAD, isolated, GO cached as `bases/<sha>`). A refusal is a failed attempt: the ticket stays `opened`, `./go resume` retries. `ci/assign.sh` proves both cold.
- **Three fixtures** in `app/fixtures/gates/`; docs (README, ARCHITECTURE, reference, tutorial, use-on-your-repo, ROADMAP) and the PLAN's M27 *Stato* note.

## Contradictions with docs/PLAN.md

- "Un ticket aperto" cannot mean `Status: open` in `tickets/`: nearly all of them are open and on `app/`, so every assign would wait. ADR 0053 §5 defines it as a ticket whose PR is open and unmerged.
- "Sulla head devono passare" is the `test` gate's verdict, not repeated by `test-proof` (it runs after `test`).
- The base check runs only `sast` and `test`: the other gates judge the diff, and running the whole `gates` on the last commit would charge the worker for someone else's commit.

## Found on the way

- `git clone .` from a worktree hard-links loose objects; inside the workbench git then hit `Permission denied` opening some of them and a fixture failed for that reason alone. Clone with `--no-hardlinks` for `.crew/` runs (worth a line in the worktree memory note).
- The lease document is read-modify-write: fine under `inproc` (one step at a time), a race under an orchestrator that runs two `assign`s at once (ADR 0053 consequences).

## First thing for the next milestone

M24 on an unknown repository: its attached contract needs `WORKLOAD_TEST_PATHS` (`./go init` drafts it), and its first ticket will meet the base check. If the repository's suite is red on main, `assign` waits by design; decide before the experiment whether to fix the base as ticket zero.

Clear the context before starting the next milestone.
