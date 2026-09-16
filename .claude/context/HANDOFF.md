# Handoff: M7 closed on 2026-09-16

## Acceptance

Plan §7 M7: `adk eval` passes in CI; a fake alert produces an incident with ordered hypotheses and a rollback proposal, without the agent touching the environment. Plus go-for-launch (ADR 0019 §8, ADR 0003's rule) and ticket 0004's check (owner scope decision, this session).

`./go ci` at L0 (key parked outside the tree), 39 s warm, sixteen checks:

```
GO: secrets … GO: tower
GO: prompts
GO: evals
GO: promote
GO: contract
GO: ci
```

`evals` = the toolset assertion, nine replay unit tests, then `adk eval` on the three roles (7 cases, `tool_trajectory_avg_score` 1.0 EXACT `ignore_args`) on the replay model; `Tests failed: 0` for each, parsed from the CLI's summary because `adk eval` exits 0 either way (verified in 2.9.1's source).

`./go demo-triage` at L0, 3 s, `PLANE_HOST=nowhere.invalid`, no engine socket:

```
[triage] canary-5xx: incident "Canary 0.2.0-waitlist 100% error rate at 5% traffic"
         1. Canary version 0.2.0-waitlist contains a regression … — Canary error_rate is 1.000 while stable error_rate is 0.000 with canary receiving 0.208 traffic.
         2. Canary routing or configuration misconfiguration … — Canary receives traffic (0.208) but experiences a 100% error rate (1.000) whereas stable operates normally
         proposal: rollback 0.2.0-waitlist — …
[demo-triage] canary-5xx: 2 hypotheses, proposal rollback (expected rollback)
[demo-triage] misleading-stable-fails-too: 2 hypotheses, proposal hold (expected hold)
[demo-triage] misleading-no-canary-traffic: 2 hypotheses, proposal hold (expected hold)
GO: demo-triage
```

`./go demo-launch` at L0, 123 s warm (kill-switch, release held at 25%, brief, `GO_FOR_LAUNCH=GO`, 100%, un-promote):

```
[launchpad] 25%: GO — held; ./go promote runs go-for-launch (record at .crew/release.json)
GO: launchpad
[go-for-launch] promotion brief for 0.2.0-waitlist (by core/promote.sh from the record — no model at L0, the release role writes it from L1):
# Promotion brief: 0.2.0-waitlist
… 5%: GO: slo / 25%: GO: slo with the slo: lines verbatim …
Recommendation: GO — every stage passed verify; the numbers above are the evidence.
GO: go-for-launch
[go-for-launch] 0.2.0-waitlist at 100% of traffic (envoy-canary)
[demo-launch] 0.2.0-waitlist at 100%: 10/10 healthz samples; now the un-promote
GO: demo-launch
```

`./go promote GO_FOR_LAUNCH=GO PROFILE=l1` on the same record, 8 s: the real release role's brief **recommended NO-GO** ("the deployed canary image was not built from the merge SHA") — a correct reading of the record's `image` line; the human's GO then shifted to 100%. That brief is the one worth showing on stage.

`./go demo` from a stopped plane (warm images): `GO: demo, milestone M7, 306s to rollback (budget 900s, plan §2)`; fully cold (no workbench image, no plane images, no build cache): `GO: demo, milestone M7, 684s to rollback (budget 900s, plan §2)` — see the open questions below. No `NOT YET` line anywhere in the run. `git grep 'NOT YET'` finds no M7 stub.

## What changed

- `adapters/adk/`: the `adk` AgentHarness adapter (ADR 0020 §1) — `run.sh` (`ROLE INPUT OUT THINKING TIMEOUT_S` → `calls.json`, `final.md`, `run.json`), package `lights_out_adk/` (`roles.py` reads `roles/<role>/prompt.md` + `role.env`; `model.py` derives the model from `AGENT_HARNESS`: `replay` → `ReplayLlm`, else `gemini-3.8-flash` with `BuiltInPlanner(thinking_level)` and `RecordingLlm` under `ADK_RECORD=1`; `replay.py` keyed by sha256 of the canonical input, indexed by model turns in the request; `run.py` on `InMemoryRunner`), three agents `agents/{product,ops_triage,release}/` with the seven decision tools of ADR 0020 §3 and their evalsets. Fixtures at `fixtures/adk/<role>/<sha256>.json` (3 + 2 + 2), recorded this session.
- `roles/{product,ops-triage,release}/prompt.md` (ROLE.md gone) and `role.env` (`HARNESS=adk`, `TIMEOUT_S=900`); `core/crew.sh` resolves `${HARNESS:-$AGENT_HARNESS}`. `roles/dev-worker/prompt.md` rewritten under ticket 0004 (no gate name, gate tool, `make`/`./go`); `ci/prompts.sh` enforces it, self-tested on a planted word.
- `core/launchpad.sh` writes `RELEASE_RECORD` (`.crew/release.json`: version, stable, stages with `slo:` lines, verdict) and the stub line is gone; `core/promote.sh` = go-for-launch; `core/triage.sh` = alert → `.crew/triage/<name>/incident.json`. Makefile: `triage`, `demo-triage`, `promote`, `demo-launch`, `record-evals`; `CI_CHECKS` += `prompts evals promote`; `go` socket list += `demo-launch`. Workflow job `launch` runs `./go demo-launch`.
- Workbench: `workbench/pyproject.toml` + `uv.lock` (`google-adk==2.9.1`, `google-cloud-aiplatform==2.1.3`, rouge-score, pandas, tabulate) into `/opt/workbench-venv`; image +300 MB (1.13 → 1.43 GB arm64), venv layer 25 s warm; `go` tags the image on Containerfile + pyproject + lock; telemetry consent answered no under both HOMEs and every `adk` call runs `</dev/null`.
- Docs: ADR 0020 (accepted, with the L0-brief note), README, ARCHITECTURE, PLAN §7 notes (M7, M8), §5 note, ADR status lines 0003/0013/0014/0017/0019, tickets 0003/0004, ROLE.md of architect/test-reviewer → M8, `core/steps/ci.sh` review line → M8.

