# Handoff: the first check on a repository with no contract (ADR 0064), 2026-11-10

Branch `claude/optimistic-meitner-aed1df`, cut from `main` at 3f24804 (0.3.0 released, the three Actions on the Marketplace). Pushed; not merged, no PR, nothing tagged or published. **The change ships with the next version (0.3.1 or 0.4.0, the owner's call at the tag), not with 0.3.0**: the published `@v0.3.0` Action and image still print the bare NO-GO.

## What changed

- **The problem, reproduced 2026-11-09** with the `v0.3.0` wrapper and image on a two-commit Python repository with no `.lights-out/workload.env`: `NO-GO: gates — the repository has no .lights-out/workload.env committed; lights-out init drafts one`, exit 1, under 1 s. The way out needed podman or docker on the stranger's machine.
- **ADR 0064 (candidate b)**, written by the `architect` subagent before the code. The first run stays NO-GO (check `failure`, job exit 1): nothing judges without a contract at the base, so ADR 0033 stays whole. On that line only, the Action runs `lights-out init HEAD=<base>` (the base, never the head: a fork cannot shape the contract the owner commits), appends init's summary (the three small files in fences their content cannot close, `runners/` by size) to the check, uploads the whole draft as the artifact `lights-out-draft-<job id>` (`actions/upload-artifact` at the repo's existing pin `cf430e0`, v7.0.2, `include-hidden-files`, `overwrite`), and writes `gh run download …` plus `git add .lights-out && git commit …`. No new permission. Rejected: (a) judging with the draft, advisory; (c) an Action that opens a PR; the reasons are in the ADR.
- **`package/entrypoint.sh`**: no contract at the head is now two lines, a removal (`NO-GO: <name> — the change removes .lights-out/workload.env, which its base has; a change cannot remove the contract that judges it`, no draft) and the first run (the 0.3.0 text, unchanged, which the Action matches exactly). `init HEAD=<commit>` drafts from that commit; every `init` writes `init/summary.md`, with no container or host path. init's stdout names the clone "the repository" instead of `/tmp/lights-out/attached`.
- **`action.yml`**: the first-run branch in the `gates` step, then an `upload` step (`continue-on-error`) and a `commands` step, both only when a draft exists. **`lights-out`**: the usage line says `init [HEAD=]`; nothing else.
- **A laptop `lights-out gates` does not draft** (ADR §5): `lights-out init` is one command away there.

## Tests, from the ADR (the `gate-writer` subagent, without the implementation)

- `package.yml` `action` job, before the existing steps: a scratch repository with no `workload.env`, the Action on c1..c2 (NO-GO, a `failure` check whose summary names c1, the three files and the artifact), `actions/download-artifact` at `9000827` (v8.0.2, verified with `gh api` 2026-11-09) into an empty directory (`.lights-out/` and nothing else, naming c1), committed as c3, a good change c4, the Action on c3..c4 GO. The existing four assertions are untouched.
- `package/demo.sh`, after the timed part (the 300 s budget unchanged): the first-run line for the three commands, a single-commit repository, `STAGED=1`; the removal line; `init HEAD=<c1>` names c1 and not HEAD; `init HEAD=not-a-commit`; `init/summary.md`'s heading, line, files, runners, no `/tmp/` and no output path; a no-stack init says "no draft is offered". One test was corrected after the hand-back: it wanted init's stdout line verbatim in the summary, which names the host's draft path the ADR forbids there; it now expects the line with the draft written `.lights-out`.
- `ci/package.sh`: the two reason texts in the entrypoint and the Action, the upload pin with `include-hidden-files` and `overwrite`, no other ref of it in the Actions, no new permission, no new REST path; each with planted defects.

## Proofs

- Local, by hand on the gates image built from the implementation: the four wrapper cases above, as the ADR says; init from c1 on workloads/minimal in 25 s of mutation.
- `./go ci-package`: GO (60 s). `ci/docs-drift.sh` on the host with `MAP_EXCLUDE="docs/PLAN.md docs/plans/* .claude/*"`: GO.
- `./go demo-package`, `./go ci` from a clean clone under `.crew/`, and the six workflows on the branch head: see the PLAN note (M31, second slice) for the run ids.

## For the owner, at the next release

- **The two standalone Actions' repositories**, `nicolaguglielmi/test-proof` and `nicolaguglielmi/test-integrity`: copy `actions/test-proof/README.md` and `actions/test-integrity/README.md` (their "What it needs" says the first check now drafts the contract). Not pushed from here.
- **The site**, `site/index.html` line ~604: "It needs a committed `.lights-out/` contract, which the wrapper below drafts." is true for 0.3.0 and left as is; at the release it can say that the first check drafts it.
- README, guide and reference say "after 0.3.0"; at the tag, name the version.

## Found and fixed here

- **0.3.0 posts no check on a first run.** The image refuses before it creates `gates/`, so the Action's fallback `gates/summary.md.line` cannot be written, the step dies with exit 2 under `sh -e`, and the check step never runs: a stranger sees a red job and no check run (package run 42721181005, the first push of this branch). The Action now runs `mkdir -p "$LO_OUT/gates"` first; the new first-run test in the `action` job is what caught it. ADR 0064 records it.

## Found, not fixed here

- `docs/use-on-your-repo.md`, "Without cloning lights-out: the wrapper", still names `ghcr.io/nicolaguglielmi/lights-out:0.2.0`, the 0.2.0 raw URL and "unsigned".
- `ci/package.sh` fails on the macOS host (BSD `sed`); it runs in the workbench through `./go ci-package`, where it is GO.
- `.github/workflows/ci.yml` uses `actions/upload-artifact@v7` by tag, not by commit; the new judge covers the Actions only.
- The light tier (`lights-out-gates --light`, ADR 0061) refuses the same way with no contract (`no .lights-out/workload.env at the base or the head; lights-out init drafts one`) and has no init of its own: out of scope (ADR 0064 covers the image's wrapper and the Action).
- A `STAGED=1` change that removes the contract is still judged by HEAD's contract (ADR 0064, Consequences).
