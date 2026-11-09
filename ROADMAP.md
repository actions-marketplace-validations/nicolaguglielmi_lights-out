# Roadmap

Derived from [docs/PLAN.md](docs/PLAN.md), the Italian working plan, which
wins when the two disagree. Decisions behind each step are in
[docs/adr/](docs/adr/).

## Done

| Milestone | What it delivered |
|---|---|
| M0–M2 | Skeleton, the bundled app, the local L0 plane |
| M3 | Canary delivery, verify, automatic rollback, kill switch |
| M4 | Six PR gates: risk, secrets, dependencies, SAST, tests, mutation (eight since M27) |
| M5 | The agent runtime: ticket → PR, recorded at L1, replayed at L0 |
| M6 | The control plane: the whole golden path, audited |
| M7 | ADK roles (product, ops-triage, release) and go-for-launch, the one human gate |
| M8, local part | Release images built, signed and verified before they take traffic |
| M9 | The review step for medium- and high-risk PRs; ticket perimeters |
| M12 | The Workload port: the platform operates on any workload, not only the bundled app |
| M13 | Attach: `./go attach <path>` points a plain clone at your repository; its `.lights-out/` holds the contract, the dev-worker's brief and your thresholds (ADR 0037) |
| M15 | The rework loop: a gates NO-GO or a review asking for changes goes back to the dev-worker with the verdict, up to four attempts, then a human (ADR 0038) |
| M18 | The model is a choice: `MODEL_PROVIDER` (gemini, anthropic, openai) and `MODEL` in the profile or `.env`, a role keeps only its thinking level and budgets, the ADK roles reach Claude and OpenAI through `LiteLlm`, `ci/model-free.sh` keeps model ids out of the core (ADR 0040). The non-Gemini recording is implemented, run once on Claude (2026-11-04, evals GO), not committed |
| M19 | The `claude-code` and `codex` harnesses beside `gemini-cli`, one provider each, and `./go harness-conformance` against a scripted model (ADR 0041). Recording with them is implemented; claude-code ran once live (2026-11-04), stopped by the mutation gate; codex not yet |
| M20 | Gates anywhere: `./go init <repo>` drafts `.lights-out/` from the repository itself, and `test`, `sast` and `mutation` run the commands the contract declares, in the workbench, a compose service or an image; init and gates in 40 s on `workloads/minimal`, 8 s on `workloads/minimal-js`, under the 300 s rule; JavaScript with Stryker as the second stack (ADR 0042, *proposed*) |
| M21 | GitHub as code host: `adapters/github/`, the eight CodeHost verbs on the REST API, the token never in argv or a `.git/config`; an attached repository's merge is built, signed and released; `./go codehost-conformance` against Gitea on every push and against GitHub in a nightly (ADR 0043). The end-to-end run on GitHub is the owner's, not yet run |
| M22 | Ops without the plane: `./go incident` and `./go postmortem`, a post mortem whose timeline is anchored to the audit chain and whose action items are tickets; the `Metrics` port reads any Prometheus-compatible endpoint (`METRICS_URL`); `./go demo-postmortem` replays a recorded answer, still six roles (ADR 0044, *proposed*) |
| M23 | One command, one package: the `lights-out` wrapper (`init`, `gates`, `triage`, `postmortem`, `doctor`) on any repository from one image, mounted read-only and never given the engine socket; `./go doctor`; a GitHub Action that posts the gates' line as a check run (ADR 0045, *proposed*). Built and tested in Actions, published as `v0.1.0` on 2026-11-05 |
| M27 | Tests that prove something: `test-weakening` refuses a diff that drops assertions or tests or adds skips, `test-proof` runs the tests a change adds on the base, where they must fail; the tower's `assign` waits while an open ticket holds a file of its perimeter, and on an attached repository until the base is green (ADR 0053, *proposed*) |
| M28 | The project map: `./go map` builds a SQLite file of one commit's tickets, files, tests, ADRs and pages, rebuilt at every merge, which files a docs ticket when a merge changes a path a page cites; `ci/docs-drift.sh` fails on a page citing a path, command or key that no longer exists; the map's slice in the worker's brief stays off (`MAP_BRIEF=off`) until M24 measures it (ADR 0054, *proposed*) |
| M29 | The dev phase visible: the console recovered (M11's five screens, ADR 0047), then `requested` → `questions` → `spec-ready` → `opened` in the tower, `./go request` and `./go answer`, the `spec` gate, one timeline per ticket from the request to the release, an overview and a kanban whose columns are the tower's states (ADR 0055, *proposed*) |
| M30 | Main stays green without a queue: no second judgment when nothing moved under a PR's perimeter, main judged again after merging in groups of at most four, a red group bisected and the culprit reverted through the code host, `assign`, `rework` and `release` stopped while main is red; `./go demo-mainline` (ADR 0056, *proposed*) |
| M31 | The stepped way in: a gates image (508 MB) beside the full one (1.25 GB, was 1.77), `action.yml` at the root with a `gates` input and a summary per gate in the check run, `test-proof` and `test-integrity` as standalone Actions, `./go doctor --level`, the `production-readiness` gate, the README along five steps with the reuse said as reuse (ADR 0057, *proposed*). Published as `v0.3.0` on 2026-11-09, both images signed; on the probe, first pull included, the three checks in 27 s, 14 s and 25 s. The Marketplace pages are the owner's (`docs/launch/checklist.md`) |
| M33 | The console as a workbench: the kanban gains a drawer, search, keys, a view in the link, collapsible columns and a highlight on a moved card, and still moves none; a light and dark theme; a specs screen and a request editor the spec gate checks as you type, saved through `./go request`; ADR search from the project map, schema 2, through logbook 1.2 (ADR 0059, *proposed*) |
| M34 | The lean plane: a `sqlite` StateStore and a `spool` EventBus, files under `.crew/`, the defaults at L0 and L1; the emulators opt-in (compose profile `emulators`); the Gitea runner, its `image` job and the Gitea compatibility check gone, the release step builds every workload's merge; five plane services instead of eight; the tower's documents outlive `./go down`. Measured on Actions, 719 to 873 s, so the demo budget stays 900 s (ADR 0060, *proposed*) |
| M35 | Gates without a container: `lights-out gates --light`, a standard-library Python package (the root `pyproject.toml`, `lights_out` is `core/`), runs the gates that need only git and Python, two by default, four with `TICKET=`, six with `TEST_ON_HOST=1`, in 0.14 s on this repository, and never prints `GO: gates`; the `--light` hook recipes verified once per CLI (ADR 0061, *proposed*). On PyPI once the owner publishes it |
| Agent network, built | The dev-worker step split between workers behind one harness port, governed like any PR (ADR 0036, still *proposed*; hand-written at L0) |

## Next

The third arc (plan §16) is built, except for the runs that are the
owner's: the OpenAI recording, a committed Claude recording and the L1
end-to-end on GitHub. Two things close before M24, each in
a session of its own: egress for the harnesses, and the tower restoring
`.lights-out/runners/` from the base.

- **The owner's release steps** (`docs/launch/checklist.md`): the package
  on PyPI and the three Marketplace pages. The tag `v0.3.0` is out since
  2026-11-09, both images signed.
- **M24 — the public legacy experiment.** Plan §14's experiment on a
  well-known open-source legacy repository, with every ticket run on the
  three providers and all three verdicts published, GO and NO-GO alike.
  The exit criterion is §14's: if at least two tickets in three do not
  reach a mergeable PR without a human touching the code, the thesis is
  weaker than expected.
- **M32 — outside adapters, other CIs, one more delivery** (ADR 0058). An
  adapter can live outside this repository once it passes its conformance
  suite; other CIs show the gates' verdict and never judge; Jenkins and
  GitLab proven locally; one more delivery adapter when someone needs it.

The adoption roadmap behind M31, M34 and M35, with what to drop, what to
change and the sequence after them (attestation, the jury, `./go
demo-loop`, the toolbelt, then the launch), is
[docs/plans/adoption-roadmap-2026-11.md](docs/plans/adoption-roadmap-2026-11.md).

## Later

- **M16 — the agent network**, reviewed and decided: who splits a
  ticket between workers, from the six roles there are.
- **M17 — the dashboard.** The board grows into the view of every
  ticket, attempt, worker and threshold you changed. The console (M29)
  already shows the tickets, their timelines and the thresholds.

## When someone needs it

- **M8 cloud track (L2)**: Google Cloud with Terraform and Cloud Deploy.
- **M10 (L3)**: Agent Engine and the nightly self-test.

Each cloud adapter costs money on every run and needs a nightly to stay
honest, so it is built when someone needs it.
