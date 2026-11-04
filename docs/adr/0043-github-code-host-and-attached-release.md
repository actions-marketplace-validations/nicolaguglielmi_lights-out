# ADR 0043 — GitHub as a code host: `adapters/github/` with the eight CodeHost verbs on the REST API, the token from `.env` handed to curl on stdin and to git through an env-scoped credential helper, never in argv or a `.git/config`; an attached repository's merge is built, signed and verified by the tower's release step instead of the Gitea `image` job; a conformance suite proves the verbs on Gitea on every push and on GitHub every night

- Status: accepted (amendments listed under "Amends")
- Date: 2026-11-04
- Milestone: M21

## Context

Plan §16 M21: the ticket's PR lands on the user's GitHub repository, is judged by its base (ADR 0033), merged after `GO: gates`, and the merge is built and released on the local plane down to the rollback. L0 stays Gitea. What the code gives us (read in this checkout):

- **Core runs git against the code host itself.** `core/crew.sh` clones `clone-url.sh` and, on a rework, fetches from `origin`; `core/steps/ci.sh` and `review.sh` fetch `ticket/<id>` from the clone URL into `$WORKLOAD`; review clones it again. Gitea's clone URL is anonymous and its repo public, so none of these needed a credential.
- **Gitea's push and bootstrap pass `user:password@` in the URL, in argv** (`adapters/gitea/env.sh`). Acceptable for L0's low-entropy local password, not for a real token.
- **Harness containers get only what `run.sh` lists with `-e`**, and compose gives them only their own provider key. The Makefile's bare `export` puts every `.env` variable in the workbench's environment. The ADK roles run in the workbench, with no shell tool. `./go` forwards no host variable into the workbench.
- **The workbench already uses env-scoped git config.** `workbench/Containerfile` sets `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=safe.directory`, `GIT_CONFIG_VALUE_0=*`.
- **Release waits for the `image` status** (`core/steps/release.sh`, ADR 0025 §5). Only this checkout's workflow posts it, and `adapters/gitea/bootstrap.sh` turns Actions off for an attached repository (ADR 0037 §9). So an attached repository stops at release today, on Gitea too (ADR 0037's consequence that hurts).
- **`.github/workflows/*.yml` is read by the L0 Gitea runner too.** Every job needs `if: github.server_url == 'https://github.com'` (ADR 0039), and `ci/gitea-compat.sh` must pass.
- **`ci/vendor-free.sh` bans Delivery and Flags names in `core/`.** Two `core/` comments say "no Gitea word appears below" and name it (`core/crew.sh:8`, `core/tower.sh:7`). `crew.sh:8` also still claims one Gemini word, but none is left.

## Decision

1. **Configuration.**
   - `.env` gets `GITHUB_TOKEN` and `GITHUB_REPO=<owner>/<name>`. It is not `GITHUB_REPOSITORY`, because Actions sets that one to lights-out itself.
   - `.env.example` carries both lines empty, plus a comment that `CODE_HOST=github` goes on the command line. In `.env` it would also redirect `./go demo`, whose bundled app GitHub refuses (§3).
   - The profiles keep `CODE_HOST=gitea` at L0 and L1.
   - There is no `GITHUB_API`/`GITHUB_URL` knob. `https://api.github.com` and `https://github.com` are literals in the adapter. GitHub Enterprise Server is not in the brief, and adding it later is two lines.
   - Requests send `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28`. That version names the reference data read below.
   - `ci/gitleaks-worktree.toml`'s `.env` entry gains `^GITHUB_TOKEN=` (ADR 0025's scoped precedent).
   - `ci/attach.sh`'s `as_ci` unsets `GITHUB_TOKEN`, `GITHUB_REPO`, `GIT_CONFIG_KEY_1` and `GIT_CONFIG_VALUE_1`, and sets `GIT_CONFIG_COUNT=1`. It does not unset the count: that would drop `safe.directory`.
