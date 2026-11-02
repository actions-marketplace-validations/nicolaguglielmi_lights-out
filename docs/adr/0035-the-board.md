# ADR 0035 — `./go board`: one page that explains the pipeline and, when the plane is up, shows it live, read-only

- Status: accepted; amended 2026-11-02 (§6: the explainer hosted alone)
- Date: 2026-11-02
- Milestone: before the public launch (visibility plan, plan §15)

## Context

The pipeline is easy to run (`./go demo`) and hard to see. A demo prints
GO/NO-GO lines and a stage log; the tower's state lives in the Firestore
emulator, the canary weight in Envoy's admin API, the locks in flagd, the
decision in `.crew/release.json`. A talk, or someone who has just cloned
the repo, needs one picture of the flow and of what stops a change, and a
way to watch a release move through it.

## Decision

1. **One page, `board/index.html`.** No build, no framework, no font or
   script from the network. It opens from disk too, where only the
   explainer works.
2. **EXPLAINER**: eight scripted walks (ship it, bad canary, fake test,
   risky diff, freeze then resume, human says no, out of bounds, kill
   switch), each a sequence of steps over the stations of the launch
   sequence, the tower document, the locks, the traffic split and the
   stdout verdict lines. They are labelled as scripted, with versions and
   numbers as examples. The page embeds core/tower.sh's transition table
   and checks every scripted transition against it on load.
3. **LIVE**: `board/serve.py` (Python standard library, inside the
   workbench) serves the page and `/state.json`. The snapshot is built
   only from the profile's port verbs: STATE_STORE `get` for each ticket
   under `tickets/`, FLAGS `evaluate` for release-freeze and the
   workload's kill switch, DELIVERY `status`, plus the release record and
   the last brief on disk. It never calls `put`, `set`, `shift`,
   `deploy` or `rollback`. A probe that cannot read answers `ok: false`
   with the adapter's own last stderr line, never a default value. One
   loop refreshes it every 2 s (provenance in serve.py: a decision), so
   open tabs do not multiply the probes.
4. **`ci/board.sh`** proves the parts that can drift: the page's table
   equals core/tower.sh's, every probe with nothing to read says so, the
   server names no verb outside the three read verbs, and it serves both
   paths.
5. **`./go board`** runs the server in the workbench with the engine
   socket (DELIVERY `status` reads each revision's version through
   `compose exec`, as promote does) and publishes it on the host's
   loopback only, `127.0.0.1:8099`; `BOARD_PORT` moves it.

6. **The explainer hosted alone** *(amended 2026-11-02)*. With
   `BOARD_STATIC=1` the server starts no probe and answers 404 on
   `/state.json`; the page reads that 404 as "no plane here" and does not
   offer LIVE at all, so a hosted copy never shows a plane it cannot see.
   `board/Dockerfile` packages it for Cloud Run (it reads `PORT`); it is
   named Dockerfile because `gcloud run deploy --source` builds only a file
   with that name. Deploying it is the owner's act.

## Alternatives rejected

- **Grafana in compose.** It would show Prometheus, not the tower's
  documents, the flags or the record, and adds a service and an image to
  every `./go up` for a view nobody needs to run the demo.
- **A compose service for the board.** It would start only with the
  plane, and the explainer is most useful before anyone has one.
- **A JavaScript framework and a build.** A toolchain for one page,
  against "toolchain in the container" and "the smallest thing".
- **Reading Envoy, flagd and Firestore directly from the browser.** Vendor
  URLs in the page, CORS on each, and a second reading of the plane that
  could disagree with the one the tower and promote use.
- **A separate static build of the page for hosting.** Two pages to keep
  in step; one page that drops LIVE on a 404 needs none.
- **A purely static diagram.** It shows the flow but not the locks
  changing state, and nothing of a real release.

## Consequences

- The board has the engine socket while it runs, like `up` or `demo`; the
  README already says what that means.
- A new tower state or step fails `./go ci` until the page's table and
  scenarios follow it.
- Not in `RISK_HIGH_PLATFORM`: the board decides nothing.
