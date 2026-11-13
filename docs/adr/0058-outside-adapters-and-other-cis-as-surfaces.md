# ADR 0058 — Outside adapters and other CIs as surfaces: an adapter outside the repository runs only if the sha256 of its tree has a conformance GO on record in this checkout, else the Makefile refuses it in one line before anything runs; another CI runs the gates image and posts the line under its own context, which the tower never reads; Jenkins is proven by Jenkinsfile Runner, and GitLab joins CodeHost, proven by its conformance suite

- Status: accepted (amends plan §4 [outside adapters; `gitlab` joins `CodeHost`]; ADR 0024 §1 [a plugin may live outside the repository, admitted by hash, not by review]; ADR 0043 [a third code host; `ci/vendor-free.sh` gains `gitlab`])
- Date: 2026-11-13
- Milestone: M32

## Context

Ports are plugins (ADR 0024), but only inside this repository: someone with
another store, bus or code host has to wait for us. Plan M32 lets an adapter
live outside, provided it has passed its port's conformance suite, with the
proof recorded for the adapter's exact hash. Other CIs are surfaces, not
judges (ADR 0033).

Five suites exist today, in `gates/`: `codehost-`, `delivery-`,
`statestore-`, `eventbus-` and `harness-conformance.sh`.

- Four of them drive `adapters/$PORT/<verb>.sh`.
- `harness-conformance` is a different shape. It iterates the in-repo CLI
  harnesses by `CONFORMANCE_HARNESS` and builds their images from compose.

Three facts shape where the code goes:

- **Callers reach an adapter by path.** Counted 2026-11-13: 104 lines in
  `core/`, `gates/` and the Makefile name `adapters/$PORT/…`, and about 50
  more build the path from a variable.
- **`.crew/` is not a harness mount.** The worker gets only its own run
  directory (`adapters/gemini-cli/run.sh`).
- **`./go demo` runs `./go ci`** as its second stage.

## Decision

1. **Outside adapters.**
   - **Where they live.** A profile or `.env` sets `ADAPTERS_PATH`, one
     absolute directory. Each subdirectory is an adapter.
   - **How a port names one.** As `outside/<name>`, where `<name>` matches
     `[a-z0-9][a-z0-9-]*`. The pattern is this ADR's decision: it allows no
     `..`, no hidden name and no slash. The `outside/` prefix keeps a third
     party's name from shadowing one of ours, now or later.
   - **The four wired ports.** `CODE_HOST`, `DELIVERY`, `STATE_STORE` and
     `EVENT_BUS` can take an outside adapter. Their suites drive verbs, and
     their Make targets record a proof (§3).
   - **`AGENT_HARNESS` is left.** It has a suite, so `admit` refuses an
     outside harness by naming `harness-conformance`. But that suite drives
     in-repo harnesses by image build through compose, a different shape
     from the four verb suites, and M32 does not wire it. So an outside
     harness cannot be admitted yet.
   - **The ports with no suite.** `outside/` on `TRACKER`, `ORCHESTRATOR`,
     `METRICS`, `FLAGS` or `REGISTRY` is refused: no suite, no proof. Such
     a port joins the list on the day its suite exists.
   - **The catalogue.** §4's table stays the catalogue of our adapters.
     Third-party adapters live outside, with their proof.
2. **The hash.** `core/adapters.py` builds one record per regular file in
   the adapter's tree, in byte order of the relative path:
   `<path>\0<x|->\0<sha256 of content>\n`, where `x` marks the executable
   bit. The adapter's hash is the sha256 of those records. NUL separates the
   fields, so two different trees cannot produce the same records.
   - **Nothing is excluded**, not dotfiles and not `.git/`: an exclusion is
     a place to hide code.
   - **Non-regular files are refused.** A symlink, a device, a FIFO or a
     socket anywhere in the tree is refused by path, because the hash would
     not cover what runs.
   - **One changed byte** changes the hash. The adapter is then refused
     until the suite passes on the new bytes.