2. **The token is never in argv, a `.git/config` or a harness container.**
   - **curl.** Every adapter call sends `Authorization: Bearer $GITHUB_TOKEN` as `curl -H @-`, with the line on stdin. This is ADR 0044 §8's mechanism, so the repository keeps one way to do it, not two; that is why it is not `-K -`. The non-secret headers and the JSON body stay in argv.
   - **git.** `adapters/github/credential.sh` is a git credential helper.
     - On `get`, when the input's `protocol=https` and `host=github.com`, it prints `username=x-access-token` and `password=$GITHUB_TOKEN`.
     - For any other host, and for `store` and `erase`, it prints nothing.
   - **Option (a), adapter-generic.** When `adapters/$(CODE_HOST)/credential.sh` exists, the Makefile **appends** one entry to the workbench's env-scoped config: `GIT_CONFIG_COUNT=2`, `GIT_CONFIG_KEY_1=credential.helper`, `GIT_CONFIG_VALUE_1=!sh $(CURDIR)/adapters/$(CODE_HOST)/credential.sh`.
     - Index 0 stays the Containerfile's `safe.directory`, because overwriting it would break git on the mounted checkout. `ci/codehost.sh` asserts that it survives.
     - With the helper set, core's own clone and fetches (crew, ci, review, release) and the adapter's `push.sh` all authenticate the same way. Core gains no verb and no vendor word.
     - Gitea ships no helper, so nothing changes at L0.
   - **Whose token.** The adapter reads `GITHUB_TOKEN` as make hands it down.
     - `.env` is included after the profile, and `./go` forwards no host variable.
     - So a `GITHUB_TOKEN` that a host, a runner or a proxy already carries never reaches the adapter.
     - An empty `.env` line is §3's refusal, never a fallback to someone else's token.
     - The nightly writes `.env` explicitly (§6).
   - **Where it stops.** The workspace's `origin` is the anonymous `https://github.com/<repo>.git`. The worker container gets neither the `GIT_CONFIG_*` variables nor the token, so a push from the model has no credential, besides being denied by the guard.
   - **Version.** `GIT_CONFIG_COUNT` needs git ≥ 2.31. The Containerfile already relies on it.
3. **Verb semantics on GitHub.** The verbs and their arguments and outputs are `adapters/gitea/`'s. Each failure is one stderr line and exit 1. An unset `GITHUB_TOKEN` or `GITHUB_REPO` is a line naming `.env`, with no network call.
   - **`bootstrap.sh` creates and pushes nothing**, because the repository is the user's.
     - The verb's postcondition is unchanged: after it, the code host's base branch head is `git -C "$WORKLOAD" rev-parse HEAD`. Gitea gets there by pushing; GitHub checks it and refuses otherwise.
     - It refuses when `WORKLOAD_ATTACHED` is empty: "`CODE_HOST=github` serves an attached repository: `./go attach <your clone>`".
     - It reads `default_branch` from `GET /repos/{repo}` and that branch's head. If the head differs from the attached clone's HEAD, it refuses: "`<repo>`'s `<branch>` is at X, the attached clone at Y: pull, then `./go attach` again".
   - **`ready.sh`** exists because `up` iterates `PLANE_ADAPTERS`. It is `GET /repos/{repo}` → 200. It does not claim to check push permission: as far as I could read, `permissions` reports the account's role, not a fine-grained token's grants, and the first push proves the grant anyway.
   - **`open-pr.sh`** bases on `default_branch`, not on a hardcoded `main`. It reuses an open PR from the same head.
   - **`status.sh`** truncates `description` to 140 characters. Provenance: external, reported by Zuul's GitHub driver (opendev commit fb6cc99); GitHub's reference gives no limit (read 2026-11-04). The suite posts a 200-character line (§5).
   - **`merge.sh`** sends `PUT /pulls/{n}/merge` with `merge_method=merge` and `sha=<judged head>`.
     - GitHub answers 409 when the head does not match, which merge.sh reports as "head moved".
     - It first checks `pr.sh` and does nothing if the PR is already merged, the idempotency rule of ADR 0019 §9.
     - On a 405, merge.sh reads `pr.sh` again. If the PR is still unmerged, it reports the 405 and names the repository setting "Allow merge commits" and branch protection as the usual causes.
   - **`pr.sh`** maps `merge_commit_sha` to `null` unless `merged`. Before a merge, GitHub fills that field with a test merge, and the audit must not read it as a real merge.
   - **`await.sh`** reads only commit statuses (`GET /commits/{sha}/statuses?per_page=100`, newest first) and takes the first entry for the context.
     - Why statuses: the tower's contexts (`gates`, `review`, `image`) are statuses it posts itself. A check run is another system's verdict, and the tower reads only its own judges (ADR 0033, ADR 0039).
     - On GitHub no core step calls it today (§4). It stays for the port and is proven by the suite.
