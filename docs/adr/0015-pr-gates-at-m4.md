# ADR 0015 — PR gates at M4: `make gates` judges a git range; tests run as they are; mutation is cosmic-ray on the lines the PR changed, against a measured threshold; bandit and osv-scanner; fixture PRs in worktrees prove both verdicts; gates stay out of `demo`; the runner socket is decided, and lands at M5

- Status: accepted (amends ADR 0004 consequences [Testcontainers note void], ADR 0010 §6, ADR 0012 consequences [runner socket]; amended by ADR 0017 §7 [socket and first Gitea job move to M6]); amended by ADR 0019 §4 [runner socket and first Gitea job move to M8]; amended by ADR 0025 §4 [the socket lands at M8 under §7's three unchanged conditions, and the first job is the image build on `main`, not the `pull_request` gates job — that one goes to the milestone that runs the tower on GCP]
- Date: 2026-09-14
- Milestone: M4

## Context

M4 (plan §7): unit, integration, contract, mutation testing with a
threshold, SAST, dependency scan, secret scan, and risk scoring (ADR 0016).
Done when a PR with a fake test is rejected by the mutation score and a PR
touching a migration is marked high risk and not auto-merged. Decisions
already taken by the owner: a "PR" at M4 is a git range `BASE..HEAD` on the
local clone, proven by `./go demo-gates` on committed fixture patches applied
in throwaway worktrees; integration tests stay on compose Postgres (ADR 0010,
no Testcontainers; plan §7 gets a dated note); the fixtures are ticket 0001's
fix with a real test, the same fix with a fake test, and a PR adding a
migration; ticket 0001 stays open on main. Facts verified 2026-09-14 are
cited inline. Gates are sh under the ADR 0002 contract; `ci/contract.sh`
cold-runs every `gates/*.sh`, so each must answer in one line with no plane.

## Decision

1. **Tools, versions, where each installs.** Two Python tools join the
   app's dev group in `app/backend/pyproject.toml` + `uv.lock` and run inside
   the `test` image over the compose Postgres, the same install path as
   pytest (ADR 0010 §4): `cosmic-ray==8.7.0` (PyPI 2026-08-09, MIT,
   classifiers up to 3.13) and `bandit==1.9.4` (PyPI 2026-02-25, Apache-2.0,
   pure Python). One Go binary joins workbench with per-arch sha256 `ARG`s
   through `fetch.sh` (ADR 0004 §1): `osv-scanner v2.6.0` (GitHub release
   2026-09-14, `osv-scanner_linux_{amd64,arm64}` 57.5/53.6 MB,
   `osv-scanner_SHA256SUMS`). Nothing else: gitleaks 8.30.1, pytest 9.1.1,
   python3 3.13, jq and git are already there. Unit + integration + contract
   tests are the existing `./go test` (ADR 0010 §4, ADR 0006 §4): one pytest
   run, unchanged.
2. **`make gates BASE=<ref> HEAD=<ref>` runs the PR gates in order, cheap
   to expensive, stops at the first NO-GO:** `risk` (ADR 0016), `secrets`
   (`ci/secrets.sh` as it is: history plus working tree already cover the
   range), `deps`, `sast`, `test`, `mutation`. Every `gates/*.sh` starts by
   requiring `BASE` and `HEAD` and NO-GOs in one line without them — what
   `ci/contract.sh` sees cold, and what keeps a cold run instant even inside
   `demo`, where workbench has the socket and a real `docker-compose run`
   would otherwise start. The effective base is `git merge-base BASE HEAD`
   (the PR's own changes, as a code host shows them; equal to `BASE` for the
   fixtures). Gates write data beyond the verdict to `$GATES_OUT/<gate>.json`
   (`GATES_OUT ?= .gates-out`, gitignored): `risk.json`, `mutation.json`.
   The target ends with `GO: gates — risk <level>, <decision>` or
   `NO-GO: gates — <gate>: <reason>`, the `make ci` shape. `gates`,
   `demo-gates` and `mutation-baseline` join the socket list in `go`; the
   plane need not be up (`run backend-test` starts Postgres itself).
3. **Mutation gate: cosmic-ray, scoped to the lines the PR added or changed
   in `app/backend/meetups/`.** `gates/mutation.sh` parses
   `git diff -U0 <base> HEAD -- app/backend/meetups/` hunks into
   `meetups/<file>=<start>-<end>,...` (the `app/backend/` prefix is dropped
   because the Containerfile `COPY`s the package to `/app/meetups`), passes
   it as `MUTATION_LINES` into `docker-compose --profile test run --rm
   --build backend-test sh tests/mutation/run.sh`. In the container:
   `cosmic-ray init` on `module-path = "meetups"`, cosmic-ray's own
   `cr-filter-lines` fed a `[cosmic-ray.filters.line-filter.lines]` table
   built from `MUTATION_LINES` (skipping it when the value is `all`),
   `cr-filter-pragma` (`# pragma: no mutate` is the reviewable escape hatch
   for an equivalent mutant), `cosmic-ray baseline` (the unmutated suite must
   pass, so a red suite can never read as "every mutant killed"), `exec`
   with `test-command = "python -m pytest tests -q -x -p no:cacheprovider"`,
   sequential local distributor (the suite shares one database), then
   `cosmic-ray dump` piped to `tests/mutation/score.py` (stdlib) which prints
   one JSON line. Config in `app/backend/tests/mutation/cosmic-ray.toml`,
   already inside the test image via `COPY backend/tests`. Operators: the
   defaults minus the `Is`/`IsNot` comparison variants, the exclusion the
   upstream filters page uses as its own example (`==` → `is` on ints and
   strings is a warning, not a test-quality signal). `timeout` (seconds per
   test run): 10 × the clean-run time measured at M4 close, written in the
   TOML with that provenance. **Score** = killed / (killed + survived) over
   mutants on changed lines; timeouts count as killed (the mutant changed
   behaviour observably), incompetent mutants (code that no longer imports)
   are excluded (they say nothing about the tests), skipped ones are not in
   the population. **Threshold = `MUTATION_BASELINE − MUTATION_MARGIN`**,
   both in `policy/merge.env` (ADR 0016 §6). `MUTATION_BASELINE`,
   provenance measurement: the same runner with `MUTATION_LINES=all`
   (`./go mutation-baseline`, a target, not a gate) over the whole package on
   main at M4 close, recorded in the policy file with commit, date, tool
   version, mutant count and wall time, and in HANDOFF; re-measured only by
   a dedicated commit when the suite or the tool changes. `MUTATION_MARGIN =
   0.10`, provenance decision: one score quantum of the smallest fixture (the
   honest fix yields roughly ten mutants on its changed lines, so one
   equivalent survivor costs about 0.1); if the baseline comes out so high
   that the threshold exceeds 0.80, the implementer stops and re-derives the
   margin as `1/N` of that fixture, recording it. Why lines, not functions:
   on `geocode()` about six of its sixteen existing mutants already survive
   (the fake ignores `format` and `limit`; no contract example returns 5xx),
   so a function-scoped score puts the honest fix near 0.67 and the fake-test
   PR near 0.56 — one mutant apart; line-scoped, they sit near 0.9 and 0.0.
   **Nothing to mutate** (no changed line under `app/backend/meetups/`, or
   changed lines that yield no mutant): stdout `GO: mutation`, stderr
   `mutation: 0 mutants on changed lines in <base>..<HEAD>; GO by absence of
   subject, nothing ran`, `mutation.json` records `total: 0, score: null`.
   Nothing is simulated; a docs or migration PR is not asked to prove Python.
   NO-GO reason: `NO-GO: mutation — 0/9 mutants on changed lines killed
   (0.000 < 0.550); survivors on stderr`, each survivor as
   `file:line operator`, which is what an M5 worker needs to write the
   missing test. Runtime, estimates until M4 measures them: the honest fix
   about ten mutants at ≤ 6 s each plus one clean run and one image build,
   under 2 min; a 50-line backend change about 5 min; the whole-package
   baseline 20–45 min, once.
4. **SAST: `gates/sast.sh` = `docker-compose run --rm --no-deps backend-test
   bandit -r meetups -q`**, any finding is NO-GO, `# nosec <reason>` is the
   escape hatch. Scope is the shipped package; `tests/` (B101 on every
   `assert`) and `fakes/` are not scanned and the README says so. No
   severity floor: a floor is a number without provenance, and per-finding
   review is what the escape hatch is for. The frontend gets no SAST at M4
   (React/Vite/TS, no tests until M11, static bundle); declared.
5. **Dependency scan: `gates/deps.sh` = `osv-scanner scan source -L
   app/backend/uv.lock -L app/frontend/package-lock.json`** in workbench, no
   engine, network to api.osv.dev; exit 1 (vulnerabilities) is NO-GO, any
   other non-zero is NO-GO with the tool's error. Both lockfiles whole,
   dev tools included (they run in the build and test chain). Determinism
   caveat, stated: the input is pinned, the advisory database is not — the
   same commit can go from GO to NO-GO overnight, and the fix is a bump or
   an `osv-scanner.toml` `[[IgnoredVulns]]` entry with `id` and `reason`,
   created only when first needed.
6. **`demo-gates` proves both verdicts on six fixtures.** For each
   `gates/fixtures/<name>/`: `git worktree prune`, `git worktree add
   --detach <mktemp -d>/wt HEAD`, `git -c user.name=lights-out-fixtures -c
   user.email=fixtures@lights-out.invalid am <name>/*.patch`, then
   `$(MAKE) -C <wt> gates BASE=<HEAD sha> HEAD=<wt sha>` with stdout
   captured; assert the lines and `.gates-out/*.json` against
   `<name>/expect` (KEY=VALUE); `git worktree remove --force` in a trap.
   Fixtures, format `git format-patch` (a real commit with author and
   message, applied by one command; a plain diff needs a second step and
   loses the message): `honest-fix` — ticket 0001 resolved as "404 is no
   result: 201 with null coordinates" (mirrors Nominatim's `200 []`), the
   contract example, the fake unchanged, a client test that posts an unknown
   venue and asserts `(None, None)`, one README sentence; expects every gate
   GO, risk `low`, decision `auto-merge`, `mutation.json` total > 0. This is
   the **positive control**: a mutation gate wired to always NO-GO, or a
   risk model that never says low, fails here, not in a talk (the ADR 0014
   lesson). `fake-test` — the same fix, the test replaced by one that claims
   the case but never reaches the new lines (it posts the venue the existing
   `200 []` example already covers); expects NO-GO from `mutation` exactly,
   with `test` GO before it. Not an assertion-free test that calls the new
   code: such a test kills every crash-type mutant, which for this fix is
   most of them — mutation testing measures whether tests observe the lines,
   and a test that never runs them is the realistic failure. `migration` —
   adds `app/backend/migrations/0004_fixture_registrations_waitlisted.sql`
   (`ALTER TABLE registrations ADD COLUMN waitlisted boolean NOT NULL DEFAULT
   false`), no Python; expects every gate GO, `mutation.json` total 0, risk
   `high`, decision `review`. Three more fixtures, one per remaining gate, because a gate
   that has never been seen failing is not a gate (`.claude/agents/gate-writer.md`;
   owner decision 2026-09-14): `sast-finding` — one obvious bandit finding
   added to `meetups/app.py`; expects NO-GO from `sast`, risk `low`.
   `vulnerable-dep` — a known-vulnerable entry added to
   `app/frontend/package-lock.json`; expects NO-GO from `deps`.
   `failing-test` — one failing assertion added under `tests/`; expects
   NO-GO from `test`, risk `low`. Location `gates/fixtures/`, not `fixtures/`:
   plan §6 reserves `fixtures/` for recorded model responses; these are
   inputs to a gate's proof. `contract.sh` and `ci/shell.sh` glob `*.sh`, so
   `.patch` and `expect` files are inert. Base is the checkout's `HEAD`, so
   the range is one commit and works on a detached CI checkout.
7. **Workflow: one added job `gates`, `runs-on: ubuntu-latest`, `if:
   github.server_url == 'https://github.com'`, `run: ./go demo-gates`,
   `CONTAINER_ENGINE=docker`** — the `engine-compat` shape (ADR 0012 §5).
   The Gitea runner does not get the engine socket at M4. **Decided now, for
   M5:** the socket goes into the `runner` service (`label=disable`,
   `DOCKER_HOST`, the path `./go` already computes) in the milestone that
   pushes the first job to Gitea, under three conditions: the runner is the
   only compose service with the socket; jobs run only on refs the workbench
   user pushed (no fork PRs, no external webhooks); the README's L0
   trusted-network line gains "and the Gitea runner controls your container
   engine". Trade-off, in one paragraph: host mode means the job *is* the
   runner container, so the socket makes every job — from M5, jobs an agent's
   PR triggers — root-equivalent on the machine running the plane; a PR that
   edits `gates/test.sh` runs with the power to mount `/`. GitHub has the
   same power on a disposable VM; L0/L1 is the developer's laptop, rootless
   podman's account and every file it reads, `.env` included. The mitigations
   that matter (gate scripts taken from the base ref, a second engine,
   docker-mode job containers without the socket) all depend on how the
   CodeHost adapter triggers jobs, which is M5's design; mounting now would
   be unexercisable code until then (ADR 0012's own objection to a red
   GitHub leg). Running the gates on this repo's own pushes (`pull_request`
   with `base.sha..sha`) is also M5's, when PRs exist.
