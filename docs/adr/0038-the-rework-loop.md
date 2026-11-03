# ADR 0038 — The rework loop: a NO-GO before merge goes back to the dev-worker with the verdict, up to four attempts, then `needs-human`

- Status: accepted (amends ADR 0019 §1 [`ci-failed` is no longer terminal; `needs-human` is] and ADR 0021 §1 [`changes-requested` lands in `ci-failed`, which now requests `rework`]; consistent with ADR 0033 [every attempt is judged by the base] and ADR 0034 [a failed rework step strands the ticket, it never loops])
- Date: 2026-11-03
- Milestone: M15

## Context

Before M15 a NO-GO before merge ended the ticket. A PR-gate NO-GO put the
tower in `ci-failed`, terminal; a review that did not approve landed in the
same state; a failed step waited for `./go resume`. Nothing ever went back
to the worker with the reason it was rejected, which is how a human PR
author works: the reviewer or CI says why, the author fixes it, pushes
again.

The owner's goal (2026-11-03) names two loops: a **condition loop** (the
exit is judged by someone other than the maker: the gates) and a **review
loop** (review, address every finding, push again). Both stay before
merge. After merge nothing loops: a failing canary rolls back, and the one
human GO/NO-GO before 100% is unchanged.

Repo facts this rests on. `core/steps/ci.sh` and `core/steps/review.sh`
already print `ci-failed` for both rejections. `adapters/gitea/push.sh`
force-pushes and `open-pr.sh` reuses an open PR from the same branch, so a
second push on `ticket/<id>` is the same PR with a new head; `merge.sh`
merges only the head CI judged (ticket 0010). The harness port's input is
`TICKET_FILE` and its range starts at `BASE` (ADR 0017 §1); `gemini-cli`
uses both generically. `ci/lib.sh`'s `nogo REASON DETAILS…` already
separates the one-line reason from the details, which go to stderr only.

## Decision

1. **Two lines in the transition table, one new terminal state.**

   ```
    precondition()                       next()
      …                                    …
   +  rework)  'ci-failed'               +  ci-failed) 'rework'
   ```

   `ci-failed` means "the gates or the reviewer rejected this head" and now
   requests `rework`. `needs-human` is terminal and means "the cap was
   reached; a person decides". The step name equals the state it leaves
   from, as `review` does. `ci.sh` and `review.sh` print what they printed
   before.
2. **`core/steps/rework.sh` is a step, not a role.** It reads the document
   only: the attempt number `n` (`.attempt`, 1 for a document written
   before M15), and who rejected the head — `.ci.verdict == "NO-GO"` is the
   gates, otherwise `.review.verdict == "changes-requested"` is the
   reviewer, anything else is a step failure. It appends
   `{attempt, judge, head_sha, line, details, at}` to `.rework`, so the
   reason each attempt was sent back survives the next attempt overwriting
   `ci` and `review`. At `n >= REWORK_MAX_ATTEMPTS` it prints
   `{state: "needs-human"}` and runs nothing. Otherwise it runs
   `core/crew.sh` for attempt `n + 1` and prints `pr-opened` with the new
   head, `attempt: n + 1`, and `ci` and `review` set to null, so `merge`
   and `audit` can only read the new attempt's verdicts.
3. **The cap is four attempts per ticket: `policy/rework.env`,
   `REWORK_MAX_ATTEMPTS=4`.** Provenance: the owner's decision already
   recorded in `roles/dev-worker/role.env` at M5 — four dev-worker
   attempts per day — against an external constraint, the Gemini API free
   tier's 250 requests per day at `MAX_TURNS=60` (4 × 60 = 240 ≤ 250). Four
   full-budget attempts of one ticket fit one day's quota; a fifth could
   not run the same day anyway. The owner confirmed four for this loop on
   2026-11-03. Context, not source: at M9 the two blind
   `record` runs took 4 (ticket 0001) and 6 (ticket 0005) live attempts
   with no verdict to read. The policy is read from the tower's own
   checkout, never from the PR, and `policy/*` is already a platform path
   (high risk, ADR 0016), so an attempt cannot raise its own cap.
4. **What the worker gets: the ticket, the previous verdict, and its own
   previous diff in the workspace. Nothing else.** For attempt `n > 1`,
   `core/crew.sh` fetches `ticket/<id>` from the code host, refuses unless
   it is the head that was judged (`REWORK_HEAD`), and checks it out: the
   worker changes what it pushed, as a PR author does. The harness input
   (`TICKET_FILE`) is `.crew/<id>/input.md`: the ticket text, then the
   verdict document `rework.sh` wrote — the NO-GO line and the gate's own
   details, or the reviewer's verdict and reason. Never a transcript: the
   document is built from the tower document alone, and the reviewers keep
   reading only the ticket and the diff. Only the previous verdict, not
   all of them: the workspace already holds what the earlier ones changed.
