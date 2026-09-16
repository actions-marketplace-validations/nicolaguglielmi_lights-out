# ADR 0003 — `make demo` is a fixed stage list; missing stages are declared, not faked

- Status: accepted. Amended by ADR 0004: the entrypoint is `./go demo`, the stage list gains `engine-compat (M2)`, and the M0 timing estimate is replaced. Amended by ADR 0012 §5: `engine-compat` runs on the host before workbench starts, so the stage order is engine-compat, ci, up, smoke, verify, deploy, rollback, e2e. Amended by ADR 0019: `e2e` is real from M6; the `100%` stub re-dates to M7. Amended by ADR 0020: the `100%` stub is removed; `demo-launch` is not a stage.
- Date: 2026-09-14
- Milestone: M0

## Context

Two rules collide before M3. CLAUDE.md requires `make demo` green on a clean
container before every milestone is closed, starting at M0. The golden rule
requires `make demo` to reach an automatic canary rollback, which does not
exist until M3. And "no hidden mocks" forbids anything that looks like it
worked when it did not.

## Decision

`make demo` is a hardcoded, ordered list of stages written in full at M0,
each tagged with the milestone that owns it:

```
ci            M0   repo self-checks (ADR 0002)
up            M2   local plane in compose
deploy        M3   release to canary stage
verify        M3   verify/slo.promql against canary and stable
rollback      M3   automatic rollback on NO-GO
e2e           M6   ticket -> PR -> CI -> canary -> rollback
```

A stage that exists runs for real. A stage that does not yet exist prints
one line to stderr, `[demo] rollback: NOT YET (M3)`, and does not fail the
run. `make demo` exits 0 when every existing stage passed and at least one
stage exists. The README states the current milestone and which stages are
real at the top, next to the level table.

This is acceptable under "no hidden mocks" because nothing is simulated: no
fake rollback, no fake metrics, no green line for something that did not
run. The stub says what is missing and when it arrives, on every run.

The specific targets are different: `make demo-rollback` and `make e2e`
fail with exit 1 and a clear message until M3 and M6 respectively. Only
`demo` aggregates; the targets it will call must never pretend.

## Alternatives rejected

- `make demo` fails until M3: contradicts CLAUDE.md, which requires it green
  at M0, M1 and M2. It would also train everyone to ignore a red `demo`.
- `make demo` is just `make ci` until M3: same exit code, but hides the
  gap. Printing the full stage list is the honest version of the same thing.
- A `MILESTONE` counter that fails `demo` when a stub outlives its milestone:
  three lines, tempting, but the done-when criteria in the plan already
  require the stage to exist, and the parent session checks them. Not yet.
- Marking stubs as skipped tests in a test framework: adds a framework to a
  Makefile-only repo for one feature.

## Consequences

- A `NOT YET` line with exit 0 is the kind of thing that becomes permanent.
  The milestone tag on each stub is the only guard. If a stub is found past
  its milestone, that milestone is not closed, whatever the commit says.
- The stage list is a promise. Adding a stage later means a plan change and
  an ADR update, not a quiet edit.
- Until M3, "make demo green" tells a stranger the repo is coherent, not
  that the platform works. The README must say so in one line.

## Golden-rule check

At M0 a stranger gets `make demo` green in about two minutes (three small
image pulls) and a printed list of what is real. The rollback arrives at M3
and the README says so. Passes, with the caveat stated.
