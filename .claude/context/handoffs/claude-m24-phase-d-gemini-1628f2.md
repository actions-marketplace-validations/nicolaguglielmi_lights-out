# Handoff: M24's Gemini leg, the ten tenacity tickets on `gemini-cli` and `gemini-3.8-flash`, 2026-11-14

Branch `claude/m24-phase-d-gemini-1628f2`: phase C (`claude/m24-phase-c`, cf1ee74) merged with `main` (bdc1943),
one lights-out fix, this handoff and the plan's note. Pushed; not merged, no PR. Nothing forked, nothing pushed
outside this repository and the local plane's Gitea, no project contacted. Live model calls on Gemini only, under
the owner's authorization of 2026-11-14 (at most $25 for this leg); no Anthropic or OpenAI call for the runs.

## The short version

- **Seven of ten merged, each at its first attempt, every gate GO; three stopped at the dev-worker's
  `TOKEN_BUDGET` with no PR, twice each.** Tests-only 4/5 (03, 05, 01, 02; 04 stopped), production 3/5 (06, 08,
  07; 09 and 10 stopped). On Anthropic the same tickets were 5/5 and 5/5.
- **§14's criterion holds on Gemini**: three failures in ten, under the two in three that would make the thesis
  weaker than expected. It holds by less than on Anthropic, and for a different reason than a gate: no Gemini PR
  was refused by any gate, and no rework ran. Every failure is the worker spending its whole token budget before
  opening a PR.
- **A lights-out bug stopped the first Gemini run, fixed here test first (a66e6df)**: the gemini-cli budget hook
  counted every streamed chunk of a model call, about six times the real use.
- **Spend**: the tower's ledger, which M50's budget reads, says $8.78. Five runs that stopped on budget are not
  in it. Every run at list price with every input token uncached: $20.88. At the cached-input price, about $3.58.
  All three are under the $25 cap; M50's budget never stopped anything. Google AI Studio has the billed figure.
- `self` was red on the first two pushes for a reason of topology, not code (section 6); green since 46f9644.

## 1. Setup

- Branch: cf1ee74 merged with bdc1943. Three conflicts: `ci/init.sh` keeps phase C's case (k) rule for the
  committed runners (it also accepts an uncommitted edit made to both copies, which main's simpler fix 8824c38
  refused) with main's `__pycache__` exclusion (6249bf3) and a fallback when there is no commit;
  `ci/core-tests.sh` takes main's line; the `MUTATION_CMD` row of `docs/use-on-your-repo.md` keeps both texts.
  `./go ci` GO from a clean clone (`.crew/m24d-ci`, 308 s) on f998ad4.
- Checkouts of this branch, outside the repository: `/Users/nicola/Dev/m24/m24d-crew/full` (tenacity attached,
  the tower), `.../plane` (`./go up APP_PORT=9000`, 85 s, up from 06:28 to 08:17 UTC). Logs in `.../logs`.
- Budget: `SPEND_BUDGET_TICKET_USD=5` and `SPEND_BUDGET_DAY_USD=25` in `full/policy/rework.env`, the file the tower
  reads (`core/spend.py`), with a provenance line; local, not committed.
- Command: `PROFILE=l1 ./go request TICKET=<id> MODEL_PROVIDER=gemini MODEL=gemini-3.8-flash
  AGENT_HARNESS=gemini-cli APP_PORT=9000` (`./go resume` for a relaunch), `GEMINI_API_KEY` read into the
  environment from the main checkout's `.env`, never printed or written. `MAP_BRIEF=off`, the profile's default.
