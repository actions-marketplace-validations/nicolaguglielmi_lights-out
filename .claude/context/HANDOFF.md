# Handoff: launch readiness, 2026-11-04, branch `claude/compassionate-cerf-t5kc8v`, pushed, no pull request, not merged

The parent session merges through `merge/<name>` after Actions is green. No pull request, tag, release or GitHub issue was created; the repository is still private. The branch starts at `main` d5d089c (M21 and M23 merged). `compose.yaml` (root) is not touched: the item 7 fix is in the workload fragments.

## Acceptance, on GitHub Actions

```
ci 41858183100 (1a1baf1, the last code and docs commit): success
  ci                   ./go ci → GO: ci
  engine-compat        GO: demo, milestone M9, 718s to rollback (budget 900s, plan §2)
  gates, launch, seam, init, harness-conformance: success
  (the Action test's "broken test, NO-GO expected" check run is red by design, M23 finding 9)
ci 41857554465 (230111f, items 6 and 7): success, all seven jobs
```

Nothing ran locally on an engine: this session has no docker daemon and no egress for image builds. The new verdict branch of `make demo` was run on its own, on the host, against a copy of the recipe: first run outside CI over budget → GO with the time, exit 0; first run with CI set → NO-GO, exit 2; later run over budget → NO-GO; under budget → the usual GO line. A GitHub run never takes the new branch (CI is set), so Actions proves only that nothing else changed.

## What changed

- **Ticket 0010, item 6** (34895bc, ADR 0013 amendment 2026-11-04): `./go` marks a run that had to build the workbench as a first run (`LIGHTS_OUT_FIRST_RUN`) and passes the host's `CI` as `LIGHTS_OUT_CI` (its own name, so no tool in the workbench changes behaviour). `make demo` keeps the verdict: outside CI, a first run over 900 s prints `GO: demo, milestone M9, <n>s to rollback, a first run: over the 900s budget, reported, not judged (...)`; CI and every later run are judged as before. README's troubleshooting table has a row for each line.
- **Ticket 0010, item 7** (230111f): the guess was wrong. In the two `launch` failures with logs (41710407450, 41821734075) Envoy started and initialised its clusters; the backend died at import with `ProviderNotReadyError: Blocking init finished before data synced`, because flagd's sync did not answer within the provider's 500 ms default (`openfeature-provider-flagd` 0.5.2, `DEFAULT_DEADLINE`, read in the wheel), and nothing restarted it. `restart: on-failure` on `backend` and `backend-canary` in `app/compose.yaml` and `workloads/minimal/.lights-out/compose.yaml`. The failure is intermittent: one green run does not prove the fix, the next red `launch` with these logs would. `seam`'s failure in 41829488115 (attempt 1) had the same symptom, but that job prints no container logs.
- **Ticket 0010 closed** (5f48d7e), every item with its commit or ADR; its perimeter now lists the files actually touched. `.gitignore` ignores `.DS_Store`.
- **`ROADMAP.md`** (9e86b5f): M18, M20, M21, M22, M23 in Done, one line each from ADRs 0040, 0042–0045 and plan §16's status notes (0042, 0044, 0045 marked *proposed*, as their status says); Next is M24 with plan §14's exit criterion, after egress for the harnesses and the tower restoring `.lights-out/runners/` from the base.
- **`docs/launch/checklist.md`** and **`docs/launch/good-first-issues.md`** (1a1baf1).

## What the owner must do

All of it is in `docs/launch/checklist.md`, each line with its command or setting. In short:

