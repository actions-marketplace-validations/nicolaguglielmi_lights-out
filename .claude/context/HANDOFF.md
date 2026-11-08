# Handoff: M35, gates without a container (ADR 0061), 2026-11-08

Branch `claude/m35-light-gates-3dbc9f`, from 30ca9dc (the adoption roadmap, on top of M33's unmerged branch). Pushed, no pull request, not merged: landing is the owner's, with M34 (`claude/m34-lean-plane-a0d988`) and M31. Nothing published.

## Acceptance

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

## What changed

- ADR 0061 first, then the code; 82 unit tests and `ci/gates-light.sh` written by gate-writer from the ADR without reading the implementation. They found one real bug: an inherited stdin (a hook's open pipe) stalled `git hash-object` on a root commit; fixed in 58824ec.
- `pyproject.toml` at the root: package `lights-out`, import name `lights_out` = `core/` by `package-dir`, `policy/merge.env` shipped as `lights_out.platform_policy`, `perimeter.sh` as data, no runtime dependency. `core/__main__.py` is the CLI, `core/light.py` the tier; the eight `from core.x` imports in `core/` became relative.
- The tier runs risk and test-weakening by default, perimeter and spec with `TICKET=`, test then test-proof on the host with `TEST_ON_HOST=1` (throwaway shared clones outside the repository); `STAGED=1` reads the index with `git diff --cached` and writes nothing; the base's contract judges.
- The `--light` hook recipes (timeout 30 s), each run once against Claude Code 2.1.311, Codex 0.166.0 and Gemini CLI 0.61.0-preview.0 with the scripted model: blocked on a weakened test with the NO-GO line returned to the model, commit through on a clean change. The guide says "verified" per CLI and what was not covered.
- `ci/contract.sh` runs the light entry point cold; `ci/app-free.sh` lists `core/light.py` beside attach and init; `gates-light` in `CI_CHECKS`; README one sentence, `docs/reference.md`, the owner's PyPI steps in `docs/launch/checklist.md`.

## Contradictions with the plan, and open points

- **"5 of 9" is "n of 10".** The PLAN's list left out `test`, which test-proof cannot do without (ADR 0053 §4); perimeter and spec need a ticket. On a repository without lights-out tickets the default is two gates, four with `TICKET=`, six with `TEST_ON_HOST=1`. "Five gates in five seconds" (roadmap K2) is two gates in a fraction of a second by default.
- **test and test-proof are not proven on the fixtures.** The app's `TEST_CMD` needs the compose Postgres, so in `./go ci` only risk and test-weakening are compared with the full verdict; the host run is proven by the unit tests on scratch repositories.
- **`lights-out` names two programs** (the image wrapper and the package's script). A `--light` hook that reaches the wrapper first on PATH gets a NO-GO on every commit; the guide says to use `uvx lights-out` or keep one. A later milestone may make the package hand everything but `--light` to the image.
- **Two version fields**: `pyproject.toml` (0.3.0.dev0) and the wrapper's `version=` (0.2.0). The checklist says to set both at a release; `package.yml` checks the tag against the wrapper only.
- **The self workflow judges only `HEAD^1..HEAD` on a push**, so the mutation of `core/light.py` is judged on the owner's merge PR, not on this branch's pushes. Measured locally in the workbench (the runner of `.lights-out/`, `MUTATION_LINES` = M35's changed `core/` lines from 30ca9dc): 337 mutants, 261 killed, score 0.774 against the threshold 0.293 (baseline 0.3934 minus margin 0.10), 1144 s. Most of the 76 survivors swap `!=` for `<`/`>` on exit codes, equivalent for codes that are never negative. Expect the merge PR's self job to spend about 20 minutes on mutation.
- `.lights-out/workload.env` still says `lights-out init` on this repository NO-GOes because there is no root `pyproject.toml`; there is one now (init would refuse for the missing `uv.lock` instead). Not changed: it is the self gate's contract.
- Found while verifying: `ci/contract.sh` on the macOS host (bash as `sh`) reports `docs-drift`, `package` and `contract(bad-unset.sh accepted)`; in the workbench (dash) it is GO. Host-only, as M33 noted for `ci/logbook.sh`.

## First thing for the next milestone

Merge order: M35 conflicts with M34 on the one `CI_CHECKS` line of the Makefile (M34 drops `gitea-compat`, adds `store-bus`; M35 adds `gates-light`). After the merge, run `./go ci` once and `lights-out gates --light` on a repository that is not lights-out. Then the owner's PyPI steps in `docs/launch/checklist.md`, soon: the name is free, not reserved.
