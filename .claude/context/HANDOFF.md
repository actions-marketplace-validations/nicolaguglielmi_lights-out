# Handoff: the integration branch `fix/adr-still-header`, 2026-11-09

The integration branch is `main` (761450f, M33 on it) + the adoption roadmap (30ca9dc) + three merge commits, M34 (aacab9e), M35 (daf3e15) and M31 (c9cc1f7), + the commit after them. Pushed; nothing tagged or published.

Resolved at the merges: the Makefile's `CI_CHECKS` (gitea-compat out, readiness, store-bus and gates-light in); `ci/gitea-compat.sh` deleted, ADR 0060 §6 over M31's widening of its exemption; `docs/reference.md`'s first-run paragraph keeps both facts (no emulator pull at L0, no gcloud or terraform in the image); `docs/launch/checklist.md` keeps M31's and M35's sections. After the merges: `core/doctor.sh`, the README and the tutorial require 8085 and 8086 only when a profile names an emulator (M34 left it to M31, which left it to the merge); the nightly workflow's comment no longer cites the deleted check. The ROADMAP moves M31, M33, M34 and M35 to Done, and the checklist gains a Product Hunt section (a second wave, the week after Show HN).

Host checks on the merged tree, 2026-11-08: `docs-drift`, `gates-light`, `store-bus` and `readiness` GO; the 681 unit tests OK in 72 s; `./go doctor` GO at L0 without the emulator ports. The proof is the six workflows on the branch head, after which `main` is fast-forwarded to it. The owner's steps are in `docs/launch/checklist.md`: tag `v0.3.0`, PyPI, the three Marketplace pages, the first-pull measure on the probe.

## Release 0.3.0, 2026-11-09

`main` is b931688 (`pyproject.toml` at 0.3.0, the wrapper's version) plus the commit that records the release. The tag `v0.3.0` is on b931688; `package.yml` run 42588480235 built, pushed and signed both images at its first run. Digests: `lights-out-gates@sha256:051894c1703071a98afa4d96d58b457b566364d3029a0d9d863984c8a4736853`, `lights-out@sha256:b5e2404c98ec45688f28c5a97039862e943539c5dfed12ea13eeb6c6d73e31e4`; both public, both signatures verified with the workbench's cosign.

The probe (`nicolaguglielmi/lights-out-probe`, pull request 1) now uses `@v0.3.0` with one job per Action: 27 s, 14 s and 25 s to the check run, first pull included, all GO (run 42589663783). The wrapper from the tag printed `GO: gates` in 46 s on an arm64 Mac, first pull included.

The standalone Actions have their repositories, `nicolaguglielmi/test-proof` and `nicolaguglielmi/test-integrity`, tagged `v0.3.0`, each with a draft release; the probe uses them (11 s and 23 s, GO, run 42591256328).

Done by the owner the same day: the three releases published to the Marketplace, and the package on PyPI as `lights-out-gates`. Before that, left to the owner: the three draft releases, the upload to PyPI (a dry-run wheel at 0.3.0 was built and answered `GO: gates-light`).

Found, and fixed after the tag: `gates/test-proof.sh` passed `HEAD=` as given to `git restore --source` inside the base's worktree, where a HEAD-relative ref names another commit (`HEAD=HEAD` gave NO-GO; the default head, a branch or a sha gave GO). `require_range` in `ci/lib.sh` now sets `$head` to the commit's id; `core/tests/test_gate_range.py` has the seven cases from ADR 0015 §2 and 0053 §2, four of them red before the fix. The 0.3.0 image still has the defect, the guide says so, and the fix ships with the next version.

## ADR 0062 merged, 2026-11-09

`claude/festive-cray-5c155e` (48ceca6, six workflows green on it) merged after the release and the `test-proof` range fix. The one conflict was this file. `ci/lib.sh` took both changes without a conflict: `record_check` from the branch, `require_range` resolving the head to an id from here. Its handoff is in `handoffs/claude-festive-cray-5c155e.md`.

## The site, and one proof per commit, 2026-11-09

The landing page says 0.3.0, and `ci/docs-drift.sh` reads it (ADR 0054, amendment 2026-11-09): its release is the wrapper's `version=`, its links into `main` and its `./go` targets exist. ADR 0065: the `plan` job in `ci`, `stranger`, `self`, `podman` and `package` skips a commit on `main` that a branch already judged green, and skips the heavy jobs on a docs-only push; `ci/plan.sh` proves the classifier and that no job escapes `plan`. Proved on Actions the same day: 5c51fdd, the code, 13 minutes for the six workflows on the branch; `main` fast-forwarded to it in 31 s, every job but `plan` skipped (ci run 42610705844); 17b23e9, docs only, 262 s, only `plan`, `ci` and `self`'s gates ran (ci run 42610803695). `./go ci` from a clean clone under `.crew/`, never from this checkout: here the secrets scan reads the other sessions' worktrees under `.claude/worktrees` (1 GB, 36 findings that are not this tree's).

