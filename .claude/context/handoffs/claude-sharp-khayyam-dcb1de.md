# Handoff: the podman demo rolls back for the right reason (ADR 0066), 2026-11-09

Branch `claude/sharp-khayyam-dcb1de`, on `claude/festive-cray-5c155e` (48ceca6, ADR 0062, pushed, not merged): landing this branch lands 0062 too. Pushed, no pull request, not merged: landing is the owner's. The handoff of ADR 0062 alone is this file at 48ceca6.

## Acceptance

GitHub Actions on 469162b (the code and the docs; the commit after it only removes the two temporary workflows and writes this file and the plan's note, its runs are named in the session's report): ci 42603828472, self 42603829314, package 42603828666, podman 42603828968, all green; site 42602408053 green on faa2aab, the last commit touching `site/`. stranger, five runs of the same commit, one on push and four dispatched:

```
stranger 42603828371  demo-rollback 381 s, e2e 616 s   GO: demo, milestone M9, 616s to rollback
stranger 42603860314  demo-rollback 419 s, e2e 656 s   GO: demo, milestone M9, 656s to rollback
stranger 42603864141  demo-rollback 392 s, e2e 627 s   GO: demo, milestone M9, 627s to rollback
stranger 42603868389  demo-rollback 339 s, e2e 551 s   GO: demo, milestone M9, 551s to rollback
stranger 42603871741  demo-rollback 392 s, e2e 624 s   GO: demo, milestone M9, 624s to rollback
engine-compat (ci 42603828472)                         GO: demo, milestone M9, 588s to rollback
```

All twelve rollbacks read `NO-GO: launchpad — 5%: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000 delta=1.000 max=0.010 → rolled back`. No 422, no hold. On podman the canary deploy now creates `backend-canary` only (`./go up` still recreates the plane, see below). Locally, from a full clone of 469162b on the podman machine: `GO: ci`, `GO: contract`.

Before the fix, run 42596034173 (ten instrumented runners, `./go demo` then `./go e2e` twice each, 40 releases): 30 rolled back on `traffic: ... exited 22: ... 422`, 6 on the error-rate verdict, 4 held.

## What was wrong

The evidence and the run ids are in ADR 0066's Context; in short:

- **Root**: on podman 4.9.3 (Ubuntu 24.04's package, the runner's), docker-compose 5.5.1 recreates every container on an unchanged `up -d`, and `--profile canary up -d backend-canary` recreates its dependencies. The compat API reports `NetworkID` as the network's name; config-hash and image are unchanged (repro-compose 42600310185, a toy project). Podman 6.1.4 on the macOS machine and docker do not.
- **The 422**: Prometheus's TSDB survives the recreate (anonymous volume carried over, the WAL grows). Old backend and old Prometheus stop in the same second, so no staleness marker: the old `target_info` (another `service_instance_id`) stays 5 min beside the new one, and the join `on (job, instance)` fails with "found duplicate series". `demo-rollback` accepted it because the verdict still began `NO-GO: slo — `.
- **The hold**: the canary deploy recreated postgres under the running stable (500s for ~30 s); `app/load.sh` started in that second, its `POST /api/meetups` got a 500, `id=$(curl ... | jq -r .id)` was empty, and the load hit `/api/meetups//registrations` (405) for the whole release: no 5xx anywhere, canary judged healthy, held. flagd answered `on` for the canary throughout: not the cause.

## What changed

- ADR 0066 first (architect), the cold tests from it (gate-writer, red on the old code: `ci/metrics.sh` cases h, i, j; `ci/workloads.sh` case h), then the fix.
- `adapters/envoy-canary/deploy.sh`: `up -d --no-deps backend-canary`.
- `verify/slo.promql`: `group_left (service_version) max by (job, instance, service_version) (target_info)` in the three queries; `verify/metric-shape.sh` skips `job` and `instance` inside `by (...)`.
- `verify/slo.sh`: a query that fails is `NO-GO: slo — cannot judge: <query>: <cause>` (`<query.sh> exited <n>: …`, `answer is not JSON`, `status <s>: <errorType>: <error>`); the launchpad is unchanged and rolls back with `NO-GO: launchpad — <pct>%: cannot judge: … → rolled back`. "No traffic" stays a verdict.
- `app/load.sh`: each setup call is checked; a failure is one stderr line `app-load: setup failed at <METHOD> <path>: <cause>; generating no load` and exit 1.
- `Makefile`: `demo-rollback` and `e2e` accept only `NO-GO: slo — error_rate `*; anything else is `NO-GO: demo-rollback — the canary was rolled back for [...]` / `NO-GO: e2e — ticket <id> rolled back for [...]`.
- Docs: the reference's release controller, ARCHITECTURE's rollback line, the README's troubleshooting (two rows), the site's canary step, the plan's M34 note.

## Found, not fixed here

1. `./go up` recreates every container on podman 4.9.3, 11 to 19 s per `up` (r2 of 42596034173), three times per demo. An engine bug; the README says so. Fixing it means either a podman that reports the network id or a compose that does not compare it.
2. No cold test for `deploy.sh`'s `--no-deps`: no check shims docker-compose for the delivery adapters. The stranger logs prove it (only `backend-canary-1` is created at the deploy).
3. A Prometheus hiccup now rolls back a good canary with a `cannot judge` line, no retry (ADR 0066, Consequences): only a measured outage duration could justify one.
4. Carried from ADR 0062's handoff: `docs/tutorial.md` "The plane comes up" still lists the two Google emulators; README and site quote 434 s for a warm local demo, not re-measured; CLAUDE.md's contract wording is the owner's.

## Merge notes

- Conflicts to expect: `verify/slo.promql`, `verify/slo.sh` and `ci/metrics.sh` if another branch touched the judge; the Makefile's `demo-rollback` and `e2e`; this file; the M34 notes in `docs/PLAN.md`; README's troubleshooting table.
- After the merge: `ci/docs-drift.sh` on the host (ADR 0066 is cited from README, reference, ARCHITECTURE).

## First thing for the next session

Land 0062 and 0066 together, or 0062 first and this branch rebased on main. Then item 1 if the recreate's 30-60 s per demo is worth an engine workaround.
