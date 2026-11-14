# Handoff: the sprint of 2026-11-14, stream A, the console (M52–M54; ADRs 0085, 0086, 0087)

Branch `claude/console-flow-313acd`, cut from bdc1943, with main (59e93e0, the M24 Gemini landing) merged in as
the first parent at aa535b2. Pushed, no pull request. Nothing is on main; the coordinator merges.

## What changed

ADRs first (e889f92), then the tests written from them, then the code, milestone by milestone.

- **M52, the flow strip (ADR 0085).** Logbook 1.6 carries `tickets[].flow`: fourteen nodes (ticket, perimeter,
  the eight gates in the Makefile's order, PR, canary, human gate, 100%), each with its verdict (GO, NO-GO,
  running, not reached), its times from the record, its seconds and its one-line reason. The logbook computes the
  nodes; the page draws them. One fact was truly missing, each gate's time: the `gates` recipe now writes
  `$(GATES_OUT)/seconds`, `core/steps/ci.sh` records `ci.seconds`, `core/steps/rework.sh` copies it into the
  rework entry. The card's face shows the strip compact (one accessible name, no tab stop: the card stays the
  board's keyboard unit); the card's back and the timeline make every node a tab stop with its reason on hover and
  focus, and a NO-GO gate opens M47's why panel by click or Enter.