## Contradicts docs/PLAN.md and ADR 0020 as drafted

- **Plan §3 "Agenti ADK: stub" at L0 is a replay model, declared** (ADR 0020 §2): the tools, the eval and the drivers run for real; the model turns come from `fixtures/adk/`. Same pattern as the M5 crew fixture. README says so.
- **ADR 0020 §4 as drafted had `./go promote` run the release role at every level; at L0 that is impossible by construction** — a live release record carries live numbers, no recording keyed on its text can match it, and keying on less would put recorded numbers beside a record that says otherwise. Found at the first `demo-launch`. Decision (dated note in §4): at L0 `core/promote.sh` renders the brief from the record and labels it so; from L1 the release role writes it; `ci/promote.sh` case (h) proves the L0 path. This is the second place (after the crew) where "replay" means something narrower than "the agent ran"; both are declared, neither is silent.
- **`adk eval` needs `google-cloud-aiplatform` even with no LLM-judge criterion**: `evaluation/vertex_ai_eval_facade.py` imports `vertexai` at module level through the metric registry. The minimal set the plan session measured (177 MB) does not run; 296 MB does; the full `[eval]` extra (658 MB, scikit-learn, gepa) is not needed. Pinned and explained in `workbench/pyproject.toml`.
- **`adk eval` writes `.adk/eval_history/` under the agent dir**, and `ci/secrets.sh` (working-tree scan, ignores .gitignore) flags the request ids in it as `generic-api-key`. `ci/evals.sh` deletes it after each run. Same family as the `.env` contradiction below.
- Review roles re-dated a second time (M6 → M7 → M8), with ticket 0003 and the two dev-worker `record`s (ADR 0020 §9, PLAN §7 notes). ADR 0003's rule binds M8: `core/steps/ci.sh` still prints "nobody reviews until M8".
- The tower does not emit an alert on a real rollback and does not call the triage role (ADR 0020 §3): the alert is a derivative of `RELEASE_RECORD` shape-wise, but the replay key would never match a live one. M8's tower can emit one; at L0 it would need the same "no model" honesty as promote.

## Found this session, fixed

