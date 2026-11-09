# console

The business client's view of lights-out ([ADR 0047](../docs/adr/0047-console-reads-one-versioned-logbook-and-writes-only-go-for-launch.md), [ADR 0055](../docs/adr/0055-the-dev-phase-visible-from-request-to-release.md); every field, rule and route in [docs/plans/console.md](../docs/plans/console.md)). Ten screens:

1. **Overview**: first, **Waiting for you**: every ticket whose turn is a person's, with the one thing to do; then the tickets by state under the four bands of the flow; the perimeters `perimeters/held` names and whether each still holds; the tickets waiting at `assign` and on whom (ADR 0053); the docs tickets merges filed (ADR 0054).
2. **Kanban**: one column per tower state, under four bands of the flow (Spec, Build, Test and review, Release), a card per ticket in its state's column with its now line, ordered by priority then age, filtered and grouped by feature and priority (`- Feature:` and `- Priority:` in the ticket's header), with the empty columns shown or hidden; it takes the page's full width. See "The kanban" below.
3. **This week's tickets**: each with GO/NO-GO, the judge that decided, and its line.
4. **One ticket's timeline**: at the top, its now line with the one action, and a strip of the four bands (done, now, or the one that stopped it); below, one row per phase, grouped under those bands, each from its record: the request (who requested and through what), the product role's questions and the answers (who, through what, when), the spec gate's verdict, assign with the perimeter, each worker attempt with turns, tokens and duration, each gate line, review, rework, merge, the canary stages with their `slo:` numbers, the human answer, 100% or rollback. A ticket waiting on a question shows an answer box.
5. **Specs**: every ticket with its state, the confirmed criteria and who confirmed them, the last `spec` verdict with its line and time, and the open question with its answer box.
6. **New request**: an editor for a ticket's title, context, criteria (Given, When, Then), perimeter, feature and priority. It shows the ticket's Markdown as it would be written and, 300 ms after the last keystroke, the line of the spec gate itself. See "The request editor" below.
7. **ADRs and one ADR**: a search over the project map's ADRs (number, title, status, text, or a path an ADR cites). Each result shows its status, files, tickets and ADRs, each a link. A ticket's drawer lists the ADRs that govern its perimeter. The search needs a project map: `./go map` builds it at `MAP_FILE` (default `.crew/map.sqlite`). With none, the screen says so and names `./go map`.
8. **Incidents and post mortems**, with their fix tickets and those tickets' states.
9. **Go-for-launch**: the ticket the release carries, the release record, what the plane runs now, the brief, and the button.
10. **Thresholds**: every number that can stop a change, where it is set, and its provenance ("undeclared" when it has none).

A switch in the header sets the theme: `system` (the default, it follows `prefers-color-scheme`), `light` or `dark`. The choice is kept in the browser's `localStorage` under `lights-out.theme`. A browser that refuses storage gets the system theme, and the switch works until the page closes. The theme changes colours only.

It reads **one document, the logbook** (`lights-out/logbook/1.2`, [schema](../core/logbook/1.2.schema.json)), which `./go logbook` writes. It never reads the tower, the plane or a file behind it. It has **three writes**: go-for-launch, through the same `core/promote.sh` and the same checks as `./go promote`; the answer to a ticket's open question, through `make answer`, the recipe `./go answer` runs, accepted only for the question the logbook shows open; and a new request, through `make request`, the recipe `./go request` runs. Each records who pressed and `via: console`. One more route, `/v1/spec-check`, writes nothing. `ci/logbook.sh` checks all of it. `GET /v1/logbook.json` carries an `ETag` and answers `304` to a matching `If-None-Match`, so the 2 s poll of an unchanged logbook costs no body.

## Whose turn it is

Every card, the drawer and the head of a ticket's timeline carry one line, its **now** ([ADR 0063](../docs/adr/0063-the-console-says-whose-turn-it-is.md)): who has the ball and what it waits for. When it is a person's turn the line says "Your turn" and links the one thing to do: answer the open question (the answer box on the timeline), go-for-launch when the ticket's canary is held and the release record is unanswered (the launch screen), or decide after the last rework attempt (`needs-human`). A ticket a failed step stopped names `./go resume`. Every other state names who runs the step the tower requests next, from the tower's own table, which the page embeds (`<script id="tower-machine">`, as the board does) and `./go ci` proves equal to `core/tower.py`. The line is a reading of the record, never a verdict, and it moves no card.

## The kanban

A card's column is the logbook's `kanban`. Nothing on the page moves a card: there is no drag-and-drop, and a card changes column only when the tower moves its ticket. The columns sit under four bands of the flow, in the logbook's order: **Spec** (`requested`, `questions`, `spec-ready`), **Build** (`opened`, `pr-opened`), **Test and review** (`review`, `ci-passed`, `ci-failed`, `needs-human`), **Release** (`merged`, `main-green`, `held`, `rolled-back`); any other state goes under **Other**. A column with no card in the view is drawn narrow, its state and count only, and the columns with cards share the width, so the whole board fits a 1440 px screen. Below 720 px the columns stack. What the page adds is a view:

- **Drawer**: click a card, or press Enter on it. It shows the state, the outcome verdict and line, the last timeline row, the perimeter, the wait (ADR 0053), the ADRs that govern the perimeter and a link to the whole timeline.
- **Search**: by ticket id, title, or a path in a perimeter. A path matches a card when one of its globs matches it or contains it.
- **Keys**: the arrows move the focus between cards (left and right across columns, up and down inside one), Enter opens the drawer, Esc closes it, `/` focuses the search.
- **Collapsible columns**: a collapsed column shows its state and count only.
- **The view is the link**: `#kanban?q=…&feature=…&priority=…&group=…&empty=hide&collapsed=a,b&card=0005`. Defaults are left out and values are percent-encoded. A page opened on that hash draws the same board.
- **A moved card shows its move**: when a refresh puts a card in another column, it is drawn there with a mark naming the column it left, highlighted for 4 s. With `prefers-reduced-motion` the slide is off and the mark stays.