4. **Release of an attached merge, at any code host.**
   - `core/steps/release.sh` keeps the `image` wait for a bundled workload, so L0 is unchanged.
   - When `WORKLOAD_ATTACHED` is set, it does five things instead:
     1. It fetches `HEAD` of `clone-url.sh` into `$WORKLOAD` and checks that `merge.sha` is an ancestor of `FETCH_HEAD`, or equal to it. It fetches no branch name and no SHA directly, so core stays vendor-free and needs no `allowReachableSHA1InWant`.
     2. It adds a detached worktree at `merge.sha` under `mktemp -d`, as `ci.sh` does. A classic-builder context there already works for `compose:backend-test` in the gates. It is not under `.crew/`, which the worker mounts.
     3. It runs `make publish TAG=sha-<merge> WORKLOAD=<worktree>`. The merge's own `.lights-out/compose.yaml` `backend` service builds the repository's own `Containerfile`; `publish.sh` pushes and signs it.
     4. It removes the worktree.
     5. It runs the unchanged `make release CANARY_TAG=sha-<merge>`, whose launchpad verifies the signature (ADR 0025 §6).
   - This also closes attached-plus-Gitea. `IMAGE_TIMEOUT` does not apply, because the build is the step's own work, as it is in `up`'s publish.
   - **Deviation from the plan:** "or `TOOLCHAIN_IMAGE`" is dropped. A toolchain image holds no application, so it cannot be a release artefact. A workload without `.lights-out/compose.yaml` has no release, and `up` already says so (ADR 0042 §7).
5. **Proof.** `./go ci` stays cold; the live proof is a conformance suite.
   - **`ci/codehost.sh`** joins `CI_CHECKS`. It needs no network, no engine and no fake GitHub. It checks five things:
     - every `adapters/*/` that has `clone-url.sh` also ships the eight verbs and `ready.sh`;
     - `credential.sh`'s answers, for the right host, a wrong host, and `store`/`erase`;
     - the Makefile's helper entry is index 1, and `safe.directory` is still at index 0;
     - with `curl` and `git` replaced on `PATH` by recorders that log argv, `GIT_CONFIG_*` and stdin, then exit 1, each GitHub verb run with a dummy token: the token is never in any argv, reaches curl only on stdin, and never appears on stdout or stderr. This catches what a grep misses, such as a token copied into another variable first;
     - a grep finds no `git config`, `git remote add` or `remote set-url` in any code host adapter.
   - **`gates/codehost-conformance.sh`** follows the ADR 0026/0041 shape. It runs only with `CONFORMANCE=1`, which only the `codehost-conformance` target sets, and `./go` gives that target the socket. It drives whichever `CODE_HOST` is set:
     1. bootstrap, then check its postcondition;
     2. clone `clone-url`, and check that the clone's `.git/config` holds no credential;
     3. push `conformance/<run id>` with a one-file commit;
     4. `open-pr` twice, which must return the same number;
     5. status `pending`, then a 200-character `success`, then `await` → `success`;
     6. `pr`: open, not merged, the head as pushed, `merge_sha` null;
     7. a second commit is pushed, then a merge at the old head must exit 1 and leave the PR unmerged;
     8. a merge at the new head prints `<merge> <head>`; `pr` agrees, and the merge's second parent is the head;
     9. a re-merge prints the same line;
     10. at no point does the token appear in the suite's captured output.
   - **Where it runs on every push:** as a last step of `ci.yml`'s existing `launch` job, against Gitea, with the plane already up. No new job and no second plane boot. This proves the suite against the reference adapter, so a red nightly points at the GitHub adapter, not the suite.
   - **The nightly does not run the full e2e.** That would need a model key secret, the whole plane and an attached contract with a ticket, and model variance would turn the nightly red for reasons that are not the adapter's. What is GitHub-specific is the eight verbs; e2e at L0 proves the tower on every push.
   - **`./go e2e CODE_HOST=github PROFILE=l1` is the owner's run, once**, and its result goes in HANDOFF and plan §16. "The nightly is green" in the done-when means the verbs are proven. It does not mean the tower is proven on GitHub.
