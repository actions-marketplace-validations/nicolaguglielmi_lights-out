# Use lights-out on your own codebase

The quickstart runs lights-out on the app that ships with it. This guide
puts your repository behind the same gates and, if you want, the same
canary and rollback. You keep a plain clone of lights-out. Your repository
gets one directory, `.lights-out/`, which you copy in and commit.
lights-out never writes to your repository.

The guide has two halves. The gates half (section 1) needs no plane, no
Gemini key and, with the workbench as your toolchain, no engine socket.
The plane half (section 2) adds the services, the canary and the rollback.

## What is proven and what is not

| | Status |
|---|---|
| A repository outside the lights-out checkout, attached, end to end (up, smoke, verify, rollback, gates) | Proven: `./go demo-seam` copies `workloads/minimal/` into a new repository and attaches it (ADR 0037) |
| `./go init` and `./go gates` on a repository with no plane | Proven on the two examples: `./go demo-init` runs both on `workloads/minimal/` and `workloads/minimal-js/` (ADR 0042 §10). Not proven on any other repository |
| The 300 s budget for init and gates | Proven on two small examples only. Init measures the whole scope (ADR 0042, Consequences) |
| The platform reads only your `.lights-out/`, and never names your repository | Proven: `ci/attach.sh` and `ci/app-free.sh` run in `./go ci` |
| A PR is judged by your base branch's policy and runners, and a change to `.lights-out/` never merges on its own | Proven: `ci/attach.sh` |
| The wrapper, from the image: `lights-out init` and `lights-out gates` on a repository with no clone of lights-out | Proven on `workloads/minimal/` as a repository of its own, by `./go demo-package` in GitHub Actions (ADR 0045 §8). Not proven on any other repository |
| The Action `action.yml` at the root, and the two standalone Actions in `actions/` | Proven in lights-out's own workflow (`uses: ./` on a scratch repository posts a GO and a NO-GO check run, and the two standalone Actions' gates run the same way) and on one repository that is not lights-out, [a probe](https://github.com/nicolaguglielmi/lights-out-probe/pull/1), with the image built in the job before 0.3.0 is published |
| The image `ghcr.io/nicolaguglielmi/lights-out:0.2.0` published | **Yes**, 2026-11-08, tag `v0.2.0` (0.1.0 on 2026-11-05), public, amd64 and arm64, unsigned (pin it by digest). CI builds and tests the image on every push |
| The hook recipes (section 5) | The `--light` recipes **verified** once per CLI on 2026-11-08 (Claude Code 2.1.311, Codex 0.166.0, Gemini CLI 0.61.0-preview.0) against the scripted model, not a vendor; each recipe says what was not covered. The full variant was not run against the CLIs |
| The light tier, `lights-out-gates --light` (ADR 0061) | Proven in `./go ci` (`ci/gates-light.sh`): on the nine fixtures of `./go demo-gates` it agrees with the full gates where both run, and it answers on this repository in under 10 s. Not on PyPI yet |
| A codebase that was not written for lights-out | **Not yet proven.** It is the public legacy experiment (plan §14) |

Known limits today, before you start:

- **No recordings of your repository.** Without a key, lights-out replays
  runs recorded on its own app. On an attached repository the crew stops
  at L0 and says so; agents need L1 and a Gemini API key.
- **Release of a merged change is implemented, not run on your code.** For
  an attached repository the tower builds the merge commit from your own
  Containerfile, signs it and releases it (ADR 0043 §4); the bundled app
  still waits for the Gitea `image` job. The canary and its rollback are
  proven on your stable image (section 2). No run has released a merged
  change of a repository that was not written for lights-out.
- **With the workbench, your tests run here.** `TOOLCHAIN_IMAGE=workbench`
  makes `./go init` and `./go gates` run your repository's commands
  in-process, inside lights-out's toolchain container, on this machine. An
  image or `compose:` form runs them in a container the engine builds.
  Attach only a repository you would run on this machine. The tower
  isolates its own runs.
- **Plane targets give your scripts the engine.** `./go up` and the other
  plane targets hand lights-out's toolchain container your container
  engine's socket, which means full control of the engine (README, "What
  is real"). Attach only a repository you would run on this machine.
- **The 300 s budget holds for small suites only.** Init measures the whole
  scope. The bundled app's whole-package run took 792 s, so init on a
  codebase that size would miss the budget on the baseline alone.
- **A first commit is judged whole.** `./go gates` with no range judges the
  last commit, and on a repository with one commit that is the whole tree.
  `deps` judges every lockfile whole, so an advisory already in a fresh
  repository's lockfile is a NO-GO on its first `./go gates` (ADR 0015's
  time bomb, now on your first run).
