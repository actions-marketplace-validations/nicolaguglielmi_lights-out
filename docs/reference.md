# lights-out reference

Everything the [README](../README.md) leaves out: what runs at each milestone, every command, the levels, the plane, the release controller, how `./go` runs, and the repository layout.

## Status

Milestones M19 (harnesses, ADR 0041), M20 (gates anywhere, ADR 0042), M21 (GitHub as code host, ADR 0043), M22 (ops without the plane, ADR 0044) and M23 (the packaged command, ADR 0045) closed. Next, in plan §16's order: M24 (the public legacy experiment). What runs today:

| Stage | Milestone | Real |
|---|---|---|
| ci | M0 | ✓ |
| engine-compat | M2 | ✓ host-side, selected engine |
| up | M2 | ✓ L0 plane, 8 services beside the app |
| smoke | M2 | ✓ a meetup created through Envoy |
| verify | M1 | ✓ metric shape at M1, canary vs stable at M3 |
| deploy | M3 | ✓ staging → 5% → 25%, held for human gate |
| rollback | M3 | ✓ automatic on verify NO-GO, triggered by `./go demo-rollback` |
| PR gates | M4 | ✓ six fixture PRs prove risk, SAST, deps, test, mutation, secrets |
| ticket → PR | M5 | ✓ crew driver, six roles, one real run recorded, replay at L0 |
| e2e | M6 | ✓ ticket → PR → CI → merge → canary → verify NO-GO → rollback, audited |
| ADK agents | M7 | ✓ product, ops-triage, release on ADK 2.9.1; adk eval in ci; replay at L0 |
| go-for-launch | M7 | ✓ held canary → brief → human GO → 100% (`./go promote`), proved by `./go demo-launch` |
| review | M9 | ✓ test-reviewer and architect on gemini-cli; risk medium/high PR goes review → ci-passed/ci-failed; ticket 0003 perimeter rule |
| seam | M12 | ✓ Workload port (ADR 0030) lets the platform operate on any workload, not just the app; app is the default (`WORKLOAD=app`) |
| attach | M13 | ✓ `./go attach <path>` makes a repository of yours the workload, its contract in `.lights-out/`, its thresholds in `.lights-out/policy.env` (ADR 0037); `./go demo-seam` attaches `workloads/minimal/` as a repository of its own |
| rework | M15 | ✓ a gates NO-GO or a CHANGES-REQUESTED review goes back to dev-worker with the verdict, up to four attempts (`policy/rework.env`), then `needs-human`; `./go demo-rework` on ticket 0013's hand-written attempts (ADR 0038) |
| mainline | M30 | ✓ main stays green without a queue: a PR merges without a second judgment when nothing moved under its perimeter, the new `mainline` step judges main (`sast`, `test`) in groups of at most four merges, bisects a red group, reverts the culprit through the code host and sends its ticket to rework; a red main stops `assign`, `rework` and `release` until fixed (`policy/mainline.env`); `./go demo-mainline` on tickets 0020–0022 (ADR 0056) |
| harnesses | M19 | ✓ `claude-code` (2.1.311) and `codex` (0.166.0) beside `gemini-cli`, one provider each, the guard in each CLI's pre-tool hook, `./go harness-conformance` against a scripted model (no key; plumbing, not a model's ability); recording with them is implemented; claude-code ran live once on 2026-11-04, its change stopped by the mutation gate, codex not yet (ADR 0041); `antigravity-cli` (agy 1.5.1) on Gemini, optional and experimental beside the default `gemini-cli`, conformance only, no live run yet (ADR 0050) |
| ops without the plane | M22 | ✓ `./go incident` and `./go postmortem` (ADR 0044); `./go verify METRICS_URL=…` on any Prometheus-compatible endpoint; `demo-postmortem` replays the ops-triage recording made at L1 on 2026-11-04 (`./go record-postmortem PROFILE=l1`, gemini-3.8-flash) and prints GO with a fix ticket |
| packaged command | M23 | ✓ built and tested in CI, published as `ghcr.io/nicolaguglielmi/lights-out:0.2.0` on 2026-11-08 (tag `v0.2.0`; 0.1.0 on 2026-11-05): the image and the `lights-out` wrapper (`init`, `gates`, `triage`, `postmortem`, `doctor`, `version`), the Action, `./go doctor`, `./go package`, `./go demo-package` (ADR 0045); the Action is proven in lights-out's own workflow only |
| tests that prove | M27 | ✓ `test-weakening` and `test-proof` on every range, `WORKLOAD_TEST_PATHS` in the contract; the tower's `assign` refuses a ticket whose perimeter overlaps an open one, and an attached repository's red base; `./go demo-gates` and `ci/assign.sh` prove it (ADR 0053) |
| gates without a container | M35 | ✓ `lights-out gates --light` (from a clone `python3 -m core gates --light`): a Python package, standard library only, from a root `pyproject.toml` mapping `lights_out` onto `core/`; risk and test-weakening by default, perimeter and spec with `TICKET=`, test and test-proof on the host with `TEST_ON_HOST=1`; one line that names the gates that did not run and never says `GO: gates`; 0.14 s on this repository; `ci/gates-light.sh` proves it agrees with the full gates on the nine fixtures; the `--light` hook recipes verified once against Claude Code, Codex and Gemini CLI with the scripted model. Not on PyPI yet (ADR 0061) |
| gates anywhere | M20 | ✓ `./go init [<path>]` drafts the gates half of `.lights-out/` in the clone (eleven keys, the three `TOOLCHAIN_IMAGE` forms, a measured `MUTATION_BASELINE`); `./go gates` judges the last commit with no engine socket on the workbench form; `./go demo-init` proves it on `workloads/minimal` and `workloads/minimal-js` without the plane, 32 s and 7 s for init plus gates, measured warm on 2026-11-03 (ADR 0042) |
| GitHub code host | M21 | ✓ implemented: `adapters/github/` with the eight CodeHost verbs, an attached repository's merge built, signed and released by the release step at any code host, `./go codehost-conformance` (Gitea on every push, GitHub nightly once the owner sets the throwaway repository). Not yet run: `./go e2e CODE_HOST=github PROFILE=l1` (ADR 0043) |

| | |
|---|---|
| **Frontend** | No tests until M11. TypeScript type-check in the image build is the only frontend check at M1. |

A green `./go demo` reaches automatic rollback: the failing version (same image, `waitlist` targeted on) clears staging, fails verify at 5%, rolls back to 100/0 on its own, and exits nonzero, then runs the whole golden path once more through the tower (`e2e`). Promotion to 100% is go-for-launch, `./go promote` after a held release; the brief is composed by the release role from L1, rendered from the release record at L0.

The PR gates (`./go demo-gates`) run on nine committed fixture patches and prove both verdicts: risk scoring, dependency scanning, SAST, test failure, mutation inadequacy, a test that passes on the base, a dropped assertion, and secrets. `./go demo-crew` proves the ticket→PR pipeline: the crew container runs the dev-worker role on ticket 0001, opening a PR that passes `make gates`. At L0 the fixture is replayed; at L1 a real run against the Gemini API is recorded.

## What is real and what is recorded

The README keeps three of these; this is the full list.

