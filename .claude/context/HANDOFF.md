# Handoff: M33, the console as a workbench (ADR 0059), 2026-11-08

Branch `claude/m33-console-7b5d5d` (at c387961) and `claude/m33-console` (this handoff on top, pushed under a new name so the self workflow judges the whole range from main), rebased on main 7153de5. Pushed, no pull request, not merged: landing is the parent session's.

## Acceptance, on GitHub Actions

On c387961, six workflows green: ci 42435760042, stranger 42435759957, self 42435759934, site 42435759984, package 42435760204, podman 42435759945.

```
engine-compat  GO: demo, milestone M9, 834s to rollback (budget 900s, plan §2)
stranger       GO: demo, milestone M9, 828s to rollback
ci             GO: ci (599 unit tests, GO: logbook), console-ui job green, GO: demo-console in launch
```

The last main runs gave 807 s and 803 s: about 25 s more, from the demo's `ci` stage (a longer `ci/logbook.sh`). The margin on the 900 s budget is now about a minute.

## What changed

- ADR 0059, written before the code; tests written from it by a separate subagent (gate-writer) before it saw the implementation, then run against it: 310 unit tests of the four touched modules green, `ci/logbook.sh` GO on the host (dash).
- Kanban: drawer, search (id, title, perimeter path), keys, view in the hash, collapsible columns, a moved card marked for 4 s; still no drag-and-drop, proved by a static check and by `ci/console-ui.py` in a browser.
- Theme switch (system, light, dark) on the console and the board; the site's board videos pinned to the dark theme they were drawn in.
- Logbook 1.2: `adrs` from the project map (map schema 2: each ADR's status and text, `mentions` edges), each ticket's governing ADRs, the request row's by/via. `/v1/logbook.json` has an ETag.
- Specs screen; request editor whose live check is `/v1/spec-check`, `gates/spec.sh` itself on a temporary draft; the third write `/v1/request` (`core/spec.py draft` + `make request`, REQUEST_BY/REQUEST_VIA), refused in snapshot, public and for a NO-GO draft.

## Contradictions with the plan, and open points

- The plan says the product role "can ask its questions on the draft"; ADR 0059 routes them through the tower after the save, because a question on an unsaved draft would leave no record. At L0 it is never consulted on a new request.
- The plan asks `ci/logbook.sh` to prove the page's interactions; the workbench has no browser, so those proofs are `ci/console-ui.py` in a `console-ui` job of `ci.yml` (site.yml's Playwright image), not in `./go ci`.
- The logbook grows by the ADRs' text (about 700 kB on this repository); the ETag keeps it off the 2 s poll.
- Found, not changed: the board's scenarios still say `release` starts from `merged` (six console errors on load, present on main): they predate M30's `main-green`.
- On macOS `sh` (bash in POSIX mode) `ci/logbook.sh` fails on `VAR=… func` assignments; it is run in the workbench (dash), where it is GO.

## First thing for the next milestone

Open the console after `./go demo` and request a ticket from the editor at L0: the request row should say `via console`. Not tried on a live plane: after the spec gate the ticket goes on as any `./go request` does, and at L0 a new ticket has no recorded worker run, so watch where it stops and whether the console says why.
