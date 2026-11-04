# Good first issues: drafts for the owner to open

Eight issue drafts, each from a real finding: a section of
`.claude/context/HANDOFF.md`, a ticket in `tickets/`, or the assessment of
2026-11-03 (`docs/plans/assessment-and-must-have-plan.md`). None is opened
on GitHub. The owner opens them after the repository is public (plan §15,
phase 0: 5–8 issues labelled `good first issue`, written from real
tickets).

Each draft has a title, the problem, acceptance criteria in
Given/When/Then, a perimeter (the files a fix should touch, in the
format `tickets/` uses) and labels. Every draft gets `good first issue`.
The second label names the area. GitHub creates `good first issue`,
`bug`, `documentation` and `enhancement` by default; `ci`, `harness`,
`wrapper` and `dependencies` have to be created first.

Every fix runs `./go ci` before its pull request, signs off its commits
(`git commit -s`, CONTRIBUTING.md), and adds an ADR amendment when it
changes a decision.

---

## 1. `./go ci` says NO-GO: secrets on a developer's checkout with git worktrees

- Labels: `good first issue`, `ci`
- Source: assessment of 2026-11-03 ("The `secrets` NO-GO is local but
  real", Horizon 1 item 1)

### Problem

`ci/secrets.sh` scans the working tree with `gitleaks dir` over the whole
directory. A developer who works in git worktrees or in full clones under
`.crew/` has copies of `.env` and `cosign.key` under `.claude/worktrees/*`
and `.crew/*/`. The allowlist in `ci/gitleaks-worktree.toml` is anchored
to the root paths only (`^\.crew/cosign\.key$`, `.env`), so those copies
are findings. The assessment counted eight. `./go ci` on that checkout
says `NO-GO: secrets`, while a clean clone of the same commit is green.

The gate exists to stop a secret that could be committed. Only two kinds
of file can be committed by accident: tracked files, and untracked files
that `.gitignore` does not exclude. Ignored files and nested repositories
cannot.

### Acceptance criteria

Given a checkout with a git worktree under `.claude/worktrees/x/` whose
`.env` holds a key, and a full clone under `.crew/m19/` with its own
`.crew/cosign.key`
When `./go ci` runs
Then `ci/secrets.sh` prints `GO: secrets`.

Given an untracked file that `.gitignore` does not exclude, holding a
private key
When `./go ci` runs
Then `ci/secrets.sh` prints `NO-GO: secrets — gitleaks found a secret in
the working tree`.

Given a tracked file holding a key
When `./go ci` runs
Then it is still `NO-GO`, and the history scan (`gitleaks git`) is
unchanged.

### Perimeter

- `ci/secrets.sh` (the working-tree scan: the list from `git ls-files
  --cached --others --exclude-standard`, not the directory)
- `ci/gitleaks-worktree.toml` (entries that no longer match anything
  scanned can go)
- `docs/adr/0025-release-artefact-build-sign-verify.md` (an amendment:
  the working-tree scan's scope)

---

## 2. The Codex and Gemini CLI hook recipes have never run against the real CLI

- Labels: `good first issue`, `documentation`
- Source: `.claude/context/HANDOFF.md`, M23, finding 6

### Problem

`docs/use-on-your-repo.md` §5, "Hook recipes for coding agents", gives one
recipe each for Claude Code, Codex and Gemini CLI. Each recipe runs
`lights-out gates STAGED=1` before the agent commits. None of the three
was run against a real CLI. Claude Code's shape was read from its docs.
For Codex and Gemini CLI, three facts are **not verified**:

- the name Codex gives its shell tool in a hook's input;
- whether a Codex project hook denies with exit 2 once the project's
  `.codex/` layer is trusted (ADR 0041 verified it only with
  `--dangerously-bypass-hook-trust`);
- whether Gemini CLI loads hooks in an untrusted folder.

### Acceptance criteria

Given a repository with a committed `.lights-out/` and the recipe for one
CLI installed as the guide says
When the agent stages a change that breaks a test and tries `git commit`
Then the commit is denied, the agent sees the `NO-GO: gates` line, and
the guide records the CLI's version and the date of the run.

Given the same setup with a passing change
When the agent commits
Then the commit goes through.

Given a fact the run contradicts
When the recipe is fixed
Then the guide drops its "not verified" for that fact, or says what is
still not verified.

### Perimeter

- `docs/use-on-your-repo.md` (section 5, "Hook recipes for coding
  agents")
- `docs/adr/0045-one-command-one-package.md` ("Verified while writing")

---

## 3. Every `lights-out gates` run reinstalls the dependencies (a cache for hooks)

- Labels: `good first issue`, `wrapper`
- Source: `.claude/context/HANDOFF.md`, M23, finding 5

### Problem

Every run of the `lights-out` wrapper is cold. Each hook run reinstalls
the repository's dependencies and the stack's runners (`uv sync` in
`stacks/python/runners/`, `npm ci` in `stacks/javascript/runners/`), about
50 s on `workloads/minimal`. A hook that runs before every commit makes
the agent wait that long each time. The finding names the first fix: a
cache under the wrapper's output directory (`~/.local/state/lights-out/
<repository>`, `LIGHTS_OUT_OUT`).

### Acceptance criteria

Given `lights-out gates` has run once on `workloads/minimal` as a
repository of its own
When it runs a second time with no change to the lockfiles
Then it prints the same verdict, and the time it reports is lower than
the first run's (both times go in the pull request).

Given a cache left by a run with a different lockfile
When `lights-out gates` runs
Then it does not reuse that cache for the changed dependencies.

Given the cache directory
When the wrapper mounts it
Then the repository is still mounted read-only and the engine socket is
still never passed (ADR 0045 §2).

### Perimeter

- `lights-out` (the wrapper)
- `package/entrypoint.sh`
- `docs/adr/0045-one-command-one-package.md` (an amendment: the cache)
- `README.md`, `docs/use-on-your-repo.md` (where the cache lives)

---

## 4. `./go doctor` prints no workbench line when there is no engine

- Labels: `good first issue`, `bug`
- Source: `.claude/context/HANDOFF.md`, M23, finding 7

### Problem

`./go doctor` prints one line per item (README, "If something goes
wrong"). In `core/doctor.sh` the workbench item is inside `if [ -n
"$answers" ]`, so with no engine that answers it prints nothing for the
workbench at all. A reader cannot tell "not checked" from "forgotten".

### Acceptance criteria

Given no container engine on PATH, or an engine that does not answer
When `./go doctor` runs
Then it prints a workbench line saying it was not checked and why, and
its last line is still `NO-GO: doctor — <items>`.

Given an engine that answers
When `./go doctor` runs
Then the workbench line is unchanged.

### Perimeter

- `core/doctor.sh`

---

## 5. `./go` cannot drive git from a `git worktree` checkout

- Labels: `good first issue`, `bug`
- Source: `.claude/context/HANDOFF.md`, M19, "Acceptance, run for real";
  assessment of 2026-11-03, Horizon 1 item 3

### Problem

The M19 session had to run its acceptance from a full clone at
`.crew/m19`, because `./go` cannot drive git from a `.claude/worktrees`
checkout. The likely reason, read from `go` and not yet reproduced:
`./go` mounts only the checkout's own directory into the workbench
container (`-v "$here:$here"`). In a linked worktree, `.git` is a file
pointing at the main repository's `.git/worktrees/<name>`, which is
outside that mount. A contributor who uses worktrees meets this with no
explanation.

### Acceptance criteria

Given a linked worktree (`git worktree add ../wt`)
When `./go ci` runs from it
Then it either works, or stops before building anything with one line
that says a linked worktree is not supported and names the way out (a
full clone).

Given a normal clone
When `./go ci` runs
Then nothing changes.

### Perimeter

- `go`
- `CONTRIBUTING.md` (one line, if worktrees stay unsupported)

---

## 6. Gemini CLI's guard hook does not see four file tools

- Labels: `good first issue`, `harness`
- Source: `.claude/context/HANDOFF.md`, M19, "Not done, and open
  decisions for the owner"

### Problem

`adapters/gemini-cli/entrypoint.sh` registers the guard
(`hooks/guard.sh`) on `BeforeTool` with the matcher
`run_shell_command|write_file|replace|read_file`. Gemini CLI's
`read_many_files`, `grep_search`, `glob` and `list_directory` reach files
without passing the guard. The container is still the boundary (only the
run's directory is mounted, README "Coding harnesses"), so this does not
open the host. But the guard's deny-list on key files does not apply to
those four tools. The finding names the fix: the matcher `.*`, or the
four tools added, with a hook case that proves it.

### Acceptance criteria

Given a run directory with a file the guard denies (a `.env`)
When the model calls `read_many_files`, `grep_search`, `glob` or
`list_directory` on it
Then the guard is called and denies the read, and `hooks.log` records it.

Given the change
When `./go ci` runs
Then `ci/hooks.sh` has a case for at least one of the four tools, and
`./go harness-conformance` is still GO (it runs in the workflow job of the
same name).

### Perimeter

- `adapters/gemini-cli/entrypoint.sh`
- `ci/hooks.sh`

---

## 7. opentelemetry-api 1.44.0 has a published advisory (ticket 0011)

- Labels: `good first issue`, `dependencies`
- Source: `tickets/0011.md`

### Problem

osv-scanner reports GHSA-xcq7-p3pf-p88h against `opentelemetry-api
1.44.0` in `app/backend/uv.lock`, fixed in 1.45.1. The app pins
`opentelemetry-sdk==1.44.0`, `opentelemetry-instrumentation-fastapi==
0.65b0` and `opentelemetry-exporter-prometheus==0.65b0` in
`app/backend/pyproject.toml`; the API moves only with them. The
instrumentation names the metric `verify/` reads
(`http_server_request_duration_seconds`, ADR 0011), so the bump must keep
the metric's shape.

### Acceptance criteria

The ticket's own:

Given the app's lockfile at HEAD
When `gates/deps.sh` runs
Then it reports no inherited finding for opentelemetry-api.

Given the bumped app
When `./go verify` and `./go demo` run at L0
Then the metric shape check is GO and the demo prints `GO: demo`.

### Perimeter

- `app/backend/pyproject.toml`
- `app/backend/uv.lock`

---

## 8. `ci/prompts.sh` does not check the dev-worker's brief, `worker.md`

- Labels: `good first issue`, `ci`
- Source: assessment of 2026-11-03, Horizon 1 item 3 (from the M13
  handoff)

### Problem

ADR 0020 §6 (ticket 0004): a prompt states the objective and its
acceptance, and names no gate, no gate's tool and no `./go` or `make`
target, because a model told what judges it tries to run the judge.
`ci/prompts.sh` applies that rule to `roles/*/prompt.md` only. The
dev-worker also reads its workload's brief, `worker.md` (ADR 0037 §6):
`app/worker.md` and each `workloads/*/.lights-out/worker.md` in this
repository. Nothing checks those, and one already breaks the rule:
`workloads/minimal/.lights-out/worker.md` line 9 calls `tests/mutation/`
and `tests/sast/` "the gate runners".

### Acceptance criteria

Given a `worker.md` in this repository that names a gate's tool (for
example `cosmic-ray`) or `./go gates`
When `./go ci` runs
Then `ci/prompts.sh` prints `NO-GO: prompts — <file>: <word>`.

Given the committed `worker.md` files
When `./go ci` runs
Then `ci/prompts.sh` is GO, or the same commit fixes the briefs it
flags.

Given the checker's self-test on planted files
When it runs
Then it also covers a planted `worker.md`.

### Perimeter

- `ci/prompts.sh`
- `app/worker.md`, `workloads/*/.lights-out/worker.md` (only if one
  breaks the rule)
