# Handoff: M31, M34 and M35 merged on `fix/adr-still-header`, 2026-11-08

The integration branch is `main` (761450f, M33 on it) + the adoption roadmap (30ca9dc) + three merge commits, M34 (aacab9e), M35 (daf3e15) and M31 (c9cc1f7), + the commit after them. Pushed; nothing tagged or published.

Resolved at the merges: the Makefile's `CI_CHECKS` (gitea-compat out, readiness, store-bus and gates-light in); `ci/gitea-compat.sh` deleted, ADR 0060 §6 over M31's widening of its exemption; `docs/reference.md`'s first-run paragraph keeps both facts (no emulator pull at L0, no gcloud or terraform in the image); `docs/launch/checklist.md` keeps M31's and M35's sections. After the merges: `core/doctor.sh`, the README and the tutorial require 8085 and 8086 only when a profile names an emulator (M34 left it to M31, which left it to the merge); the nightly workflow's comment no longer cites the deleted check. The ROADMAP moves M31, M33, M34 and M35 to Done, and the checklist gains a Product Hunt section (a second wave, the week after Show HN).

Host checks on the merged tree, 2026-11-08: `docs-drift`, `gates-light`, `store-bus` and `readiness` GO; the 681 unit tests OK in 72 s; `./go doctor` GO at L0 without the emulator ports. The proof is the six workflows on the branch head, after which `main` is fast-forwarded to it. The owner's steps are in `docs/launch/checklist.md`: tag `v0.3.0`, PyPI, the three Marketplace pages, the first-pull measure on the probe.

## Release 0.3.0, 2026-11-09