6. **The nightly.** `.github/workflows/nightly-github.yml` runs on `schedule` (daily) and `workflow_dispatch`. Its one job has the GitHub-only guard and a single `run:` step, so it uses no status functions (gitea-compat).
   - If `vars.LIGHTS_OUT_GITHUB_REPO` is empty, it prints `::notice::nightly-github skipped: set the repository variable LIGHTS_OUT_GITHUB_REPO and the secret LIGHTS_OUT_GITHUB_TOKEN` and exits 0.
   - If the variable is set and the secret is empty, it fails, naming the secret: half a configuration is an error, not a skip.
   - Otherwise:
     1. It writes `.env` (umask 077) with `GITHUB_TOKEN` and `GITHUB_REPO`, both from the secret and the variable, never from the runner's ambient environment.
     2. It clones the throwaway on the host, with the helper given as `git -c credential.helper=…`. The argv holds a path, not the token.
     3. It runs `./go attach <clone>`, then `./go codehost-conformance CODE_HOST=github`.
   - Actions' own `GITHUB_TOKEN` cannot reach another repository, hence the separate secret.
7. **`ci/vendor-free.sh` gains `gitea|github`**, the CodeHost column of plan §4. The headers of `core/crew.sh` and `core/tower.sh` are reworded without the name: by that check's own rule, a comment that names the vendor is a coupling. The stale "one Gemini word" in crew.sh's header goes with it.

**The token, and where the owner sets it.**
- It is a fine-grained personal access token, created at github.com → Settings → Developer settings → Fine-grained tokens, with "Only select repositories" set to the one repository.
- Its repository permissions: Contents read and write (push and merge), Pull requests read and write (create and read), Commit statuses read and write. Metadata read is implied.
- It goes in `.env` for local runs, and in the lights-out repository's Actions secret `LIGHTS_OUT_GITHUB_TOKEN` for the nightly.

**L0 replays nothing new.** No GitHub answer is recorded and no fake GitHub exists. `./go demo` keeps `CODE_HOST=gitea` and the bundled app's `image` wait.

## Alternatives rejected

