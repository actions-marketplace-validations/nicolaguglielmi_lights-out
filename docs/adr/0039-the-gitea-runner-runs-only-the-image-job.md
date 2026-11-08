# ADR 0039 — The `ci` job runs only on GitHub; the L0 Gitea runner's one job is `image`

- Status: accepted (amends ADR 0002 [one workflow file for both hosts still holds; on Gitea it now runs only `image`] and ADR 0025 §4 [the image job is the runner's only job, not its first])
- Superseded 2026-11-08 by ADR 0060 §5-§6: the runner is gone, so it has no job at all. The `image` build is the release step's own work (`core/steps/release.sh`, for every workload), Gitea Actions are off, and `ci/gitea-compat.sh` is retired. §1's guard stays on every job, inert. The measurements below remain the record of why the runner's queue was a cost.
- Date: 2026-11-03
- Milestone: follow-up to M15 (the golden rule could not be verified on 2026-11-03)

## Context

`.github/workflows/ci.yml`'s `ci` job (`./go ci`) had no `if:`. Inside
the L0 plane the Gitea runner ran it on every push e2e makes: the
bootstrap force-push of `main`, the worker's `ticket/<id>` push, the PR
(`pull_request`), the merge commit. The runner runs one job at a time
(`gitea-runner` 3.4.2's default `capacity: 1`; `adapters/gitea/runner/
config.yaml` does not set it). So up to four `./go ci` runs — 23 checks
each, `core-tests`, `tower` and `contract` among them — sat ahead of the
merge commit's `image` job, which `core/steps/release.sh` waits for with
`IMAGE_TIMEOUT=300` (ADR 0025 §5). On 2026-11-03, on a loaded host,
`./go demo` failed twice in e2e at `await-gitea: image on <merge sha>
still pending after 300s` while Gitea's `actions/tasks` showed the
runner on `ci` jobs.

Nothing read those jobs. Gitea posts no commit status per job (ADR 0025
§4, verified 2026-09-20). At L0 the CI leg is `core/steps/ci.sh`: the
base's gates, run in workbench, posted as the `gates` status (ADR 0019,
ADR 0033). `./go demo` already runs `./go ci` once, as its first stage,
on the tree bootstrap pushes. And on a ticket branch the runner's `ci`
ran the PR's own `ci/` scripts, the self-judging ADR 0033 rules out.

## Decision

1. **`ci` gets `if: github.server_url == 'https://github.com'`**, the
   guard `engine-compat`, `gates`, `launch` and `seam` already carry
   (ADR 0012 §5). On GitHub nothing changes. On Gitea the runner's only
   job is `image`, on `main`.
2. **Nothing else moves.** `IMAGE_TIMEOUT` stays 300, the runner keeps
   one slot, and bootstrap's push still triggers an `image` job for the
   tag `./go up` already published (a cached build and a push of layers
   Zot has), which is the one job left ahead of the merge's.

## Measured

`./go demo`, L0, 2026-11-03, one run each, back to back on the same
machine (Mac15,12, 8 cores; podman machine 4 CPU / 4 GiB), each from a
fresh full clone with the plane down and the engine's image cache as
earlier runs left it. Runner jobs from Gitea's `actions/tasks`, polled
every 5 s.

| | before (main a53e166) | after (this change) |
|---|---|---|
| `./go demo` | GO, 561 s to rollback | GO, 353 s to rollback |
| host load, 1 min, at start | 10.7 | 4.4 |
| `ci` jobs on the runner | 4 (bootstrap 71 s, PR 61 s, ticket push 75 s, merge 51 s) | 0 (skipped) |
| merge commit's `image` | ran after the merge's own `ci`: ≥ 55 s after the merge | success ≤ 10 s after the merge |

The `image` wait accounts for about a minute of the 208 s gap. The rest
is not attributed: the four `./go ci` runs shared the podman machine's
4 CPUs with the tower's own work, but one pair of runs, started at
different host loads, does not separate that from noise. What the
numbers do show is the mechanism of the failures in Context: before, the
merge's `image` waited behind up to four `ci` jobs whose length grows
with the host's load; after, it waits behind none.

## Alternatives rejected

- **Raise `IMAGE_TIMEOUT`.** Waits the queue out instead of removing it:
  every demo pays its length out of the 900 s budget.
- **Runner `capacity: 2`, or a second runner for `image`.** Builds the
  image while `make ci` runs on a host that is already the bottleneck;
  the second runner is also a new compose service.
- **Run `ci` on Gitea only for `pull_request`, or only off `main`.** Still
  one `./go ci` ahead of the merge's `image`, and its result is still
  read by no one.
- **Keep `ci` on Gitea and have the tower read it.** It would be a second
  CI verdict next to `gates`, computed by the PR's own scripts (ADR 0033).

## Consequences

- At L0 (and L1, which shares the Gitea runner) the repo's self-CI runs
  where `./go demo` and `./go ci` run it, in workbench; on GitHub, on
  every push and PR as before.
- `docs/ARCHITECTURE.md`'s "one workflow YAML" line says the Gitea side
  runs only `image`.

## Golden-rule check

Removes the four `./go ci` runs that sat on the runner between the
bootstrap and the merge's `image`. `./go demo` measured GO in 561 s
before and 353 s after, against the 900 s budget (see Measured).
