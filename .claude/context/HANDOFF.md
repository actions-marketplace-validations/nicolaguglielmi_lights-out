# Handoff: each `./go ci` check runs once (ADR 0062), 2026-11-09

Branch `claude/festive-cray-5c155e`, on 8e968aa (main moved to b931688 since: `pyproject.toml` and `docs/launch/checklist.md`, no file of this branch). Pushed, no pull request, not merged: landing is the owner's. The handoff of M31, M34 and M35 as merged is this file at 8e968aa.

## Acceptance

GitHub Actions on 877e7a2, the code and the docs without the after-measures: ci 42588292173, stranger 42588292176 (second attempt, see "Found"), self 42588292191, package 42588292374, podman 42588292212, all green. The commit after it adds measures, the plan's note and this file; its runs are named in the session's report. `site` does not trigger on these paths and is dispatched by hand on the branch head.

```
before, 8e968aa   engine-compat  GO: demo, milestone M9, 828s to rollback   (42530031181; contract 229 s)
                  engine-compat  GO: demo, milestone M9, 815s to rollback   (42533480920; contract 225 s)
                  stranger       GO: demo, milestone M9, 820s to rollback   (42530031109; contract 186 s)
                  stranger       GO: demo, milestone M9, 732s to rollback   (42533480868; contract 142 s)
after, 877e7a2    engine-compat  GO: demo, milestone M9, 632s to rollback   (42588292173; contract 0.9 s)
                  stranger       GO: demo, milestone M9, 678s to rollback   (42588292176 attempt 2; contract 1 s)
local, clean clone, podman machine
  before  ./go ci           GO: ci in 360 s (the 40 checks 186 s, contract 174 s)
  after   ./go ci           GO: ci in 183 s and 185 s (contract 1 s; engine-compat the one check run cold)
  after   ./go ci-contract  GO: contract in 179 s, alone: every gate cold, as before
  after   ./go ci-contract CI_RECORDS=.crew/planted
            a GO record for every check                GO: contract, 1 s
            help.out = "GO: help" and an empty line    NO-GO: contract — gate(s) violate the output contract: help(lines=2)
            help.rc removed                            help run cold, GO: contract
```

`ci/docs-drift.sh` GO on the host and in both local runs.

## What changed

- ADR 0062 before the code, by the architect; the proof in `ci/contract.sh` written from the ADR by the gate-writer before the feature existed, red on the old code for the right reasons, then merged over the implementation.
- `Makefile`: `ci` sets `CI_RECORDS` to `.crew/ci/<16 hex>` for its prerequisites only, drawn once per make invocation; `ci-%` is `record_check ci/<name>.sh <name>`; a GO removes the run's records.
- `ci/lib.sh`: `record_check SCRIPT NAME` keeps stdout in `NAME.out` and the exit code in `NAME.rc`, written last; with `CI_RECORDS` empty or unset it only runs the check.
- `ci/contract.sh`: a `ci/` check with a usable record is judged on it, anything else is run cold with one stderr line saying so; `gates/`, `verify/`, the light entry point and the `nogo` probes are as before. The records proof plants a tree (a copy of the lib and of the script, eleven gates and records, a `record_check` case) and runs the copy with `CONTRACT_PLANTED=1`.
- Docs: ADR 0062; dated amendments to ADR 0060 §7 and ADR 0011 §4; ARCHITECTURE's one-CI invariant; the reference's `ci/` listing; the tutorial's line on the meta-gate; ROADMAP's M34 row; the plan's M34 note; the Makefile's comment on `DEMO_BUDGET_SECONDS`.

## Proof that the proof can fail

Nine deliberate breaks of the implementation, each on a scratch copy with planted GO records for the real checks, so only the proof decides:

