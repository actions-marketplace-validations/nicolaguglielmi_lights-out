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

## Next

1. **Contributor surface and README.** This file, CONTRIBUTING.md, a
   quickstart and a guide for using lights-out on your own codebase.
2. **M13 — ready for the experiment.** A workload-neutral dev-worker
   prompt, `./go report`, tower records that survive a restart (ADR 0031).
3. **The public legacy experiment.** lights-out pointed at a known
   open-source Python codebase, on a batch of mechanical tickets
   (dependency upgrades, dead code, tests for untested code, deprecated
   APIs). The audit chain is published and the runs are replayable
   without a key. It fails if fewer than two tickets in three produce a
   mergeable PR with no human touching the code.

## Later

- **M11 — console.** A view of the audit chain, and go-for-launch from a
  browser.
- **Gates for any agent.** The gates packaged to run beside Claude Code,
  Codex or Copilot. It needs its own ADR first.
- **Language independence**, for the language of the first adopter who
  needs it.

## When someone needs it

- **M8 cloud track (L2)**: Google Cloud with Terraform and Cloud Deploy.
- **M10 (L3)**: Agent Engine and the nightly self-test.

Each cloud adapter costs money on every run and needs a nightly to stay
honest, so it is built when someone needs it.
