# Launch checklist

What is left before the repository goes public and on launch day. It is
split into what the owner does (the owner's accounts, keys and GitHub
settings) and what is done in the repository. Each line gives the command
or the GitHub setting.

Sources: `docs/PLAN.md` §15 (phase 0, what is measured, risks) and §16;
`docs/plans/assessment-and-must-have-plan.md` (Horizon 1, "Measured before
launch"); `.claude/context/HANDOFF.md`, the M21 and M23 sections; the
README. A line taken from another file names that file.

Publishing is the owner's act: making the repository public, the tag,
the image, the issues and the announcement (plan §14, §15).

## The owner does: before launch

### Decide the numbers first

- [ ] **Set the target numbers before launch.** Plan §15, "Cosa si
  misura": stars, clones and unique visitors (GitHub → Insights →
  Traffic), issues opened by outsiders, outside contributors, talk
  invitations, inbound consulting requests. A target chosen afterwards
  measures nothing. The same goes for the signals that would start the
  search for a co-founder.

### Merge what is pending

- [ ] **Merge the open branches into `main`**, this one included, through
  a `merge/<name>` branch once Actions is green on it
  (`docs/plans/third-arc-execution.md`). That includes the two parallel
  sessions: egress for the harnesses, and the tower restoring
  `.lights-out/runners/` from the base. M23's finding 2 says the second
  must land before M24 runs on a repository the owner does not control.
- [ ] **`./go demo` green on Linux and on macOS** from a clean clone, before
  every announcement (plan §15, "Rischi").
  ```sh
  git clone https://github.com/nicolaguglielmi/lights-out.git
  cd lights-out
  ./go demo
  ```
  The last line is `GO: demo, milestone M9, <n>s to rollback (budget
  900s, plan §2)`. A first run over the budget now says `a first run: over
  the 900s budget, reported, not judged` (ADR 0013, amendment 2026-11-04).
  Run it again to get the judged figure.

### The recordings that spend keys

