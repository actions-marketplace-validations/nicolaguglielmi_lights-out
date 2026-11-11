# Handoff: M24 phase C, five production-code tickets on tenacity, live on Anthropic, 2026-11-11

This file: `docs/plans/m24-phase-c-handoff.md`, because `.claude/` could not be written from this session; its place is `.claude/context/handoffs/claude-m24-phase-c.md`.

Branch `claude/m24-phase-c`, cut from dee4e34. Pushed; not merged, no PR, nothing tagged. Nothing forked,
nothing pushed outside this repository and the local plane's Gitea, no project contacted (tenacity's issue
tracker was only read). Live model calls on Anthropic only (`claude-code`, `claude-sonnet-5-5`), as the owner
authorized for phase B; no Gemini or OpenAI call.

## The short version

- **Five tickets that change code under `tenacity/`**, each an open upstream bug reproduced at 01db331, each
  `GO: spec`, each proven before any model call: a test written to its criteria fails on the base
  (`GO: test-proof`), and a reference fix within the perimeter passes the whole suite.
- **Five merged PRs, five of five, no human touching the code.** Three at attempt 1, two at attempt 2 after
  `NO-GO: mutation` sent them back. `test-proof` judged every attempt that reached it; `mutation` scored real
  mutants on every final attempt (1 to 4 each, every one killed) and refused two first attempts.
- **The mutation gate could not see production code until this session.** Phase B's `mutation` and `test-proof` passed by absence
  because the tickets were tests-only. The first proof here found that on tenacity, `mutation` would have passed
  by absence on production code too: the contract's `VAR=value` test command made cosmic-ray mark every mutant
  incompetent, and the scorer dropped them. Fixed in lights-out (093b858, test first) and in tenacity's contract
  (eb254b1) before the first live ticket.
- **§14's criterion**: phase B 5/5, phase C 5/5, together 10/10 mergeable without a human on the code. The
  criterion says the thesis would be weaker than expected if two tickets in three failed; none did. Section 5
  says what that does and does not cover.
- **Cost**: phase C 554,218 tokens, at most $1.26 at list price; with phase B, 801,933 tokens, at most $1.83.

## 1. The tickets (in the clone's `.lights-out/tickets/`, commit 71933b5)

Chosen from tenacity's open issues on 2026-11-11. Each has open, unmerged upstream PRs. The agents could not read them: their egress is
the provider and PyPI only. Each bug was reproduced at 01db331 with a script before any
ticket was written.

| Ticket | Upstream | Perimeter | The bug at 01db331 |
|---|---|---|---|
| tenacity-06 | #710 | `tenacity/wait.py`, `tests/test_tenacity.py` | `wait_exponential(multiplier=0.0, max=60)` at attempt 1025 returns 60.0 (overflow handler), not 0 |
| tenacity-07 | #748 | `tenacity/wait.py`, `tests/test_tenacity.py` | `sum()` of 1000 `wait_fixed(1)` raises `RecursionError` |
| tenacity-08 | #529 | `tenacity/retry.py`, `tests/test_asyncio.py` | `retry_if_not_exception_type(ValueError)` retries `asyncio.CancelledError` 3 times, ends in `RetryError` |
| tenacity-09 | #766 | `tenacity/asyncio/__init__.py`, `tests/test_asyncio.py` | one `AsyncRetrying` iterated by two coroutines under `gather`: `['a', None]` (deterministic with `sleep(0)`) |
| tenacity-10 | #701, its reentrant case | `tenacity/__init__.py`, `tests/test_tenacity.py` | a `@retry` function calling itself once per attempt leaves `statistics["attempt_number"]` at 1, not 3 |

None was dropped or rewritten for `test-proof`. I proved each one before any model call, in `.crew/proof` (a clone of this
branch) on a scratch clone `/Users/nicola/Dev/m24/tenacity-c` with one reference branch per ticket (test plus
fix, never shown to a worker):

- `sh gates/spec.sh` on each ticket: `GO: spec` ×5.
- `./go gates BASE=01db331 HEAD=origin/ref-NN GATES=test-proof`: `GO: test-proof — in workbench, the changed
  tests fail on the base 01db331` ×5, each failing on exactly the intended test.
