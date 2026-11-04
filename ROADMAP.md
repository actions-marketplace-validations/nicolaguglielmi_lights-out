# Roadmap

Derived from [docs/PLAN.md](docs/PLAN.md), the Italian working plan, which
wins when the two disagree. Decisions behind each step are in
[docs/adr/](docs/adr/).

## Done

| Milestone | What it delivered |
|---|---|
| M0–M2 | Skeleton, the bundled app, the local L0 plane |
| M3 | Canary delivery, verify, automatic rollback, kill switch |
| M4 | Six PR gates: risk, secrets, dependencies, SAST, tests, mutation |
| M5 | The agent runtime: ticket → PR, recorded at L1, replayed at L0 |
| M6 | The control plane: the whole golden path, audited |
| M7 | ADK roles (product, ops-triage, release) and go-for-launch, the one human gate |
| M8, local part | Release images built, signed and verified before they take traffic |
| M9 | The review step for medium- and high-risk PRs; ticket perimeters |
| M12 | The Workload port: the platform operates on any workload, not only the bundled app |
| M13 | Attach: `./go attach <path>` points a plain clone at your repository; its `.lights-out/` holds the contract, the dev-worker's brief and your thresholds (ADR 0037) |
| M15 | The rework loop: a gates NO-GO or a review asking for changes goes back to the dev-worker with the verdict, up to four attempts, then a human (ADR 0038) |
| M18 | The model is a choice: `MODEL_PROVIDER` (gemini, anthropic, openai) and `MODEL` in the profile or `.env`, a role keeps only its thinking level and budgets, the ADK roles reach Claude and OpenAI through `LiteLlm`, `ci/model-free.sh` keeps model ids out of the core (ADR 0040). The non-Gemini recording is implemented, not yet run |
| M19 | The `claude-code` and `codex` harnesses beside `gemini-cli`, one provider each, and `./go harness-conformance` against a scripted model (ADR 0041). Recording with them is implemented, not yet run |
| M20 | Gates anywhere: `./go init <repo>` drafts `.lights-out/` from the repository itself, and `test`, `sast` and `mutation` run the commands the contract declares, in the workbench, a compose service or an image; init and gates in 40 s on `workloads/minimal`, 8 s on `workloads/minimal-js`, under the 300 s rule; JavaScript with Stryker as the second stack (ADR 0042, *proposed*) |
| M21 | GitHub as code host: `adapters/github/`, the eight CodeHost verbs on the REST API, the token never in argv or a `.git/config`; an attached repository's merge is built, signed and released; `./go codehost-conformance` against Gitea on every push and against GitHub in a nightly (ADR 0043). The end-to-end run on GitHub is the owner's, not yet run |
| M22 | Ops without the plane: `./go incident` and `./go postmortem`, a post mortem whose timeline is anchored to the audit chain and whose action items are tickets; the `Metrics` port reads any Prometheus-compatible endpoint (`METRICS_URL`); `./go demo-postmortem` replays a recorded answer, still six roles (ADR 0044, *proposed*) |
| M23 | One command, one package: the `lights-out` wrapper (`init`, `gates`, `triage`, `postmortem`, `doctor`) on any repository from one image, mounted read-only and never given the engine socket; `./go doctor`; a GitHub Action that posts the gates' line as a check run (ADR 0045, *proposed*). Built and tested in Actions, not yet published |
| Agent network, built | The dev-worker step split between workers behind one harness port, governed like any PR (ADR 0036, still *proposed*; hand-written at L0) |

## Next

The third arc (plan §16) is built, except for the runs that are the
owner's: the Claude and OpenAI recordings, the L1 end-to-end on GitHub
and the first publish of the image. Two things close before M24, each in
a session of its own: egress for the harnesses, and the tower restoring
`.lights-out/runners/` from the base.

1. **M24 — the public legacy experiment.** Plan §14's experiment on a
   well-known open-source legacy repository, with every ticket run on the
   three providers and all three verdicts published, GO and NO-GO alike.
   The exit criterion is §14's: if at least two tickets in three do not
   reach a mergeable PR without a human touching the code, the thesis is
   weaker than expected.

## Later

- **M16 — the agent network**, reviewed and decided: who splits a
  ticket between workers, from the six roles there are.
- **M17 — the dashboard.** The board grows into the view of every
  ticket, attempt, worker and threshold you changed.
- **M11 — console.** A view of the audit chain, and go-for-launch from a
  browser.

## When someone needs it

- **M8 cloud track (L2)**: Google Cloud with Terraform and Cloud Deploy.
- **M10 (L3)**: Agent Engine and the nightly self-test.

Each cloud adapter costs money on every run and needs a nightly to stay
honest, so it is built when someone needs it.