- [ ] **Record the Claude and OpenAI harnesses** (README, "Coding
  harnesses"; HANDOFF M19). Each writes
  `fixtures/0001/dev-worker/<harness>/`:
  ```sh
  ./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=claude-code MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5
  ```
  ```sh
  ./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=codex MODEL_PROVIDER=openai MODEL=gpt-6.1-sol
  ```
  Then read `tokens`, `turns` and `model` in each `run.json`. The first
  run may stop on a budget measured on Gemini.
- [ ] **Record an ADK role with Claude and with OpenAI** (plan §16, M18's
  "Fatto quando"; implemented, never run):
  ```sh
  ./go record-evals PROFILE=l1 MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5
  ```
  and the same with `MODEL_PROVIDER=openai MODEL=gpt-6.1-sol`.
- [ ] **Write the cost per provider in the README**, from those
  `run.json` files. The README says: "The cost per provider will be stated
  here once those recordings exist". Plan §16's "Rischi" asks for it before
  launch.
- [ ] **Re-record fixtures 0001 and 0005 under the shipped prompt** (two
  L1 runs with the owner's key, assessment Horizon 1 item 4). The
  assessment dated this on 2026-11-03; check that it is still needed.
  ```sh
  ./go record TICKET=0001 PROFILE=l1
  ```
  ```sh
  ./go record TICKET=0005 PROFILE=l1
  ```

### GitHub as code host (M21)

- [ ] **The throwaway repository** (HANDOFF M21, "What the owner must
  do"): an empty GitHub repository with `workloads/minimal/`'s contents at
  its root, committed and pushed. Merge commits allowed (GitHub's default).
- [ ] **The token**: github.com → Settings → Developer settings →
  Fine-grained tokens. Only that repository. Contents, Pull requests and
  Commit statuses, read and write.
- [ ] **The one L1 end-to-end on GitHub.** In `.env`:
  `GITHUB_REPO=<owner>/<name>`, `GITHUB_TOKEN=…`, `GEMINI_API_KEY=…`. Clone
  the throwaway, then:
  ```sh
  ./go attach <clone>
  ```
  ```sh
  ./go e2e CODE_HOST=github PROFILE=l1
  ```
  Expected: the PR opens on GitHub with the `gates` status, merges after
  `GO: gates`, the merge is built, signed and released on the local
  plane, the canary (0.2.0-outage) rolls back, and `GO: e2e` follows.
  This is the first execution of the attached release path anywhere
  (M21 finding 3). Record the result in plan §16 M21. Afterwards, pull the
  clone and run `./go attach` again before any other ticket.
- [ ] **The nightly.** This repository → Settings → Secrets and
  variables → Actions: the variable `LIGHTS_OUT_GITHUB_REPO` and the
  secret `LIGHTS_OUT_GITHUB_TOKEN`. It runs from the default branch, so
  after the merge to `main`. Run it once by hand: Actions → the
  `nightly-github` workflow → Run workflow (`workflow_dispatch`). Each run
  leaves a merged PR and a `conformance/<id>` branch in the throwaway
  repository.

### The package (M23)

- [ ] **Check the version** in the `version=` line of `lights-out`
  (`0.1.0`). Change it before the tag if you want another.
- [ ] **Push the tag from the merge on `main`** (HANDOFF M23, "What the
  owner must do to publish"):
  ```sh
  git tag v0.1.0 && git push origin v0.1.0
  ```
  The `publish` job of `package.yml` checks the tag equals `v$version`,
  builds amd64 and arm64 through QEMU and pushes
  `ghcr.io/nicolaguglielmi/lights-out:0.1.0`. The multi-platform build has
  **never run**: expect it to be slow (the workbench under QEMU for arm64),
  and look there first if it fails.
- [ ] **Make the package public**: GitHub → the package → Package
  settings → Change visibility → Public. It is linked to the repository
  by the `org.opencontainers.image.source` label.
- [ ] **The release `v0.1.0` with notes** (plan §15, phase 0): GitHub →
  Releases → Draft a new release → tag `v0.1.0`.
- [ ] **Prove the plan's own criterion for M23** once the image is public:
  a PR on another repository with
  `uses: nicolaguglielmi/lights-out@v0.3.0` (the root Action; up to
  v0.2.0 the path was `nicolaguglielmi/lights-out/action@<tag>`), and
  `lights-out gates` on a clean machine that pulls the published image.
  Since ADR 0057 the 300 s include the first pull.
- [x] **Update the README's "Not published yet" paragraph** once the image
  and the package are public. Done 2026-11-05 with `v0.1.0`.

### The gates image and the three Actions (M31)

Nothing here has run yet. Publishing is your act (ADR 0057).

- [ ] **Check `version=0.3.0`** in `lights-out` (the wrapper). The
  `publish` job refuses a tag that is not `v` plus that version.
- [ ] **Tag `v0.3.0` from the merge on `main`.** The `publish` job of
  `.github/workflows/package.yml` builds both images for amd64 and arm64,
  pushes them to ghcr.io and signs both keyless. It has never run, so look
  there first if anything fails.
- [ ] **Make the new package `lights-out-gates` public**: GitHub → the
  package → Package settings → Change visibility → Public.
- [ ] **Verify both signatures** from a machine with cosign. Run it once
  for `lights-out-gates:0.3.0` and once for `lights-out:0.3.0`:
  ```sh
  cosign verify ghcr.io/nicolaguglielmi/lights-out-gates:0.3.0 \
    --certificate-identity-regexp '^https://github.com/nicolaguglielmi/lights-out/.github/workflows/package.yml@refs/tags/v' \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com
  ```
- [ ] **Draft the root Action's Marketplace release** from the banner of
  `action.yml`: GitHub → Releases → Draft a new release → tick "Publish
  this Action to the GitHub Marketplace", pick a primary category, accept
  the GitHub Marketplace Developer Agreement. Two-factor authentication
  must be on for the account.
- [ ] **For each standalone Action, a public repository of its own**:
  `nicolaguglielmi/test-proof` and `nicolaguglielmi/test-integrity`. Copy
  `actions/test-proof/` (or `actions/test-integrity/`) to the root of the
  repository, tag `v0.3.0`, and publish the release to the Marketplace the
  same way. The copies can lag a version without any check failing:
  `ci/package.sh` checks the sources here, never the copies.
- [ ] **Measure the first pull.** In the public probe repository
  `nicolaguglielmi/lights-out-probe` (made public on 2026-11-08 because the
  account's Actions billing refused a private run), set the workflow's and
  the two shims' `uses:` to `@v0.3.0`, drop the step that builds the image
  and the `image:` inputs, and push a change on a pull request. The three
  times then include the first pull: write them in the README's step 1,
  replacing the 19 s, 2 s and 17 s measured with the image built in the
  job. Delete the probe afterwards if you do not want it public.

### The Python package on PyPI (M35)

The light tier, `lights-out gates --light`, is a Python package built from
the root `pyproject.toml` (ADR 0061). Publishing it is the owner's act.

- [ ] **Publish soon after the merge.** The name `lights-out` was free on
  PyPI on 2026-11-08 (`https://pypi.org/pypi/lights-out/json` answered 404),
  not reserved: until the first upload, `uvx lights-out` in a hook recipe
  runs whatever package holds the name.
- [ ] **Set the version** in `pyproject.toml` (`0.3.0.dev0` today) to the
  release. A release that also ships the image sets the wrapper's
  `version=` in `lights-out` to the same: `package.yml` checks the tag
  against the wrapper only.
- [ ] **Build from a clean clone of the merge on `main`** and look inside:
  ```sh
  uv build
  python3 -m zipfile -l dist/lights_out-*.whl
  ```
  The wheel holds `lights_out/*.py`, `lights_out/perimeter.sh` and
  `lights_out/platform_policy/merge.env`, and no `tests/`.
- [ ] **Try the wheel** in a repository with a committed `.lights-out/`:
  ```sh
  uvx --from ./dist/lights_out-0.3.0-py3-none-any.whl lights-out gates --light
  ```
- [ ] **Upload**, from a PyPI account with two-factor authentication and a
  token scoped to the project, the token in the environment, never in a
  file (TestPyPI first, if you want a dry run:
  `--publish-url https://test.pypi.org/legacy/`). `uv publish` asks for the
  token, or reads it from uv's own token variable:
  ```sh
  uv publish
  ```
  No workflow publishes it: trusted publishing from GitHub Actions would be
  a new workflow, a repository change.
- [ ] **After the upload**, on a clean machine: `uvx lights-out gates
  --light` in a repository with a contract. Then drop "Not on PyPI yet"
  from `docs/use-on-your-repo.md` (the hook recipes and the status table),
  `docs/reference.md` and the README.

### The README's front page

- [ ] **Record the rollback** (plan §15, phase 0; assessment Horizon 1
  item 3): a terminal recording under 60 seconds of the canary at 5%,
  verify NO-GO, and the return to 100/0 on its own. It goes at the top of
  the README. `./go demo-rollback` is the one-minute path (README, "Shorter
  looks").
- [ ] **Measure the time to a first GO on your own repository** without
  the plane. Target: under 10 minutes (assessment, "Measured before
  launch"). The second measure there, two tickets in three reaching a
  mergeable PR with no human touching the code, is M24's exit criterion
  (plan §14), not a launch-day number.

### GitHub settings

- [ ] **Description and topics**: the repository page → About (the gear).
  Plan §15's topics: `ai-agents`, `coding-agents`, `guardrails`,
  `canary`, `progressive-delivery`, `platform-engineering`, `devsecops`,
  `gemini`, `adk`. The assessment found the topics already set on
  2026-11-03; check them against the list.
- [ ] **Social preview image**: Settings → General → Social preview.
- [ ] **Discussions on**: Settings → General → Features → Discussions.
  Plan §15 says Discussions are enough: no Discord or Slack that 10 hours
  a week cannot staff.
- [ ] **Private vulnerability reporting on**: Settings → the security
  section → Private vulnerability reporting → Enable. `SECURITY.md` and the issue form's
  contact link send reporters to the Security tab's "Report a
  vulnerability" button, which exists only with this on. (From
  `SECURITY.md`, not from the sources above.)
- [ ] **Create the labels, then open the good first issues** from
  [good-first-issues.md](good-first-issues.md): 6–8 issues labelled
  `good first issue` (plan §15, phase 0). That file lists the labels to
  create first.

### The soft launch

- [ ] **Soft launch to 10–20 trusted people** (colleagues, Italian
  communities), on Linux and macOS, with one question: "did `./go demo`
  reach the end on your machine?" (plan §15, phase 0; assessment Horizon
  1 item 5). Fix every friction found before anything public.

## The owner does: on launch day

- [x] **Flip the repository to public** (done 2026-11-04): Settings → General → Danger
  Zone → Change repository visibility → Public. Only then does the
  wrapper's raw-URL download work for strangers (HANDOFF M23).
- [ ] **`./go demo` from a clean clone of the public URL**, once more, on
  the day (plan §15, "Rischi": a quickstart broken on launch day).
- [ ] **One message everywhere** (plan §15, "Il messaggio"): autonomous
  agents that carry a change to production on a codebase nobody
  trusts — numeric gates, a declared perimeter, automatic rollback, one
  human before 100%. The hook is the automatic rollback of a change an
  agent wrote. Say *one* human, *one* gate; never "human in the loop".
- [ ] **No Show HN yet.** Plan §15 puts Show HN, newsletters and the long
  article in phase 2, after the experiment: "the first judgement is the
  one that stays". Launch day for phase 0 is the public repository, the
  soft launch's fixes and the weekly diary (phase 1).
- [ ] **Answer outside issues and PRs within 48 hours** (plan §15, "Il
  ritmo settimanale").

### Product Hunt, the week after Show HN

A second wave, not the launch. Product Hunt's readers are makers and
product people; fewer of them run a DevOps toolchain, and a dev tool there
converts to stars far below Hacker News (the adoption roadmap, section 3.3:
Hacker News exposure is worth about +121 stars in 24 h). A first impression
there happens once, so it waits for the prerequisites.

- [ ] **Prerequisites**: `v0.3.0` tagged and both images signed, the
  package on PyPI, the root Action on the Marketplace, the README's
  recording real, M24's numbers published, Show HN done (plan §15, phase 2).
- [ ] **The "coming soon" page**, any time before: it costs nothing and
  collects followers who are told on launch day.
- [ ] **Launch on a Tuesday or Wednesday at 00:01 Pacific**, the week
  after Show HN. The tagline is the one message in under 60 characters
  (draft: "Autonomous agents to production, behind gates, one human GO").
- [ ] **The gallery from the console** (M33): the kanban, a ticket's
  timeline down to the rollback, the overview; the demo's recording from
  the README. The first comment tells the one human gate, the 15-minute
  demo with no account and no card, and gives `uvx lights-out gates
  --light` as the ten-second try.
- [ ] **Stay in the comments all day** and answer within the hour: launch
  day costs a day of the owner's time.
- [ ] **Measure** stars and unique visitors over the 48 h after, beside
  Show HN's, in the adoption roadmap's section 8.

## Done in the repository

| Item | Where |
|---|---|
| `CONTRIBUTING.md` with the DCO, `ROADMAP.md` in English, `SECURITY.md` | repository root |
| Issue forms (bug, attach, gate bypass) and a pull request template | `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` |
| ADR 0031 committed (assessment Horizon 1 item 2) | `docs/adr/0031-worker-brief-report-and-durable-tower-documents.md` |
| `.DS_Store` ignored (assessment Horizon 1 item 2) | `.gitignore` |
| ROADMAP follows plan §14 and §16: M18 and M20–M23 done, M24 next | `ROADMAP.md` |
| A local first run of `./go demo` reports its time over the 900 s budget instead of failing; CI and later runs are judged | `go`, `Makefile` (`demo`), ADR 0013 amendment 2026-11-04, ticket 0010 item 6 |
| The `launch` job's "envoy-canary not ready after 180s": the backend now restarts when flagd is not ready at import | `app/compose.yaml`, `workloads/minimal/.lights-out/compose.yaml`, ticket 0010 item 7 |
| Ticket 0010, the pre-launch audit's hardening items, closed | `tickets/0010.md` |
| Eight good-first-issue drafts from real findings | [good-first-issues.md](good-first-issues.md) |
| The README states what is real, recorded, hand-written and not yet published | `README.md`, "What is real and what is recorded" |
| The image and the Action built and tested on every push; `publish` only on a `v*` tag or a dispatch | `.github/workflows/package.yml` |
| The nightly against GitHub, skipping with a notice while its variable is unset | `.github/workflows/nightly-github.yml` |
