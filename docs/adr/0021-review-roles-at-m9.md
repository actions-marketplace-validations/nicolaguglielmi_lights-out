# ADR 0021 — Review at M9: the tower gains one step, `review`, between `ci` and `merge` on the risk verdict the gates already computed; `test-reviewer` runs on the existing `gemini-cli` harness with a second artefact contract (an input document, a final message, no commit) and its verdict decides `ci-passed` or `ci-failed`; `architect` gets a prompt and one recorded run but no wiring; ticket 0003's perimeter is a `## Perimeter` section in the ticket, checked by `core/` after every harness run at every level, before the PR exists; the two dev-worker `record`s are one run of ticket 0001 and one of the new medium-risk ticket, and they — not this ADR — produce `TOKEN_BUDGET`

- Status: accepted
- Date: 2026-09-17
- Milestone: M9

## Context

Plan §7 M9 (written by the owner, renumbered ahead of M8 because none of
this work depends on GCP): real prompts for `architect` and `test-reviewer`
on the existing `gemini-cli` harness; a `review` step in `core/tower.sh`
(precondition `review`, next state `ci-passed` or `ci-failed`); ticket
0003's perimeter rule before the next `record`; the two dev-worker `record`s
that fix the token budget (ADR 0020 §9: 12M/call is a hypothesis, not a
measurement) and validate ticket 0004's prompt rewrite. Done when a
medium-risk PR (recorded at L1, replayed at L0) goes through `review`,
`test-reviewer` marks it approved or changes-requested with a traceable
reason in the tower's document, and a fixture whose diff leaves the ticket's
perimeter is not written by `record`, the reason naming the file.

Repo facts this decision rests on. `core/steps/ci.sh` already computes the
routing: `GO`+`auto-merge` → `ci-passed`, `GO`+`review` → `review`, `NO-GO`
→ `ci-failed`, and prints "nobody reviews until…"; `review` is terminal
(ADR 0019 §1). `merge`'s precondition is `ci-passed`. In `policy/merge.env`
every path signal is `high` and the only source of `medium` is size ≥ 200
changed lines (ADR 0016 §2; the 200 is external, SmartBear/Cisco, and M9
does not touch it). The AgentHarness port is `adapters/<name>/run.sh` with
an env contract and an artefact directory (ADR 0017 §1); ADR 0020 §1 already
established that one verb may carry a **second, declared** artefact contract
(the ADK roles: an input document, tool calls and a final message, no
workspace). `core/crew.sh` calls `core/harness-check.sh` after every run —
a core-side, harness-independent invariant — and resolves
`${HARNESS:-$AGENT_HARNESS}`. `adapters/replay/run.sh` is already keyed by
`fixtures/<ticket>/<role>/`. `roles/dev-worker/role.env` states, in the file,
the exact condition that turns `TOKEN_BUDGET` from a hypothesis into a
measurement. The gemini-cli entrypoint hardcodes a dev-worker-shaped closing
instruction ("your final message must be exactly the pull request text").
Measured at M7 close: `./go demo` 684 s cold of a 900 s budget (HANDOFF).

## Decision

1. **Two lines in the transition table; `merge`'s precondition is
   unchanged.** `core/tower.sh`:

   ```
    precondition()                       next()
      assign)  'opened'                    pr-opened) 'ci'
      ci)      'pr-opened'               +  review)    'review'
   +  review)  'review'                     ci-passed) 'merge'
      merge)   'ci-passed'                  merged)    'release'
      release) 'merged'
   ```

   Nothing else changes. A `low` PR reaches `ci-passed` straight from `ci`
   and never enters `review`; a `medium` or `high` PR reaches `ci-passed`
   only through an approval, and `changes-requested` lands in `ci-failed`,
   which is already terminal. The step name equals the state it starts from;
   that reads oddly and is the dumb thing that works. `core/steps/ci.sh`
   loses its "nobody reviews" line and nothing else.
