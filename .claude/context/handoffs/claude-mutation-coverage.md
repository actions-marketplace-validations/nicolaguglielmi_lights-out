# Handoff: claude/mutation-coverage (ADR 0076, test selection in the python mutation runner)

Cut from origin/fix/mutation-shards (main did not contain it yet), rebased onto its tip
0213078. Not merged, not tagged: the coordinator merges.

## What landed
- docs/adr/0076-a-mutant-runs-the-tests-that-reach-it.md: decision, score argument, measurement,
  alternatives (module-to-test mapping, pytest-testmon, coverage's test_function contexts,
  run-whole for never-executed lines, a pytest plugin, deferred). ADR 0015's status says it is amended.
- stacks/python/tests/test_mutation_select.py, written from the ADR before the code.
- stacks/python/runners/: hook/sitecustomize.py (per-test coverage in the clean run; a loader
  filter in a mutant's run), select.py (map builder; cosmic-ray's test command), mutation.sh
  (MUTATION_SELECT on|off, fallbacks, tally line), coverage==7.17.0 in pyproject and uv.lock.
  Copied byte for byte to .lights-out/runners/ (ci/init.sh g-self).
- docs/use-on-your-repo.md MUTATION_CMD row; ci/core-tests.sh comment.

## Measured (provenance in the ADR)
core/mcp.py + core/__main__.py + core/risk.py, 4 shards, judge-653d29f image:
3,467 s before (bf618fa runner), 251 s after; same score line (558/409/149, 0.7330), same 149
survivors line for line. 38 mutants ran no test, 509 a selection, 11 the whole suite.
Raw outputs: /Users/nicola/Dev/lights-out/.crew/mutsel/{old,new}.{out,err}, times.txt.

## Things to know
- The runner is the base's in self (ADR 0033): the speedup reaches the pushes judged from a base
  that carries this branch.
- Selection only applies to unittest.TestCase suites (pytest collects those too); plain pytest
  functions run the whole suite. A pytest plugin is the deferred follow-up.
- The clean run is instrumented: 50.5 s against 22.3 s on core, so the timeout grows with it.
- cosmic-ray runs the test command through shlex.split, not a shell; select.py does the same.
