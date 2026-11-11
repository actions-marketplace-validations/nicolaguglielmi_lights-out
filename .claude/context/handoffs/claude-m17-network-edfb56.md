# Handoff: M17's third slice, the governed network on screen and in text (ADR 0071), 2026-11-11

Branch `claude/m17-network-edfb56`, cut from the integration branch `fix/adr-still-header` (98f49e8: M17's second slice and M39). Pushed; no pull request, nothing merged, no tag. Landing it is the coordinator's and the owner's.

## Acceptance

- `./go ci` GO from a clean clone under `.crew/` on 82ced75 and again on 635a79c (`GO: ci`, every check GO, `logbook`, `tower`, `network`, `shell-boundary`, `docs-drift`, `contract` included).
- 905 unit tests (`python3 -m unittest discover -s core/tests`), one skipped by design (`test_network`: a template that takes arguments).
- `ci/console-ui.py`: `GO: console-ui` locally in the pinned Playwright image and in `ci`'s `console-ui` job.
- GitHub Actions on 82ced75, six workflows green: ci 43006233004 (its `console-ui`, `launch`, `engine-compat` and the other jobs green), stranger 43006233050 (`./go demo` at L0, no key, no engine variable: `GO: demo, milestone M9, 668s to rollback`, the rollback on `NO-GO: launchpad — 5%: error_rate canary(0.2.0-waitlist)=1.000 …`), self 43006233021, site 43006233324, package 43006232993, podman 43006233201.
- 635a79c (the replay draws the attempt of the row it reveals; the plan's status; ADR item 12): six workflows green: ci 43010420261 (`console-ui`, `launch`, `engine-compat` and the rest), stranger 43010419712 (`GO: demo, milestone M9, 555s to rollback` at L0, no key), self 43010419699, site 43010419713, package 43010419749, podman 43010420242.

## What was built

- **ADR 0071** (architect), then the slice and its acceptance criteria in `docs/PLAN.md` (Italian) before any code, then the tests from two gate-writer subagents, written from the ADR and a contract fixed before the code (`m17-network/contract-0071.md` in the shared notes folder), in worktrees that never saw the implementation. Readings the tests and the code had to settle are in the ADR's "Decided at build".
- **Logbook 1.3** (`core/logbook/1.3.schema.json`, optional additions only): `core/tower.py task --patch` keeps a network attempt's `members` and the attempt's `patch` (cut at 65,536 bytes at a newline) and `files` (+/− per path, the member by perimeter glob); `core/steps/ci.sh` records every gate's line (`ci.lines`), `rework.sh` copies them into the rework entry (no shell count rose); the reader turns them into `ci.gates` / `rework[].gates`, withholds a patch unless that attempt's `secrets` gate said GO, and adds `tickets[].files` (glob, worker, attempts, tests from the map's `tests` edges, ADRs, who holds it). `fixtures/logbook/golden-1.3.json` is the reader's output over the stubs, with ticket 0010 (a two-member network, mutation NO-GO, rework, eight GO, review, held at 25%, bob's GO) and 0004 (an attempt in flight, its patch withheld); `golden-1.2.json` stays as the old-logbook fixture.
- **`./go network [TICKET=] [ATTEMPT=] [NETWORK_LOGBOOK=]`** (`core/network.py`): the screen's facts in text, from one table of words (`--table`) the page embeds as `#network-words`; `ci/logbook.sh` proves the copy, its roles (`roles/`) and its gates (the Makefile's `GATES`), and that `make network` prints what `core/network.py` prints. A view, not a gate: exit 1 for an unreadable logbook, 2 for an unknown ticket or attempt.
- **`#network` in the console**: inline SVG of the tower, the six roles, the workers with harness and model, the gates lighting GO / NO-GO / not run, the review, the rework loop, the canary stages and the human gate; beside it every attempt with its files, verbatim gate lines and patch; below, the files by perimeter. Live: facts a new logbook adds are marked 4 s and announced. Replay (button or `?replay=1`): one timeline row every 2 s under "Replay of the recorded logbook: nothing is running", no request; the graph draws the attempt of the row revealed, so 0010's first attempt lights its mutation NO-GO before the second runs. A 1.2 logbook draws one summary gate edge and says it records no patches or gate lines. The console writes nothing new; no `draggable`.
- **Site**: `site/render.py` records `media/network.mp4` (34 s, 1600×900) and `network.jpg` from the replay of 0010 over the golden, captioned on every frame "Replay of a recorded logbook · nothing is running"; `site/index.html` shows it in the console section with a caption that says it is a replay of stub data, not a real run. `site.yml` follows the golden's new name and uploads `network.jpg` and `network.mp4` in `site-review`.
- Docs: README, `docs/reference.md`, `console/README.md`, `docs/plans/console.md` (1.3 field by field), the Makefile's and `./go`'s help.

## What I saw in `site-review` (site 43006233324, 82ced75)

`network.mp4` 1600×900, 32.9 s; `render: network.mp4: replay of ticket 0010, 14 rows, 33 s`. Frames at 3, 12 and 22 s: the caption bar at the bottom and the replay label at the top on every frame; nodes dimmed until their row, the facts list growing row by row, the stream showing attempt 2's patch. On that commit the graph showed only the final attempt during the replay, so attempt 1's NO-GO never lit in the video: 635a79c fixes that (a local render in the same image shows mutation red at 9 s). The seven console stills are now rendered over golden-1.3 and look as before, with 0010 as one more card in `held`.

On 635a79c (site 43010419713): `render: network.mp4: replay of ticket 0010, 14 rows, 33 s`; the frame at 9 s shows the graph at attempt 1 with risk to test GO, mutation red and test-proof not run, the stream holding attempt 1 alone with its NO-GO line in red; at the end the static drawing of attempt 2. Copied to `after/network-video-still-ci.jpg`, `after/network-replay-frame-9s-ci.jpg` and the landing `after/landing-desktop-full-ci.png`.

## Screenshots (shared notes folder, outside the repo)

`/Users/nicola/Library/Application Support/Claude/side-session-notes/local_8c7f0a84-f30c-438c-b776-32f7fc434b51/m17-network/`

- `before/`: the console over golden-1.2 before the slice (`overview`, `kanban`, `kanban-dark`, `ticket-0007`, `overview-phone`): no network view, no worker, patch or gate line anywhere.
- `after/`: `network-0010-light`, `network-0010-dark`, `network-0010-attempt1-dark` (mutation NO-GO, test-proof not run, review not reached), `network-0001-rollback-light`, `network-0004-withheld-light`, `network-over-1.2-light` (the degradation), `network-0010-phone-light` and `-full`, `kanban`, `overview`.
- The video's still: `after/network-video-still.jpg`; a replay frame with attempt 1's NO-GO: `after/network-replay-frame-9s-attempt1-nogo.jpg`; a local render: `after/network-local-render.mp4`.

## Left open

- The ADR's seven "Open for the owner" items carry provisional decisions (patches in the tower document, the 64 KiB cap, withholding until secrets GO, replay on request only, no CLI follow mode, the default ticket, release and ops-triage dark).
- Release and ops-triage never light for a ticket: the logbook does not tie a brief or a post mortem to a role per ticket (a 1.4 question).
- `ci/logbook.sh`'s console runtime once answered `000` on a spec-check POST under load on this machine (green alone and in the next full run); not touched.
- No real recorded network run exists: 0012's members are hand-written (ADR 0036 §7) and the golden's 0010 is stub data; the video says so.
