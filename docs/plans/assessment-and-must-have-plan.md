# Assessment and plan — from a talk-ready harness to a tool every developer installs

- Date: 2026-11-03
- Scope: state of the repository at `main` a53e166, adherence to [docs/PLAN.md](../PLAN.md) (§2, §14, §15) and to [ROADMAP.md](../../ROADMAP.md), and a plan for the open-source release
- Author: the owner, with Claude Code; the owner decides what of this enters the plan

## Verdict

lights-out is a disciplined governed-autonomy harness: 38 ADRs, 23
self-checks in `./go ci`, the gate output contract kept everywhere, no
hidden mock, and the golden rule holding (`./go demo` reaches rollback
in 459 s on a clean clone today, budget 900 s). It is faithful to the
plan.

It is also, today, a product for a talk and for a platform team, not for
"every developer". The differentiating asset — the automatic rollback of
a change an agent wrote, the declared perimeter, the mutation gate, the
audit chain — sits under eight compose services, one model runtime
(Gemini CLI on a preview pin) and a heavy `.lights-out/` contract. The
central thesis of plan §14, that the harness works on a codebase not
written for it, is not measured yet.

## State of the repository

| | |
|---|---|
| Commits / ADRs / make targets | 167 / 38 / 41 |
| Tracked lines (fixtures and lockfiles excluded) | about 25,700, in sh, py and md |
| Milestones closed | M0–M9, M12, M13, M15, the agent network (hand-written at L0) |
| Milestones open | M8 cloud track, M10, M11 console, M14 stacks, M16, M17 |
| `./go ci` on the owner's checkout, 2026-11-03 | **NO-GO: secrets** |
| `./go ci`, `./go demo`, `./go demo-seam` on a clean clone, same day | GO / GO, 459 s / GO |
| GitHub | private, 0 stars, topics set, Discussions off, no release, no issues, no recording of the rollback |

Findings:

- **The `secrets` NO-GO is local but real.** `ci/secrets.sh` runs
  `gitleaks dir` over the whole directory and finds eight copies of
  `.env` and `.crew/cosign.key` under `.claude/worktrees/*` and
  `.crew/integration/`. The allowlist in `ci/gitleaks-worktree.toml` is
  anchored to those two paths at the root only. A contributor who works
  in git worktrees hits it on their first `./go ci`.
- **Uncommitted leftovers:** ADR 0031 (proposed, never tracked),
  `.DS_Store`, fifteen local worktrees.
- **Plan and roadmap disagree on order.** Plan §14 says: experiment, then
  M11. ROADMAP says: M14, M16, experiment, M17.
- **Two of the four newest demos replay hand-written patches** (network,
  rework). Declared in the README, but it weakens the "nothing is faked"
  hook that §15 builds the launch on.
- **Fixtures 0001 and 0005 were recorded under the old prompt** (M13
  handoff). They replay, but they no longer prove the prompt that ships.

## Adherence to the goals

What holds: the golden rule (459–765 s measured, 900 s budget); replay
and hand-written runs declared where they happen; the `Workload` and
`Delivery` seams proven by `ci/app-free.sh` and `ci/vendor-free.sh`; six
roles, checked by `ci/roles.sh`; every threshold with its provenance;
English everywhere but the plan.

What does not hold, or holds halfway:

1. **Phase 0 of §15 is half done.** README, CONTRIBUTING, SECURITY,
   ROADMAP and the issue forms exist. Missing: the rollback recording,
   `v0.1.0`, Discussions, the 5–8 `good first issue`s, the soft launch.
2. **The implied audience is not "every developer".** To run lights-out
   on your own repository you need: a podman machine with 6 GB, a 1.2 GB
   pull, seven free ports, the engine socket handed to a container, a
   `.lights-out/` with a compose fragment, smoke and load scripts, a
   cosmic-ray runner and a bandit runner, Python 3.13 and Node 24, and a
   Gemini API key. The merge lands on a local Gitea and the loop stops at
   release. A developer who uses Claude Code or Codex on GitHub finds no
   way in.
3. **The thesis is unmeasured.** Everything proven so far runs on
   workloads written for lights-out (`app/`, `workloads/minimal/`).

## The plan: three horizons

Principle: **the gate pack is the product every developer installs; the
full plane is the product a platform team installs.** Today only the
second exists. The one change to §15 is to pull its "phase 3" forward and
run it beside the experiment, because the experiment buys credibility
and the gate pack buys adoption, and a launch needs both.

Budget assumed: 5–15 hours a week (§14 amendment of 2026-11-02).

### Horizon 1 — weeks 1 to 4: publishable and honest

1. Fix the `secrets` gate: scan tracked and untracked-but-not-ignored
   files, not the whole directory. The first `good first issue`.
2. Decide ADR 0031 (commit it as proposed, or delete it); add `.DS_Store`
   to `.gitignore`; make ROADMAP follow §14's order.
3. A recording of the rollback under 60 s at the top of the README;
   release `v0.1.0`; enable Discussions; open 6–8 issues from the M13
   handoff's findings (`roles/product/prompt.md` still says "meetup",
   `ci/prompts.sh` does not read `worker.md`, `./go` cannot drive git
   from a worktree, `RISK_HIGH_PLATFORM` lists lights-out's own paths on
   an attached target).
4. Re-record fixtures 0001 and 0005 under the shipped prompt (two L1
   runs, the owner's key).
5. Soft launch to 10–20 trusted people, Linux and macOS, one question:
   "did `./go demo` reach the end on your machine?". Every friction found
   here is fixed before anything public.

### Horizon 2 — months 1 to 3: the thesis, in public

6. The legacy Python experiment of §14, with the weekly diary, GO and
   NO-GO alike. It is the only thing that earns the sentence "proven on a
   codebase that was not written for lights-out".
7. M14 cut to what the experiment needs: the dev-worker runs on the
   target repository's own toolchain, and a merge on an attached
   repository is built and released.
8. Postpone M16 (the network, decided) and M17 (the dashboard): neither
   moves adoption.

### Horizon 3 — months 3 to 6: the must-have

9. **`lights-out gates` as a package of its own**, with its ADR (ROADMAP
   already asks for one): the six gates and the perimeter check on any
   pull request, with no plane and no engine socket. `secrets` and
   `deps` already run in the bare workbench; `test`, `mutation` and
   `sast` go through the workload's in-image runners today and move to
   "run the command `worker.md` declares". Distribution: a GitHub
   Action, a pre-merge hook, and a command Claude Code or Codex can call
   that prints `GO` or `NO-GO`.
10. **A minimal contract.** For the gates, `policy.env` and `worker.md`
    are enough. The compose fragment, the flags, smoke and load stay for
    whoever wants the canary and the rollback.
11. **`claude-code` and `codex` adapters on the `AgentHarness` port**: a
    directory and an ADR each, as `network` showed. Gemini stays the
    L0/L1 default because the fixtures are recorded there, but the README
    stops saying "Gemini" in its first lines.
12. **A `github` adapter on the `CodeHost` port** (already in the §4
    table, assigned to M10): the pull request lands on the user's
    repository, not on the local Gitea. Without it, `attach` closes the
    loop for nobody.
13. A second stack, JavaScript with Stryker, after Python.

### Measured before launch, as §15 requires

- Time to the first `GO` on your own repository, without the plane:
  target under 10 minutes.
- Share of attached repositories that reach a mergeable PR with no human
  touching the code (the §14 exit criterion, two in three).

### Not before an external consumer exists

The M8 and M10 cloud tracks, the full M11 console, M16, M17.
