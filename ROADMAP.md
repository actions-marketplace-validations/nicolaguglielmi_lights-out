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
| Agent network, built | The dev-worker step split between workers behind one harness port, governed like any PR (ADR 0036, still *proposed*; hand-written at L0) |

## Next

The third arc (plan §16, decided 2026-11-03): zero entry cost, and the
model is a choice. Each milestone gets an ADR first and leaves `./go ci`
and `./go demo` green. M18 and M20 touch different files (but the
Makefile and the README) and can run in parallel; M19 needs M18; M21,
M22 and M23 need M20.

1. **M18 — the model is a choice.** `MODEL_PROVIDER` (gemini, anthropic,
   openai) and `MODEL` in the profile or `.env`; a role keeps only its
   thinking level and budgets; the ADK roles run on Claude and OpenAI
   through ADK's LiteLLM wrapper; `ci/model-free.sh` keeps model ids out
   of the core. L0 stays replay, with no key.
2. **M19 — `claude-code` and `codex` harnesses.** Two more adapters on
   the `AgentHarness` port, same artefact contract as `gemini-cli`, and
   a harness conformance suite every adapter must pass: push denied,
   `.env` unreadable, budgets enforced, the served model recorded, no key
   in the artefacts.
3. **M20 — gates anywhere.** `./go init <repo>` drafts `.lights-out/`
   from the repository itself; `test`, `sast` and `mutation` run the
   commands the contract declares in the repository's own toolchain
   image, so the dev-worker is no longer tied to Python 3.13 and Node 24;
   a second golden rule: `init` and `gates` under 300 s, no plane.
   JavaScript with Stryker as the second stack. Absorbs M14's toolchain
   half.
4. **M21 — GitHub as code host.** The ticket's PR lands on your
   repository, judged by your base's policy; a merge on an attached
   repository is built, signed and released. Proven by a nightly against
   a throwaway repository. Absorbs M14's release half.
5. **M22 — ops without the plane.** An incident in (alerts, release
   record, logs), a post mortem out, anchored to the audit chain, with
   every action item a ticket that re-enters the tower; the `Metrics`
   port reads any Prometheus-compatible endpoint (`METRICS_URL`).
   Still six roles.
6. **M23 — one command, one package.** A published image and a thin
   `lights-out` wrapper: `init`, `gates`, `triage`, `postmortem` on any
   repository without cloning lights-out; a GitHub Action for the gates;
   a recipe for calling them from a Claude Code, Codex or Gemini CLI hook.
7. **M24 — the public legacy experiment**, every ticket run with the
   three providers, the three verdicts published.

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