- **Init drafts the gates half only.** The plane half (`compose.yaml`, the
  flag file, the smoke and load scripts, the fixtures) cannot be inferred
  from a lockfile. You write it.
- **Two stacks.** Init infers python and javascript from their files. For
  any other repository it names what it looked for and stops.
- **A `compose:` workload's worker stays on the workbench.** The dev-worker
  runs in an image of your own only when `TOOLCHAIN_IMAGE` names an image
  (ADR 0042 §8).
- **The dev-worker's image is built, not yet run.** On an image form the
  worker's image is built on your toolchain image. The build was verified on
  `docker.io/library/python:3.13-slim-trixie`. No run at L1 has been made,
  because the session had no key.

## 1. Gates on your repository: `init`, then `gates`

### Start from an example

Two examples show the layout your repository will have:

- `workloads/minimal/` is python: FastAPI, with the plane half. It is the
  smallest thing that satisfies the port (ADR 0030).
- `workloads/minimal-js/` is javascript: `node --test`, no runtime
  dependencies. It has the gates half only: no compose file, no flag file.

Both keep their `.lights-out/` committed. Use them as a reference for what a
value looks like. Then:

```sh
./go init ~/code/your-repo
./go gates
```

`./go init <path>` attaches a clone of your repository's `HEAD` into
`.attached/`, then drafts the gates half of `.lights-out/` there. Without a
path, it drafts into the clone that is already attached. `./go gates` judges
the last commit of that clone, with the draft as its contract. Neither
command writes to your repository.

### What init writes

`.attached/.lights-out/` holds:

| File | What it is |
|---|---|
| `workload.env` | The twelve keys, below, each under a provenance line |
| `worker.md` | The dev-worker's brief: `## Scope` (the paths it may change) and `## Tests` (the exact command, and where to run it) |
| `policy.env` | Your thresholds. A draft overrides none: every threshold is the platform default (section 3) |
| `runners/` | The stack's runners, copied from `stacks/<stack>/runners/`: cosmic-ray and bandit for python, StrykerJS and eslint with eslint-plugin-security for javascript. Each set is pinned by its own lockfile |

