# ADR 0033 — A PR is judged by the base's gates and policy, and by its ticket's perimeter, in the tower's CI step

- Status: accepted (amends ADR 0019 §4 [the gates still run on the PR head, but the files that judge it come from the base]; amends ADR 0021 §5 [the perimeter is checked again in the CI step, not only in `core/crew.sh`])
- Date: 2026-11-02
- Ticket: 0007

## Context

`core/steps/ci.sh` ran `make gates` in a worktree at the PR head. The
Makefile, `gates/*.sh`, `ci/lib.sh`, `core/risk.py` and `policy/merge.env`
that judged the PR were the PR's own. A PR that added every level to
`RISK_AUTO_MERGE_LEVELS` routed itself to auto-merge: `RISK_HIGH_PLATFORM`
lists `policy/*`, but the copy that classified the PR was the PR's. The
ticket's `## Perimeter` was checked in `core/crew.sh` only, so a diff that
reached the code host any other way was never checked against it.

## Decision

1. **The code under test is the PR's; what judges it is the base's.** The
   step still adds a worktree at the PR head, then restores from
   `BASE_SHA`, with `git restore --source --staged --worktree` (no-overlay,
   so a file the PR adds there is removed too): `Makefile`, `profiles/`
   (the Makefile includes it), `gates/`, `ci/`, `core/`, `policy/` and
   `$WORKLOAD/workload.env` (the Makefile includes it; it carries the
   mutation baseline). Then `make gates BASE HEAD`, as before. A PR that
   edits any of these is classified by the base's `RISK_HIGH_PLATFORM`,
   so it is high risk and goes to review.
2. **The perimeter is checked again in the CI step.** Before any gate, the
   step fetches the ticket from the Tracker and pipes
   `git diff --name-only <merge-base> HEAD_SHA` into `core/perimeter.sh`,
   both from the tower's own checkout. A path outside the perimeter is
   `ci-failed` with `FAILED=perimeter` and the line
   `NO-GO: perimeter — <path> is outside …`, posted as the `gates` status.
   No gate runs. It stays a `core/` check and not a gate, for ADR 0021 §5's
   reason: gates know nothing about tickets.
3. **The test is `ci/tower.sh` case (g).** It runs the real step on a real
   git range with a stub CodeHost and Tracker, the base built from this
   checkout's judges with `GATES` narrowed to `risk` (the other five need
   an engine or the network). The PR loosens `policy/merge.env`. The test
   first checks that the PR's own policy would auto-merge it. Then it
   checks two verdicts: `review`, risk `high`, under a ticket whose
   perimeter holds the diff; `ci-failed` on `perimeter` under one whose
   perimeter does not.

## Alternatives rejected

- **A worktree at the base, gates run against the PR range.** `test`,
  `sast` and `mutation` run on the checked-out tree, so they would test the
  base's code and pass every PR.
- **Take only `policy/merge.env` from the base.** The PR could still
  rewrite `gates/risk.sh`, `core/risk.py` or the `gates` target to print an
  auto-merge. The judge is the whole chain, not one file.
- **Take the workload's build surface too (`compose.yaml`, `Containerfile`,
  `tests/`).** That is what the PR changes and what `test` must exercise. A
  legitimate PR that adds a dependency would be tested without it. Its
  edits are already high risk under the base policy (ADR 0030 §4).
- **A `gates/perimeter.sh`.** Rejected by ADR 0021 §5, for a reason that
  still holds: it would have to pass on any range with no ticket.

## Consequences

- A change to the judges is judged by the judges it replaces. A new gate
  takes effect on the PR after the one that adds it. That is the point.
- `core/steps/ci.sh` now needs `TRACKER` and `WORKLOAD` in its
  environment. `./go` and the Makefile export both.
- The PR's code still runs inside `backend-test` during `test`, `sast` and
  `mutation`. It cannot rewrite the risk decision: the decision is made in
  the workbench, from the git range, by the base's files. If a workload's
  `compose.yaml` ever bind-mounts the worktree into `backend-test`, that
  stops being true.
- `BASE_SHA` comes from the tower document (`pr.base_sha`, written by
  `assign` from the clone it started from). The PR does not set it.

## Golden-rule check

No new tool, no new service, no network. `ci/tower.sh` stays cold: two
local git repos and one `make gates` with `risk` only, a few seconds.
