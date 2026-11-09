# ADR 0064 — The first run: a repository with no contract stays NO-GO, and the Action drafts the contract from the base into the check's summary and an artifact

- Status: accepted
- Date: 2026-11-09
- Milestone: M31, second slice
- Amends ADR 0045 §3 (the no-contract NO-GO becomes two lines; `init`
  takes `HEAD=`) and ADR 0057 §6 (on the first run the Action posts init's
  summary and one paragraph of its own). Consistent with ADR 0033 and its
  2026-11-04 amendment (a range is judged by the contract at its base),
  ADR 0037 §1 (lights-out never writes the repository), §4 (an attached PR
  is judged by its base), §5 (`.lights-out/*` is in `RISK_HIGH_PLATFORM`,
  not overridable), ADR 0042 §6 (what init drafts), ADR 0045 §8 (the
  Action's permissions).

## Context

The Marketplace YAML on a repository with no `.lights-out/` gives a bare
red check. Reproduced 2026-11-09 with the v0.3.0 wrapper and image on a
two-commit Python repository (workloads/minimal without `workload.env`):
`NO-GO: gates — the repository has no .lights-out/workload.env committed;
lights-out init drafts one`, exit 1, under 1 s. The way out needs podman or
docker on the user's machine; the job that printed the line has docker.

- `package/entrypoint.sh` refuses on the head's missing `workload.env`
  before it looks at the base: a PR that deletes the contract and a first
  run get the same line. With a contract at the base, the base's
  `workload.env`, `policy.env`, `runners/` judge; with none, the head's own
  (the bootstrap).
- The draft, measured 2026-11-09 by `lights-out init` on that repository
  (17.8 s wall, podman arm64, 8/8 mutants): `workload.env` 2,139 bytes,
  `policy.env` 416, `worker.md` 550, `runners/` 253,666 (`uv.lock`
  242,044); the javascript runners' `package-lock.json` is 115,476. Checks
  API, `output.summary`: "Maximum length: 65535 characters" (external).
  Three files fit; the draft whole does not.
- What init infers comes from the commit it reads: `TEST_CMD` from
  `package.json` `scripts.test`, the scope from `pyproject.toml`, and
  `MUTATION_BASELINE` from running that commit's suite.
- docs.github.com, read 2026-11-09: required checks pass on "successful,
  skipped, or neutral"; a PR opened with `GITHUB_TOKEN` gets runs "in an
  approval-required state"; personal-account repositories by default do
  not let workflows create pull requests; a fork PR's token is read-only.
- actions/upload-artifact v7: hidden files skipped unless
  `include-hidden-files: true`; "File permissions are not maintained"
  (644); retention 90 days by default (external); download needs a
  logged-in user. The draft calls its runners through `sh`, `python3`,
  `node`, never by mode. Pinned here at `cf430e0…` (v7.0.2).

## Decision

1. **Candidate (b).** The first run is NO-GO: check run `failure`, job
   exit 1. No check is `neutral` or `success` without a committed contract.
2. **Three cases, in the entrypoint, on the range judged** (base: `BASE`,
   else `HEAD~1`, else none). `<name>` is `gates`, `test-proof` or
   `test-integrity`.
   - The head has `workload.env`: unchanged, bootstrap included.
   - The head lacks it, the base has it: `NO-GO: <name> — the change
     removes .lights-out/workload.env, which its base has; a change cannot
     remove the contract that judges it`. No draft.
   - Neither has it, or there is no base: today's line, unchanged, `NO-GO:
     <name> — the repository has no .lights-out/workload.env committed;
     lights-out init drafts one`. With `STAGED=1` the order stays: the
     repository's HEAD, the staged change's base, lacking it gives this line.
3. **`init HEAD=<commit>` drafts from that commit**; without it, from HEAD
   as today; an unknown commit is `NO-GO: init — HEAD=<commit> is not a
   commit of the repository (a shallow checkout? fetch-depth: 0)`. Every
   init writes `init/summary.md` in the output directory: `### lights-out
   init, drafted from <short sha>`, init's line, then on GO `workload.env`,
   `policy.env` and `worker.md` each in a fence its content cannot close,
   and `runners/` one line per file with its bytes; on NO-GO (no stack, no
   baseline measured) the line and "no draft is offered". No container or
   host path: the clone is "the repository", the draft `.lights-out/`.
4. **The Action, on the first-run line only** (its reason matched
   exactly), runs `lights-out init HEAD=<from>`: `<from>` is the base it
   gave the gates (input `base`, else the PR's base), else the head judged.
   On GO it uploads the draft, through upload-artifact at that pin with
   `include-hidden-files: true` and `overwrite: true`, as
   `lights-out-draft-<job id>`: unzipped at the repository's root it is
   `.lights-out/` and nothing else. Check and step summary: the line block
   (today's fallback), init's `summary.md`, and, when uploaded, the
   artifact's name and URL and, to run at the root after review,
   `gh run download <run id> -R <owner>/<repo> -n lights-out-draft-<job id>`
   and `git add .lights-out && git commit -m "lights-out: the contract
   drafted from <short sha>"`. Init's outcome changes neither the line, the
   conclusion nor the exit. Permissions stay `contents: read`, `checks:
   write`.
5. **A laptop `gates` does not draft.** It gets §2's wording; `lights-out
   init` is one command away, on the engine it just used.
6. **Proof.** `package.yml`'s `action` job, before today's steps: a scratch
   repository from workloads/minimal without `workload.env`, commits c1,
   c2; the Action on c1..c2 prints the first-run line, fails its step,
   posts a `failure` check titled with it whose summary names c1 and the
   artifact and holds the three files; the artifact, unzipped at the root
   and committed as c3, then a good change c4: the Action on c3..c4 is
   `GO: gates — …`. `./go demo-package`, outside its timed part: the
   removal line, `init HEAD=`, `init/summary.md` with no `/tmp/` or output
   path, a no-stack init. `ci/package.sh`: the matched reason equals the
   entrypoint's, the pin and `include-hidden-files`, no new permission.

## Alternatives rejected

- **(a) Judge with the draft, advisory.** From the head, the PR sets its
  own bar (ADR 0045's rejected "judge with HEAD's contract"); `neutral`
  passes a required check, so no contract is ever needed; `failure` is (b)
  plus a verdict from an unreviewed contract and a second verdict grammar.
- **(c) An init input or Action that opens a PR.** Its runs wait for
  approval, the setting is off by default, a fork's token cannot, and it
  needs `contents: write` + `pull-requests: write` to write the user's
  repository (ADR 0037 §1).
- **Draft from the head.** A fork would shape what the owner commits.
- **The whole draft in the summary.** 253,666 bytes against 65,535.
- **Runners fetched from lights-out's tag.** A dev or `sha-` image has no
  tag; two sources for one draft.
- **Judge a removal with the base's contract.** A GO there leaves every
  later range with no contract.
- **A `draft: false` input.** Committing the contract turns it off.

## Consequences

- **The one that will hurt: until the contract is committed, every run
  pays a whole-scope mutation run of its base before going red.** 17.8 s
  on workloads/minimal; 792 s on the app's package (ADR 0042). A repository
  that keeps the Action and never commits pays it on every PR.
- The Action's branch hangs on a reason's exact text; `ci/package.sh`
  ties the two copies.
- A PR whose base has no stack yet (it adds `pyproject.toml`) gets no draft
  until merged.
- The bootstrap stays: a PR adding a contract is judged by it, high under
  `.lights-out/*`, so reviewed; its GO is the PR's claim.
- A `STAGED=1` removal is still judged by HEAD's contract (§2's order).
- An artifact expires with the repository's retention; re-run to redraft.

## Golden-rule check

`./go demo` does not use the image or the Action. `./go ci` gains static
checks in `ci/package.sh`: no engine, no network, no key. The artifact and
`gh` are GitHub's and stay in `action.yml`; nothing enters `core/`. Passes.
