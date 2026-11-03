# ADR 0037 — Attach: `./go attach <path>` clones a repository of the user's into `.attached/`, which becomes the workload; an attached workload's contract lives in its `.lights-out/` and nowhere else, its thresholds in `.lights-out/policy.env`, and its brief for the dev-worker in `.lights-out/worker.md`

- Status: accepted (amends ADR 0030 §1 [a workload may be a repository of its own], §3 [the port gains `worker.md`, an optional `policy.env` and, attached, `tickets/`], §4 [`.lights-out/*`, `*policy.env` and `*worker.md` are platform-risk], §5 [`app-free` scans `roles/dev-worker` and bans the attach location], §7 [`demo-seam` attaches `workloads/minimal`]; ADR 0033 §1 [the judges of an attached PR]; ADR 0017 §4 and §5 [crew hands the harness ticket plus brief; Gitea mirrors the workload's repository]; ADR 0016 §6 [platform defaults in one file, workload paths out of it]; ADR 0013 §5 [the SLO deltas move to `policy/merge.env`]; takes ADR 0031 §1–§2's `worker.md` and leaves the rest of that draft open)
- Date: 2026-11-03
- Milestone: M13

## Context

On 2026-11-03 the owner set the product goal: clone lights-out, attach it to
your own repository, see everything on a dashboard. M12 put the app behind
a port, but the port's `WORKLOAD` is still a path inside the lights-out
checkout: `adapters/gitea/bootstrap.sh` pushes this checkout to Gitea, the
gates diff this checkout's history, and the dev-worker's prompt names
`app/backend`, `uv sync` and `pytest`. To use lights-out on their code, a
user forks it.

Three facts shape the answer:

- **The workbench sees one directory.** `./go` mounts the checkout at its
  own path, nothing else. The engine resolves compose bind mounts (flagd's
  flag directory) on its own host: on macOS that is the podman machine,
  which shares `/Users`, `/private` and `/var/folders` (the owner's
  machine, checked 2026-11-03), not `/Volumes` or `/opt`. Git worktrees
  show the same limit from the other side: a worktree's `.git` points at
  the main repository, outside the mount, and git fails inside workbench.
- **Thresholds are in three places.** `policy/merge.env` (margin, size,
  auto-merge levels, and three path lists that name the app),
  `verify/slo.sh` (two deltas as shell defaults), `workload.env`
  (`MUTATION_BASELINE`). A per-repository override needs one file and one
  reader, or a typo in one of them becomes a silent default.
- **`.crew/` is mounted read-write into the worker container.** Anything
  the base of a PR is built from cannot live there.

## Decision

1. **Attach is a clone inside the checkout.** `./go attach <path>` runs, on
   the host, `core/attach.sh <path> .attached` (POSIX sh and git, the two
   things the host has): `<path>` must be a git repository with
   `.lights-out/workload.env` committed at `HEAD`; its `HEAD` is cloned to
   `.attached/`, gitignored, replacing any earlier clone. Then `make attached`
   checks the contract inside the workbench (§7) and prints one line.
   `./go detach` removes `.attached/`. A new commit in the user's repository
   reaches lights-out by running `attach` again; uncommitted changes never
   do. The user's repository is only ever read.
2. **One rule places the contract.** `ATTACHED ?= .attached`;
   `WORKLOAD ?=` that directory when it holds a clone, `app` otherwise. A
   workload whose directory is the top of a git repository other than the
   platform's is *attached* (`WORKLOAD_ATTACHED=1`): its contract is
   `$WORKLOAD/.lights-out/`, with no fallback to the repository root or to
   `app/`. A workload inside the platform's repository keeps its contract in
   its directory. `WORKLOAD_CONTRACT` is exported, and every contract read
   goes through it: make's include, `COMPOSE_FILE`, `FLAGS_FILE`, flagd's
   mount, `smoke.sh`, `load.sh`, `crew-prepare.sh`, `fixtures/gates/`,
   `worker.md`, `policy.env`, and `TICKETS_DIR` (the file Tracker's
   directory: `tickets/` for the bundled app, `.lights-out/tickets/` for an
   attached repository). A compose fragment names its repository's root
   `${WORKLOAD}` in build contexts: paths still resolve from the
   platform's root (ADR 0030 §3), and an attached repository is not at a
   path it can know.
3. **Git runs in the workload's repository.** `require_range`, the risk,
   mutation and deps gates, Gitea's bootstrap push, and the tower's CI and
   review fetches use `git -C "$WORKLOAD"`; `APP_TAG` is that repository's
   `HEAD`. For `app/` it is the same repository as before, so nothing
   changes there. The mutation gate strips `git rev-parse --show-prefix`
   plus `WORKLOAD_TEST_ROOT`; the deps gate reads `<rev>:./<lockfile>`.
   `ci/secrets.sh` inside `make gates` on an attached range scans the
   target's history and tree with no allowlist. As a self-check it scans
   this checkout, where `.attached/` is allowlisted by path, after the
   check proves it gitignored and untracked (the cosign key's precedent):
   the target's own range gate is where its content is judged.
4. **An attached PR is judged by its base, and by the platform it runs
   on.** ADR 0033's step keeps its path for a bundled workload, with the
   contract's `policy.env` added to the judges. For an attached one: a
   worktree of the target at the PR head; `.lights-out/workload.env` and
   `.lights-out/policy.env` taken from `BASE_SHA` (no-overlay: one the PR
   adds and the base lacks is removed); `make gates WORKLOAD=<worktree>`
   from the platform's root. The Makefile, `gates/`, `ci/`, `core/` and
   `policy/` cannot be in a PR to another repository: they are the running
   checkout's. `demo-gates` takes the same two paths.
5. **`policy.env`.** `core/policy.py` (stdlib, `core/risk.py`'s shape)
   writes the effective policy: `policy/merge.env`, the contract's
   `MUTATION_BASELINE`, then the contract's optional `policy.env`. The
   risk and mutation gates and `verify/slo.sh` read only its output.
   - Overridable keys, nine: `MUTATION_MARGIN`, `RISK_SIZE_MEDIUM_LINES`,
     `RISK_AUTO_MERGE_LEVELS`, `RISK_HIGH_MIGRATIONS`, `RISK_HIGH_AUTH`,
     `RISK_HIGH_PAYMENTS`, `ERROR_RATE_MAX_DELTA`,
     `LATENCY_P95_MAX_DELTA`, `MUTATION_BASELINE`. `RISK_HIGH_PLATFORM`
     and `RISK_SIZE_EXCLUDE` are not.
   - NO-GO naming the key, never a default: an unknown key, a key set
     twice, a line that is not `KEY=VALUE`, a number that does not parse
     or is out of range (a score or margin outside 0–1, a delta below 0, a
     size below 1), an auto-merge level other than `low` or `medium`, a
     key without `# Provenance, measurement:`, `# Provenance, external:`
     or `# Provenance, decision:` in the comment block right above it.
   - Looser than the default is reported on stderr, one line per key: a
     higher margin, size or delta, a lower baseline, an auto-merge level
     the default lacks, a path the default list has and the override
     drops.
   - `policy/merge.env` gains the two SLO deltas (ADR 0013 §5's numbers
     and provenance, moved). Its three path lists become empty: the app's
     paths move to `app/policy.env`, so the platform's defaults name no
     workload, and a repository that declares its own paths is never
     reported as dropping the app's.
   - `RISK_HIGH_PLATFORM` gains `.lights-out/*`, `*policy.env` and
     `*worker.md`. With `high` refused in `RISK_AUTO_MERGE_LEVELS`, a
     change to an attached repository's contract never merges on its own.
6. **`worker.md`, from ADR 0031 §1–§2, no more.** A workload's brief for
   the dev-worker: markdown with `## Scope` and `## Tests`. `app/worker.md`
   holds the prompt's former lines 15–16 and 27–37; the prompt now says the
   input is a ticket followed by the workload's brief, keeps its platform
   rules, and drops ticket 0001's "four files" sentence. `core/crew.sh`
   passes `.crew/<t>/input.md` (ticket, `---`, brief) as `TICKET_FILE`,
   and NO-GOes naming the file if the brief is missing. `app-free` scans
   `roles/dev-worker/`. ADR 0031's report and durable tower documents are
   not taken (plan §7 M13 note).
7. **Checks.** `ci/workloads.sh` checks every in-repo workload, including
   `workloads/*/.lights-out/`, and with an argument the one named
   (`make attached`): the seven keys, the compose services, the flag file,
   `worker.md`'s two headings, and `policy.env` through `core/policy.py`.
   `ci/attach.sh` proves, cold: only `.lights-out/` is read; the policy
   invariants on the real CI step; the L0 crew refusal (§8). `ci/app-free.sh`
   bans `\.attached` and `\.lights-out` in `core/`, `gates/`, `verify/`,
   `adapters/`: they reach the attached repository only through
   `WORKLOAD` and `WORKLOAD_CONTRACT`.
8. **At L0 an attached repository has no recordings.** `fixtures/` holds
   this checkout's runs on its own tickets. `core/crew.sh` refuses as soon
   as it knows the role's harness: `NO-GO: crew — the attached repository
   <its origin> has no recordings to replay at L0; run the crew at L1:
   PROFILE=l1 and GEMINI_API_KEY in .env (see .env.example)`. Nothing is
   bootstrapped or cloned before it.
9. **The code host holds the workload's repository.** Gitea's repository
   is `lights-out/workload`. Bootstrap pushes the workload repository's
   `HEAD`, and leaves Actions off for an attached one: its workflows were
   written for its own CI, not for this runner, which holds the engine
   socket (ADR 0015 §7's conditions hold for lights-out's own workflow
   only). Merged changes come back by
   `git fetch http://localhost:3000/lights-out/workload.git main` in the
   user's repository, before the next `assign`, `up` or `down`: L0 Gitea
   has no volume, and every assign mirrors the attached commit again.
10. **`workloads/minimal` is an attachable repository.** Code at its root,
   contract in `workloads/minimal/.lights-out/` (with `worker.md` and a
   `policy.env` holding one stricter override), build context
   `${WORKLOAD}`, its flag file read from `.lights-out/flags/` by the
   Containerfile and the tests, the honest-fix patch root-relative.
   `./go demo-seam` copies it into a fresh git repository outside the
   checkout, attaches it, runs `down`, `up`, `smoke`, `verify`,
   `demo-rollback`, `demo-gates`, the `error_rate` assertion and `down`,
   then detaches. It refuses to start while another repository is
   attached. `./go demo` refuses too: it runs the bundled app.

## Alternatives rejected

- **Mount the user's path into the workbench.** A path outside the podman
  machine's shares (an external disk under `/Volumes`) breaks flagd's bind
  mount; a repository that is itself a git worktree would not resolve;
  worktrees and fetches would write into the user's `.git`; every `./go`
  run would need the path.
- **The clone under `.crew/`.** The worker container mounts `.crew/`
  read-write; a model could rewrite what the next bootstrap pushes as the
  base.
- **An existence rule** (`.lights-out/` if present, else the directory).
  An attached repository without `.lights-out/workload.env` would be read
  from its root, which is the fallback the contract forbids.
- **Move `app/` into `.lights-out/` too.** One layout, but `app/`'s flag
  directory is read by its code, tests and `crew-prepare.sh`, and six
  committed gate fixtures and two dev-worker recordings would need checking
  for nothing a criterion asks.
- **`policy.env` make-included like `workload.env`.** Make would run any
  `$(shell …)` in it, and an unknown key would be one more ignored
  variable.
- **`MUTATION_BASELINE` only in `policy.env`.** `workload.env`'s seven keys
  stay the port; the measured baseline stays next to the code it measures,
  and `policy.env` may set a different bar, reported if lower.
- **The refusal inside the replay adapter.** It runs after bootstrap, the
  ticket fetch and the clone; a missing ticket would answer first.
- **Re-record fixtures 0001 and 0005 on the new prompt now.** It needs the
  owner's key and a live run for each; replay does not hash the dev-worker's
  input. Left to the owner (Consequences).

## Consequences

- **The one that will hurt: an attached repository stops at release at
  L1.** The tower's release step waits for the `image` status that
  lights-out's own Gitea workflow posts; an attached repository has no such
  job and Actions are off for it. `demo-rollback`, `demo-hold` and
  `demo-launch` release the stable image under another version, so the
  canary and its rollback are proven; a merged change of an attached
  repository is not yet built and released. Building it is the next
  milestone's (M14, stacks) to place.
- Fixtures 0001 and 0005 were recorded under the pre-M13 prompt, where the
  brief was part of the system prompt; now the same words reach the model
  in its input. L0 replays them unchanged. A re-record is the owner's call.
- The attached repository's `.lights-out/` scripts (`smoke.sh`, `load.sh`,
  `crew-prepare.sh`) run in the workbench, which holds the engine socket,
  as `app/`'s do. Attach only a repository you would run on this machine.
  An agent's change to them is high risk and waits for a human.
- `RISK_HIGH_PLATFORM` still lists lights-out's own paths (`core/*`,
  `ci/*`, `Makefile`, `go`, …). A target with a directory of the same name
  gets its changes there reviewed instead of auto-merged: conservative,
  and visible in `risk.json`'s signals.
- A multi-ticket batch at L1 on an attached repository loses merges it did
  not fetch before the next assign. That is L0 Gitea's mirror semantics
  (ADR 0017 §5), unchanged; durable code-host state is outside M13.
- `ci/tower.sh` case (h) copies `core/policy.py` into the base it builds
  and passes `WORKLOAD_CONTRACT`; the CI step leaves out of its restore a
  judge neither side has (that base has no `app/policy.env`).
  `core/tests/test_risk.py` takes its path lists from a stated policy,
  since the platform's are empty.
- Expect merge conflicts in `go` and the `Makefile` with the unmerged
  `agentic-network` and `fix/perimeter-noglob` branches.

## Golden-rule check

`./go demo` runs the bundled app as before: same targets, same fixtures,
the same merged compose project (flagd's mount resolves to the same
`./app/flags`). `./go ci` gains `ci/attach.sh`, a few local git
repositories and make probes, no engine, no network. `./go demo-seam`
needs no key either. Nothing is attached on a fresh clone. Passes.