1. Merge this branch and the two parallel sessions (egress, the tower's `runners/`).
2. The key-spending runs: the two harness recordings and the non-Gemini `record-evals` (then the cost per provider in the README); M21's throwaway repository, token, `./go e2e CODE_HOST=github PROFILE=l1`, and the nightly's variable `LIGHTS_OUT_GITHUB_REPO` and secret `LIGHTS_OUT_GITHUB_TOKEN`.
3. `git tag v0.1.0 && git push origin v0.1.0`, the package made public, the release notes, then `uses: nicolaguglielmi/lights-out/action@v0.1.0` on another repository.
4. The rollback recording for the README; description, topics, social preview, Discussions, private vulnerability reporting; the labels, then the good first issues.
5. The soft launch to 10–20 people, `./go demo` on Linux and macOS, and only then the visibility flip.

## Found

1. **`main`'s last run, 41846872298 (d5d089c), failed `engine-compat`** on something else: `await-gitea: image on <merge> still pending after 300s`, the Gitea `image` job never ran; the runner log is many `Cannot ping the Gitea instance server` lines, then `Runner registered successfully`. Not in this task's perimeter and not investigated further. It did not recur on this branch.
2. **The good-first-issue drafts include a guard gap** (gemini-cli's `BeforeTool` matcher misses four file tools, HANDOFF M19). The container stays the boundary, but the owner may want it fixed before launch rather than filed publicly.
3. **`workloads/minimal/.lights-out/worker.md` line 9 calls `tests/mutation/` and `tests/sast/` "the gate runners"**, against ADR 0020 §6's rule; `ci/prompts.sh` does not read `worker.md` (good first issue 8).
4. The checklist's private-vulnerability-reporting line comes from `SECURITY.md`, outside the sources the brief named, and says so.

---

# Handoff: the tower judges an attached PR with its base's runners/, 2026-11-04, branch `claude/upbeat-cori-u7ddcv`, pushed, no pull request, not merged

Closes M23's finding 2 (below, "Contradictions with the plan"): `core/steps/ci.sh` restored an attached PR's `.lights-out/workload.env` and `policy.env` from the base, but not `runners/`, so the sast and mutation verdicts came from the PR's own runners. The parent session merges through a `merge/<name>` branch.

## What changed

- **`core/steps/ci.sh`**: both judges lists gain `${contract}runners`. Attached: `workload.env policy.env runners`, the wrapper's set (`package/entrypoint.sh`, ADR 0045 §3), not a second one. Bundled: the same three after `Makefile profiles gates ci core policy`, costless (no bundled contract has `runners/`; a judge neither side has is left out of the pathspec). Restore stays no-overlay: a `runners/` the PR adds and the base lacks is removed.
- **ADR 0033**, an amendment of 2026-11-04 (the architect's; an amendment, not a new ADR, since it completes 0033's own rule and 0046/0047 are being taken by parallel sessions): the contract's judges are exactly `workload.env`, `policy.env`, `runners/`; not `worker.md`, `tickets/` or the plane half, one reason each; §3 now names `ci/tower.sh` case (h) (it said (g)). ADR 0045's note on the gap points at the amendment.
- **`ci/attach.sh` case (f)** (the gate-writer's, written from the amendment): the base's contract has `TOOLCHAIN_IMAGE=workbench`, `SAST_CMD=sh .lights-out/runners/sast.sh` and a runner reporting one finding; the PR (perimeter: the runner) rewrites it to report none. Premise: the head's own `SAST_CMD` prints `{"findings": 0}`. Verdict: the real step returns `ci-failed NO-GO sast` with a line naming the base's finding. The `sast` gate is an in-process **stand-in** in the case's platform root, said in the case: the real gate runs under the step's `TOOLCHAIN_ISOLATE=1`, which needs the engine socket `./go ci` does not mount, so it would NO-GO on the socket and pass the case for the wrong reason. With `${contract}runners` removed from the attached list the case fails (`NO-GO: attach — case f disagrees with docs/adr/0037 or 0033`; the step then said `review GO`).
- **Docs**: `docs/use-on-your-repo.md` (the status table row and section 3: a PR is judged by the base's `policy.env`, `workload.env` and `runners/`), `docs/reference.md` (the attach paragraph), `docs/PLAN.md` §16 (an Italian note under M23).

## Proven

Locally (no engine in this session): `sh ci/attach.sh` → `GO: attach`, and `NO-GO` on case f with the fix reverted; `sh ci/tower.sh` → `GO: tower`; `sh ci/contract.sh` → `GO: contract`.

On GitHub Actions, workflow `ci`:

```
ci 41861742824 (a0f96d8, the last code commit): success on every job —
  ci (./go ci, with ci/attach.sh case f), engine-compat (./go demo), gates (./go demo-gates),
  launch, init (./go demo-init), harness-conformance on attempt 1;
  seam (./go demo-seam) on attempt 2: attempt 1 failed pulling the Gitea image
  (docker.gitea.com: connection reset by peer), before any of this branch's code ran
ci 41858143391 (c474458): failure — ci and engine-compat on ci-shell, shellcheck SC2015
  in the new case (fixed in a0f96d8)
ci 41857856995 (c55cbdd): success; ci 41857040896 (7695192): success
```

## Contradictions with the plan, and things found

1. **Runners outside `.lights-out/runners/` are still the PR's**: the bundled app's and `workloads/minimal`'s `SAST_CMD=sh tests/sast/run.sh`, `MUTATION_CMD=sh tests/mutation/run.sh`. That is ADR 0033's build surface, left to the PR on purpose; an edit there is always high (`RISK_HIGH_PLATFORM` lists `*tests/sast/*` and `*tests/mutation/*`, not overridable), so it never auto-merges, but its sast/mutation GO is the PR's own claim and the reviewer must not read it as evidence (ADR 0033 amendment, Consequences).
2. **The same three paths live in two places**, `core/steps/ci.sh` and `package/entrypoint.sh`. A fourth judge must be added to both; each test names only its own paths.
3. **Case (f) proves the restore, not the real sast gate under isolation**: no cold check can run that without an engine. The end-to-end proof of the isolated sast gate on an attached PR stays with the engine jobs.
4. A legitimate runner change (a new bandit pin) is judged by the old runner and takes effect from the next PR.
5. The first push of case (f) failed `ci-shell` on shellcheck SC2015 (run 41858143391, jobs `ci` and `engine-compat`): this session had no shellcheck. Fixed in a0f96d8.

---

# Handoff: M23 "one command, one package", 2026-11-04, branch `claude/kind-gauss-tzw1q7`, pushed, no pull request, not merged

The owner reviews and merges (the parent session resolves the expected conflicts with M21 on `Makefile`, `go`, README and `docs/PLAN.md`). Plan: `docs/PLAN.md` §16 M23 (status note added); decision: `docs/adr/0045-one-command-one-package.md`; file-by-file plan: `docs/plans/m23.md` (committed before the build, plan mode was not available).

## Acceptance, run for real on GitHub Actions (docker, ubuntu-latest)

The cloud session had docker, but Docker Hub rate-limited it and its egress is a TLS proxy (`deps` could not reach api.osv.dev from a container), so every engine proof below is from Actions. Local runs used a CA-patched copy of the workbench in the session's scratchpad only; nothing of it is in the repository.

```
package run 41826312637 (commit d7ba966), job package (126561824769):
  ./go demo-package → GO: demo-package — init and gates 51s in workbench (budget 300s),
                      a staged break NO-GO at test, image localhost/lights-out:dev
    on the way: lights-out gates on the committed compose:backend-test contract →
      NO-GO: gates — TOOLCHAIN_IMAGE=compose:backend-test needs the engine socket, which the
      lights-out image never gets (docs/adr/0045 §3); judge it from a clone with ./go gates, ...
    GO: init — python, draft in <out>/.lights-out, baseline 1.0 (8/8 mutants killed, 27s, in workbench)
    [lights-out] the contract that judges is the base's, 9a4efbd
    GO: gates — risk low, auto-merge, in workbench (51s for init and gates)
    staged, breaking a test: NO-GO: gates — test: NO-GO: test — in workbench: the test command failed (exit 1)
  image localhost/lights-out:dev, 1.77 GB, built in about 60 s on the runner

package run 41826312637, job action (126561824256): uses: ./action on a scratch repository
  good: GO: gates — risk low, auto-merge, in workbench
        → check run "lights-out gates (Action test: a good change, GO expected)" success (126562736955)
  bad:  NO-GO: gates — test: NO-GO: test — in workbench: the test command failed (exit 1), see stderr
        → check run "lights-out gates (Action test: a broken test, NO-GO expected)" failure (126562846010),
          the Action step failed, as it must

ci run 41824848177 (commit 9c6145c, the first with the package): ci, engine-compat, gates, init,
  seam, launch, harness-conformance all success;
  engine-compat: GO: demo, milestone M9, 689s to rollback (budget 900s, plan §2)
ci run 41825221364 (fecc782): success
```

Final commit 4c1012e: see "Runs on the final commit" at the end.

`./go ci` gains `ci/package.sh` (the gate-writer's, from ADR 0045 §8): `GO: package` and `GO: ci` in the workbench, and the `ci` job of run 41831535100 below.

## What changed

- **The image** (ADR 0045 §1): `package/build.sh <engine> <tag>` assembles one context, the workbench's three inputs, `git archive HEAD` under `lights-out/`, and `workbench/Containerfile` + `package/Containerfile.tail`; podman, docker and `docker buildx --platform` build the same file, and only committed files enter. `package/entrypoint.sh` is the image's entrypoint. `./go package` builds `localhost/lights-out:dev`.
- **The wrapper** `lights-out` (POSIX sh, repo root): `init gates triage postmortem doctor version`, a `KEY=VALUE` allowlist, the repository read-only at `/repo`, one output directory (`~/.local/state/lights-out/<repo>`, `LIGHTS_OUT_OUT`), `--security-opt label=disable` (never `:z`), keys by name from the environment, never `.env`, never the engine socket. Inside: a range is judged by the contract at its base (`workload.env`, `policy.env`, `runners/`, no-overlay); `STAGED=1` judges the staged diff as one commit; `init` copies the draft to the output directory; make's exit 2 leaves as 1.
- **`./go doctor`** (`core/doctor.sh`, host-side, before ./go needs an engine): engine, podman API socket, git, workbench image, the plane's ports, the key the profile needs (named from `adapters/*/conformance.env`, so `core/` names no key), then one verdict line.
- **The Action** `action/action.yml` (composite): runs `$GITHUB_ACTION_PATH/../lights-out gates`, posts a check run (`name` input, default `lights-out gates`) after the container exits, `contents: read` + `checks: write`; fork PRs warn. **Workflow** `.github/workflows/package.yml`: `package` and `action` on every push, `publish` on a `v*` tag (must equal the wrapper's `version=`) or a dispatch only, amd64+arm64 with QEMU and buildx, `packages: write` on that job only; every job GitHub-only (ADR 0039).
- **Docs**: README (the wrapper as the developer's first command after the demo, `./go doctor` first in "If something goes wrong", what is real), `docs/reference.md`, `docs/use-on-your-repo.md` (the wrapper path, section 5: the Action and the hook recipes for Claude Code, Codex, Gemini CLI).

## What the owner must do to publish

Nothing is published: no tag was created, no dispatch was run, the package does not exist on ghcr.io.

1. Merge the branch (the version is `0.1.0`, the `version=` line of `lights-out`; change it first if you want another).
2. Push the tag from the merge: `git tag v0.1.0 && git push origin v0.1.0`. The `publish` job checks the tag equals `v$version`, builds amd64 and arm64 through QEMU, and pushes `ghcr.io/nicolaguglielmi/lights-out:0.1.0`. A manual dispatch instead pushes `:sha-<commit>`. The multi-platform build has **never run**: expect it to be slow (the workbench under QEMU for arm64) and the first place to look if it fails.
3. The package is private, linked to the repository by the `org.opencontainers.image.source` label. To let anyone pull it: GitHub → the package → Package settings → Change visibility → Public. While the repository is private, the raw URL of `lights-out` does not work for strangers either.
4. Then the plan's original criterion can be proven: a PR on another repository with `uses: nicolaguglielmi/lights-out/action@v0.1.0`, and `lights-out gates` on a clean machine pulling the published image (the 300 s does not count the first pull, about 1.8 GB uncompressed).

## Contradictions with the plan, and things found

1. **The criterion "the Action green on a PR of the example repository" cannot be met before publishing**: `@<tag>` needs the image on ghcr.io and the action at a tag. It is proven in lights-out's own workflow with `uses: ./action` instead (ADR 0045 §8 amends plan §16).
2. **The gates judged a range with HEAD's contract** in the first design: a PR could set `TEST_CMD=true` and pass. The architect caught it; the wrapper restores the base's contract. **The tower has the same gap for `runners/`**: `core/steps/ci.sh` restores `workload.env` and `policy.env` from the base but not `runners/` (ADR 0042 came after ADR 0037 §4); the risk gate's `.lights-out/*` → high still stops an auto-merge. It needs its own fix.
3. **Only `TOOLCHAIN_IMAGE=workbench` works through the wrapper**, by decision (no socket ever). `workloads/minimal`'s committed contract (`compose:backend-test`) gets a NO-GO through it, said in the line.
4. **The image is the whole workbench, 1.77 GB** (gcloud, terraform, litellm) for four commands; a slimmer image is a second set of pins (ADR 0045, rejected for now).
5. **Every run is cold**: each hook run reinstalls the repository's dependencies and the stack runners (about 50 s on minimal). A cache under the output directory is the first fix if hooks drag.
6. **Hook recipes**: Claude Code's shape was read from its docs; Codex's shell tool name, whether its project hooks deny with exit 2 once trusted, and whether Gemini CLI loads hooks in an untrusted folder are **not verified**, and the doc says so. None of the three recipes was run against a real CLI.
7. The gate-writer also found, and left as is: the wrapper accepts `help`/`-h`/`--help` (exit 0, usage), not in the ADR; `triage` and `postmortem` mount the current directory, not the top level (the ADR sentence is ambiguous; file arguments are paths under the current directory); with no engine, doctor prints no workbench line.
8. The first `demo-package` change (a key added to `/healthz`) was rightly NO-GO at test: an existing test asserts the body exactly. The gates work; the demo now adds a `/version` route with its test.
9. The checks API returns only the latest check run per name unless `filter=all`: the Action test now posts each case under its own name. The expected-NO-GO check run is red on every branch commit by design, and its name says so.

## The first thing the next milestone should look at

M21 merges with this on `Makefile`, `go`, README and `docs/PLAN.md`. Then the owner's publish (above) and the first real PR on another repository through `@v0.1.0`; the tower's `runners/` gap (finding 2) before M24 runs on a repository the owner does not control.

Clear the context before the next milestone.

## Runs on the final code commit (4c1012e) and the handoff commit (b537222)

```
ci      41831535100 (4c1012e): success — ci (./go ci with ci/package.sh), engine-compat (./go demo),
                               gates, init, seam, launch, harness-conformance
package 41831535098 (4c1012e): success — package (./go demo-package), action (GO and NO-GO check runs)
package 41831657158 (b537222): success
ci      41831657167 (b537222): running when this was written; docs only since 4c1012e
```

---

# Handoff: M21 "GitHub as code host, release of an attached repository", 2026-11-04, branch `claude/beautiful-darwin-kxrm8m`, pushed, not merged, no pull request

The owner, or the parent session, reviews and merges. Plan: `docs/PLAN.md` §16 M21 (status note added); decision: `docs/adr/0043-github-code-host-and-attached-release.md` (accepted); file-by-file plan: `docs/plans/m21.md`. The branch starts at `main` d903a85.

## Acceptance, run for real

GitHub Actions, workflow `ci`, run **41829488115** on commit 8489eb7 (https://github.com/nicolaguglielmi/lights-out/actions/runs/41829488115):

```
ci                   success   ./go ci → 32 checks GO, codehost among them, GO: ci
engine-compat        success   GO: engine-compat, GO: ci, GO: demo-rollback, GO: e2e, GO: audit,
                               GO: demo, milestone M9, 700s to rollback (budget 900s, plan §2)
gates                success   ./go demo-gates
launch               success   GO: demo-launch, then the new step:
                               case 1 bootstrap … case 10 no secret in the captured output: GO
                               (case 8: merge exit 1 on attempt 1 of 3, GO on attempt 2)
                               GO: codehost-conformance — gitea, PR #1 merged
init                 success
harness-conformance  success
seam                 failure on attempt 1 (below), success on the re-run of the failed job (attempt 2)
image                skipped (Gitea-only)
```

Run **41831405824** on the hand-off commit 92bf9c6 (docs only): all seven jobs success on the first attempt, `seam` included; engine-compat `GO: demo, milestone M9, 690s to rollback (budget 900s, plan §2)`.

The `seam` failure: `deploy-envoy-canary: backend-canary reports no answer after 180s, want 0.2.0-outage`, so the canary never answered in staging. `seam` drives `make release` directly and touches nothing M21 changed. It passed on the previous push, 41824209894.

Earlier runs on this branch (41823357054, 41823941895, 41824209894) failed `ci` and `engine-compat` only because the Makefile already listed `codehost` before `ci/codehost.sh` was committed.

Locally, in this cloud session:
- **Engine.** The docker daemon could be started.
- **Workbench image.** Image builds have no egress without the session proxy's CA, so I built the workbench image once from a scratchpad copy of `workbench/Containerfile` with that CA appended. That copy is not committed, and it carries the same tag `./go` computes.
- **`./go ci`.** It ran on that image: `GO: ci`, 32 checks, 3m56s.
- **The plane.** It cannot start here, because every plane image build needs the same egress.

Not run, by design (no token in this session):
- `./go e2e CODE_HOST=github PROFILE=l1`.
- The nightly against GitHub.

The GitHub adapter's read-only verbs were tried against this repository through the session proxy:
- `ready.sh` succeeded.
- `pr.sh 999999` gave a 404 line.
- `await.sh` printed its timeout line.

Nothing was written to GitHub.

## What changed

- **`adapters/github/`.** The eight CodeHost verbs plus `ready.sh`, `env.sh` and `credential.sh`, on the REST API, API version 2022-11-28.
  - The token goes to curl on stdin (`-H @-`).
  - git gets it from a credential helper that the Makefile appends as env-scoped config (`GIT_CONFIG_KEY_1`, after the workbench's `safe.directory`).
  - It never goes in argv, a `.git/config` or a harness container.
- **`core/steps/release.sh`.** For an attached repository, on any code host, the merge is:
  1. fetched from the default branch;
  2. checked out in a `mktemp -d` worktree;
  3. built by its own `.lights-out/compose.yaml` `backend` (its Containerfile), pushed and signed by `make publish`;
  4. verified by the unchanged launchpad.

  The bundled app still waits for the Gitea `image` job.
- **Proof.**
  - `ci/codehost.sh` in `./go ci`. It is cold: curl and git are recorders, there is no fake GitHub, and it has 27 defect self-tests.
  - `gates/codehost-conformance.sh`, ten cases, as `./go codehost-conformance`. It runs against Gitea in `launch` on every push.
  - `.github/workflows/nightly-github.yml` runs it against GitHub daily, and skips with a notice while `vars.LIGHTS_OUT_GITHUB_REPO` is unset.
- **Other repository changes.**
  - `ci/vendor-free.sh` bans `gitea|github` in `core/`. Two core headers that named Gitea while claiming not to were reworded.
  - `.env.example` and the gitleaks `.env` allowlist name `GITHUB_REPO` and `GITHUB_TOKEN`.
  - `ci/attach.sh`'s `as_ci` drops them.
  - `workloads/minimal` carries ticket 0001 (`GET /version`) for the owner's run.
- **Docs.** README, `docs/reference.md`, `docs/ARCHITECTURE.md`, `docs/use-on-your-repo.md` (new section "Your PR on GitHub (L1)"), and `docs/PLAN.md` §3, §4 and §16 status note.

## Found (contradicts the plan or the brief)

1. **`TOOLCHAIN_IMAGE` is not a release artefact.** Plan §16 M21 says "con il Containerfile del repo (o TOOLCHAIN_IMAGE)". A toolchain image holds no application. The release builds the contract's `backend` service, and a workload without `.lights-out/compose.yaml` has no release (ADR 0043 §4).
2. **"The nightly is green" proves the eight verbs, not the tower on GitHub.**
   - The nightly runs the conformance suite with a token only.
   - The full e2e needs a model key and the whole plane, and model variance would make the nightly red for reasons that are not the adapter's.
   - The e2e on GitHub is the owner's one-time run (ADR 0043 §5).
3. **The attached release path has never run anywhere.** No CI job reaches it:
   - an attached repository has no recordings, so its e2e at L0 is refused (ADR 0037 §8);
   - `demo-seam` calls `make release` directly, not the tower.

   The owner's L1 e2e is its first execution, on Gitea or GitHub alike.
4. **`CODE_HOST=github` serves only an attached repository, and goes on the command line, not in `.env`.** In `.env` it would also redirect `./go demo`.
   - Bootstrap pushes nothing to the user's repository. It refuses unless the attached clone's HEAD is the default branch's head.
   - So after every merged ticket the owner pulls and runs `./go attach` again.
5. **On GitHub, a merge commit can contain base commits no gate judged** (humans push to the default branch). Making `gates` a required, up-to-date check turns that into a 405 before merge (ADR 0043, consequences).
6. **Gitea's merge right after a push fails once.** Conformance case 8 needed its second attempt, 5 s later. Mergeability is computed after the push. The tower's merge step does not retry, but at L0 the CI step runs for minutes between push and merge, so it has never hit this. The suite's retry (3 × 5 s) is the gate-writer's decision, written in the gate's header.
7. **GitHub facts not verified on docs.github.com, which this session could not reach.** The architect read GitHub's own reference data (`github/docs` `src/rest/data/fpt-2022-11-28`) and octokit's docs instead. Unverified:
   - the 140-character status description limit (secondary source: Zuul);
   - whether `permissions.push` reflects a fine-grained token's grants, which is why bootstrap does not check it.
8. **The execution plan's "a cloud environment refuses the egress image builds need" is half true.** docker runs here, and the workbench builds with the session proxy's CA added. The plane's many image builds were not attempted that way. Every engine proof above is from Actions.

## What the owner must do

1. **The throwaway repository.** Create an empty GitHub repository. Copy `workloads/minimal/`'s contents to its root, commit and push. Merge commits must be allowed, which is GitHub's default.
2. **The token.** github.com → Settings → Developer settings → Fine-grained tokens. Only that repository. Contents, Pull requests and Commit statuses, read and write.
3. **The one L1 run.** In `.env`: `GITHUB_REPO=<owner>/<name>`, `GITHUB_TOKEN=…`, `GEMINI_API_KEY=…`. Clone the throwaway locally, then:
   ```
   ./go attach <clone>
   ./go e2e CODE_HOST=github PROFILE=l1
   ```
   **Expected:** the PR opens on GitHub with the `gates` status, merges after `GO: gates`, and the merge is built, signed and released on the local plane. The canary (0.2.0-outage) rolls back, and `GO: e2e` follows the audit cross-checking GitHub. Record the result in plan §16 M21.

   **Afterwards:** pull the clone and run `./go attach` again before any other ticket.
4. **The nightly.** In this repository's settings, set the variable `LIGHTS_OUT_GITHUB_REPO` and the secret `LIGHTS_OUT_GITHUB_TOKEN`. A scheduled workflow runs from the default branch, so it starts after the merge to `main`; run it once by hand with `workflow_dispatch`. Each run leaves a merged PR and a `conformance/<id>` branch in the throwaway repository.

## Next

M23 is running in a sibling session. Expect conflicts on the Makefile (`CI_CHECKS`, new targets), `go` (header and socket list), README and `docs/PLAN.md`. The parent session resolves them on `merge/M21`.

M24 starts when M19 and M21 are merged. Its first look should be finding 3: the owner's L1 e2e is the only execution of the attached release, so run it before M24 attaches a real repository.

Clear the context before the next milestone.

---

# Handoff: M19 "claude-code and codex harnesses", 2026-11-04, branch `claude/xenodochial-chaum-7241fa`, not pushed, not merged

The owner reviews. Plan: `docs/PLAN.md` §16 M19 (status note added); decision: `docs/adr/0041-claude-code-and-codex-harnesses.md`. The branch starts with a fast-forward to local `main` at 06047b8 (M18 and M20 merged); the session's worktree had been cut before them.

## Acceptance, run for real

All on 2026-11-04 from a full clone of the branch at `<worktree>/.crew/m19` (`./go` cannot drive git from a `.claude/worktrees` checkout), on the owner's machine (podman machine, aarch64, 4 GiB), with the shared plane empty (M22's demo had finished; the plane this session started was taken down after).

```
./go harness-conformance → GO: harness-conformance — claude-code codex gemini-cli, against a
                           scripted model, 144 s (2:55 with the image builds warm)
                           preceded by GO: harness-conformance-proof (the suite refuses 17 broken fakes)
                           per harness, cases 0-8; the budget cases print
                           over MAX_TURNS (2) / over TOKEN_BUDGET (2500) / over TIMEOUT_S (30 s)
./go ci                  → GO: ci, 87 s, 29 checks, harness-shape and the 132-run hooks among them
./go demo                → GO: demo, milestone M9, 422s to rollback (budget 900s, plan §2), clean clone,
                           APP_PORT=9000 in .env, no key
./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=claude-code MODEL_PROVIDER=anthropic \
    MODEL=claude-sonnet-5-5 MODEL_BASE_URL=http://example.invalid
                         → NO-GO: record — MODEL_BASE_URL is set: a run against a scripted or proxied
                           endpoint is never a fixture (docs/adr/0041 §7)
```

Each harness also ran alone first (`CONFORMANCE_HARNESS=claude-code` 59 s, `codex` 76 s); both failed once and were fixed (findings 5 and 6). Codex passed case 3's code-mode JS read: the second canary never reached the scripted model, so the Fable task ADR 0041 §3 reserved was not needed.

## What changed

- **Two adapters** (ADR 0041 §1–§6): `adapters/claude-code/` (Claude Code 2.1.311, the npm `stable` tag) and `adapters/codex/` (Codex 0.166.0), gemini-cli's shape: lockfile pinning every platform's native binary, Containerfile on `HARNESS_BASE_IMAGE`, entrypoint, `run.sh`, `thinking.env` (`--effort`, `model_reasoning_effort`), `conformance.env`, `hooks/guard.sh` (byte-identical to gemini-cli's) and a budget hook each. One provider per harness; `run.json` carries the served model (Claude: the assistant messages' `model`; codex: `response.completed` from a trace that never enters `OUT`).
- **gemini-cli first**: the worker mounts only its run directory (OUT's parent) and the uv cache, never `.crew/`; the guard's deny-list is the union of three vendors plus key files and `*_API_KEY`; budget hooks write `OUT/stop` and every `run.sh` prints `over MAX_TURNS|TOKEN_BUDGET|TIMEOUT_S (<n>)`; `MODEL_BASE_URL` is the one seam the suite sets; compose.yaml's three worker services share `x-crew-worker`, as does `app/compose.yaml`'s Postgres fragment; `RISK_HIGH_PLATFORM` gains `.claude/*`, `.codex/*`, `CLAUDE.md`, `AGENTS.md`.
- **The suite** (written by the gate-writer from the ADR, not the adapters): `gates/harness-conformance.sh` (nine cases), `gates/harness-conformance/stub.py` (one scripted model, three wire protocols, `<requested>-conformance` served), `proof.sh`, compose service `conformance-model`; `./go harness-conformance [CONFORMANCE_HARNESS=]`; a GitHub job. `./go ci` gets `ci/harness-shape.sh` and `ci/hooks.sh` in three input shapes.
- **Record**: `record` and `record-review` take any CLI harness; a non-gemini harness writes `fixtures/<ticket>/<role>/<harness>/`; both refuse `replay` and a set `MODEL_BASE_URL`.
- **Docs**: README "Coding harnesses" (table: guard in the hook, boundary the container, codex's sandbox off), `docs/reference.md`, `docs/ARCHITECTURE.md`, `docs/PLAN.md` §4 and §16 status note, `docs/use-on-your-repo.md`, `.env.example`, `ROADMAP.md`.

## Found (contradicts the plan or the brief)

1. **All three CLIs have hooks that fire headless**, so the plan's "where a vendor has no hooks, the guard is the container" never applies; the network stays open for all three (each must reach its provider) and closing egress is open before M24 runs on a repository the owner does not control (ADR 0041 §3).
2. **Codex's own sandbox cannot start in rootless podman** (bubblewrap, three ways tried); codex runs `danger-full-access` with the container as its sandbox.
3. **The suite is not inside `./go ci`**: `ci` has no engine socket and the suite builds three CLI images. `ci` runs the engine-free half; the full suite is `./go harness-conformance` and a workflow job (ADR 0041 §9).
4. **Three guard bypasses, older than M19, closed**: a repository's `.env` pointed gemini-cli's `GOOGLE_GEMINI_BASE_URL`, key included, at another host (now always set); a repository's `.claude/settings.json` with `disableAllHooks` and its `.codex/config.toml` with `[features] hooks = false` each switched the guard off (now `--setting-sources user` and `--enable hooks`; conformance case 4 proves it); the worker mounted `.crew/` with the release signing key `.crew/cosign.key`.
5. **Claude Code's session file lags the run**: a token budget read from `transcript_path` stopped three requests late; the hook now reads the stream-json output on PreToolUse.
6. **Codex 0.166.0 sends no top-level `tools`**: they ride in an `additional_tools` input item, in namespaces; the stub reads them there.
7. **gemini-cli refuses a workspace `.env` by itself** ("Path not in workspace") before its BeforeTool hook; case 3 counts such a refusal as stopped, the canary checks unchanged.
8. **The record command must name provider and model** (`MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5`, `openai gpt-6.1-sol`), M18's finding again; and `compose.yaml` alone is not a loadable project, so the suite runs with `workloads/minimal`'s fragment (ADR 0041 §8 corrected).
9. Claude Code refuses `--dangerously-skip-permissions` as root, and the crew service is uid 0 under rootless podman: the adapter uses `--tools`/`--allowedTools` instead (verified as uid 0).

## Not done, and open decisions for the owner

- **The owner's item:** no Claude or OpenAI recording exists. `./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=claude-code MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5` and `./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=codex MODEL_PROVIDER=openai MODEL=gpt-6.1-sol` are implemented and documented, not run: they spend your keys. They write `fixtures/0001/dev-worker/<harness>/`; replay does not read those yet. Their `run.json`s are the first measurement of `MAX_TURNS` and `TOKEN_BUDGET` outside Gemini (the first run may stop on a Gemini-measured budget) and of the per-run cost the README still owes.
- gemini-cli's BeforeTool matcher covers `run_shell_command|write_file|replace|read_file` only; `read_many_files`, `grep_search`, `glob` and `list_directory` reach files without the guard (the gate-writer's finding). Older than M19; matcher `.*` or excluding those tools, with a hook case, is a short follow-up.
- The guard is a deny-list on strings: `grep -r SECRET .` reads a key file without naming it. The container (only the run directory mounted) is the boundary; egress is the open question.
- `ROADMAP.md` still lists M18 and M20 under "Next".
- `.github/workflows/ci.yml`'s `harness-conformance` job has not run on GitHub (nothing pushed).
- Expect conflicts with M22's branch on `compose.yaml`, `Makefile`, `README.md`, `docs/reference.md` and `docs/PLAN.md` §16.

## First thing the next milestone should look at

M24 needs the two recordings above before anything else: run them, read `run.json`'s `tokens`, `turns` and `model`, and re-measure the budgets in `roles/` per provider (ADR 0041 §5). For M21, `adapters/*/run.sh`'s mount of the run directory is the pattern a GitHub token must follow: never in `.crew/`, never in the worker's view.

---

# Handoff: M20 "gates anywhere", 2026-11-03, branch `claude/vibrant-dubinsky-a82fa0`, not pushed, not merged

---

# Handoff: M22 "ops without the plane", 2026-11-04, branch `claude/nostalgic-engelbart-1820af`, not pushed, not merged

The owner reviews. Plan: `docs/PLAN.md` §16 M22 (status note added); decision: `docs/adr/0044-incident-in-postmortem-out.md` (proposed). The branch was fast-forwarded to `main` (06047b8) before work: it had been cut before M18/M20.

## The gap, first

`./go demo-postmortem` does **not** print GO yet, and cannot from this session: the ops-triage recording of the post mortem needs your Gemini key and there is no `.env` with a key in the worktree. It prints, honestly:

```
NO-GO: demo-postmortem — no recording of the ops-triage role for fixtures/incidents/demo-rollback.json; at L0 it replays fixtures/adk/ops-triage, record it with ./go record-postmortem PROFILE=l1
```

What is missing is one command from you, with `GEMINI_API_KEY` in `.env`: `./go record-postmortem PROFILE=l1`. It writes `adapters/adk/agents/ops_triage/evals/postmortem.evalset.json` from `fixtures/incidents/*.json`, records through `record-evals ROLES=ops_triage` (which also re-records the three alert cases under the new prompt), and keeps the evalset only if the eval passes. Commit the evalset and the new `fixtures/adk/ops-triage/*.json`; then `./go demo-postmortem` should print `GO: demo-postmortem` with a fix ticket (never run against a real recording: the GO path is proved by `ci/postmortem.sh` with a stub harness, not by the demo). The incident it replays is real: `fixtures/incidents/demo-rollback.json`, built by `./go incident` from the release record of a real `./go demo-rollback` run (README in that folder has the provenance). No model output is hand-written anywhere.

## Acceptance, run for real

Full clone of the branch at `<worktree>/.crew/m22b`, `APP_PORT=9000`, warm images, a host that was under load (see "Found" 3).

```
./go demo          → GO: demo, milestone M9, 590s to rollback (budget 900s, plan §2); it runs ./go ci first:
                     30 checks GO, among them roles (six), prompts, evals (four tools), postmortem, metrics, contract
./go demo-postmortem → NO-GO: demo-postmortem — no recording … ./go record-postmortem PROFILE=l1   (exit 1, as designed)
./go verify METRICS_URL=http://host.containers.internal:9090 CANARY_VERSION=0.2.0-waitlist STABLE_VERSION=0.1.0-m2
                   → NO-GO: slo — error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000 delta=1.000 max=0.010
                     the same line launchpad recorded for the 5% stage of the run just before (release.json stages[0].verdict, via the prometheus adapter)
./go verify        → metric-shape, unchanged; ./go verify METRICS_URL=… with no versions → NO-GO: slo — CANARY_VERSION and STABLE_VERSION must both be set
```

The verify comparison was made once, right after a `demo-rollback`, inside slo.promql's `[1m]` window; a second try during a live stage did not happen (the image tag moved with the clone's HEAD and `up` had to be redone).

`ci/postmortem.sh` and `ci/metrics.sh` were written by the gate-writer from the ADR, before the implementation existed; against it they first failed on several points (error-message wording, the "Found by" line, `postmortem.json` keys, missing-variable handling, `put.sh` usage), all in the implementation, none in the checks.

## What changed

- `adapters/promql/query.sh` (`METRICS_URL`, `METRICS_AUTH_HEADER` via curl stdin); `adapters/prometheus/query.sh` is its case at `$PLANE_HOST:9090` and ignores an ambient `METRICS_URL`; `./go verify METRICS_URL=…` runs `verify/slo.sh`, otherwise metric-shape as before; `./go demo` passes `METRICS_URL=`.
- `adapters/file/put.sh`: the Tracker's write verb (next id, `- Origin:` makes a re-run file nothing, no `## Perimeter`).
- `ops-triage` gains `file_postmortem` (same role, same prompt; `roles/ops-triage/prompt.md` has an incident section); `core/incident.sh`, `core/postmortem.sh`, `core/postmortem.py`: `./go incident`, `./go postmortem`, anchored timeline (ids the document holds, evidence printed beside each claim), NO-GO P1–P10, tickets through the Tracker.
- `./go demo-postmortem`, `./go record-postmortem`, `fixtures/incidents/`; ci checks `postmortem` and `metrics`; ADR 0044; README, `docs/reference.md`, `docs/ARCHITECTURE.md`, `docs/PLAN.md` (§4 rows, §16 status note).

## Found (contradicts the plan or the brief)

1. The plan's `METRICS_URL=http://prometheus:9090` cannot work for a host-side `./go`: that is a compose name the workbench does not resolve. The plane's case is `http://$PLANE_HOST:9090`.
2. Decisions of mine for you to veto: (a) the evalset lands with the recording, so `./go ci` stays green; (b) `demo-postmortem` writes its tickets to a copy of `tickets/` under `.crew/demo-postmortem/` and runs twice to prove idempotency, instead of into `tickets/` as the done-when says (an untracked `0014.md` per run would take your next number); `./go postmortem` itself writes to `tickets/`.
3. This machine's podman VM is fragile under several sessions: `./go up` failed twice (the backend gave up on flagd at load average ~150), then the machine stopped and I ran `podman machine start`. Nothing else was touched; I `./go down`ed only the planes I started.
4. A fix ticket has no `## Perimeter` (the role never saw the code): `core/perimeter.sh` refuses it until a human adds one. That is the deliberate stop, and "re-enters the tower" means it is a valid ticket, nothing more.
5. An anchored timeline is not a true one: the rule stops invented releases and PRs, not a wrong story about real ones (ADR consequences).
6. `roles/ops-triage/prompt.md` changed, so the three alert recordings replay with a "recorded under a different prompt" line on stderr until re-recorded (the same `record-postmortem` run does it).
7. Attached repositories: `METRICS_URL` and `METRICS_AUTH_HEADER` are `env -u`'d in `ci/attach.sh`.

## First thing the next milestone should look at

The recording (above), then M21/M23 can use `put.sh` and `promql` as they are. If you merge before recording, nothing else is needed; the demo is not a `./go demo` stage.
