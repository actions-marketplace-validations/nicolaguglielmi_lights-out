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

1. **M14 — other stacks.** The dev-worker on your repository's own
   toolchain instead of Python 3.13 and Node 24, with one stack beyond
   Python proven end to end.
2. **M16 — the agent network**, reviewed and decided: who splits a
   ticket between workers, from the six roles there are.
3. **The public legacy experiment.** lights-out attached to a known
   open-source Python codebase, on a batch of mechanical tickets
   (dependency upgrades, dead code, tests for untested code, deprecated
   APIs). The audit chain is published and the runs are replayable
   without a key. It fails if fewer than two tickets in three produce a
   mergeable PR with no human touching the code.
4. **M17 — the dashboard.** The board grows into the view of every
   ticket, attempt, worker and threshold you changed.

## Later

- **M11 — console.** A view of the audit chain, and go-for-launch from a
  browser.
- **Gates for any agent.** The gates packaged to run beside Claude Code,
  Codex or Copilot. It needs its own ADR first.

## When someone needs it

- **M8 cloud track (L2)**: Google Cloud with Terraform and Cloud Deploy.
- **M10 (L3)**: Agent Engine and the nightly self-test.

Each cloud adapter costs money on every run and needs a nightly to stay
honest, so it is built when someone needs it.