- **Real:** the gates, the signed build, the canary, the metrics, the rollback, the audit chain. Nothing in them is simulated.
- **Gates without the plane:** `./go demo-init` proves attach, init and gates on the two examples, `workloads/minimal` and `workloads/minimal-js`, with no plane and no engine for the draft's run. It does not prove the same on your repository.
- **Recorded:** no model is called without a key. The agents replay answers recorded once against the Gemini API (`fixtures/`), and the promotion brief at this level is rendered from the release record and labelled so. With `GEMINI_API_KEY` in `.env` and `PROFILE=l1`, the agents run live.
- **Hand-written (rework):** `./go demo-rework` sends ticket 0013's first attempt back to the worker with the gates' verdict (ADR 0038). No rework has been recorded against the Gemini API yet, so at L0 both attempts replay patches written by hand (`fixtures/0013/`, `hand_written: true`), and the run says `model none`. The gates that reject the first attempt and pass the second, the tower, the loop and the cap are real.
- **Hand-written (mainline):** `./go demo-mainline` runs tickets 0020–0022 (ADR 0056). No run of these tickets has been recorded against the Gemini API, so at L0 the patches are written by hand (`hand_written: true`) and the run says `model none`. The person's merge to `db.py` is made by the demo through the code host. The re-judge rule, the main check, the bisection and the revert are real.
- **Hand-written (network):** `./go demo-network` splits ticket 0012 between two workers behind one harness port (ADR 0036). No network run has been recorded yet, so at L0 the two workers replay patches written by hand, and the run, the PR and the audit say `model none`. The governance around them (perimeters, gates, canary, rollback, audit) is real.
- **Recorded (post mortem):** `./go demo-postmortem` replays the ops-triage recording of the incident captured from a real `demo-rollback` run (`fixtures/incidents/`). It was recorded once at L1 on gemini-3.8-flash (`./go record-postmortem PROFILE=l1`, 2026-11-04), so `demo-postmortem` prints GO with a fix ticket and no key. `./go postmortem` on your own incident needs a key at L1 for the same reason as any agent on your code.
- **The images (0.3.0 published 2026-11-09; 0.2.0 on 2026-11-08, 0.1.0 on 2026-11-05):** `./go demo-package` builds the gates image and runs `lights-out init`, `gates`, `test-proof` and `test-integrity` from it on `workloads/minimal` as a repository of its own, in GitHub Actions. 0.3.0 is public, for amd64 and arm64, and signed keyless; 0.2.0 and 0.1.0 are unsigned. The Action (`action.yml` at the root) is proven on one outside repository, the probe, with the published image (probe run 42589663783).
- **Local only:** at L0 merges happen on a Gitea inside the plane, never on this repository. At L1 an attached repository can use GitHub (ADR 0043). No GitHub answer is recorded and there is no fake GitHub; the adapter is proven against the real API only by a nightly that needs the owner's throwaway repository.
- **Your engine:** for plane commands, `./go` hands its toolchain container your engine's socket, which means full control of the engine. Run it where that is acceptable.
- **Live, on Claude:** the first live run on another provider, on GitHub Actions on 2026-11-04 (`claude-code` 2.1.311, `claude-sonnet-5-5`). `record-evals`: GO for product, ops-triage and release. `record` on ticket 0001: `GO: crew`, then `NO-GO: mutation`, 5 of 8 mutants killed on the changed lines (0.625 < 0.666). Nothing was saved: a NO-GO keeps no fixture, and see [Coding harnesses](#coding-harnesses) for why the ADK recordings are not committed. OpenAI has not run.
- **Cloud:** Google Cloud profiles are designed, not yet run.
- **Before the ticket (ADR 0055):** the product role replays only where it was recorded: ticket 0005's waiting-list request, a question and, after the owner's answer, the criteria (`./go ci` drives it through the tower). For any other request at L0, ticket 0001 in `./go demo` included, the step records `product: not consulted` with the replay's own reason, takes the criteria the ticket states, and the spec gate judges them for real. Under replay an answer's text is not compared with the recording. Recording the role on ticket 0001 is `./go record-evals PROFILE=l1`.

## Control plane

The tower (`core/tower.sh`) is a state machine over a JSON document per ticket in the state store, driven by step events on the event bus, with the `inproc` orchestrator pulling one event at a time. `./go e2e` runs it end to end and `./go audit TICKET=<id>` rebuilds the chain deploy → merge → PR → ticket → spec from the document and cross-checks it against the code host: a record that says merged while the PR is open is a NO-GO.

Before merge, a NO-GO is not the end (ADR 0038). A gates NO-GO or a review's CHANGES-REQUESTED puts the ticket at `ci-failed`, which requests `rework`: dev-worker runs again on the same ticket, from its own PR head, with the ticket followed by the verdict as its input (the NO-GO line and the gate's own details, such as surviving mutants, or the reviewer's reason; never a transcript). The new head goes through the same `ci` step and, if routed, the same review. Each history entry carries its attempt number and the document's `rework` list keeps every rejected attempt's verdict. At `REWORK_MAX_ATTEMPTS` (`policy/rework.env`, four) the ticket stops at `needs-human`. After merge nothing loops: a failing canary rolls back.

Before `opened` (ADR 0055) there are three states. `./go request TICKET=<id>` (`REQUEST_BY=<who>` records who requested, `unauthenticated` by default, and the request row shows it with the way in, `cli` or `console`) writes the document at `requested` and runs `clarify`: the product role reads the request and either asks one question (`questions`) or confirms the criteria (`spec-ready`). At `questions` the tower waits for a person: `./go answer TICKET=<id> ANSWER=<text>`, or the console's answer box, records the answer with who answered, through what and when, and runs the role again with every answer so far as later turns of the same conversation. At `spec-ready` the spec gate (`gates/spec.sh`, deterministic, no model) judges the request with the confirmed criteria: every criterion has Given, When and Then in that order and an outcome with no word from the ADR's vague list, `## Perimeter` declares a path, and the optional header fields `- Feature: <slug>` and `- Priority: P0|P1|P2|P3`, when present, are well formed (a ticket without them is valid and shows as unprioritised on the console's kanban). GO opens the ticket and requests `assign`; NO-GO sends it back to `questions` with the reason as the question. `core/tower.sh open`, which the other demos use, still starts a ticket at `opened` directly. The tower also keeps every attempt's task in `tasks`, so the console shows each attempt's turns, tokens and duration.

Declared at L0 (ADR 0019, amended by ADR 0025): the CI leg of `e2e` is still the gates run by the tower on the PR head (with the base's gates, Makefile and policy, and the ticket's perimeter checked again, ADR 0033) and posted as the `gates` commit status on the PR; no Actions runner exists at L0 (ADR 0060). The canary the tower releases after the merge is a real build of the merge commit, made by the release step itself in a throwaway worktree (ADR 0043 §4, ADR 0060 §5), signed by the `Registry` port and verified by the launchpad before it takes any traffic — `./go audit` prints the verified digest, not a placeholder. The bus carries the tower's own messages back to itself in one process — at L2 the same message starts a job; `e2e` deletes the ticket's document before opening it again, a replay that a production tower never does. At L0 and L1 the bus and the store are files under `.crew/` (`spool`, `sqlite`), so the documents outlive `./go down` (ADR 0060). The merge happens on the L0 Gitea only; nothing merges into this repository's own `main`.

Declared at L0 (ADR 0020): the three ADK roles (product, ops-triage, release) answer from model responses recorded once at L1 under `fixtures/adk/<role>/`, keyed by the input text — the tools, the eval and the drivers run for real, the model does not; a missing recording is a NO-GO naming `./go record-evals PROFILE=l1`, never a fallback. `./go promote` at L0 renders the promotion brief from the release record itself (a live record carries live numbers no recording can match) and says so on the line above the brief; from L1 the release role writes it. Promotion at L0 is Envoy weight 100 on the canary cluster; the canary does not become the new stable image (M8). Since M22 (ADR 0044) ops-triage has a fourth tool, `file_postmortem(title, timeline, causes, actions)`, answered once for an incident document; its recording does not exist until the owner runs `./go record-postmortem PROFILE=l1`. Each timeline entry carries one anchor that core checks against the document, and each action item becomes a ticket through the Tracker's `put` verb, with no `## Perimeter`. The tower does not call the triage role on a real rollback at M7; `./go triage ALERT=<file>` and `./go demo-triage` do, on alerts taken from the evalset. Since M18 (ADR 0040) a recording and its `run.json` carry `provider` and the served `model`; all seven ADK recordings are Gemini's, and recording the roles on Claude or OpenAI is `./go record-evals PROFILE=l1 MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5` (or `openai` / `gpt-6.1-sol`). It ran once on Claude, on GitHub Actions on 2026-11-04, GO for product, ops-triage and release; the recordings are not committed (see [Coding harnesses](#coding-harnesses)).

The project map (ADR 0054). After the code host merges, the merge step rebuilds a SQLite file, `MAP_FILE` (`.crew/map.sqlite`), from the merge commit: tickets and their perimeters, the commits that named them, ADRs, pages, files, tests and their imports, Python and JS symbols, and every path, `./go` command and `NAME=` key a page or an ADR cites. No model, no service; the same commit gives the same rows, and the file carries the commit's sha, so a reader at another base is refused. Schema 2 (ADR 0059) also keeps each ADR's status and text and `mentions` edges between ADRs and tickets; a map of schema 1 is refused until `./go map` rebuilds it. When the merge changed a path that a page or an ADR cites (the path itself, or a directory two segments deep or more above it) and did not change that document, the step files one ticket through the Tracker, origin `docs merge <sha>`, with a perimeter of those documents only, for the dev-worker. A failed rebuild fails the step and `./go resume` runs it again without a second merge. `e2e`, `demo-rework` and `demo-review` file into a copy of the tickets, `.crew/replay-tickets/`. With `MAP_BRIEF=on` (off in every profile until M24 measures it), `assign` puts the map's slice for the ticket's perimeter in the worker's `input.md`: the ADRs, pages, tests, past tickets and symbols of those files.

Declared at L0 (ADR 0036, proposed): `CREW_HARNESS=network` makes the assign step fan a ticket's `## Network` section out to its members — each a run of the profile's harness in its own clone of the base, judged alone (exit code, the harness check, its own perimeter, no path shared with another member) and then integrated in the declared order into one PR, which the tower governs like any other. Only `core/crew.sh` reads the variable, so the review step keeps its own harness; a ticket without `## Network` runs as a single worker. Ticket 0012's two members (`impl`, `tests`) replay patches written by hand under `fixtures/0012/`, marked `hand_written` in their `run.json`: no network has been recorded at L1 yet, and `./go record` cannot save one.

## Commands

On macOS, podman runs inside `podman machine`, a VM. The docker CLI is compatible but not the documented path; use `CONTAINER_ENGINE=docker` if needed.

If port 8080 is already taken on your machine, put `APP_PORT=9000` (or any free port) in `.env`: the app then answers at `http://localhost:9000`, and every command follows it.

```sh
./go up              # start the L0 plane and wait for it
./go smoke           # create a meetup through Envoy
./go engine-compat   # host-side engine gate: versions, then up and smoke
./go down            # stop the plane
./go test            # run backend tests
./go verify          # check the metric shape
./go demo-rollback   # release the failing version and prove automatic rollback
./go demo-seam       # attach workloads/minimal as a repository of its own and run the plane on it
./go attach <path>   # make a repository of yours the workload (its .lights-out/ is the contract)
./go detach          # back to the bundled app
./go init [<path>]   # draft the gates half of .lights-out/ in .attached/ (attaches <path> first); the baseline is measured (ADR 0042 §6)
./go gates           # judge a range: BASE=<ref> HEAD=<ref>, default the last commit; no plane, no engine socket on the workbench toolchain (ADR 0042 §4-§5)
./go demo-init       # prove attach, init and gates on workloads/minimal and workloads/minimal-js without the plane, timed against 300 s (ADR 0042 §10)
./go demo-hold       # release the same version with kill switch on and prove it holds at 25%
./go demo-gates      # run all six PR gate fixtures and prove both verdicts
./go e2e             # run the full tower: ticket → PR → CI → merge → canary → verify NO-GO → rollback, audited
./go audit           # rebuild the chain from a ticket's state: ./go audit TICKET=0001
./go resume          # request again the step a ticket failed, history kept: TICKET=<id>
./go request         # start a ticket at requested: the product role asks or confirms, then the spec gate (ADR 0055): TICKET=<id> [REQUEST_BY=<who>]
./go answer          # answer a ticket's open question, then the product role again: TICKET=<id> ANSWER=<text> [ANSWER_BY=<who>]
./go demo-rework     # prove a NO-GO goes back to the worker with its verdict, then GO and merged (ticket 0013)
./go demo-mainline   # prove main stays green without a queue: a merge under a moved perimeter goes to rework, a red main is bisected and the culprit reverted (tickets 0020-0022)
./go assign          # turn a ticket into a PR: TICKET=<id> [ROLE=dev-worker] [MAP_BRIEF=on, the map's slice in the brief (ADR 0054 §5)]
./go map             # build the project map of the workload repository at HEAD into .crew/map.sqlite: no model, no plane (ADR 0054)
./go demo-crew       # prove ticket 0001 becomes a PR that passes the M4 gates (L0 replay)
./go demo-network    # prove a network of members on ticket 0012: one PR through the whole tower (ADR 0036)
./go record          # run a ticket for real at L1 and save the fixture: TICKET=<id> [ROLE=dev-worker] [AGENT_HARNESS=claude-code|codex MODEL_PROVIDER=anthropic|openai MODEL=<id>]; a non-gemini harness writes fixtures/<ticket>/<role>/<harness>/ (ADR 0041 §10); refuses a set MODEL_BASE_URL
./go harness-conformance # every CLI harness against a scripted model, ten cases, no key: [CONFORMANCE_HARNESS=<name>] (ADR 0041 §8, 0046, 0050); builds four CLI images, not part of ./go ci or demo
./go codehost-conformance # ten cases on the CODE_HOST set: Gitea with the plane up, or `CODE_HOST=github` on an attached throwaway repository (ADR 0043 §5); not part of ./go ci or demo
./go review          # run the review step on a PR: TICKET=<id> [ROLE=test-reviewer]
./go demo-review     # prove a medium-risk PR goes through review (L0 replay of fixture)
./go record-review   # record the review role's response at L1 (TICKET=<id> [ROLE=test-reviewer] PROFILE=l1)
./go triage          # run the ops-triage role on an alert: ALERT=<file>
./go demo-triage     # prove a fake alert becomes an incident with ranked hypotheses and a proposal (no plane)
./go incident        # build an incident document from the release record: NAME= FROM= TO= [LOGS=<file>] [TICKET=<id>] (the plane only for TICKET)
./go postmortem      # run ops-triage on an incident document: INCIDENT=<file>; writes .crew/postmortem/<name>/ and files a ticket per action item
./go demo-postmortem # replay the post mortem of fixtures/incidents/demo-rollback.json, tickets into a copy of tickets/ (no plane); NO-GO until it is recorded
./go record-postmortem # record that answer at L1 (PROFILE=l1); keeps the evalset and fixtures only if the eval passes
./go promote         # go-for-launch: the brief, then GO_FOR_LAUNCH=GO|NO-GO (or the terminal), then 100% or rollback
./go demo-launch     # prove go-for-launch: held canary, brief, GO → 100%, then the un-promote
./go record-evals    # record the ADK roles' responses at L1 (PROFILE=l1)
./go mutation-baseline # whole-scope mutation score of the workload, where its TOOLCHAIN_IMAGE says (ADR 0042 §6)
./go kill-switch     # turn off waitlist for all versions (manual flag edit)
./go freeze          # stop launchpad from deploying or shifting (manual flag edit)
./go unfreeze        # re-enable launchpad after freeze
./go board           # the pipeline explained, live while the plane runs, on localhost:8099 (BOARD_PORT to move it)
./go console         # the client's console on localhost:8098: an overview, each ticket's timeline from request to release, post mortems, go-for-launch, thresholds; three writes, go-for-launch, the answer to an open question and a new request, and a spec check that writes nothing; ten screens, a theme switch (CONSOLE_PORT; CONSOLE_SNAPSHOT=<file> without the plane; ADR 0047, 0055, 0059)
./go logbook         # write the logbook, the one versioned record the console and a consumer read: LOGBOOK_FILE (default .crew/logbook.json)
./go demo-console    # prove go-for-launch pressed from the console: held canary, POST GO → 100% via console, then the un-promote
./go doctor          # host-side: engine, podman socket, git, workbench image, the plane's ports, the key the profile needs; one line each, then GO or NO-GO (ADR 0045 §4)
./go doctor --level l2   # what a level still lacks, from profiles/<level>.env (l0 to l3): one line per item, adapters with no adapters/<name>/ named "designed, not built" (ADR 0057 §8)
./go production-readiness  # GO only when delivery has passed its conformance, metrics come from your endpoint, .env holds no secret, and named people press go-for-launch (ADR 0057 §10)
./go package         # build the full image as localhost/lights-out:dev, for the lights-out wrapper (ADR 0045 §1)
./go package-gates   # build the gates image as localhost/lights-out-gates:dev (ADR 0057 §3)
./go demo-package    # prove the wrapper: build the gates image, workloads/minimal as its own repository, init, commit the draft, gates GO in the workbench under 300 s, then a staged break NO-GO at test; test-proof and test-integrity GO and NO-GO (ADR 0045 §8, 0057)
./go help            # list all targets
./go shell           # interactive shell inside workbench
./go clean           # remove the workbench image
```

With no container engine on your machine, the same three recordings run on GitHub Actions: add the key once as a repository secret (`gh secret set GEMINI_API_KEY`), then `gh workflow run record -f target=record -f ticket=0001 -f provider=gemini` (or `target=record-evals`, `target=record-postmortem`; `provider=anthropic` runs claude-code and claude-sonnet-5-5, `provider=openai` codex and gpt-6.1-sol, each from its own secret). The workflow is manual only, writes the key into a `.env` that it deletes at the end, keeps each target's own guard, and uploads the fixtures as an artifact for you to read and commit; it never pushes (`.github/workflows/record.yml`).

The first run builds the workbench image (about 1 GB on disk, 350–400 MB download, 3–6 minutes depending on connection speed). The plane pulled about 840 MB (amd64) / 720 MB (arm64) of images on the first run, more than half of it the emulators image (measured 2026-09-14, ADR 0012), which L0 no longer pulls (ADR 0060); the new total is not measured. The image no longer includes gcloud or terraform (ADR 0057 §1). `./go demo` now needs the network for the `deps` gate (osv-scanner) inside e2e, not only for image pulls.

## The image, the wrapper and the Action

ADR 0045 (M23) packaged the gates half so that it runs on a repository without cloning lights-out, and ADR 0057 (M31) split it in two images. Status: version 0.3.0 was published on 2026-11-09 by the tag `v0.3.0` (package.yml run 42588480235): `ghcr.io/nicolaguglielmi/lights-out-gates@sha256:051894c1703071a98afa4d96d58b457b566364d3029a0d9d863984c8a4736853` and `ghcr.io/nicolaguglielmi/lights-out@sha256:b5e2404c98ec45688f28c5a97039862e943539c5dfed12ea13eeb6c6d73e31e4`, both signed keyless and both signatures verified the same day with the workbench's cosign (3.1.3). From a clone the gates image is built with `./go package-gates`, the full one with `./go package`. History: 0.2.0 was published on 2026-11-08 as `ghcr.io/nicolaguglielmi/lights-out:0.2.0` (tag `v0.2.0`, index digest `sha256:d647d0555ce8dbfb622da35f068a8883af8fcd0366d07beb0a7eb53e22aa3631`, unsigned); 0.1.0 on 2026-11-05.

- **Two images**, from one `workbench/Containerfile` with two stages, for amd64 and arm64. `ghcr.io/nicolaguglielmi/lights-out-gates:0.3.0` is the gates stage plus the committed tree: `init`, `gates`, `test-proof` and `test-integrity` run in it. `ghcr.io/nicolaguglielmi/lights-out:0.3.0` is the full workbench plus the tree: `triage` and `postmortem` need it, because they need the ADK. In the gates image those two say so in one NO-GO line. Size unpacked, amd64: 508 MB for the gates image, 1,246 MB for the full one, which was 1.77 GB with gcloud and terraform (package.yml run 42519069964; 529 MB and 1.30 GB on arm64 under podman). gcloud and terraform are in neither (ADR 0057 §1).
- **Built and published** by `.github/workflows/package.yml`. It builds and tests both on every push (`./go demo-package`, `./go package`, the Action's test job). It publishes only on a `v*` tag or a manual dispatch, which is the owner's act. Proven once from the outside for 0.1.0, on 2026-11-05: on clean GitHub runners, amd64 and arm64, with no login, the wrapper downloaded by raw URL pulled the image and printed `GO: doctor`, `GO: init` and `GO: gates` on `workloads/minimal` as a repository of its own, 65 s and 72 s including the first pull (Actions run 41992224334, a throwaway branch). For 0.3.0, before publishing: the root Action and the two standalone Actions posted their checks on a pull request of a public probe repository, [nicolaguglielmi/lights-out-probe#1](https://github.com/nicolaguglielmi/lights-out-probe/pull/1), in 19 s, 2 s and 17 s, with the gates image built in the job in 23 s (run 42519118155). With 0.3.0 published, on 2026-11-09: the same three, each in a job of its own on a runner that had never pulled the image, posted their checks in 27 s, 14 s and 25 s, first pull included, all GO (probe run 42589663783); and the wrapper from the tag, on an arm64 Mac under podman, pulled the image and printed `GO: gates` in 46 s.
- **Signed keyless.** The `publish` job signs both images with Sigstore, through GitHub's OIDC token. There is no key and no secret. To check an image:

```sh
cosign verify ghcr.io/nicolaguglielmi/lights-out-gates:0.3.0 \
  --certificate-identity-regexp '^https://github.com/nicolaguglielmi/lights-out/.github/workflows/package.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

  The identity matches a tag publish. A manual dispatch publishes `:sha-<commit>` with another identity, which this command does not accept. Tags are mutable: to pin, set `LIGHTS_OUT_IMAGE` to a digest. From a clone, `LIGHTS_OUT_IMAGE=localhost/lights-out-gates:dev` points the wrapper at a local build.
- **The wrapper.** `lights-out`, version 0.3.0, a POSIX script at the repository root. The host needs podman or docker, and git. Download it by raw URL, or copy it from a clone onto your PATH.

```sh
lights-out init                      # draft to ~/.local/state/lights-out/<repo name>/.lights-out (LIGHTS_OUT_OUT moves it)
lights-out gates                     # the last commit; BASE= HEAD= for a range; STAGED=1 for what is staged, as one commit
lights-out test-proof                # test, then test-proof: the tests a change adds or changes must fail on its base
lights-out test-integrity            # test-weakening, then mutation on the changed lines
lights-out triage ALERT=<file>       # the full image
lights-out postmortem INCIDENT=<file>   # the full image
lights-out doctor                    # engine, git, image, key: one line each
lights-out version
```

  `test-proof` and `test-integrity` each print one line named for itself. `init`, `gates`, `test-proof` and `test-integrity` run the gates image; `triage` and `postmortem` the full one; `LIGHTS_OUT_IMAGE` overrides the image for every command. Your repository is mounted read-only, and `init` never writes into it. Copy the draft with `cp -R <out>/.lights-out/. .lights-out/` (the `/.` matters). Keys are read from your environment by name, never from `.env`. The engine socket is never given to the image, so the gates work for `TOOLCHAIN_IMAGE=workbench` only; `compose:` and image forms get a NO-GO naming the socket, and are judged from a clone with `./go gates`. A range is judged by the contract at its base (`workload.env`, `policy.env`, `runners/`), so a change cannot loosen what judges it. At L0, `triage` and `postmortem` replay only lights-out's own recordings: on your alerts and incidents use `PROFILE=l1` and the key in your environment. The plane (`./go demo`, canary, rollback) stays the clone path.
- **The Action.** `action.yml` at the repository root, used as `nicolaguglielmi/lights-out@v0.3.0`. It runs the wrapper of the same ref and posts one check run, `lights-out gates`, with the line as its title and a summary with one line per gate, the gates not run, and the first 20 lines of a NO-GO's details. The input `gates` is `all` (default), `test-proof` or `test-integrity`. The caller grants `contents: read` and `checks: write` and checks out with `fetch-depth: 0`. Linux runners only. Fork PRs cannot post the check (a warning; the job status still carries the verdict). A private package needs `docker login ghcr.io` before it. Up to v0.2.0 the path was `nicolaguglielmi/lights-out/action@<tag>`, and those tags keep it. Proven in lights-out's own workflows: `uses: ./` on a scratch repository, one GO and one NO-GO check run, and on lights-out itself, every push and pull request, judged by an image built from the base (`.github/workflows/self.yml`, [ADR 0049](adr/0049-lights-out-judges-itself.md)). Not proven on another repository yet. Usage is in [the guide](use-on-your-repo.md).
- **Two standalone Actions**, `nicolaguglielmi/lights-out/actions/test-proof@v0.3.0` and `nicolaguglielmi/lights-out/actions/test-integrity@v0.3.0`. Each is a shim over the Action above with `gates:` set. Their sources are `actions/test-proof/` and `actions/test-integrity/`, each with a README. The Marketplace lists one Action per repository, so each has a repository of its own with a copy at the same version, `nicolaguglielmi/test-proof` and `nicolaguglielmi/test-integrity`, created and tagged `v0.3.0` on 2026-11-09; on the probe's pull request, used from those repositories, they posted their checks in 11 s and 23 s, both GO (probe run 42591256328). Publishing each to the Marketplace is the owner's (`docs/launch/checklist.md`).

Decisions and rejected alternatives: [ADR 0045](adr/0045-one-command-one-package.md) and [ADR 0057](adr/0057-the-stepped-way-in.md).

## Coding harnesses

The coding roles run on one of four CLI harnesses, chosen by `AGENT_HARNESS`. Each has one provider, and `run.sh` refuses a mismatch with a line naming a harness that fits. Gemini has two: `gemini-cli`, the default, and `antigravity-cli`, optional and experimental (ADR 0050).

| Harness | Provider | Key variable | Guard | Boundary | Vendor sandbox | Egress |
|---|---|---|---|---|---|---|
| `gemini-cli` | `gemini` | `GEMINI_API_KEY` | `BeforeTool` hook | container | not used | `generativelanguage.googleapis.com:443` |
| `claude-code` (Claude Code 2.1.311) | `anthropic` | `ANTHROPIC_API_KEY` | `PreToolUse` hook | container | not used | `api.anthropic.com:443` |
| `codex` (Codex 0.166.0) | `openai` | `OPENAI_API_KEY`, passed to the container as `CODEX_API_KEY` | `PreToolUse` hook | container | off (`danger-full-access`) | `api.openai.com:443` |
| `antigravity-cli` (Antigravity CLI 1.5.1), experimental | `gemini` | `GEMINI_API_KEY` | `PreToolUse` hook, through a shim; only its command and file tools reach the guard, the rest are denied by name | container | none | `generativelanguage.googleapis.com:443` |

`antigravity-cli` is offered, not the default: gemini-cli stays the Gemini harness until a live agy run on ticket 0001 has passed the gates. agy is a proprietary Google binary with no licence in its repository. The image downloads it at build, pinned by version and sha256 (`adapters/antigravity-cli/release.env`), and is never published. Running it accepts Google's terms. Its telemetry and self-update hosts are denied by the egress proxy, and that denial is what keeps the pinned version pinned. **Open gap:** a repository's own `.agents/hooks.json` is loaded beside the worker's hooks, and its `SessionStart` and `PreToolUse` commands run inside the container, before the model and outside the guard. It cannot switch the guard off (the worker's hooks get a random name every run) and its `allow` does not override the guard's deny, but it runs. The container and the proxy bound it (ADR 0050 §7). A command that runs longer than 10 s goes to the background, and agy returns its output only after the model ends its turn (ADR 0050 §8).

The guard is the same `guard.sh`, copied byte-identical into each adapter. The container is the boundary for all four: no git credential, no engine socket, and only the run's directory and `/roles` (read-only) mounted. Codex's own sandbox is off because its bubblewrap cannot start in rootless podman.

The network is closed except for one door (ADR 0046). Each harness sits on an internal `crew` network only. Its one way out is the `egress` proxy (stdlib Python on the workbench image, `core/egress.py`), which opens exact `host:port` pairs: the adapter's provider host (`EGRESS` in `adapters/<h>/conformance.env`) plus whatever the workload's contract lists in `crew-egress.txt`. `app` and `workloads/minimal` list PyPI's two read hosts, `pypi.org:443` and `files.pythonhosted.org:443`. Each listed host is an open channel. The worker has its own Postgres, `crew-postgres`, not the plane's. No plane service is reachable from it.

Channels that remain:

- The provider's own host. An injected attacker key can upload the container's key there, and the proxy cannot read TLS. Each `crew-egress.txt` host is one more of the same kind.
- The pull request. `run.sh` greps the literal key. An encoded key passes.
- DNS is closed: the engine's resolver still answers the names on `crew`, but every service there has `dns: 192.0.2.1`, a documentation address that never answers, as its upstream (ADR 0046 §7). Before that, rootless podman on GitHub's Ubuntu runner resolved `example.com` from the internal network; case 9 caught it.
- The guard's `/proc/self/environ` gap (an interpreter reading the environment) now reaches only the channels above.

`MAX_TURNS`, `TOKEN_BUDGET` and `TIMEOUT_S` stop each harness, each read from the vendor's own signal. The budgets in `roles/` are Gemini measurements and bind every harness until recordings re-measure them.

`./go harness-conformance` runs the real pinned CLI in its real container against a scripted model (`gates/harness-conformance/stub.py`). It needs no key and no account. The model is simulated: the far end of the wire is a script, not a vendor. The suite proves a harness's plumbing in ten cases, 0 to 9 (guard, budgets, artefacts, served model, no key in artefacts, confinement). Case 9 is the confinement: a probe inside the harness reads its own environment (the key canary) and tries eight ways out. All eight must be blocked. The suite proves it on docker in GitHub Actions on every push. Rootless podman is run by a separate workflow, `podman` (claude-code only). <!-- podman result: filled in after the run --> It does not prove a model's ability or the real vendor wire. It builds four CLI images (about 350 MB of binaries for codex on arm64, about 560 MB of `node_modules` for claude-code, a 240 MB binary for antigravity-cli) and is not part of `./go demo`. `./go ci` runs its engine-free half, `harness-shape` and `hooks`. The full suite is its own target and a workflow job.

Found while building it, three of them older than M19, and closed: a repository's own `.env` could point gemini-cli's `GOOGLE_GEMINI_BASE_URL`, key included, at another host; a repository's own `.claude/settings.json` (`disableAllHooks`) or `.codex/config.toml` (`[features] hooks = false`) switched the guard off; the worker mounted all of `.crew/`, including the release signing key.

Recording with another harness spends the owner's keys, so it runs on demand, from a clone or on GitHub Actions (`gh workflow run record -f target=record -f ticket=0001 -f provider=anthropic`, see [Commands](#commands)):

```sh
./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=claude-code MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5
./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=codex MODEL_PROVIDER=openai MODEL=gpt-6.1-sol
./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=antigravity-cli MODEL_PROVIDER=gemini MODEL=gemini-3.8-flash
```

These write `fixtures/<ticket>/<role>/<harness>/`. L0 keeps replaying gemini-cli's `fixtures/<ticket>/<role>/`, and replay does not read the new directories yet. Claude and OpenAI cost money per run. The cost per provider will be stated here once a recording is committed.

The first Claude run, on GitHub Actions on 2026-11-04: `record-evals` GO for the three ADK roles; `record` on ticket 0001 `GO: crew`, then `NO-GO: mutation` 5/8 (0.625 < 0.666), the three surviving mutants on one comparison in `app/backend/meetups/geocoder_client.py`. No Claude recording is committed. A NO-GO saves no fixture, and an ADK recording is keyed by its input, not by provider, so committing Claude's would replace Gemini's, which the default profile replays. OpenAI has not run.

## Levels

Local first, cloud optional (ADR 0022): L0 and L1 are the whole product, no capability exists only in the cloud; L2 and L3 swap containers for managed Google services.

| | **Local — the product** | | **Cloud — optional** | |
|---|---|---|---|---|
| | L0 · Replay | L1 · Local | L2 · Cloud | L3 · Platform |
| **Needs** | podman rootless (podman machine on macOS) | + the chosen provider's API key (Gemini's free tier is the free path) | + GCP project with billing | + Agent Engine quota |
| **Models** | Recorded responses (fixtures) | The profile's `MODEL_PROVIDER`/`MODEL` (ADR 0040): Gemini API `gemini-3.8-flash` by default; Claude or OpenAI for the ADK roles | idem, Gemini via Gemini Enterprise Agent Platform | idem + thinking level per role |
| **Harness worker** | Replay from `fixtures/` | Gemini CLI headless in compose | Gemini CLI on Cloud Run Job | + adapter Antigravity SDK |
| **Git and PR** | Gitea in compose | Gitea; GitHub for an attached repository with `CODE_HOST=github` (M21, ADR 0043; run end to end only by the owner, once) | GitHub real | GitHub real |
| **CI** | `./go ci`; the tower's gates on each PR (no runner, ADR 0060) | idem | GitHub Actions or Cloud Build | idem |
| **Registry and signing** | Zot local, local key, signature verified before staging (M8) | idem | Artifact Registry, KMS key, Binary Authorization | idem |
| **App database** | Postgres in compose | idem | Cloud SQL — does not scale to zero, the one fixed cost; stop or delete it between runs (`infra/README.md`) | idem |
| **Canary** | Envoy weighted cluster | Envoy | Cloud Deploy → Cloud Run | + option GKE |
| **Metrics** | `promql` on `METRICS_URL`; `prometheus` is its case at `http://$PLANE_HOST:9090` | idem | Managed Prometheus + Cloud Monitoring | idem |
| **Flags** | flagd (file) | flagd | flagd on Cloud Run or Unleash | idem |
| **Events and state** | `spool` + `sqlite`, files under `.crew/` (ADR 0060) | idem | Pub/Sub + Firestore | + adapter Cloud Workflows |
| **Agent ADK** | Replay of recorded model responses (`fixtures/adk/`) | ADK 2.9.1 in workbench on the profile's model: Gemini natively, Claude and OpenAI through ADK's `LiteLlm` (`litellm` 1.106.6), thinking per role mapped in `adapters/adk/thinking.env` | ADK on Cloud Run | Agent Engine + BigQuery analytics |
| **Time to first rollback** | < 15 min | < 20 min | ~45 min (terraform apply) | ~90 min |

*Note: Google renamed Vertex AI to Gemini Enterprise Agent Platform in April–May 2026. The endpoints, `GOOGLE_GENAI_USE_VERTEXAI` environment variable, and `aiplatform.googleapis.com` remain unchanged; `vertex` still appears in env vars and Terraform.*

*Note: since June 18, 2026 Gemini CLI no longer serves Google AI Pro/Ultra, Gemini Code Assist for individuals, or the free login with Google. The documented path is a Gemini API key (free tier: about 250 requests per day, Flash models only) or Gemini Enterprise Agent Platform. Whether a free-tier key still works with Gemini CLI is verified at M5.*

L0 and L1 run today, with the adapters under `adapters/`. L2 and L3 are designed, not run.

### The cloud track

The Google Cloud profiles (L2 and L3) are designed, not run. They are built when someone pays for them. Their adapters (`pubsub`, `firestore`, `cloud-deploy`, `managed-prometheus`, `artifact-registry`, `cloud-workflows` and `github-issues`) do not exist under `adapters/`, and the cloud toolchain is not in the images (ADR 0057 §1). `./go doctor --level l2` lists what is missing, one line per item.

## The app

This workload (the default, `WORKLOAD=app`) is a meetup RSVP platform: FastAPI backend (`app/backend/`), Postgres database, React frontend (`app/frontend/`). The app is one implementation of the `Workload` port (ADR 0030); another is `workloads/minimal/`, a minimal second workload that exists only to prove the seam. After `./go up` it answers behind Envoy at `http://localhost:8080` on the host or `http://host.containers.internal:8080` from inside workbench. Three auth-free endpoints list meetups, two auth routes signup and login, one create route, one RSVP route. Geocodes venues through a fake `GEOCODER_URL`. Feature-flagged partial waitlist (evaluates but returns 501 at M1).

Test and verify commands:
- `./go test` — Run the backend test suite against compose Postgres (pytest, 25 tests).
- `./go verify` — Check `verify/slo.promql` against the live app (metric shape only; evaluation at M3).

## PR gates

Eight gates run in order on a git range (the merge-base of `BASE` and `HEAD`, or the last commit when no range is given; a root commit's base is the empty tree, ADR 0042 §5); the first NO-GO stops the rest. Both verdicts are proven by committed fixture patches. Run with `./go demo-gates` on the nine fixtures, or `./go gates BASE=<ref> HEAD=<ref>` on your own range.

**Order** (`GATES` in the `Makefile`, the board's GATES station in the same order): risk (rules-based classification from path and size), secrets (gitleaks history and working tree), test-weakening (`gates/test-weakening.sh`: the diff of `WORKLOAD_TEST_PATHS` loses no test file, assertion or test definition and gains no skip, xfail, todo or only marker that the ticket's `## Removes tests` does not declare; no toolchain), deps (osv-scanner on both lockfiles, a time bomb by design), SAST (bandit on the active workload's `WORKLOAD_MUTATION_SCOPE`), test (pytest, one failing assertion proves it works), mutation (cosmic-ray on changed lines, scored against a measured baseline), test-proof (`gates/test-proof.sh`: the changed tests, taken onto the base without the change, must fail there; ADR 0053).

**The light tier** (ADR 0061): `lights-out gates --light` runs, with no engine, the gates of this list that need only git and Python, risk and test-weakening, plus perimeter and spec on a ticket (`TICKET=<file>`) and test then test-proof on the host (`TEST_ON_HOST=1`); secrets, deps, SAST and mutation need the image. Its line is `GO: gates-light — risk <level>, <decision>; <n> of 10 gates ran; …` and names what did not run, or `NO-GO: gates-light — <gate>: <reason>`; it is never the judge's `GO: gates`. A range is judged by its base's contract, `STAGED=1` writes nothing to the repository, and `GATES_OUT=<dir>` leaves a `verdict.env`. `ci/gates-light.sh` runs it on the nine fixtures below and requires the same verdict where both run.

**Risk levels:** `low` → `auto-merge`; `medium` or `high` → review. The risk classifier reads five signals: auth, payments, migrations, platform (gates/ci/verify/policy/core and the toolchain), and diff size. Policy lives in `policy/merge.env`, readable by sh and Python.

**Nine fixtures:** `honest-fix` (ticket 0001 resolved, every gate GO, risk low); `fake-test` (same fix, inadequate test, mutation NO-GO); `migration` (adds a schema column, every gate GO, risk high); `sast-finding` (one bandit issue); `vulnerable-dep` (a known advisory); `failing-test` (one assertion fails); `test-passes-on-base` (a contract change whose test already passed on the base, test-proof NO-GO); `assertion-removed` (one assertion dropped from an existing test, test-weakening NO-GO); `test-edited` (a contract value corrected and the assertions pinning it edited, every gate GO; ADR 0053). Each fixture is a git-format-patch `.patch` file applied in a worktree, with expected verdicts and JSON data recorded in `expect`.

**Declared limits:** The gates do not name the app or any workload (verified by `ci/app-free.sh`); instead, they read the active workload's `workload.env` configuration (`WORKLOAD_MUTATION_SCOPE`, `WORKLOAD_LOCKFILES`, `WORKLOAD_KILL_SWITCH`, `MUTATION_BASELINE`). Dependency scan covers both dev and runtime dependencies in the workload and workbench (cosmic-ray and other test tools are included) and is live-validated against the OSV database over the network; `adapters/gemini-cli/package-lock.json` (the Gemini CLI platform toolchain) is declared and not scanned, like workbench's own pinned binaries; the same commit can go from GO to NO-GO overnight with no code change when a new advisory lands (the fix is a version bump or an `osv-scanner.toml` ignore entry with a reason). The migration fixture's column lands in the shared `postgres-data` named volume (the same one `./go up` and `./go test` use) and stays there across runs, harmless to every current test (they use explicit column lists, never `SELECT *`); `./go down` does not remove it, only `docker-compose --profile test --profile canary down -v` from inside `./go shell` does, or a fresh clone. At M4 the Gitea runner has no engine socket; the `gates` CI job runs only on GitHub (`if: github.server_url == 'https://github.com'`). At M8 the socket arrives, but not for this job: it goes to a new `image` job that builds, signs and pushes the merge commit (below); `gates` stays GitHub-only until the milestone that runs the tower on GCP. The socket's three conditions (ADR 0015 §7, ADR 0025 §4): the runner is the only compose service with it, jobs run only on refs the workbench user pushed, and the trusted-network line below says so.

**Model reality check:** The worker pins Gemini CLI `0.61.0-preview.0`, deliberately on the preview channel, because `0.59.0` and the current stable `0.60.0` silently serve `gemini-3.5-flash` when asked for `gemini-3.8-flash` (upstream fix google-gemini/gemini-cli#29252, in no stable release yet); the pin returns to the stable channel at `0.61.0`. A live L1 run on this pin answers from `gemini-3.8-flash` (verified 2026-09-16). The fixture at `fixtures/0001/dev-worker/` stays recorded on `gemini-3.5-flash` — its `run.json` says so — so at L0 the replayed PR was written by 3.5 while a live L1 run answers from 3.8, until the fixture is next re-recorded. See ADR 0018. Since M18 the id comes from `MODEL` in the profile (ADR 0040), still `gemini-3.8-flash`. Since M19 (ADR 0041) the other two harnesses are pinned the same way, by `package-lock.json` in their adapter: Claude Code `2.1.311` (the npm `stable` tag; latest was 2.1.318) with provider `anthropic` and `ANTHROPIC_API_KEY`, and Codex `0.166.0` (latest; no stable channel) with provider `openai` and `OPENAI_API_KEY` passed to the container as `CODEX_API_KEY`. Each `run.sh` refuses another provider. `MAX_TURNS` and `TOKEN_BUDGET` in `roles/` are Gemini measurements and bind all three until recordings re-measure them; the first Claude or OpenAI run may hit a budget for tokenizer reasons alone. The served model is read from the vendor's own signal (the `assistant` events for Claude, a trace line on stderr for Codex) and is `unknown` when unreadable. The conformance suite uses a scripted model. Claude Code's pin has run against the real API once (2026-11-04, see [Coding harnesses](#coding-harnesses)); Codex's has not. Antigravity CLI `1.5.1` (ADR 0050) is pinned by `release.env`, a version and a sha256 per architecture, provider `gemini`; its served model is read from its conversation store, which nobody documents, and is `unknown` when unreadable; it has answered a real key once, in the spike (`gemini-3.8-flash` served as asked), and has no recorded run.

**Found building M19 (ADR 0041):** three holes, each closed. A repository's own `.env` could point gemini-cli's `GOOGLE_GEMINI_BASE_URL`, key included, at another host; the adapter now always sets it. A repository's own `.claude/settings.json` with `disableAllHooks`, and its `.codex/config.toml` with `[features] hooks = false`, each switched the guard off; the adapters now run Claude Code with `--setting-sources user` and Codex with `--enable hooks`, and conformance case 4 checks it. The worker used to mount all of `.crew/`, including the release signing key `.crew/cosign.key`; it now mounts only its run directory (the parent of `OUT`).

## The L0 plane

Five services run beside the app in `compose.yaml` (eight before ADR 0060: the Gitea runner left, the two emulators became opt-in). `./go up` returns only after each adapter's `adapters/<name>/ready.sh` answered; `sqlite` and `spool` answer by creating their file under `.crew/`.

| Service | Host port | What |
|---|---|---|
| Envoy | 8080 | The app's only entrance; shifts traffic between `stable` and `canary` via weighted clusters, admin API on 9901 |
| Envoy admin | 9901 | Runtime config: `GET /runtime` reads weights, `POST /runtime_modify` shifts traffic between stable and canary |
| backend | implicit | Stable revision, answering at port 8000 inside compose |
| backend-canary | implicit | Canary revision (started on-demand by deploy, same image as backend); answering at port 8000 inside compose |
| Gitea | 3000 | Rootless, sqlite; bootstrap creates a fixed admin user (`lights-out` / `lights-out-local-not-a-secret`) and a public `lights-out/workload` repo holding the workload's repository (this checkout, or the attached one); Actions off and no runner (ADR 0060 §5) |
| Prometheus | 9090 | Scrapes both backends every 5 s; canary and stable tell apart by the `service_version` label reached via `target_info` join |
| Zot | 5050 | OCI registry, empty until a merged PR is built into an image (M5 at the earliest); 5000 is macOS AirPlay |
| flagd | 8016 | OFREP; serves the active workload's `flags/flags.json` (`$WORKLOAD_CONTRACT/flags/flags.json`, bind-mounted dynamically); edit the file and the flag flips within seconds |
| Pub/Sub emulator | 8085 | Opt-in, `EVENT_BUS=pubsub-emulator` (compose profile `emulators`): event bus for the tower's step events (topic `tower`, subscription `tower-inproc`) |
| Firestore emulator | 8086 | Opt-in, `STATE_STORE=firestore-emulator` (compose profile `emulators`): one JSON document per ticket (`tickets/<id>`) |

At L0 and L1 the event bus and the state store are not services: `spool` keeps the tower's step events in `.crew/spool.sqlite`, `sqlite` keeps one JSON document per ticket in `.crew/state.sqlite`. Both outlive `./go down`, and no harness container mounts them. So does a stranded ticket, a red `mainline/main` that refuses `assign`, or an open ticket's perimeter hold: the demos delete their own documents first; otherwise `./go resume TICKET=<id>`, or remove `.crew/state.sqlite` and `.crew/spool.sqlite` with the plane down to start empty. `./go statestore-conformance` and `./go eventbus-conformance` prove an adapter against its port (ADR 0060 §4).

`./go smoke` signs up, logs in and creates a meetup through Envoy.

**L0 assumes a trusted network**: every port is unauthenticated on every interface, and anyone on the LAN can push to Gitea or Zot. No compose service holds the engine socket since ADR 0060 retired the Gitea runner (ADR 0015 §7's grant).

At L0 the canary revision reuses the same image as stable, with the `waitlist` feature flag (the app's `WORKLOAD_KILL_SWITCH`) targeted at the version string `0.2.0-waitlist` (the app's `CANARY_VERSION`): the failing version is the same code, different flag targeting. The Workload port generalizes this to any workload (ADR 0030). The first real code diff arrives with the M5 worker.

## Release controller

`core/launchpad.sh` is the production release flow at every level. It stages a canary through four phases: `staging` (app readiness), `5%`, `25%`, then holds for the human gate (M7 `go-for-launch`). At each phase except staging it evaluates `verify/slo.sh`, comparing the canary against stable on three metrics: `traffic`, `error_rate`, and `latency_p95`. A NO-GO at any stage rolls back automatically to 100/0 on stable. A stage whose Metrics query fails (curl error, HTTP error, an answer that is not JSON or not `success`) cannot be judged: `verify/slo.sh` prints `NO-GO: slo — cannot judge: <query>: <cause>` and the launchpad `NO-GO: launchpad — <pct>%: cannot judge: … → rolled back`. It rolls back too, but it is never read as a verdict on the canary ([ADR 0066](adr/0066-a-canary-that-cannot-be-judged.md)). `verify/slo.promql` collapses `target_info` by `(job, instance, service_version)` before the join, so a stale series left by a restarted target does not break it.

The controller itself generates no load; the Makefile starts the active workload's `load.sh` (`$(WORKLOAD_CONTRACT)/load.sh`, default `app/load.sh`) beside it, stopping when the controller exits. A `load.sh` that cannot set up its traffic says so on stderr and exits non-zero; the release then rolls back on `no traffic from canary` (ADR 0066 §4). The canary deploy starts `backend-canary` alone (`--no-deps`), leaving the plane's other services as `./go up` started them.

At L0, the release is a manual Makefile target (`./go release` with `CANARY_VERSION`). Three proof commands demonstrate the flow:

- `./go demo-rollback` releases the failing version (waitlist on), expects the kill switch's `error_rate` NO-GO at 5% and refuses any other reason (`cannot judge`, `no traffic`), and asserts the rollback (weights.canary=0, traffic on stable). `./go e2e` checks the same verdict on its release record (ADR 0066 §5). This is now `./go demo`'s last stage.
- `./go demo-hold` releases the same failing version with the kill switch thrown first (waitlist off), expects GO all the way, and asserts the canary is held at 25% (not silently rolled back), then rolls back itself for clean state.
- `./go demo-launch` proves go-for-launch: a held canary, the brief, `GO_FOR_LAUNCH=GO` to promote to 100%, then the un-promote. A reader can step through the stages or let it run end-to-end (~150 s warm).

**Release of an attached repository (ADR 0043 §4), at any code host.** The bundled app still waits for the Gitea `image` job. For an attached repository `core/steps/release.sh` fetches the default branch, checks that the merge is on it, builds the merge commit in a throwaway worktree with `make publish` (the repository's own Containerfile, through the `backend` service of its `.lights-out/compose.yaml`) and signs it. The unchanged launchpad then verifies the signature and releases. `TOOLCHAIN_IMAGE` is not a release artefact: it holds no application. A workload without `.lights-out/compose.yaml` has no release. The build has no timeout of its own.

`demo-rollback` and `demo-hold` are manual, optional; only `./go demo` (which includes `demo-rollback`) is on the critical path. `demo-launch` is also optional; the manual human path is `./go kill-switch`, `./go release`, `./go promote` (the answer travels as `./go promote GO_FOR_LAUNCH=GO`; `go` forwards no host environment).

**Kill switch and freeze** are feature-flag edits in the active workload's `flags/flags.json`, live within seconds through flagd's file poller, no deploy:
- `./go kill-switch` turns off the active workload's kill-switch flag (named by `WORKLOAD_KILL_SWITCH`; for the app it is literally `waitlist`) for every version: the canary stops producing 501s.
- `./go freeze` / `./go unfreeze` toggle the `release-freeze` flag: `on` stops launchpad from deploying or shifting.

**Timing budget**: plan §2 requires `./go demo` to reach automatic rollback in under 900 s on a fresh container (cold pulls included). M3 measured this at 92 s warm (images already present); with the baseline 258 s cold from M2, a reasoned estimate is roughly 350 s total, well under budget. (Caveat: the 350 s figure is an estimate, not a fresh cold measurement this session, because forcing a safe cold re-pull of ~50 host images was not performed here.)

## The Workload port

A workload is any directory that owns a `workload.env` file and provides the services and scripts the platform expects. The app and `workloads/minimal/` are two implementations; `WORKLOAD=<path>` (default `app`) selects which one runs. The contract is declared in ADR 0030: seven environment variables (e.g., `CANARY_VERSION`, `WORKLOAD_KILL_SWITCH`, `WORKLOAD_MUTATION_SCOPE`), three compose services (`backend`, `backend-canary`, `backend-test`), health and metrics endpoints on `:8000`, one flag file, `smoke.sh` and `load.sh`, in-image test runners (`tests/mutation/run.sh`, `tests/sast/run.sh`), and gate fixtures. Every gate and control system reads these values instead of naming the app, verified by `ci/app-free.sh`. `./go demo-seam` (like `demo-rollback` and `demo-launch`, outside the main `demo`) proves the seam is real: two distinct workloads, same platform.

A workload can also live in a repository of its own (ADR 0037). `./go attach <path>` clones it into `.attached/`, which becomes the default `WORKLOAD` until `./go detach`. Its contract is in `.lights-out/` at its root and nowhere else: the files above plus `worker.md` (the dev-worker's brief), an optional `policy.env` (nine overridable thresholds, each with a provenance line, read by `core/policy.py`) and optional `tickets/`. The gates diff its history, Gitea mirrors it, and a PR is judged by its base's `workload.env`, `policy.env` and `runners/` (ADR 0033). `workloads/minimal/` is laid out this way; `./go demo-seam` copies it into a fresh repository and attaches it. [Use it on your own codebase](use-on-your-repo.md) is the walkthrough.

## How it runs

`./go <target>` builds `workbench/Containerfile` and runs `make <target>` inside it with the repo mounted at the same absolute path as on the host. The workbench image carries make, git, gcloud, terraform, and all verification tools, so the host needs only a container engine and a shell.

Profiles: `./go demo PROFILE=l2` selects `profiles/l2.env`. Secrets go in `.env` (gitignored, template `.env.example`). L0 needs no `.env`. Two optional keys serve `./go verify` on your own metrics (ADR 0044): `METRICS_URL`, the base that `/api/v1/query` is appended to, and `METRICS_AUTH_HEADER`, one header line such as `Authorization: Bearer …`, never printed. `./go demo` and the plane's own judge ignore both.

Two more keys serve the GitHub code host (ADR 0043): `GITHUB_REPO=<owner>/<name>` and `GITHUB_TOKEN`, a fine-grained token for that one repository with Contents, Pull requests and Commit statuses, read and write. `CODE_HOST=github` goes on the command line, never in `.env`, because in `.env` it would also redirect `./go demo`. The token reaches curl on stdin and git through a credential helper the Makefile adds as env-scoped config; it is in no argv, no `.git/config` and no model container.

### Workflows

`.github/workflows/ci.yml` runs `./go ci` and the `launch` job. Since M21 the `launch` job ends with `./go codehost-conformance` against Gitea, with the plane up, on every push. `.github/workflows/nightly-github.yml` runs the same suite daily against GitHub, on a throwaway repository named by the repository variable `LIGHTS_OUT_GITHUB_REPO`, with the secret `LIGHTS_OUT_GITHUB_TOKEN`. While the variable is unset it prints a notice and skips; a variable without the secret fails. The nightly does not run the full e2e: it proves the eight verbs on GitHub, not the tower on GitHub.

### Engine socket

Targets `up`, `down`, `test`, `demo`, `demo-rollback`, `demo-seam`, `e2e`, and `shell` mount the engine's API socket into workbench, which gives the container full control of the engine. It can start privileged containers, read any volume, and delete images. For `gates`, `init`, `mutation-baseline` and `demo-init` the socket is optional (ADR 0042 §4): mounted when it exists, and a toolchain other than `workbench` answers NO-GO naming it when it does not.

The `ci` target never gets the socket. `engine-compat` is the one gate that runs on the host itself, before workbench starts: `./go engine-compat` and `./go demo` both begin with `ci/engine-compat.sh`.

### Rootless notes

The engine socket is `unix:///run/user/$(id -u)/podman/podman.sock`. Enable it with:

```sh
systemctl --user enable --now podman.socket
```

(On macOS, `podman machine` enables it automatically.)


Rootless podman usage:

- All published ports must be above 1024.
- Bind mounts get no `:z` (relabelling fails on podman machine's virtiofs, podman #26465/#21269); the one bind-mounted service (flagd) uses `security_opt: label=disable`.
- Use `host.containers.internal` instead of `host.docker.internal`.
- Prefer compose network aliases over any `host.*.internal` name.

Only the docker-compose features proven by `./go engine-compat` are allowed; proven at M2 on podman: `build` with `args`, `depends_on` long syntax, `profiles`, `ports`, `user`, `restart`, `security_opt`, a read-only bind mount.

## Repository

```
lights-out/
  LICENSE                   # Apache 2.0 license
  NOTICE                    # copyright
  README.md                 # this file
  Makefile                  # targets: help, ci, ci-*, demo, up, smoke, down, test, verify, demo-rollback, demo-seam, demo-hold, demo-launch, triage, demo-triage, incident, postmortem, demo-postmortem, record-postmortem, promote, record-evals, kill-switch, freeze, unfreeze, e2e, request, answer, board, logbook, console, demo-console
  go                        # host entrypoint, POSIX sh
  .env.example              # template for secrets (gitignored)
  .gitignore

  workbench/
    Containerfile           # the toolchain: make, gcloud, terraform, tools
    fetch.sh                # script for verifying downloads

  board/
    index.html              # the board: scripted scenarios, live view (ADR 0035)
    serve.py                # serves it and /state.json, read through the port verbs

  console/
    index.html              # M11: the client's ten screens over the logbook, a theme switch (ADR 0047, 0059)
    serve.py                # serves it, /v1/logbook.json (ETag), and four POSTs: go-for-launch, answer, request, and the spec check that writes nothing
    README.md               # how to run it, CONSOLE_AUTH, what is real at L0, who built it

  core/
    launchpad.sh            # release controller: stages, verify gates, automatic rollback
    incident.sh             # M22: ./go incident, the incident document from the release record
    postmortem.sh           # M22: ./go postmortem, runs the role, checks and files tickets
    postmortem.py           # M22: the document and anchor checks
    logbook.sh              # M11: ./go logbook, the one versioned record (ADR 0047 §2)
    logbook.py              # M11: its reader, by the rules in docs/plans/console.md; 1.1 adds the timeline (ADR 0055), 1.2 the map's ADRs (ADR 0059)
    spec.py                 # M29: the spec gate and the product role's step before the ticket (ADR 0055); `draft` turns the request editor's fields into a ticket file (ADR 0059)
    logbook/1.0.schema.json # M11: the logbook's schema, one file per minor (1.0, 1.1, 1.2)
    risk.py                 # risk classifier: rules-based PR scoring
    tests/                  # unit tests for risk.py

  policy/
    merge.env               # policy-as-code: risk levels, mutation baseline and margin

  gates/                    # PR gates: risk, test-weakening, deps, sast, test, mutation, test-proof
    *.sh                    # individual gate scripts (read WORKLOAD_* from active workload)

  profiles/
    l0.env                  # L0: podman, no key, no account
    l1.env                  # L1: + MODEL_PROVIDER, MODEL and that provider's key
    l2.env                  # L2: + GCP project
    l3.env                  # L3: + Agent Engine quota

  ci/                       # repo self-checks; each prints one line, GO or NO-GO
    lib.sh                  # go / nogo helpers, the output contract; record_check keeps each check's stdout and exit code for the run (ADR 0062)
    contract.sh             # meta-gate: every gate honours the contract; under ./go ci it judges the record of each check's one run, alone it runs every gate cold (ADR 0062)
    harness-shape.sh        # every CLI harness: pinned version and lockfile, thinking.env, conformance.env, guard.sh identical to gemini-cli's, fragments name every harness service (ADR 0041 §9)
    hooks.sh                # the guard's cases in each vendor's input shape (gemini, Claude, Codex)
    secrets.sh              # gitleaks, history and working tree
    lint.sh                 # actionlint on the workflow
    shell.sh                # shellcheck on every sh script
    help.sh                 # make help exits 0
    docs-drift.sh           # every path, ./go command and NAME= key a page cites exists (ADR 0054 §3)
    map.sh                  # the project map end to end: this repository, workloads/minimal, a stale map refused, a docs ticket (ADR 0054)
    codehost.sh             # every code host adapter: the eight verbs and ready.sh, credential.sh answers, the Makefile's git config index, the token never in argv (curl and git replaced by recorders, `date` by a clock that moves a second per read; no network, no fake GitHub; ADR 0043 §5)
    profiles.sh             # profiles are plain KEY=value, same keys
    store-bus.sh            # the StateStore and EventBus suites on sqlite and spool, and each suite failing on a broken adapter (ADR 0060 §4)
    workloads.sh            # validate every workload's workload.env (replaces compose.sh)
    app-free.sh             # verify core/gates/verify/adapters never name the app (ADR 0030)
    engine-compat.sh        # host side, runs first in ./go (ADR 0012)

  docs/
    ARCHITECTURE.md         # ports and adapters
    PLAN.md                 # working plan (Italian)
    adr/                    # architecture decision records
      0001-profiles-and-single-makefile.md
      0002-self-ci-is-make-ci.md
      0003-make-demo-before-m3.md
      0004-containerised-toolchain.md
      0005-backend-stack-and-auth.md
      0006-external-service-geocoder-fake-and-contract.md
      0007-metrics-and-feature-flags.md
      0008-sql-migrations-expand-contract.md
      0009-frontend-built-into-backend-image.md
      0010-compose-layout-and-app-tests.md
      0011-slo-queries-and-metric-shape-gate-at-m1.md
      0012-l0-plane-layout-runner-envoy-readiness.md
      0013-launchpad-canary-verify-rollback-at-l0.md
      0014-prove-the-go-branch-with-demo-hold.md
      0015-pr-gates-at-m4.md
      0016-risk-model-and-merge-policy.md
      0017-agent-runtime-at-m5.md
      0018-gemini-cli-pin-for-the-model-id-fix.md
      0019-control-plane-at-m6.md
      0020-adk-agents-and-go-for-launch-at-m7.md

  verify/                   # SLO verification; shape-checked at M1, evaluated at M3
    slo.promql               # traffic, error_rate and latency_p95, canary vs stable via target_info join
    metric-shape.sh         # checks them against one live /metrics scrape
    slo.sh                  # verifies canary metrics against stable, the release gate

  app/                      # the default workload (docs/adr/0005-0010)
    backend/                 # FastAPI + psycopg, meetups/, migrations/, tests/
    frontend/                # React + Vite + TypeScript, built into the backend image
    fakes/geocoder/          # the external-service dependency, stdlib only
    contracts/geocoder/      # the fake's committed example-pair contract
    flags/                   # flagd file-resolver flag definitions
    load.sh                  # load generator: loops registration POSTs through Envoy
    smoke.sh                 # signup, login, meetup through Envoy
    fixtures/gates/          # gate fixtures proving risk, test, mutation, deps, sast, secrets
      <name>/
        *.patch              # git-format-patch applied in worktrees
        expect               # expected gate outcomes and JSON data

  workloads/                # other workloads behind the Workload port
    minimal/                 # a second minimal workload (no database, no frontend; proves the seam)
      fixtures/gates/        # gate fixture for this workload (at least one required)
    minimal-js/              # a second workload, javascript, gates half only: the gates on a repository with no plane (ADR 0042 §9)

  stacks/                   # the gate runners ./go init copies into a repository, one directory per stack, each with its lockfile (ADR 0042 §7)
  compose.yaml               # the L0 plane: workload + Gitea, Zot, Envoy, Prometheus, flagd; the emulators opt-in

  adapters/                 # one directory per adapter named in profiles/*.env
    adk/                    # M7: ADK roles, replay/recording model, evalsets
    envoy-canary/           # Containerfile, envoy.yaml, ready.sh, deploy.sh, shift.sh, rollback.sh
    prometheus/             # Containerfile, prometheus.yml, ready.sh, query.sh (calls promql with http://$PLANE_HOST:9090)
    promql/                 # M22: query.sh, any Prometheus-compatible endpoint at METRICS_URL
    gitea/                  # ready.sh and the eight CodeHost verbs; no runner (ADR 0060)
    github/                 # M21: the eight CodeHost verbs, ready.sh, env.sh, credential.sh; GitHub's REST API, an attached repository only (ADR 0043)
    flagd/                  # ready.sh
    zot/                    # ready.sh
    sqlite/                 # M34: get.sh, put.sh, delete.sh, ready.sh over store.py; the L0/L1 StateStore, .crew/state.sqlite (ADR 0060)
    spool/                  # M34: publish.sh, pull.sh, ack.sh, ready.sh over spool.py; the L0/L1 EventBus, .crew/spool.sqlite (ADR 0060)
    pubsub-emulator/        # opt-in EventBus, compose profile emulators
    firestore-emulator/     # opt-in StateStore, compose profile emulators

  roles/                    # M5/M7: agent role definitions (prompt.md + role.env; the three ADK roles name HARNESS=adk)
  policy/                   # from M4: policy-as-code
  tickets/                  # project tickets, one per file; 0001 is the first bug found
  gates/                    # from M4: PR gates, identical at every level
  fixtures/                 # M5: recorded agent responses at L1, replayed at L0; fixtures/adk/: recorded ADK model responses; fixtures/incidents/: the incident documents (M22)
  .crew/                    # M5: per-ticket workspace and output directory (gitignored)
  design/                   # from M11: Stitch artifacts for the console (ADR 0023)
  console/                  # from M11: the view over git and the state store (ADR 0023)
  infra/                    # from M8: Terraform for GCP
  e2e/                      # from M6: golden path test
```

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — the port/adapter pattern, how levels compose
- [docs/use-on-your-repo.md](use-on-your-repo.md) — put your own codebase behind the gates and the rollback
- [docs/adr/](adr/) — architecture decision records
- [PLAN.md](PLAN.md) — the working plan (Italian)
- [app/README.md](../app/README.md) — the target application: routes, auth, migrations, metrics, flags
