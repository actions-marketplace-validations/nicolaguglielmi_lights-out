# ADR 0014 — A canary that clears every stage is held at 25% for the human gate instead of being retracted, and `demo-hold` proves that branch with the same release and the kill switch thrown

- Status: accepted (amends ADR 0013 §4: hold on green, exit code carries the
  branch, second acceptance target; extends ADR 0013 §6: `demo-hold` writes
  `app/flags/flags.json` and restores it). Amended by ADR 0019 §8: the human gate is M7, not M6 (re-dated by ADR 0019 §8). Amended by ADR 0020 [launchpad writes `RELEASE_RECORD`; the held line names `./go promote`].
- Date: 2026-09-14
- Milestone: M3

## Context

ADR 0013 §4 retracts a release that clears 5% and 25%: `rollback.sh` runs
before `[launchpad] 100%: NOT YET (M6, go-for-launch)`, "because promotion is
not built: nothing is left half-shifted". The only acceptance command,
`demo-rollback`, therefore exercises the NO-GO branch alone. A verify runner
wired to always NO-GO — a sign error in a threshold comparison, a query that
never matches — passes `demo-rollback` for the wrong reason and ends the run
on the same 100/0 plane a correct runner would, so nothing downstream catches
it either. The M3 plan review asks for the symmetric proof: same release, flag
off, verify GO, the canary advances to the human gate. That proof is
impossible while a clean pass and a rollback are indistinguishable in both the
exit code and the final plane state.

## Decision

1. **A release that clears every stage is held at the last shifted
   percentage; only a NO-GO calls `rollback.sh`** (amends ADR 0013 §4).
   `core/launchpad.sh` on a full pass leaves Envoy at `weights.canary=25`,
   prints `[launchpad] 25%: GO — canary holds 25% of traffic, waiting for
   go-for-launch` on stderr before the unchanged `[launchpad] 100%: NOT YET
   (M6, go-for-launch)`, and exits 0 with the single stdout line
   `GO: launchpad`. NO-GO is unchanged: `rollback.sh`, weights 0/100, exit 1,
   `NO-GO: launchpad — <stage>: <slo reason> → rolled back`. The exit code
   carries the branch, so an acceptance script reads which one ran instead of
   re-deriving it: `weights.canary=0` has two causes (retracted, or never
   shifted because deploy failed) and the exit code has one meaning each.
   Exit 0 means "reached the gate", not "promoted" — still true at M6 when the
   gate is a human — and it introduces no vendor word into `core/`: Cloud
   Deploy pauses a rollout at a phase awaiting approval, Envoy holds a weight,
   the controller says "held at 25%".