3. **The register.**
   - **The file.** `.crew/adapters/register`, which `ADAPTERS_REGISTER` can
     move (the tests use it). Lines are only appended, one per proof:
     `<PORT> <name> <sha256> <suite>@<sha256[:12] of gates/<suite>.sh>
     <UTC time>`.
   - **What admits.** Admission needs a line that matches the adapter's
     current hash and the current suite file. A proof made against an older
     suite does not count.
   - **Who writes it.** Only `python3 core/adapters.py register`.
   - **The Make glue.** It is one `define` in the Makefile, used by the four
     suite targets, and it runs three steps:
     1. `trial <PORT>` records the hash and links the adapter.
     2. The gate runs.
     3. `register` runs only after the gate's GO, and only if the hash is
        unchanged since the trial.
   - **What the target prints.** Its stdout stays the gate's one line.
   - **Sub-makes.** The suite target exports `ADAPTERS_TRIAL=<PORT>` to the
     makes that the suite starts (`delivery-conformance` releases through
     make). There, that port's adapter is admitted on its trial hash only.
   - **The trial record** is removed when the target ends, whether the
     suite printed GO or NO-GO. An `ADAPTERS_TRIAL` outside a running suite
     therefore matches nothing.
   - **What the register guards against.** Mistakes and drift. It does not
     guard against the owner of the checkout, who can write any file in it.
4. **Admission, the one line.**
   - **When it runs.** The Makefile tests `$(filter outside/%,…)` over the
     ports in make itself, so with no outside port no process runs. When
     the filter matches, the Makefile runs `python3 core/adapters.py admit`
     at parse time. Admission is skipped only when every goal on the command
     line is a `*-conformance` goal.
   - **On refusal.** Admission removes the link, and make stops with
     `$(error …)` before any recipe runs. Make wraps the message in its own
     `Makefile:<n>: *** … Stop.`; the message itself is one line, for
     example: `STATE_STORE=outside/json-files is refused: sha256
     3f9a0c1e2b4d has no statestore-conformance GO on record; run ./go
     statestore-conformance STATE_STORE=outside/json-files`. Twelve hex
     digits is a display choice; matching uses the full hash.
   - **On admission.** Admission links `adapters/outside/<name>` to
     `$ADAPTERS_PATH/<name>`, as a symlink in a gitignored directory. Every
     existing caller of `adapters/$PORT/<verb>.sh` works unchanged, and
     `core/` names no vendor (ADR 0024).
   - **How verbs run.** With the lights-out checkout as their working
     directory, as ours do. An outside adapter must not reach into the
     checkout by relative path.
   - **The mount.** When `ADAPTERS_PATH` is set, `./go` mounts it read-only
     at its own path. It resolves the value from the environment, `.env` or
     the profile, as make does.
   - **Where the code goes.** The logic goes in `core/adapters.py` (ADR 0052
     §2). The Makefile holds only glue.
5. **What is proven, cold and live.** `ci/outside.sh` joins `CI_CHECKS`. Its
   fixture is a test StateStore adapter that writes JSON files. The fixture
   lives in `fixtures/outside-adapters/json-files/`, and the check copies it
   to a temporary `ADAPTERS_PATH` outside the checkout, in a scratch root
   that links this checkout's files, so no link lands in the checkout. A
   profile cannot select it. The check runs eight cases, then two on the
   glue (a suite beside another goal on one command line tries nothing; no
   trial record outlives its suite):
   1. With no proof, the adapter is refused.
   2. `statestore-conformance` prints GO and registers it.
   3. After that, it is admitted.
   4. One changed byte gets it refused again.
   5. A broken copy fails the suite and stays refused.
   6. A symlink in the tree is refused.
   7. `outside/` on a port with no suite is refused.
   8. `outside/` on `AGENT_HARNESS` is refused, naming `harness-conformance`.

   This is the fixture adapter that ADR 0024 rejected. It is admitted here
   because admitting outside code cannot be proven without some outside
   code.

   `CODE_HOST`, `DELIVERY` and `EVENT_BUS` go through the same `trial` and
   `register` glue, but no outside adapter has run on them. The README says
   "not proven" for those three, and "left" for `AGENT_HARNESS`.
6. **Other CIs are surfaces, never judges (ADR 0033).** A surface runs the
   gates image through the `lights-out` wrapper, as `action.yml` does.
   - **Its own context.** It posts the one GO/NO-GO line as a commit status
     under `lights-out/jenkins`. It never uses `gates` or `review`: those
     are the contexts `core/steps/ci.sh` and `review.sh` post and the tower
     awaits. A `ci/` check asserts this.
   - **The recipe.** It is `surfaces/jenkins/Jenkinsfile`. It posts to the
     GitHub-shaped `POST /repos/{owner}/{repo}/statuses/{sha}`, which GitHub
     and Gitea both answer.
   - **The description** is cut to 140 characters, the GitHub limit sourced
     in ADR 0043 §3.
   - **Recipes not run or not written.** A recipe that has never been run is
     marked "not proven" in the README. GitLab CI and CircleCI are named
     here and not written in M32.
