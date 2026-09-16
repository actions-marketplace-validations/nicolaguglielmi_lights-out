# ADR 0017 — Agent runtime at M5: `AgentHarness` is `adapters/<name>/run.sh` over a cloned workspace; `core/crew.sh` drives ticket → PR through Tracker and CodeHost verbs; the Gemini CLI worker is workbench + `@google/gemini-cli` in compose with hooks as the guardrail and the app's tests in reach; the one real L1 run of ticket 0001 is recorded into `fixtures/` and replayed at L0; `demo-crew` is the acceptance; the runner socket moves to M6

- Status: accepted (amends ADR 0015 §7 and consequences [runner socket and the first Gitea job move to M6; no Gitea job needs the socket at M5], ADR 0015 §6 alternatives [`fixtures/` does not replace `honest-fix`], ADR 0016 §2 [`platform` gains `roles/*`, `fixtures/*`, `.gemini/*`], ADR 0012 consequences [`actions/checkout` mirror is M6's]; fixes the `.env` clobbering in `gates/mutation.sh` and `mutation-baseline`; amended by ADR 0018 §3 [the pinned CLI version is no longer `0.59.0`] and its "Contradicts the plan" section [the substitution is a fixed upstream bug, not a standing property])
- Date: 2026-09-15
- Milestone: M5

## Context

M5 (plan §7): the `AgentHarness` port with `replay` and `gemini-cli`, the
six role definitions, hooks against push-to-main, destructive commands and
secret access, a containerised worker with token, time and turn budgets
that ends by opening a PR. Done when at L1, with a Gemini API key, a ticket
becomes a PR that passes M4's CI, and at L0 the same ticket yields the same
PR from fixtures. Owner decisions: a key is available in this session, so
ticket 0001 runs once for real and its output is the L0 fixture; "passes
M4's CI" means `make gates` from workbench on the fetched PR branch (the
`demo-gates` worktree mechanism), Gitea Actions and the runner socket are
M6's. Facts verified 2026-09-15 against Gemini CLI v0.59.0 docs and source
are cited inline; what could not be verified without a key is listed under
"verify at L1" and the build must close each item before the milestone
closes. Repo facts: `AGENT_HARNESS`, `TRACKER`, `ORCHESTRATOR` are declared
in every profile and consumed nowhere; `core/launchpad.sh` is the
vendor-free controller precedent; Gitea has no users, no repo, no volume;
the runner is host mode on the workbench image with no socket.

## Decision

1. **The port is one verb, `adapters/$AGENT_HARNESS/run.sh`, with an env
   contract and a directory of artefacts.** Input: `ROLE`, `TICKET` (id),
   `TICKET_FILE` (path to the ticket markdown), `WORKSPACE` (a clean git
   clone on branch `ticket/<id>`), `BASE` (the sha the branch starts from),
   `OUT` (an empty directory), plus the role's budgets `THINKING`,
   `MAX_TURNS`, `TIMEOUT_S`, `TOKEN_BUDGET`. Success = exit 0, the
   workspace holds one or more commits over `BASE`, and `OUT` holds
   `patch` (`git format-patch --stdout BASE..HEAD`, one file), `pr.json`
   (`{"title","body"}`), `run.json` (`{"harness","model","thinking",
   "turns","tokens":{"input","output","total"},"duration_s","exit_code"}`),
   and whatever evidence the harness has (`transcript.jsonl`, `hooks.log`
   for gemini-cli). Adapter convention (ADR 0012 §6): not a gate, silent on
   success, one stderr line and exit ≠ 0 on failure. **The PR text is the
   harness's final response: first line title, the rest body.** Every
   harness the table names has a final message; not every one lets a model
   write outside the workspace, and a file the model writes inside it would
   land in the diff. **The adapter commits, not the model**: identity
   `lights-out-crew <crew@lights-out.invalid>` (the `lights-out-fixtures`
   precedent), message = title + body, so the commit and the PR say the
   same thing. A model that commits anyway loses nothing: its commits are
   kept, a dirty remainder is committed on top. Clean tree and no commit
   over `BASE` = failure "worker produced no change". **Harness-independent
   invariant (HANDOFF's own warning, not re-derived): exit 0 is not success
   by itself.** An empty `patch`, no commit over `BASE`, a missing
   `pr.json`, or a `pr.json` with an empty title is a failure regardless of
   the harness's exit code — the documented failure mode where a headless
   coding-agent CLI (Antigravity's, observed and reported) exits 0 having
   produced nothing. `core/harness-check.sh` runs after every
   `adapters/$AGENT_HARNESS/run.sh` and enforces exactly this, independent
   of which harness ran; `ci/harness.sh` proves it on stub `OUT` directories
   (empty patch, missing pr.json, empty title, and a valid case), each
   answering GO or NO-GO with no model involved.
2. **`replay`: `adapters/replay/run.sh` copies `fixtures/<ticket>/<role>/*`
   into `OUT`, `git am`s the recorded `patch` into `WORKSPACE`, and writes
   its own `run.json`: `{"harness":"replay","model":null,"source":
   "fixtures/<ticket>/<role>","recorded":<the recorded run.json>}`.** A
   replayed run never claims tokens it did not spend. A missing fixture
   fails with the exact record command (`./go record TICKET=<id>
   PROFILE=l1`). No model call; the README says "at L0 the worker replays
   the recorded PR of the one real run; it does not re-execute tool calls".
3. **`gemini-cli`: a compose service `gemini-cli` (profile `crew`) built
   `FROM ${WORKBENCH_IMAGE}` plus `npm ci` of a committed
   `adapters/gemini-cli/package.json` + `package-lock.json` pinning
   `@google/gemini-cli@0.59.0` (2026-09-08, Apache-2.0).** The runner
   precedent (ADR 0012 §3): workbench already carries node 24, python3
   3.13, uv, git, jq, `timeout`; no second base image, no new sha256 pins,
   the lockfile is the pin (the frontend precedent). No engine socket, on
   the plane network, `depends_on: postgres`. Two bind mounts with
   `security_opt: label=disable` (ADR 0012 §2): `./.crew:/crew`
   (gitignored; workspace, out, uv cache live there) and `./roles:/roles:ro`.
   `user: "${CREW_UID:-0}:${CREW_GID:-0}"` from `id -u`/`id -g` in the
   Makefile — 0 under rootless podman, the host uid under docker, so files
   the model's `git` writes in the workspace stay writable by workbench;
   `HOME=/tmp/crew-home` because that uid has no passwd entry. Env:
   `GEMINI_API_KEY: ${GEMINI_API_KEY:-}` (the `:-` keeps `ci-compose`
   green at L0; the adapter fails first, loudly, on an empty key or the
   `.env.example` placeholder `replace-me`), `GIT_AUTHOR_*`/`GIT_COMMITTER_*`
   = the crew identity, `UV_PROJECT_ENVIRONMENT=/tmp/crew-venv` (the venv
   must not land in the workspace), `UV_CACHE_DIR=/crew/.uv-cache`,
   `POSTGRES_MAINTENANCE_URL` and `TEST_DATABASE_URL` as `backend-test` has
   them (§10). Per run, `-e ROLE`, budgets, `CREW_OUT`. Inside, the
   adapter's entrypoint (`COPY`ed into the image, ADR 0012 §2) writes
   `$HOME/.gemini/GEMINI.md` ← `/roles/$ROLE/prompt.md` and generates
   `$HOME/.gemini/settings.json` from `role.env`: `security.auth.selectedType
   = "gemini-api-key"`, `model.name = "gemini-3.8-flash"`, a model alias
   with `thinkingConfig.thinkingLevel = <THINKING uppercased>`,
   `model.maxSessionTurns = MAX_TURNS`, `tools.exclude = [web_fetch,
   google_web_search]` (the ticket and the repo are the spec; a fetch is
   also the one channel a prompt injection in repo content could use to
   exfiltrate the context), `hooks` (§9). Nothing Gemini-specific is
   written into the workspace. Run: `cd $WORKSPACE && timeout $TIMEOUT_S
   gemini -p "$(prompt)" --approval-mode yolo --output-format stream-json
   > $OUT/transcript.jsonl`, the prompt = the ticket text plus three
   lines (work here, do not commit or push, final message = PR title then
   body). Exit 53 (turn limit, verified) → "over MAX_TURNS", 124 → "over
   TIMEOUT_S", other non-zero → the `error` event's message; all fail
   without a PR. After the run, in workbench: commit (§1), `patch`,
   `pr.json` from the `result` event's response, `run.json` from its
   `stats`. Two key guards: `grep -F "$GEMINI_API_KEY" $OUT/*` must find
   nothing, or the run fails and nothing is recorded; `ci/secrets.sh`
   scans every committed transcript on every `ci`.
4. **The driver is `core/crew.sh`, POSIX sh, vendor-free, `launchpad`'s
   shape; the Makefile target is `assign TICKET=<id> [ROLE=dev-worker]`.**
   Steps: `sh adapters/$CODE_HOST/bootstrap.sh` (§5); `sh
   adapters/$TRACKER/get.sh $TICKET > .crew/$TICKET/ticket.md`
   (`adapters/file/get.sh` prints `tickets/<id>.md` after validating the
   id — five lines, and the port the profile already declares; `core/`
   never spells `tickets/`); `git clone $(sh adapters/$CODE_HOST/clone-url.sh)
   .crew/$TICKET/workspace`, `git checkout -b ticket/$TICKET`; `.
   roles/$ROLE/role.env`; `sh adapters/$AGENT_HARNESS/run.sh`; `sh
   adapters/$CODE_HOST/push.sh <workspace> ticket/$TICKET` (force); `sh
   adapters/$CODE_HOST/open-pr.sh ticket/$TICKET <pr.json>` prints
   `<number> <url>` (idempotent: an open PR for that head is reused);
   `.crew/$TICKET/pr-opened.env` (`PR_NUMBER`, `PR_URL`, not recorded);
   stderr `[crew] ticket 0001: PR #1 <url>`; `go`. **The model never
   holds a credential**: the clone URL is anonymous (the bootstrapped repo
   is public, like every L0 port), `push.sh` passes the authenticated URL
   as a command argument, never into `.git/config`; Gitea refuses an
   anonymous push, so the hook's `git push` denial is the second layer,
   not the first. `assign`, `demo-crew`, `record` join `go`'s socket list.
5. **Gitea bootstrap, `adapters/gitea/bootstrap.sh`, idempotent, called
   by `assign` (not by `up`):** `docker-compose exec -T gitea gitea admin
   user create --admin --username lights-out --password
   lights-out-local-not-a-secret --must-change-password=false` (the API
   cannot create the first user under `INSTALL_LOCK`), `POST
   /api/v1/user/repos` `lights-out/lights-out` public, `PATCH` it with
   `has_actions: false`, `git push --force <authenticated url>
   HEAD:refs/heads/main` from the local checkout. Credentials and URLs in
   `adapters/gitea/env.sh`, sourced by the four scripts; the password is
   low-entropy on purpose (ADR 0012 §9: a duller string, never a gitleaks
   allowlist; the scripts pass `-u "$GITEA_USER:$GITEA_PASSWORD"`, never a
   literal, because gitleaks 8.30 has a `curl-auth-user` rule). Not in
   `up`: `./go demo` must not grow a stage whose result nobody reads, and
   `up` stays what M2 promised. **Actions off on the repo**: a job that
   runs on every push, needs gitea.com for `actions/checkout`, and whose
   result M5 never consults is noise on a laptop and a red badge in a
   talk; M6 turns it on the day it consumes the result. **Amends ADR 0015
   §7 and consequences**: the runner socket lands at M6 under the same
   three conditions; "M5 is not closed while the runner lacks it and a
   Gitea job needs it" is void because no Gitea job runs at M5.
6. **`demo-crew` is the acceptance; `record` makes the fixture; fixtures
   live in `fixtures/<ticket>/<role>/`; `honest-fix` stays.** `demo-crew`
   = `up`, `assign TICKET=0001`, `git fetch <clone-url> ticket/0001` from
   the code host (proves the PR branch exists there, not in `.crew/`),
   `git worktree add --detach <mktemp>/wt FETCH_HEAD`, `$(MAKE) -C <wt>
   gates BASE=<HEAD sha> HEAD=<fetched sha>`, `verdict.env` diffed against
   `fixtures/0001/dev-worker/expect`, `GO: demo-crew`. The `demo-gates`
   code, reused. `record TICKET=<id>` = `demo-crew` at `PROFILE=l1`, then
   `cp .crew/<id>/out/* fixtures/<id>/<role>/` and `verdict.env` →
   `expect`; it refuses at L0 ("recording a replay is circular"), refuses
   a NO-GO or over-budget run (kept in `.crew/` for study), and HANDOFF
   records how many attempts the recorded run took, with the context for
   each: what the model did, which gate or which budget stopped it. That
   is the worker's reliability measurement at M5, not a footnote — the
   number a stranger reading HANDOFF needs before trusting the L0 replay
   is representative of a real run, not a lucky first try edited quietly
   out of the record. Fixture files: `patch`,
   `pr.json`, `run.json`, `transcript.jsonl`, `hooks.log`, `expect`; plan
   §6 reserves `fixtures/` for recorded model responses, and these are
   exactly that. `gates/fixtures/honest-fix` stays (contradicting ADR 0015
   §6 alternatives): it is a hand-written positive control with known
   mutants and a shared base across six fixtures, and `demo-gates` judges
   the gates; the recorded PR is whatever the model did — re-recording it
   must not move the gates' control. Workflow: one added job `crew`,
   `if: github.server_url == 'https://github.com'`, `run: ./go demo-crew`,
   `CONTAINER_ENGINE=docker` — at L0 it exercises bootstrap, replay, push,
   PR and gates on every push. `demo-crew` does not join `./go demo` (ADR
   0015 §8: M6's `e2e` carries it).
7. **Roles: six directories, `role.env` in every one, a prompt and budgets
   only where a run exists.** `roles/<role>/role.env` (`policy/merge.env`
   format): `THINKING` for all six from plan §5's table (provenance: plan,
   owner decision); `MAX_TURNS`, `TIMEOUT_S`, `TOKEN_BUDGET` for
   `dev-worker` only (§8). `roles/dev-worker/prompt.md` is the standing
   instruction the adapter installs as the global `GEMINI.md`; the other
   five hold `ROLE.md` naming what runs them and when (`test-reviewer`,
   `architect`: this port, M6; `product`, `release`, `ops-triage`: ADK,
   M7). **Why a prompt only where a run exists, not why not**: a prompt is a
   claim about how a model behaves against it, and the only way to know if
   the claim holds is to run it; five roles have no run at M5, so a prompt
   for them would be an unexercised hypothesis, and M6/M7 would rewrite it
   against their own first real run anyway rather than trust one nobody
   tested. Writing it now spends words that get discarded, not saved.
   **Not `GEMINI.md` inside `roles/`**: Gemini CLI discovers context files
   in sub-directories below cwd (`context.discoveryMaxDirs`), and the
   workspace is a clone of this repo, so six `roles/*/GEMINI.md` would all
   load into the dev worker; a plan §6 naming deviation, for that reason.
   **No harness field in `role.env`**: the profile's `AGENT_HARNESS` runs
   every role; `crew.sh` NO-GOs on a role without prompt and budgets,
   naming the milestone. A per-role override (one role on
   `antigravity-sdk`, L3) is decided when a second real harness exists.
   **`RISK_HIGH_PLATFORM` gains `roles/*`, `fixtures/*`, `.gemini/*`**
   (amends ADR 0016 §2): prompts and hooks are the platform, a fixture
   change changes what L0 replays, and `.gemini/settings.json` in the
   repo would reconfigure the worker (project settings override user
   settings, verified precedence); one unit case each in `core/tests`.
8. **Budgets, initial values with provenance, re-measured by the recorded
   run.** `MAX_TURNS=60` → `model.maxSessionTurns`: external constraint,
   the free tier's 250 requests/day (verified), divided by four attempts
   per day (decision; a headless turn is a request). `TIMEOUT_S=900` →
   `timeout(1)`: decision, the one wall-clock figure this repo has with
   provenance (plan §2); revisited by a dedicated commit if the measured
   duration contradicts it. `TOKEN_BUDGET=4000000` total tokens across
   the session: decision, a cost ceiling of about $3 per run at the
   introductory price ($0.75/M in, $3.75/M out, verified) for a
   realistic 95/5 input/output split, because cumulative input re-sends
   the context every turn; the free tier makes it moot, a paid key does
   not. Enforcement: an `AfterModel` hook accumulates
   `llm_response.usageMetadata.totalTokenCount` into `$CREW_OUT/tokens`,
   a `BeforeModel` hook denies once the sum exceeds the budget (exit 2,
   reason "TOKEN_BUDGET exceeded"), the adapter maps that to "over
   TOKEN_BUDGET", no PR. **Verify at L1**: that hooks see
   `usageMetadata`. If they do not, the budget is checked after the run
   on the `result` event's `stats` — the PR is still refused, the money
   is spent — and `role.env`, README and this ADR's status line say so;
   `MAX_TURNS` and `TIMEOUT_S` remain the pre-emptive limits either way.
   The recorded `run.json` (turns, tokens, duration) goes into `role.env`
   as a provenance comment; the numbers change only when a measurement
   contradicts them.
9. **Hooks: one `BeforeTool` script, `adapters/gemini-cli/hooks/guard.sh`,
   matcher `run_shell_command|write_file|replace|read_file`, exit 2 with
   the reason on stderr (verified block convention), CLI default timeout
   (no number of ours).** Vendor format, so it lives in the adapter, not
   in `roles/`. It joins every string in `tool_input` (`jq '.. | strings'`,
   independent of parameter names) and denies on any match: `git push`,
   `git reset --hard`, `git clean -f`, `rm -rf` on `/`, `~`, `..`, a glob
   or a variable, `--no-preserve-root`, `sudo`, `chmod -R 777`, `docker`,
   `podman`, `docker-compose`, `curl`, `wget`, `ssh`, `scp`, `nc`; `.env`,
   `.pem`, `id_rsa`, `id_ed25519`, `.git-credentials`, `.gemini/`,
   `/run/secrets`, `GEMINI_API_KEY`, `printenv`, a bare `env` command,
   `os.environ`, `process.env`. Every call, allowed or denied, appends
   one line to `$CREW_OUT/hooks.log`, which is recorded with the fixture
   and is the evidence hooks fired in the real run. `ci/hooks.sh` joins
   `CI_CHECKS`: feeds stdin JSON cases written from this list (both
   verdicts) to the script in workbench, no Gemini needed. No user-level
   policy TOML: two denylists drift, the TOML is untestable outside the
   CLI, and the plan says hooks; the policy engine is the fallback if L1
   shows `BeforeTool` is not honoured under `-p --approval-mode yolo`.
   Hooks are a policy on tool calls, not a sandbox: the container with no
   socket, no credential and no write path outside `/crew` is the
   boundary, and `GEMINI_API_KEY` is inside it because the CLI needs it.
10. **The worker can run the app's tests: option (b).** The crew container
   is workbench, so `cd app/backend && uv sync --locked && python -m
   pytest tests -q -p no:cacheprovider` works against the plane's
   `postgres` at `meetups_test` — the same database `./go test` uses,
   because `conftest.py` hardcodes `CREATE DATABASE meetups_test` and
   `demo-crew` is sequential (worker first, gates after); per-worker
   databases are M6's, the lever HANDOFF already names for mutation
   parallelism. `prompt.md` gives that command and says `./go` and
   `make` do nothing here. Cost: `uv sync` once per cold cache (~30
   wheels, seconds after, cache on the bind mount), two to three turns
   per test run, and a `.venv`-free workspace by `UV_PROJECT_ENVIRONMENT`
   plus `-p no:cacheprovider`. Reason: the mutation gate demands a test
   that observes the new lines, and a worker that cannot run its test
   spends a whole attempt (60 requests) to learn what three turns would
   have told it.
11. **`.env` clobbering fixed with `-p lo-mutation` on both compose
   invocations** in `gates/mutation.sh` and `mutation-baseline`, the
   `printf > .env` lines removed. `COMPOSE_PROJECT_NAME` via the flag is
   explicit and leaves the user's `.env` (where L1's key lives) alone; a
   worktree never had one, which is why M4 did not see it.
12. **Not built at M5**: dispatcher, state machine, `EventBus`, `StateStore`,
   `Orchestrator` (M6); a review-agent run, merge, image build into Zot,
   promotion; `github` CodeHost, `antigravity-sdk` and `adk` harnesses;
   Gitea Actions gates and the runner socket (M6); per-role tool
   allowlists and harness overrides; retries (one `assign` = one attempt).

## Alternatives rejected

- Crew image on `node:24-slim` + `npm ci` (+ apt python or a second uv
  pin): a second base to pin, and the python question (§10) reopens;
  workbench is already local and already has everything but gemini-cli.
- `npm install -g @google/gemini-cli@0.59.0`: no lockfile, floating
  transitive tree; the frontend already established `npm ci`.
- Adding the gemini-cli lockfile to `gates/deps.sh`: ~700 packages of
  platform toolchain would turn every app PR red on an unrelated advisory;
  workbench's binaries are not scanned either — same class, declared.
- The model writes `pr.json` into `OUT` via `--include-directories`: not
  every harness has that; the final message is universal.
- Model commits, adapter only reads `git log`: a model that forgets to
  commit fails an expensive run on a formality.
- `core/crew.sh` reads `tickets/<id>.md` directly: five lines cheaper, and
  `core/` learns a directory layout that `github-issues` does not have.
- Bootstrap in `up`: a push and a Gitea job on every `./go demo` for a
  result nobody reads before M6.
- Actions left on: `actions/checkout` needs gitea.com from the runner,
  and an unconsulted job is the "seems to work" the rules forbid.
- Replacing `honest-fix` with the recorded PR (ADR 0015 §6 alternative):
  the gates' positive control must not move when a model run is re-recorded.
- `roles/<role>/GEMINI.md` and `roles/_hooks/`: subdirectory discovery
  loads them all; hooks are Gemini's JSON dialect, an adapter concern.
- Real prompts for `test-reviewer` and `architect` now: unexercised
  content, rewritten by M6 against a run.
- `HARNESS=` per role: a precedence rule between profile and role for a
  second harness that does not exist yet.
- Policy TOML in the image as defense-in-depth: two lists, one untestable.
- Token budget as a post-run check only: not a budget, a report; tried as
  the fallback, never as the design.
- Named volume for the uv cache: ADR 0012's "no plane state outliving
  `down`" applies to caches too when one bind mount already exists.
- `meetups_crew` database: `conftest.py` creates `meetups_test` by name
  regardless; a stray database to avoid a collision that sequencing avoids.
- Fetching the PR by `refs/pull/N/head`: Gitea/GitHub-specific ref
  namespace in the Makefile; the branch name is the core concept.
- Building the crew image at L0 in `demo-crew` or CI: minutes of npm for
  an image L0 cannot use; found by the next L1 run instead (consequence).
- `COMPOSE_PROJECT_NAME` written to a per-worktree file other than `.env`:
  still a file; the flag is one token.

## Consequences

- The worker clones this repository: the app lives inside the platform,
  so the model can edit `gates/`, `roles/`, `Makefile`. The hook does not
  stop that; `RISK_HIGH_PLATFORM` routes it to review, which is the design
  (ADR 0016 §2). A PR is never merged at M5 anyway.
- The crew image rebuilds whenever the workbench Containerfile changes and
  adds gemini-cli's `node_modules` (size measured at record, in HANDOFF)
  to a 1 GB base. Under docker, `user:` and `HOME` are the price of a
  writable bind mount; a third engine-specific line in `./go` is still
  not needed (ADR 0004's ceiling holds: this is one `id -u` in the Makefile).
- The recorded transcript carries every file the model read; it is a
  talk artefact and a repo-size cost that grows per recorded ticket.
  Size recorded at M5 close; the lever if it hurts is stripping
  `tool_result` payloads, not dropping the transcript.
- The first real run is unknown: the model may choose 502 over 201, write
  a test the mutation gate rejects, or exhaust 60 turns. Four attempts fit
  a free-tier day; the attempt count is published. If no attempt passes
  the gates, M5 does not close and the ADR is wrong about something
  measurable.
- Free-tier per-minute limits may throttle a 60-turn run; the CLI's
  retry/backoff is what stands between that and exit 1 (verify at L1).
- `GEMINI_API_KEY` is in the model's process environment; the hook denies
  the obvious reads and the post-run grep catches a leak into the
  artefacts, but a determined prompt injection with shell access can read
  its own environment. The README says the key is inside the worker
  container and nothing else is.
- `assign` force-pushes local `HEAD` to Gitea's `main` and `ticket/<id>`;
  any hand-made state in the L0 Gitea is overwritten by design.
- `.crew/` on podman machine is virtiofs: the uv cache is slower there
  than in the container filesystem; measured at record.
- Gitea's `ci` job is now explicitly off on the bootstrapped repo; the M2
  runner registration remains the only thing the runner has ever done.
  M6 turns the repo's Actions on, mounts the socket under ADR 0015 §7's
  three conditions, and writes the trusted-network sentence.
- `medium`/`high` still route to "review" with nobody to review; M6.
- One more `ci` check (`hooks`), milliseconds.

## Golden-rule check

Stranger with podman, git, sh, no key, no account: `./go demo` is
byte-for-byte the M4 stage list, no new pull, no new stage — confirmed:
`GO: demo, milestone M3, 113s to rollback` after M5's own changes, same
as before them. `./go demo-crew` at L0 pulls nothing new either:
bootstrap is three API calls and a push to the local Gitea, replay is
`cp` and `git am`, the PR is one API call, then one `gates` run on the
honest path — measured, warm, 97s end to end (mutation is the
honest-fix-sized path ADR 0015's 90–110s estimate already covers). One
transient failure observed mid-session, immediately after a fresh
`./go demo` teardown/rebuild cycle (`open-pr on gitea failed`, ~11s,
before any real work started); an immediate retry passed cleanly, most
likely Gitea's API not fully warm yet right after bootstrap on a cold
plane — noted for M6, not chased further, since no other run in the
same session (six real L1 attempts, three L0 mechanics runs) hit it.
The gemini-cli image is built only by an L1 run: confirmed, `demo-crew`
at L0 never builds it. Passes. The L1 record time (six real attempts,
detailed in HANDOFF, not a ceiling this ADR sets) is measured and
recorded there.

## Contradicts the plan, found at the first L1 run — flagged, not silently
## routed around (CLAUDE.md: "verifica prima di scrivere... se un'API
## non esiste più come descritta, fermati e segnalalo")

Plan §5 commits to `gemini-3.8-flash` for every role. `models/gemini-3.8-
flash` is real and reachable with this key (confirmed directly against
`GET https://generativelanguage.googleapis.com/v1beta/models`), but
**Gemini CLI v0.59.0 silently serves `gemini-3.5-flash` regardless**: `-m
gemini-3.8-flash`, `-m models/gemini-3.8-flash`, and the settings.json
`model.name` all produce a `result` event whose `stats.models` key is
`gemini-3.5-flash`, with no warning on stderr or anywhere else. Read
against the installed bundle's model-resolution code, not guessed twice:
0.59.0 (published 2026-09-08) most likely predates this CLI's own
support for the model ID, one week before `gemini-3.8-flash`'s GA date
this plan cites, and falls back to its own default rather than erroring
on an ID it does not recognize. This is the runtime model substitution,
not a construction-time one (docs/PLAN.md §5's "Con cosa lo costruisci
tu" distinction): it changes what every role actually runs on, at every
level, until the CLI pin moves. Not fixed here: a version bump is its
own dedicated commit under CLAUDE.md's pinning rule, and the newest
tag at record time was a nightly (`v0.61.0-nightly.20260915`), not a
stable release worth pinning to under that same rule. `gemini-3.5-flash`
is a real, capable model, not a mock — M5 records against what actually
runs, states plainly that it is not what the plan asked for, and leaves
the pin decision to the owner. `roles/dev-worker/role.env`'s `THINKING`
values and this ADR's §8 budgets are unaffected: thinking level and
token accounting are orthogonal to which Flash generation answers.

*Correction, 2026-09-16 (ADR 0018):* the last sentence was wrong. Under
0.59.0 the remap to `gemini-3.5-flash` happened in `resolveModel` before
the model-config alias lookup, so the alias §3 keys on `gemini-3.8-flash`
— the only place `THINKING` is applied — was never consulted: **the
per-role thinking level was never applied at M5**, and the recorded
fixture ran on the CLI's default thinking for 3.5 Flash, not on
`THINKING=high`. Read from the two code paths, not measured (the
transcript does not record the thinking config sent). The alias was also
abstract (no `model`), which the fixed CLI refuses; ADR 0018 §1 gives it
the documented shape. The first run with the lever known to be wired is
ADR 0018's eval run, and §8's budgets, measured without it, are
re-measured there.

## Verify at L1 — closed (the build closes each before the milestone closes)

Every item below is now closed, by six real L1 runs (attempts 1–6,
2026-09-15) against ticket 0001. Attempt 6 is the one recorded as the
fixture; attempts 1–5 each found one real, distinct bug, fixed before the
next attempt, detailed in HANDOFF, not repeated here.

1. **Confirmed live.** `AfterModel`'s input carries
   `llm_response.usageMetadata.totalTokenCount` exactly, matching the
   static reading below; §8's design (accumulate-and-deny) is the live
   path, not the post-run fallback — attempt 4's `tokens` file
   (4,040,294) and attempt 5's (4,193,082) both crossed the budget and
   `budget-before.sh` correctly denied the next model call each time,
   surfaced by the CLI itself as `"Agent execution blocked: TOKEN_BUDGET
   exceeded: <n> >= <budget>"`.
2. **Confirmed live, after a real bug.** `BeforeTool` hooks fire under
   `gemini -p --approval-mode yolo --skip-trust`; `hooks.log` is real
   evidence in the recorded fixture. But the first two real attempts
   (2, 3) showed every single tool call denied, always for the same
   reason (`.gemini/`): `createBaseInput()` puts a `transcript_path` on
   every hook call, pointing into the CLI's own `~/.gemini/tmp/...`
   recording file, and `guard.sh`'s original `[.. | strings]` joined
   that in with `tool_input`, so the rule matched unconditionally.
   Fixed by scoping the join to `.tool_input` (commit `46ee945`); attempt
   4 onward shows real ALLOW/DENY discrimination in `hooks.log`.
3. **Corrected twice against real transcripts, not guessed a third
   time.** The static correction (no `response` field on `result`; flat
   `stats`) held. What static reading could not show: the model narrates
   continuously between tool calls — a `message` burst before nearly
   every `tool_use` — so joining every assistant message across the
   session (the first live version) produced a soup of "I will… I
   have…" planning narration as the "PR title," not a real one (attempt
   4). Fixed by taking only assistant message content strictly *after*
   the last `tool_use`/`tool_result` event (commit `9c54d90`); attempt 6's
   `pr.json` is a clean, real title and body. Turn count is still not
   reported anywhere in the stream; the `role:"user"`-count proxy reports
   `1` for every headless run (there is exactly one user message per
   session) and is acknowledged in run.sh's comment as not useful, not
   removed, since `MAX_TURNS` itself is still enforced correctly
   server-side regardless of what this repo can observe about it.
4. Not reached — no run needed a workspace-level settings override, so
   this stays open, harmless: `roles/dev-worker/prompt.md` is the only
   per-role content this repo writes, and it goes through `GEMINI.md`,
   not `.gemini/settings.json`.
5. **Answered by a design that did not depend on it.** Never directly
   tested (`prompt.md` is copied to the global `~/.gemini/GEMINI.md`
   explicitly, sidestepping subdirectory discovery entirely, so the
   question is moot for M5 as built).
6. **Confirmed live**, first on the L0 mechanics run (a temporary fixture
   built from `gates/fixtures/honest-fix`, never committed), then on
   every real attempt after: `docker-compose exec -T gitea gitea admin
   user create` works in the rootless image and is idempotent on
   "already exists"; `PATCH /repos/{o}/{r}` accepts `has_actions`. One
   real bug found and fixed in the same mechanics run: `bootstrap.sh`'s
   repo-create `curl -fsS` discarded the body and the HTTP code together
   on the expected, idempotent 409, misread as a hard failure — `-f`
   dropped, the code read from `-w` and branched on directly (commit
   `8c042c1`).
7. **Confirmed clean**, `./go ci-secrets` green with attempt 6's real
   `transcript.jsonl` (38,926 bytes) committed under `fixtures/`.
8. **Not hit, six real calls in under two hours on the same key**: no
   429, no visible throttling, no retry/backoff behaviour observed to
   describe. Left open as a fact this session's six attempts were too
   few to exercise, not as a design gap.
9. **Confirmed.** Crew image: 5 npm packages, ~35s warm / ~3 min cold, 0
   vulnerabilities. `uv sync --locked` inside the crew container: a few
   seconds warm (the bind-mounted `/crew/.uv-cache` persisted across all
   six attempts in the same session).
10. **Found live, not anticipated by any item above — the reason the
    first four real attempts produced nothing usable.** `-m
    gemini-3.8-flash` (and `models/gemini-3.8-flash`, and settings.json's
    `model.name`) silently serve `gemini-3.5-flash` under Gemini CLI
    v0.59.0. Detailed in the "Contradicts the plan" section above.
11. **Found live.** The model can run out of budget mid-task, after real,
    correct, on-topic work, with no trailing message to build a PR from
    (attempt 5: 29 correct tool calls across all five files the ticket
    needed, then denied on the next call, nothing to extract). `run.sh`
    originally exited on the missing response *before* committing, so
    that real work was briefly, silently discarded — caught by
    inspecting the still-dirty workspace directly, fixed by committing
    first, always, with a WIP placeholder message amended to the real
    one if a response does arrive (commit `2f26996`).