- Bases, the same as on Anthropic: tests-only tickets from df51380 (clone branch `lights-out-gemini-b`), production
  tickets from eb254b1 (`lights-out-gemini-c`: Anthropic's phase B merges, the tickets 06–10 and the contract fix).
  Each merge was brought home before the next ticket; a ticket with no PR left the base where it was.
- Orders as on Anthropic: 03, 05, 01, 04, 02, then 06, 08, 07, 09, 10.

## 2. The runs

Tokens are gemini-cli's own `result` stats per run (the tower's ledger has input and output only). "Cost ≤" is
list price with every input token uncached ($0.75/M in, $3.75/M out until 2026-12-31, `profiles/prices.json`),
over every dev-worker run of the ticket; "cached" applies $0.075/M to the cached input. The product role ran
live on every ticket (2,898 to 5,414 tokens, $0.03 for all ten together). Time is request to the last step,
both launches included.

| Ticket | PR | Launches | Gate lines | Merged | dev-worker: tool calls, input (cached), output | Cost ≤ / cached | Time |
|---|---|---|---|---|---|---|---|
| tenacity-03 | #1 | 2 (the first stopped by the bug in section 3) | all eight GO; `test-proof — nothing ran: only test files changed` | cf34766 | 13 + 37; 2,202,279 (2,025,588); 4,670 | $1.67 / $0.30 | 1,072 s |
| tenacity-05 | #2 | 1 | all eight GO, as 03 | 6d84ab8 | 40; 1,470,019 (1,350,297); 3,552 | $1.12 / $0.20 | 360 s |
| tenacity-01 | #3 | 1 | all eight GO, as 03 | 27054e3 | 50; 1,691,482 (1,549,709); 3,509 | $1.28 / $0.24 | 306 s |
| tenacity-04 | — | 2, both `over TOKEN_BUDGET (2600000)` | none: no PR | no | 57 + 57; 5,156,856 (4,835,677); 10,046 | $3.91 / $0.64 | 1,167 s |
| tenacity-02 | #4 | 1 | all eight GO, as 03 | 392097a | 32; 863,857 (771,342); 2,496 | $0.66 / $0.14 | 193 s |
| tenacity-06 | #5 | 1 | all eight GO; `test-proof — the changed tests fail on the base eb254b1` | 06bdc78 | 40; 1,746,028 (1,618,443); 3,493 | $1.32 / $0.23 | 352 s |
| tenacity-08 | #6 | 1 | all eight GO; `test-proof — … fail on the base 06bdc78` | 4a707a1 | 44; 1,816,805 (1,680,639); 3,391 | $1.38 / $0.24 | 324 s |
| tenacity-07 | #7 | 1 | all eight GO; `test-proof — … fail on the base 4a707a1` | 22df69a | 42; 2,134,722 (1,996,817); 3,668 | $1.62 / $0.27 | 372 s |
| tenacity-09 | — | 2, both over `TOKEN_BUDGET` | none: no PR | no | 48 + 49; 5,222,782 (4,905,883); 13,934 | $3.97 / $0.66 | 1,423 s |
| tenacity-10 | — | 2, both over `TOKEN_BUDGET` | none: no PR | no | 41 + 43; 5,217,140 (4,891,834); 6,257 | $3.94 / $0.63 | 1,473 s |

- "All eight GO" is `risk` (low, auto-merge), `secrets`, `test-weakening` (one test file changed, none weakened),
  `deps`, `sast`, `test`, `mutation`, `test-proof`, in workbench (isolated), and `mainline` GO after each merge.
  No review and no human gate ran (low risk). `release` fails after `main-green` by construction on a library, as
  on Anthropic, so `./go request` exits 2 every time.