7. **The Jenkins proof, `./go demo-jenkins`.** It runs host-side, like
   `./go demo-package`, because its subject is the wrapper and an engine,
   as on a Jenkins agent.
   - **Gitea.** It starts a Gitea container of its own, with its own name
     and network, so it does not take the shared plane slot.
   - **The repository and the PR.** `workloads/minimal` becomes a
     repository with its `init`-drafted contract on `main`. A PR adds a
     change and its test.
   - **The runner.** Jenkinsfile Runner judges the PR in a container.
     - Base image: `docker.io/jenkins/jenkinsfile-runner@sha256:1510739cb658772e733899a56e7ababb44cc113ee7fa22ec915c5fd0e7bff7a2`.
     - Added: git, curl, and the docker CLI 29.9.3 static binary.
     - The binary is checked against sha256
       `3fb5d1f13014c18cc54945bc177c58a9056a482dada031e17d12cf2e6922c973`.
       I computed it on download on 2026-11-13, because Docker publishes no
       checksum file.
     - The container gets the engine socket. The workspace is mounted at
       its own path, because the wrapper asks the host engine to bind it.
   - **GO** comes when Gitea shows the `lights-out/jenkins` status on the PR
     head with exactly the line Jenkins printed.
8. **GitLab as a CodeHost.** `adapters/gitlab/` ships the eight verbs plus
   `ready.sh`.
   - **The instance.** It is GitLab CE 19.5.5-ce.0, released 2026-11-12,
     for amd64 and arm64. It is pulled anonymously and pinned by digest, as
     ADR 0051 §4 pins k3s. It runs in a compose project of its own beside
     the plane, `lights-out-gitlab`. `./go gitlab-conformance`, in the shape
     of `./go argo-conformance`, starts it (`adapters/gitlab/instance.sh`),
     runs `codehost-conformance` with `CODE_HOST=gitlab` and removes it
     after; `KEEP_GITLAB=1` leaves it up. The generic target never names a
     vendor.
   - **Proof.** The M32 criterion is `gates/codehost-conformance.sh` GO on
     it.
   - **Memory.** I measured it on 2026-11-13, with this ADR's settings:
     puma in single mode, sidekiq concurrency 5, and monitoring, registry
     and KAS off. It took 224 s to serve and held 2.4 GB resident. It cannot
     run beside the plane on the podman VM it was measured on (4538 MiB in
     all, `free -m`, the same day), so the full tower on
     GitLab is not run in M32 ("not proven" in the README). CI runs the
     conformance in a job of its own.
   - **The token.** It is a published low-entropy constant, seeded with
     `gitlab-rails runner` (37 s, measured 2026-11-13). This follows the
     precedent of ADR 0012 §9 and `adapters/gitea/env.sh`: the instance
     lives for one run and holds nothing worth protecting.
   - **Mapping.**
     - `failure` and `error` both map to GitLab's `failed`.
     - A merge request is the PR, and its `iid` is the PR number.
     - A merge at a given head is refused by the adapter when `pr.sh`
       already shows another head, and otherwise sent with the API's `sha`
       guard, which answers 409 when the head moved in between.
   - **Case 10's secret.** The suite looked for `GITHUB_TOKEN` or Gitea's
     password only, and would refuse any other host as unprovable. It now
     also looks for `CODEHOST_SECRET`, set by the caller or by the adapter's
     `env.sh` (GitLab's names its token there): an outside code host hands
     the suite its secret the same way.
9. **Flagger.** Flagger (v1.45.0, released 2026-09-01) on M25's k3s stays
   optional in the plan. It is recorded here, not built, and left for a
   later milestone.

## Alternatives rejected

- **A register shipped with the adapter.** That is self-certification.
- **A signature scheme.** Third parties have no key infrastructure, and the
  proof is cheap to re-run locally.
- **A register committed in the workload's `.lights-out/`.** The proof
  covers this suite and these bytes on this machine. A committed proof
  could go stale and still travel.
- **Git's tree id as the hash.** The adapter would have to be a git
  repository, and the tree id skips untracked files, which still run.
- **Outside adapters on any port, trusting the author.** The plan admits an
  adapter only with its proof, and five ports have no suite to give one.
- **Wiring `harness-conformance` now.** It would mean reshaping a suite
  that builds images through compose into one that drives an outside
  directory: a milestone of its own.
- **Rewriting the call sites to a resolver.** That is churn on more than
  100 lines for no product gain, and it conflicts with M51 moving `gates/`
  to Python in parallel.
- **Copying the adapter into the checkout.** It closes no gap that the
  symlink leaves open: the copy sits in a writable tree, as the original
  does. It also adds a second tree, which goes stale when a copy fails
  partway.
- **Admission in `core/tower.py` only.** `release`, `promote` and other
  targets call adapters directly, so they would bypass it.
- **A full Jenkins controller.** It needs a setup wizard, plugins and an
  admin account, and it keeps state between runs, all for a proof whose
  subject is the recipe.
- **Building a current Jenkinsfile Runner now.** That would put a JDK and a
  Maven build into the demo while the published image still runs.
- **A random GitLab token per run.** That is a secret to pass around for an
  instance that holds nothing.
- **The full tower on GitLab in M32.** It does not fit in memory (§8).

## Consequences

- **The one that hurts: the admitted bytes are the live bytes.** Through
  the symlink, an edit made after admission runs unproven until the next
  make parse re-admits. Every `./go` call and every sub-make re-parses, so
  the gap lasts at most one make invocation, but it is not zero.
- **Re-proving after changes.** An adapter kept as a git clone needs a new
  proof after every fetch, because `.git/` is hashed. A changed suite file
  needs a new proof for every outside adapter of its port.
- **The outside harness is left.** Until `harness-conformance` is wired, an
  outside harness is refused and the README says so.
- **Demo time.** `ci/outside.sh` runs in the demo's `ci` stage. It is cold:
  no engine, no network. Its time is measured at merge and recorded in plan
  §16 against the 900 s budget (ADR 0060 §7).
- **Jenkinsfile Runner is old but alive.** Its repository is active
  (commits in July 2026), but its last release is 1.0-beta-32 (2023-11).
  Its only official image was last pushed on 2022-07-29: amd64 only, Ubuntu
  18.04, Java 8. On arm64 it runs under qemu: a declarative pipeline took
  58 s on this podman VM (measured 2026-11-13). On amd64 runners it runs
  natively. It is accepted because what is proven is the recipe and the
  wrapper, not Jenkins' version. Two costs follow: a breaking change in a
  current Jenkins is not caught, and on the day the image disappears the
  demo needs a self-built runner.
- **The socket.** `demo-jenkins` gives the engine socket to the agent
  container. That is acceptable for a local demo, and it is what a real
  agent with an engine has. The wrapper itself still never mounts it (ADR
  0045 §3).
- **GitLab loses a distinction.** A status round trip loses `error` versus
  `failure`, so `await.sh` reports `failure` for both.
- **CI cost.** `ci.yml` gains a GitLab job with about 4 minutes of boot
  (the 224 s measured in §8) and a Jenkins job. `ci/vendor-free.sh` gains
  `gitlab`.
- **GitLab needs the VM to itself.** On 2026-11-13 a first cold
  `./go gitlab-conformance`, run beside an emulated build of the Jenkins
  agent image and other projects' containers on the 4538 MiB, swapless
  podman VM, hung the VM for minutes and failed when the database cancelled
  the token seeding on its statement timeout. Seeding is now tried three
  times; run alone, the same target was GO in 10 min 46 s, serving after
  about 245 s. Run it with nothing else heavy on a small VM.
- **Jenkins settings are environment, not parameters.** Jenkins drops the
  build parameters of a job's first run, before it knows them: the first
  `demo-jenkins` judged the change and posted nothing. The recipe reads
  `LIGHTS_OUT_STATUSES`, `LIGHTS_OUT_BASE` and `LIGHTS_OUT_HEAD` from the
  environment, as it reads the token. `demo-jenkins` took 239 s with the
  agent image already built (measured 2026-11-13).

## Golden-rule check

No shipped profile and no `.env.example` sets `ADAPTERS_PATH`, so make's
filter matches nothing and no admission process runs. The only change on
the demo path is `ci/outside.sh`, which is cold. `demo-jenkins` and the
GitLab conformance run off the demo path, pull their images anonymously and
need no account. Passes.

## Verified (2026-11-13)

- **Jenkinsfile Runner:** the repository, release and image dates are as
  stated above, and it runs with no account.
- **GitLab CE 19.5.5-ce.0:** published for amd64 and arm64, and pulled
  anonymously.
- **Flagger v1.45.0:** it exists.
- **Docker static CLI 29.9.3:** Docker publishes no checksum file for it.