2. **`core/steps/review.sh` is the step, `test-reviewer` is the role, and
   it obeys the existing step-script contract.** Inputs from the tower:
   `TICKET`, `PR_NUMBER`, `BASE_SHA`, `HEAD_SHA`, `DOC_FILE`; `ROLE`
   defaults to `test-reviewer` (`assign.sh`'s `: "${ROLE:=dev-worker}"`
   precedent). It fetches `ticket/<id>` from the code host and asserts
   `FETCH_HEAD == HEAD_SHA` (`ci.sh`'s six lines, reused), clones the head
   into `.crew/<id>/review/workspace` (a worktree's `.git` file would not
   resolve inside the harness container), builds the **input document**
   `.crew/<id>/review/input.md` = the ticket text from
   `adapters/$TRACKER/get.sh` + `git diff BASE_SHA FETCH_HEAD`, sources
   `roles/$ROLE/role.env`, resolves `${HARNESS:-$AGENT_HARNESS}` and runs
   `adapters/$harness/run.sh`. It then reads `OUT/final.md`: **first line
   exactly `APPROVED` or `CHANGES-REQUESTED`, the rest the reason.** Any
   other first line, or an empty reason, is a step failure (exit 1, document
   untouched, the tower's own rule) — never a default verdict. It posts the
   verdict as a `review` commit status through the existing `status.sh` verb,
   and prints one JSON line:

   ```json
   {"state":"ci-passed","review":{"role":"test-reviewer","verdict":"approved",
    "reason":"…","harness":"replay","model":null,"input_sha256":"…",
    "input_matches_recorded":true}}
   ```

   `changes-requested` prints the same object with `"state":"ci-failed"`.
   Makefile `review TICKET=<id> [ROLE=test-reviewer]` runs the same script
   outside the tower from `.crew/<id>/pr-opened.env` — the way `crew-run`
   already calls `core/steps/ci.sh` — so one script serves both.
3. **The reviewer's artefact contract is the second one ADR 0020 §1 opened,
   and it costs three small edits, not a new adapter.** (a)
   `adapters/gemini-cli/run.sh` writes the reconstructed final response to
   `OUT/final.md` as well as `OUT/pr.json` (`adk` already writes `final.md`;
   after this, *every* harness writes its final message to one field, which
   is a deletion of variance, not a new abstraction) and records
   `input_sha256` (sha256 of the document it was given) in `run.json`.
   (b) `adapters/gemini-cli/entrypoint.sh`'s trailer stops naming the pull
   request: "do not commit or push; when you are done your final message is
   this run's artefact and must contain exactly what your role's
   instructions say, nothing else" — the role-specific half already lives in
   `prompt.md`, twice, for dev-worker. (c) `adapters/replay/run.sh` branches
   on the fixture's contents: a fixture with `patch` is applied as today; a
   fixture with `final.md` and no `patch` is copied; a fixture with neither
   is the existing loud failure naming the record command. No new adapter,
   no new port, no `REVIEW_*` env in the port's contract.
4. **`architect` gets a prompt and one recorded run, and no tower wiring.**
   The acceptance names only `test-reviewer`; a second verdict in the tower
   needs a policy for combining two verdicts that nothing at M9 consumes.
   But a prompt nobody has run is the "unexercised hypothesis" ADR 0017 §7
   refused for these two roles, so `architect` is exercised once through the
   same script — `./go review TICKET=<id> ROLE=architect PROFILE=l1` — on the
   same PR, recorded to `fixtures/<id>/architect/` and replayed by
   `demo-review`'s second assertion. Plan §7 M9's sentence is satisfied
   literally; the tower still has exactly one reviewer. When a structural
   change needs the architect's verdict, that is a routing decision with its
   own ADR.
5. **Ticket 0003: option 1's declaration, but checked in `core/`, not in
   `gates/`.** The ticket declares a `## Perimeter` section, one glob per
   line as a list item; `core/perimeter.sh <ticket-file>` reads changed paths
   on stdin (`core/risk.py`'s stdin-from-git shape) and prints the first path
   matching no glob. `core/crew.sh` calls it right after
   `core/harness-check.sh` with `git -C "$WORKSPACE" diff --name-only
   "$base"..HEAD`, and `nogo`s naming the file. Consequences, all of them
   wanted: the check runs **at every level on the same code path** (L1 real
   run and L0 replay, which is ticket 0003's second criterion, mechanically,
   with no new comparison to write); the fixture is not written because no
   PR is ever opened; and the demo's own PRs are checked too, which is what
   ticket 0003's option 3 could not do. A ticket with no `## Perimeter` is a
   NO-GO naming the ticket, not a silent pass. Ticket 0001's perimeter is the
   four files it already names in prose, spelled as globs —
   `app/backend/tests/test_geocoder_*.py`, not `app/backend/tests/*`, which
   is why the M5 fixture's `app/backend/tests/conftest.py` hunk is outside it,
   as ticket 0003 requires. **Not a gate**: `gates/` judge a git range and
   know nothing about tickets (ADR 0015); a `gates/perimeter.sh` would need
   `TICKET` plumbed through `make gates` and would have to answer GO on the
   six `demo-gates` fixtures and on any manual `./go gates BASE=… HEAD=…`,
   i.e. pass when it cannot check — the one thing the gate contract must
   never do.
6. **The two dev-worker `record`s are one run of ticket 0001 and one of the
   new medium-risk ticket; the number is theirs, not this ADR's.** Ticket
   0004's own criterion names a `record TICKET=0001` under the rewritten
   prompt, and that run also replaces the M5 fixture — recorded on
   `gemini-3.5-flash` under a prompt the tree no longer has (ADR 0018 §5,
   ADR 0020 consequences: "the one that hurts"). The second run is the new
   ticket, which is where the medium-risk PR comes from. Together they are
   the "two consecutive successful `./go record … PROFILE=l1` runs on this
   prompt" that `roles/dev-worker/role.env` already names as the condition
   for `TOKEN_BUDGET`: the committed value becomes the larger of the two
   `run.json` totals plus one call's headroom at those runs' own per-call
   cost, written into `role.env` with both totals quoted. **No number is
   written here: it does not exist yet.** If either run is denied at
   12,000,000, there is no second successful run, the line stays provisional,
   and HANDOFF records that as the measurement — the ceiling is not raised to
   make a run fit.
7. **Budgets for the two review roles: borrowed, then measured.**
   `THINKING=high` in both files already (plan §5). The first L1 run uses
   dev-worker's numbers verbatim — `MAX_TURNS=60` (external: the free tier's
   250 requests/day over four attempts), `TIMEOUT_S=900` (plan §2, the one
   wall-clock figure this repo has), `TOKEN_BUDGET` = dev-worker's — each
   marked *borrowed, provisional, no measurement exists* in `role.env`. The
   committed values come from that run's `run.json` in the same commit as the
   fixture, with the recorded totals as provenance. Plan §5 says the review
   roles are "few calls, high impact"; that is a reason to expect lower
   numbers, not a reason to invent them before the first run.
8. **The medium-risk ticket is a size-medium ticket, and that is a
   measurement.** `medium` has exactly one source: ≥ 200 changed lines with
   no `high` path touched — so the new ticket (0005) must be app-only (no
   migration, no auth, nothing under `RISK_HIGH_PLATFORM`) and big enough
   that a correct implementation crosses 200 lines; a contract-and-fake
   ticket (every documented geocoder case gets an example, the fake serves
   them, the tests assert them) is the candidate that fits the app we have.
   Whether the recorded run actually crosses 200 lines is measured, not
   assumed. If two runs land under it, the honest moves are to enlarge the
   ticket or to take the word "medium" back to the owner —
   `RISK_SIZE_MEDIUM_LINES` is not lowered to fit the demo, and a `high` PR
   is not relabelled.
9. **Acceptance and tests.** `demo-review TICKET=0005` (manual, not a
   `./go demo` stage): `up`, delete the document, `tower.sh open`, the
   `inproc` loop, then assert the document carries `review.verdict` ∈
   {approved, changes-requested}, a non-empty `review.reason`,
   `input_matches_recorded == true`, and that the state matches the verdict
   (approved → past `ci-passed`; changes-requested → `ci-failed`, no
   `merge.sha`); then `./go review ROLE=architect` on the same PR.
   `record-review TICKET=<id> [ROLE=…]` (the `record-evals` precedent)
   refuses at L0 and copies `.crew/<id>/review/out/*` plus `input.md` into
   `fixtures/<id>/<role>/`. Cold, no plane, in `CI_CHECKS`: `ci/tower.sh`
   gains the two new transitions (approved → `ci-passed` → `merge`;
   changes-requested → `ci-failed`, nothing published, no merge effect) and
   loses the old "`review` is terminal" case; `ci/review.sh` proves
   `core/steps/review.sh` on a stub harness and a local bare repo as the code
   host (approved, changes-requested, a third word → exit 1 and no state, an
   empty reason → exit 1, a recorded-input mismatch → a warning and the field
   `false`); `ci/perimeter.sh` proves `core/perimeter.sh` on stub tickets and
   stub path lists, including the literal `app/backend/tests/conftest.py`
   case ticket 0003 came from, and a ticket with no `## Perimeter`.
   `core/audit.sh` gains one link line and one NO-GO: a document whose
   `ci.decision` is `review` and whose state is past `review` must carry
   `review.verdict` and `review.reason` — a reviewed merge with no review on
   the record is exactly what an audit exists to catch.
10. **Not built at M9.** Two reviewers in the tower and any policy for
    combining verdicts; a human in the review loop (the one human gate is
    `go-for-launch`, plan §1); review comments posted line-by-line on the PR
    (one commit status and the document, no new CodeHost verb); a reviewer at
    L2; re-review after a changes-requested (`ci-failed` is terminal and the
    next `assign` force-pushes, as today).

## Alternatives rejected

- `review` as a branch keyed off `risk.json` rather than off the `review`
  state: the state *is* the risk verdict, already computed once by
  `core/steps/ci.sh` and written to the document; re-reading the gate output
  would give the tower a second source of the same truth.
- New states `review-approved` / `changes-requested`: two more states, and
  `merge`'s precondition would have to accept two — the owner's note says
  `ci-passed`/`ci-failed` and they cost nothing here.
- Running the reviewer inside `core/steps/ci.sh` (one step, two roles): the
  gates and the reviewer would share a failure mode, and the document could
  not say which judge blocked the PR.
- `core/crew.sh` driving the reviewer: it exists to produce a commit and a
  PR, and `core/harness-check.sh` fails a run with no commit over `BASE` —
  the invariant is right for a coding run and wrong for a reading one.
- A `Reviewer` port, or an `AgentHarness` adapter for reviews: plan §4's
  table has one harness port and the `gemini-cli` adapter already runs a role
  on a workspace; what differs is the artefact, which ADR 0020 §1 already
  declared may differ.
- Feeding the reviewer the risk verdict as well as the ticket and the diff:
  it invites a review of the size number instead of the code; the risk
  verdict has already done its job by routing the PR here.
- `gates/perimeter.sh` joining `GATES` (ticket 0003 option 1 as written), and
  risk-scoring the perimeter (option 2): §5; option 2 also leaves the fixture
  written at L0, which the ticket itself says.
- A `record`-only perimeter check (option 3): the demo's own PRs would carry
  the same drift, and ticket 0003's second criterion ("the same check runs on
  the replayed PR") would need a second mechanism.
- Deriving the perimeter from the ticket's prose ("the tests under
  `app/backend/tests/`"): that phrase *includes* `conftest.py`, so the one
  case the ticket exists for would pass.
- `architect` wired into the tower for `high` PRs: a second recorded PR and a
  verdict-combining policy for something nothing consumes at M9.
- `architect` with a prompt and no run: ADR 0017 §7.
- `demo-review` in `./go demo`: 684 s cold of 900 already (HANDOFF); the
  stage list is a promise (ADR 0003) and the golden rule's criterion is the
  rollback. A workflow job runs it on every push, the `demo-launch`
  precedent.
- A NO-GO when the recorded review's input does not match the current diff:
  a prose edit to the ticket would then block the tower; the document records
  the mismatch, `demo-review` fails on it, and the tower stays honest instead
  of stuck.

## Consequences

- **`ci-failed` now has two causes**: a gate said NO-GO, or a reviewer asked
  for changes. Anyone reading the state must read `ci.verdict` and
  `review.verdict` to tell them apart. This is the one that will hurt, and
  it is the owner's own wording; the audit line prints both.
- After M9, a `medium` or `high` PR merges on an **agent's** approval. That
  is plan §8 steps 4–5 and the project's single-human-gate design, but it is
  the first time an agent's judgement opens a merge, and it should be said
  out loud in the README, not discovered from the code.
- The perimeter is a second thing to keep true, exactly as ticket 0003
  warned: a ticket that forgets a path it legitimately needs burns a real L1
  run before the PR exists. The NO-GO names the path, and the fix is a
  one-line ticket edit — which is the right conversation.
- Landing order is load-bearing: the perimeter rule makes the committed M5
  fixture (with its `conftest.py` hunk) illegal, so `./go demo-crew`, `./go
  e2e` and therefore `./go demo` are red between the rule landing and ticket
  0001 being re-recorded. The re-record must succeed in the same session; if
  it does not, M9 does not close. `core/crew.sh`'s symlink fix (ADR 0018) is
  the reason to expect it will.
- Re-recording ticket 0001 changes what every L0 run replays: a different
  correct patch, a new `expect`, possibly the other documented outcome of
  that ticket. `demo-crew` compares against the new `expect`, so the change
  is visible, not silent.
- The review fixture is only true about the dev-worker fixture recorded
  beside it; the pair must be re-recorded together. `input_sha256` makes the
  drift visible in the document and red in `demo-review`, but nothing
  prevents committing a drifted pair.
- Two more `ci` checks (`perimeter`, `review`), one changed one (`tower`),
  two more socketed targets (`demo-review`, `record-review`), one more
  workflow job. Milliseconds in `ci`; `./go demo` is untouched.
- `roles/architect/` and `roles/test-reviewer/` lose `ROLE.md`: after M9
  every one of the six roles has a prompt and at least one recorded run.

## Golden-rule check

A stranger with podman, git and sh: `./go demo` gains no stage, no pull, no
network call and no model — the 684 s cold figure is unchanged, because
ticket 0001 stays `low` and never enters `review`. `demo-review` and
`record-review` are manual; `record-review` refuses at L0 naming the profile,
and a missing review fixture is a loud failure naming the command, never a
skipped review or a default verdict. The two new `ci` checks run in the image
with no plane. Passes.
