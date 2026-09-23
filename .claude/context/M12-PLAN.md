# M12 — the seam: plan approved 2026-09-23

Read first: docs/PLAN.md §7 M12 and §14, docs/adr/0029, docs/adr/0030 (the
design; every decision below comes from it). This file is the file-by-file
plan the owner approved, so `/milestone M12` can skip straight to §3 of the
skill after re-checking §1.

## Frame

**Deliverable.** The `Workload` port (ADR 0030): a directory chosen by
`WORKLOAD=<path>` (default `app`), seven keys in `workload.env`, three fixed
compose services (`backend`, `backend-canary`, `backend-test`), `/healthz`
and `/metrics` on :8000, one flag file, `smoke.sh`/`load.sh`, two in-image
runners, `fixtures/gates/`. Two static checks (`app-free`, `workloads`), a
second workload `workloads/minimal/`, and `./go demo-seam`.

**Acceptance, verbatim (ADR 0030 §7):**

```
./go ci          → GO: ci        (app-free and workloads added; compose removed)
./go demo        → GO: demo, milestone M9, <t>s to rollback (budget 900s)  — same fixtures, same tickets
./go demo-seam   → GO: demo-seam (down, up, smoke, verify, demo-rollback, demo-gates, down on
                    workloads/minimal; asserts the rollback's NO-GO stage is error_rate)
docker-compose config of the merged app project == the pre-M12 output
```

Still GO: `demo-gates`, `demo-hold`, `demo-launch`, `delivery-conformance`.

**Out of scope.** `tickets/`, `fixtures/`, `policy/` do not move (declared
per-instance). `roles/dev-worker/prompt.md` does not change (it would detach
fixtures 0001/0005 from the prompt they were recorded under). No `./go new`.
The seam is proven for location, not language: both workloads are Python.

## Pre-steps (before touching any file)

1. Park the owner's `.env` for the `ci` runs: `mv .env .env.l1` … `mv .env.l1 .env`.
   `ci/secrets.sh` scans the working tree and flags the L1 key in it
   (pre-existing, see HANDOFF M7/M9).
2. Capture the merged compose config of the untouched tree into the
   scratchpad: `printf 'docker-compose config\n' | ./go shell > before.yaml`
   (214 lines, 14 services on 2026-09-23). The acceptance diffs against it.

## Files

**Created**
- `app/workload.env` — the seven keys: `CANARY_VERSION`, `MUTATION_BASELINE`
  (with its provenance comment, moved from policy), `WORKLOAD_KILL_SWITCH`,
  `WORKLOAD_SAMPLE_PATH`, `WORKLOAD_LOCKFILES`, `WORKLOAD_MUTATION_SCOPE`,
  `WORKLOAD_TEST_ROOT`. Paths relative to the workload directory.
- `app/compose.yaml` — the app's services lifted out of the root file
  (`postgres`, `migrate`, `geocoder`, `backend`, `backend-canary`,
  `backend-test`) plus the `environment` the `gemini-cli` worker merges to
  run the app's tests. No `name:`.
- `app/crew-prepare.sh <workspace>` — the three symlinks from `core/crew.sh:58-62`.
- `app/backend/tests/sast/run.sh` — bandit inside the test image; one JSON
  line `{"findings": N}` on stdout, report on stderr, non-zero only if bandit
  itself failed.
