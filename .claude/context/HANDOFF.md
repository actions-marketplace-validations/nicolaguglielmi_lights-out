# Handoff: M30, main always green without a queue (ADR 0056), 2026-11-07

Branch `claude/m30-mainline-on-m29`, rebased on main 1f48e4a (M27, M28, M29); the earlier `claude/m30-mainline-f7ffa4` is the same work on 373da51. Pushed, no pull request, not merged: landing is the parent session's. With M29, `main-green` is a column of the logbook's kanban and of the console, and a red main does not stop M29's `clarify`, `answer` and `spec` (no code yet).

## Acceptance, on GitHub Actions (the owner moved engine-heavy runs there)

On 373da51, before the M29 rebase:

```
c824de0: ci, package, stranger, podman, self — all success
ci 42407872153
  mainline       GO: demo-mainline                       (job 444 s, plane included)
  engine-compat  GO: demo, milestone M9, 729s to rollback (budget 900s, plan §2)
  ci             GO: ci (442 unit tests, ci-mainline)
stranger         GO: demo, milestone M9, 780s to rollback
```

`demo-mainline`'s own lines: 0020 and 0021 merged onto a main a person's merge had moved, without re-judging; 0022 sent back with `NO-GO: base — main moved under the perimeter since <base>: app/backend/meetups/db.py by <the person's merge>`; main NO-GO, bisected in two gate runs to 0021's merge, reverted through Gitea (a revert PR, never a force push), main GO again by the same-tree rule; 0020 releases the green main. The release and the two attempts 2 are requested and left to `e2e` and `demo-rework`, as the demo says.

## What changed

- ADR 0056, written first, revised after an architect review. `core/mainline.py` (`rejudge`, `check`), `core/steps/mainline.sh`, `policy/mainline.env` (`MAINLINE_GROUP_MAX=4`).
- The table: `merged` → `mainline` → `main-green` → `release`; `mainline` can print `ci-failed`. The board's copy follows. The tower refuses `assign`, `rework` and `release` while `mainline/main` is red.
- `merge.sh` runs the re-judge rule before the adapter (and before M28's map block); `rework.sh` reads `.mainline` first; `crew.sh` starts a tower-sent rework from main's head (`REWORK_FRESH`) and never resets main on a rework; `release.sh` releases `mainline.green`; `core/assign.py` holds a perimeter through `merged` (amends ADR 0053 §5).
- Gitea's merge verb waits out the 405 Gitea gives while it re-checks a PR whose base moved.
- Tickets 0020–0022 with hand-written fixtures, `fixtures/mainline/outside.patch`, `./go demo-mainline`, a `mainline` job in `ci.yml`; README, reference and architecture.

## Contradictions with the plan, and open points

- PLAN M30 says the main check runs "the workload's gates": ADR 0056 narrows it to `sast test` on purpose (the diff gates judged each PR's own diff; the ticket-bound ones have no ticket on main).
- `MAINLINE_GROUP_MAX=4`'s provenance is the free-tier four-attempts-a-day decision; it does not bound outside merges or other providers. The owner should confirm or replace it.
- L0's Gitea bootstrap still force-pushes main at attempt 1: an `assign` after a merge in the same run (ADR 0053's resume) resets main under merged tickets, and their `mainline` step then fails on a merge not on main.
- The GitHub merge verb has not been exercised on a moved base.
- The mainline integration tests make the `unittest` suite slower; the self gate's mutation of `core/` pays it per mutant.

## First thing for the next milestone

M24 is the first run with several tickets in flight on a repository with human merges: watch `mainline/main` and the `base` reworks there, and the cost of the main check's gate runs per group.
