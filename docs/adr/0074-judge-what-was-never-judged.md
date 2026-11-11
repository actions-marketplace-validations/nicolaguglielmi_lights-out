# ADR 0074 — Judge what was never judged: a push's range starts at its last green ancestor, every green check records its range, and mutation skips the lines a recorded green already judged

- Status: proposed (amends ADR 0049 §2 [the range of a push]; ADR 0015 §3 [which lines mutation mutates])
- Date: 2026-11-11

## Context

Run 42972832733 of `self`, the push of the merge 98f49e8 on
`fix/adr-still-header` (2026-11-11), took 168 min; a normal `self` run
takes 4 to 6 (42936682055: 5). In its `gates` job the self-checks took
4.6 min, the mutation gate 162 min 05 s, the rest about 2 (measure, the
job's step times). It judged HEAD^1..HEAD, 2099f7f..98f49e8: `core/mcp.py`
+330 lines, `core/__main__.py` +61, `core/map.py` +15. cosmic-ray 8.7.0
on that range, after the line, operator and pragma filters, has 412
mutants (299, 112, 1); the log says 6559 excluded, 90 survivors, GO. That
is 23.6 s per mutant, serial, each running the 735 tests of `core/tests`
(27.8 s clean on the runner). `-f` saves little: `test_mcp.py` sorts
after the slow modules. All measured today.

Those 168 min were the first judgement of `core/mcp.py`, not a second
one. `self` judges only HEAD^1..HEAD of a push. `core/mcp.py` came in
6436c3a, pushed with three more commits; only 9662227 got a run (range
56d92e0..9662227, no `core/` change). Commits with no run of their own: 8
of 12 on M39's branch, 3 of 5 on M17's, and the merge 2099f7f, pushed
with 98f49e8 (measure, the runs list). "Both branches were green" proved
their tips' last commit, nothing more.

The owner's rule (2026-11-11): a change that was never judged is judged;
nothing becomes GO because it was too slow to judge.

## Decision

1. **A push judges from its frontier, not from HEAD^1.** The base is the
   nearest first-parent ancestor of HEAD (HEAD^1 first) whose most recent
   `lights-out gates` check run posted by GitHub Actions (app slug
   `github-actions`), ignoring those whose record (§2) names another
   head, is `success`. Every commit a push brings is in its range, and a
   NO-GO commit no longer lets the next fix-up be judged alone. None
   within 100 first-parent commits: `NO-GO: gates — no green ancestor
   within 100 first-parent commits of <sha>`, never HEAD^1. 100 is a
   decision: one API call per commit, a tenth of the token's 1,000
   requests an hour per repository (external, GitHub's REST limits), and
   eight times M39's 12 commits, the longest branch here (measure). The
   way out is to push an older commit of the branch first. A green
   posted before this ADR records nothing and judged only HEAD^1..HEAD:
   it is trusted as a base exactly as today's rule trusts HEAD^1, no
   more. A pull request keeps the PR's base.
2. **Every check records what it judged.** The Action sets the check
   run's `external_id` to `<base>..<head>`, full shas. A check is a
   record of the commit it is posted on only if the recorded head is that
   commit: a pull request's run judges GitHub's merge commit, so its
   check on the PR's head is not one.
3. **Mutation does not re-mutate a judged tree.** For each merge on the
   first-parent path from the range's base to HEAD, HEAD included, walk
   the first parents of its second parent, from it and stopping before
   the merge-base with the first parent, to the nearest commit T whose
   most recent check is a green record (§2). T is a judged tree only if
   its record is sound: following the records' bases from T, one reaches
   an ancestor-or-self of the range's base before an unrecorded commit or
   100 steps. A grandfathered green is never sound on its own, so a
   branch that carried `core/mcp.py` unjudged under the old rule still
   gets it mutated at its merge. The gate mutates only the lines HEAD
   adds against the base and against every judged tree: the intersection
   of the `+` sides of `git diff -U0 <tree> HEAD`. A merge with no judged
   tree keeps today's diff; a side with one unrecorded commit over a
   sound green has that commit's lines mutated; a merge's own
   conflict-resolution lines match no tree and are mutated.
4. **JUDGED, the trees, flows as the base does.** The gates job's range
   step computes base and trees (`.github/range.sh`: git, gh, jq; the job
   already holds `checks: write`), passes them as the Action's `base` and
   new `judged` input (space-separated shas), the Action as `JUDGED=` to
   the wrapper only when non-empty, the wrapper and the entrypoint to
   `make gates`, and on to `gates/mutation.sh`. A JUDGED sha not in the
   checkout or not an ancestor of HEAD is a NO-GO. Like BASE, JUDGED is
   the caller's claim; the token never enters the container. The verdict
   says what was skipped: `GO: mutation — in <where>, <n> lines judged at
   <short shas>`, the trees and their line counts on stderr. Empty JUDGED
   is today's gate exactly.
5. **Only mutation narrows.** risk, secrets, test-weakening, deps, sast,
   test and test-proof keep base..HEAD: about 2 min together (measured
   above). A line deleted, or a test weakened, is still seen across the
   whole range; aligning lines by `git diff` is the approximation the
   changed-lines rule of ADR 0015 §3 already makes.

## What changes

`.github/range.sh` (new) and `self.yml`'s range step; `action.yml`
(`judged` input, `external_id` in the POST); the `lights-out` wrapper and
`package/entrypoint.sh` (accept JUDGED=); the Makefile's `gates`;
`gates/mutation.sh`. `plan.sh` is untouched: its job has no history.
The tests below are `ci/range.sh`, a self-check in `./go ci`.

## Tests, from the spec

- Frontier: picks the nearest green ancestor; skips a red one and one
  with no check; skips a green whose record names another head; NO-GO
  past 100; a pull request's base is untouched.
- Record: `external_id` is `<base>..<head>`; a check whose recorded head
  differs from its commit is not a record.
- Judged trees: a merge whose side tip is a sound record gives it; an
  unrecorded side gives none; the walk takes the side's nearest recorded
  ancestor; it stops before the merge-base; a record whose chain reaches
  a grandfathered green that is not an ancestor of the base is not sound.
- Mutation: a line equal to a judged tree's is not mutated; a merge's own
  conflict-resolution line is; a JUDGED sha missing or not an ancestor of
  HEAD is NO-GO; empty JUDGED gives today's lines on the same range.

## Alternatives rejected

- **Trust the tips: skip on a merge what both parents were judged on.**
  Unsound: the tips' greens judged one commit each, and 98f49e8 would
  have let `core/mcp.py` through never judged.
- **Base = the push's `before`.** It may be red, all zeros on a new
  branch, or not an ancestor after a force push.
- **Prove every commit of each side had its own run.** Sound, but
  multi-commit pushes are the norm here (8 of 12, 3 of 5): it would never
  hold, and 98f49e8 would still take 162 min.
- **Pick the tests from the map.** Its `tests` edges are static imports;
  `test_mcp.py` drives `core/mcp.py` and `core/__main__.py` through a
  subprocess, so 411 of the 412 mutants would have no test and survive: a
  false NO-GO. Never looser, useless here.
- **Killers first** (run first the tests that killed a mutant on that
  line): exact, but the runner gets an opaque test command. Deferred.
- **Mutants in parallel inside the runner:** exact and generic, but it
  divides a first judgement by the runner's cores at most. Deferred: that
  judgement is owed, and §1 moves it to the branch push that brings the
  code, where it no longer blocks the landing twice.
- **A time budget per gate, NO-GO past it.** Deferred, and no number:
  none has a provenance yet. Today a slow gate already fails closed (the
  job's 360-min default timeout, external, posts no check, so §1 judges
  the commit again), and a budget would make a large first judgement
  unlandable unless pushed in parts.

## Consequences

- The first judgement of a large `core/` change is still slow, about 160
  min at M39's size, now on the branch push that brings it. A merge of
  branches judged under this ADR costs the gates' fixed ~5 min plus its
  own conflict-resolution lines.
- Not faster at first: until records exist every merge mutates its whole
  diff, as today, and a push whose parent has no green check widens its
  range back to one that has. That is the debt the old rule left.
- A green check now waives mutation elsewhere. Who can post one can push
  here and could already edit `self.yml` (ADR 0049); the waiver is named
  in the line and in the check's summary.
- Merging a recorded branch into a base older than this ADR hands
  JUDGED= to an image that refuses it: a loud NO-GO, never a GO.
- One more decision number, 100, in `range.sh` with this ADR's reason.

## Measured after

- TODO: replay of 98f49e8 under this ADR: run id, total and mutation
  minutes.
- TODO: a merge of two branches judged under this ADR: run id, minutes.

## Golden-rule check

`./go demo` and `./go ci` are unchanged: the frontier and the trees live
in a GitHub-only job (ADR 0039); locally `lights-out gates` without
JUDGED= judges exactly as before, with no account and no key.

## Amendment 2026-11-11: a judge older than this ADR

The first push that brought this ADR onto the integration branch (38935b1)
was judged from a base whose image predates it: the Action, from HEAD,
passed `JUDGED=` to the base's entrypoint, which refused it as an unknown
argument (`NO-GO: gates`, run 43023293782). The judge is the base's by
design, so the workflow now passes no judged trees when the base's
`package/entrypoint.sh` does not take `JUDGED=`, and says so in a notice:
mutation covers the whole range, as before this ADR. Nothing is skipped
that the old rule would have judged; the speed comes once the base carries
this ADR.
