# Tutorial: lights-out in one sitting

This is a guided path through lights-out, in five steps:

1. Run the demo and read what happened, stage by stage.
2. Take the short looks: rework, triage, post mortem, go-for-launch.
3. Put the gates on your own repository, without the plane.
4. Write a ticket and hand it to an agent at L1, with a key.
5. Run the ops commands on an incident and on your own metrics.

Steps 1 to 3 need no account and no API key. Step 4 needs a model key.
Step 5 needs a key only for `./go postmortem` on your own incident.

**About the outputs.** Every output block below is real. Each one is
copied from a GitHub Actions run of this repository, or printed by a
command run on a file this repository commits. The source is named under
each block, and an HTML comment beside it gives the run id. Where lines
were left out (container build noise, the signature's JSON), the source
line says so. Your digests, commit ids and timings will differ. Where no
real output exists, the tutorial says so and shows none.

The [README](../README.md) is the short version. [The
reference](reference.md) has every command, and [the
guide](use-on-your-repo.md) has every key of `.lights-out/`.

## 0. Before you start

Install podman (or use docker) as the README's "Try it" table says, then
clone and check your machine:

```sh
git clone https://github.com/nicolaguglielmi/lights-out.git
cd lights-out
./go doctor
```

`./go doctor` prints one line per item (engine, podman socket, git,
workbench image, the plane's ports, the key your profile needs) and ends
with `GO: doctor` or `NO-GO: doctor — <items>`. The ports 3000, 5050,
8016, 8085, 8086, 9090, 9901 and 8080 (or `APP_PORT`) must be free.

On docker, put `CONTAINER_ENGINE=docker` before every `./go`. That is what
the CI runs below did.

Every gate in lights-out prints exactly one line on stdout: `GO: <name>`,
sometimes followed by ` — <detail>`, or `NO-GO: <name> — <reason>`. The
lines around the verdicts are progress, and the evidence behind each
verdict.

## 1. The demo, and how to read it

```sh
./go demo
```

The first run downloads about 1.2 GB and builds the toolchain image, so
expect 10 to 15 minutes. Later runs take about 7 (README). The demo runs,
in order: `ci`, `up`, `smoke`, `verify`, `demo-rollback` and `e2e`. The
last two are the story.

### The repository checks itself

`./go ci` runs the repository's own checks. Each prints one line. The
last ones in the run:

<!-- source: GitHub Actions run 41866972654 (commit ee2f679), job engine-compat (126703546061), step "./go demo" -->
```
GO: metrics
GO: package
GO: contract
GO: ci
```
*GitHub Actions run 41866972654, job engine-compat, last four lines of `ci`.*

`GO: contract` is the meta-gate: it runs every gate with stdout captured
and fails if one prints more than one line, a colour code, or an exit code
that disagrees with its verdict.

### The plane comes up

`up` starts the L0 plane: Gitea, Envoy, Prometheus, flagd, Zot and the two
Google emulators, beside the app. `smoke` creates a meetup through Envoy.
`verify` checks the shape of the metrics against one live scrape.

<!-- source: GitHub Actions run 41866972654 (commit ee2f679), job engine-compat (126703546061), step "./go demo" -->
```
[demo] up: L0 plane, gitea envoy-canary prometheus flagd zot pubsub-emulator firestore-emulator
smoke: meetup 2 created through Envoy at http://host.containers.internal:8080 (venue_lat=45.4641)
[demo] smoke: the happy path passed through Envoy at http://host.containers.internal:8080
metric-shape: checked query/app agreement against one live scrape (metric and label names, semconv seconds buckets, status-code value format)
GO: metric-shape
metric-shape: did not evaluate rate() or histogram_quantile() — needs a TSDB (Prometheus at M2, canary vs stable comparison at M3)
[demo] verify: metric shape only; canary vs stable is evaluated inside demo-rollback below
```
*GitHub Actions run 41866972654, job engine-compat.*

### A bad release rolls itself back

`demo-rollback` releases version `0.2.0-waitlist` directly, with no ticket
and no PR. It is the same image as stable, with the `waitlist` feature
flag targeted on for that version. That feature answers 501, so the canary
fails.

<!-- source: GitHub Actions run 41866972654 (commit ee2f679), job engine-compat (126703546061), step "./go demo"; left out: cosign's warning line and its JSON, and the "Container …" lines of compose -->
```
[demo-rollback] stable is 0.1.0-m2; releasing 0.2.0-waitlist (waitlist targeted on)
Verification for host.containers.internal:5050/lights-out-backend@sha256:036e2fd8664f69cd85594fb920adbe6e5bf2fc0a622047efd561e5a5c94c12b1 --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - Existence of the claims in the transparency log was verified offline
  - The signatures were verified against the specified public key
[launchpad] staging: deploying 0.2.0-waitlist at lights-out-backend@sha256:036e2fd8664f69cd85594fb920adbe6e5bf2fc0a622047efd561e5a5c94c12b1 (stable is 0.1.0-m2)
slo: traffic canary(0.2.0-waitlist)=0.151 stable(0.1.0-m2)=4.236
slo: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=no data
slo: latency_p95 canary(0.2.0-waitlist)=0.024 stable(0.1.0-m2)=0.024
NO-GO: launchpad — 5%: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000 delta=1.000 max=0.010 → rolled back
make[2]: *** [Makefile:488: release] Error 1
GO: demo-rollback
```
*GitHub Actions run 41866972654, job engine-compat. Left out: cosign's
warning line and JSON, and compose's container lines.*

Read it from the top:

- **The signature is checked before any traffic.** The launchpad verifies
  the image's cosign signature against the plane's local key, then deploys
  the verified digest, not a tag.
- **Staging, then 5%.** At 5% verify compares the canary with stable on
  three numbers from `verify/slo.promql`: traffic, error rate and p95
  latency. Stable's error rate reads `no data` because stable served no
  errors, and verify counts that as 0.
- **NO-GO, then rollback.** An error-rate delta of 1.000 against a maximum
  of 0.010 is a NO-GO, and the launchpad puts all traffic back on stable
  on its own. `make` reports the `release` target's exit 1. That is the
  NO-GO, and `demo-rollback` expects it, so its own line is `GO`.

### A ticket goes all the way: `e2e`

`e2e` runs the same thing through the tower, the control plane: ticket →
PR → the six gates → merge → a signed build of the merge → canary 5% →
verify NO-GO → rollback, then the audit.

<!-- source: GitHub Actions run 41866972654 (commit ee2f679), job engine-compat (126703546061), step "./go demo"; left out: git's push hints, the gates' tool output, cosign's warning and JSON, compose's container lines -->
```
[e2e] replay: deleting the document of ticket 0001 before opening it again
[tower] 0001: opened, assign requested
[tower] 0001: assign (state opened)
[crew] ticket 0001: role dev-worker, harness replay, attempt 1
Applying: Handle unknown geocoder venue with 201 and null coordinates
[crew] ticket 0001: PR #1 http://host.containers.internal:3000/lights-out/workload/pulls/1
GO: crew
[tower] 0001: assign → pr-opened
[tower] 0001: ci (state pr-opened)
risk: level=low decision=auto-merge signals=none
deps: scanning 2 lockfile(s) at 5804fca9b45c05e68da6364745c09adb57181328 and at the base ee2f679bc63159c97a6eb4fbaf17520822cdbbcc: app/backend/uv.lock app/frontend/package-lock.json
deps: 1 advisory finding(s) inherited from the base, not gating (docs/adr/0032):
  PyPI opentelemetry-api GHSA-xcq7-p3pf-p88h
score: 211 mutant(s) excluded from the population (skipped, no-test, or incompetent)
[ci] gates: GO: gates — risk low, auto-merge, in compose:backend-test
[tower] 0001: ci → ci-passed
[tower] 0001: merge (state ci-passed)
[merge] PR #1 merged as a4502bbc0bb2d3525e5709d19e1ec8adbd25c922 (head 5804fca9b45c05e68da6364745c09adb57181328)
[tower] 0001: merge → merged
[tower] 0001: release (state merged)
[launchpad] staging: deploying 0.2.0-waitlist at lights-out-backend@sha256:87d0a257a29afd15724adb370c50cbe013540d379ad9bf4cea7ebf16428cbb0f (stable is 0.1.0-m2)
slo: traffic canary(0.2.0-waitlist)=0.287 stable(0.1.0-m2)=4.091
slo: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=no data
slo: latency_p95 canary(0.2.0-waitlist)=0.024 stable(0.1.0-m2)=0.024
make[2]: *** [Makefile:488: release] Error 1
[tower] 0001: release → rolled-back
[tower] 0001: rolled-back is terminal, nothing requested
[inproc] queue empty after 4 event(s), 0 failed
```
*GitHub Actions run 41866972654, job engine-compat, the `e2e` stage.
Left out: git's push hints, the gates' tool output (gitleaks, pytest,
cosmic-ray, image builds), cosign's warning and JSON, compose's container
lines.*

Stage by stage:

- **Ticket.** `tickets/0001.md` is a real bug: an unknown venue made
  `POST /api/meetups` answer 500. The tower opens a document for it in the
  state store (the Firestore emulator) and requests `assign`.
- **PR.** The dev-worker role turns the ticket into a patch. At L0 nothing
  calls a model: the `replay` harness applies the answer recorded once
  against the Gemini API (`fixtures/0001/dev-worker/`). The patch must
  stay inside the ticket's `## Perimeter`, checked before any PR exists.
  The PR opens on the plane's own Gitea, never on this repository.
- **The six gates.** risk, secrets, deps, SAST, test, mutation, in that
  order, on the PR's range, with the base's contract and policy (a PR
  cannot loosen what judges it). Here: risk `low` with no signal, so
  `auto-merge`; gitleaks found no leaks; one advisory already on the base,
  which does not gate (ADR 0032); the tests pass; the mutation score on
  the changed lines holds. `in compose:backend-test` says where the test
  tools ran.
- **Merge.** On GO and risk `low`, the tower merges the PR at the head the
  gates judged.
- **Signed image.** The merge commit is built, pushed to the local Zot
  registry and signed. The launchpad verifies the signature before staging
  (the same cosign lines as above, left out here).
- **Canary 5%, verify NO-GO, rollback.** The release is the failing
  version, so verify stops it at 5% and the canary rolls back. The ticket
  ends at `rolled-back`.

The audit closes `e2e` (it is shown below, under `./go audit`). The
demo's last two lines:

<!-- source: GitHub Actions run 41866972654 (commit ee2f679), job engine-compat (126703546061), step "./go demo" -->
```
lights-out: open the app at http://localhost:8080, Gitea at http://localhost:3000, Prometheus at http://localhost:9090
GO: demo, milestone M9, 716s to rollback (budget 900s, plan §2)
```
*GitHub Actions run 41866972654, job engine-compat.*

The 900 s budget is the golden rule: a clone reaches an automatic rollback
in under 15 minutes, with no account and no key.

### The gates saying no

The demo shows the gates saying GO. `./go demo-gates` judges six committed
fixture patches, and shows the test, mutation, SAST and deps gates saying
NO-GO, and risk sending a change to review:

<!-- source: GitHub Actions run 41866972654 (commit ee2f679), job gates (126703546044), step "./go demo-gates"; only the [demo-gates] lines and the last line -->
```
[demo-gates] failing-test: NO-GO: gates — test: NO-GO: test — in compose:backend-test: the test command failed (exit 1), see stderr
[demo-gates] fake-test: NO-GO: gates — mutation: NO-GO: mutation — in compose:backend-test: 4/8 mutants on changed lines killed (0.500 < 0.666); survivors on stderr
[demo-gates] honest-fix: GO: gates — risk low, auto-merge, in compose:backend-test
[demo-gates] migration: GO: gates — risk high, review, in compose:backend-test
[demo-gates] sast-finding: NO-GO: gates — sast: NO-GO: sast — in compose:backend-test: 1 SAST finding(s) in the workload's scope
[demo-gates] vulnerable-dep: NO-GO: gates — deps: NO-GO: deps — this diff introduces 4 advisory finding(s); list on stderr
GO: demo-gates
```
*GitHub Actions run 41866972654, job gates: the `[demo-gates]` lines and
the last line.*

`fake-test` is the same fix as `honest-fix` with a test that does not
really test it. The tests pass, so the test gate says GO. Mutation testing
catches it: it changes the fixed lines and checks whether a test fails.
`migration` passes every gate but is risk `high`, so it goes to review
instead of merging on its own.

### `./go board`

```sh
./go board
```

The board is one page on `http://127.0.0.1:8099` (`BOARD_PORT` moves it).
It has two parts (ADR 0035). EXPLAINER has eight scripted walks (ship it,
bad canary, fake test, risky diff, freeze then resume, human says no, out
of bounds, kill switch). They are labelled as scripted, and their versions
and numbers are examples. LIVE appears while the plane is up: the tower's
documents, the release-freeze and kill-switch flags, the traffic split and
the release record. It refreshes every 2 seconds and only reads. It never
deploys, shifts or rolls back.

The board is a page, not a command with an output, so no output is shown
here. `./go ci` checks it (`ci/board.sh`): the page's state table must
equal the tower's.

### `./go audit`: the chain, rebuilt

```sh
./go audit TICKET=0001
```

The audit rebuilds the chain from the release down to the spec, and
cross-checks the state store against the code host. A record that says
merged while the PR is still open is a NO-GO. `e2e` runs it as its last
stage:

<!-- source: GitHub Actions run 41866972654 (commit ee2f679), job engine-compat (126703546061), step "./go demo", the audit inside e2e -->
```
deploy   0.2.0-waitlist rolled-back — NO-GO: launchpad — 5%: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000 delta=1.000 max=0.010 → rolled back
         slo: traffic canary(0.2.0-waitlist)=0.287 stable(0.1.0-m2)=4.091
         slo: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=no data
         slo: latency_p95 canary(0.2.0-waitlist)=0.024 stable(0.1.0-m2)=0.024
         image: lights-out-backend@sha256:87d0a257a29afd15724adb370c50cbe013540d379ad9bf4cea7ebf16428cbb0f
  ← merge  a4502bbc0bb2d3525e5709d19e1ec8adbd25c922 (code host agrees)
  ← PR     #1 http://host.containers.internal:3000/lights-out/workload/pulls/1 (gates GO, risk low, auto-merge; head 5804fca9b45c05e68da6364745c09adb57181328)
  ← ticket 0001 (dev-worker, harness replay, model gemini-3.8-flash)
  ← spec   sha256:83d4cbb27987e3d18f8d273787b64534b3e387fc4c5726a3d29980c40dc82742 "0001 — Unknown venue makes `POST /api/meetups` answer 500 instead of the documented 502"
GO: audit
GO: e2e
```
*GitHub Actions run 41866972654, job engine-compat.*

Read it from the top down: what ran in production, which merge it was
built from (and that the code host agrees), which PR and which gate
verdict let it merge, which ticket and which agent wrote it, and the
spec: the sha256 of the ticket file as the agent read it. `harness
replay, model gemini-3.8-flash` says the PR was replayed, and which model
wrote the recording. The image digest is the one the launchpad verified.

## 2. The short looks

Each of these is a separate command, not a stage of `./go demo`.

### `./go demo-rework`: a fake test, caught, and fixed

```sh
./go demo-rework
```

Before a merge, a NO-GO is not the end (ADR 0038). The ticket goes back to
the dev-worker with the gates' verdict: the NO-GO line and the gate's own
details, such as the surviving mutants. The new head is judged by the same
gates. After four attempts (`policy/rework.env`) the ticket stops at
`needs-human`.

`demo-rework` runs this on ticket 0013, which is ticket 0001's bug again.
It needs the plane, and runs the whole tower. Attempt 1 is the
`fake-test` patch above, so the mutation gate rejects it with the line and
the survivors you saw in `demo-gates`:

<!-- source: GitHub Actions run 41866972654 (commit ee2f679), job gates (126703546044), step "./go demo-gates", the fake-test fixture: the same patch as demo-rework's attempt 1 -->
```
SURVIVOR meetups/geocoder_client.py:26 core/ReplaceComparisonOperator_Eq_Gt
SURVIVOR meetups/geocoder_client.py:26 core/ReplaceComparisonOperator_Eq_GtE
SURVIVOR meetups/geocoder_client.py:26 core/NumberReplacer
SURVIVOR meetups/geocoder_client.py:26 core/NumberReplacer
score: 211 mutant(s) excluded from the population (skipped, no-test, or incompetent)
[demo-gates] fake-test: NO-GO: gates — mutation: NO-GO: mutation — in compose:backend-test: 4/8 mutants on changed lines killed (0.500 < 0.666); survivors on stderr
```
*GitHub Actions run 41866972654, job gates, the `fake-test` fixture. This
is `demo-gates`' output for the patch that is `demo-rework`'s attempt 1,
not `demo-rework`'s own output.*

The worker's input for attempt 2 is the ticket, the workload's brief,
then that verdict.
Attempt 2 adds the geocoder contract's 404 example for an unknown venue,
and the combined change is the `honest-fix` fixture's: GO. The tower
merges it, and the canary rolls back as in `e2e`. The audit shows the
rework.

Both attempts are written by hand: no rework has been recorded against a
model yet. The fixtures say so:

<!-- source: the committed file fixtures/0013/dev-worker/run.json, printed with cat -->
```
$ cat fixtures/0013/dev-worker/run.json
{
  "hand_written": true,
  "model": null,
  "attempt": 1,
  "note": "Written by hand to prove the rework loop at L0 (docs/adr/0038 §10): the committed fake-test change, which the mutation gate rejects. No model produced this patch."
}
```

The gates that reject attempt 1 and pass attempt 2, the tower, the loop
and the cap are real. No GitHub Actions job runs `demo-rework`, so its
own output is not shown here. PLAN.md's M15 status note records
`GO: demo-rework` in 404 s on a cold plane, on 2026-11-03, outside
Actions.

### `./go demo-triage`: an alert becomes hypotheses

```sh
./go demo-triage
```

No plane, about 3 seconds (README). The ops-triage role reads three
alerts and, for each, files an incident with ranked hypotheses and
proposes rollback or hold. The demo checks each proposal against the one
the evalset expects. Two of the alerts are traps: in one stable fails too,
in the other the canary got no traffic. Rolling back is the wrong answer
to both.

At L0 the role replays answers recorded at L1 on 2026-11-04 with
`gemini-3.8-flash`. What the evalset expects, and what the recordings
answer:

<!-- source: the committed evalset adapters/adk/agents/ops_triage/evals/alerts.evalset.json, read with jq -->
```
$ jq -r '.eval_cases[] | .eval_id + ": " + .conversation[0].intermediate_data.tool_uses[-1].name' adapters/adk/agents/ops_triage/evals/alerts.evalset.json
canary-5xx: propose_rollback
misleading-stable-fails-too: propose_hold
misleading-no-canary-traffic: propose_hold
```

<!-- source: the committed recordings fixtures/adk/ops-triage/*.json, read with jq -->
```
$ for f in fixtures/adk/ops-triage/*.json; do jq -r '(.input | fromjson | .kind // "alert") + ": " + ([.. | .function_call? // empty | .name] | join(", "))' "$f"; done
alert: file_incident, propose_hold
alert: file_incident, propose_rollback
incident: file_postmortem
alert: file_incident, propose_hold
```

The fourth recording, `incident`, is the post mortem below. No GitHub
Actions job runs `demo-triage`, so its own output is not shown here. Its
last line is `GO: demo-triage`. The incidents it writes are in
`.crew/triage/<alert>/incident.json`.

### `./go demo-postmortem`: an incident becomes a post mortem and a ticket

```sh
./go demo-postmortem
```

No plane, no key. The input is `fixtures/incidents/demo-rollback.json`, an
incident document built by `./go incident` from a real `demo-rollback`
run (`fixtures/incidents/README.md` gives the date, commit and commands).
The ops-triage role answers with one `file_postmortem` call. Core then
checks that every timeline entry is anchored to an id the document holds:
the release, a stage, a log line, an alert. It prints that evidence beside
each entry, and files each action item as a ticket. The demo files them
into a copy of `tickets/` under `.crew/demo-postmortem/`, runs a second
time, and checks that nothing new is filed.

The recording it replays, read straight from the fixture:

<!-- source: the committed recording fixtures/adk/ops-triage/e3b939ad61f9fccf16e91a5b11657951829ef9bdd2383424cbbe1ae1f2958c9f.json (recorded 2026-11-04T10:59:27Z, gemini-3.8-flash), read with jq -->
```
$ jq -r '.. | .function_call? // empty | select(.name == "file_postmortem") | .args.timeline[] | .anchor + "  " + .event' fixtures/adk/ops-triage/*.json
log:1  Stable confirmed at 0.1.0-m2 and release 0.2.0-waitlist initiated.
release:0.2.0-waitlist  Release 0.2.0-waitlist deployed to staging using image lights-out-backend@sha256:ab76e8057597500f4c290834014aba7e5031bea11938076cd516f8bef16eaacc.
release:0.2.0-waitlist@5  Canary reached 5% traffic and breached error rate SLO with verdict NO-GO.
alert:1  Alert fired for SLO breach on error_rate canary(0.2.0-waitlist)=1.000 exceeding delta max 0.010.
$ jq -r '.. | .function_call? // empty | select(.name == "file_postmortem") | .args.actions[].title' fixtures/adk/ops-triage/*.json
Fix waitlist service endpoint failures on canary
```

The model writes no times: the release record has no clock, and a time it
invented could not be checked. A filed ticket has no `## Perimeter`,
because the role saw the incident, not the code. A human adds one before
`./go assign`, and until then the perimeter check refuses the ticket. An
anchored timeline is not a true one: the check stops invented releases and
log lines, not a wrong story about real ones.

No GitHub Actions job runs `demo-postmortem`, so its own output is not
shown here. Its last line is `GO: demo-postmortem`, with the fix ticket's
path on stderr (README: recorded once at L1 on 2026-11-04).

### `./go demo-launch`: go-for-launch, the one human gate

Agents and gates decide everything up to 25% of traffic. The step to 100%
waits for one person. `demo-launch` needs the plane up:

```sh
./go up
./go demo-launch
```

<!-- source: GitHub Actions run 41866972654 (commit ee2f679), job launch (126703545476), step "./go demo-launch"; left out: cosign's warning and JSON, compose's container lines -->
```
lights-out: waitlist is off for every version (app/flags/flags.json edited; git checkout it to undo)
GO: kill-switch
[demo-launch] stable is 0.1.0-m2; releasing 0.2.0-waitlist with waitlist off
[launchpad] staging: deploying 0.2.0-waitlist at lights-out-backend@sha256:3e5724e8c0fea28776f7d200d09f7f3f4fb411e056588ac2c7112331a2091784 (stable is 0.1.0-m2)
slo: traffic canary(0.2.0-waitlist)=0.182 stable(0.1.0-m2)=4.236
slo: error_rate canary(0.2.0-waitlist)=no data stable(0.1.0-m2)=no data
slo: latency_p95 canary(0.2.0-waitlist)=0.024 stable(0.1.0-m2)=0.024
[launchpad] 5%: GO
slo: traffic canary(0.2.0-waitlist)=1.091 stable(0.1.0-m2)=3.327
slo: error_rate canary(0.2.0-waitlist)=no data stable(0.1.0-m2)=no data
slo: latency_p95 canary(0.2.0-waitlist)=0.024 stable(0.1.0-m2)=0.024
[launchpad] 25%: GO
[launchpad] 25%: GO — held; ./go promote runs go-for-launch (record at .crew/release.json)
GO: launchpad
[go-for-launch] promotion brief for 0.2.0-waitlist (by core/promote.sh from the record — no model at L0, the release role writes it from L1):

# Promotion brief: 0.2.0-waitlist

Promote `0.2.0-waitlist` (`lights-out-backend@sha256:3e5724e8c0fea28776f7d200d09f7f3f4fb411e056588ac2c7112331a2091784`), replacing stable `0.1.0-m2`.

## Stages
- 5%: GO: slo
  - slo: traffic canary(0.2.0-waitlist)=0.182 stable(0.1.0-m2)=4.236
  - slo: error_rate canary(0.2.0-waitlist)=no data stable(0.1.0-m2)=no data
  - slo: latency_p95 canary(0.2.0-waitlist)=0.024 stable(0.1.0-m2)=0.024
- 25%: GO: slo
  - slo: traffic canary(0.2.0-waitlist)=1.091 stable(0.1.0-m2)=3.327
  - slo: error_rate canary(0.2.0-waitlist)=no data stable(0.1.0-m2)=no data
  - slo: latency_p95 canary(0.2.0-waitlist)=0.024 stable(0.1.0-m2)=0.024

## Not verified
- 100% of traffic: not observed yet; that is what this decision starts.

Recommendation: GO — every stage passed verify; the numbers above are the evidence.

[go-for-launch] 0.2.0-waitlist at 100% of traffic (envoy-canary)
GO: go-for-launch
[demo-launch] 0.2.0-waitlist at 100%: 10/10 healthz samples; now the un-promote
GO: demo-launch
```
*GitHub Actions run 41866972654, job launch. Left out: cosign's warning
and JSON, compose's container lines.*

What happened:

- **The kill switch** turned the failing feature off for every version,
  live, with no deploy. So the same release now passes verify at 5% and
  25%. The kill switch edits `app/flags/flags.json`; run
  `git checkout app/flags/flags.json` to undo it.
- **Held at 25%.** The launchpad never goes to 100% on its own. It stops
  and writes the release record.
- **The brief.** At L0 it is rendered from the release record by
  `core/promote.sh`, and the line above it says so. From L1 the release
  role writes it. It ends with what is not verified yet: 100% of traffic.
- **The human answer.** The demo answers `GO` for you
  (`GO_FOR_LAUNCH=GO`). By hand, the path is `./go kill-switch`, then
  `./go release`, then `./go promote`, which asks in the terminal, or
  `./go promote GO_FOR_LAUNCH=GO`. A `NO-GO` rolls back.
- **The un-promote.** The demo checks 100% with ten health samples, then
  rolls back, so the plane is clean again.

## 3. Your repository, without the plane

The gates half of lights-out needs no plane, no key and, with the
workbench as the toolchain, no engine socket.

### `./go init`, then `./go gates`

```sh
./go init ~/code/your-repo
./go gates
```

`./go init` clones your repository's HEAD into `.attached/` and drafts
`.lights-out/` there. It never writes to your repository. It infers the
stack (python with `pyproject.toml` and `uv.lock`, or javascript with
`package.json` and `package-lock.json`) and measures your mutation
baseline by running the mutation tool over the whole scope. `./go gates`
then judges the last commit of the clone, with the draft as its contract.

This is what the two commands printed on `workloads/minimal-js`, copied
into a repository of its own (`./go demo-init` does exactly that):

<!-- source: GitHub Actions run 41866972654 (commit ee2f679), job init (126703545986), step "./go demo-init", the minimal-js part; left out: npm and Stryker output -->
```
init: stack javascript: source src/, tests test, toolchain workbench
init: the repository has a committed .lights-out/; its workload.env, worker.md, policy.env and runners/ are replaced by this draft in the clone only
mutation-baseline: npm ci && sh .lights-out/runners/mutation.sh src "npm test" over src/, in workbench
score: 0 mutant(s) excluded from the population (RuntimeError, CompileError, Ignored, Pending)
mutation-baseline: 30/32 killed, score=0.9375, 13s wall time, in workbench
[demo-init] minimal-js: GO: init — javascript, draft in .attached/.lights-out, baseline 0.9375 (30/32 mutants killed, 13s, in workbench); copy .lights-out/ into your repository and commit it
[gates] no BASE/HEAD given: judging the last commit, 4b825dc..3737af6
risk: level=high decision=review signals=platform(.lights-out/policy.env .lights-out/runners/eslint.security.mjs .lights-out/runners/mutation.sh .lights-out/runners/package-lock.json .lights-out/runners/package.json .lights-out/runners/sast.sh .lights-out/runners/score.mjs .lights-out/worker.md .lights-out/workload.env)
deps: scanning 1 lockfile(s) at 3737af6f0bd579bf357d5caabd567c0ce8544396 and at the base 4b825dc642cb6eb9a060e54bf8d69288fbee4904: .attached/package-lock.json
deps: .attached/package-lock.json is new at HEAD, judged whole
deps: the lockfile(s) list no package; nothing to scan
score: 0 mutant(s) excluded from the population (RuntimeError, CompileError, Ignored, Pending)
[demo-init] minimal-js, draft, no engine: GO: gates — risk high, review, in workbench (23s for init and gates)
```
*GitHub Actions run 41866972654, job init. Left out: npm and Stryker
output. Run by hand, the two GO lines come without the `[demo-init]`
prefix.*

Two things to notice:

- **The first commit is judged whole.** The repository has one commit, so
  "the last commit" is the whole tree, from the empty tree `4b825dc`. Its
  lockfile is new and judged whole. An advisory already in your lockfile
  is a NO-GO on your first `./go gates`.
- **`risk high, review`.** The example's one commit already contains its
  own `.lights-out/`, and any change to `.lights-out/` is high risk: it
  never merges on its own. On your repository, the commit that adds
  `.lights-out/` is judged the same way. Your other commits are judged on
  their own paths and size.

`demo-init` proves init and gates in under 300 s on two small examples
only: 44 s and 23 s in this run. Init measures the whole scope, so a large
suite takes longer.

### Read the draft

`.attached/.lights-out/` holds `workload.env`, `worker.md` (the
dev-worker's brief: the paths it may change, and the exact test command),
`policy.env` (your thresholds; a draft overrides none) and `runners/` (the
stack's mutation and SAST runners, pinned by their own lockfile).

```sh
cat .attached/.lights-out/workload.env
```

`workload.env` has eleven keys, and every value sits under a comment that
says where it came from:

- `# Provenance, inferred: <file>: <evidence>`: read from a file of your
  repository, such as `TOOLCHAIN_IMAGE` from `requires-python` or
  `engines.node`.
- `# Provenance, default: ...`: a platform default, such as the runners or
  an empty plane key.
- `# Provenance, measurement: ...`: `MUTATION_BASELINE`, with the date, the
  commit, the command, the mutant and kill counts and the wall time.
- `# Provenance, kept: ...`: a plane key kept from a contract you already
  committed.

No GitHub Actions job prints a draft, so no draft is shown here. [The
guide](use-on-your-repo.md#the-eleven-keys) explains each key and what
init infers it from. Fix what is wrong (the scope, the test command, the
toolchain), then copy the draft into your repository and commit it:

```sh
cp -R .attached/.lights-out/. ~/code/your-repo/.lights-out/
git -C ~/code/your-repo add .lights-out
git -C ~/code/your-repo commit -m "add lights-out contract"
./go attach ~/code/your-repo
./go gates
```

Use `attach`, not `init`, after the commit: `init` would draft again over
the contract you just committed. Keep the `/.` in the `cp` command.
Without it, `cp -R` into an existing `.lights-out/` nests the draft one
level deeper. With a workbench toolchain your tests run in lights-out's
toolchain container on this machine: attach only a repository you would
run here.

### The packaged wrapper, without cloning lights-out

The same gates run from one script, `lights-out`, and an image.

**The image is not published yet.**
`ghcr.io/nicolaguglielmi/lights-out:0.1.0` does not exist on any
registry. CI builds and tests it on every push. Publishing it is the
owner's act. Until then, build it from a clone:

```sh
./go package
cp lights-out ~/.local/bin/
export LIGHTS_OUT_IMAGE=localhost/lights-out:dev
```

Then, in your repository:

```sh
cd ~/code/your-repo
lights-out doctor
lights-out init
cp -R ~/.local/state/lights-out/your-repo/.lights-out/. .lights-out/
git add .lights-out && git commit -m "add lights-out contract"
lights-out gates
```

`./go demo-package` runs this path in CI on `workloads/minimal` as a
repository of its own:

<!-- source: GitHub Actions run 41866972365 (workflow package, commit ee2f679), job package (126703545895), step "./go demo-package"; only the [demo-package] and [lights-out] lines and the last line -->
```
[demo-package] /tmp/tmp.2Vm5UcVPbG/minimal: workloads/minimal as a repository of its own, image localhost/lights-out:dev
[lights-out] no contract at the base: the head's own .lights-out/ judges it
[demo-package] committed contract, no socket: NO-GO: gates — TOOLCHAIN_IMAGE=compose:backend-test needs the engine socket, which the lights-out image never gets (docs/adr/0045 §3); judge it from a clone with ./go gates, or set TOOLCHAIN_IMAGE=workbench
[demo-package] GO: init — python, draft in /tmp/tmp.2Vm5UcVPbG/out/.lights-out, baseline 1.0 (8/8 mutants killed, 25s, in workbench); copy .lights-out/ into your repository and commit it
[lights-out] the contract that judges is the base's, e7035fa
[demo-package] GO: gates — risk low, auto-merge, in workbench (50s for init and gates)
[lights-out] judging the staged changes as one commit on 65c4eb7
[lights-out] the contract that judges is the base's, 65c4eb7
[demo-package] staged, breaking a test: NO-GO: gates — test: NO-GO: test — in workbench: the test command failed (exit 1), see stderr
GO: demo-package — init and gates 50s in workbench (budget 300s), a staged break NO-GO at test, image localhost/lights-out:dev
```
*GitHub Actions run 41866972365 (workflow `package`), job package: the
`[demo-package]` and `[lights-out]` lines and the last line.*

Read it in order:

- **The wrapper never gets your engine's socket.** So it runs only
  `TOOLCHAIN_IMAGE=workbench`. `workloads/minimal` commits
  `compose:backend-test`, and the line says so and names the fix. Judge
  the `compose:` and image forms from a clone, with `./go gates`.
- **`init` writes outside your repository**, to
  `~/.local/state/lights-out/<repo>/.lights-out` (`LIGHTS_OUT_OUT` moves
  it). Your repository is mounted read-only.
- **The base's contract judges.** A range is judged by `workload.env`,
  `policy.env` and `runners/` as they are at its base, so a change cannot
  loosen what judges it.
- **`STAGED=1`** judges what is staged as one commit: the shape the hook
  recipes for coding agents use ([the guide](use-on-your-repo.md#hook-recipes-for-coding-agents)).

### The GitHub Action

`action/action.yml` runs the wrapper on a pull request and posts one check
run, `lights-out gates`, whose title is the GO or NO-GO line:

```yaml
permissions:
  contents: read
  checks: write
steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0
  - uses: nicolaguglielmi/lights-out/action@v0.1.0
```

**`@v0.1.0` does not work yet**: it needs the published image and the
tag. The Action is proven in lights-out's own workflow only, with
`uses: ./action` on a scratch repository, once with a good change and
once with a broken test:

<!-- source: GitHub Actions run 41866972365 (workflow package, commit ee2f679), job action (126703546538); the verdict and check-run lines of the two cases -->
```
GO: gates — risk low, auto-merge, in workbench
lights-out gates (Action test: a good change, GO expected): check run posted on ee2f679bc63159c97a6eb4fbaf17520822cdbbcc, success
NO-GO: gates — test: NO-GO: test — in workbench: the test command failed (exit 1), see stderr
lights-out gates (Action test: a broken test, NO-GO expected): check run posted on ee2f679bc63159c97a6eb4fbaf17520822cdbbcc, failure
```
*GitHub Actions run 41866972365 (workflow `package`), job action: the
verdict and check-run lines of the two cases.*

Linux runners only. A fork PR's token cannot write checks: the post is
skipped with a warning, and the job status still carries the verdict. Tags
are mutable and the image is unsigned, so pin the image by digest with the
`image` input.

## 4. A ticket, assigned to an agent at L1

At L0 the agents replay recordings of lights-out's own tickets. Your
repository has none, so on an attached repository the crew stops at L0
and says so: `has no recordings to replay at L0; run the crew at L1`.
From here on you need a model key, and nothing in this section has real
output to show.

### What you need

- **The plane half of `.lights-out/`.** `./go assign` pushes to the
  plane's Gitea, so the plane must be up, and `./go up` refuses a
  contract without `compose.yaml`. `./go init` does not draft the plane
  half; you write it ([the guide, section 2](use-on-your-repo.md#2-the-plane-half)).
  The shortest way to try this step is a throwaway repository made from
  `workloads/minimal`, which has the plane half and one ticket.
- **One key, in `.env`** (copy `.env.example`):

| Harness | Provider | Key in `.env` | Command line |
|---|---|---|---|
| `gemini-cli` (the default) | `gemini` | `GEMINI_API_KEY` | `PROFILE=l1` |
| `claude-code` | `anthropic` | `ANTHROPIC_API_KEY` | `PROFILE=l1 AGENT_HARNESS=claude-code MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5` |
| `codex` | `openai` | `OPENAI_API_KEY` | `PROFILE=l1 AGENT_HARNESS=codex MODEL_PROVIDER=openai MODEL=gpt-6.1-sol` |

Each harness has one provider. `run.sh` refuses a mismatch and names the
harness that fits. The model ids are the ones the README and `.env.example`
name.

### Write the ticket

One file per ticket in `.lights-out/tickets/<id>.md`. `workloads/minimal`
carries this one:

<!-- source: the committed file workloads/minimal/.lights-out/tickets/0001.md, printed with cat -->
```
$ cat workloads/minimal/.lights-out/tickets/0001.md
# 0001 — `GET /version` answers the running version

- Status: open
- Labels: feature, small, the attached e2e's ticket (docs/adr/0043)
- Found: 2026-11-04, writing M21: a repository made from `workloads/minimal`
  needs one ticket of its own before `./go e2e` can run on it at L1

## Problem

Release tooling and humans read the version from `/healthz`, which also
answers a status. A route that answers the version alone is what a smoke
test or a dashboard wants to read.

## Acceptance criteria

Given the service is running with `APP_VERSION` set
When a client sends `GET /version`
Then the response is `200` with the JSON body `{"version": "<APP_VERSION>"}`.

Given the test suite (`uv run pytest tests -q`)
When it runs
Then a test asserts the status and the exact body of `GET /version`, and
every existing test still passes.

## Perimeter

- `minimal/app.py`
- `tests/test_app.py`
```

- **The first line** is `# <id> — <title>`. The tower records it as the
  spec's title, and the audit prints the hash of the whole text.
- **Acceptance criteria** as Given/When/Then. Name the test that must
  exist and what it asserts: the mutation gate rejects a test that does
  not really check the change.
- **`## Perimeter`**: one path or glob per list item, where `*` also
  crosses `/`. A change to any path outside it is refused before a PR
  exists. A ticket with no `## Perimeter` is refused too. `tickets/0005.md`
  in this repository is a longer example.

### Assign it

```sh
./go attach ~/code/your-clone
./go up
./go assign TICKET=0001 PROFILE=l1
```

The dev-worker reads the ticket, then your `worker.md`. It works in your
`TOOLCHAIN_IMAGE` when that names an image, and in the workbench otherwise.
`assign` opens the PR on the plane's Gitea. To run the whole tower on it
(the gates, the merge, the build, the canary, the audit), use `./go e2e
PROFILE=l1` instead. Merges land on the plane's Gitea, not in your
repository. Fetch them back before the next `assign`, `up` or `down`:
Gitea has no volume.

```sh
git -C ~/code/your-clone fetch http://localhost:3000/lights-out/workload.git main
git -C ~/code/your-clone merge FETCH_HEAD
```

With `CODE_HOST=github` on the command line and `GITHUB_REPO` and
`GITHUB_TOKEN` in `.env`, the PR lands on your GitHub repository instead
([the guide](use-on-your-repo.md#your-pr-on-github-l1)).

### What it costs

- **Gemini, free tier.** Free within its cap: about 250 requests a day,
  Flash models only (reference, Levels). A headless turn is one request,
  and the dev-worker stops at 60 turns (`roles/dev-worker/role.env`), so a
  day holds about four attempts.
- **Tokens.** The dev-worker may spend up to 2.6M tokens per run
  (`TOKEN_BUDGET`). The recorded run of ticket 0001 spent 2,435,115 tokens
  in 328 s (`fixtures/0001/dev-worker/run.json`).
- **Claude and OpenAI** cost money per run. No run has been made with
  either, so lights-out cannot tell you the price yet. The README will
  state the cost per provider once those recordings exist.

### What is not proven yet

- **No run at L1 on a repository other than lights-out's own app.** The
  release of an attached repository's merge is implemented and has not
  run on a repository of yours. So there is no output in this section.
- **Claude Code and Codex** have never run against their real APIs. `./go
  harness-conformance` proves each harness's plumbing (guard, budgets,
  artefacts, served model) against a scripted model, not a model's
  ability: `GO: harness-conformance — claude-code codex gemini-cli,
  against a scripted model, 273 s` <!-- source: GitHub Actions run 41866972654, job harness-conformance (126703545920) --> in
  run 41866972654.
- **The budgets are Gemini measurements.** `MAX_TURNS` and `TOKEN_BUDGET`
  bind every harness until recordings re-measure them. A first Claude or
  OpenAI run may hit a budget for tokenizer reasons alone.
- **The network stays open** in the worker's container, because each
  harness must reach its provider. The guard denies the network tools, but
  an interpreter could still send out what the container holds, the
  provider key included.
- **The GitHub code host** is proven verb by verb, not end to end.
- **A codebase not written for lights-out** has not been tried. That is
  the next milestone, M24.

## 5. Ops

Three commands for after a release, two of them without the plane.

### `./go incident`: the document

```sh
./go incident NAME=<slug> FROM=<utc> TO=<utc> [LOGS=<file>] [TICKET=<id>]
```

It builds one JSON file, `.crew/incidents/<name>.json`, from the last
release record (`.crew/release.json`), the time window (format
`2026-11-04T10:32:07Z`), an optional log excerpt copied verbatim, and with
`TICKET` the PR and merge from the tower's document. `TICKET` is the only
option that needs the plane. After a full `./go demo` the record on disk
is `e2e`'s release, not `demo-rollback`'s. Its stdout is
`GO: incident — <path>`.

No GitHub Actions job runs it. The document it built from a real
`demo-rollback` run is committed:

<!-- source: the committed file fixtures/incidents/demo-rollback.json (built by ./go incident on 2026-11-04, see fixtures/incidents/README.md), read with jq -->
```
$ jq '{name, window, verdict: .release.verdict, alerts: (.alerts | length), logs: (.logs | length), chain}' fixtures/incidents/demo-rollback.json
{
  "name": "demo-rollback",
  "window": {
    "from": "2026-11-04T10:32:07Z",
    "to": "2026-11-04T10:33:33Z"
  },
  "verdict": "rolled-back",
  "alerts": 1,
  "logs": 5,
  "chain": null
}
```

One alert per stage whose verdict was not GO. `chain` is `null` because
`demo-rollback` releases with no ticket and no PR.

### `./go postmortem`: the post mortem and its tickets

```sh
./go postmortem INCIDENT=.crew/incidents/<name>.json PROFILE=l1
```

At L0 the role replays only lights-out's own recordings, so on your
incident it needs L1 and a key. It writes `.crew/postmortem/<name>/`
(`postmortem.md`, `postmortem.json`, the run's artefacts) and files each
action item as a ticket in `tickets/`, with no `## Perimeter`. The checks
of `demo-postmortem` apply: every anchor must name something the document
holds, at least one timeline entry must be anchored to the release, and
there must be at least one cause and one action. Otherwise it is
`NO-GO: postmortem — <reason>` and no ticket is written. A second run on
the same incident files nothing new. The stdout line on GO is
`GO: postmortem — <k> action item(s): tickets <id> …`. No run on an
incident other than the committed one exists, so no output is shown.

### `./go verify` on your own metrics

```sh
./go verify METRICS_URL=<endpoint> CANARY_VERSION=<v> STABLE_VERSION=<s>
```

This runs the unchanged `verify/slo.promql` against any
Prometheus-compatible endpoint. That means one that answers
`/api/v1/query`, with the OTel HTTP semconv histogram joined to
`target_info{service_version}`. On other metrics the answer is NO-GO with
"no data". `METRICS_URL` is the base that `/api/v1/query` is appended to.
An auth header goes in `.env` as `METRICS_AUTH_HEADER` and is never
printed. Both versions must be set.

The plane's own judge goes through the same `promql` adapter (ADR 0044),
so the `slo:` lines and the `NO-GO: launchpad — 5%: error_rate …` verdict
in section 1 are this code's output on the plane's Prometheus. No GitHub
Actions job runs `./go verify` against another endpoint, so none is shown.

## Where next

- [The guide](use-on-your-repo.md): every key of `.lights-out/`, the plane
  half, `policy.env`, the hook recipes.
- [The reference](reference.md): every command and every level.
- [Architecture](ARCHITECTURE.md) and [the decisions](adr/).
- [All the docs](README.md).