- `mutation` on the production tickets: GO each time. The GO line prints no counts (phase C's finding 2); the
  survivors on stderr: 06 three (`wait.py:239` `==`→`<=`, `:240` NumberReplacer, `:245` ExceptionReplacer), 08
  and 07 none. Anthropic's first attempt at 06 was refused by `mutation`; Gemini's passed at once.
- tenacity-01 and -04 each first failed at `clarify`, before any model call (section 4, finding 4); the table
  counts the launch that ran the worker.
- The relaunches (`./go resume`) are a human action with nothing touched in the code. They did not help: 0 of 3.

What the merged PRs do, as I read them (no gate reads them):

- 03 asserts `to_seconds` with `==` and never that the result is a `float`, which the criteria ask for (`3 ==
  3.0` holds for an int). 05, 01 and 02 assert what their criteria say; 01 is deterministic.
- 06: a `multiplier == 0` branch before the exponent, the overflow handler moved under the `else`.
- 08: `isinstance(e, Exception) and not isinstance(e, self.exception_types)`: no `BaseException` that is not an
  `Exception` is retried any more (`KeyboardInterrupt`, `SystemExit`, `GeneratorExit`), broader than the ticket's
  `CancelledError`. Anthropic's change named `CancelledError` only.
- 07: `wait_combine.__init__` splices in the operands of any `wait_combine` by `isinstance`, so a subclass with
  its own `__call__` would lose it; Anthropic's left subclasses nested.

Why the three stopped: the worker explores far more than Sonnet did. A Gemini ticket took 32 to 57 tool calls,
each model call resending about 45k tokens of context (93 % of it cached); Claude Code's runs on the same tickets
took 4 to 13 turns at about 19k a request (tenacity-09: 10 requests, 187,194 input tokens, its cache reads
included). The budget counts the same unit on both harnesses (input including cache reads, plus output: checked
in `adapters/claude-code/hooks/budget.sh` and the phase C transcript), so the stops are real consumption, not an
accounting difference. 04's first run had written its test and was mutating `tenacity/asyncio/__init__.py` by
hand to check it when it stopped; 09's was still reading code.

## 3. The lights-out bug, fixed (a66e6df)

`adapters/gemini-cli/hooks/budget-after.sh` added `llm_response.usageMetadata.totalTokenCount` on every
`AfterModel` event. gemini-cli 0.61.0-preview.0 (the pin since 0fb2f4a) fires `AfterModel` once per streamed
chunk (`fireAfterModelEvent(originalRequest, chunk)` in its chat stream loop, read in the built image), and each
chunk carries the call's running total. tenacity-03's first run was stopped at 2,638,713 counted tokens when its
own stats said 400,473, 13 tool calls into a tests-only ticket.

- Test first, in `ci/hooks.sh`: four model calls with streamed chunks (one with no usage) against a budget of
  1,000. NO-GO on the old hooks (the third call denied at 1,750), GO after.
- The fix: `budget-after.sh` keeps the largest running total of the call in flight in `tokens.call`;
  `budget-before.sh` adds it to `tokens` before the next call and denies once the total reaches `TOKEN_BUDGET`.
  ADR 0017 is amended. Live after the fix: 04's stop at 2,600,375 counted against 2,608,349 in the CLI's stats.
- ADR 0017's "confirmed live" item of 2026-09-15 read the right field on the wrong event; the budget-stopped runs
  recorded then (4,040,294 and 4,193,082 counted) were likely overcounted the same way.

## 4. Findings, not fixed (each a follow-up)

1. **A run that stops on budget is not in the spend ledger.** `assign` records a run only from `run.json`, which a
   failed crew does not leave, so M50's budget cannot see the five runs that cost most (about $12 of the $20.88
   uncached bound). The $5 ticket limit would not see them either: 04, 09 and 10 show $0.003 each in the ledger.
2. **The ledger prices every Gemini input token uncached.** `run.json` keeps input and output but drops
   gemini-cli's `cached`; with 93 % cached here, the ledger is about six times the cached-price figure.
   `profiles/prices.json` has no cached price either.
3. **`TOKEN_BUDGET=2600000` binds on Gemini and not on Anthropic.** Its provenance (`policy/rework.env`) is the
   Gemini free tier of M5. Whether Gemini gets a larger budget, a per-provider one, or a brief that makes it
   explore less is the owner's decision; raising it would have made these three runs cost more, not necessarily
   pass.