- `app/fixtures/gates/*` — the six gate fixtures, `git mv`, byte-identical.
- `ci/app-free.sh` — `vendor-free`'s shape; `grep -rniE
  'app/|meetup|waitlist|geocoder|workloads/'` over `core/ gates/ verify/
  adapters/` in `*.sh *.py *.md *.promql *.yaml *.yml`.
- `ci/workloads.sh` — replaces `ci/compose.sh`: for `*/workload.env` and
  `workloads/*/workload.env`, the exact key set, `docker-compose config`
  showing the three services/profiles/images, and a flag file defining
  `release-freeze` and the kill switch.
- `workloads/minimal/` — `workload.env`, `compose.yaml`, `Containerfile`
  (same Python digest and uv version as `app/backend/Containerfile`),
  `pyproject.toml` + `uv.lock`, `minimal/app.py` (`/healthz`, `/metrics`,
  one route answering 501 while the kill switch is on for its version; the
  app's `metrics.py`/`flags.py` are the template), `flags/flags.json`
  (`release-freeze`, its kill switch targeted on `CANARY_VERSION`),
  `smoke.sh`, `load.sh`, `tests/` (pytest; `mutation/run.sh`,
  `cosmic-ray.toml`, `score.py`; `sast/run.sh`), `fixtures/gates/honest-fix/`
  (expect: `GATES=GO RISK_LEVEL=low RISK_DECISION=auto-merge
  MUTATION_TOTAL=some`), a one-line README ("exists to prove the seam, ADR
  0030; an instance has one workload, at app/"). No value in its
  `workload.env` equals the app's. `MUTATION_BASELINE` measured with
  `./go mutation-baseline WORKLOAD=workloads/minimal` and quoted.
- `.github/workflows/ci.yml` — a `seam` job shaped like `launch`.

**Modified**
- `Makefile` — `WORKLOAD ?= app`; `include $(WORKLOAD)/workload.env`;
  `COMPOSE_FILE := compose.yaml:$(WORKLOAD)/compose.yaml` and `FLAGS_FILE`
  as `:=`, exported; every literal goes (`app/smoke.sh`, `app/load.sh`,
  `app/flags/flags.json`, `waitlist`, the `CANARY_VERSION` default, the
  "meetup" wording in messages); `down` gains `--remove-orphans`;
  `demo-gates` iterates `$(WORKLOAD)/fixtures/gates/*`; new `demo-seam`
  (down, up, smoke, verify, demo-rollback, demo-gates, down with
  `WORKLOAD=workloads/minimal`, then the `error_rate` assertion on
  `RELEASE_RECORD`); `CI_CHECKS`: `compose` → `workloads`, plus `app-free`.
- `compose.yaml` — plane and `gemini-cli` only; flagd mounts `./${WORKLOAD}/flags`.
- `go` — `demo-seam` in the socket list and the help header.
- `gates/mutation.sh` (`WORKLOAD_MUTATION_SCOPE`, `WORKLOAD_TEST_ROOT`,
  `MUTATION_BASELINE` from workload.env), `gates/deps.sh`
  (`WORKLOAD_LOCKFILES`), `gates/sast.sh` (runs `tests/sast/run.sh`, parses
  the JSON line), `gates/test.sh` (comment), `gates/delivery-conformance.sh`
  (`$WORKLOAD_KILL_SWITCH`, `$FLAGS_FILE`). A gate whose key is empty or
  names a path absent at HEAD: NO-GO naming the key.
- `verify/metric-shape.sh` — `$WORKLOAD_SAMPLE_PATH`.
- `adapters/flagd/ready.sh` — polls `release-freeze`, any value.
  `adapters/flagd/set.sh` — `FLAGS_FILE` from the environment, no `app/` default.
- `core/crew.sh` — runs `$(WORKLOAD)/crew-prepare.sh` when present.
  `core/launchpad.sh` — one comment. `core/tests/test_risk.py` — only if the
  new globs need a case.
- `policy/merge.env` — `MUTATION_BASELINE` leaves; `RISK_HIGH_PLATFORM` +=
  `*workload.env:*tests/sast/*:*fixtures/gates/*:*compose.yaml:*Containerfile:*tests/mutation/*:*flags/flags.json`.
  Verified 2026-09-23: no committed fixture (gates or crew) touches any of
  them, so no recorded verdict changes.
- `ci/shell.sh` — every workload's scripts. `ci/prompts.sh` — hand list:
  `bandit` → `tests/sast`.
- `docs/PLAN.md` — §4 `Workload` row (wording in ADR 0030 Consequences) and
  the exception to "the profile chooses"; §5, §7 M12, §12 add `adapters/` to
  app-free's scope; §6 gains `workloads/`.
- `docs/ARCHITECTURE.md`, `README.md`, `.claude/context/HANDOFF.md`.

**Deleted:** `ci/compose.sh`; `gates/fixtures/` (moved).

## Sequence and delegation

1. Plan amendments (§4, §5, §6, §7, §12) — main session.
2. The seam on the app alone: `./go ci`, `./go demo-gates`, `./go demo`
   identical, `docker-compose config` diff against the capture. Commit.
3. `workloads/minimal/` and `demo-seam`; measure its baseline. Commit.
4. README, ARCHITECTURE, HANDOFF. Commit.

`gate-writer`: `ci/app-free.sh`, `ci/workloads.sh`, the five gates,
`minimal`'s tests and fixture. `doc-scribe`: README, ARCHITECTURE, HANDOFF,
commit messages. Main session: Makefile, compose split, workload.env, the
minimal app, `core/crew.sh`, adapters.

Commits are `[M12] …` with the Co-Authored-By trailer; no push.