A refresh redraws only when the logbook changed, and keeps the focus, the drawer and the search box.

## The request editor

The spec gate's line and the Request button sit in a bar held at the bottom of the window, so the verdict is in view while you type. After a save that wrote the ticket, the form is emptied, Request waits for the next edit, and the top of the editor links the new ticket's timeline: a second press cannot file the same text twice.

`POST /v1/spec-check` takes the fields, has `core/spec.py draft` write the draft into a temporary directory, runs `gates/spec.sh` on it and answers `{ticket, markdown, line}`. The line is the gate's own: `GO: spec` or `NO-GO: spec — <why>`. Nothing is written in the repository or the tower. It is refused with `CONSOLE_AUTH=public`.

Save is the third write, `POST /v1/request`:

- It is refused in snapshot mode and with `CONSOLE_AUTH=public`. It checks the draft again and refuses a NO-GO draft with nothing written.
- On a GO draft it creates `TICKETS_DIR/<id>.md`, the next id after the highest four-digit id there, with an exclusive create (a second save at once gets 409). It then runs `make request TICKET=<id>` with `REQUEST_BY` set to the identity and `REQUEST_VIA=console`. The tower records both on the request, and the timeline's request row shows them.
- The file is written, not committed. The editor says so and names the file. Committing it is yours.
- At L0 the product role is not consulted on a new request: it replays recordings and a new request has none. The editor says so before saving, and the spec gate alone judges the request. At L1, with a key, saving is how the role is consulted; its questions open the ticket at `questions` and the answer box takes them.

## Run it

```bash
./go up
```

```bash
./go console
```

Open http://localhost:8098. After `./go demo` it shows ticket 0001's timeline from `requested` to the rollback. At L0 the product role has no recording for that request, and its row says it was not consulted (ADR 0055 §3). To press the button, hold a canary first: `./go kill-switch`, then `./go release`, which holds the canary at 25% when verify passes (`git checkout app/flags/flags.json` undoes the kill switch afterwards). `CONSOLE_PORT` moves the port.

Without the plane, serve a logbook file instead; nothing can be pressed, answered or saved (the spec check still works):

```bash
CONSOLE_SNAPSHOT=console/snapshot/logbook.json ./go console
```

`./go demo-console` is the acceptance: a held canary promoted by an HTTP POST to a running console, checked at 100% through Envoy, then un-promoted. It is not part of `./go demo`.

## Who may press (`CONSOLE_AUTH`)

The console has no login, no session and no password. It does not start unless the mode is declared:

| `CONSOLE_AUTH` | When | Who presses |
|---|---|---|
| `loopback` (default) | published on 127.0.0.1, ::1 or localhost only | anyone at that machine; recorded as `unauthenticated` |
| `proxy` | behind a proxy that authenticates, with `CONSOLE_IDENTITY_HEADER` naming the header it sets | go-for-launch: the identities listed in `CONSOLE_LAUNCHERS` (comma-separated, compared verbatim). Answer and request: any identity the proxy sets. A request without the header gets 401 |
| `public` | only with `CONSOLE_SNAPSHOT=console/snapshot/logbook.json` | nobody: no write, and no spec check |

Every POST also needs `Content-Type: application/json`, an `Origin` and `Host` that are the console's own (`CONSOLE_HOSTS` adds host names a proxy uses). go-for-launch also needs a body that matches the record and the brief as they are now. Only one press runs at a time. `CONSOLE_LAUNCHERS` stays the go-for-launch list: it does not limit who may answer or request.

**`proxy` trusts a header.** The console cannot tell whether a request came through the proxy. Make it reachable from the proxy only (bind it to a private interface, a firewall rule, or the same pod), or anyone can claim any identity. Behind Google's Identity-Aware Proxy the header is `X-Goog-Authenticated-User-Email` and its value carries the `accounts.google.com:` prefix, which `CONSOLE_LAUNCHERS` must repeat. The first version does not verify IAP's signed `X-Goog-IAP-JWT-Assertion` (ADR 0047, provisional decision 8). oauth2-proxy's header names were not verified when this was written; check your proxy's documentation.

## What is real at L0

- **The record is real**: the tower's documents, the release log (`.crew/releases.jsonl`), launchpad's record and the policy files, as `./go logbook` reads them.
- **The tower is in memory at L0**: tickets from before the last `./go down` are not shown, and screen 1 says so. The mirror that fixes this (ADR 0031 §6) is not built yet.
- **The workers replayed**: at L0 a ticket's task shows the provider, model and tokens of the recorded run, marked "replayed"; no tokens were spent.
- **The brief at L0 is rendered from the record** by `core/promote.sh`, labelled as such; from L1 the release role writes it (ADR 0020 §4).
- **The button is real**: it runs `core/promote.sh`, which shifts the canary to 100% or rolls it back.

## Who built it

This first version was written by a Claude Code session on 2026-11-04, by hand, as plain HTML and a standard-library Python server, without Stitch and without a frontend worker: no key could be spent where it was built, and Stitch's export format is still unverified (ADR 0047, provisional decision 6). The plan is for Stitch to design the five screens into `design/` and a frontend worker to rebuild `index.html` from it, against the same logbook and the same ci check.
