# Handoff: stream C of the sprint of 2026-11-12, delivery measures (M48, ADR 0082) and cost per ticket with a budget (M50, ADR 0083)

Branch `claude/sprint-c-dora-spend`, cut from `origin/claude/sprint-plan-1112` at dd79626. It is pushed with no pull request. Nothing is merged. The coordinator merges.

## What changed

- **ADR 0082, "The delivery measures, from the logbook".** DORA's four keys as dora.dev's guide names them today (last updated 2026-01-05): deployment frequency, change lead time, change fail rate, failed deployment recovery time. The ADR covers what lights-out records for each one, how that differs from DORA's definition, and a fixture with values computed by hand. Deployment rework rate, DORA's fifth key, is not measured, and the ADR says why. `WINDOW_DAYS` defaults to 30, recorded as the owner's decision from the plan.
- **`./go dora`** (`core/dora.sh` and `core/dora.py`) writes the logbook first unless `DORA_LOGBOOK` names one, then reads only the logbook's `releases[]` and `tickets[].history`. It writes `.crew/dora.json` (`DORA_OUT`, schema `dora/1`), prints one line per measure on stderr and one contract line on stdout.
  - **Deployment frequency**: the GO answers in the window, per day.
  - **Lead time**: the median time from a ticket's first history entry (`request`, or `open`) to the GO answer of its release.
  - **Change fail rate**: rolled-back releases plus NO-GO answers, divided by the decided releases. A held release with no answer is counted as `pending`.
  - **Recovery time**: the median time from the last stage's `started_at` to the rollback (the release's `at`, or `answer.at` for a NO-GO).
  - A measure with no sample is printed as not measured, with the reason.
- **ADR 0083, "Cost and time per ticket"**, with these parts:
  - **`profiles/prices.json`**: four entries, each with its vendor page and `checked: 2026-11-12`:
    - gemini-3.8-flash: $0.75/$3.75 per MTok until 2026-12-31, then $1.50/$7.50 from 2027-01-01 (aistudio.google.com/docs/pricing).
    - claude-sonnet-5-5: $2/$10 (platform.claude.com/docs/en/about-claude/pricing).
    - gpt-6.1-sol: $2/$10 for prompts up to 272K tokens (developers.openai.com/api/docs/pricing).
  - **Cost per run**: input × in + output × out, at the price whose period contains the run's day. A replayed run costs 0. A network run costs the sum of its members. With no price, the cost is unknown and the reason is recorded.
  - **Ledger**: `core/tower.py` appends one entry to the ticket document's `spend[]` for each run in a step's result (`task`, `review`, `product`; not a product with `consulted: false`). Each entry holds the tokens and `cost_usd` side by side, or `cost_unknown` with the reason. `task`, `tasks`, `review` and `product` are unchanged, so the logbook output and its golden do not move.
  - **Budget**: `SPEND_BUDGET_TICKET_USD` and `SPEND_BUDGET_DAY_USD` in `policy/rework.env`, empty by default. The tower checks them before `assign` and `rework`. The day total covers every ticket in `TICKETS_DIR`, read through the store, UTC day. A limit stops the next attempt when the spend is at or over it, or when an unknown cost is part of the sum. A malformed value refuses the step and names the key.
    - Over the limit at `rework`: `SPEND_STOP=<line>` goes to `core/steps/rework.sh`. It records the rejected attempt as always and prints `needs-human` with `budget.line`.
    - Over the limit at `assign`: the step is refused like a red main and the ticket stays at `opened` until `./go resume`.
  - **`./go spend`** (`core/spend.sh`, `core/spend.py report`) prints cost, agent time and elapsed time per ticket, per role and per day on stderr, and one contract line on stdout.