4. **A re-attach right after `./go detach` can see a stale `.attached/`.** `./go attach` deletes and re-clones
   on the host, then `make attached` runs in the workbench, which sometimes still saw no `.attached/.git` and fell
   back to `WORKLOAD=app` (`NO-GO: attached — WORKLOAD=app is not an attached repository`); a `./go request` in
   that window failed at `clarify` (`no request tickets/<id>.md`), before any model call. It settled in seconds;
   the run waited for two `GO: attached` in a row from `./go attached`. Seen on this libkrun VM; not seen in
   phases B and C.
5. Phases A–C's follow-ups came back unchanged: the docs ticket the merge step opens blocks the re-attach until
   `./go detach`, and `release` fails on a library.

## 5. §14's criterion, side by side

The criterion (§14, point 2): the thesis is weaker than expected if at least two tickets in three do not produce
a mergeable PR without a human touching the code.

| | Tests-only (B) | Production (C) | Together | Reworks | Failures |
|---|---|---|---|---|---|
| Anthropic, `claude-code`, `claude-sonnet-5-5` | 5/5 | 5/5 (two through `mutation`'s rework) | 10/10 | 2 | none |
| Gemini, `gemini-cli`, `gemini-3.8-flash` | 4/5 | 3/5 | 7/10 | 0 | 3, all at `TOKEN_BUDGET`, no PR |

- The criterion holds on both providers. On Gemini it holds at 7/10, and the gates were never the reason: every
  PR Gemini opened passed all eight gates at once, including `test-proof` and `mutation` on production code.
- Gemini's results on the two tickets Anthropic needed a rework for: 06 merged at once, 10 stopped.
- Cost per merged ticket, list and uncached: Anthropic ≤ $0.07–$0.44, Gemini ≤ $0.66–$1.67; at the cached price
  Gemini's are $0.14–$0.30. Gemini's three failures cost more than its seven merges together, uncached.
- What it does not show: one run per ticket and provider (no variance); OpenAI not run (no key); M28's map-in-the-
  brief comparison not run; every ticket small and low risk, so no review and no human gate ran.

## 6. `self` and the merge's parent order

The first two pushes (f998ad4, a66e6df) were red in `self` at `secrets`: the range started at 7ba8a4c, the last
green first-parent ancestor on phase C's line, because main's record (bdc1943) does not chain back to it (ADR
0074), so gitleaks judged main's history against 7ba8a4c's old `.gitleaksignore`. A force-push to rebuild the
merge was refused by the auto-mode classifier; 46f9644 is a fast-forward merge of a66e6df into bdc1943 with main
as the first parent, the same tree. `self` then took bdc1943 as its base and went green. The coordinator lands
the branch with main as the first parent, as always.

## Where things are

- tenacity clone `/Users/nicola/Dev/m24/tenacity`: `lights-out-gemini-b` at 392097a (df51380 + four merges),
  `lights-out-gemini-c` at 22df69a (eb254b1 + three merges), checked out on `-c`; `lights-out` (Anthropic) at
  4831978, untouched.
- Run checkouts and logs: `/Users/nicola/Dev/m24/m24d-crew/` (`full/.crew/state.sqlite` is the tower; `logs/`
  has every run's log, each run's `out/` copy, `stats.jsonl` with each run's gemini-cli stats, the chain scripts).
- The plane: down since 08:17 UTC on 2026-11-14; the slot is free.
- Working notes: the shared notes folder, `m24-phase-d-gemini-notes.md`.

## Proofs

- `ci/hooks.sh`: NO-GO before a66e6df, GO after; `ci/harness.sh`, `ci/harness-shape.sh`, `ci/shell.sh` GO.
- `./go ci` from a clean clone: GO on f998ad4 (308 s) and on the final head (see the plan's note).
- The runs: section 2, from the tower documents, each run's `transcript.jsonl` and `./go spend`
  (`GO: spend — 10 tickets, 17 runs, $8.78 known, 0 of cost unknown`).
- Workflows on 46f9644: ci 43568373040, stranger 43568373058, self 43568373013, package 43568373000, podman
  43568373036, all success.
