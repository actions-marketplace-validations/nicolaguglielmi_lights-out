# Use lights-out on your own codebase

The quickstart runs lights-out on the app that ships with it. This guide
puts your repository behind the same gates, canary and rollback. You keep
a plain clone of lights-out; your repository gets one directory,
`.lights-out/`, and lights-out never writes to it.

## What is proven and what is not

| | Status |
|---|---|
| A repository outside the lights-out checkout, attached, end to end (up, smoke, verify, rollback, gates) | Proven: `./go demo-seam` copies `workloads/minimal/` into a new repository and attaches it (ADR 0036) |
| The platform reads only your `.lights-out/`, and never names your repository | Proven: `ci/attach.sh` and `ci/app-free.sh` run in `./go ci` |
| A PR is judged by your base branch's policy, and a change to `.lights-out/` never merges on its own | Proven: `ci/attach.sh` |
| A codebase that was not written for lights-out | **Not yet proven.** It is the public legacy experiment (plan §14) |

Known limits today, before you start:

- **No recordings of your repository.** Without a key, lights-out replays
  runs recorded on its own app. On an attached repository the crew stops
  at L0 and says so; agents need L1 and a Gemini API key.
- **At L1 the tower stops at release.** It waits for the image that
  lights-out's own Gitea workflow builds from a merge, and your repository
  has no such job. The canary and its rollback are proven on your stable
  image (step 4); a merged change is not yet built and released.
- **The worker's toolchain is fixed.** The dev-worker runs Python 3.13 and
  Node 24. Other stacks are the next milestone (M14).
- **lights-out sees what you committed.** It clones your `HEAD` when you
  attach; run `./go attach` again after a new commit.
- **Your `.lights-out/` scripts run in lights-out's toolchain container**,
  which controls your container engine (README, "What is real"). Attach
  only a repository you would run on this machine.

## 1. Start from the minimal example

`workloads/minimal/` is laid out the way your repository will be: code at
its root, the lights-out contract in `workloads/minimal/.lights-out/`.
Copy that `.lights-out/` into the root of your repository and adapt each
file. It is the smallest thing that satisfies the port: FastAPI, no
database, no frontend.

## 2. What `.lights-out/` holds

| File | What it is |
|---|---|
| `workload.env` | Seven keys, below. Paths are relative to your repository's root |
| `compose.yaml` | Your services, merged into the plane's. `${WORKLOAD}` is your repository's root: use it as the build context |
| `flags/flags.json` | `release-freeze`, plus your kill switch, on for `CANARY_VERSION` |
| `smoke.sh`, `load.sh` | The happy path through `$APP_URL`; traffic until killed |
| `crew-prepare.sh` | Optional: prepares the worker's checkout |
| `fixtures/gates/<name>/` | At least one: a `git format-patch` against your repository and the verdict you expect |
| `worker.md` | The dev-worker's brief: `## Scope` (the paths it may change) and `## Tests` (the exact command, and where to run it) |
| `policy.env` | Optional: your thresholds (step 3) |
| `tickets/<id>.md` | Optional: your tickets (step 5) |

The seven keys of `workload.env` (`ci/workloads.sh` rejects an eighth):

| Key | What it says |
|---|---|
| `CANARY_VERSION` | The version string your flag file targets as the failing release |
| `MUTATION_BASELINE` | Your suite's measured mutation score (step 4) |
| `WORKLOAD_KILL_SWITCH` | The flag that turns the risky feature off |
| `WORKLOAD_SAMPLE_PATH` | One read-only, instrumented `GET` route |
| `WORKLOAD_LOCKFILES` | Lockfiles for the dependency gate, `:`-separated |
| `WORKLOAD_MUTATION_SCOPE` | The source directory the mutation gate reads |
| `WORKLOAD_TEST_ROOT` | The prefix stripped to address lines in the test image (may be empty) |

A key that is empty or names a missing path makes its gate answer NO-GO
and name the key. A typo never turns into a silent GO.

The rest of the port is ADR 0030 §3: three compose services (`backend`,
`backend-canary` with profile `canary` and image `${CANARY_IMAGE}`,
`backend-test` with profile `test`), `GET /healthz` and `GET /metrics` on
`:8000`, and two runners in your test image, `tests/mutation/run.sh` and
`tests/sast/run.sh`, wherever your Containerfile puts its working
directory.

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
- A PR is judged by your base branch's `policy.env` and `workload.env`,
  never its own. Anything under `.lights-out/` is high risk: it goes to
  review, whatever `RISK_AUTO_MERGE_LEVELS` says.

## 4. Attach it and prove the plane on it

```sh
./go attach ~/code/your-repo
./go mutation-baseline
```

`attach` clones your repository's `HEAD` into `.attached/` and checks the
contract. Write the baseline score into `MUTATION_BASELINE`, with a
comment saying when, at which commit and with which tool version, commit,
and attach again. On a legacy codebase, the baseline is whatever you have
today, not a target. Then:

```sh
./go down
./go up
./go smoke
./go verify
./go demo-rollback
./go demo-gates
```

These are the steps `./go demo-seam` runs for `workloads/minimal/`. When
the last two answer GO, a failing canary of your code rolls itself back,
and your fixtures get the verdicts you declared. `./go detach` makes the
bundled app the workload again; `./go demo` refuses to run while a
repository is attached.

## 5. Tickets and a real agent run

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

The dev-worker reads the ticket, then your `worker.md`.

## 6. Bringing merged changes home

At L0 and L1 the code host is the Gitea inside the plane, which holds a
copy of your attached commit as `lights-out/workload`. A change the tower
merges lands there, not in your repository. Fetch it before the next
`./go assign`, `./go up` or `./go down`: Gitea has no volume, and every
assign mirrors your attached commit again.

```sh
git -C ~/code/your-repo fetch http://localhost:3000/lights-out/workload.git main
git -C ~/code/your-repo merge FETCH_HEAD
```

A GitHub code host replaces this step when its adapter lands (M10).

## When something does not fit

Open an issue saying which step failed and what your codebase looks like:
language, test runner, how it starts. The port is young, and every
codebase that does not fit it shows where it needs to grow.