```
records never read                         contract(record two-lines accepted) ... (record good rejected) (record good-nogo rejected)
the record's exit code ignored             contract(record go-exit-1 accepted) contract(record good-nogo rejected)
ANSI not looked for                        contract(record ansi accepted)
a missing .rc taken as exit 0              contract(record no-rc accepted)
record_check writes no .rc                 contract(record_check: NAME.rc is not the line 1)
record_check keeps stdout for itself       contract(record_check: CI_RECORDS set: not both lines on stdout and return 1)
record_check records with CI_RECORDS empty contract(record_check: CI_RECORDS unset: wrote something)
lines counted after $(...)                 contract(record blank-after accepted)
the digits test on .rc removed             GO: equivalent code, the 0-to-255 test still refuses "zero"
```

## Found, not fixed here

1. **The stranger's first attempt on 877e7a2 failed in `e2e`**: `NO-GO: e2e — ticket 0001 ended at held, expected rolled-back` at 813 s, after `GO: ci` at 374 s. The re-run of the same commit was GO in 678 s. What the logs show:
   - On podman the canary deploy (`adapters/envoy-canary/deploy.sh`, `docker-compose --profile canary up -d backend-canary`) recreates postgres, flagd and geocoder as well; on docker (engine-compat) only `backend-canary` is created.
   - On docker every rollback read is the real verdict: `error_rate canary=1.000 ... delta=1.000 max=0.010`. On podman, of the eight rollbacks in the four stranger logs read in full (42530031109, 42533480868, 42588292176 both attempts), six are `traffic: adapters/prometheus/query.sh exited 22: curl: (22) ... 422`, one is the real error-rate verdict, one is the hold. The 422 in 42530031109 is "found duplicate series for the match group {instance="backend:8000", job="backend"}": two `target_info` series with different `service_instance_id` for one target. Five older stranger runs sampled show the same mix.
   - In the failed attempt the queries answered, and the canary was judged healthy at 5 % and at 25 %: `traffic canary=0.055` then `1.055`, `error_rate canary=no data`, `latency_p95 canary=0.005`. So the canary served traffic with no 5xx, where the demo expects the kill switch to make it fail.
   - Not established: why the canary did not fail in that run (the flag evaluated off while flagd was being recreated is a guess), and why the duplicate series appears and ages out.
   - Why it is not this change: everything above happens after `up`; the `ci` stage ends before it and leaves nothing behind but an empty `.crew/ci/`. What this change does alter is how long the plane started by engine-compat lives before the demo's `up` recreates it, about 170 s less.
   A rollback that happens because a query errors is the demo passing for the wrong reason, and a hold is the demo failing: both are worth a ticket before the launch.
2. `docs/tutorial.md`, "The plane comes up", still lists the two Google emulators in the L0 plane; since M34 they are opt-in.
3. README and the site quote 434 s for a warm local demo. With `ci` at half its time it should be lower; not re-measured, the claim is now conservative.
4. CLAUDE.md's contract section says the meta-gate "esegue ogni gate con stdout catturato". Under `./go ci` it judges the record of each check's one run. The wording is the owner's.
5. The 40 checks themselves are what is left of the `ci` stage: 145 to 251 s on Actions, `shell` 42 s, `evals` 33 s, `logbook` 19 s, `core-tests` 13 s locally.

## Merge notes

- Conflicts to expect: the Makefile's `ci` and `ci-%` block, `ci/contract.sh` if another branch touched `shape()` or the judging loop (the proof reads the reason tokens `lines=N`, `ansi`, `GO,exit=N`, `NO-GO,exit=N`, `format`), this file, the M34 note in `docs/PLAN.md`, ROADMAP's M34 row.
- A new check in `CI_CHECKS` needs nothing: it is recorded like the others. A `ci/*.sh` outside `CI_CHECKS` is run cold by `contract`.

## First thing for the next session

Decide what to do with finding 1: reproduce the hold on podman (`./go demo` in a loop on the stranger job, or locally on the rootless connection), then make the canary deploy leave its dependencies alone and make a failed query a failure of its own kind instead of a rollback verdict.
