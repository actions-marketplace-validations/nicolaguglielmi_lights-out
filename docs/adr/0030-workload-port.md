# ADR 0030 — The `Workload` port: a workload is a directory named by `WORKLOAD=<path>` (default `app`) that owes the platform seven keys, three compose services, `/healthz` and `/metrics`, one flag file and two in-image runners; `core/`, `gates/`, `verify/` and `adapters/` may not name it (`ci/app-free.sh`); `workloads/minimal/` proves the seam with `./go demo-seam`

- Status: accepted (amends plan §4 [a `Workload` row; this port is chosen by `WORKLOAD`, not by the profile], §5, §7 M12 and §12 [app-free's scope gains `adapters/`], §6 [`workloads/`]; ADR 0010 §1 [the app's services leave the root `compose.yaml`]; ADR 0011 §2 and ADR 0012 §2 [metric-shape's sample GET and flagd's bind mount follow `WORKLOAD`]; ADR 0013 §6 and ADR 0026 §5 [the one flag file is the workload's; `waitlist` becomes `$WORKLOAD_KILL_SWITCH`]; ADR 0015 §4–§6 [SAST calls an in-image runner; lockfiles and gate fixtures come from the workload]; ADR 0016 §2 [the platform signal covers the workload's gate surface]; ADR 0020 §6 [`ci/prompts.sh`'s hand list]; ADR 0029 §2 [what it left open is fixed here]; consistent with ADR 0024 §1 [a plugin is a directory plus one line])
- Date: 2026-09-23
- Milestone: M12
- Amended 2026-11-02 (owner, ticket 0010 item 2): §5's "the launchpad reads an unanswerable freeze as not frozen" no longer holds. An unanswered `release-freeze`, or an answer other than `true`/`false`, refuses the release: `NO-GO: launchpad — cannot read release-freeze from the Flags port; refusing to release`, rolled back when it happens past staging. A harness for an untrusted codebase fails closed; with flagd down, a freeze that was on used to be ignored.

## Context

ADR 0029 §2 made the meetup app the first workload behind a port and left
this ADR its name, its contract, the second workload and the acceptance.
ADR 0029's count (87 references, 15 files) still holds on 2026-09-23;
§5's wider pattern adds `core/tests/test_risk.py`, `adapters/flagd/set.sh`,
a comment in `core/launchpad.sh` and `roles/dev-worker/prompt.md`. Not
names: envoy-canary reads `/healthz` by running `python3` in the
container, and `ci/prompts.sh`'s drift check needs a gate naming `bandit`.

The trap in the proposal: `MUTATION_BASELINE` (`policy/`), the SAST
command and the gate fixtures (`gates/`) are under `RISK_HIGH_PLATFORM`
today. Moved into a workload unguarded, they would let a PR lower its
own bar and auto-merge, which is what ADR 0016 §2 exists to stop.

## Decision

1. **Name, selection, location.** `Workload`: what the platform operates
   on, not a vendor. A workload is a directory; `WORKLOAD ?= app` in the
   Makefile is its path from the repo root, and `include
   $(WORKLOAD)/workload.env` stops make, naming the file, if it is
   missing. Not the profile's choice: a workload is the same at every
   level. Derived values (`COMPOSE_FILE :=
   compose.yaml:$(WORKLOAD)/compose.yaml`, `FLAGS_FILE`) are `:=` and
   exported, never `?=`: §7 re-enters make with another `WORKLOAD`, and
   `export` hands the parent's values down. *(a) A path.*

2. **`workload.env`: exactly seven keys**, profile syntax, file paths
   relative to the workload (the gates prefix `$WORKLOAD/`, so the app's
   resolved strings are today's). Two keep names the platform already
   reads; five are new, prefixed so one grep finds every read of the port.

   | Key | `app/` | Read by |
   |---|---|---|
   | `CANARY_VERSION` | `0.2.0-waitlist` | release default, launchpad, conformance: the version the committed targeting rule fails |
   | `MUTATION_BASELINE` | `0.7658…` | `gates/mutation.sh`; moves from `policy/merge.env` with its provenance comment |
   | `WORKLOAD_KILL_SWITCH` | `waitlist` | `kill-switch`, `demo-hold`, `demo-launch`, conformance |
   | `WORKLOAD_SAMPLE_PATH` | `/api/meetups` | `metric-shape.sh`: one read-only, instrumented GET (the app does not instrument `/healthz` or `/metrics`; no other route is common to every workload) |
   | `WORKLOAD_LOCKFILES` | `backend/uv.lock:frontend/package-lock.json` | `gates/deps.sh` |
   | `WORKLOAD_MUTATION_SCOPE` | `backend/meetups/` | `gates/mutation.sh`: the diff it reads |
   | `WORKLOAD_TEST_ROOT` | `backend/` | `gates/mutation.sh`: stripped to address lines in the test image |

   A gate whose input is empty, or names a path absent at `HEAD`, answers
   NO-GO naming the key, never the "GO by absence of subject" a misspelt
   scope would earn on every PR. *(d) The baseline measures one
   workload's suite; `MUTATION_MARGIN`, a decision, stays in policy.*

3. **Fixed by the port.**
   - `$WORKLOAD/compose.yaml`, merged after the root file, its relative
     paths resolving from the repo root (docs.docker.com, verified
     2026-09-23; `include:` would resolve them per file but cannot extend
     `gemini-cli`), no `name:` (the last wins). `backend`: no profile,
     image `localhost:5050/lights-out-backend:${APP_TAG:-latest}`, which
     the `Registry` adapters build, push and verify (one plane runs one
     workload, so one name serves). `backend-canary`: profile `canary`,
     image `${CANARY_IMAGE}`, no `build:` (only the verified digest
     runs), reports `${CANARY_VERSION}`. `backend-test`: profile `test`;
     its default command runs the suite and its exit code is the verdict.
     The rest is the workload's (`postgres`, `migrate`, `geocoder`); it
     may merge `environment` and `depends_on` into `gemini-cli`, which
     runs its tests. flagd mounts `./${WORKLOAD}/flags`.
   - HTTP on `:8000`, both revisions: `GET /healthz`, JSON with `version`;
     `GET /metrics`, Prometheus text with the stable HTTP semconv
     histogram `http_server_request_duration_seconds` (default buckets
     `0.005` to `10` s, label `http_response_status_code`) and
     `target_info` whose `service_version` is the `/healthz` version,
     joined on `(job, instance)`: what `verify/` reads.
   - `flags/flags.json`: `release-freeze` (default off) and
     `$WORKLOAD_KILL_SWITCH`, on for context `version` equal to
     `CANARY_VERSION`, so `load.sh`'s traffic answers 5xx on that version.
     *(b) One file, as ADR 0013 §6 has it.*
   - `smoke.sh` (exit 0 when the happy path answers through `$APP_URL`),
     `load.sh` (traffic through `$APP_URL` until killed), optional
     `crew-prepare.sh <workspace>` (`core/crew.sh`'s three links move in).
   - In the test image, from its working directory, `tests/mutation/run.sh`
     (ADR 0015 §3's wire format) and `tests/sast/run.sh` (one JSON line
     `{"findings": N}`, report on stderr, non-zero only if the tool
     failed); bandit leaves `gates/sast.sh` for the app's runner.
   - `fixtures/gates/<name>/{*.patch,expect}` (ADR 0015 §6), at least one;
     `demo-gates` iterates them and NO-GOes on none. The app's six move
     there byte-identical. *(c) A fixture is a patch against one workload.*

4. **The workload's gate surface is platform-risk.** `RISK_HIGH_PLATFORM`
   gains `*workload.env`, `*tests/sast/*`, `*fixtures/gates/*` (the trap)
   and `*compose.yaml`, `*Containerfile`, `*tests/mutation/*`,
   `*flags/flags.json` (the same hole, already open: a PR could rewrite
   `score.py`, the test image's `CMD` or the freeze flag and merge
   itself). No committed fixture touches any (checked 2026-09-23).

5. **Two static checks.** `ci/app-free.sh`, `vendor-free`'s shape: `grep
   -rniE 'app/|meetup|waitlist|geocoder|workloads/'` over `core/`,
   `gates/`, `verify/`, `adapters/`, in `*.sh`, `*.py`, `*.md`,
   `*.promql`, `*.yaml`, `*.yml`. Today it hits eleven files, all edited
   by M12 (`core/tests/test_risk.py` takes its paths from the policy's
   globs). `adapters/` joins ADR 0029's three because `flagd/ready.sh`
   polls `waitlist`, where the second workload's `up` would time out
   first; it polls `release-freeze` now, any value. `ci/workloads.sh`
   replaces `ci/compose.sh`: for each `*/workload.env` and
   `workloads/*/workload.env`, exactly §2's keys (an extra one could
   override `DELIVERY` or a `?=` default), `docker-compose config` showing
   §3's services, profiles and images, and a flag file defining
   `release-freeze` and the kill switch (the launchpad reads an
   unanswerable freeze as not frozen).

6. **`workloads/minimal/`**: FastAPI on the app's pinned Python digest and
   uv version, OTel FastAPI instrumentation with the Prometheus exporter,
   the flagd in-process provider; no database, no frontend; `/healthz`,
   `/metrics` and one route answering 501 while its kill switch is on for
   its version; pytest, both runners, a flag file, `smoke.sh`, `load.sh`;
   one fixture, `honest-fix`, expecting `GATES=GO`, `RISK_LEVEL=low`,
   `RISK_DECISION=auto-merge`, `MUTATION_TOTAL=some`, its changed lines
   reaching the baseline minus `MUTATION_MARGIN` (with a handful of
   mutants: none survives). Baseline provenance: `./go mutation-baseline
   WORKLOAD=workloads/minimal`. No value in its `workload.env` equals the
   app's; no tickets. A future `./go new` would copy it; nothing is built
   for that.

7. **Acceptance: `./go demo-seam`**, outside `./go demo` (ADR 0003): with
   `WORKLOAD=workloads/minimal`, `down`, `up`, `smoke`, `verify`,
   `demo-rollback`, `demo-gates`, `down`, then `GO: demo-seam`. It
   asserts the release record's failing stage is an `error_rate` NO-GO:
   `demo-rollback` passes on any NO-GO, "no traffic" included (the ADR
   0014 lesson), and only `error_rate` shows both versions' samples
   crossed the `target_info` join. `down` gains `--remove-orphans` and
   brackets the run: after it Prometheus starts empty (a later `up`
   re-mounts no anonymous volume, docs.docker.com), so verify never joins
   the two workloads' `backend:8000` series. M12 closes on `./go ci`,
   `./go demo` (L0, clean container, within plan §2's 900 s, same fixtures
   and tickets) and `./go demo-seam` GO; the targets this ADR edits
   (`demo-gates`, `demo-hold`, `demo-launch`, `delivery-conformance` at
   L0) still GO; `docker-compose config` for the merged app as pre-M12.

## Alternatives rejected

- **(a) A name under `workloads/`.** `app/` would move (committed patches
  carry `app/…`; re-recording needs an L1 key) or be a special case.
- **(b) Two flag files, the freeze in `adapters/flagd/`.** flagd.dev does
  not say what the in-process sync (the app's flag path) returns with two
  sources; `set.sh` would have to find each flag's file. §4 guards one.
- **(c) `gates/fixtures/<workload>/`.** `gates/` keeps app paths,
  `app-free` needs an exclusion, a workload stops being one directory.
- **(d) The baseline in policy.** The second workload judged by a number
  measured on another codebase: a threshold with a false provenance.
- **(e) Move `tickets/`, `fixtures/`, `policy/` into the workload.** Every
  ticket, recording and `adapters/replay/` path moves, for no criterion.
- **Bandit stays in `gates/`, behind a key.** The next workload (§14) is
  not Python; `gates/` would reopen for it.
- **`demo-hold` inside `demo-seam`.** Two more `STAGE_SECONDS` windows
  (60 s each, ADR 0013 §5) for a direction the app already proves.

## Consequences

- Plan: §4's table gains `| Workload | app, workloads/minimal | what the
  platform operates on, chosen by WORKLOAD=<dir> (default app), not the
  profile; workload.env, compose.yaml, /healthz and /metrics on :8000,
  flags/flags.json, smoke.sh, load.sh, in-image test/mutation/SAST
  runners, fixtures/gates/; unnamed in core/, gates/, verify/, adapters/
  (ci/app-free.sh); checked by ci/workloads.sh and ./go demo-seam (ADR
  0030) |`; the "profile chooses" rule excepts it; §6 gains
  `workloads/`; §5, §7 M12 and §12 add `adapters/` to app-free's scope.
- *(e)* The workload directory, `tickets/`, `fixtures/` and `policy/` are
  declared the instance's (here, the meetup instance's) and do not move;
  a real instance replaces them. Everything else is platform.
- **The one that will hurt: the seam is proven for location, not
  language.** Both workloads are Python; before any gate, the §14
  experiment's first ticket meets envoy-canary's `python3` probes (a fix
  inside the adapter) and a dev-worker prompt naming the meetup layout,
  which stays: `roles/` is outside `app-free`, and editing it would detach
  `fixtures/0001` and `0005` from the prompt they were recorded under.
- `ci/prompts.sh`'s hand list trades `bandit` (and `cosmic-ray`, once no
  gate names it) for `tests/sast`, so a prompt naming bandit passes. The
  Python mutation runner exists twice, in step only through the contract.
  More reviews: flag-file, Containerfile and compose-fragment changes are
  high risk. Switching workloads costs a `down` and an `up`.
- `.github/workflows/ci.yml` gains a `seam` job shaped like `launch`: one
  more plane per push. `./go` adds `demo-seam` to its socket list,
  `ci/shell.sh` checks every workload's scripts, and README and
  `docs/ARCHITECTURE.md` describe the port.

## Golden-rule check

`./go demo` runs the same merged project (`docker-compose config` proves
it); `./go ci` gains two static checks and loses one; `workloads/minimal/`
is built only by `./go demo-seam`, which needs no key either. Passes.
