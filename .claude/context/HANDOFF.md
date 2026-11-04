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

`./go ci` gains `ci/package.sh` (the gate-writer's, from ADR 0045 §8): GO in the full `make ci` run inside the workbench, `GO: ci`, before the last two commits; on Actions in the runs below.

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

## Runs on the final commit

Pending when this was written: the `ci` and `package` runs on 4c1012e; the next commit records them.
