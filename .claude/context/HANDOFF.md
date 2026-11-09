# Handoff: M17's first slice, the console says whose turn it is (ADR 0063), 2026-11-09

Branch `claude/console-ux-flow-1c108a`, on main 8e968aa. Pushed, no pull request, not merged:
landing is the owner's (or the coordinating session's). The previous handoff, of the merge of
M31, M34 and M35, is in main's history at 8e968aa.

## What the owner asked

UX work on the console's kanban and on the whole flow request → spec → build → test → release, as
one person follows one ticket. The launch gallery (Show HN, then Product Hunt) shows the kanban, a
ticket's timeline down to the rollback, and the overview.

## How it was done

1. **Audit by use, before any change.** The real console (`console/serve.py`, LIVE) over
   `ci/logbook.sh`'s stub root (its `mkroot`: the golden's stub tickets, stub StateStore and
   Delivery, stub `make answer` and `make request`), the real `core/logbook.sh` reading it every
   2 s. Ticket 0010 was filed in the request editor, keyboard only, and saved through
   `POST /v1/request`; its tower document was then staged by hand in the tower's own shapes,
   stage by stage, from `requested` to `held` and GO at 100%, and the other ending, rolled back
   at 5%. **No plane and no demo run**: the podman VM was busy with another session; the staged
   records are an audit harness and nothing of them is committed. Desktop 1440×900 and phone
   390×844, light and dark. Notes, the ranked findings, before/after screenshots (156 each) and a
   one-page list of what changed and what was left out are in the shared notes folder,
   `console-ux/` (`audit.md`, `CHANGES.md`, `before/`, `after/`).
2. **ADR 0063 first** (architect subagent), with the nine findings ranked by what they cost a
   first-time viewer, the chosen set, and the alternatives rejected. Filed in PLAN as **M17's first
   slice**, not M40: the adoption roadmap reserves M40 for "K7, Go then Java", and ADR 0047's open
   decision 2 folds M17 into the console. Acceptance criteria in PLAN before the code.
3. **Tests from the ADR** (gate-writer subagent, its worktree cut from the ADR commit, without the
   new page): `ci/logbook.sh` gains the cold table check; `ci/console-ui.py` gains g–k. On the old
   page every new section is NO-GO and a–f stay GO. Two corrections after the first run on the
   new page, one each way: the page drew an "Outcome" heading the ADR does not name (the page
   changed), and the test wanted a "now" stage for a state no band holds (`assigned`, golden 0004;
   the test was narrowed, said in the commit).
4. **The implementation** in `console/index.html` only; `console/serve.py`, the logbook (still
   1.2), its schema, the golden and the snapshot are unchanged.

## What changed

- **Kanban**: the columns, in the logbook's order, under four bands (Spec, Build, Test and review,
  Release; Other last); a column with no card in the view is 40 px; the golden's board fits 1440 px
  (1374 of 1374 px); below 720 px the columns stack and the nav scrolls in one line.
- **The now line** on every card, at the top of the drawer and at the head of the timeline: who has
  the ball and what it waits for, through the tower's table the page embeds
  (`script#tower-machine`: `next`, `who`, `bands`), checked against `core/tower.py` and
  `core/logbook.py` by `ci/logbook.sh`. "Your turn", with the one action, for an open question,
  `needs-human`, a failed step with no holder (`./go resume`, as text), and a held canary whose
  release is the unanswered launch record.
- **Timeline**: the now line, a strip of the four bands (done, now, stopped, skipped for a ticket
  opened directly), the rows grouped under the bands in the logbook's order, a link back to the
  card. The launch screen names the ticket its release carries.
- **Overview**: opens with "Waiting for you", then the tickets by band and state.
- **Editor**: the gate's line and Request in a bar held at the bottom; a save that wrote a ticket
  clears the form and links it.
- Small: `at` does not wrap; `gates` → `review` reads GO; a product row that asked reads "asked";
  the drawer drops empty Outcome and Line rows before a verdict.
- Docs: README, `docs/reference.md`, `ROADMAP.md`, `console/README.md`, `docs/plans/console.md`
  (the now-line rules; the amended "the console does not interpret states"), `site/index.html`
  and `site/render.py` (the kanban still drawn whole; a new still, `console-rollback`, ticket
  0001's timeline to the automatic rollback, dark). `docs/tutorial.md` does not describe the
  console, so it is unchanged. The README's images keep their names; `console-rollback.jpg` is
  on the site only, so the README links nothing that the site has not published yet.

## Checks

- Host: `ci/console-ui.py` GO (Playwright 1.64.1, 56 s); `ci/docs-drift.sh` GO with the
  Makefile's `MAP_EXCLUDE`.
- `./go ci` from a full clone of the branch head (`.crew/ci-clone`, the worktree cannot drive git
  in the workbench): see the Actions section below for the run on 27fc8cb; locally GO, every check
  of `CI_CHECKS` GO, `logbook` included.
- The proof that counts: the six workflows on the pushed branch (ci with `console-ui`, stranger,
  self, site, package, podman). Run ids and the demo lines are below.

## Left out, and why

- **F7**: a reworked ticket's first gates NO-GO row shows "—" because `core/logbook.py` keeps the
  line on the last `ci` only; a reader change and a logbook minor; the line is on the `rework`
  row. A follow-up.
- Renaming the columns (ADR 0055 §7), a docked drawer, an answer box in the drawer, a `now` field
  in the logbook, a committed snapshot of a real demo: ADR 0063, alternatives.
- An eighth column with cards scrolls sideways at 1440 px (ADR 0063, consequences).

## For whoever lands it

- Small, local edits where the coordinator expects conflicts: `docs/PLAN.md` gains one section,
  "M17, prima fetta", before "Dopo"; no `CI_CHECKS` change; this file is rewritten whole.
- The parallel session on `claude/festive-cray-5c155e` owns ADR 0062 and `ci/contract.sh`; this
  branch touches neither.
