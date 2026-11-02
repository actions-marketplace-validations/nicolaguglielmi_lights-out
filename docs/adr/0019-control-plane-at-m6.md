# ADR 0019 — Control plane at M6: `core/tower.sh` is a four-step state machine in POSIX sh over a plain-JSON ticket document; `EventBus` and `StateStore` are curl+jq verbs against the emulators; the `inproc` orchestrator pulls one event at a time; the CI leg of `e2e` is the gates run by the tower and posted as a commit status, not a runner job; the PR is merged with a merge commit and the canary stays the stable image; `./go audit` reads only the state store; `e2e` is the last real stage of `./go demo`; `go-for-launch` and the review roles re-date to M7, the runner socket to M8

- Status: accepted (amends ADR 0003 stage list [`e2e` real; the `100%` stub re-dates to M7]; ADR 0012 consequences [`actions/checkout` mirror is M8's]; ADR 0013 §1 [Zot stays empty through M6] and §4 [`100%: NOT YET (M7, go-for-launch)`]; ADR 0015 §7 and ADR 0017 §5 [runner socket and the first Gitea job move to M8; Actions stay off]; ADR 0017 §7 [`architect`, `test-reviewer` ROLE.md say M7] and §12; `docs/ARCHITECTURE.md` ports table [emulators in use]); amended by ADR 0020 [review roles, ticket 0003 and the budget records move to M8; go-for-launch landed]; amended by ADR 0021 [the tower transition table gained two lines for the `review` step and its outcomes]. Amended by ADR 0022: §8's "image signing: M8" lands at L0 first, with a local key, not as a cloud-only item. Amended by ADR 0025: §4's "A is due at M8" splits — the socket and the first Gitea job land at M8 as the **image build** on `main` (and there is no `actions/checkout` in it), while the `pull_request` gates job goes to the milestone that runs the tower on GCP; §5 ends, the canary is the merge commit's signed image and the `release.image` placeholder is deleted. Amended by ADR 0027 §1: §3's L2 `pubsub`/`firestore` verbs re-date from M8 to that same milestone. Amended 2026-11-02 by ADR 0034 (ticket 0009): §1's failed step appends one `{step, state, at, error}` history entry, state and fields unchanged; a ticket whose last entry has `error` is stranded, and `tower.sh resume` / `./go resume TICKET=<id>` request that step again without wiping the history.
- Date: 2026-09-16
- Milestone: M6

## Context

M6 (plan §7): dispatcher, ticket state machine, artefact model, idempotency,
an audit log that rebuilds deploy → PR → task → spec. Done when `./go e2e`
runs ticket → PR → CI → canary → verify failed → rollback with no human,
and the audit shows the whole chain. Plan §5: "boring on purpose: events on
Pub/Sub, a dispatcher, a state machine with its state on Firestore, workers
as ephemeral jobs; both have an official emulator, so L0 and L2 share the
code". Names from plan §1: `tower`, `crew`, `launchpad`, `go-for-launch`.
Verified live 2026-09-16 by the main session: the plane is up; Gitea 1.27.3
exposes `statuses/{sha}`, `commits/{ref}/status`, `pulls/{index}/merge`;
the Pub/Sub emulator answers REST (`PUT …/topics/x` → 200, `…:publish` →
messageIds); the Firestore emulator answers REST (`PATCH …/documents/c/x`
with typed `fields` → 200, GET returns the document). Repo facts: `core/`
holds two POSIX drivers (`crew.sh`, `launchpad.sh`) that call
`adapters/<name>/<verb>.sh`, plus `risk.py` tested by `ci/core-tests.sh`;
`ci/harness.sh` proves a core script on stub inputs with no plane;
`crew-run` (Makefile) already fetches a PR branch into a worktree and runs
`make gates`; `open-pr.sh` reuses an open PR; `launchpad.sh` rolls back
first; `fixtures/0001/dev-worker/expect` says `risk low, auto-merge`.
Measured: `demo-crew` 97 s warm including the gates (HANDOFF M5); `./go
demo` 113 s warm to the rollback (HANDOFF M5); one release to the 5 % NO-GO
≈ 80 s (ADR 0013 §5 arithmetic).

## Decision

1. **The machine is `core/tower.sh`, POSIX sh, one `case` per step; the
   effects are four scripts in `core/steps/`.** `tower.sh step <ticket>
   <step>` reads the ticket document, checks the step's precondition state,
   runs `core/steps/<step>.sh`, writes the document, publishes the next
   step's event. States are what has happened to the ticket: `opened` →
   `pr-opened` → `ci-passed` | `ci-failed` | `review` → `merged` →
   `rolled-back` | `held`. Steps, and the event that requests each, are the
   verbs: `assign` (calls `core/crew.sh`; records `pr.number`, `pr.url`,
   `pr.base_sha`, `pr.head_sha`, `harness`, `model`, `spec.sha256` of the
   ticket file the harness read and `spec.title`, its first line), `ci`
   (fetches `ticket/<id>` from the code host, asserts `FETCH_HEAD ==
   pr.head_sha`, runs `make gates` in a detached worktree — the `crew-run`
   recipe moves here and `crew-run` calls it — posts the verdict with
   `adapters/$CODE_HOST/status.sh <sha> <state> gates <description>`,
   records `ci.verdict`, `ci.risk_level`, `ci.decision`, `ci.head_sha`;
   next state `ci-passed` on `GO`+`auto-merge`, `review` on `GO`+`review`,
   `ci-failed` on `NO-GO`), `merge` (`adapters/$CODE_HOST/merge.sh <pr>`,
   records `merge.sha`, `merge.head_sha`), `release` (`make release` with
   `CANARY_VERSION`, stderr captured to `.crew/<id>/release.log`; records
   `release.version`, `release.verdict` — launchpad's one stdout line —
   and `release.numbers`, the `slo:` lines from that log, the numbers that
   produced the decision; exit 1 → `rolled-back`, exit 0 → `held`, the ADR
   0014 semantics unchanged). `ci-failed`, `review`, `rolled-back`, `held`
   publish nothing: terminal. `review` is terminal at M6 because nobody
   reviews (ADR 0017 consequence, re-dated in §7 below); the stderr line
   names it. Why `core/steps/` and not inline: the machine must be proven
   without a plane (§8) and the effects cannot run without one; a stub
   `TOWER_STEPS` directory is the whole seam. `core/crew.sh` gains
   `BASE_SHA` and `HEAD_SHA` in `pr-opened.env`; nothing else changes.
2. **The document is plain JSON, one per ticket, id = ticket id; the
   adapter owns the typed encoding.** `adapters/$STATE_STORE/get.sh
   <collection> <id>` prints plain JSON (or exits 1 on absence), `put.sh
   <collection> <id>` reads plain JSON on stdin and writes the whole
   document, `delete.sh`. `firestore-emulator`: curl against
   `http://$PLANE_HOST:8086/v1/projects/lights-out/databases/(default)/documents`,
   a jq filter each way between plain JSON and Firestore's
   `{"fields":{…Value}}`; `core/` never sees `stringValue`. The tower reads,
   edits with jq, writes back the whole document — small, and no update
   mask to get wrong. Idempotency rule: **an event whose step precondition
   is not the document's current state is acked and dropped**, one stderr
   line `[tower] 0001: assign already applied (state pr-opened), ignoring`.
   No compare-and-set: the `inproc` loop runs one step at a time, so a
   precondition on `updateTime` would guard nothing today; it is M8's, the
   day two workers pull the same topic. A crashed step re-runs from the
   event, and every effect is re-runnable: `crew.sh` wipes `.crew/<id>` and
   reclones, bootstrap and `push.sh` force, `open-pr.sh` reuses the open
   PR; `ci` is a function of `(base, head)` and statuses append; `merge.sh`
   is written idempotent — a PR already `merged` prints its
   `merge_commit_sha` and exits 0 instead of taking Gitea's 405; `release`
   starts with `rollback.sh`, so a re-run is a second release from a known
   state, not a half one — a duplicate action, recorded as the latest
   verdict, never a corrupt state.
3. **`EventBus` is three verbs, one topic, one subscription; `inproc` is a
   loop.** `adapters/$EVENT_BUS/publish.sh <json>`, `pull.sh` (prints one
   message's data and its ack id, or nothing), `ack.sh <ackid>`.
   `pubsub-emulator`: curl against `http://$PLANE_HOST:8085/v1/projects/lights-out`,
   topic `tower`, subscription `tower-inproc`, both created idempotently
   (PUT → 200 or 409) by the first verb that needs them; the message is
   `{"ticket":"0001","step":"assign"}`. `adapters/inproc/run.sh <ticket>`:
   pull one, `tower.sh step`, ack, repeat; an empty pull ends the run (the
   implementer verifies which pull option makes the emulator return
   immediately on an empty subscription, and writes it in the script's
   header). At L0 the bus carries the tower's own messages back to itself
   in one process: declared in the README, because that is the point — at
   L2 the same message starts a Cloud Run job and the machine does not
   change. Where the L2 adapters (M8) differ: base URL and an
   `Authorization` header, plan §4's "stesso codice, cambia l'endpoint".
4. **CI at L0 is the gates run by the tower on the PR head, posted as a
   Gitea commit status; the Gitea Actions job and the runner socket move to
   M8.** Option B of the two weighed. This is the `demo-crew` mechanism
   (ADR 0017 §6) plus one CodeHost verb, `status.sh`, ~10 lines of curl to
   `POST /repos/{o}/{r}/statuses/{sha}` so the PR page shows the check.
   Against plan §3's table (CI = Gitea Actions at L0): a declared deviation
   of the *executor*, not of the CI — the gates, the verdict and the status
   on the PR are real, and the README says "at L0 the CI leg of `e2e` is
   the gates run by the tower on the PR head, posted as the `gates` status;
   the Gitea runner does not execute them until M8". Not a hidden mock:
   nothing is simulated and the runner is not claimed to have run. Why not
   A now: it needs five things this session could not verify from the
   official docs (that Gitea reads `.github/workflows/`; that
   `pull_request` fires for a PR opened by API; that `actions/checkout@v4`
   resolves from the runner container — `DEFAULT_ACTIONS_URL` defaults to
   `github`, verified, so github.com must be reachable from inside the
   podman machine; the engine-host socket path as a compose bind source
   with `ci-compose` still clean; `WORKBENCH_IMAGE` reaching the runner's
   job environment), plus ADR 0015 §7's socket with its three conditions,
   for the same six gates the tower already runs. A is due at **M8**, the
   milestone that adds the `github` CodeHost and makes "wait on a status
   the tower did not produce" the shared code path; doing that at L0 alone
   at M6 would be a path no other level uses. The `pull_request`-range job
   (`./go gates BASE=<base sha> HEAD=<head sha>` from the event context,
   one YAML, `if:` not duplication) lands with it. ADR 0015 §7's three
   conditions stand unchanged.
5. **Merge with a merge commit; the canary is the stable image.**
   `merge.sh` posts `{"Do":"merge"}`: the merge sha's second parent *is*
   the PR head, so the audit's first link is checkable by `git` later, not
   only by the document; a squash would make a new sha unrelated to the one
   CI judged. The release after the merge is today's `make release`:
   `backend-canary` from the `lights-out-backend` tag with
   `APP_VERSION=0.2.0-waitlist` — option (i). The deploy record names the
   merge sha it stands for and carries `release.image: "stable image, not
   built from merge.sha (M8)"` so the audit prints the gap on every run,
   and the README says "at L0 the canary the tower releases after the
   merge is the stable image under `0.2.0-waitlist`, not a build of the
   merged commit; build and push to Zot arrive at M8 with the Registry
   port". Why not (ii) now: a build from the merge commit changes nothing
   observable — ticket 0001's fix touches the geocoder path and the verify
   fails on the flag, either way — costs 1–2 min warm inside a budget
   measured cold only by projection since M3, and needs the `backend`
   image tag parameterised on both services to avoid clobbering stable's
   tag; at M8 Cloud Run deploys by digest and the build becomes
   load-bearing. The version string is not a mock: `0.2.0-waitlist` is the
   name the release gives the revision, the committed targeting rule turns
   `waitlist` on for it, and the README has declared that injection since
   M3; the mock would be a verify that does not read the metrics.
6. **`./go audit TICKET=<id>` reads only the state store.** `core/audit.sh`
   prints the chain on stderr — `deploy 0.2.0-waitlist rolled-back at 5%
   (numbers) ← merge <sha> ← PR #1 <url> (gates GO, risk low) ← ticket 0001
   ← spec sha256:<…> "<title>"` — and one stdout line: `GO: audit` or
   `NO-GO: audit — <missing link>`. Links checked: `spec.sha256`,
   `pr.number`, `ci.verdict`, `merge.sha`, `release.verdict` present; and
   `pr.head_sha == ci.head_sha == merge.head_sha` (the sha CI judged is
   the sha that was merged). Mapping: deploy = `release.*` + `merge.sha`;
   PR = `pr.*` + `ci.*`; task = the ticket id + `harness`, `model`; spec =
   the ticket file's hash and title as the harness saw it. No socket: curl
   to the emulator through `PLANE_HOST`. **Owner addition, 2026-09-16: the
   audit also asks the code host, and NO-GOs when the two disagree.** An
   audit that reads only its own archive confirms itself. One more
   CodeHost verb, `adapters/$CODE_HOST/pr.sh <number>`, prints the PR as
   the host sees it (`state`, `merged`, `head_sha`, `merge_sha`); the
   audit compares: a document at or past `merged` needs the host to say
   `merged: true` with `merge_sha == merge.sha`; a document at
   `pr-opened`, `ci-*` or `review` needs the host's `head_sha ==
   pr.head_sha`. "State store says merged, code host says PR #1 is open"
   is the NO-GO the owner named. Still no socket: `pr.sh` is curl through
   `PLANE_HOST`.
7. **`e2e` and `demo`.** Makefile `e2e [TICKET=0001]`: `up`, delete the
   ticket's document (a replay on a per-`up` plane; stderr says so; a
   production tower never deletes), publish `assign`, `adapters/$ORCHESTRATOR/run.sh`,
   assert the final state is `rolled-back` (the done-when ends in a
   rollback, the `demo-rollback` precedent), then `audit`; `GO: e2e`. It
   replaces the `[demo] e2e: NOT YET (M6)` line; `demo-rollback` stays
   before it (it proves the controller alone). Estimate, warm: 97 s crew
   and gates + ~2 s merge, statuses, documents + ~80 s release + ~1 s
   audit ≈ 180 s; `./go demo` ≈ 113 + 180 ≈ 295 s warm, cold ≈ 340 + 180
   ≈ 520 s by ADR 0013 §5's projection, ~58 % of 900 s (plan §2). Measured
   at M6 close in HANDOFF. The 1m window and the reused `instance` (ADR
   0013 §2): ≥ 97 s pass between `demo-rollback`'s rollback and `e2e`'s
   5 % verify, so the window holds only `e2e`'s canary; reordering the two
   stages breaks that and the Makefile comment says so. `go`'s socket
   list already has `e2e`; `audit` is not added.
8. **Not built at M6, and where each goes.** `go-for-launch` / promotion to
   100 %: not in the done-when; the stub becomes `[launchpad] 100%: NOT YET
   (M7, go-for-launch)` — M7 because the release agent that composes the
   promotion brief the human reads is M7's (plan §5, §7), and plan §7 M7
   gets a dated note; ADR 0003's rule then applies to M7. `architect` and
   `test-reviewer` prompts: no run on this path (`review` is terminal), so
   `roles/*/ROLE.md` say M7, the first milestone about agents after the
   tower exists, and ticket 0003's perimeter rule goes with them, before
   the next `record`. Cloud adapters, `github` CodeHost, image build and
   Zot push, image signing, the runner socket: M8. Compare-and-set on the
   document, per-worker databases: M8. No retries, no timeouts of the
   tower's own: a step fails, the event is acked, the state stays where it
   was and the stderr line says which step.
9. **Tests from the spec: `ci/tower.sh` joins `CI_CHECKS`.** The
   `ci/harness.sh` shape: a temp root with `adapters/stub-state/`,
   `adapters/stub-bus/` (file-backed), and a `TOWER_STEPS` directory whose
   four scripts append their name to a log and write the fields §1 names;
   `STATE_STORE`, `EVENT_BUS`, `TOWER_STEPS` pointed at them. Proven: (a)
   the transition table, every state × step, including that `review`,
   `ci-failed`, `rolled-back`, `held` publish nothing; (b) the same event
   twice → one line in the effects log; (c) `core/audit.sh` NO-GO on a
   document missing `merge.sha`, and on `ci.head_sha ≠ merge.head_sha`,
   GO on a complete one; (d) **owner addition, 2026-09-16: the crash
   case, not only the duplicate event** — the effect happened but the
   state was not written: the stub code host's PR is already merged with
   sha X, the document still says `ci-passed`; the `merge` event arrives
   again; the real `core/steps/merge.sh` (not a stub) runs against the
   stub CodeHost, performs no second merge (the effects log shows none),
   and the document advances to `merged` with `merge.sha == X`. This is
   how these systems actually break, so the seam for `merge` is the
   CodeHost adapter, not the step; (e) the audit's divergence NO-GO: the
   document says `merged`, the stub host says the PR is open. Cold, no
   plane, milliseconds, under the contract.

## Alternatives rejected

- Python for the machine (`core/tower.py` beside `risk.py`): a second
  runtime for a `case` statement; the drivers it calls are sh.
- No event bus at M6, a sequential script: plan §5 names the bus and the
  done-when names the dispatcher; it is the owner's, not this ADR's, to
  strip. Kept minimal: one topic, one message per step.
- Command events vs. state events (`pr.opened`): a state event needs the
  consumer to know the table; a step event is the table's input.
- Firestore update masks: more API surface for a document of ~20 fields.
- A `CI` port with `inproc-gates` and `github-actions` adapters: not in
  plan §4's table; the status is a CodeHost verb, the gates are core.
- Option A (Gitea Actions job + socket) at M6, and the middle A′ (Actions
  on, a socket-less `ci` job consumed by status): both put github.com
  reachability from the runner container on the demo path for a job that
  does not judge the PR, on five unverified facts.
- Squash merge: loses the CI-judged sha from the graph.
- Option (ii), build from the merge commit, and a Zot push: §5.
- A run id per document: the audit would need it; `e2e` deleting the
  document says the same thing in one line.
- `./go promote` as a manual target now: not in the done-when, no
  acceptance path without an un-promote, and the brief it should wait for
  is M7's.
- Audit that reads only the state store (this ADR's first draft): the
  owner overruled it the same day — an audit that reads only its own
  archive confirms itself (§6). Cross-checking against *git* (the merge
  sha's parents) is still left to M8's digest.
- `demo-rollback` dropped from `demo` now that `e2e` rolls back too: it is
  the controller-only proof and costs one stage; kept.

## Consequences

- **The runner socket is re-dated a third time** (M4 → M5 → M6 → M8) and
  the runner has run no job since M2. ADR 0003's rule binds: if M8 closes
  with the runner idle, M8 is not closed. This is the consequence that will
  hurt.
- The audit's first link is by declaration at L0: the bytes in the canary
  are not the merge commit's, and every audit line says so until M8.
- `./go demo` needs the network beyond image pulls for the first time:
  `deps` (osv-scanner) is now on the demo path via `e2e`; offline it
  NO-GOs at `ci`, honestly.
- `e2e` leaves Gitea's `main` one merge ahead of the local checkout; the
  next `assign` force-pushes over it (ADR 0017 consequence, unchanged).
- Two release runs per `demo`; the 5 s scrape and 1m window rule now has
  two stages to keep apart.
- `.crew/<id>/` now holds tower logs beyond `assign`'s wipe; no new
  gitignore entry.
- `review` is a terminal state until M7: a medium or high PR stops there,
  visibly.
- One more `ci` check, `tower`, milliseconds; `ci/shell.sh` picks up the
  new scripts by its `find`.
- The audit now depends on the code host being up: `./go audit` on a
  plane that is down NO-GOs with "code host unreachable", not with a
  verdict about the record.
- `roles/dev-worker/role.env` budgets are re-tuned in this milestone on
  ADR 0018's run 3 (owner request, 2026-09-16): the old numbers were
  measured on 3.5 without thinking. Provenance in the file.

## Golden-rule check

Stranger with podman, git, sh; no key, no account. Nothing new to pull or
install: the two emulators have been in the plane since M2, the adapters
are sh, curl and jq, the crew replays the fixture, the gates and the
release are the M4/M3 code. `./go demo` gains one stage of about 180 s warm;
projected cold ≈ 520 s of 900. Network is now required for `deps`, as it
already was for the cold pulls. Passes; the clean-container figure is
recorded at M6 close and the GitHub `engine-compat` job measures it on
every push.