8. **`gates` does not join `./go demo`.** ADR 0003's stage list is a
   promise; plan §2's 900 s measures the path to the rollback, which the
   gates are not on until M6's `e2e` (ticket → PR → CI → canary → rollback)
   carries them as that stage already foresees. `demo-gates` is the M4
   acceptance command, run manually and by the GitHub job on every push,
   the `demo-hold` precedent (ADR 0014). Warm estimate 4–5 min (three image
   builds, two mutation runs); measured at M4 close, recorded in HANDOFF, no
   ceiling binds.
9. **Amendments.** ADR 0010 §6 said `uv lock --check`, ruff and `npm audit`
   belong to M4: `uv lock --check` is replaced by `uv sync --locked` in both
   stages of `app/backend/Containerfile` (a stale lock now fails every
   build, no gate needed; `--frozen` skipped the check); `npm audit` is
   subsumed by §5; ruff is not a merge gate and is not in the milestone
   text — it arrives, as a `ci` check, the first time style blocks a review
   (M5 at the earliest). ADR 0004's Testcontainers rootless facts are void.
   Plan §7 M4 gets the dated note the owner asked for.

## Alternatives rejected

- mutmut 3.8.0 (PyPI 2026-09-12, BSD-3): the faster tool (per-mutant test
  selection, in-process) and fewer dependencies, but its unit is the
  function — mutants are keyed `module.function__mutmut_N`, no line is
  persisted, `mutate_only_covered_lines` measures coverage itself — and the
  arithmetic in §3 shows function scope cannot separate the two fixtures
  reliably. Its `fork` model also loses the flagd provider's file-poll
  thread in every child, so `test_flags.py` fails under every mutant it
  touches (false kills); `forkserver` with `warmup = "none"` avoids that at
  the cost of the speed advantage.
