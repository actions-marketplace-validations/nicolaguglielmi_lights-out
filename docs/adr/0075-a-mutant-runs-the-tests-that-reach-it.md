# ADR 0075 — A mutant runs the tests that reach it: per-test coverage from the clean run selects them, the whole suite when coverage cannot say

- Status: proposed (amends ADR 0015 §3 [the test command runs whole for every mutant]; keeps ADR 0074's amendment [the shards])
- Date: 2026-11-11

## Context

Every mutant of the python runner (`stacks/python/runners/mutation.sh`,
copied to `.lights-out/runners/`) runs the repository's whole test
command. On lights-out's own `core/` that is 947 tests, about 37 s clean,
about 27 s per mutant with `-f` (measurement, 2026-11-11, the 774 pending
mutants of the unjudged integration range, ADR 0074's amendment). A
killed mutant stops at the first failing test, but a surviving one pays
the whole suite, and so does every mutant on a line that only one slow
module reaches. The shards divide the wall clock by the processors; they
do not cut what one mutant costs. The owner, 2026-11-11: release times
are far too long.

A mutant can only be killed by a test that executes its line (or observes
its effect, see Consequences). The clean run the runner already does
before `cosmic-ray init` can say which tests those are.

## Decision

1. **The clean run records per-test coverage.** The runner puts
   `runners/hook/` first on `PYTHONPATH` for the clean run. Its
   `sitecustomize.py` starts coverage.py (pinned in the runners' own
   lockfile, imported from the runners' environment and dropped from
   `sys.path` again) in every Python process the suite starts, and in the
   process that runs the tests it switches coverage.py's context to
   `unittest.TestCase.id()` around each `TestCase.run`. Outside a test
   the context is `-`. Processes the tests spawn inherit the running
   test's context: the hook puts itself back on the `PYTHONPATH` of a
   `subprocess.Popen` whose `env` dropped it, because tests that drive
   the code through a subprocess set their own `PYTHONPATH` (lights-out's
   `test_mcp.py`, `test_light.py` and `test_map.py` do). A test running
   inside another test keeps the outer one's context.
2. **A mutant runs the tests that executed its statement.** The runner
   gives cosmic-ray `python3 runners/select.py run` as the test command.
   The wrapper finds the mutated file by comparing the package with a
   copy taken after the clean run, the changed lines by a diff, and widens
   each line to its statement: the innermost `ast.stmt` holding it, for a
   compound statement its header lines (decorators, `def`, `if`, `else:`)
   without the bodies. Then:
   - a statement line executed outside any test (`-`: import time, a
     `setUpClass`, a process with no test around it): the whole suite;
   - executed by some tests: those tests only, through the hook, which
     filters `unittest.TestLoader.getTestCaseNames` to their ids in the
     process that runs the tests and nowhere else;
   - executed by nothing: no test can reach the mutant, so nothing runs
     and the mutant survives, as it would under the whole suite;
   - a line outside every statement, or no mutated file found (the
     baseline): the whole suite.
   The test command is run the way cosmic-ray runs it, split by `shlex`
   and executed, never through a shell.
3. **Coverage missing, the whole suite.** No test context recorded (the
   suite is not `unittest.TestCase` based, or runs under `python -S` or
   `-I`, or
   coverage.py does not import in its interpreter), or a clean run that
   passes only without the hook: every mutant runs the whole suite, as
   before this ADR, and stderr says so in one line.
   `MUTATION_SELECT=off` asks for the same; any other value than unset,
   `on` or `off` is refused before any tool runs.
4. **Shards unchanged.** Each shard's copy of the tree compares itself
   with the same pristine copy by relative path, so the selection works
   in every shard; the score and survivors stay a single exec's.
5. **Accounting.** The runner prints on stderr how many mutants ran no
   test, a selection, the whole suite.

The timeout keeps ADR 0015 §3's rule, 10 x the clean run measured at
every run; the clean run is now the instrumented one, so the timeout
grows by coverage.py's overhead and only a mutant that loops pays it.

## The score

Selection runs a subset of the tests that run today. A mutant it reports
killed was killed by a test the whole suite also runs, so **the score
cannot rise**: selection never forges a kill. It can fall only when the
test that kills a mutant under the whole suite did not execute the
mutant's statement in the clean run: a test that reads a cache, a module
global or a file another test filled, or a process coverage.py did not
see (started with `-I`/`-E`, through `os.exec*` or `os.posix_spawn`
with a scrubbed environment, or ended by `os._exit`). A fall is a NO-GO
that should not have been, never a GO that should not have been.

## Measured

(filled in by the measurement commit)

## Tests, from the spec

`stacks/python/tests/test_mutation_select.py`, on a package made by the
test, run through the real runner with cosmic-ray:

- with selection on, the score line and the survivors equal
  `MUTATION_SELECT=off`'s, with one and with three shards;
- a function no test calls: its mutants are counted as running no test
  and survive;
- a function only a subprocess reaches, the subprocess started with its
  own `PYTHONPATH`: its mutants are killed, as with the whole suite;
- a module constant read by a test: its mutants run the whole suite;
- with selection, fewer test runs than with the whole suite (the tests
  log each run);
- `python3 -S -m unittest` (no site, so no hook): no per-test coverage,
  the whole suite, the same score;
- `MUTATION_SELECT=maybe` is refused, nothing on stdout;
- the package is left as it was.

## Alternatives rejected

- **Module-to-test name mapping** (`core/x.py` → `core/tests/test_x.py`,
  or the project map's static `tests` edges, ADR 0054). Static imports
  miss what tests drive through a subprocess: the map names no test for
  `core/mcp.py` or `core/__main__.py`, which `test_mcp.py` runs through
  `python -m core`, so all 411 mutants of the range that took 168 min
  (ADR 0074) would have run no test and survived. A name convention is
  the same guess with less information.
- **pytest-testmon.** It selects tests affected by a change, for pytest
  only, from its own database kept in the repository's environment:
  lights-out's own suite is `unittest`, the runner's tools never go into
  the repository's environment (ADR 0042 §6), and testmon's unit is a
  changed block, not a mutant, so it would need one database update per
  mutant.
- **coverage.py's `dynamic_context = test_function`.** It names the
  test function by its frame, which a subprocess cannot know and a
  `setUp` attributes to the test; the hook's own context per
  `TestCase.run`, passed to children through the environment, can.
- **Marking every mutant on a never-executed line run-whole.** Safe
  against blind spots, but those mutants are most of the survivors and
  each pays the whole suite: the cost this ADR removes. The test with a
  subprocess that drops the hook's path guards the blind spot that
  lights-out's own suite has.
- **A pytest plugin for pytest-style test functions.** Under pytest, a
  `unittest.TestCase` class is recorded and filtered by the same hook
  (pytest collects it through `getTestCaseNames`); a plain test function
  runs in context `-`, so the lines it alone reaches run the whole suite.
  A plugin would extend selection to them; deferred until a measured
  attached repository needs it, since nothing in the image runs pytest to
  test it.

## Consequences

- Attached repositories whose suites are `unittest.TestCase` based get
  the speedup with no change to their contract; pytest function suites
  run as before.
- `runners/` gains `select.py` and `hook/sitecustomize.py`, and the
  lockfile coverage.py; `./go init` copies them with the rest.
- A repository's own `sitecustomize` is shadowed while the runner runs
  the suite.
- The runner is the base's in `self` (ADR 0033): the speedup reaches
  the first push judged from a base that carries this ADR.

## Golden-rule check

`./go demo` does not run the python runner; nothing in the demo path
changes, no account, no key.