- The whole gate set on each reference, with the attached clone checked out at the head, on the corrected contract
  (`base-c2` = 71933b5 + the scorer + `MUTATION_CMD`): 07, 08 and 10 `GO: gates — risk low, auto-merge` (mutation
  3/3, 2/2, 14/18); 09 GO with no mutable operator on its lines (`total 0`, nothing incompetent); **06 `NO-GO:
  mutation` 9/12 (0.750 < 0.769)** on my own reference fix. These were the same three survivors the worker's first attempt
  then got. The gates decide, not the reference.

## 2. The lights-out bug the first proof exposed, fixed (093b858)

Phase A's handoff left open whether cosmic-ray accepts `SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0 uv run …` as
its test command. It does not. cosmic-ray 8.7.0 runs it as `Popen(shlex.split(command))`, with no shell
(`cosmic_ray/testing.py`), so every mutant came back `incompetent` with the worker outcome `normal`. Each check after that passed it on:

- `cosmic-ray baseline` fails only on `killed` (`cosmic_ray/cli.py`), so it passed.
- The runner's own clean run uses `sh -c`, so it passed too.
- `score.py` left every incompetent mutant out of the population and printed `{"total": 0}`.
- The gate said `GO: mutation` by absence of subject, on a real production change.

- Before: `./go gates BASE=01db331 HEAD=origin/ref-06 GATES=mutation` → `GO: mutation — in workbench`,
  `score: 1781 mutant(s) excluded`.
- `stacks/python/tests/test_score.py` (first written as `core/tests/test_python_score.py`; moved because
  `ci/app-free.sh` keeps core/ from naming the contract directory), written from cosmic-ray 8.7.0's two incompetent sources and ADR 0042 §1,
  black box over the four python copies of the scorer: 8 failures before the fix, OK after.
- The fix: a result `incompetent` with worker outcome `normal` makes the scorer print no score and exit 1,
  naming the cause. A result `incompetent` with `exception` (the mutation could not be applied) stays out of the
  population. The same code is in `stacks/python/runners/score.py`, `.lights-out/runners/score.py`,
  `workloads/minimal/tests/mutation/score.py` and `app/backend/tests/mutation/score.py`. ADR 0042 is amended
  (2026-11-11), and `docs/use-on-your-repo.md` says to put a variable before the runner.