`main` is b931688 (`pyproject.toml` at 0.3.0, the wrapper's version) plus the commit that records the release. The tag `v0.3.0` is on b931688; `package.yml` run 42588480235 built, pushed and signed both images at its first run. Digests: `lights-out-gates@sha256:051894c1703071a98afa4d96d58b457b566364d3029a0d9d863984c8a4736853`, `lights-out@sha256:b5e2404c98ec45688f28c5a97039862e943539c5dfed12ea13eeb6c6d73e31e4`; both public, both signatures verified with the workbench's cosign.

The probe (`nicolaguglielmi/lights-out-probe`, pull request 1) now uses `@v0.3.0` with one job per Action: 27 s, 14 s and 25 s to the check run, first pull included, all GO (run 42589663783). The wrapper from the tag printed `GO: gates` in 46 s on an arm64 Mac, first pull included.

The standalone Actions have their repositories, `nicolaguglielmi/test-proof` and `nicolaguglielmi/test-integrity`, tagged `v0.3.0`, each with a draft release; the probe uses them (11 s and 23 s, GO, run 42591256328).

Left to the owner (`docs/launch/checklist.md`): publish the three draft releases with the Marketplace box ticked, the upload to PyPI (a dry-run wheel at 0.3.0 was built and answered `GO: gates-light`).

Found, and fixed after the tag: `gates/test-proof.sh` passed `HEAD=` as given to `git restore --source` inside the base's worktree, where a HEAD-relative ref names another commit (`HEAD=HEAD` gave NO-GO; the default head, a branch or a sha gave GO). `require_range` in `ci/lib.sh` now sets `$head` to the commit's id; `core/tests/test_gate_range.py` has the seven cases from ADR 0015 §2 and 0053 §2, four of them red before the fix. The 0.3.0 image still has the defect, the guide says so, and the fix ships with the next version.


Each section below this line is the branch's own handoff, kept whole.

## Handoff: M34, the lean plane (ADR 0060), 2026-11-08

Branch `claude/m34-lean-plane-a0d988`, on 30ca9dc (the adoption roadmap, on `fix/adr-still-header`, M33 not yet on main). Pushed, no pull request, not merged: landing is the owner's, with M31 and M35 beside it.

### Acceptance

On a0fc792, every workflow the push triggers green: ci 42510074390, stranger 42510074189, self 42510074229, package 42510074180, podman 42510074435; `site` did not trigger on those paths and was green on e2599c8 (42506965553). The lines below are from 8fd756c (ci 42508676734, stranger 42508676759), green the same way; a0fc792 gave 825 s and 719 s.

```
engine-compat  GO: demo, milestone M9, 757s to rollback (budget 900s, plan §2)
stranger       GO: demo, milestone M9, 801s to rollback (./go demo: 802s, exit 0)
engine-compat  after ./go down && ./go up: GO: logbook — .crew/logbook-restarted.json, 1 tickets
               launch.plane {"canary":"0.2.0-waitlist",...} → {"canary":null,...}; the rest identical (diff empty)
launch         GO: demo-launch, GO: demo-console, GO: codehost-conformance — gitea, PR #1 merged
               GO: statestore-conformance — firestore-emulator, 8 cases
               GO: eventbus-conformance — pubsub-emulator, 5 cases; case 5 (redelivery) not run
mainline       GO: demo-mainline, GO: demo-rework
seam           GO: demo-seam
local          ./go ci from a clean clone: GO: ci (4 min 50 s), store-bus GO: sqlite 8 cases, spool 6 cases
```

The run before, e2599c8: 873 s and 852 s, with `demo-rework` red (stale expectation, below) and the logbook `cmp` red at `launch.plane`.

### What changed

- ADR 0060 before the code; the two suites and `ci/store-bus.sh` written by a subagent from the ADR without seeing the adapters, then run against them.
- `adapters/sqlite` (StateStore) and `adapters/spool` (EventBus): stdlib Python behind `.sh` verbs, `.crew/state.sqlite` and `.crew/spool.sqlite`, default at L0 and L1. The emulators sit behind the compose profile `emulators`, started when a profile names them.
- The Gitea runner, its image, the `image` job and `ci/gitea-compat.sh` are gone; Gitea Actions off; no compose service holds the engine socket; `./go` no longer passes `HOST_DOCKER_SOCK`.
- `core/steps/release.sh` builds every workload's merge in a throwaway worktree; for the bundled app it restores the checkout's Makefile, compose file, profiles and adapters over the merge's first, and signs with the checkout's key.
- Dated amendments to ADR 0039 (superseded), 0025 §4 §5 and 0043 §4; PLAN §3, §4 rows and the M34 status note; ARCHITECTURE, reference, ROADMAP, the board's release stage.

### Contradictions with the plan, and open points

- **The budget.** The plan proposed 600 s warm, to be measured. Measured: 719 to 873 s on this branch over three pushes, 116 s apart on the same job. The budget stays 900 s (ADR 0060 §7). M34 removes a failure mode (the 300 s `image` wait) and three services, not seconds on Actions: a green run's image wait was about a second, and GitHub pulls the emulators fast. The time is in the demo's `ci` stage (43 %, every check run twice, once inside `contract`'s cold re-run) and the workbench build (15 %).
- **"Identical logbook"** holds except `launch.plane`, which reads the live Delivery status: `down` removes the rolled-back canary revision the demo leaves at weight 0. The CI step compares everything else and prints both plane values.
- **The plan named the bus `inproc`**, which is the Orchestrator's directory; it is `spool`.
- **State now outlives `./go down`**: a stranded ticket or a red `mainline/main` stays until `./go resume` or deleting `.crew/state.sqlite`. The demos delete their own documents first.
- **Found:** `demo-rework` had been NO-GO since M30 (its expected history lacked the `mainline` step) and no workflow ran it; it now runs in the `mainline` job. The Firestore emulator refused a JSON array only by a jq accident; now by rule. `ci/board.sh`'s "nothing to read" probe assumed a network store.
- **Left to M31** (noted in the shared notes folder): `core/doctor.sh` and the README lines describing it still require ports 8085 and 8086 free.
- Not done, a follow-up: the `if: github.server_url == 'https://github.com'` guards and the "L0 Gitea runner reads this directory" comments in the other workflows are inert now.

### First thing for the next milestone

The demo budget: the `ci` stage runs every check twice (`contract` re-runs each one cold to check its output line), about 170 s of an 800 s demo. Making `contract` judge the lines the first pass already printed, or running a smaller `ci` in the demo, is the next real cut; nothing in the plane is left to trim.

## Handoff: M35, gates without a container (ADR 0061), 2026-11-08

Branch `claude/m35-light-gates-3dbc9f`, from 30ca9dc (the adoption roadmap, on top of M33's unmerged branch). Pushed, no pull request, not merged: landing is the owner's, with M34 (`claude/m34-lean-plane-a0d988`) and M31. Nothing published.

### Acceptance

On a bare clone of this repository (`git clone --no-local`, its last commit judged):

```
$ time python3 -m core gates --light
GO: gates-light — risk high, review; 2 of 10 gates ran; secrets, deps, sast, mutation need the image; test, test-proof need TEST_ON_HOST=1; perimeter, spec need TICKET=
python3 -m core gates --light  0.08s user 0.04s system 82% cpu 0.137 total
$ uvx -q --from git+file://<clone> lights-out gates --light     # 2.4 s first run (build), 0.23 s cached, same line
```

`./go ci` in a full clone under `.crew/`: GO in 4:35, with `GO: gates-light` (the nine `app/fixtures/gates` fixtures agree with `expect` where both run, the 10 s budget, the package mapping, each proven able to fail) and `GO: contract` (the light entry point's three shapes). GitHub Actions on 58824ec, six workflows green: ci 42507391349, stranger 42507391336, self 42507391335, site 42507391329, package 42507391379, podman 42507391334.

```
engine-compat  GO: demo, milestone M9, 847s to rollback (budget 900s, plan §2)
stranger       GO: demo, milestone M9, 745s to rollback
self           GO: gates — risk high, review, in workbench
ci             GO: ci (681 unit tests, GO: gates-light)
```

M33 gave 834 s and 828 s: engine-compat is 13 s slower (the demo's `ci` stage has one more check, and `contract` runs it twice), stranger 83 s faster (runner noise). The margin on the 900 s budget is 53 s.

### What changed

- ADR 0061 first, then the code; 82 unit tests and `ci/gates-light.sh` written by gate-writer from the ADR without reading the implementation. They found one real bug: an inherited stdin (a hook's open pipe) stalled `git hash-object` on a root commit; fixed in 58824ec.
- `pyproject.toml` at the root: package `lights-out`, import name `lights_out` = `core/` by `package-dir`, `policy/merge.env` shipped as `lights_out.platform_policy`, `perimeter.sh` as data, no runtime dependency. `core/__main__.py` is the CLI, `core/light.py` the tier; the eight `from core.x` imports in `core/` became relative.
- The tier runs risk and test-weakening by default, perimeter and spec with `TICKET=`, test then test-proof on the host with `TEST_ON_HOST=1` (throwaway shared clones outside the repository); `STAGED=1` reads the index with `git diff --cached` and writes nothing; the base's contract judges.
- The `--light` hook recipes (timeout 30 s), each run once against Claude Code 2.1.311, Codex 0.166.0 and Gemini CLI 0.61.0-preview.0 with the scripted model: blocked on a weakened test with the NO-GO line returned to the model, commit through on a clean change. The guide says "verified" per CLI and what was not covered.
- `ci/contract.sh` runs the light entry point cold; `ci/app-free.sh` lists `core/light.py` beside attach and init; `gates-light` in `CI_CHECKS`; README one sentence, `docs/reference.md`, the owner's PyPI steps in `docs/launch/checklist.md`.

### Contradictions with the plan, and open points

- **"5 of 9" is "n of 10".** The PLAN's list left out `test`, which test-proof cannot do without (ADR 0053 §4); perimeter and spec need a ticket. On a repository without lights-out tickets the default is two gates, four with `TICKET=`, six with `TEST_ON_HOST=1`. "Five gates in five seconds" (roadmap K2) is two gates in a fraction of a second by default.
- **test and test-proof are not proven on the fixtures.** The app's `TEST_CMD` needs the compose Postgres, so in `./go ci` only risk and test-weakening are compared with the full verdict; the host run is proven by the unit tests on scratch repositories.
- **`lights-out` names two programs** (the image wrapper and the package's script). A `--light` hook that reaches the wrapper first on PATH gets a NO-GO on every commit; the guide says to use `uvx lights-out` or keep one. A later milestone may make the package hand everything but `--light` to the image.
- **Two version fields**: `pyproject.toml` (0.3.0.dev0) and the wrapper's `version=` (0.2.0). The checklist says to set both at a release; `package.yml` checks the tag against the wrapper only.
- **The self workflow judges only `HEAD^1..HEAD` on a push**, so the mutation of `core/light.py` is judged on the owner's merge PR, not on this branch's pushes. Measured locally in the workbench (the runner of `.lights-out/`, `MUTATION_LINES` = M35's changed `core/` lines from 30ca9dc): 337 mutants, 261 killed, score 0.774 against the threshold 0.293 (baseline 0.3934 minus margin 0.10), 1144 s. Most of the 76 survivors swap `!=` for `<`/`>` on exit codes, equivalent for codes that are never negative. Expect the merge PR's self job to spend about 20 minutes on mutation.
- `.lights-out/workload.env` still says `lights-out init` on this repository NO-GOes because there is no root `pyproject.toml`; there is one now (init would refuse for the missing `uv.lock` instead). Not changed: it is the self gate's contract.
- Found while verifying: `ci/contract.sh` on the macOS host (bash as `sh`) reports `docs-drift`, `package` and `contract(bad-unset.sh accepted)`; in the workbench (dash) it is GO. Host-only, as M33 noted for `ci/logbook.sh`.

### First thing for the next milestone

Merge order: M35 conflicts with M34 on the one `CI_CHECKS` line of the Makefile (M34 drops `gitea-compat`, adds `store-bus`; M35 adds `gates-light`). After the merge, run `./go ci` once and `lights-out gates --light` on a repository that is not lights-out. Then the owner's PyPI steps in `docs/launch/checklist.md`, soon: the name is free, not reserved.

## M31, the stepped way in (ADR 0057), 2026-11-08

Branch `claude/m31-front-door-9de845`, on 30ca9dc, pushed, no pull request, not merged: landing is the owner's, with M34 and M35. Nothing published: no image tag, no Marketplace release.

### Acceptance

On 0a0d073, six workflows green: ci 42519069855, stranger 42519069911, self 42519069842, site 42519069848, package 42519069964, podman 42519069828.

```
engine-compat  GO: demo, milestone M9, 848s to rollback (budget 900s, plan §2)
stranger       GO: demo, milestone M9, 782s to rollback
package        GO: demo-package — init and gates 48s in workbench (budget 300s), test-proof and test-integrity GO and NO-GO, a staged break NO-GO at test, image localhost/lights-out-gates:dev, 508 MB unpacked
package        localhost/lights-out-gates:dev 508 MB, localhost/lights-out:dev 1246 MB (was 1.77 GB)
argo           NO-GO: production-readiness — delivery (...), metrics (...), human gate (...)      L0 defaults
argo           GO: production-readiness — delivery argo-rollouts, conformance passed 2026-11-08T20:20:34Z, metrics from METRICS_URL, 2 target_info series, no secrets in .env, launchers owner@example.invalid
```

Outside repository: `nicolaguglielmi/lights-out-probe` (public; made public because the account's Actions billing refused the private run), PR #1, run 42519118155: `lights-out gates` 19 s, `lights-out test-proof` 2 s, `lights-out test-integrity` 17 s, three check runs posted `success`, the image built in the job in 23 s. The first pull is not measured: the image is not published.

Locally: `./go ci` GO from a clone under `.crew/m31-clone` (273 s); `./go demo-package` GO on arm64 podman (init and gates 35 s, the gates image 529 MB); `./go doctor --level l2` lists 9 missing items on this machine.

### What changed

- `workbench/Containerfile`: gcloud, terraform, unzip and node's C headers out; two stages, `gates` and `workbench` on it. `package/build.sh` builds either (`PACKAGE_FLAVOUR`), `./go package-gates`.
- `lights-out` 0.3.0: the gates image for init, gates and the new `test-proof`, `test-integrity`; the image writes `gates/summary.md`, one line per gate; `STAGED=1` takes the patch from the host's git.
- `action.yml` at the root (`action/` removed), `gates` input, the per-gate summary in the check run; `actions/test-proof`, `actions/test-integrity` shims; keyless `cosign sign` in `publish`.
- `./go doctor --level`; `gates/production-readiness.sh`; the delivery suite's record in `.crew/conformance/`; `./go` passes `.env.example`'s secret keys by name.
- README in the five steps with the two reuse claims; `docs/production.md`; reference, guide, tutorial, checklist, site.

### Contradictions with the plan, and open points

- The Marketplace lists one Action per repository, from its root. The two standalone Actions need two repositories of their own; the checklist says how. "Three Marketplace pages published" is the owner's.
- GitHub's `pull_request_target` change was announced 2025-11-07 and took effect 2025-12-08; it takes the default branch, not the PR's base. The README says that.
- "Under 300 s, first pull included" waits for v0.3.0: the checklist has the probe edit that measures it.
- The gates image is 508 MB, not under 400: git with perl and python3, node, osv-scanner and uv are what the gates run.
- Doctor names no vendor or key (`ci/vendor-free.sh`): an adapter should declare its credentials one day.
- The gates image does not render a repository's plane half (no docker-compose) and says so on stderr.
- Merge with M34: it deletes `ci/gitea-compat.sh` (M31 widened its exemption to package.yml: drop that change), drops ports 8085/8086 (doctor, README, tutorial lists), and conflicts on `CI_CHECKS` (M31 adds `readiness`, M35 `gates-light`).
- The gate-writer's worktree `.claude/worktrees/agent-aa6396a5fabe61d67` (branch `worktree-agent-aa6396a5fabe61d67`) is kept; its two commits are cherry-picked here.

### First thing for the next milestone

Tag v0.3.0 after the merge, run the checklist's M31 section, and replace the probe's 19/2/17 s with times that include the first pull.
