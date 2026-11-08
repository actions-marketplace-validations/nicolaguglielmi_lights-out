# Handoff: M34, the lean plane (ADR 0060), 2026-11-08

Branch `claude/m34-lean-plane-a0d988`, on 30ca9dc (the adoption roadmap, on `fix/adr-still-header`, M33 not yet on main). Pushed, no pull request, not merged: landing is the owner's, with M31 and M35 beside it.

## Acceptance, on GitHub Actions

On 8fd756c, every workflow the push triggers green: ci 42508676734, stranger 42508676759, self 42508676764, package 42508676787, podman 42508676737; `site` did not trigger on those paths and was green on e2599c8 (42506965553).

```
engine-compat  GO: demo, milestone M9, 757s to rollback (budget 900s, plan §2)
stranger       GO: demo, milestone M9, 801s to rollback (./go demo: 802s, exit 0)
engine-compat  after ./go down && ./go up: GO: logbook — .crew/logbook-restarted.json, 1 tickets
               launch.plane {"canary":"0.2.0-waitlist",...} → {"canary":null,...}; the rest identical (diff empty)
launch         GO: demo-launch, GO: demo-console, GO: codehost-conformance — gitea, PR #1 merged
               GO: statestore-conformance — firestore-emulator, 8 cases
               GO: eventbus-conformance — pubsub-emulator, 5 cases; case 5 (redelivery) not run
mainline       GO: demo-mainline, GO: demo-rework
seam           GO: demo-seam
local          ./go ci from a clean clone: GO: ci (4 min 50 s), store-bus GO: sqlite 8 cases, spool 6 cases
```

The run before, e2599c8: 873 s and 852 s, with `demo-rework` red (stale expectation, below) and the logbook `cmp` red at `launch.plane`.

## What changed

- ADR 0060 before the code; the two suites and `ci/store-bus.sh` written by a subagent from the ADR without seeing the adapters, then run against them.
- `adapters/sqlite` (StateStore) and `adapters/spool` (EventBus): stdlib Python behind `.sh` verbs, `.crew/state.sqlite` and `.crew/spool.sqlite`, default at L0 and L1. The emulators sit behind the compose profile `emulators`, started when a profile names them.
- The Gitea runner, its image, the `image` job and `ci/gitea-compat.sh` are gone; Gitea Actions off; no compose service holds the engine socket; `./go` no longer passes `HOST_DOCKER_SOCK`.
- `core/steps/release.sh` builds every workload's merge in a throwaway worktree; for the bundled app it restores the checkout's Makefile, compose file, profiles and adapters over the merge's first, and signs with the checkout's key.
- Dated amendments to ADR 0039 (superseded), 0025 §4 §5 and 0043 §4; PLAN §3, §4 rows and the M34 status note; ARCHITECTURE, reference, ROADMAP, the board's release stage.

## Contradictions with the plan, and open points

- **The budget.** The plan proposed 600 s warm, to be measured. Measured: 757 to 873 s on this branch, 116 s apart on the same job. The budget stays 900 s (ADR 0060 §7). M34 removes a failure mode (the 300 s `image` wait) and three services, not seconds on Actions: a green run's image wait was about a second, and GitHub pulls the emulators fast. The time is in the demo's `ci` stage (43 %, every check run twice, once inside `contract`'s cold re-run) and the workbench build (15 %).
- **"Identical logbook"** holds except `launch.plane`, which reads the live Delivery status: `down` removes the rolled-back canary revision the demo leaves at weight 0. The CI step compares everything else and prints both plane values.
- **The plan named the bus `inproc`**, which is the Orchestrator's directory; it is `spool`.
- **State now outlives `./go down`**: a stranded ticket or a red `mainline/main` stays until `./go resume` or deleting `.crew/state.sqlite`. The demos delete their own documents first.
- **Found:** `demo-rework` had been NO-GO since M30 (its expected history lacked the `mainline` step) and no workflow ran it; it now runs in the `mainline` job. The Firestore emulator refused a JSON array only by a jq accident; now by rule. `ci/board.sh`'s "nothing to read" probe assumed a network store.
- **Left to M31** (noted in the shared notes folder): `core/doctor.sh` and the README lines describing it still require ports 8085 and 8086 free.
- Not done, a follow-up: the `if: github.server_url == 'https://github.com'` guards and the "L0 Gitea runner reads this directory" comments in the other workflows are inert now.

## First thing for the next milestone

The demo budget: the `ci` stage runs every check twice (`contract` re-runs each one cold to check its output line), about 170 s of an 800 s demo. Making `contract` judge the lines the first pass already printed, or running a smaller `ci` in the demo, is the next real cut; nothing in the plane is left to trim.
