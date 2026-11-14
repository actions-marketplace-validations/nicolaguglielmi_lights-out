# Handoff: stream A of the sprint of 2026-11-12, the release console (M47, M45, M46; ADRs 0078, 0079, 0080)

Branch `claude/sleepy-mcclintock-886394`, cut from dd79626. Main at a741bf0 (streams B and C) is merged in (cf825fc). Tip before this handoff: 72094f1. The branch is pushed with no pull request. Nothing is on main; the coordinator merges.

## What changed

Three slices, in the plan's order. Each one: ADR first, a WIP commit, tests written from the ADR by the `gate-writer` subagent in its own worktree, then the code.

- **M47, ADR 0078: the why of a NO-GO, one click away.**
  - Logbook 1.4 (`core/logbook/1.4.schema.json`) adds `why` on `ci` (null unless NO-GO) and on every `rework[]` entry. `why` is `{attempt, judge, gate, line, details, sast}`.
  - `details` and `sast` are withheld as `{ok:false, error:"withheld: …"}` unless the same entry's gate lines hold `GO: secrets`. This is ADR 0071's patch rule, applied to details. Where it withholds, the 1.3 `details` is null and the timeline draws no `gate` row.
  - Tower: `core/steps/ci.sh` copies `sast.json`'s `new` (`{rule,file,line}`) into `ci.sast` on a sast NO-GO. `core/steps/rework.sh` carries `failed` and `sast` into each rework entry.
  - Console: one `dialog#why`. It opens from the card's NO-GO chip, the back's and timeline's `gates`/`rework` rows, and `#network`'s NO-GO gate node and stream line. On `#network` the fact element itself is the opener, so its words stay equal to `./go network`. It shows the line, gate and judge, the details or the withheld reason, the SAST table, the attempt, the attempts left on `REWORK_MAX_ATTEMPTS`, and the next move (the now line, or "sent back to the dev-worker: attempt n+1").
  - Stub: ticket 0003 is now attempt 2: a `sast` NO-GO at attempt 1 and a `test` NO-GO at attempt 2. Golden: `fixtures/logbook/golden-1.4.json`. `golden-1.3.json` is kept as the old fixture.
- **M45, ADR 0079: the human gate on the card.** The owner's amendment of ADR 0059 §1 and ADR 0068 §1 applies to this gesture only.
  - `core/releases.py answer` writes `reason` (`GO_FOR_LAUNCH_REASON`), `brief_sha256` and `brief_author` (from `$PROMOTE_OUT`) into `promoted`/`rejected` and onto the release log's answer line. These are the names stream B reads.
  - Same `POST /v1/go-for-launch`, with one new optional field, `reason`. A NO-GO with a blank or missing reason gets 400 and nothing runs. The CLI never requires a reason.
  - The held release's card (`release.version` equal to the launch record, held, unanswered) is the only `draggable` card. `#drop-promote` and `#drop-rollback` are drop targets and buttons; Enter is the keyboard path.
  - The drop, the targets and `#launch`'s GO/NO-GO buttons open `dialog#launch-confirm`. `window.confirm` is gone. The dialog shows the brief, the verify thresholds with provenance, the stages, the risk, the PR's gate lines and the reason. Nothing is sent before `#lc-confirm`.
  - `./go demo-console` now runs two releases. The first is rolled back through the console with a reason; a NO-GO with no reason is refused first. The second is promoted with a reason. Each is checked in the record, the log and Envoy.
- **M46, ADR 0080: the live canary.**
  - Each stage gains `started_at`, `judged_at` and `slo: [{query, canary, stable, delta, max_delta}]`. `max_delta` comes from the effective policy, read by `core/releases.py` through `core/policy.py`. The `slo:` lines stay.
  - While a release runs, the record carries `running: {pct, started_at, judge_after_s}`. A rollback records `reason` (`<stage>: <why>`).
  - Console: `section#canary` on `#launch`, and at the top of the overview while a release is in progress. It shows one row per stage, with numbers against stable and threshold (`data-within`). The running row counts down against `read_at`, never the browser clock. A rollback shows the banner with its reason and marks the deciding stage. It is not a time series.

