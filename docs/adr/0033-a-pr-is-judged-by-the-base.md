# ADR 0033 — A PR is judged by the base's gates and policy, and by its ticket's perimeter, in the tower's CI step

- Status: accepted (amends ADR 0019 §4 [the gates still run on the PR head, but the files that judge it come from the base]; amends ADR 0021 §5 [the perimeter is checked again in the CI step, not only in `core/crew.sh`]); amended 2026-11-04 [the contract's `runners/` joins its judges, the set ADR 0045 §3's wrapper already takes]
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
3. **The test is `ci/tower.sh` case (h).** It runs the real step on a real
   git range with a stub CodeHost and Tracker, the base built from this
   checkout's judges with `GATES` narrowed to `risk` (the other five need
   an engine or the network). The PR loosens `policy/merge.env`. The test
   first checks that the PR's own policy would auto-merge it. Then it
   checks two verdicts: `review`, risk `high`, under a ticket whose
   perimeter holds the diff (h1); `ci-failed` on `perimeter` under one whose
   perimeter does not (h2).

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

## Amendment, 2026-11-04 (ADR 0042, 0045)

**Context.** ADR 0042 §6–§7 added `runners/` to the gates half of a
contract: `SAST_CMD` and `MUTATION_CMD` call `.lights-out/runners/*.sh`.
The step restored the contract's `workload.env` and `policy.env` (§1, ADR
0037 §4), not its runners. So a PR could rewrite `runners/sast.sh` to
print `{"findings": 0}`, and the base's `sast` gate would trust it. The
risk gate's `.lights-out/*` → high still blocked auto-merge, but the sast
and mutation verdicts the reviewer saw came from the PR's own runners.
The wrapper (ADR 0045 §3) already restores the base's runners.

**Decision.**

1. **The contract's judges are `workload.env`, `policy.env` and
   `runners/`, taken from `BASE_SHA`, no-overlay.** This is the set
   `package/entrypoint.sh` restores, with no fourth path. A judge that
   neither side has is left out of the pathspec. When the base has no
   `runners/` and the PR adds one, the PR's copy is removed, as with
   `policy.env`. The step adds `${contract}runners` to both lists:
   - attached: `${contract}workload.env ${contract}policy.env ${contract}runners`
   - bundled: `Makefile profiles gates ci core policy` + the same three.

   There is one definition of the contract's judges, wherever the
   contract lives. The bundled entry costs nothing: no bundled contract
   has a `runners/` today.
2. **Not taken from the base, one reason each.**
   - `worker.md`: the dev-worker's brief. It is read before the PR
     exists, and no gate reads it.
   - `tickets/`: the step reads the ticket from the Tracker, outside the
     worktree (§2). A copy in the worktree is read by nothing.
   - The plane half (`compose.yaml`, `flags/flags.json`, `smoke.sh`,
     `load.sh`, `fixtures/gates/`): no gate reads it, except
     `compose.yaml`, which is build surface that `test` must exercise.
     The third rejected alternative above still holds.

   An edit to any of these is high under `.lights-out/*`.
3. **The test is `ci/attach.sh` case (f), next to (b) and (c).**
   - **Setup.** The base's contract has `TOOLCHAIN_IMAGE=workbench`,
     `SAST_CMD=sh .lights-out/runners/sast.sh`, and a runner that
     reports one finding. The PR's ticket perimeter holds that runner,
     and the PR rewrites it to report none.
   - **Premise.** The test first shows that the head's own `SAST_CMD`,
     run in-process on the head, reports zero findings.
   - **Verdict.** The real step must return `ci-failed`, verdict
     `NO-GO`, failed `sast`, with a line that names the base's finding.
   - **The `sast` gate is a stand-in.** The test's platform root
     replaces `gates/sast.sh` with a script that runs the worktree's
     `SAST_CMD` in-process. The real gate runs under the step's
     `TOOLCHAIN_ISOLATE=1`, which needs the engine socket, and `./go ci`
     mounts none. The real gate would NO-GO on the socket, and the case
     would pass for the wrong reason. What is under test is the restore,
     not the gate.

**Alternatives rejected.**

- *Attached list only:* this gives two definitions of the contract's
  judges, and the gap reopens silently once a bundled `SAST_CMD` calls
  `runners/`.
- *Run case (f) only when an engine is present:* a skip is a green that
  proved nothing.
- *A switch that turns isolation off for the test:* it would be a
  product knob that exists only for a test, and it would remove what
  keeps a PR's code out of the tower's container.

**Consequences.**

- **Runners outside `runners/` remain the PR's.** This covers bundled
  `app/tests/{sast,mutation}/run.sh`, and also an attached contract whose
  command calls `tests/sast/run.sh`, as `workloads/minimal` does. These
  are the build surface of §1. Editing them is always high: the platform
  `RISK_HIGH_PLATFORM` lists `*tests/sast/*` and `*tests/mutation/*`, no
  `policy.env` can override it (it is not in `core/policy.py`
  `OVERRIDABLE`), and high never auto-merges. The sast or mutation GO on
  such a PR is still the PR's own claim. The reviewer must not read it as
  evidence.
- **A legitimate runner change (a new bandit pin) is judged by the old
  runner.** It takes effect from the next PR onward.
- **The same three paths now live in two places**, `core/steps/ci.sh`
  and `package/entrypoint.sh`. A fourth path must be added in both;
  ci/attach.sh (f) and the wrapper's test catch only the paths they name.
- **Golden rule:** the demo path is untouched, and case (f) is local git
  with no engine.
