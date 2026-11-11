# Handoff: M17's second slice, the Trello-style kanban (ADR 0068), 2026-11-11

Branch `claude/m17-kanban-trello-33fff3`, on main b395aff (0.3.1). Pushed. No pull request, nothing
merged, no tag: landing is the owner's, or the coordinating session's.

## What the owner asked

PLAN, "M17, seconda fetta": the kanban that makes a first-time viewer of the launch gallery say
"wow". It should have Trello's look and pace and the best usability possible, and lose nothing
that keeps it honest. No drag-and-drop that moves a card. One page, no build, no dependency, no
network asset.

## How it was done

1. **Before-screenshots** of the console over the golden logbook, before any change: desktop
   1440×900 and phone 390×844, light and dark, the kanban and three cards' backs. They are in the
   shared notes folder, `m17-trello/before/`.
2. **ADR 0068 first** (architect subagent), committed with the PLAN's acceptance criteria
   (Italian) before any code: ac248b6.
3. **Tests from the ADR** (gate-writer subagent, without the new page): 7eff42a.
   - `ci/console-ui.py` gains sections l to s. `ci/logbook.sh` proves the table's new `actor`.
   - On the old page (b395aff's `console/index.html`) the new suite is NO-GO at l (the labels).
   - On the new page it is GO.
   - Four defects were planted in the page one at a time, and each was caught:
     - a feature hue mod 5;
     - a flight under reduced motion;
     - a dark muted colour at 2.7:1;
     - a backdrop that does not close the back.
4. **The page** (`console/index.html` only) with the site and the docs: 8f2e83c.
   - Unchanged: `console/serve.py`, the logbook (still 1.2), its schema, the golden and the
     snapshot.
5. **One fix to the tests:** dd86a46. The gate-writer's edit took the space out of
   `mach bands-order '...'`, and `./go ci` stopped at `ci/logbook.sh: 625: 2: parameter not set`.

## What changed (ADR 0068)

- **The look.** Lists sit on a tinted board, with white cards, a soft shadow and a hover lift. Each
  band has a thin coloured rule above its name, never in the GO, waiting or NO-GO hues. The 40/140
  px widths and the 1440 fit of ADR 0063 are unchanged.
- **The card's face**, top to bottom:
  - priority and feature labels (a feature's colour is the sum of its UTF-16 units mod 6);
  - the title, with the search's match marked;
  - the unchanged now line;
  - a badge row: an icon for who has the ball, the time in the state, the rework attempts as pips,
    and the outcome.

  The actor comes from the embedded table's new `actor`, which `./go ci` checks against
  `core/tower.py`. A card whose turn is a person's has a bar on its edge. The time in the state
  counts to the console's `read_at` when live, and to the newest `at` in a snapshot. It never
  reads the viewer's clock.
- **The card's back** replaces the docked drawer. It is a native modal `<dialog>` over the dimmed
  board that keeps `aside#drawer[data-id]`. It shows:
  - the now line, with the one action drawn as a primary link;
  - the open question's text;
  - the band strip;
  - a compact timeline;
  - the perimeter, the wait, the ADRs and a link to the whole timeline.

  Esc, Close or the backdrop closes it, and the focus returns to the card. It is full screen below
  720 px. The answer box was weighed again and stays out: the kanban writes nothing (ADR 0059 §1).
- **Motion.** A moved card flies in 400 ms (FLIP, Web Animations), with no flight under
  `prefers-reduced-motion`. `#announce`, a polite live region, says which card moved and where. A
  long list scrolls inside itself with its header in view, from 720 px up.
- **Usability.**
  - "Your turn only" is in the link as `turn=you`; the key order is q, feature, priority, turn,
    group, empty, collapsed, card.
  - Below 720 px, a sticky band bar jumps to each band.
  - Focus is always drawn.
  - Contrast is WCAG 2.1 AA in both themes, and the suite measures it.
- **Site:** `site/render.py` adds the still `console-card` (0009's back, dark). The captions in
  `site/index.html` describe the new face and the back.
- **Docs:** README, `docs/reference.md`, `console/README.md`, `docs/plans/console.md` (a new
  section on what a card shows) and ROADMAP (an M17 second-slice row) are updated.
  `docs/tutorial.md` does not describe the console, so it is unchanged.

Rejected, with the reasons in the ADR:

- drag as a gesture that asks the tower for a step (the owner's decision, with its own ADR);
- chips instead of the selects;
- scroll-snap;
- a density switch;
- feature colours from a table;
- the time in a state measured against the viewer's clock;
- the Stitch loop (deferred: Stitch's export format is still unverified).

## Proof

- **Locally:**
  - `ci/console-ui.py` is GO, run with Playwright 1.64.1 through `uv run --with`.
  - `./go ci` is GO from a full clone of dd86a46 under `.crew/ci-m17`, including `docs-drift`
    and `logbook`.
- **GitHub Actions on dd86a46:** all six workflows are green: ci 42921648789, stranger 42921648855, self
    42921648862, site 42921648814, package 42921648792 and podman 42921648795.
    - The `console-ui` job printed `GO: console-ui`, with sections a to s.
    - Time to rollback: `GO: demo, milestone M9, 652s to rollback` on engine-compat and 570 s on
      stranger.
    - The two `lights-out gates` Action-test jobs marked failure are the ones named "NO-GO
      expected". The run succeeded.
  - **The `site-review` artifact of site 42921648814**, looked at:
    - `console-kanban.jpg` is the whole golden board at 1440: coloured band rules, labels on 0009
      and 0001, the edge bar on the four "Your turn" cards, and the badge rows with actor, age and
      pips.
    - `console-card.jpg` is new: 0009's back, dark, over the dimmed board. It shows the Answer it
      button, the spec gate's question, the band strip with Spec current, and the six compact rows
      down to the spec gate's NO-GO.
    - The other five stills render, unchanged in content.
    - One difference from the local screenshots: the CI image's font draws the card titles in a
      regular weight, not bold.
- **Screenshots** are in the shared notes folder
  (`~/Library/Application Support/Claude/side-session-notes/local_8c7f0a84-f30c-438c-b776-32f7fc434b51/m17-trello/`):
  - `before/` and `after/` use the same names: `kanban-{desktop,phone}-{light,dark}[-full].png`
    and `back-{0009,0001,0003}-{desktop,phone}-{light,dark}.png`;
  - `after/only-mine-*.png` shows "Your turn only";
  - `audit.md` is the audit run again, compared with the one of 2026-11-09.

## Open

- **Usability with people who do not know the project:** not run. It is the owner's to organise
  (ADR 0068 §8).
- **The audit's live walk:** the staged ticket over the stub root was not repeated, because the
  podman VM was busy with M24. A live move is proven only by section o, which simulates a live
  console in the browser.
- **Small findings:**
  - On a phone, the back's compact timeline puts the `at` on its own line.
  - 0009 reads `0m` in a snapshot, because its event is the newest one.
- **F7** (a reworked ticket's first gates row) is still a reader change and a logbook minor.
- **ADR 0068 is *proposed*.** The answer box in the back is kept as the alternative, if the owner
  wants one place fewer to go.