- Mutation scope = whole package per PR: 20–45 min per PR, and a score that
  moves with code the PR never touched.
- Threshold tuned to the fixtures, or fixed at 100 %: the first is circular,
  the second makes one equivalent mutant a NO-GO with no provenance for why.
- A home-grown mutator on diff lines: the operator set is the tool.
- semgrep 1.177.0 (LGPL-2.1): bundles a native engine, its rule packs come
  from a registry over the network under their own terms, and the app is
  420 lines of Python; bandit is Apache-2.0, offline, and readable.
- pip-audit 2.10.1 + `npm audit`: two verdict formats, two ignore
  mechanisms (npm has none without a third tool), pip-audit audits a venv
  rather than the lockfile; osv-scanner is one binary, both lockfiles, one
  per-ID ignore with a reason field, and the workbench pin pattern.
- trivy v0.74.0: 50/45 MB tarball plus a vulnerability database download per
  run; scans images we do not gate at M4.
- SAST and mutation as workbench Python tools: a second lockfile
  (`requirements.txt --require-hashes`) to keep the sha256 guarantee; the
  app's `uv.lock` already gives it, and the socket is needed by `test` anyway.
- Testcontainers: owner decision; ADR 0010 §4 already runs the suite on
  compose Postgres with the same command locally and in CI.
