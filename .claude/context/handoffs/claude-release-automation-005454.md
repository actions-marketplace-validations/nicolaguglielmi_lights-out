# Handoff: release automation (ADR 0075), 2026-11-11

Branch `claude/release-automation-005454`, cut from `origin/main` at f97085d (0.3.1). It is pushed with no pull request. Nothing is merged, tagged or published. The coordinator merges. Versions and the 0.4.0 checklist section are untouched.

## What changed

- **ADR 0075, "The tag releases itself"**, with the alternatives it rejected: a PyPI API token as a secret, `pypa/gh-action-pypi-publish`, a GitHub App, submodules or a subtree split, a separate `release.yml`, uploading to PyPI from `publish`, and a dispatch that uploads. It amends ADR 0057 §4 and §7, with a note in each.
- **`.github/workflows/package.yml`** runs five release jobs on a `v*` tag:

  | Job | What it does |
  |---|---|
  | `dist` | Checks that the tag, the wrapper and `pyproject.toml` carry one version. Runs `uv build` at the workbench pin, looks inside the wheel, runs `lights-out-gates version` from it, and uploads `dist/`. |
  | `publish` | Needs `dist`. Same as before, plus `cosign verify` by digest against `https://github.com/$GITHUB_WORKFLOW_REF`. Outputs the version and both digests. |
  | `pypi` | Tag only, environment `pypi`, `contents: read` + `id-token: write`. Runs `uv publish --trusted-publishing always --check-url https://pypi.org/simple/`. |
  | `actions` | `contents: read`. Runs `package/sync-action.sh` for test-proof and test-integrity, then `gh release create --draft` in each repository, with the secret `ACTION_REPOS_TOKEN` read only on a tag. |
  | `release` | `contents: write`. Writes the notes with `package/release-notes.sh` and creates the draft `v<version>` here. |

  A `workflow_dispatch` takes `dry_run` (boolean, default `true`). Each job prints its commands, diffs and notes to the step summary and pushes nothing. `dist` builds and runs the wheel for real, and `actions` commits and tags both clones on the runner.
- **`package/sync-action.sh`** is idempotent:
  - A remote tag that holds the same files: exit 0, nothing pushed.
  - A remote tag that holds other files: exit 1, the tag is never moved.
  - It refuses a shim that does not use `lights-out@v<version>`.
  - It refuses `--push` to https without the token.
  - It commits as `Nicola <45848139+nicolaguglielmi@users.noreply.github.com>`.
- **`package/release-notes.sh`** writes the notes. If `docs/releases/v<version>.md` exists, its prose comes first.
- **Tests**:
  - **`ci/release.sh`** is new, added to `CI_CHECKS` before `contract`, and written from the ADR. It checks the workflow as YAML: jobs, `needs`, exact permissions, the single secret, and the dry-run and tag guards. It runs only what an `echo` does not print. It also runs both scripts against local bare repositories. Every judge is shown to fail on planted defects: 31 for the workflow and 10 for the scripts.
  - **`ci/package.sh`** now allows `id-token: write` on `package.yml`'s `pypi` job too, never `packages: write`. Two planted cases were added.
- **`ci/plan.sh`** (ADR 0065) now exempts `package.yml`'s `dist`, `pypi`, `actions` and `release` from the `plan` gate, as it already exempted `publish`. `plan` skips a commit that is already green, and a tag is always on one. The probe proves the exemption covers that file only. The first push, a96ba73, was red in ci, stranger and self for this reason alone (`NO-GO: plan — 4 job(s) escape the plan job`).
- **Docs**:
  - `docs/launch/checklist.md` has a new section, "Release automation (ADR 0075)", placed before "The README's front page". It gives the owner's three one-time settings with exact fields (the PyPI trusted publisher, the environment `pypi` with a `v*` tag rule, the fine-grained token and the `ACTION_REPOS_TOKEN` secret) and the steps for each release: rehearse, tag, three Marketplace clicks, re-run failed jobs.
  - Two older checklist lines point to that section, and the table "Done in the repository" has a row for it.
  - `docs/reference.md`, the comment in `pyproject.toml`, and ADR 0057 are also updated.

## Proven

- On the Mac and in the workbench, `sh ci/release.sh` gives `GO`. Against the real public repository, `sh package/sync-action.sh test-proof 0.3.1 <dir>` answers "v0.3.1 already holds these files; nothing to push": the 0.3.1 copies equal `actions/` and `LICENSE` today.
- **`./go ci` from a clean clone under `.crew/`** on df27c96: `GO: ci` in 5:48, 45 checks GO, `GO: release` among them. Before that, `release`, `plan` and `package` were run alone in the workbench image. The first run on GitHub had caught the awk interval that mawk refuses.
- **Six workflows green on df27c96:**

  | Workflow | Run | Result |
  |---|---|---|
  | ci | 43102935859 | engine-compat `GO: demo, milestone M9, 631s to rollback` |
  | stranger | 43102935748 | `GO: demo, milestone M9, 572s to rollback` |
  | self | 43102935717 | green |
  | package | 43102935758 | green |
  | podman | 43102935731 | green |
  | site | 43103004311 | green, dispatched by hand because its paths were untouched |

- **The dry-run dispatch**, package run 43099901825 on a96ba73, with `dry_run=true`:
  - `dist` built `lights_out_gates-0.3.1-py3-none-any.whl` and the sdist, looked inside, and ran it: `lights-out-gates 0.3.1 (the light tier: --light)`.
  - `publish` printed the buildx, `cosign sign` and `cosign verify` commands for both images, with the identity `…/package.yml@refs/heads/claude/release-automation-005454`, and built nothing.
  - `actions` cloned both repositories and answered "v0.3.1 already holds these files; nothing to push", then printed both drafts' notes.
  - `release` printed the notes and the `gh release create` command.
  - `pypi` was skipped.
  - Nothing was pushed, uploaded or tagged. The dispatch's jobs ran in under 40 s.

## Not proven

- A real tag. The `pypi` upload, the push to the two repositories, and the `gh release create` calls have never run. The first real run is the next release's tag, after the owner's three settings.
- `gh release view <tag>` on an existing draft, used for idempotency, is assumed to find drafts (gh falls back to the draft list).

## Merge notes

- Expect conflicts in `docs/launch/checklist.md`, where the coordinator's 0.4.0 section lands tonight, and in `CI_CHECKS` in the Makefile.
- If 0.4.0 is tagged before this lands, it is released by hand as before.
- After the merge, the next release needs the owner's three settings first.
- The Gemini extension repository, `lights-out-gemini` (ADR 0069), is not covered. When it exists, it is the same kind of copy.
