# Handoff: M29, the dev phase visible from request to release (ADR 0055), 2026-11-07, branch `claude/m29-dev-visible-90a231`

Not merged: the parent session lands it after the five workflows are green on the pushed head. Rebased onto main 373da51 (M28 and M27 landed).

## Acceptance

```
./go ci (local, clean clone of 1bb611b)  → GO: ci (dev-phase and logbook new; core unit tests 368 → 459)
GitHub Actions, run 42406976968 on 1bb611b:
  engine-compat ./go demo  → GO: demo, milestone M9, 681s to rollback (budget 900s)
    [tower] 0001: requested → clarify (3 s, product not consulted: no recording) → spec-ready → GO: spec → opened
  engine-compat logbook    → ticket 0001: request, product, spec GO, assign PR #1, attempt, gates, merge,
                             canary NO-GO, release rolled-back, outcome NO-GO; kanban card in rolled-back
  launch ./go demo-console → GO: demo-console
```

## What changed

- Step 0, the console recovered (one commit, rebased from `merge/console`, which is untouched): the cost fields and the release log moved to `core/tower.py task` and `core/releases.py` (shell-boundary debt down, not up); `perimeter.sh --list` dropped.
- `requested → questions → spec-ready → opened`: `./go request`, `./go answer`, steps clarify/answer/spec, `gates/spec.sh`, `core/spec.py`; the adk harness takes ANSWERS as later turns and says `no_recording` under replay.
- Logbook 1.1: per-ticket timeline, feature/priority, wait (M27's refused assign + `perimeters/held`), map (M28's docs ticket); top-level kanban, perimeters_held, docs_to_realign.
- Console: overview, kanban (no drag-and-drop), timeline screen, answer box (`POST /v1/answer` runs `make answer`).
- `ci/dev-phase.sh`: the gate's GO and two NO-GOs, and the state table on the product role's own recording.

## Contradictions with the plan

- The brief said the logbook's cost fields were written into `core/tower.sh`; they were in the step scripts, `promote.sh` and `launchpad.sh`.
- The console branch could not be merged as it was: two commits authored outside the project identity, and a golden line the history secret scan flags.
- `demo-console` was red in CI once: `demo-launch` runs before it in the launch job and left a brief of the same version, so the console had nothing to prepare. Fixed in the recipe.

## Next

The worker still reads `tickets/<id>.md`, not `.crew/<id>/spec.md` with the confirmed criteria (ADR 0055 Consequences). Recording the product role on ticket 0001 (`./go record-evals PROFILE=l1`) is the owner's.
