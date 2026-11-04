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