5. **The gate's own details reach the document.** `nogo` also writes its
   DETAILS lines to `$NOGO_DETAILS` when the caller sets it; stdout is
   unchanged (one line, ADR 0011 §4). `make gates` sets it to
   `$(GATES_OUT)/<gate>.details` and `ci.sh` records the failed gate's lines
   as `ci.details` (for a perimeter NO-GO, the perimeter's own lines). For
   the mutation gate these are the surviving mutants, `file:line operator`.
   A gate whose details are thin (`test`: "see stderr") gives thin
   feedback; that is the gate's to improve, not the loop's.
6. **Every attempt passes the same judges.** Attempt `n + 1` is a new head
   through the same `ci` step: the base's Makefile, gates, policy and
   perimeter (ADR 0033), the same risk routing and, when routed, the same
   blind review. The perimeter is checked on the whole PR (fork point to
   the new head) against the untouched ticket file, before anything is
   pushed. `core/harness-check.sh` judges the attempt's own range: an
   attempt that changes nothing is a failure. An attempt that loosens a
   test is caught by mutation, one that touches a gate or the policy by
   the platform-risk paths — never by trusting the worker.
7. **A failed rework step is not an attempt.** No change, a perimeter
   breach, a missing fixture, a push that fails: the tower records the
   error and the ticket waits at `ci-failed` for `./go resume` (ADR 0034),
   at the same attempt number. Only a verdict advances the count. There is
   no path that requests `rework` without a verdict in between.
8. **Replay is keyed by attempt.** The harness gets `ATTEMPT`; a live
   harness ignores it (the verdict is in `TICKET_FILE`), `replay` replays
   `fixtures/<ticket>/<role>/attempt-<n>/` for `n > 1` and fails loudly,
   naming that path, when it is missing. `review.sh` passes the document's
   attempt too, so a reviewer replays the verdict recorded for that head.
9. **The history shows every attempt.** Each tower history entry gains
   `attempt` when the document has one (`assign` sets 1); `.rework` holds
   each rejected attempt's verdict, details and time. `./go audit` prints
   the trail and reads `needs-human` as a stopped PR.
10. **`./go demo-rework`** proves it live at L0 on ticket 0013 (ticket
    0001's bug restated with its test in `test_meetups.py`): attempt 1 is
    the committed `fake-test` change, NO-GO at mutation; the worker's input
    for attempt 2 carries that line and its survivors; attempt 2 posts the
    contract's 404 venue, the cumulative diff is `honest-fix`'s, GO; the
    tower merges it and releases, and the canary rolls back as in `./go
    e2e`. Both attempts are hand-written fixtures (`run.json`:
    `hand_written: true`, `model: null`), declared in the README. The cap
    is proved cold by `ci/tower.sh` case (k): a ticket the gates never
    pass stops at `needs-human` after four attempts.

## Alternatives rejected

- **The cap inside the tower** (when `ci-failed` would request a fifth
  attempt, write `needs-human` instead). A conditional transition: the
  table stops being a table, and the board's copy of it (ADR 0035) can no
  longer be checked line by line.
- **`./go resume` as the loop.** A human per attempt, and resume carries no
  verdict: it requests the same step from the same input.
- **A fresh workspace from the base every attempt.** The verdict names
  lines (`geocoder_client.py:26`) the worker could no longer see, and the
  diff the reviewer judged would vanish rather than be fixed.
- **A new harness variable for the verdict.** `TICKET_FILE` already is the
  instruction; a second input would change the port for every adapter.
- **A seventh "fixer" role.** The fix is dev-worker's job on dev-worker's
  ticket, under its own prompt and budget; `ci/roles.sh` keeps it at six.
- **Every previous verdict, or the previous conversation.** The workspace
  holds what earlier attempts changed; a transcript would hand the worker
  its own reasoning and the reviewer's, which is what keeps the judges
  outside the maker.
- **A distinct `changes-requested` state.** The two rejections differ only
  in who judged; `.rework[].judge` says so without a third table line.

## Consequences

- `ci/tower.sh` replaces its two "ci-failed is terminal" cases with the
  loop: gates NO-GO then GO, review rejection then approval, and the cap.
  Its `core/` becomes per-file links so `core/crew.sh` can be a stub while
  `core/steps/rework.sh` is the real one.
- `ci/contract.sh` checks that `nogo` with `NOGO_DETAILS` still prints one
  line and leaves the details in the file.
- The board's `tower-machine` table gains the two lines, its state list
  `needs-human`, and one scenario: "NO-GO, rework, GO".
- `demo-review` no longer expects `changes-requested` to end at
  `ci-failed`; its recorded verdict is an approval, unchanged.
- Recording a rework at L1 (a real attempt 2 against the real verdict) is
  not done here: it spends API tokens, and the owner decides when.

## Golden-rule check

`./go demo` runs `e2e` on ticket 0001, whose recorded attempt passes the
gates first time: the table's new lines are never taken, and the only
cost is one `jq` field per history entry. `./go demo-rework` is a separate
target, not in the demo's fixed list (ADR 0003).