2. **The passing release is the failing one with the kill switch thrown
   first.** Same `CANARY_VERSION ?= 0.2.0-waitlist`, same image, same
   targeting rule; `make kill-switch` (ADR 0013 §6) runs before `release`, so
   the identical version evaluates `waitlist` off, the load loop gets 409 on
   both revisions, neither produces a 5xx, and `verify/slo.sh` reaches GO on
   real numbers. `kill-switch`'s own OFREP assertion with `{"context":
   {"version": "$CANARY_VERSION"}}` doubles as the wait for flagd's file
   poll: no sleep, and no race in which the canary fails on a stale flag. The
   target **must restore `app/flags/flags.json`**: copy it aside before
   `kill-switch`, restore in a `trap` on EXIT/INT/TERM. A copy, not
   `git checkout`: it needs no git in workbench and does not destroy a
   pre-existing edit. ADR 0013 §6's "`demo-rollback` never writes the tree"
   stands unchanged; `demo-hold` writes it and puts it back.
3. **The script asserts the shifted state, then rolls back itself.** The
   automatic-rollback-only-on-failure property is proven at the moment it
   matters — immediately after the controller exits — and the plane then
   returns to 100/0 so the next `./go demo` is repeatable. Leaving it shifted
   would route a quarter of the next `smoke` through a canary whose targeting
   rule is restored, i.e. intermittent 501s unrelated to anything under test.
   The cleanup rollback prints `[demo-hold] cleanup: rollback to 100/0 (not a
   verdict)` on stderr so no reader mistakes it for the controller's decision.
4. **The target is `demo-hold`** (`./go demo-hold`), manual, requiring a plane
   already up, exactly like `demo-rollback`; it is **not** added to
   `./go demo`'s fixed stage list (ADR 0003). The name says what happens to
   the traffic split, which is all M3 controls, and claims nothing about 100%,
   promotion or an approval — all M6. Stages and evidence:
   a. save `app/flags/flags.json`, arm the restore trap;
   b. `kill-switch`: OFREP answers `false` for `CANARY_VERSION` — flag state
      proven off before the release starts;
   c. `release` with the default `CANARY_VERSION` and `app/load.sh` beside it
      (ADR 0013 §4: the controller generates no traffic);
   d. controller exited 0 and stdout was exactly `GO: launchpad` — the branch,
      read from the controller;
   e. Envoy admin `GET /runtime`: `weights.canary=25`, `weights.stable=75` —
      the canary was not retracted;
   f. 40 `GET $APP_URL/healthz` through Envoy: both `CANARY_VERSION` and
      `STABLE_VERSION` appear at least once — the split is live traffic, not
      just a runtime key. 40: decision, from the binomial tail at p=0.25,
      P(no canary in 40) = 0.75^40 ≈ 1e-5, about a second of sampling;
   g. cleanup `rollback.sh`, re-assert `weights.canary=0`, trap restores the
      flag file; one final stdout line `GO: demo-hold`, as `demo-rollback`
      does. Neither is scanned by `ci/contract.sh` (`ci/ gates/ verify/`
      only): the shape is a convention here, not the gate contract.
5. **The 900 s verdict of ADR 0013 §7 is unchanged and stays scoped to
   `./go demo` and the rollback it reaches:** `demo-hold` carries no timing
   budget of its own, because none has provenance, and it neither reads nor
   sets `LIGHTS_OUT_T0` nor prints or alters the `make demo` verdict line.

## Alternatives rejected

- Keep the retract-on-green of ADR 0013 §4: the GO branch stays unobservable,
  and an always-NO-GO verify ends on the same plane a correct one does.
- A marker word in the controller's stdout (`GO: launchpad — held at 25%`): a
  third line shape for one bit the exit code already carries.
- The acceptance script re-deriving the branch from Envoy weights: 0 means
  both "retracted" and "deploy never shifted".
- A second known-good canary version (`0.2.0-ok`): it changes the release
  under test, so a verify keyed on the version string still passes, and it
  adds a second version string the Makefile default must track.
- `git checkout app/flags/flags.json` as the restore: assumes git in
  workbench and destroys any pre-existing edit to the file.
- `demo-promote` as the name: claims M6's promotion. `demo-gate`: collides
  with the one meaning "gate" has in this repo, the GO/NO-GO contract.
- Folding `demo-hold` into `./go demo`: plan §2's criterion is the automatic
  rollback, so the GO branch has no provenance as a timed requirement, and it
  would add about 140 s (two full stages) to the measured path.
- A `verify/slo-green.sh` twin for the passing case: a second copy of the
  thresholds; the proof must run the same `verify/slo.sh`.
- Leaving the canary shifted for manual inspection: the next `./go demo`
  starts from an unknown weight.

## Consequences

- "Nothing is left half-shifted" is now false on the GO path, deliberately:
  the plane really holds 25/75 between the controller's exit and the cleanup,
  because that is the state a human gate is supposed to inherit — a real
  canary sits at a shifted percentage until something promotes or rolls it
  back. A `demo-hold` killed mid-run leaves a stale weight; `make down`, a
  restarted Envoy (§3: the admin layer is in-memory, default 100/0) and the
  `rollback.sh` that opens every `launchpad` run each undo it.
- Two acceptance targets must now be kept in step: a change to the stage list,
  the version default or the thresholds has to be checked against both.
- `demo-hold` dirties the committed flag file for the length of the run; the
  trap restores it on exit and on signals, but a `kill -9` leaves it dirty and
  the stderr line names `git checkout app/flags/flags.json`.
- The kill switch becomes load-bearing in an acceptance path: breaking its jq
  or its OFREP assertion now breaks `demo-hold` too. That is the point, and
  the coupling is real.
- `demo-hold` costs about 140 s warm (arithmetic on ADR 0013 §5: staging ≤15 s
  + 2 × 60 s + verify and assertions), untimed and off the 900 s path; anyone
  who later folds it into `demo` redoes §5's budget.

## Golden-rule check

Nothing new: no image, dependency, port, key or account. `demo-hold` reuses
`launchpad`, the same `verify/slo.sh`, the existing `kill-switch` target and
the admin port ADR 0013 §3 already opened. It is not on `./go demo`'s path, so
a stranger's 15 minutes are unchanged; it is one optional ~140 s command for
whoever wants to watch the green branch. Passes.
