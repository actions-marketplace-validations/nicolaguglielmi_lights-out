# Handoff: M60, the first run, flawless (ADR 0093), 2026-11-16

Branch `claude/m60-onboarding-39ac32`, cut from `origin/main` at b4b1590. Pushed, no pull request, nothing merged. The coordinator merges.

## The acceptance, and what proves it

- `./go ci` from a full clone under `.crew/m60/ci1` at cc90936: `GO: ci` (53 checks with `first-run`), 693 s on a VM shared with other sessions.
- `./go demo` on a clean runner, the `stranger` workflow, cold, 3000 and 8080 planted: `GO: demo` in 370 s (run 43837534798), 480 s (43841491822) and 394 s (43844732461, on bf08e7c), against 700–805 s before; the job fails over 600 s. On this Mac from a fresh clone with no `.env`: `GO: demo` in 759 s (after4), against 1,106 s and NO-GO before.
- Every workflow on bf08e7c, the last commit with code: ci 43844732398 (engine-compat's verbose docker demo included), stranger 43844732461, self 43844732421, podman 43844732547, package 43844732410, site 43844732484, all success. The commits after it touch only the ADR, PLAN and this file.

## Before and after

| | before | after |
|---|---|---|
| `stranger`, clean runner, cold | 700–805 s (five runs, 43627237505 … 43657565581); rollback at 491–577 s | **370 s, 480 s, 394 s** (runs 43837534798, 43841491822, 43844732461), rollback at 166–209 s, with 3000 and 8080 held by planted servers and moved |
| this Mac, fresh clone | NO-GO after 20 s (8080 busy), `.env` and `./go down` by hand, then 1,106 s, `NO-GO: demo` over the 900 s budget | no `.env`: 8080 moved to 8081 by itself; **759 s, `GO: demo`** (after4, df603a1, load 2.6–6.7 from other sessions) |
| lines on the terminal | ~3,260 (clean runner), 2,048 (Mac) | 17–21, the rest in `.crew/demo/run.log` |
| at the end | the app's, Gitea's and Prometheus's URLs | the run's console frozen and opened on ticket 0001, the rollback's reason, what to try next, the plane's URLs and `./go down` |
| your repository | `./go init <path>`, `./go gates`, copy and commit by hand | `./go try <path>`: 27 s on a small JavaScript repository, `GO: try`, the keep-commands printed and proven |

The Mac's VM was shared with other sessions running `make ci` and tests (load 6–14 on 4 CPUs, recorded per run in `.crew/m60/times.txt`). There the checks beside the plane compete for CPU that is not free: after3 (cc90936) passed every stage, rollback at 197 s, but waited for the checks until 1,333 s, `NO-GO: demo` over 900 s. The clean runner is the measure; on a loaded 4-CPU machine the 900 s is not held (ADR 0093, After).

## The friction log

In ADR 0093, Context, as the provenance of every number: the stranger's stage timeline (`make ci` 318 s of 751 s before the plane, a second `make up` 16 s, e2e 218 s), the Mac's two first runs, and three cases from the brief. The logs: `.crew/m60/before-demo-1.log`, `before-demo-2.log`, `after1-term.log` … `after3-term.log`, `times.txt` (outside the repository).

## What changed, in five lines

1. `core/preflight.sh` (host): a stopped podman machine started; memory warned under 3,800 MiB; disk NO-GO under 8,000 MB (6.87 GB measured); five plane ports moved off a busy default into `.crew/ports.env` (`APP_PORT`, `CODE_HOST_PORT`, `METRICS_PORT`, `DELIVERY_ADMIN_PORT`, `FLAGS_PORT`), 5050 named and refused, another directory's plane refused. `adapters/gitea/ready.sh` names the port and what answered.
2. `core/progress.sh` (host): `[n/7]` steps with estimates from this machine's last run, everything else in `.crew/demo/run.log`, the log's tail and path on a failure; `LIGHTS_OUT_VERBOSE=1` streams (the ci workflow's engine-compat job sets it).
3. `make ci` beside the plane, in a second container started by `./go` right after the toolchain image, awaited before `GO: demo`; no second `make up` inside the demo.
4. The end: logbook → `core/freeze.py --hash ticket/0001` → `.crew/demo/console.html`, the link printed and opened on a terminal (`LIGHTS_OUT_OPEN=0` stops it).
5. `./go try <path>`: attach, `init`, `gates`, the draft copied to `.crew/try/<name>/`, detached.

Tests from the ADR: `ci/first-run.sh` (new, in `CI_CHECKS`), shown to fail on two planted breaks and on a planted stage verdict; `core/tests/test_freeze.py` gains `--hash`. The `stranger` workflow plants 3000 and 8080, checks both moves and the console link, and fails over 540 s.

Docs: README section 2 (the quick start) and "If something goes wrong", the tutorial's §0–§1, the reference (stage table, commands, the preflight), `docs/use-on-your-repo.md` (`./go try`), `site/index.html` (the try panel, the proof number), PLAN "Sprint 2026-11-16 (M58–M63)" › "M60". docs-drift GO on the host.

## Screenshots

In the shared notes folder, `m60-shots/`: `end-console-ticket-0001-dark.jpg` (the page the demo opens at the end: ticket 0001's flow strip, each gate with its seconds, the canary ✕, the rollback's reason) and `terminal-stranger-370s.jpg` (the whole terminal of the clean-runner run).

## Contradicting the plan, or worth knowing

- `ci/vendor-free.sh` stopped the first draft's `GITEA_PORT`/`PROMETHEUS_PORT`/… in `core/preflight.sh` and `core/doctor.sh`: host files under `core/` are bound by ADR 0024 too. The variables are named for the port.
- The brief's "gitea not ready after 180s" on a busy 3000 was not reproduced here: the Mac's 3000 was free during this session. The preflight probes 127.0.0.1 and ::1 (with `nc`; `ss` lists every address), and the ready check now names the port and what answered, proven against a planted 404 server in `ci/first-run.sh`. Not proven: a holder bound only on another interface.
- `make ci` was 42% of the demo on a clean runner. Beside the plane it finishes before the plane's stages on the runner; on a loaded 4-CPU Mac it competes with e2e's gates, and the plane step went from 45 s alone to 76–152 s.
- The demo's stdout now carries only the demo's own verdict; the checks' 53 lines are in `.crew/demo/ci.out` and the log.
- Likely merge conflicts for the coordinator: the `demo` recipe (rewritten), `CI_CHECKS` (`first-run`), the Makefile's include of `.crew/ports.env` and the init/try include rule, `go` (the demo wrapper, the preflight, the checks' container), PLAN's new sprint heading (other sessions add theirs).

## The first thing the next milestone should look at

On a 4-CPU machine the checks beside the plane slow the plane's own stages (the Mac's plane step 45 s → 76–152 s under load). If a measured run on an idle 4-CPU machine confirms it, give the checks' container a lower CPU weight (`--cpu-shares`, which needs the cpu controller delegated under rootless podman, so measure on the stranger runner first).