- `RecordingLlm` must carry the real model id in its `model` field: ADK copies `agent.canonical_model.model` into every request, so a wrapper named "recording" hit `models/recording is not found`.
- ADK logs every failure with a full traceback; `run.py` sets `google_adk` logging to CRITICAL and filters the `[EXPERIMENTAL]` warning so the adapter's one stderr line is what the driver shows. A replay's `run.json` puts the recorded tokens under `recorded` and reports 0 spent (ADR 0017 §2's rule).
- `go` forwards no host environment: `GO_FOR_LAUNCH=GO ./go promote` does nothing; `./go promote GO_FOR_LAUNCH=GO` (a make variable) is the form. Help text and ADR say so.
- Product role, attempt 1: asked about status codes on the complete ticket. The prompt gained "ready does not mean exhaustive"; attempts 2–3 passed (3 was a re-record after `ci/prompts.sh` rejected the English word "make" in the new paragraph — the check is that literal). ops-triage and release recorded first time.
- `ci/promote.sh`'s new case (h) has to sit before the test's `cd "$repo"`; a shellcheck SC2015 in it failed `ci-shell` on the first `./go demo`.

## Found, not fixed

- **`./go ci` still cannot pass with a real key in `.env`** (M5, M6): parked outside the tree for every `ci`/`demo` run, restored for the three `record-evals` and the L1 `promote`. Owner of `ci/` decides (gitignore-aware gitleaks vs ADR 0002).
- `ci/prompts.sh` forbids the bare words `gate`, `gates`, `make` in any prompt, including English prose ("make the change"). It is what ticket 0004 asked for; if it bites, the rule text should change, not the check.
- The three ADK roles have no `TOKEN_BUDGET`; `run.json` records the numbers (ops-triage ≈ 3.2k tokens, 2 calls, 9 s at L1). A dedicated commit can set budgets from a few more runs.
- `demo` measured 306 s warm from a stopped plane vs 360 s at M6 — noise from a warm image cache, not a speed-up. Cold is measured by the GitHub `engine-compat` job; the workbench image now pulls ~300 MB more of wheels on a cold build.
- The M6 `.env` clock-skew prerequisite for M8 stands (see the M6 HANDOFF in git history).

## Open questions for the owner, before M8 is framed

1. **Do the review roles stay in M8, or become a milestone of their own?** They are at their second re-date (M6 → M7 → M8) and the Gitea runner socket at its third (M4 → M5 → M6 → M8); M8 is already the largest milestone in the plan (Terraform, Artifact Registry, Cloud Run, Cloud Deploy, Monitoring, Binary Authorization, WIF, Secret Manager, plus the socket, the image build and the clock check inherited from M6). Independent review is one of the five principles of the platform (plan §8 step 4: "parte la review agent"; the `review` state has been terminal since M6), not an extra — and it is the only one of the five with no run behind it. The concrete work is: two prompts on the existing gemini-cli harness, a `review` step in `core/tower.sh` (precondition `review`, next `ci-passed`/`ci-failed`), a medium-risk PR recorded at L1 (`fixtures/<ticket>/test-reviewer/`), ticket 0003's perimeter rule, and the two dev-worker `record`s — all L1 work with no GCP dependency, which is the argument for its own milestone before M8 rather than inside it. The plan's numbering (M8 GCP, M9 platform, M10 design) and the talk's "six roles" both survive either answer; ADR 0003's rule binds whichever milestone owns it.

2. **The workbench image: what belongs in the base.** Measured 2026-09-16 inside the image (`du -sm`, arm64): `/opt/google-cloud-sdk` 368 MB, `/opt/workbench-venv` (google-adk + aiplatform) 304 MB, node 118 MB, terraform 106 MB, shellcheck 53, osv-scanner 52, uv 41, docker-compose 29, gitleaks 20; 1.42 GB total. The ADK's 300 MB **cannot move to a cloud-tier image** without moving `ci-evals` off the L0 path: `adk eval` runs inside `./go ci`, which `./go demo` runs at L0 with no socket, so whatever it needs must be in the image `./go` builds for a stranger (ADR 0002, 0020 §5). What *can* move is the 474 MB nothing uses before M8 — gcloud and terraform, both untouched by any script in `ci/`, `core/`, `adapters/`, `gates/`, `verify/` today (verified by grep) — into a `workbench-cloud` image (`FROM` the base, the two fetches, `PROFILE=l2`/`l3` selecting it in `go`), which would leave the L0 base at ≈ 0.95 GB, smaller than it was at M6 (1.13 GB). Not done this session: it is a structural change to `go` and ADR 0004 (an ADR, and M8 is the milestone that first needs gcloud). **Cold build re-measured**: `podman build --no-cache` of the workbench, 90 s on this connection (the venv step: 78 packages resolved and installed in ≈ 8 s of it; the gcloud tarball is the largest single download). A fully cold `./go demo` — no workbench image, no plane images, no build cache, arm64 podman on this laptop — measured **`GO: demo, milestone M7, 684s to rollback (budget 900s, plan §2)`** — 76 % of the budget, 216 s of margin, against 306 s warm the same afternoon: 378 s of cold cost, of which the workbench build is 90 s and the rest is the plane's image pulls (Gitea, Postgres, flagd, Zot, the two emulators, Envoy, Prometheus) and the app image builds (vite, uv, the backend-test image the gates need). Not broken down further this session — the demo log has no timestamps; adding one `date` per `[demo]` stage line is the cheap way to get the split next time. ADR 0013 §5's estimate (cold ≈ 340 s to the rollback) and ADR 0019 §7's projection (≈ 520 s) are superseded by that number; the GitHub `engine-compat` job measures the amd64 docker figure on every push.

## Prerequisites M8 inherits

- The review roles: `architect` and `test-reviewer` prompts, a `review` tower step (precondition `review`, next `ci-passed`/`ci-failed`), a medium-risk PR recorded at L1; ticket 0003's perimeter rule before that `record`; the two dev-worker `record`s that fix the 12M budget and validate the rewritten prompt (ticket 0004's second criterion).
- Engine-host clock skew check before signing/OIDC; the runner socket and the first Gitea Actions job (ADR 0019 §4's five facts; ADR 0003's rule); image build from the merge commit and Zot push — the release role's NO-GO brief above is the user-visible reason.
- If M8's tower emits alerts from `RELEASE_RECORD` on a rollback, `core/triage.sh` is the consumer; at L0 the same "no model for live input" rule as `promote` applies.

## First thing M8 should look at

- `core/steps/ci.sh` line 53 ("nobody reviews until M8"): the review step is the one stub-like line left, and ADR 0003's rule binds it.
- Before any `record`: park `.env` for `ci`, sync the podman clock (`podman machine ssh "sudo date -s @$(date +%s)"`), and re-read ADR 0018 for the 3.8 routing check.