- After, with the new scorer alone in tenacity's base (`base-c1`): `NO-GO: mutation — in workbench: mutation run failed
  before scoring (baseline or tooling error)`, stderr `cosmic-ray could not run the test command for 12
  mutant(s)`. With the variable before the runner (`base-c2`): 12 real mutants, 9 killed.
- tenacity's contract (eb254b1, human, contract only): `MUTATION_CMD=SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0 sh
  .lights-out/runners/mutation.sh tenacity "uv run --locked pytest tests -q -x -p no:cacheprovider"`, and the
  runners' `score.py` copied from 093b858.

## 3. Phase C: the five live runs

The command was `sh /tmp/m24c/run-ticket.sh <id>`, which runs `PROFILE=l1 ./go request TICKET=<id> MODEL_PROVIDER=anthropic
MODEL=claude-sonnet-5-5 AGENT_HARNESS=claude-code` from `.crew/full` (tenacity attached). `ANTHROPIC_API_KEY` was
read into the environment from `/Users/nicola/Dev/lights-out/.env`, never printed or written.

- The plane: `./go up APP_PORT=9000` from `.crew/plane` (a non-attached clone of this branch at 093b858). It took 147 s and was up from 17:15 to 17:53 UTC.
- `MAP_BRIEF=off`, the profile's default, as in phase B.
- Order 06, 08, 07, 09, 10. Each was merged and brought home before the next: fetch Gitea `main`, fast-forward the clone, `./go detach` to drop the untracked docs ticket, `./go attach`.

| Ticket | PR | Attempts | Gate lines, attempt 1 | Gate lines, attempt 2 | Mutation (final) | Merged | dev-worker turns, tokens (in / out) | product | Cost ≤ |
|---|---|---|---|---|---|---|---|---|---|
| tenacity-06 | #1 | 2 | risk, secrets, test-weakening, deps, sast, test GO; **`NO-GO: mutation — 9/12 (0.750 < 0.769)`** (survivors `wait.py:229` `==`→`<=`, `:230` ×2 `NumberReplacer`) | all eight GO; `test-proof — the changed tests fail on the base eb254b1` | 4/4 | 373844c | 8, 88,262 (85,045 / 3,217) | 4,524 | $0.214 |
| tenacity-08 | #2 | 1 | all eight GO; `test-proof — … fail on the base 373844c` | — | 2/2 | 88841bd | 4, 43,321 (41,454 / 1,867) | 4,632 | $0.114 |
| tenacity-07 | #3 | 1 | all eight GO; `test-proof — … fail on the base 88841bd` | — | 3/3 | e27de33 | 6, 57,815 (55,698 / 2,117) | 4,216 | $0.143 |
| tenacity-09 | #4 | 1 | all eight GO; `test-proof — … fail on the base e27de33` | — | 1/1 | 9709c38 | 12, 191,758 (187,194 / 4,564) | 5,236 | $0.435 |
| tenacity-10 | #5 | 2 | six GO; **`NO-GO: mutation — 10/14 (0.714 < 0.769)`** (survivors `__init__.py:405` `>`→`!=` and `NumberReplacer`, `:412`, `:416`) | all eight GO; `test-proof — … fail on the base 9709c38` | 4/4 | 4831978 | 13, 149,054 (143,926 / 5,128) | 5,400 | $0.356 |

- Every ci step ran in workbench (isolated). Every risk was `low, auto-merge`: the production diffs were 2 to 17
  lines, under `RISK_SIZE_MEDIUM_LINES=200`. So no `test-reviewer` and no human gate ran. `mainline` was GO after
  each merge. `release` fails after `main-green` by construction, because a library publishes no image, as in phase B;
  `./go request` therefore exits 2 every time.
- An attempt with `NO-GO: mutation` has no test-proof line: `make gates` stops at the first NO-GO,
  and mutation runs before test-proof.
- The GO line of `mutation` does not print its counts. The "Mutation (final)" column and the attempt-1 counts
  were measured again afterwards on the same heads, in `.crew/proof`, with the same survivors the tower saw.
- Tokens: `run.json` and the tower document's `tasks` give input and output only. The cost uses Sonnet 5.5's list
  price as read on 2026-11-10 (phase A handoff: $2/M in, $10/M out) with every input token uncached, so it is an upper bound.
  Phase C: 534,903 in, 19,315 out, 554,218 tokens, **≤ $1.26**. Phase B: 247,715 tokens, ≤ $0.57. Both:
  801,933 tokens, ≤ $1.83. The Anthropic console has the billed figure.

What the PRs did, as I read them (no gate read them):

- **06**: attempt 1 added `if self.multiplier == 0: return max(max(0, self.min), min(0, self.max))`. Its
  `min(0, self.max)` is dead for a non-negative `max`, hence two equivalent survivors. Attempt 2 wrote `if not
  self.multiplier: return max(0, self.min)` and added two cases (negative `min`, `min` at attempt 1). Its PR body
  says the new check "has no comparison operator or literal to mutate".
- **07**: a `_flat_combine` helper splices in the operands of a plain `wait_combine`, and leaves subclasses nested. Its
  `__radd__` now orders `(other, self)` where it was `(self, other)`. The body's "evaluation order unchanged" is
  true only for `__add__`. This is harmless for a sum, and no gate saw it. The worker reported one flaky run of
  `tests/test_asyncio.py::TestContextManager::test_sleeps`, unrelated, and did not touch it.
- **08**: `CancelledError` is never retried. Two tests, the second criterion included.
- **09**: `__aiter__` iterates a `copy()` that shares the original's statistics dict, on both the enabled and disabled paths.
  This is the same design as my reference.
- **10**: a per-wrapper `threading.local` flag, so a reentrant call gets a private statistics dict. Attempt 2
  replaced an integer depth (only ever 0 or 1) with a boolean "to remove the comparison and numeric literals the
  mutation gate flagged", and added a test that a failed call resets the flag.

## 4. Findings

1. **Fixed**: the scorer's false GO (section 2).
2. **The reworks answered the mutation gate partly by shrinking what it mutates**: 12 → 4 mutants on 06, 14 → 4
   on 10. As I read them, both simplifications are sound (dead code, and a counter that was really a flag), and both reworks added a
   test. The line-scoped gate cannot tell a sound simplification from a shape chosen to dodge it, and a
   change with no mutable operator passes by absence (09's reference). Two questions for the owner: should the GO line
   print `killed/total` (the tower stores no count for a GO today), and should a review look at
   reworks that cut the mutant count?
3. **`./go gates BASE=<a> HEAD=<b>` from a clone runs `test`, `sast` and `mutation` on the attached clone's
   working tree, not on `<b>`** (`core/toolchain.sh` `run_in_toolchain`, workbench form: `cd "$WORKLOAD"`).
   Only `test-proof` builds its own worktree. The tower (`core/steps/ci.sh`: a worktree at the head,
   `TOOLCHAIN_ISOLATE=1`), `demo-gates` and the image's wrapper (`package/entrypoint.sh` checks out `HEAD`) are
   not affected. Reproduced: my first proof run judged five references with one tree. Not fixed here. The
   follow-up: refuse, or judge a worktree of `HEAD`, when `HEAD` is not the checked-out commit.
4. **Phase A's follow-ups came back**: the merge step's docs ticket (`0001.md`, which counts the tickets as
   pages citing the merged files) blocked every re-attach until `./go detach`, and `release` fails on a library.
5. Once, `./go gates` in `.crew/proof` failed in 1 s with `make: No rule to make target
   '.attached/workload.env'` right after a `git checkout` of the attached clone. It did not recur on the same
   heads. Not investigated.

## 5. §14's criterion, said plainly

The criterion (§14, point 2): the harness thesis is weaker than expected if at least two tickets in three do not
produce a mergeable PR without a human touching the code.

- **Phase B alone**: 5/5. The tickets were tests-only, so `mutation` and `test-proof` passed by absence. `mutation`
  would have passed by absence on code too (section 2).
- **Phase C alone**: 5/5, two of them through the rework loop, with `test-proof` and `mutation` judging for
  real. This is the case that matters most: the gates rejected two first attempts and the agent fixed them alone.
- **Together**: 10/10. The criterion is met; on this evidence the thesis is not weaker than expected.
- **What it does not show**:
  - One provider (Anthropic, Sonnet 5.5), not three.
  - Every ticket was low risk and auto-merged, so neither `test-reviewer` nor the human gate ran.
  - The tickets were small (2–17 production lines). I wrote them with exact reproductions and a two-file perimeter, and checked each was solvable before the run.
  - The upstream issues are public and could be in the model's training data.
  - The human contract commits come before the tickets and touch no code under `tenacity/`: two prep commits and three contract commits in phase A, 71933b5 and eb254b1 here.
  - M28's map-in-the-brief comparison was not run.

## The owner's decisions

1. **Publishing the verdicts**: the ten PRs and their gate lines in the diary, naming tenacity and the human
   commits. Whether any of the five fixes goes upstream is a separate act, under tenacity's review; each issue
   already has open PRs from others.
2. **A public fork** of the clone on GitHub. No money, but a public act that names tenacity.
3. **The third provider**: M24 asks for every ticket on three providers. Gemini spend is not authorized and the
   OpenAI key is absent. Phase C on Anthropic cost at most $1.26.
4. Finding 2 (counts in the GO line, a look at reworks that cut mutants) and finding 3 (the `gates` working
   tree), each a change of its own.

## Where things are

- Clone `/Users/nicola/Dev/m24/tenacity`, branch `lights-out` at 4831978 (71933b5 tickets, eb254b1 contract,
  five merges). Scratch clone with the reference fixes: `/Users/nicola/Dev/m24/tenacity-c`, local only.
- Checkouts of this branch, moved after the runs from this clone's `.crew/` to `/Users/nicola/Dev/m24/m24c-crew/`
  (inside the clone their caches and the plane's cosign key made `./go ci`'s working-tree secret scan NO-GO):
  - `proof`, attached to the scratch clone.
  - `full`, tenacity attached. The tower state is in `full/.crew/state.sqlite`, and each ticket's last `run.json` is in `full/.crew/<id>/out/`.
  - `plane`, the plane's.
- Logs: `/tmp/m24c/` (run logs, gate outputs, the docs ticket after each merge). Temporary.
- The plane: down since 17:53 UTC on 2026-11-11, both podman connections empty.

## Proofs

- The scorer test: 8 failures before 093b858, OK after; now `python3 -m unittest discover -s
  stacks/python/tests`, run by `ci/core-tests.sh`.
- The gates on the references and the scorer before and after the fix: sections 1 and 2.
- The runs: section 3, from the tower documents and `./go network TICKET=<id>`.
- `./go ci` and the six workflows: recorded in the commit after this handoff's.