- **M53, the role matrix (ADR 0086).** Logbook `roles` (one row per `roles/` directory, the network table's
  order): provider and model from the profile, harness from `role.env` or the profile, thinking, `TOKEN_BUDGET`,
  the role's last run from the ledger, its run in flight, tokens used, state and one line; `roles_summary` counts
  the providers. `section#roles` on the Overview after "Waiting for you", with meters. No model id in `core/`,
  `gates/`, `verify/`, `roles/` (`ci/model-free` and `ci/app-free` caught two in my tests; fixed by reading the
  stub's own values).
- **M54, the burn and the run in flight (ADR 0087).**
  - The ledger fix (the M24 phase D follow-up): when `assign` or `rework` fails, the tower appends the run the
    crew left in `.crew/<ticket>/out/run.json` during the step, with `failed` = the stop marker (`TOKEN_BUDGET`,
    `MAX_TURNS`, else `the run failed`). gemini-cli and antigravity-cli now write `run.json` before exiting on
    `TOKEN_BUDGET` (claude-code and codex already did); `harness-conformance` case 6 asserts it for every harness.
  - `./go spend` prints `burn:` (known cost per hour of the last day with a run, over at least one hour) and
    `projection:` (that day at that rate to 24:00 UTC against `SPEND_BUDGET_DAY_USD`), as of the last run: the
    logbook still reads no clock. The panel shows both, a 24-bar inline-SVG sparkline and `data-over`.
  - `tickets[].live`: the dev-worker's attempt in flight from the budget hooks' count (`.crew/<id>/out/tokens`),
    against `TOKEN_BUDGET`, `warn` from 80% (provenance in the ADR: proposed, the owner's to confirm; M24's ~45k
    tokens per Gemini call leave ~11 calls between warning and stop). Shown on the card (badge + meter), the
    back, the timeline, the spend panel and the dev-worker's matrix row. At L0 the replay harness keeps no count,
    so nothing shows in the demo.
- **Logbook 1.6** (`core/logbook/1.6.schema.json`, additions only, validates against 1.0–1.6);
  `golden-1.6.json` by the reader over the stub; `golden-1.5.json` kept as the old fixture. The stub gained
  `roles/` (the committed `role.env` keys), `crew/0003/out/tokens` (2,210,000) and `ci.seconds` on 0003 and 0010.
- **Docs**: the three ADRs, ADR 0083 points at 0087, `docs/plans/console.md` (1.6 table and DOM contract),
  `console/README.md`, `docs/reference.md`, `README.md`, the plan's sprint heading and M52–M54 criteria, the
  golden's path in `site.yml` and `site/render.py`.

## DOM contracts for stream B's static snapshot

Unchanged: every id and class that existed. Added (also in `docs/plans/console.md`, "1.6"): card face
`ol.flow[role=img]` > `li.flow-node[data-node][data-gate][data-verdict][title]`, `span.live[data-warn]`; back
`ol.flow.flow-detail`; timeline `ol#flow.flow-detail` (nodes `tabindex=0`, `.flow-why` via `aria-describedby`,
`data-seconds`); `p.live-line`; Overview `section#roles` (`#roles-summary`, `table#role-matrix`,
`tr.role-row[data-role]`, `td[data-provider]`, `td.harness`, `td.thinking`, `td.tokens`, `td.state`); in
`section#spend` `#spend-burn`, `svg#spend-hours` (24 `rect.hour[data-hour]`), `#spend-projection[data-over]`,
`ul#spend-live`.

## Site text for the coordinator (I did not edit `site/index.html`)

- The shots note: `fixtures/logbook/golden-1.5.json` → `fixtures/logbook/golden-1.6.json` (docs-drift does not
  catch it: the 1.5 file still exists).
- Proposed lines for the console section, in the site's voice:
  - "Every card carries its ticket's path in one row: the request, the perimeter, the eight gates in the order the
    tower runs them, the PR, the canary, the human gate and 100%. Each node says GO, NO-GO, running or not
    reached, how long it took and why; on the card's back each one is a tab stop."
  - "Who runs each role: the provider, the harness, the thinking level and the tokens of the last run against its
    budget, side by side for the six roles."
  - "The spend panel shows the burn per hour, the day's projection against its limit, and the attempt in flight
    against its token budget, with a warning before the stop. A run stopped by its budget is in the ledger too."

## Verified

- `core/tests` (unittest) all green on the host; `ci/tower.sh` GO, and NO-GO with `core/steps/ci.sh` or the
  Makefile reverted (planted).
- `ci/console-ui.py` in `localhost/m17-pw:dev`: GO with the new `ae` (strip), `af` (roles), `ag` (burn, live).
- `ci/logbook.sh`: every 1.6 hand check and plant passes on the host; its one host-only failure (a 403 vs 409 in the
  runtime press, also on main) does not occur in the workbench.
- `./go ci` from a full clone under `.crew/`: GO at a2800db, 52 GO lines, 355 s.
- `./go demo` from a second full clone (L0, no key, `APP_PORT=9000` in its `.env`): GO, 886 s to rollback
  (budget 900 s). A `./go ci` ran in the other clone for the first minutes of it; stream A of the last sprint
  measured 655 s, M51's local run 1,235 s. `./go spend` after it is the tutorial's new excerpt. `./go down` after.
- `./go ci` again at 848ec6a (the conformance fix and the docs): GO, 52 GO lines, 309 s.
- `harness-conformance-proof` in the workbench image: GO, with the new planted `no-run-on-stop`.
- docs-drift (`MAP_EXCLUDE='docs/PLAN.md docs/plans/* .claude/*'`): GO.
- Workflows on a2800db: package 43580898357, site 43580898353, stranger 43580898449 green; ci 43580898350 and
  podman 43580898371 red at `harness-conformance` case 6: the suite's own good fake-cli did not write `run.json` on
  its budget stop. Fixed in 1963239, with a
  planted fake that does not.
- Workflows on 848ec6a, all green: ci 43582541787 (the `gitlab` job re-run once: GitLab answered 400 to the merge
  request right after the push, a timing flake; it passed at a2800db with the same code), self 43582541829,
  stranger 43582541789, podman 43582541786, package 43582541792. site is not triggered by this push (path filter);
  it was green at a2800db. The two `Action test … NO-GO expected` check runs are red by design, as on every green
  branch.
- Screenshots of the three panels, light and dark: the shared notes folder, `console-flow/shots/` (12 PNGs).

## Deviations and left out

- `harness-conformance.sh` sits on the shell-boundary debt list (693 lines, can only go down): the case-6 check
  replaced its line instead of adding one, so the count is unchanged.
- The network harness's members are not read for a failed run (a member that stops leaves the network's
  `run.json` unwritten). The light gate tier records no seconds. Cached-input pricing (M24 finding 2) is its own
  change.
- `.claude/context/HANDOFF.md` untouched (it conflicts at every landing).
