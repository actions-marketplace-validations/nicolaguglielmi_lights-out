# ADR 0083 — Cost and time per ticket: a dated price table in `profiles/`, a spend ledger in the tower, a budget per ticket and per day that stops the next attempt

- Status: proposed (M50)
- Date: 2026-11-12

## Context

Every role's `run.json` reports its tokens and duration, and the tower
copies them into the ticket's document (ADR 0047 §2, P1). A run has a
token budget of its own (`roles/*/role.env` `TOKEN_BUDGET`, ADR 0021
§7). Nothing turns tokens into money, nothing adds a ticket's runs up,
and nothing stops a ticket that keeps reworking, or a day of tickets,
before the money is gone. Two more gaps, found reading the code
(2026-11-12): the tower keeps every dev-worker attempt in `tasks`, but
`review` and `product` keep only the last run (`rework` clears `review`),
so the earlier reviews of a ticket are not on the document at all.

The plan asks for prices with their source and date, the cost of every
run beside its tokens, two limits that stop the next attempt and send the
ticket to `needs-human` with a one-line reason, `./go spend`, and no
invented price (docs/PLAN.md, sprint 2026-11-12, M50).

## Decision

1. **The price table is `profiles/prices.json`**, the one place besides
   `adapters/` where a model id may be written (ADR 0040 §5). One entry
   per provider, model and period: `{provider, model, input, output,
   from, until, source, checked}`, prices in USD per million tokens,
   `from`/`until` dates (UTC, both included, either may be absent),
   `source` the vendor's own pricing page and `checked` the day it was
   read. Provenance, external, each read on 2026-11-12:

   | provider | model | input | output | period | source |
   |---|---|---|---|---|---|
   | gemini | gemini-3.8-flash | 0.75 | 3.75 | until 2026-12-31 | aistudio.google.com/docs/pricing (ai.google.dev's page redirects there), "Standard", paid tier; output includes thinking tokens |
   | gemini | gemini-3.8-flash | 1.50 | 7.50 | from 2027-01-01 | the same page, the announced price |
   | anthropic | claude-sonnet-5-5 | 2.00 | 10.00 | — | platform.claude.com/docs/en/about-claude/pricing, base input and output; no long-context tier for this model |
   | openai | gpt-6.1-sol | 2.00 | 10.00 | — | developers.openai.com/api/docs/pricing, Standard, prompts up to 272K tokens |

   A model the table does not name, or a run outside every period of its
   model, has no price: **cost unknown**, never a neighbour's price, never
   a prefix match.
2. **The cost of a run** is `input x price.input / 1e6 + output x
   price.output / 1e6`, from `tokens.input` and `tokens.output`, at the
   price whose period holds the day the run was recorded; rounded to the
   micro-dollar. A replayed run (`replayed: true`) costs 0: no model was
   called (ADR 0017 §2). A network's run (ADR 0036) is the sum of its
   members', unknown if any member's is. Unknown, with the reason, when
   the run names no provider or model, reports no input or output tokens,
   or has no price.
3. **The ledger.** After every step, the tower appends to the document's
   `spend` list one entry per run the step's result carries: `task` (the
   dev-worker's, `assign` and `rework`), `review` (the reviewer's) and
   `product` (the clarify and answer steps'), each an object with a
   `harness`; a `product` with `consulted: false` is not a run (ADR 0055:
   at L0 with no recording no model was asked). An entry is `{step,
   attempt, role, harness, provider, model, replayed, tokens, duration_s,
   cost_usd, cost_unknown, at}`: the cost beside the tokens, `cost_usd`
   null and `cost_unknown` the reason when there is no price. The list is
   appended, never rewritten, so a review a rework cleared is still
   counted. `task`, `tasks`, `review` and `product` are unchanged, and the
   logbook does not read `spend` yet.
4. **The budget.** `SPEND_BUDGET_TICKET_USD` and `SPEND_BUDGET_DAY_USD`
   in `policy/rework.env`, beside the cap they extend, read from the
   tower's own checkout like it. Empty by default: no limit, and `./go
   demo` unchanged. Provenance, decision: the owner's, docs/PLAN.md,
   sprint 2026-11-12, M50 ("vuoti di default"); a number set there must
   carry its own provenance (ADR 0047's check on policy keys). A value
   that is neither empty nor a positive decimal number refuses the step,
   naming the key.
   - **When.** Before the two steps that launch a dev-worker attempt,
     `assign` and `rework`; a run in progress is never cut (its own
     `TOKEN_BUDGET` does that), and `review`, `clarify` and `answer`
     are not stopped.
   - **What is counted.** The ticket: every `spend` entry of its
     document. The day: every `spend` entry dated today (UTC) of every
     ticket the Tracker lists (`TICKETS_DIR/*.md`, as the logbook reads
     them), read through the state store.
   - **Over.** A limit is reached when the spend counted is at or over
     it, or when any entry counted has an unknown cost: a sum with an
     unknown term cannot be shown under a limit. The reason is one line
     naming the key, the limit and the spend, or the run whose cost is
     unknown and why.
   - **`rework` over the limit**: the tower runs `core/steps/rework.sh`
     with `SPEND_STOP=<line>`, which records the rejected attempt in
     `rework` as always and prints `needs-human` with `budget: {line}`,
     without launching the next attempt.
   - **`assign` over the limit**: refused like a red main (ADR 0056 §5):
     the history entry carries the line as its error and the ticket stays
     at `opened`, resumable with `./go resume` once the day has turned or
     the policy has changed. Not `needs-human`: no attempt and no PR
     exist yet, and a ticket at `needs-human` holds its perimeter
     (ADR 0053 §5).
5. **`./go spend`** reads every ticket's document through the state
   store and prints on stderr the cost and time per ticket (the known
   cost, how many runs, how many of unknown cost, the agents' time as the
   sum of `duration_s` of the runs that were not replayed, and the
   elapsed time from the first to the last history entry), per role and
   per day. A replayed run reports the recorded run's duration, not its
   own (found at the first `./go demo` with this ADR: ticket 0001's
   replayed attempt reported 328 s of agents inside 218 s of ticket); stdout is one line of the gate
   contract, `GO: spend — <n> tickets, <r> runs, $<x> known, <u> of cost
   unknown`, or `NO-GO: spend — <why>` when the store cannot be read.

## The gap between the cost and the bill

- **Cached input is priced as input.** Claude Code's input counts cache
  reads and writes (`adapters/claude-code/run.sh`), Codex's and Gemini
  CLI's input include cached tokens; the bill discounts cache reads
  (0.05x on Claude Sonnet 5.5). The cost overstates such runs.
- **Tokens in neither input nor output are not priced.** Gemini CLI's
  `total` can exceed input plus output: the recorded run of ticket 0001
  reports 2,329,279 in, 2,838 out, 2,435,115 total (measurement,
  `fixtures/0001/dev-worker/run.json`), 102,998 tokens unaccounted. The
  plan prices input and output; the rest is not guessed at.
- **Long-context prices are not applied.** OpenAI's prompts over 272K
  tokens cost more; a run's totals do not say how large each request
  was, so the base price is used.
- **The release role's run is not in the ledger.** `core/promote.sh`
  runs it from L1 without recording its `run.json` in the tower; that
  file belongs to the sprint's stream A, so recording it is left to a
  follow-up, as is the logbook carrying `spend` (the console slice).

## Tests, from this ADR

`core/tests/test_spend.py`, with a price table of the test's own
(provider `prov`; `model-a` at 1.00 in and 5.00 out; `model-b` at 0.75
and 3.75 until 2026-12-31, 1.50 and 7.50 from 2027-01-01):

- `model-a`, 2,000,000 in and 100,000 out: $2.50. `model-b`, 1,000,000
  and 1,000,000, on 2026-12-31: $4.50; on 2027-01-01: $9.00. Replayed:
  $0. `model-z`: unknown, the reason naming `prov/model-z`. No `tokens`:
  unknown. A network of `model-a` members (1,000,000/0 and 0/100,000):
  $1.50; with one `model-z` member: unknown.
- The committed `profiles/prices.json`: every entry has provider,
  model, a non-negative input and output, an `https://` source and a
  `checked` date; no two periods of one model overlap.
- The report, on two documents. Ticket 0201: assign, dev-worker,
  `model-a`, 2,000,000/100,000, 300 s, 2026-11-10T10:00:00Z ($2.50);
  review, test-reviewer, `model-a`, 400,000/20,000, 60 s,
  2026-11-10T10:10:00Z ($0.50); rework, dev-worker, `model-a`,
  1,000,000/40,000, 200 s, 2026-11-11T09:00:00Z ($1.20); history from
  2026-11-10T09:00:00Z to 2026-11-11T10:00:00Z. Ticket 0202: assign,
  dev-worker, `model-z`, 50 s, 2026-11-11T12:00:00Z (unknown); review,
  test-reviewer, replayed, 5 s, 2026-11-11T12:05:00Z ($0); history from
  2026-11-11T11:00:00Z to 2026-11-11T12:30:00Z. Expected: 0201 $4.20, 3
  runs, 0 unknown, 560 s of agents, 90,000 s elapsed; 0202 $0.00, 2
  runs, 1 unknown, 50 s (the replayed review's 5 s not counted), 5,400
  s; dev-worker $3.70, 3 runs, 1 unknown, 550 s; test-reviewer $0.50, 2
  runs, 60 s; 2026-11-10 $3.00, 2 runs;
  2026-11-11 $1.20, 3 runs, 1 unknown; in all $4.20, 5 runs, 1 unknown.
- The budget, on 0201's spend: `SPEND_BUDGET_TICKET_USD=4.20` stops,
  4.21 does not; on a day whose entries are 0201's $1.20 alone,
  `SPEND_BUDGET_DAY_USD=1.20` stops, 1.21 does not, and yesterday's
  entries never count; 0202's unknown entry stops either limit; empty
  limits never stop; `x`, `0` and `-1` are refused naming the key.
- The tower: a step whose result carries a `task`, a `review` and a
  `product` appends three entries with the cost beside the tokens; a
  `product` with `consulted: false` appends none; a result with no run
  appends none. `rework` over a limit runs the step with `SPEND_STOP`
  set to the line, under it with `SPEND_STOP` empty; `assign` over a
  limit leaves the ticket at `opened` with the line as the history
  error, runs no step and publishes nothing.
- `core/steps/rework.sh` with `SPEND_STOP` set, at attempt 1 of 4:
  `needs-human`, the rejected attempt appended to `rework`,
  `budget.line` the line, and no crew run.
- `core/spend.sh`: one `GO: spend — ` line with no ticket; one `NO-GO:
  spend — ` line with no `STATE_STORE`.

## Alternatives rejected

- **The cost inside `task()`** (`core/tower.py`), beside the tokens of
  `task`, `tasks` and `review`. It would change every document key the
  logbook copies and every test that pins them, and it would still lose
  the reviews a rework clears; the ledger keeps every run once.
- **Prices in `profiles/l1.env`.** A profile names one model; the price
  of the others would have nowhere to live, and env keys cannot hold a
  model id.
- **An unknown cost counted as zero under a limit.** The budget would
  pass a ticket whose spend nobody knows: the limit exists to stop that.
- **`needs-human` at `assign`.** See §4: no attempt to decide about, and
  it would hold a perimeter for a ticket that never started.
- **Stopping `review` and `clarify` too.** A review stopped halfway
  leaves a PR with no verdict; the limit acts at the one point where
  stopping leaves a clean state, between attempts.

## Consequences

- With the limits empty nothing changes: `./go demo` replays, every run
  costs 0, and `./go spend` says so.
- A price change is a commit to `profiles/prices.json` with its new
  source date; a run keeps the cost computed when it was recorded.
- The console slice (after stream A) adds `spend` to the logbook and a
  panel; the release role's run joins the ledger when promote records it.