- **The token in a URL in argv (Gitea's way), or `git -c http.extraHeader=…`:** both put it in the process list. **In `clone-url.sh`:** it would be written into the workspace's `.git/config`, which the worker mounts.
- **The helper at `GIT_CONFIG_KEY_0`:** it silently replaces the Containerfile's `safe.directory`.
- **A ninth verb (`fetch`), or public repositories only:** the verb changes four core call sites and every adapter for what one env config does. Public-only excludes most users' work repositories.
- **The `gh` CLI, or a GitHub App installation token:** a new workbench binary with its own token store, or an app, a private key and a JWT, for one owner. L2 may revisit.
- **Bootstrap pushing the attached HEAD to the user's default branch:** that writes to the user's repository outside a PR. **Bootstrap fast-forwarding `.attached/`:** that moves the workload silently under a running plane.
- **Check runs in `await.sh`:** another system's verdict (§3). **The `merge-async` endpoint** (it is listed in the reference data): polling for nothing, because the synchronous merge is enough.
- **One release path for both workloads (retire the `image` job):** less code, but it changes `./go demo`'s measured path and ADR 0025 §4/0039's runner in a milestone whose done-when says the demo is unchanged. It is the obvious follow-up.
- **`TOOLCHAIN_IMAGE` as the artefact:** it holds no application (§4).
- **The full e2e as the nightly:** see §5. **A recorded or fake GitHub, at L0 or in `./go ci`:** the plan forbids it, and it would encode my belief about GitHub where the nightly measures it.
- **`GITHUB_REPOSITORY` or `GITHUB_API` knobs:** the first collides with Actions; the second has no consumer (§1).

## Consequences

- **The one that hurts: on GitHub, a merge commit can contain base commits that no gate judged.** Humans push to the default branch; on L0 Gitea only the tower writes. The gates judged `merge-base..head`, and only the canary judges the merge. The user can make `gates` a required status check with "require branches to be up to date". GitHub then answers 405, and the ticket stops before merge with that reason.
- Every merge moves the default branch, so the next `assign` on GitHub refuses until the owner pulls and runs `./go attach` again (§3). This is visible and never silent, but it is a manual step per ticket.
- A repository with merge commits disabled cannot be served: ADR 0019 §5 needs the judged head as the second parent.
- The attached release step now includes a build, and nothing times it out. The 900 s budget does not apply because `./go demo` never takes this path.
- `launch` runs one more suite on every push. The throwaway repository gains a merged PR every night.
- Any later env-scoped git config entry must take the next free index too. The Makefile owns the count, and `ci/codehost.sh` checks it.
- The owner's one-time e2e needs a throwaway repository holding a `.lights-out/` contract (`workloads/minimal`'s works), a `.lights-out/tickets/<id>.md` with a perimeter, the token, and a model key; `docs/use-on-your-repo.md` gains these steps.

## Golden-rule check

At L0 `CODE_HOST=gitea` ships no `credential.sh`, so the git config stays the Containerfile's single `safe.directory` entry. The bundled release path is byte-for-byte the same. `./go ci` gains one cold check with no network. The only edits on the demo path are a branch in `release.sh` that the bundled app does not take and two reworded comments. Passes.

## Verified (2026-11-04)

docs.github.com was unreachable from this session. GitHub's own reference data was read instead from `github/docs`, `src/rest/data/fpt-2022-11-28/{pulls,commits}.json` (raw.githubusercontent.com), and octokit's generated endpoint docs:
- Merge a pull request: `PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge`. `sha` means "SHA that pull request head must match to allow merge"; `merge_method` is one of `merge`, `squash` or `rebase`. 405 is "Method Not Allowed if merge cannot be performed" and 409 is "Conflict if sha was provided and pull request head did not match". The fine-grained token needs Contents write.
- Create a pull request: 201, Pull requests write. Get a pull request: Pull requests read and Contents read. Before a merge, `merge_commit_sha` "holds the SHA of the *test* merge commit".
- Create a commit status: `POST /repos/{owner}/{repo}/statuses/{sha}`, Commit statuses write, `description` "A short description of the status" with no stated limit, and 1000 statuses per sha and context. List commit statuses: "reverse chronological order. The first status in the list will be the latest one", Commit statuses read.
- In this checkout: `workbench/Containerfile` sets `GIT_CONFIG_COUNT=1` with `safe.directory` at index 0.
- Not verified this session:
  - the 140-character limit (a secondary source, §3);
  - `curl -H @-`, checked in the workbench at build time;
  - whether `permissions` reflects a fine-grained token's grants (§3 states it as my reading).

## Amends

- ADR 0025 §5: the `image` wait applies to a bundled workload only.
- ADR 0037 Consequences: the attached release gap is closed.
- ADR 0017 §4: "the authenticated URL passed as a command argument" holds for Gitea; a code host with `credential.sh` authenticates through the env-scoped helper.
- ADR 0024 §1 / `ci/vendor-free.sh`: the word list gains the CodeHost column.
- Plan §16 M21: `TOOLCHAIN_IMAGE` is dropped as an artefact, and "the nightly is green" means the conformance suite. CLAUDE.md is not touched.