- **Tests, written from the ADRs before the code**: `core/tests/test_dora.py` (13 tests) and `core/tests/test_spend.py` (26 tests). A second ADR amendment, 93f18e0, came from the first demo: a replayed run reports the recorded run's duration, so the agents' time excludes replayed runs. One hand computation in ADR 0083 was wrong: the report total is $4.20, not $4.70. Commit 2fe7400 corrects it in both the ADR and the test.
- **Other files**: `Makefile` targets `dora` and `spend`, the `go` header and socket lists, and `docs/reference.md` (the commands and the control-plane paragraph).

## Verified

- `./go ci` from this clone: GO at 801d9c9 (50 GO lines, `GO: ci`). The earlier runs went NO-GO on shell-boundary (`rework.sh` past its 51-line debt, fixed in e86d52f) and, once, on secrets. The secrets NO-GO was a false positive that `./go dora` exposes: it writes `.crew/logbook.json`, and gitleaks' generic-api-key rule matches the logbook's `"key": "<POLICY_KEY>"` threshold rows. This happens to any `./go logbook` followed by `./go ci`. Not fixed here (ci/gitleaks-worktree.toml).
- `./go demo` at e86d52f: `GO: demo, milestone M9, 660s to rollback (budget 900s)`, 661 s wall, the automatic rollback reached. On the state it left: `./go dora` GO with 2 of 4 measured (0 deployments; fail rate 100%, 2 of 2 rolled back; lead time and recovery not measured, with reasons). `./go spend` GO: 1 ticket, 1 run, $0.00 (replayed). The plane was brought down afterwards.
- Actions at e86d52f: package 43315098033 success, stranger 43315098182 success, podman 43315098028 failure, ci 43315098239 failure. Both failures were the eager `import spend` in core/tower.py: console-ui loads tower.py by path, and the harness-conformance proof copies tower.py into a tree on its own. 1d7476b makes the import lazy. At 1d7476b: package 43316941685 success, the rest still running at handback. At 801d9c9 (head): self 43317945904, package 43317945914, stranger 43317946028, ci 43317946001, podman 43317946069, all running at handback.

## Deviations from the plan

- **M50, "il run del ruolo di rilascio (promote.sh) registrato come gli altri": not done.** `core/promote.sh` belongs to stream A. ADR 0083 lists it as a follow-up: promote should hand its `run.json` to the ledger.
- **M50, "il ticket va a needs-human"**: this holds for `rework`. At `assign` the ticket is instead refused and stays at `opened`, where it can be resumed. At `opened` there is no attempt and no PR to decide about, and a `needs-human` ticket holds its perimeter (`core/assign.py` HOLDING). ADR 0083 §4 records this.
- **M48, "tempo di ripristino"**: it is measured only when a stage has `started_at`, which stream A's ADR 0080 adds. Until stream A lands, a real logbook reports recovery time as not measured, with the reason.
- **No `ci/dora.sh` or `ci/spend.sh`.** The contract tests for each command (one stdout line, GO and NO-GO) are in the unit tests that `ci/core-tests.sh` already runs, so `CI_CHECKS` is unchanged.
- **Not updated**: `docs/use-on-your-repo.md`, because the budgets are platform policy and not keys an attached repository can override; the site; and `docs/PLAN.md` (the coordinator's status notes).

## What the console slice will need

- **For the M48 panel**: `.crew/dora.json` already comes from the logbook. The slice can embed it in the logbook (say `dora`, the same object) or have `console/serve.py` run `core/dora.py` over the logbook it serves. `measured: false` entries carry `why` for display.
- **For the M50 panel**: the logbook does not read `spend[]` yet. Add `tickets[].spend` (the ledger entries) to the logbook schema, and possibly a `spend` summary built with `core.spend.report({id: doc})`. A `needs-human` stopped by the budget carries `budget.line` on the document. The logbook's `outcome()` still shows `rework[-1].line`, so the console should prefer `budget.line` when it is present.
- **For stream A's promote**: price the release role's run with `spend.entries("promote", {"task": dict(tower.task(run), role="release")}, None, now)` and append the result to the ticket's `spend`.
