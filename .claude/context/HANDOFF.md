# Handoff: M13 "attach", 2026-11-03, branch `claude/m13-attach-c88b96`, not pushed, not merged

The owner reviews. Plan: `docs/PLAN.md` §7 M13 (rewritten); decision: `docs/adr/0037-attach-a-repository.md`.

## Acceptance, run for real

All runs from a full clone of the branch at `<worktree>/.crew/m13-run` (see "Found" 1), on `APP_PORT=9000`, warm workbench and plane images, a host other sessions were also loading.

```
./go ci          → GO: ci, 23 checks, ci/attach.sh among them (inside ./go demo below)
./go demo-seam   → GO: demo-seam, 149 s: workloads/minimal copied into a new git repository
                   in the workbench's /tmp, attached, GO: attached, up, smoke,
                   GO: metric-shape, rollback on error_rate canary(0.2.0-outage)=1.000
                   stable(0.1.0-minimal)=0.000, honest-fix GO (risk low, auto-merge), down
./go demo        → GO: demo, milestone M9, 765s to rollback (budget 900s, plan §2);
                   rollback on error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000
./go demo-gates  → GO: demo-gates, 314 s, the app's six fixtures as recorded: failing-test (test),
                   fake-test (mutation 0.500 < 0.666), honest-fix (GO, low, auto-merge),
                   migration (GO, high, review: the path now comes from app/policy.env),
                   sast-finding (sast), vulnerable-dep (deps, 4 new advisories)
```

By hand, from the clone, against a repository in the scratchpad: `./go attach <path>` → `GO: attached — <path> at <sha>, contract in .attached/.lights-out`; a make probe shows `WORKLOAD=.attached`, `WORKLOAD_CONTRACT=.attached/.lights-out`, `WORKLOAD_ATTACHED=1`, `APP_TAG=sha-<target sha>`, `TICKETS_DIR=.attached/.lights-out/tickets`; `./go demo` refuses while attached; `./go assign TICKET=0001` → `NO-GO: crew — the attached repository <path> has no recordings to replay at L0; run the crew at L1: PROFILE=l1 and GEMINI_API_KEY in .env (see .env.example)`; `./go detach` removes the clone.

`ci/attach.sh` was written by the gate-writer from the ADR, not from the code; it caught 17 of 17 deliberate breaks of the implementation. `core/tests/test_policy.py` (47 cases plus one script-entry case) likewise.

## What changed

- `./go attach <path>` / `./go detach`, `core/attach.sh`: the user's repository cloned into `.attached/`, which the Makefile makes the default `WORKLOAD`; an attached workload's contract is `.lights-out/` and nowhere else (`WORKLOAD_CONTRACT`, `WORKLOAD_ATTACHED`, `TICKETS_DIR`).
- Gates, Gitea bootstrap and the tower's CI and review steps use `git -C "$WORKLOAD"`; an attached PR is judged by its base's `.lights-out/workload.env` and `policy.env`, from this checkout's platform; Gitea's repo is `lights-out/workload`, Actions off for attached repos.
- `core/policy.py`: one reader for every threshold; platform defaults consolidated in `policy/merge.env` (SLO deltas moved in, the app's risk paths moved to `app/policy.env`); `.lights-out/*`, `*policy.env`, `*worker.md` are platform risk; `high` can never auto-merge.
- `worker.md`: the dev-worker's prompt is workload-neutral; `app/worker.md` holds the app's lines; `core/crew.sh` sends ticket + brief, and refuses an attached repo at L0.
- `workloads/minimal` is laid out as an attachable repository; `demo-seam` attaches it.

## Found (contradicts the plan or the brief)

1. `./go` cannot drive git from a git worktree: the workbench mounts only the worktree, whose `.git` points outside it. Every session under `.claude/worktrees/` needs a full clone to run plane targets (M15 found the same). Not fixed: a candidate is mounting `git rev-parse --git-common-dir` when it lies outside the checkout.
2. All sessions share one podman machine and one compose project (`name: lights-out`). This session's first `demo-seam` (about 15:35 CET) ran `down` on a plane another session had up: its `podman ps` came too early. The parent session then set the rule (check by label, down after each run, M13 first). Separately, at 15:40:12 CET every container on the machine was removed, other projects' stopped ones included; this session's logs show only `lights-out-*` removals. Volumes and images are intact.
3. The podman machine shares `/Users`, `/private` and `/var/folders`, not only `$HOME`; ADR 0037's context says so.
4. ADR 0036 is taken by the unmerged `agentic-network` branch; this one is 0037 (M15 took 0038).

## Not done, and open decisions for the owner

- Fixtures 0001 and 0005 were recorded under the old prompt; the same words now reach the model in its input. Re-record (needs your key and an L1 run each) or accept.
- `./go report` and durable tower documents (old M13, ADR 0031 §3–§6): proposed for M17, not decided.
- At L1 an attached repository's tower run stops at release: no `image` job builds its merge. Proposed for M14.
- `RISK_HIGH_PLATFORM` still lists lights-out's own paths (`core/*`, `ci/*`, `Makefile`, `go`); a target with such a directory gets those changes reviewed, never auto-merged.
- `roles/product/prompt.md` still says "meetup" (app-free now scans `roles/dev-worker/` only; the product role's change re-hashes the ADK fixtures). `ci/prompts.sh` does not read `worker.md` files.
- Expect conflicts on merge with `agentic-network`, `fix/perimeter-noglob` and M15's branch in `go`, `Makefile`, `core/crew.sh`, `docs/PLAN.md`, `README.md`, `docs/reference.md`.

## First thing M14 should look at

The release of an attached repository's merge (who builds the image when the repository has no lights-out workflow), then the worker's toolchain per stack, starting from `.lights-out/worker.md`'s `## Tests`.