Init also lists, on stderr, every secret gitleaks finds in your history,
each with its fingerprint. The secrets gate judges the whole history: a key
in history is live until it is rotated. Rotate a real one. A finding you
judge a false positive is excused by its fingerprint in
`.lights-out/.gitleaksignore` (gitleaks' own format), which init never
writes. The gate reads that file from the base of the range, never from
the change it judges, so a change cannot excuse its own finding, and it
still prints each excused finding on stderr ([ADR 0049](adr/0049-lights-out-judges-itself.md)).

The plane half is in section 2.

### The twelve keys

`ci/workloads.sh` checks these twelve keys. The first seven are ADR 0030's
contract, `WORKLOAD_TEST_PATHS` is ADR 0053's, and the last four are ADR
0042's runner contract.

| Key | What it says |
|---|---|
| `CANARY_VERSION` | The version string your flag file targets as the failing release. Plane half: empty in a draft |
| `MUTATION_BASELINE` | Your suite's measured mutation score (section 1, provenance). `./go init` measures it |
| `WORKLOAD_KILL_SWITCH` | The flag that turns the risky feature off. Plane half: empty in a draft |
| `WORKLOAD_SAMPLE_PATH` | One read-only, instrumented `GET` route. Plane half: empty in a draft |
| `WORKLOAD_LOCKFILES` | Lockfiles for the dependency gate, `:`-separated |
| `WORKLOAD_MUTATION_SCOPE` | The source directory the mutation gate reads |
| `WORKLOAD_TEST_ROOT` | The prefix stripped to address lines in the compose test image (may be empty). On the workbench and image forms, the directory the three commands run from |
| `WORKLOAD_TEST_PATHS` | Which files are tests, `:`-separated globs relative to the repository's root, `*` crossing `/`. `test-proof` runs the ones a change adds or edits on the base, where they must fail; `test-weakening` refuses a change that deletes them, drops assertions or tests, or adds skips. `./go init` drafts your stack's default discovery |
| `TOOLCHAIN_IMAGE` | Where the three toolchain gates run their commands: `workbench`, `compose:<service>` or an image reference. The three forms are below |
| `TEST_CMD` | The test command, one `sh -c` line, run from the repository's root. Its exit code is the verdict of the `test` gate |
| `SAST_CMD` | The static analysis command, one `sh -c` line. It prints one line, `{"findings": N}`. Any finding is a NO-GO. A non-zero exit with no findings parsed is one too |
| `MUTATION_CMD` | The mutation command, one `sh -c` line. It reads `MUTATION_LINES` (`all` for the whole scope, as init uses it) and prints one line, `{"total","killed","survived","score"}`. The gate compares the score with `MUTATION_BASELINE` and `MUTATION_MARGIN` |

A key that is empty or names a missing path makes its gate answer NO-GO and
name the key. A typo never turns into a silent GO.

A ticket that removes tests on purpose (a dead feature, a refactor that
merges two suites) says so in a `## Removes tests` section, list items of
globs in the `## Perimeter` form. `test-weakening` excuses the files it
matches and prints each one on stderr; without the section, nothing is
excused ([ADR 0053](adr/0053-tests-that-prove-and-tickets-that-wait.md)).

The three `*_CMD` keys run from the repository's root. On the workbench and
image forms they run from `WORKLOAD_TEST_ROOT`; `compose:` runs them where the
image's working directory is. A `*_CMD` may not contain `$` or `#`: make's
`include` would expand the one and cut at the other. `ci/workloads.sh`
refuses both.

### The three forms of `TOOLCHAIN_IMAGE`

- **`workbench`**: the command runs in lights-out's toolchain container,
  in-process, with no engine. The workbench has Debian trixie,
  Python 3.13, uv, Node 24 and npm. A Python the workbench lacks fails
  loudly; it is not downloaded (`UV_PYTHON_DOWNLOADS=never`). No engine
  socket is needed.
- **`compose:<service>`**: a service of your `compose.yaml` with profile
  `test`, built and run through the engine. The bundled app uses
  `compose:backend-test`. This form needs the plane half, and the socket.
- **An image reference**, such as `docker.io/library/node:24@sha256:…`: a
  throwaway image is built from it through the engine, with your repository
  copied in. Nothing of the host is mounted, and the judged code cannot write
  into the clone. This form needs the socket. Pin the reference by digest.

Where a gate ran goes on its GO line: `GO: test — in workbench`,
`GO: test — in compose:backend-test`, or `GO: test — in
docker.io/library/node:24@sha256:…`. An engine form without a socket is a
NO-GO that names the socket. It never falls back to the workbench.

### What init infers, and from what

- **The stack.** A `pyproject.toml` with a `uv.lock` makes a python
  repository. A `package.json` with a `package-lock.json` makes a javascript
  one. Python wins when both are there. A `pyproject.toml` without
  `uv.lock`, or a `package.json` without `package-lock.json`, is a NO-GO
  that names the missing file, because the deps gate scans a lockfile. A root
  with neither is a NO-GO that names both.
- **`WORKLOAD_LOCKFILES`.** `uv.lock` or `package-lock.json`, at the root.
- **`WORKLOAD_MUTATION_SCOPE`.** Python: the package named by
  `[tool.hatch.build.targets.wheel].packages`, else the directory named by
  `[project].name` at the root or under `src/`, else the first package at the
  root. Javascript: `src/`, else `lib/`.
- **`WORKLOAD_TEST_ROOT`.** Empty, because the sources sit at the root.
- **`TEST_CMD`.** Python: `uv run --locked pytest tests -q -p no:cacheprovider`,
  with `test/` in place of `tests` when that is the directory, and pytest's
  own discovery when neither exists. The lock is honoured in every case.
  Javascript: `npm ci && npm test` when `package.json` has a `test` script,
  else `npm ci && node --test`.
- **`TOOLCHAIN_IMAGE`.** The runtime the repository declares: `requires-python`
  in `pyproject.toml`, `engines.node` in `package.json`. If the declared range
  admits the workbench's Python 3.13 or Node 24, the draft says `workbench`.
  If it does not, the draft names an image: astral's uv image for the first
  admitted Python (`ghcr.io/astral-sh/uv:python<X.Y>-trixie-slim`), or the
  official node image for the first admitted major, 24, 22, 20 or 18
  (`docker.io/library/node:<major>`). Those are tags. The comment asks you to
  pin them by digest before you commit.
- **`SAST_CMD` and `MUTATION_CMD`.** The stack's runners over the scope, read
  from `.lights-out/runners/`. Their comments say `default:`.
- **`MUTATION_BASELINE`.** Init runs `MUTATION_CMD` once over the whole scope,
  on the same toolchain, and writes the score. A failed run is a NO-GO that
  names the command, and it leaves the key empty. Every mutation gate refuses
  an empty baseline.
- **The plane keys.** Empty in a draft. A repository that already has a
  committed `.lights-out/` keeps its three plane values, and init says so on
  stderr.

### Provenance comments

Every value sits under a comment that says where it came from:

- `# Provenance, inferred: <file>: <evidence>`: read from a file of your
  repository, with the evidence it was read from.
- `# Provenance, default: ...`: a platform default, such as the runners or an
  empty plane key.
- `# Provenance, measurement: ...`: `MUTATION_BASELINE`, with the date, the
  commit, the command, the mutant count, the kill count and the wall time.
- `# Provenance, kept: ...`: a plane key kept from a committed contract.

### Copy, edit, commit

1. Read `.attached/.lights-out/`. Each provenance line says where its value
   came from. Change what is wrong: the scope, the test command, the
   toolchain, and the baseline's command if it is not yours.
2. Copy `.attached/.lights-out/` into the root of your repository, then commit
   it.
3. Run `./go attach ~/code/your-repo`, not `init`, and then `./go gates`. That
   judges your committed contract. `./go init` drafts again in the clone, so
   it replaces the contract you just committed there. Your repository is not
   touched.

`./go attach` refuses while `.attached/.lights-out/` holds a draft you have not
copied out. `./go detach` drops it.

### Without cloning lights-out: the wrapper

The gates half also runs from the `lights-out` wrapper, with no clone of
lights-out. The host needs podman or docker, and git.

The image is `ghcr.io/nicolaguglielmi/lights-out:0.2.0`, public, for amd64
and arm64. Install the wrapper of the same version:

```sh
mkdir -p ~/.local/bin   # any directory on your PATH
curl -fsSL -o ~/.local/bin/lights-out https://raw.githubusercontent.com/nicolaguglielmi/lights-out/v0.2.0/lights-out
chmod +x ~/.local/bin/lights-out
```

Tags are mutable and the image is unsigned. To pin it, set
`LIGHTS_OUT_IMAGE=ghcr.io/nicolaguglielmi/lights-out@sha256:d647d0555ce8dbfb622da35f068a8883af8fcd0366d07beb0a7eb53e22aa3631`.
From a clone of lights-out, `./go package` builds
`localhost/lights-out:dev` instead, for `LIGHTS_OUT_IMAGE`.

Then, in your repository:

```sh
lights-out doctor
lights-out init
cp -R ~/.local/state/lights-out/your-repo/.lights-out/. .lights-out/
git add .lights-out && git commit -m "add lights-out contract"
lights-out gates
```

- `init` writes the draft to `~/.local/state/lights-out/<repo name>/.lights-out`
  and prints the path. `LIGHTS_OUT_OUT` moves it. It is never written into
  your repository. Keep the `/.` in the `cp` command: a plain `cp -R` into
  an existing `.lights-out/` nests the draft inside it.
- `gates` judges the last commit, or `BASE=<ref> HEAD=<ref>`. `STAGED=1`
  judges what is staged as one commit. In 0.3.0, name the head by branch or
  id, or leave it out: `test-proof` reads a name relative to HEAD
  (`HEAD=HEAD`, `HEAD=HEAD~1`) from the base's worktree and answers NO-GO.
  Fixed after the tag, in the next version.
- `triage ALERT=<file>` and `postmortem INCIDENT=<file>` also work. At L0
  they replay only lights-out's own recordings, so on your alerts and
  incidents use `PROFILE=l1` and the key in your environment.
- Keys are read from the environment by name, never from `.env`. Your
  repository is mounted read-only. The engine socket is never given to the
  image.
- Only `TOOLCHAIN_IMAGE=workbench` works through the wrapper. A `compose:` or
  image form gets a NO-GO that names the socket. Judge it from a clone with
  `./go gates`.
- A range is judged by the contract at its base (`workload.env`,
  `policy.env`, `runners/`), so a change cannot loosen what judges it.
  With no contract at the base, the head's own judges, and the wrapper says
  so on stderr.
- The plane (`./go demo`, canary, rollback) stays the clone path.

## 2. The plane half

The plane half is what `./go up`, smoke, verify, release and `demo-gates`
need. Nothing in it is drafted. A lockfile cannot tell lights-out how your
services start, where health is, or which flag turns a feature off, and a
guessed file would be a hidden mock. `./go up` refuses a contract without
`compose.yaml` and names it. `compose:` in `TOOLCHAIN_IMAGE` needs it too.

| File | What it is |
|---|---|
| `compose.yaml` | Your services, merged into the plane's. `${WORKLOAD}` is your repository's root: use it as the build context. A service with profile `test` is what `compose:<service>` names. Services the worker needs (Postgres, say) are declared once under `x-crew-worker` and applied to the four worker services, `gemini-cli`, `claude-code`, `codex` and `antigravity-cli` (ADR 0041 §11, 0050; `./go ci` checks it) |
| `flags/flags.json` | `release-freeze`, plus your kill switch, on for `CANARY_VERSION` |
| `smoke.sh`, `load.sh` | The happy path through `$APP_URL`; traffic until killed |
| `crew-prepare.sh` | Optional: prepares the worker's checkout |
| `fixtures/gates/<name>/` | At least one: a `git format-patch` against your repository and the verdict you expect |

The worker's services go under one anchor, so every harness gets them:

```yaml
x-crew-worker: &crew-worker
  depends_on: [crew-db]
  environment:
    DATABASE_URL: postgresql://app:app@crew-db:5432/app

services:
  # The worker's own database, never the one your app runs on (ADR 0046 §6).
  crew-db:
    image: <the same pinned image as your app's database>
    profiles: ["crew"]
    networks: [crew]
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
  gemini-cli: *crew-worker
  claude-code: *crew-worker
  codex: *crew-worker
  antigravity-cli: *crew-worker
```

A harness sits on the internal `crew` network, with one way out: the `egress`
proxy, which opens only its provider's host (ADR 0046). A service a harness
depends on must be on `crew` only (`networks: [crew]`, as `crew-db` above):
give the worker its own copy, never the service your app uses, which sits on
the plane's network with a route out. `./go ci` checks the rendered project.

Optional `crew-egress.txt` in the contract: one `name:port` per line, for
hosts the worker may reach besides its provider, such as
`pypi.org:443`. The default is none, so `uv sync` fails without it. The plane
reads it from the contract, never from the worker's workspace, and a change
to it is high risk. Each host you list is an open channel for an injected
instruction. Do not list `registry.npmjs.org`, or any host that accepts
uploads, without reading why: `npm publish` with an injected token sends
anything out through it.

The rest of the port is ADR 0030 §3: three compose services (`backend`,
`backend-canary` with profile `canary` and image `${CANARY_IMAGE}`, and
`backend-test` with profile `test`), and `GET /healthz` and `GET /metrics`
on `:8000`. ADR 0042 amends the runners part of §3. `SAST_CMD` and
`MUTATION_CMD` name whatever runners you have. `workloads/minimal/` keeps its
two in `tests/sast/run.sh` and `tests/mutation/run.sh`, in its test image.

### Attach it and prove the plane on it

```sh
./go attach ~/code/your-repo
```

`attach` clones your repository's `HEAD` into `.attached/`. With a committed
`.lights-out/` it checks the contract. Without one it says so, and `./go init`
drafts one. `./go mutation-baseline` measures the whole-scope score again on
the clone, for a later commit or when the suite or the tool changes. Put the
score into `MUTATION_BASELINE`, with a comment saying when, at which commit and
with which tool version, then commit it and attach again. On a legacy codebase,
the baseline is whatever you have today, not a target. Then:

```sh
./go down
./go up
./go smoke
./go verify
./go demo-rollback
./go demo-gates
```

These are the steps `./go demo-seam` runs for `workloads/minimal/`. When the
last two answer GO, a failing canary of your code rolls itself back, and your
fixtures get the verdicts you declared. `./go detach` makes the bundled app
the workload again. `./go demo` refuses to run while a repository is attached.

### Bringing merged changes home

At L0 and L1 the code host is the Gitea inside the plane, which holds a copy
of your attached commit as `lights-out/workload`. A change the tower merges
lands there, not in your repository. Fetch it before the next `./go assign`,
`./go up` or `./go down`: Gitea has no volume, and every assign mirrors your
attached commit again.

```sh
git -C ~/code/your-repo fetch http://localhost:3000/lights-out/workload.git main
git -C ~/code/your-repo merge FETCH_HEAD
```

With the GitHub code host the PR lands on your repository instead, and
this step is replaced by the next section.

### Your PR on GitHub (L1)

Implemented in M21 (ADR 0043) and not yet run end to end: the session that
built it had no token. The code host's eight verbs are checked by
`./go codehost-conformance`, on Gitea on every push and on GitHub nightly
once the owner of lights-out has set a throwaway repository. GitHub is
chosen for an attached repository only. `./go demo` and the bundled app
stay on Gitea.

1. Make a throwaway GitHub repository from `workloads/minimal`. It carries
   `.lights-out/` and a small ticket, `.lights-out/tickets/0001.md`
   (`GET /version`). Clone it locally.
2. Create a fine-grained personal access token at github.com, Settings,
   Developer settings, Fine-grained tokens. Set "Only select repositories"
   to that one repository. Grant Contents, Pull requests and Commit
   statuses, each read and write. Metadata read comes with them.
3. Put `GITHUB_REPO=<owner>/<name>`, `GITHUB_TOKEN` and `GEMINI_API_KEY` in
   `.env`. Do not put `CODE_HOST` there: it goes on the command line,
   because in `.env` it would also redirect `./go demo`.
4. Run:

```sh
./go attach ~/code/your-clone
./go e2e CODE_HOST=github PROFILE=l1
```

The PR opens on GitHub and gets the `gates` status. After GO it is merged
with the merge method `merge`, pinned to the head the gates judged. The
merge is built, signed and released on the local plane, the canary
(`CANARY_VERSION` 0.2.0-outage) rolls back, and the audit cross-checks
GitHub.

The token goes to curl on stdin and to git through a credential helper that
lights-out sets as environment config. It is in no command line, no
`.git/config` and no model container.

**After every merge, pull and attach again.** Each merge moves your default
branch. The next `assign` checks that the attached clone's HEAD equals the
default branch head on GitHub and refuses otherwise:

```sh
git -C ~/code/your-clone pull
./go attach ~/code/your-clone
```

Limits. The repository must allow merge commits, because the judged head
must be the merge's second parent. If you make `gates` a required status
check with "require branches to be up to date", GitHub refuses the merge
and the ticket stops with that reason. A merge commit can contain commits
from your default branch that no gate judged; only the canary judges the
merge.

## 3. Your thresholds: `policy.env`

`policy/merge.env` holds lights-out's defaults. `.lights-out/policy.env`
overrides any of nine of them: `MUTATION_MARGIN`,
`RISK_SIZE_MEDIUM_LINES`, `RISK_AUTO_MERGE_LEVELS` (`low`, `medium`; never
`high`), `RISK_HIGH_MIGRATIONS`, `RISK_HIGH_AUTH`, `RISK_HIGH_PAYMENTS`,
`ERROR_RATE_MAX_DELTA`, `LATENCY_P95_MAX_DELTA` and `MUTATION_BASELINE`.

```sh
# Provenance, decision: our only authentication module; every change to
# it gets a human review.
RISK_HIGH_AUTH=src/auth/*
```

- Every key sits under a `# Provenance, measurement:`, `# Provenance,
  external:` or `# Provenance, decision:` line.
- An unknown key, a malformed value or a missing provenance line is a
  NO-GO that names the key, in every gate that reads the policy.
- An override looser than the default is applied and reported on stderr.
- The three `RISK_HIGH_*` lists are empty by default: lights-out cannot
  know where your migrations, authentication and payments live. Declare
  them, or a change to them is judged on size alone.
- A PR is judged by your base branch's `policy.env`, `workload.env` and
  `runners/`, never its own. Anything under `.lights-out/` is high risk: it goes to
  review, whatever `RISK_AUTO_MERGE_LEVELS` says.

## 4. Tickets and a real agent run

One file per ticket in `.lights-out/tickets/`, with acceptance criteria
written as Given/When/Then and a `## Perimeter` section listing the paths
the change may touch. A diff outside the perimeter is refused before a PR
exists (ADR 0021 §5). `tickets/0005.md` in lights-out is a complete
example.

A real agent run needs L1 and a Gemini API key in `.env` (see
`.env.example`):

```sh
./go assign TICKET=<id> PROFILE=l1
```

The dev-worker reads the ticket, then your `worker.md`. Its toolchain is
your `TOOLCHAIN_IMAGE` when that names an image, and the workbench otherwise
(ADR 0042 §8).

## 5. Before a commit and on a PR

### The Action

`action.yml` at the root of lights-out runs the wrapper on a pull request and
posts one check run, `lights-out gates`, with the GO or NO-GO line as its
title.

```yaml
permissions:
  contents: read
  checks: write
steps:
  - uses: actions/checkout@v7
    with:
      fetch-depth: 0
  - uses: nicolaguglielmi/lights-out@v0.3.0
```

- **The check run's summary** has one line per gate, the gates that did not
  run ("not run: stopped at the first NO-GO"), and for a NO-GO the first 20
  lines of that gate's details, such as the surviving mutants or the file
  outside the perimeter. The same summary goes to the job's step summary.
- **The `gates` input** is `all` (the default, the eight gates),
  `test-proof` or `test-integrity`. `test-proof` runs the tests, then checks
  that the tests a change adds or changes fail on its base.
  `test-integrity` runs test-weakening, then mutation on the changed lines.
- **Two standalone Actions** run one of those each:
  `nicolaguglielmi/lights-out/actions/test-proof@v0.3.0` and
  `nicolaguglielmi/lights-out/actions/test-integrity@v0.3.0`. Their sources
  are `actions/test-proof/` and `actions/test-integrity/`. Each also has a
  repository of its own for its Marketplace page, with a copy at the same
  version: `nicolaguglielmi/test-proof@v0.3.0` and
  `nicolaguglielmi/test-integrity@v0.3.0`.
- Linux runners only. The Action needs docker.
- A fork PR's token cannot write checks. The post is skipped with a warning,
  and the job status still carries the verdict.
- A private package needs `docker login ghcr.io` before the Action.
- The images are signed keyless; tags are mutable. To pin, set the `image`
  input to a digest. The check is in [the README](../README.md#1-gates-on-your-repository).
- Up to v0.2.0 the path was `nicolaguglielmi/lights-out/action@<tag>`. Those
  tags keep it.
- **Proven on one outside repository**,
  [the probe](https://github.com/nicolaguglielmi/lights-out-probe/pull/1): with
  `@v0.3.0` published, the check in 27 s, first pull included (`test-proof`
  14 s, `test-integrity` 25 s, each in a job of its own). In lights-out's own
  workflow it runs with `uses: ./` on a scratch repository (a GO and a NO-GO
  check run).

### Hook recipes for coding agents

A hook runs the gates on the staged changes before an agent commits. These
are recipes to copy, not files lights-out writes into your repository. Each
runs one `sh -c`: exit 0 unless the hook's stdin contains `git commit`, else
the gates, and exit 2 on a NO-GO. Exit 2 is the deny all three CLIs read
(ADR 0041). There are two variants.

- **`--light`, seconds, no engine** (ADR 0061). `lights-out-gates --light
  STAGED=1` runs the gates that need only git and Python: risk and
  test-weakening, perimeter and spec with `TICKET=<file>`, test and
  test-proof with `TEST_ON_HOST=1`. Its line names the gates that did not
  run, and it never says `GO: gates`: secrets, deps, sast and mutation need
  the image. It runs no code of your repository unless you add
  `TEST_ON_HOST=1`, and writes nothing into it. Timeout 30 s: three times
  the 10 s the light tier is held to (ADR 0061 §8). With `TEST_ON_HOST=1`
  your suite runs once on the head and, when tests changed, once on the
  base: raise the timeout by that.
- **The full gates, from the image**: `lights-out gates STAGED=1` with the
  wrapper (section 1), timeout 300 s. Without an engine, the hook exits 2.

Install the light tier once. It is a Python package, standard library only,
Python 3.11 or later:

```bash
uv tool install lights-out-gates
```

`pipx install lights-out-gates` works too, and `uvx lights-out-gates --light
STAGED=1` in the hook needs no install at all. PyPI refused the name
`lights-out`, too close to an existing project, so the package and its
command are `lights-out-gates`, the name of the gates image (ADR 0061,
amendment 2026-11-09); the image wrapper keeps `lights-out`. **Not on PyPI
yet**: until the owner publishes it, install it from the repository:

```bash
uv tool install git+https://github.com/nicolaguglielmi/lights-out
```

**Verified on 2026-11-08, once per CLI.** Each recipe below ran against the
pinned CLI in its own image (`adapters/<cli>/`, built on the workbench), with
the settings file where the recipe says, the wheel installed with `uv tool
install`, and the scripted model of `./go harness-conformance`
(`gates/harness-conformance/stub.py`) in place of the vendor. Two runs each,
on a scratch repository with a `.lights-out/` contract. A staged change that
removes an assertion: the hook exited 2, the CLI blocked `git commit`, the
model received the `NO-GO: gates-light — test-weakening: …` line as the
tool's error, and no commit landed. A clean staged change: the commit
landed. What this does not cover is said under each CLI. The full variant
was not run against the CLIs.

**Claude Code** (verified, 2.1.311), `.claude/settings.json` in the
repository (also `.claude/settings.local.json` or `~/.claude/settings.json`).
`PreToolUse`, matcher `Bash`; the command is in `tool_input.command` on
stdin; `timeout` is in seconds. Verified with the project file and `claude
-p`: the model got `PreToolUse:Bash hook error: […] NO-GO: gates-light — …`.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "sh -c 'if grep -q \"git commit\"; then lights-out-gates --light STAGED=1 >&2 || exit 2; fi'",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

**Codex** (verified, 0.166.0), `~/.codex/hooks.json` or `.codex/hooks.json`
in the repository. `PreToolUse`, matcher `*`; `timeout` is in seconds. The
matcher stays `*`: the recipe relies on the `git commit` test. Verified with
the user-level file under `CODEX_HOME` and `codex exec
--dangerously-bypass-hook-trust --enable hooks`: the model got `Command
blocked by PreToolUse hook: … NO-GO: gates-light — …`. **Not verified:** the
project file `.codex/hooks.json`, and the trust step. Codex runs a hook only
once you trust it with `/hooks`; the run bypassed that.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "sh -c 'if grep -q \"git commit\"; then lights-out-gates --light STAGED=1 >&2 || exit 2; fi'",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

**Gemini CLI** (verified, 0.61.0-preview.0), `~/.gemini/settings.json` or
`.gemini/settings.json` in the repository. `BeforeTool`, matcher a regex on
the tool name, here `run_shell_command`. `timeout` is in **milliseconds**
and the default is 60000: 30000 here. Verified with the user-level file,
`gemini -p --skip-trust --approval-mode yolo`: the model got `Tool execution
blocked: … NO-GO: gates-light — …`. **Not verified:** the project file in
a folder Gemini CLI does not trust.

```json
{
  "hooks": {
    "BeforeTool": [
      {
        "matcher": "run_shell_command",
        "hooks": [
          {
            "type": "command",
            "command": "sh -c 'if grep -q \"git commit\"; then lights-out-gates --light STAGED=1 >&2 || exit 2; fi'",
            "timeout": 30000
          }
        ]
      }
    ]
  }
}
```

For the full variant, replace the command's `lights-out-gates --light
STAGED=1` with `lights-out gates STAGED=1` (the wrapper) and the timeout
with 300 (Gemini CLI: 300000).

Limits:

- The hook matches text. `git -C x commit`, an alias, or a script that
  commits are not seen.
- `git commit -a` stages inside the commit, so the hook judges only what was
  staged before. `--amend` judges the staged diff only.
- The light tier judges the staged diff on the contract HEAD has committed;
  a `.lights-out/` that is only staged does not judge it.
- The full variant's every run is cold: the dependencies are reinstalled
  each time.
- What a CLI does when a hook times out was not verified.
- The Action is the real gate. The hook is a convenience, and the light tier
  is not the judge.

## When something does not fit

Open an issue saying which step failed, what `./go init` or `./go gates`
printed, and what your codebase looks like: language, test runner, how it
starts. The port is young, and every codebase that does not fit it shows
where it needs to grow.
