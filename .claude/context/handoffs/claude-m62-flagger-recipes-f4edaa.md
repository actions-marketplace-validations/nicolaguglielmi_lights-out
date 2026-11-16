# Handoff — M62: Flagger and the CI recipes (ADR 0095)

Branch `claude/m62-flagger-recipes-f4edaa`, not merged. Commits as Nicola, no trailers.

## Acceptance

Head 343fe38. Every workflow green on it: ci 43846825646, self 43846825672, podman 43846825660, package 43846825650, stranger 43846825524.

| What | How proven | Result |
|---|---|---|
| `./go ci` GO from a full clone | `.crew/m62-clone` | d1c5ec3: 53 checks GO, 1067 s (VM shared with other sessions). 343fe38: 53 checks GO, 524 s. Actions `ci` job GO on 343fe38 |
| `DELIVERY=flagger`, the six-case Delivery suite unchanged | `./go flagger-conformance` on Actions, k3s v1.37.2 + Flagger v1.45.0 + loadtester 0.39.0 | run 43846825646, job `flagger` 133230349964: `GO: delivery-conformance` (case 1 rejected at 5% and rolled back, case 2 held at 25 and promoted to 100 on GO, cases 3-5) |
| A canary rolled back on bad metrics | `./go flagger-proof` case a: kill switch on, shift to 5%, load, nobody but Flagger rolls back | same job: rolled back on Flagger's own failed checks in 38 s, status `{stable 0.1.0-m2, canary null, weight 0}` |
| A promotion that waits for the gate | `./go flagger-proof` case b: 5, 25, 100, gate left open | same job: `WaitingPromotion` held 30 s (three ticks) at 100%, completed once the promotion URL became `/gate/approve`; `GO: flagger — … 238s` |
| GitLab CI recipe | `./go demo-gitlab-ci`: a real gitlab-runner v19.5.3 (docker executor, socket binding) on GitLab CE 19.5.5 (the gitlab adapter's image), merge request pipeline | job `gitlab-ci` 133230350387: `GO: demo-gitlab-ci — GitLab CI (gitlab-runner, merge request !1's pipeline) posted [GO: gates — risk low, auto-merge, in workbench] as lights-out/gitlab-ci, 277s` |
| CircleCI recipe | `./go demo-circleci`: `circleci config validate` (CLI 1.15.0 image by digest), then the recipe's step on a local Gitea PR. Not a CircleCI run | job `circleci` 133230350272: `GO: demo-circleci — config NOT validated (CircleCI's API asked for a token; CIRCLE_TOKEN unset); the recipe's step posted … as lights-out/circleci on PR #1, 59s`. The config was validated anonymously ("Config file … is valid") in runs 43833404799 and 43836791053; the API started asking for a token at run 43840181787 |
| The demo | `engine-compat` (`./go demo` cold on a runner) | job 133230350078: `GO: demo, milestone M9, 787s to rollback (budget 900s)`. Not run locally: another session's demo held the rootful plane slot all session |
| Refactors | `argo` job (cluster.sh's `CLUSTER_ADAPTER`), `jenkins` job (shared `surfaces/gitea-pr.sh`) | both GO on 343fe38 |

## What changed

- `adapters/flagger/`: four verbs, `ready.sh`, `env.sh`, `install.sh` (Flagger + loadtester 0.39.0, sha256 per file), `proof.sh`, README. `app/k8s/flagger/backend.yaml`: Deployment, Canary (`stepWeights [5,25,100]`, interval 10 s, threshold 2), MetricTemplate (canary 5xx rate minus stable's, no traffic = 0), Traefik routes.
- `adapters/argo-rollouts/cluster.sh` takes the controller from `CLUSTER_ADAPTER`; Argo's install moved to `install.sh` unchanged; `@ERROR_RATE_MAX_DELTA@` substituted from `policy/merge.env`.
- `surfaces/gitlab-ci/.gitlab-ci.yml`, `surfaces/circleci/config.yml`, their demos; `surfaces/gitea-pr.sh` shared with `demo-jenkins` (refactor, `jenkins` job green).
- `ci/outside.sh` (b) checks all three recipes (context, line from the wrapper, success only on GO); NO-GO on two planted failures before the recipes were final. `ci/vendor-free.sh` gains `flagger`.
- Make/`./go`: `flagger-conformance`, `flagger-proof`, `demo-gitlab-ci`, `demo-circleci`; CI jobs `flagger`, `gitlab-ci`, `circleci`. Docs: reference, use-on-your-repo "Your CI as a surface", README, plan §4, PLAN M62 (Italian), argo README, prometheus.yml comment.

## What contradicts the brief or the plan (read this)

1. **`confirm-promotion` cannot be lights-out's human gate before 100% with the same suite.** In Flagger (source at v1.45.0, `scheduler.go`) promotion copies the canary into the primary and leaves the canary at weight 0; the port's 100% (ADR 0026, the suite asserts weight 100 after GO) is the canary taking every request. So: the human gate is Flagger's `confirm-traffic-increase` stage gate, which only `./go promote`'s GO opens to 100%; `confirm-promotion` points at `/gate/halt` and holds Flagger's own promotion until a person changes the URL. The owner may want a port verb for "complete" (the M8 decision ADR 0051 §3 already defers).
2. **Two judges, one direction.** Flagger's analysis can roll back a canary the launchpad is still measuring. It can never pass one the launchpad stopped. Its 1-minute window carries a rolled-back canary's errors into the next canary of the same workload (seen: delta 0.14, case b rolled back on case a's errors) — the suite's order keeps them apart; worth watching for flakes in the `flagger` job.
3. **Flagger's kustomize base at v1.45.0 lacks the `traefik.io` RBAC its Helm chart has**: the Canary stayed `Initializing`. `install.sh` adds the chart's rule. Upstream bug, reportable.
4. **gitlab-ci-local is not enough** for the recipe (services do not share the job's build volume); a real runner was used. `docker:dind` runners: not proven.
5. **CircleCI cannot be run locally** for a machine job; the proof is validate + the step, declared "not a CircleCI run" everywhere.
6. GitLab 19 job traces prefix each line with a timestamp and a stream mark.
7. **Flagger zeroes `status.canaryWeight` on entering `WaitingPromotion`** (`setStatusPhase`) while the routes stay at 100%: `status.sh` reports the last step there.
8. **CircleCI's API answered anonymous validation twice, then asked for a token**: a `CIRCLE_TOKEN` secret would make the validation part of the proof deterministic; the owner decides whether to make a CircleCI account for it (no-account rule).

## Still open (out of scope, from M32)

An outside AgentHarness; the full tower on GitLab; a real Jenkins controller. Also: Flagger on a team's cluster or another router; a dind GitLab runner; a real CircleCI run (needs an account).

## Site text (for whoever owns `site/index.html`)

> **Your CI/CD, not ours.** Envoy and Compose are the default, not a requirement. `DELIVERY=flagger` keeps Flagger's own analysis and automatic rollback; lights-out opens each step and holds 100% for a human GO (`./go flagger-conformance`, `./go flagger-proof`). GitLab CI and CircleCI join Jenkins as surfaces: each posts the gates' one line under its own status (`lights-out/gitlab-ci`, `lights-out/circleci`) and never judges. GitLab CI proven with a real runner; CircleCI validated and its step run, not a CircleCI run.

Truth list additions: "Flagger: proven on k3s on Actions (suite + own rollback + held promotion)"; "GitLab CI: proven with gitlab-runner on a local GitLab"; "CircleCI: config validated and step run; not run on CircleCI".

## Next

The coordinator merges with `--no-ff`; expect conflicts in `docs/PLAN.md` (the "Sprint 2026-11-16 (M58–M63)" heading is created here too), `docs/reference.md` row tables, `.github/workflows/ci.yml` tail, the Makefile help printf. Clear the context before the next milestone.
