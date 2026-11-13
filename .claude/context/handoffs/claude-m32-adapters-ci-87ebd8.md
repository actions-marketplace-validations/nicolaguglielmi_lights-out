# Handoff — M32, outside adapters, other CIs as surfaces, GitLab (ADR 0058)

Branch `claude/m32-adapters-ci-87ebd8`, cut from main at d1390ba. Not merged.

## Acceptance, as run (2026-11-13, from a full clone under `.crew/`)

- Outside adapter refused, then accepted: `./go ci-outside` →
  `GO: outside — an outside StateStore refused, proven, admitted, refused again on one byte; Jenkins posts under lights-out/jenkins, the tower under gates review`.
  The refusal, by hand: `Makefile:51: *** STATE_STORE=outside/json-files is refused: sha256 267adb317a89 has no statestore-conformance GO on record for its suite as it is; run ./go statestore-conformance STATE_STORE=outside/json-files.  Stop.`
- `./go demo-jenkins` →
  `GO: demo-jenkins — Jenkinsfile Runner posted [GO: gates — risk low, auto-merge, in workbench] as lights-out/jenkins on PR #1, 239s` (agent image cached).
- `./go gitlab-conformance` (cold instance) →
  `GO: codehost-conformance — gitlab, PR #1 merged`, 10 min 46 s wall, serving after ~245 s.
- `./go ci` → GO (52 checks).
- `./go demo` → `GO: demo, milestone M9, 759s to rollback`, then `663s` on a second run; main at d1390ba, run between the two on the same VM, `732s`. Noise from other sessions on the VM, not this branch: its demo-path cost is `ci-outside`, under 2 s.

GitHub at 8ad72aa, after merging main at b75dea8 (M51 and the opentelemetry
1.45.2 fix): package, self, podman, stranger and ci green, every ci job
included (gitlab, now through core.gates.codehost, and jenkins). The merge's
one conflict was gates/codehost-conformance.sh: M51's wrapper, which now also
hands CODEHOST_SECRET to the suite in CONFORMANCE_SECRETS (21 code lines);
ci/outside.sh's "the tower reads no status" excludes core/gates/, the suites.

## What changed

- `core/adapters.py` (+34 unit tests): tree hash, trial/register/untrial, admit; the Makefile admits at parse time and stops in one `$(error)` line; four suite targets go through `conform` (trial, gate, register on GO). `./go` mounts `ADAPTERS_PATH`. `ci/outside.sh` proves it cold with `fixtures/outside-adapters/json-files`.
- `adapters/gitlab/` (eight verbs, ready, instance.sh, compose.yaml) and `./go gitlab-conformance`; the codehost suite's case 10 also reads `CODEHOST_SECRET`.
- `surfaces/jenkins/` (Jenkinsfile recipe, agent Containerfile, host-side demo.sh) and `./go demo-jenkins`.
- CI: jobs `gitlab` and `jenkins` in ci.yml; `outside` in CI_CHECKS; `gitlab` in vendor-free's word list.
- ADR 0058; README, reference, use-on-your-repo, site "real" list, PLAN §4 and M32 status, ROADMAP.

## Against docs/PLAN.md

- Jenkinsfile Runner exists but is stale: last release 1.0-beta-32 (2023-11), the only official image pushed 2022-07-29, amd64 only, Java 8. Used as is, pinned by digest; recorded in ADR 0058.
- GitLab CE needs ~2.4 GB: it does not fit beside the plane on this VM, so the tower on GitLab is not proven. A first cold run beside an emulated build hung the podman VM for minutes.
- Jenkins drops build parameters on a job's first run: the recipe uses environment variables.
- On a docker runner the agent must run as the workspace's owner (as ./go runs the workbench), or git in the gates container refuses the repository.
- AgentHarness outside adapters are left: harness-conformance builds images through compose and is not wired to trial/register.
- Flagger (v1.45.0) not built, left. GitLab CI / CircleCI recipes not written.

## Next

- Wire an outside CodeHost/Delivery/EventBus adapter through its suite once (they are "not proven").
- Merge conflicts to expect: Makefile CI_CHECKS line, the conformance targets (M51 moves gates/ to Python), docs/PLAN.md notes, README "Toward production".