## The package is `lights-out-gates`, 2026-11-09

PyPI refused the first upload of `lights-out` ("too similar to an existing project": `lightsout`). ADR 0061's amendment of the same day renames the distribution and its one script to `lights-out-gates`, `gates` implied (`lights-out-gates --light`); `python3 -m core gates --light` is unchanged; the package no longer ships a `lights-out` script, so the collision with the wrapper is gone. Tests: `core/tests/test_light.py` `TheGatesScript` (same line and exit as `gates --light`, arguments through, one NO-GO without `--light`, `version`), `ci/gates-light.sh`'s pyproject check (the name, exactly one script, two new planted wrong pyprojects). The hook recipes' command is renamed; their verification of 2026-11-08 ran `lights-out gates --light`, which `lights-out-gates --light` equals line for line. The wheel to upload is built from `main` at the rename, version 0.3.0: the code of the tag `v0.3.0` but for the command's name in three messages and `gates_main`; the owner uploads it.

## Release 0.3.1, 2026-11-10

Release commit 995ba3f on `main`, tag `v0.3.1`, images published and signed (package.yml run 42790042827), signatures verified; `nicolaguglielmi/test-proof` and `nicolaguglielmi/test-integrity` refreshed and tagged. Three draft releases wait for the owner's Marketplace publish. The podman workflow's harness-conformance timed out twice in 40 runs ("the scripted model did not answer within 60 s"): worth a session of its own if it happens again. My landing gate's `grep -q -v` never failed (grep is ugrep in this shell); replaced by awk.

## Branches landed, one handoff each

Since docs/adr/0065 §5 each branch writes its own handoff under `.claude/context/handoffs/`; this file is the coordinator's: the state of the integration branch and one line per branch landed.

- `claude/m34-lean-plane-a0d988`: Handoff: M34, the lean plane (ADR 0060), 2026-11-08, [handoffs/claude-m34-lean-plane-a0d988.md](handoffs/claude-m34-lean-plane-a0d988.md)
- `claude/m35-light-gates-3dbc9f`: Handoff: M35, gates without a container (ADR 0061), 2026-11-08, [handoffs/claude-m35-light-gates-3dbc9f.md](handoffs/claude-m35-light-gates-3dbc9f.md)
- `claude/m31-front-door-9de845`: M31, the stepped way in (ADR 0057), 2026-11-08, [handoffs/claude-m31-front-door-9de845.md](handoffs/claude-m31-front-door-9de845.md)
- `claude/festive-cray-5c155e`: Handoff: each `./go ci` check runs once (ADR 0062), 2026-11-09, [handoffs/claude-festive-cray-5c155e.md](handoffs/claude-festive-cray-5c155e.md)
- `claude/sharp-khayyam-dcb1de`: the podman demo rolls back for the right reason, ADR 0066 (0063 on its branch), [handoffs/claude-sharp-khayyam-dcb1de.md](handoffs/claude-sharp-khayyam-dcb1de.md)
- `claude/console-ux-flow-1c108a`: M17's first slice, the console says whose turn it is, ADR 0063, [handoffs/claude-console-ux-flow-1c108a.md](handoffs/claude-console-ux-flow-1c108a.md)
- `claude/optimistic-meitner-aed1df`: the first run on a repository with no contract drafts it, ADR 0064, ships with the next version, [handoffs/claude-optimistic-meitner-aed1df.md](handoffs/claude-optimistic-meitner-aed1df.md)