- `fixtures/` for the patches: plan §6 reserves it for model responses; when
  M5's replay adapter records ticket 0001's PR there, `demo-gates` reads it
  from there instead of keeping `honest-fix`.
- Plain diffs + `git apply` + a synthetic commit: one more step, no message.
- Socket into the runner now with a `ready.sh` proof: a socket file present
  is not a job that works; unexercisable until M5.
- `gates` as a `demo` stage: a plan change and 4–5 min inside a budget that
  measures something else.
- `risk` NO-GO on high: see ADR 0016.

## Consequences

- The test image grows by cosmic-ray's tree (aiohttp, sqlalchemy,
  gitpython, rich; ~50 MB); never shipped, and an advisory on any of them
  turns `deps` red although the app does not ship it — the ignore-with-
  reason entry is the answer, and the README says the scan covers the
  build-and-test chain, not only the runtime.
- `deps` is a time bomb by design: `demo-gates` goes red the day an advisory
  lands on a pinned dependency, including on a fixture that changed nothing;
  the fix is a bump. The README carries that line.
- Line scope cannot see deletions (nothing to mutate on a removed line); a
  PR that deletes a check untested by the suite passes `mutation` and it is
  `test`'s job to notice. Stated in the gate's header comment.
- A changed function's untouched, badly tested lines are not scored: the
  gate judges what the PR wrote, not the debt around it; the whole-package
  baseline is where that debt is visible.