## Verified

- **`./go ci`** from a full clone under `.crew/`:
  - GO at 2decdcb (pre-merge, 295 s).
  - GO at cf825fc (the merge, 279 s).
  - GO at 4767528 (292 s). 72094f1 after it changes only the `demo-console` recipe.
- **`ci/console-ui.py`** in `localhost/m17-pw:dev`: GO at dcfb757 (M47), 2decdcb and 4767528 (final). The `gate-writer` agents report it GO at the M45 and M46 test commits.
- **`ci/logbook.sh`**: GO at the M47 commit in the workbench. The agents report it GO at M45 and M46. It is part of `./go ci` above.
- **`./go demo`, L0, no key, `APP_PORT=9000`, same machine, warm cache:**
  - Baseline dd79626 (main before the sprint): 681 s to rollback.
  - This branch at cf825fc: 655 s to rollback. Budget 900 s. No second more.
  - The record carried `reason`, the stage times and `slo`. That run showed the stable's error series is absent, so the deciding delta was null. 4767528 fixes the `slo` parse to treat it as zero, as verify does (ADR 0080 §1 amended, with tests). It changes no shell and no timing. The demo was not re-timed on it.
- **`./go demo-console`** locally (`./go up` first): GO at 72094f1, 259 s. One rollback and one promotion through the console, each with its reason and its own brief sha256 on the log's answer line.
- **Workflows on 72094f1, all green:**
  - ci 43333734946 (with `launch`/demo-console and `console-ui`)
  - self 43333735199
  - stranger 43333735108
  - podman 43333734998
  - package 43333734997
  - site did not trigger after cf825fc (its paths are unchanged since); on cf825fc it was green, 43330568523, over golden-1.4.
- **Found by CI and fixed:** the `ci` run 43330568466 on cf825fc failed in `launch`. `demo-console`'s second release had the same version, so it met the first release's brief still on disk: the console saw it pressable, not preparable. 72094f1 clears the brief before each release and waits until the console offers one to prepare.

## Deviations from the plan

- **The release role's brief run is not in the spend ledger.** This was stream C's request, left for later. `core/promote.sh` runs outside the tower and knows no ticket. Recording its `run.json` means a new write from promote into the StateStore, which ADR 0079 §2 rules out ("no new write path"). At L0 the brief is rendered by the script, so there is no run. It needs its own small ADR: which ticket (the release log's `ticket`), and who writes (the tower or promote).
- **`demo-console` takes one more release**, about 2 × `STAGE_SECONDS` more in the `launch` job. It is not in `./go demo`.
- **Shell debt.**
  - `core/launchpad.sh` is down from 72 to 70 code lines (the ratchet lowered in `ci/shell-boundary.sh`).
  - `core/steps/ci.sh` and `core/steps/rework.sh` are at their ceilings (85, 51).
  - The thresholds moved into Python to make that fit.
- **Files touched outside the stream's list:**
  - `core/steps/ci.sh`, `core/steps/rework.sh`: sast and failed.
  - `Makefile`: `demo-console` only.
  - `ci/promote.sh`, `ci/shell-boundary.sh`.
  - `core/tests/test_releases.py`.
  - The golden's path in `.github/workflows/site.yml`, `README.md` and `site/index.html`.
  - `docs/plans/console.md`, `console/README.md`.
- **Not touched, as agreed:** `core/audit.py`, the budget logic in `core/tower.py`, `profiles/`, and the dora, spend and evidence commands.

## For the coordinator

- Logbook 1.4 is the stream's single minor. Streams B and C read the record and the log directly. B's expected names (`started_at`, `judged_at`, `reason`, `brief_sha256`, `brief_author` on the answer line) match. The notes for B and C are in the shared notes folder: `sprint-a-release-console-notes.md`.
- The final console slice (the M48/M50 panels) can now build on logbook 1.4.
