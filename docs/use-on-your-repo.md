# Use lights-out on your own codebase

The quickstart runs lights-out on the app that ships with it. This guide
puts your code behind the same gates, canary and rollback.

## What is proven and what is not

| | Status |
|---|---|
| A second workload behind the port, end to end (up, smoke, verify, rollback, gates) | Proven: `./go demo-seam` on `workloads/minimal/` (ADR 0030) |
| The platform never names the workload | Proven: `ci/app-free.sh` runs in `./go ci` |
| A codebase that was not written for lights-out | **Not yet proven.** It is the public legacy experiment (plan §14) |

Known limits today, before you start:

- **Your code lives inside a lights-out checkout.** `WORKLOAD` is a path
  from the repository root, so you fork lights-out and add a directory
  under `workloads/`. Pointing at a separate repository is not supported.
- **The worker's toolchain is fixed.** The dev-worker runs Python 3.13 and
  Node 24. The PR gates have runners for Python (cosmic-ray, bandit) and
  for the lockfiles osv-scanner reads.
- **The dev-worker's prompt still describes the bundled app.** M13 moves
  that text into a per-workload `worker.md` (ADR 0031, proposed). Until
  then, a real agent run on another workload starts from the wrong brief.

The path below is the one `./go demo-seam` proves. Steps 5 and 6 on a
codebase from outside this repository are what the legacy experiment
will test.

## 1. Start from the minimal workload

Copy `workloads/minimal/` to `workloads/<name>/`. It is the smallest
thing that satisfies the port: FastAPI, no database, no frontend.
Replace its code with yours and keep its shape.

Every command takes the workload as an argument:

```sh
./go up WORKLOAD=workloads/<name>
```

## 2. Fill in `workload.env`

There are exactly seven keys, and `ci/workloads.sh` rejects an eighth.
Paths are relative to the workload directory.

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

## 3. Satisfy the port

ADR 0030 §3 is the full contract. In short:

- **`compose.yaml`** with three services: `backend` (stable),
  `backend-canary` (profile `canary`, image `${CANARY_IMAGE}`, no build)
  and `backend-test` (profile `test`; its exit code is the test verdict).
  Your database and fakes go here too.
- **HTTP on `:8000`**: `GET /healthz` returns JSON with `version`.
  `GET /metrics` exposes the OpenTelemetry HTTP server histogram
  `http_server_request_duration_seconds` and `target_info` with
  `service_version`. Verify compares canary and stable from these.
- **`flags/flags.json`**: `release-freeze`, plus your kill switch, on for
  `CANARY_VERSION`.
- **`smoke.sh`** (happy path through `$APP_URL`), **`load.sh`** (traffic
  until killed), and optionally `crew-prepare.sh`.
- **`tests/mutation/run.sh`** and **`tests/sast/run.sh`** in the test image.
- **At least one gate fixture** in `fixtures/gates/<name>/`: a patch and
  the verdict you expect for it.

Every file in this list is platform-risk (`RISK_HIGH_PLATFORM` in
`policy/merge.env`). A PR that edits one never merges on its own.

## 4. Measure your baseline

```sh
./go mutation-baseline WORKLOAD=workloads/<name>
```

Write the score into `MUTATION_BASELINE`, with a comment saying when,
at which commit and with which tool version. The mutation gate is a
ratchet: a PR may not lower the score on the lines it touches below the
baseline minus `MUTATION_MARGIN`. On a legacy codebase, the baseline is
whatever you have today, not a target.

## 5. Prove the plane on your workload

```sh
./go ci
./go down WORKLOAD=workloads/<name>
./go up WORKLOAD=workloads/<name>
./go smoke WORKLOAD=workloads/<name>
./go verify WORKLOAD=workloads/<name>
./go demo-rollback WORKLOAD=workloads/<name>
./go demo-gates WORKLOAD=workloads/<name>
```

These are the steps `./go demo-seam` runs for `workloads/minimal/`. When
the last two answer GO, a failing canary of your code rolls itself back,
and your fixtures get the verdicts you declared.

## 6. Declare risk and write tickets

- **Risk.** Put your sensitive paths in `policy/merge.env`
  (`RISK_HIGH_MIGRATIONS`, `RISK_HIGH_AUTH`, `RISK_HIGH_PAYMENTS`). A PR
  touching them goes to review instead of merging on its own (ADR 0016).
- **Tickets.** One file per ticket in `tickets/`, with acceptance criteria
  written as Given/When/Then and a `## Perimeter` section listing the paths
  the change may touch. A diff outside the perimeter is refused before a
  PR exists (ADR 0021 §5). `tickets/0005.md` is a complete example.
- **A real agent run** needs L1, a Gemini API key in `.env` (see
  `.env.example`):

  ```sh
  ./go record TICKET=<id> PROFILE=l1 WORKLOAD=workloads/<name>
  ```

  The run is recorded under `fixtures/`, so anyone can replay it at L0
  without a key.

## When something does not fit

Open an issue saying which step failed and what your codebase looks like:
language, test runner, how it starts. The port is young, and every
codebase that does not fit it shows where it needs to grow.