- The score's quantum is `1/N`; below ten mutants one equivalent survivor
  can cross the threshold and the reviewable pragma is the way out. An M5
  worker will be tempted to sprinkle pragmas; ADR 0016's platform signal
  does not cover `app/`, so the reviewer must read them.
- `mutation-baseline` is a 20–45 min run on a laptop; it is run once at M4
  close and re-run only by decision. If the measured suite time differs
  much from the ~6 s assumed here, the `timeout` and the runtime estimates
  above are the numbers to rewrite.
- `demo-gates` applies the fixture migration to the plane's `meetups_test`
  database; `registrations.waitlisted` stays there until `down -v`, harmless
  to every current test (explicit column lists), named in the README. The
  patches are coupled to the files they touch: a change to
  `geocoder_client.py` on main makes `git am` fail and `demo-gates` NO-GO
  "fixture does not apply; regenerate", loudly.
- Every `./go ci` now cold-runs five more gates; each answers in
  milliseconds because of the range guard.
- The socket decision is made but not exercised until M5; M5 is not closed
  while the runner lacks it and a Gitea job needs it.
- Plan §8 step 4 expects "medium" for the waitlist PR; under ADR 0016 that
  holds only if the PR carries no migration. Either way the review agent
  starts, which is the step's point.

## Golden-rule check

Stranger with podman, git, sh: `./go demo` is unchanged — no new stage, no
new pull, the workbench gains one 57 MB download at build. `./go demo-gates`
needs no key and no account: two Python packages resolved from the committed
`uv.lock` at image build, one OSV query over the network (NO-GO with the
error if offline, never a fake GO). Passes; the demo budget is untouched
and `demo-gates` is timed at M4 close for the record, not against a limit.
