# Handoff: stream B of sprint 2026-11-14, M55 (the provider scoreboard, ADR 0088) and M56 (a read-only console snapshot, ADR 0089)

Branch `claude/public-proof-176b67`. Not merged, no PR. It holds origin/main up to 59e93e0 (M24's Gemini leg), merged
with main as the first parent. No live LLM run and no API spend. The plane ran twice locally, at `APP_PORT=9000`, and is
down.

## What is built

- **`./go scoreboard`** (`core/scoreboard.sh`, `core/scoreboard.py`, ADR 0088). It reads a curated dataset
  (`SCOREBOARD_DATA`, default `docs/scoreboard/m24-tenacity.json`) and any run logbooks (`SCOREBOARD_LOGBOOKS`). It prints
  one line per provider, harness and model:
  - tickets, merged, and merged at the first attempt;
  - reworks;
  - NO-GOs by gate and reason;
  - budget stops;
  - tokens per ticket;
  - cost per ticket on three bases: ledger, list and cached.

  A basis that no source gives is "not recorded". A provider that was planned but not run prints as not run, with the
  reason. Each total's note becomes a footnote. The page is self-contained (no script, no external resource), light and
  dark, and is published at `scoreboard/`.
- **The M24 dataset**: 20 rows, four totals and OpenAI as not run.
  - Every row names its handoff and its run:
    - phase B: `.claude/context/handoffs/claude-m24-phase-a-5dacb7.md` §6;
    - phase C: `docs/plans/m24-phase-c-handoff.md` §3;
    - Gemini: `.claude/context/handoffs/claude-m24-phase-d-gemini-1628f2.md` §2.
  - Each row was checked against its tower document on 2026-11-14: attempts, merge sha, PR number, rework lines, tokens
    per attempt, and the Gemini spend ledger (sum $8.782964 = the handoff's $8.78). The towers:
    - `optimistic-meitner-aed1df/.crew/full`;
    - `m24/m24c-crew/full`;
    - `m24/m24d-crew/full`.
  - Result: Anthropic 10/10 (8 merged at the first attempt, 2 mutation reworks, cost per ticket ≤ $0.18 list, ledger not
    recorded). Gemini 7/10 (0 reworks; 3 `TOKEN_BUDGET` stops; ledger $0.88, list ≤ $2.09, cached ~$0.36 per ticket).
- **`core/freeze.py`** (ADR 0089). It writes the console's own `index.html`, untouched, plus:
  - the logbook and a `console.json` answer (mode snapshot, auth public, `can_launch` false), inlined;
  - a `fetch` that answers the two reads and refuses every other request with 403;
  - a CSP of `default-src 'none'`;
  - a banner naming the run.

  It does not list panels: stream A's panels freeze as the page draws them.
- **Evidence pack**: `make evidence` writes the logbook first. `core/evidence.sh` then writes `<v>.console.html` beside
  the pack and signs and verifies it into its own bundle. The GO line ends `; console snapshot signed`, or `; no console
  snapshot: <why>`. The pack's JSON and ADR 0081's tests are unchanged.
- **Site**:
  - The landing links `scoreboard/` and `console/snapshot.html`.
  - A new stat card ("10 · 7 of 10", "not a benchmark").
  - "What is real" is updated: the scoreboard, the frozen console, and "Not yet" now names tenacity.
  - `site.yml` renders the scoreboard and runs `site/demo-logbook.py`. That script finds the newest successful `ci` run
    on main whose `console-snapshot` artifact holds `logbook-demo.json`, and freezes that logbook with this commit's
    console.
  - `site/render.py` opens the snapshot in Chromium in both themes. It fails on any request that leaves the file, on a
    header without "snapshot", on a ticket 0001 that does not reach the rollback, or on a go-for-launch button that can
    be pressed.
- **Docs**: ADRs 0088 and 0089, the reference (commands, "what is real", and two paragraphs), the tutorial (the
  `./go scoreboard` section and the evidence snapshot), and the PLAN under "Sprint 2026-11-14 — Il flusso a colpo
  d'occhio (M52–M56)". Stream A adds the same heading; keep one.

## Proofs

- **Tests**, written from the ADRs before the code:
  - `core/tests/test_scoreboard.py` (29) and `core/tests/test_freeze.py` (19).
  - `ci/evidence.sh` adds two cases. With a logbook: signed, verified, one byte rejected. Without one: GO, and the line
    says why.
  - All 1,376 core tests pass.
- **`./go ci`**: GO from a full clone, `.crew/pp-ci` at 4fd8340, in 307 s.
- **`./go demo`**: GO from the same clone, 867 s to rollback. The same day, main at bdc1943 took 886 s on the same
  machine (`.crew/pp-demo`). Both are inside the 900 s budget, but close to it; the first builds of the day count.
- **`./go evidence VERSION=0.2.0-waitlist`** after that demo: `GO: evidence — … signed and verified; 4 missing; console
  snapshot signed`. The `.console.html` is 1.4 MB.
- **`./go scoreboard SCOREBOARD_LOGBOOKS=.crew/logbook.json`**: GO, 2 groups run and 1 not run. The demo's replayed
  ticket is counted and not scored.
- **Workflows on 4fd8340**, all success:
  - ci 43578817482 (the `launch` job's evidence: "console snapshot signed");
  - site 43578817564 (`render: console/snapshot.html: frozen, read-only, nothing sent, in both themes`);
  - podman 43578817626, package 43578817520, stranger 43578817576;
  - self 43578817588: see the last section.
- **The site's snapshot** comes from ci run 43501367427 (5870da4, 2026-11-13), the newest successful main run with the
  artifact. Recent main runs skip `engine-compat` through `.github/plan.sh`, so they have none.

## Screenshots

In the shared notes folder, `public-proof-shots/`, taken with Playwright (localhost/m17-pw:dev) from `file://`:

- `scoreboard-light.png`, `scoreboard-dark.png`;
- `snapshot-{overview,ticket-0001,launch,kanban}-{light,dark}.png`.

The snapshot shots are of main's local demo (bdc1943).

## Deviations from the brief

1. **The demo logbook is not committed** (ADR 0089 §6). gitleaks reads a threshold's `key` as a secret, and a change
   cannot excuse its own finding (ADR 0049 §4, `site/render.py`). The site takes the logbook from the ci workflow's
   artifact instead. This also makes the snapshot the latest run with no capture to refresh. Costs:
   - the site build needs `actions: read`;
   - it fails when no recent full main run has the artifact, because a snapshot it cannot build is never linked;
   - the snapshot can trail main by the runs that skipped `engine-compat`.
2. **The scoreboard does not read the three M24 towers.** They are outside the repository, and the towers record neither
   the `TOKEN_BUDGET` stops nor the cached tokens. The curated dataset is the source the brief allowed, and every row is
   sourced.
3. **No hourly refresh.** It is one run per ticket and provider, and there is no spend.
4. **Phase B's per-ticket cost is not recorded.** Its handoff gives only the phase total, which is part of the ≤ $1.83
   Anthropic total. The board divides that total; it does not estimate per ticket.
5. **The site's stat card** "10 · 7 of 10" is new. The version was not moved.

## Follow-ups

- A full `ci` run on main (with `engine-compat`) after this lands would make the site's snapshot show this branch's
  console over a newer demo. Until then it freezes 5870da4's logbook with the new console.
- The M24 Gemini findings that the scoreboard surfaces: the ledger misses budget-stopped runs, and it drops `cached`.
  Fixing either would let a logbook carry what only the dataset carries today.

## self

Still running on 4fd8340 at the time of writing. The branch then moved to e86cc22: the tutorial line and the merge of
59e93e0, with main as the first parent. Its workflows were pushed after this file was first written. Read their verdicts
on the branch before landing.
