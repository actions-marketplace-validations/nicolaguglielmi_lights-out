# ADR 0020 — ADK agents and go-for-launch at M7: the three conversational roles run on `adapters/adk/` behind the AgentHarness verb with a second, declared artefact contract (tool calls + final text, no workspace) and a `HARNESS=adk` line in their `role.env`; at L0 the model is a `BaseLlm` that replays `LlmResponse`s recorded once at L1, keyed by the first user message, and every decision the eval must see is a tool call so `adk eval` judges trajectories with no LLM judge; `core/launchpad.sh` writes a release record and `core/promote.sh` is go-for-launch — a brief from the release role, one human answer, weight 100 or rollback; `demo-launch` proves it mechanically and does not join `./go demo`; the ADK is pinned into the workbench image by `uv.lock`; `ci/prompts.sh` enforces ticket 0004 and `dev-worker/prompt.md` is rewritten under it now; the review roles, ticket 0003 and the two budget `record`s re-date to M8

- Status: accepted (amends ADR 0003 [the `100%` stub is removed; `demo-launch` is not a stage]; ADR 0013 §4 and ADR 0014 §1 [launchpad writes `RELEASE_RECORD`; the held line names `./go promote`]; ADR 0017 §1 [a second artefact contract on the same verb], §7 [the per-role `HARNESS` override now exists; `product`, `release`, `ops-triage` get `prompt.md`; `architect`, `test-reviewer` ROLE.md say M8]; ADR 0019 §8 [review roles, ticket 0003 and the budget records move to M8]; ADR 0004 [the workbench image carries a Python venv and its tag covers `uv.lock`]; amended by ADR 0021 [§9's "not built at M9" list, now built at M9: review roles with prompts, review step in the tower, perimeter rule for tickets])
- Date: 2026-09-16
- Milestone: M7

## Context

M7 (plan §7): product, ops-triage and release agents on ADK; an `adk eval`
suite with the ambiguous question and the misleading alert; done when
`adk eval` passes in CI and a fake alert yields an incident with ordered
hypotheses and a rollback proposal, without the agent touching the
environment. Inherited from ADR 0019 §8: `go-for-launch` (the stub
`[launchpad] 100%: NOT YET (M7, go-for-launch)`; ADR 0003's rule binds) and
ticket 0004's `ci/prompts.sh`. Owner decisions 2026-09-16, not re-opened
here: this scope; at L0 the ADK agents run on a replay model, recorded once
at L1 — "the tools and the eval run for real, the model does not"; the
review roles, ticket 0003 and the two dev-worker `record`s move to M8.
Verified facts (official sources, 2026-09-16, cited by the parent session):
google-adk 2.9.1 on PyPI, Python ≥ 3.10, `adk eval <AGENT_DIR> <evalset>
[--config_file_path]` with `tool_trajectory_avg_score` (exact tool match, no
model) and `response_match_score` (ROUGE-1, no model) as the only judge-free
criteria; 2.9.0 added `ignore_args`; **the `adk eval` CLI does not exit
non-zero when cases fail** — it prints `Tests passed: N / Tests failed: M`;
`BaseLlm.generate_content_async(llm_request, stream)` yields `LlmResponse`
(pydantic); `LlmAgent.model: str | BaseLlm`, `planner=BuiltInPlanner(
thinking_config=ThinkingConfig(thinking_level=LOW|MEDIUM|HIGH))`. Read
from `adk-python` main by this session: `AgentLoader` imports the agent
directory **by its basename as a module name** and rejects any name not
matching `^[a-zA-Z0-9_]+$`, so `roles/ops-triage/` can never be an `adk
eval` target; the CLI has an interactive telemetry consent prompt backed
by `~/.adk/config.json` (`telemetry: false` opts out). Repo facts: `./go ci`
runs in workbench with no socket (ADR 0002), so whatever `ci` runs must be
in the image; `go` tags the image by `cksum workbench/Containerfile`;
`core/launchpad.sh` holds at 25 % and prints the stub; `verify/slo.sh`'s
`slo:` lines go to stderr and `core/steps/release.sh` greps them from the
log; `adapters/envoy-canary/shift.sh <pct>` sets canary=pct/stable=100-pct
and verifies the runtime value; ADR 0017 §7 deferred a per-role `HARNESS`
"until a second real harness exists". Measured: `./go demo` 360 s warm at
M6; `demo-hold` ≈ 140 s warm (ADR 0014 arithmetic).

## Decision

1. **`adapters/adk/` is the `adk` AgentHarness adapter of plan §4's table,
   with a second artefact contract on the same verb, and the three roles
   name it in `role.env`.** `adapters/adk/run.sh` takes `ROLE`, `INPUT` (a
   file: the alert, the release record, the ticket), `OUT` (empty dir),
   `THINKING`, `TIMEOUT_S`; no `WORKSPACE`, no `BASE`. Success = exit 0 and
   `OUT` holds `calls.json` (the ordered tool calls, `[{name, args}]`),
   `final.md` (the final text) and `run.json` (`{harness:"adk", model,
   thinking, turns, tokens:{input,output,total}, duration_s, exit_code}`,
   plus `source` and `recorded_under` when replayed, §2). **The
   harness-independent invariant (ADR 0017 §1) is: exit 0 with an empty
   `calls.json` is a failure**; the role-specific shape is checked by the
   core driver that asked (§3, §4), the ADK-specific shape (`function_call`
   parts in events) stays inside the adapter. `roles/product/role.env`,
   `roles/ops-triage/role.env`, `roles/release/role.env` gain `HARNESS=adk`:
   core resolves `${HARNESS:-$AGENT_HARNESS}` — a role's harness is a
   property of the role (needs a workspace or a conversation), the
   profile's `AGENT_HARNESS` is a property of the level (what runs the
   coding roles). This is the override ADR 0017 §7 deferred "until a second
   real harness exists"; `core/` never spells `adk`. Layout, forced by the
   loader's name rule: one package `adapters/adk/lights_out_adk/` (role
   loading, model selection, the replay/record models, the runner that
   writes `OUT`), and three agent directories `adapters/adk/agents/{product,
   ops_triage,release}/` each an `__init__.py` + `agent.py` exposing
   `root_agent`; the agent derives its role directory by `_` → `-`. The
   instruction is `roles/<role>/prompt.md` read at import; `THINKING` is
   `roles/<role>/role.env`'s, so the six roles keep one layout (plan §6,
   ADR 0017 §7) and the vendor format (Python agents, evalset JSON) stays
   in the adapter, the ADR 0017 §9 hooks precedent. `PYTHONPATH=adapters/
   adk` is set by `run.sh` and `ci/evals.sh`; the build verifies that `adk
   eval adapters/adk/agents/<role>` puts `adapters/adk/agents` on
   `sys.path` as the loader reads. `ROLE.md` of the three roles is replaced
   by `prompt.md` (a run now exists: the eval); `architect` and
   `test-reviewer` ROLE.md say M8.
2. **The model is derived from `AGENT_HARNESS`, no new profile key;
   `replay` means a `BaseLlm` that replays recorded responses, anything
   else means `gemini-3.8-flash` through `GEMINI_API_KEY`.** Honest because
   plan §3's Models row and `profiles/l0.env`'s own comment define L0 as
   "recorded model responses"; for the crew the recorded response is the
   whole run, for a conversation it is each model turn — both are declared
   in the README. Real model: `Gemini(model="gemini-3.8-flash")` with
   `planner=BuiltInPlanner(thinking_config=ThinkingConfig(thinking_level=
   THINKING))`; an empty or `replace-me` key fails first, loudly (the
   gemini-cli precedent); Vertex is M8's env. **Replay keying**:
   `fixtures/adk/<role>/<sha256 of the first user message text>.json`,
   holding `{input, instruction_sha256, model, recorded_at, responses:
   [LlmResponse.model_dump()…]}`; the call index is the number of
   model-role contents in `llm_request.contents`, so the replay is
   stateless and re-runnable across turns; index beyond the recording, or
   no file, is one stderr line naming the role, the key, the first 80
   characters of the input and `./go record-evals PROFILE=l1`, then exit 1
   — never a fallback. The input document is always the user message
   (§3), canonicalised by `jq -S .` for JSON inputs, so a file and an eval
   case with the same content share one key. A fixture whose
   `instruction_sha256` differs from the current `prompt.md` still replays
   — the dev-worker precedent, §6 — but says so on stderr on every use and
   `run.json.recorded_under.matches_current` is `false`. **Recording**:
   `ADK_RECORD=1` at L1 wraps the real model and writes the same path.
   Makefile `record-evals [ROLE=<role>]`: refuses at L0 ("recording a
   replay is circular", the `record` precedent), runs `ci/evals.sh`'s eval
   with `ADK_RECORD=1`, keeps a role's fixtures only if that role's eval
   passed (otherwise moved to `.crew/adk/<role>/` for study), refuses if
   the key appears in any response (the gemini-cli grep), and HANDOFF
   records the attempt count as ADR 0017 §6 requires. `record` itself is
   untouched: it is crew-run based and records a PR.
3. **Every decision the eval must see is a tool call; the criterion is
   `tool_trajectory_avg_score` at 1.0 with `ignore_args`; tools are pure
   functions of their arguments.** Threshold provenance: ADK's own default
   for this criterion, and the only value that means "the decision was the
   expected one"; `response_match_score` is not configured — a real L1 run
   varies its wording, and the record run must pass the same eval.
   Toolsets, exact: product `ask_product_owner(question)`,
   `confirm_acceptance(criteria)`; ops-triage `file_incident(title,
   hypotheses:[{rank, cause, evidence}])`, `propose_rollback(version,
   reason)`, `propose_hold(reason)`; release `submit_brief(version, brief)`,
   `decline_brief(reason)`. No tool reads a file, a socket or the plane: each
   returns its arguments echoed with `status: recorded`; the runner derives
   the artefacts from the events. That is the mechanical form of "without
   the agent touching the environment", and `ci/evals.sh` asserts each
   `root_agent`'s tool names equal this list (a fourth tool on ops-triage
   is a NO-GO). Cases, written from plan §7 and §8 before any run: product
   — a ticket without acceptance criteria → `ask_product_owner`, the answer
   arrives in turn two → `confirm_acceptance`; a ticket with criteria →
   `confirm_acceptance` in one turn. ops-triage — the real alert (headline
   blames the canary, numbers: canary error_rate 1.0, stable 0.0, canary
   traffic > 0) → `file_incident` then `propose_rollback(version)`; the
   misleading alert (headline blames the canary, numbers: stable fails
   too) → `file_incident` then `propose_hold`; the second misleading alert
   (canary has no traffic, error_rate `no data`) → `propose_hold`. release
   — a held record → `submit_brief`; a rolled-back record → `decline_brief`
   (nothing to promote; core refuses first, §4, the agent's refusal is the
   eval's discriminating case). The alert is a derivative of the release
   record: `{headline, version, stable, stage:{pct, verdict, numbers:[the
   slo: lines]}}`, so M8's tower can emit one from `RELEASE_RECORD`. Alert
   texts live only in the evalsets (`adapters/adk/agents/<role>/evals/
   <name>.evalset.json` + `test_config.json`); `demo-triage` extracts them
   by case id with jq, so the replay key cannot drift from the eval's.
   **Incident artefact** (core's, written by `core/triage.sh` from
   `calls.json`): `.crew/triage/<name>/incident.json` = `{alert, title,
   hypotheses:[{rank,cause,evidence}], proposal:{action: rollback|hold,
   version?, reason}, run}`; the driver NO-GOs on fewer than two ranked
   hypotheses ("ordered" needs two, plan §7's plural), on a proposal
   without `file_incident` before it, or on a rollback whose `version` is
   not the alert's. Makefile `triage ALERT=<file>` runs it on any alert;
   `demo-triage` runs the ops-triage eval cases through `triage` with
   `PLANE_HOST=nowhere.invalid` and asserts each case's `proposal.action`
   against the evalset's expected tool — a triage that touches the plane
   cannot pass, by construction, not by inspection. Neither needs the
   socket; `go`'s list does not gain them. Session state and cross-session
   memory are not used at M7 (plan §5 names them; nothing in the done-when
   needs them). Budgets: `TIMEOUT_S=900` in the three `role.env` (plan §2,
   the one wall-clock figure with provenance, the ADR 0017 §8 precedent),
   ADK's own `max_llm_calls` default as the call ceiling (its provenance is
   the library; the free tier's 250/day is the external cap at L1); no
   `TOKEN_BUDGET` — `run.json` records the first real numbers and a
   dedicated commit sets budgets from them.
4. **`core/launchpad.sh` writes `RELEASE_RECORD`; `core/promote.sh` is
   go-for-launch; the stub is gone.** Launchpad captures `verify/slo.sh`'s
   stderr per stage and writes `RELEASE_RECORD` (default
   `.crew/release.json`): `{version, stable, stages:[{pct, verdict,
   numbers}], verdict: held|rolled-back, held_at, image:"stable image, not
   built from merge.sha (M8)"}` on both outcomes; the stub line becomes
   `[launchpad] 25%: GO — held; ./go promote runs go-for-launch`.
   `core/steps/release.sh`'s grep stays (one change per milestone; the
   duplicate is a consequence). `core/promote.sh`: read the record — none
   → `NO-GO: go-for-launch — no release record; run ./go release`; verdict
   ≠ held → NO-GO naming the verdict and stage; resolve the release role's
   harness (§1), run it with `INPUT=$RELEASE_RECORD`, take `submit_brief`'s
   `brief` as `.crew/promote/brief.md` — a `decline_brief`, a missing call,
   or a brief that does not name the record's version and every stage pct
   is a NO-GO before anything shifts; print the brief on stderr; then the
   answer: `GO_FOR_LAUNCH=GO|NO-GO` if set, else one line read from the
   TTY (`go-for-launch <version> to 100%? [GO/NO-GO]`), else — no env, no
   TTY — NO-GO "no human answer". GO → `adapters/$DELIVERY/shift.sh 100`
   (which verifies the weight took) and `promoted:{weight:100}` appended
   to the record; NO-GO → `rollback.sh`; one stdout line `GO:
   go-for-launch` / `NO-GO: go-for-launch — …`. **At L0 promotion is Envoy
   weight 100 on the canary cluster; the canary does not become the new
   stable image** — the record and the README say so; digest and build are
   M8's. Makefile `promote` (manual; no socket, curl only) and
   `demo-launch`: save and trap `flags.json`, `kill-switch`, `release`
   (held), `promote` with `GO_FOR_LAUNCH=GO`, assert `weights.canary=100`
   and 10/10 `healthz` samples report `CANARY_VERSION` (10: the
   demo-rollback precedent, same number, same reason), then the cleanup
   `rollback.sh` with `weights.canary=0` re-asserted — the un-promote ADR
   0019 asked for — and `GO: demo-launch`. `demo-launch` joins `go`'s
   socket list (its `release` deploys through compose). **Not a `./go demo`
   stage**: plan §2's criterion is the rollback (ADR 0014's reasoning,
   unchanged); the arithmetic fits (360 + ≈150 s warm ≈ 510 of 900) but
   the stage list is a promise (ADR 0003) and a human gate answered by an
   env var proves the mechanism, not the gate. A workflow job runs
   `./go demo-launch` on every push (the `gates` job precedent), so the
   un-promote is exercised without being on the stranger's path.
   `demo-hold` keeps its cleanup rollback (ADR 0014 §3 stands); the manual
   human path is `./go kill-switch`, `./go release`, `./go promote`
   (`GO_FOR_LAUNCH=GO` as a make variable: `./go promote GO_FOR_LAUNCH=GO`;
   `go` forwards no host environment).

   *Note, 2026-09-16, found at the first `demo-launch` at L0:* a live release
   record carries live numbers (traffic, latency), so no recording keyed on
   its text can ever match it — the release role cannot be replayed on a
   real record, by construction, and a replay keyed on anything less than
   the whole record would put recorded numbers in front of the human
   beside a record that says otherwise. So **at L0 (`AGENT_HARNESS=replay`)
   `core/promote.sh` renders the brief from the record itself** — version,
   stable, every stage with its verdict and `slo:` lines verbatim, the
   image line, one recommendation — and labels it "by core/promote.sh from
   the record — no model at L0, the release role writes it from L1". The
   release role's brief is still what `adk eval` judges on the recorded
   held record, and what `./go promote PROFILE=l1` prints (verified live:
   the role recommended NO-GO on the M6 record because the image is not
   built from the merge sha — a correct reading the human then overrides
   or not). `ci/promote.sh` case (h) proves the L0 path: held + GO →
   `shift 100`, the harness never called, the brief names version and
   stages. README declares it beside the replay declaration.
5. **The ADK is in the workbench image, pinned by `workbench/uv.lock`.**
   `workbench/pyproject.toml` (`google-adk==2.9.1` exact, plan §5) +
   `uv.lock`; `uv sync --frozen --no-dev` into `/opt/workbench-venv` on the
   system interpreter (`UV_PYTHON_DOWNLOADS=never`, Debian trixie's
   python3), `PATH` prefixed; `go` tags the image by `cksum` of
   `Containerfile`, `pyproject.toml` and `uv.lock` together. The install
   set for `adk eval` with trajectory-only criteria (whether `google-adk`
   plus `rouge-score`/`pandas`/`tabulate` suffices, or the `eval` extra is
   needed) is **measured at build** in the image, and the image-size and
   cold-build deltas are recorded in this ADR's consequences and HANDOFF —
   not guessed. Telemetry: the opt-out the installed package honours (the
   `~/.adk/config.json` key, or an env var if one exists) is read from the
   package source at build and applied so `adk` never prompts under
   either HOME (`/root` under rootless podman, `/tmp` under docker);
   `ci/evals.sh` proves it by running with stdin closed.
6. **`ci/prompts.sh` enforces ticket 0004; `dev-worker/prompt.md` is
   rewritten under the rule now, its re-record stays with M8's `record`s.**
   Forbidden in any `roles/*/prompt.md`, case-insensitive: the word `gate`
   or `gates` (the pipeline's judge, by name); every `gates/*.sh` basename
   as a whole word, except `test` — the one basename that is also the
   role's own acceptance vocabulary and the word ticket 0004's rule text
   itself uses; `make <t>` and `./go <t>` for every `## `-listed target `t`
   (the `ci/readme.sh` regex and derivation); and the tools the gates run
   — `bandit`, `osv-scanner`, `gitleaks`, `cosmic-ray`, `tests/mutation` —
   a hand list, because "which executable a gate invokes" is not
   mechanically derivable; the script self-checks it by NO-GOing if a listed
   tool is no longer invoked by any `gates/*.sh` or `ci/secrets.sh` (drift
   one way is caught; a new tool not listed is the gate-writer's duty,
   named in the script). NO-GO names file and word. The check fails on
   today's dev-worker prompt (it names bandit, sast, mutation, `./go`,
   `make gates`), so it lands with the rewrite: the L0 fixture is unaffected
   (`replay/run.sh` never reads `prompt.md`; `demo-crew` compares verdicts;
   the fixture carries the prompt it was recorded under), and the run that
   validates the rewritten prompt is one of the two M8 `record`s. The three
   ADK prompts are written under the rule from the start; they name their
   own tools, which are not gate tools. The gate proves itself on a planted
   temp file before scanning `roles/`.
7. **Names.** Makefile: `triage`, `demo-triage`, `promote`, `demo-launch`,
   `record-evals`. `ci/evals.sh` (`CI_CHECKS` gains `evals`; the check is
   about the agents' regression evals, ci names say what is checked, as
   `hooks`, `harness`, `tower` do) and `ci/prompts.sh`. Fixtures:
   `fixtures/adk/<role>/<sha256>.json` — the format is ADK's, the adapter's
   name is honest there. Evals: `adapters/adk/agents/<role>/evals/`. The
   go-for-launch answer is `GO_FOR_LAUNCH`. Plan §1's four names, no fifth.
8. **Tests from the spec, cold, no plane, under the gate contract.**
   `ci/evals.sh`: (a) every `root_agent`'s toolset equals §3; (b) `adk eval`
   per role at the current profile, the summary parsed — `Tests failed: 0`
   for each role or NO-GO naming role and count, details on stderr (the CLI
   exits 0 either way, verified); (c) `python3 -m unittest` over
   `adapters/adk/lights_out_adk/tests/`: the replay model returns recorded
   responses in order, indexes by model-role contents, fails loudly on a
   missing fixture naming the record command, fails on an exhausted
   recording, never constructs the real model at `AGENT_HARNESS=replay`.
   `ci/promote.sh` (the `ci/tower.sh` shape: stub `DELIVERY`, stub harness
   whose `run.sh` writes a `calls.json`): no record → NO-GO, no adapter
   call; rolled-back record → NO-GO, no adapter call; held record +
   `GO_FOR_LAUNCH=GO` → the stub log shows exactly `shift 100`; `NO-GO` →
   exactly `rollback`; a brief that omits the version → NO-GO before any
   shift; no env, no TTY → NO-GO. `ci/prompts.sh` catches a planted
   `mutation` and passes the real prompts. `ci/contract.sh` picks all three
   up by its `find`.
9. **Not built at M7, and where each goes.** The review roles (`architect`,
   `test-reviewer` prompts, the tower's `review` step), ticket 0003's
   perimeter rule and the two `record`s that fix the dev-worker budget: **M8**
   — all three need a medium-risk PR run at L1, which is the same `record`
   work as the budget, and this session's scope is the owner's; plan §7 M7
   and M8 get the dated note, ADR 0019 §8's way. *Owner ruling at close,
   2026-09-16: not inside M8 — a milestone of its own after M8, because
   none of it depends on GCP and in M8 it would sit there by placement
   only; M9 proposed, shifting the platform and design milestones by one.
   gcloud and terraform leave the base image for a `workbench-cloud`
   image inside M8, with an ADR amending 0004 (HANDOFF).* Number accepted
   without change, 2026-09-17: M9 is Review, run before M8 because none of
   its work depends on GCP; the platform milestone (Agent Engine, BigQuery,
   the nightly) is now M10, design is M11; M8 (GCP) remains open. Product on
   the tower's `assign` path, session memory, Agent Engine, BigQuery
   analytics: M10. The canary as the new stable image, Vertex: M8.

## Alternatives rejected

- ADK roles outside the AgentHarness port (a `Conversation` port): not in
  plan §4's table; the table already lists `adk` under AgentHarness.
- `adapters/adk` called by name from `core/triage.sh` and `core/promote.sh`:
  a vendor word in core for the sake of skipping one `role.env` line.
- A profile key for the model (`MODEL=replay|gemini-api|vertex`): a fifth
  value that only restates `AGENT_HARNESS`'s first; if L2's Vertex needs a
  key, M8 adds it with a reason.
- `roles/<role>/agent.py` per role: the loader refuses hyphenated names and
  imports by module name; renaming `ops-triage` to `ops_triage` would break
  the six-role layout for one tool's rule.
- The record in session state with `read_release_record()`: every release
  would share one user message and one replay key; the input in the user
  message is the dumb thing and it works.
- The brief as final text with an empty expected trajectory: a vacuous
  eval; `submit_brief`/`decline_brief` give it one discriminating case.
- `response_match_score` on the brief: the record run must pass the same
  eval, and a real model's wording varies.
- Fixtures keyed by eval case id: the model never sees the id; the input
  hash is what the request carries.
- A NO-GO on a prompt/fixture hash mismatch: it would forbid every prompt
  edit at L0, which this very ADR does for dev-worker; warn and record.
- `demo-launch` in `./go demo`: §4; ADR 0014's reasoning is unchanged.
- `demo-hold` without its cleanup so `promote` can follow it: ADR 0014 §3.
- A `rollback` target as the human un-promote: `down`, a restarted Envoy and
  the next launchpad run already undo a weight (ADR 0014 consequences).
- `healthz` sampling inside `core/promote.sh`: needs a server in the cold
  test; `shift.sh` already verifies the weight, the demo samples (ADR 0014
  §4 f precedent).
- A compose service for the ADK: `ci` has no socket. A venv built at `ci`
  time: network and no cache on every run. `pip install` in the
  Containerfile: no lockfile; `uv.lock` is the pin (the frontend and
  gemini-cli precedent).
- `AgentEvaluator.evaluate` under pytest instead of parsing the CLI: a
  second test runner in the image for one string; the parse is documented
  and re-verified at build.
- Gate basenames matched only as `gates/<name>` paths: "mutation testing"
  in prose is exactly what ticket 0004 forbids.
- Deferring the dev-worker rewrite to M8 with the check: the check would
  then land against a prompt it fails, or not land; the rewrite costs
  nothing at L0 and the measurement is M8's either way.
- `record ROLE=ops-triage`: `record` runs `crew-run`, which assigns a ticket.

## Consequences

- **The replay can drift from the prompt silently enough**: a fixture
  recorded under an older `prompt.md` still passes the eval at L0. The
  stderr line and `recorded_under` are the only guard; the same is now true
  of the dev-worker fixture until M8's record. This is the one that hurts.
- The review roles are re-dated a second time (M6 → M7 → M8); ADR 0003's
  rule binds M8, and `review` stays a terminal state.
- The workbench image grows by **+300 MB** (1.13 → 1.43 GB on arm64,
  measured 2026-09-16): `google-adk==2.9.1` plus `google-cloud-aiplatform`,
  which the eval CLI imports unconditionally (`evaluation/
  vertex_ai_eval_facade.py` → `vertexai`) even with no LLM-judge criterion
  configured — 296 MB installed against 658 MB for the full `[eval]` extra
  (scikit-learn, gepa), which nothing here uses; `rouge-score`, `pandas`,
  `tabulate` complete the set. The venv layer builds in ≈ 25 s warm
  (`uv sync --frozen --no-cache`); any `uv.lock` bump rebuilds it. `ci`
  gains ≈ 30 s (39 s total warm at M7 close, 16 checks); `./go demo` from
  a stopped plane measured 306 s warm against 360 s at M6 (the plane was
  warm-cached; not a speed-up, noise).
- `adk eval` writes `.adk/eval_history/` under the agent directory on every
  run; gitignored, but `ci/secrets.sh` scans the working tree and flags the
  request ids in it (verified). `ci/evals.sh` removes it after each run;
  the CLI's summary in the gate's log is the record kept.
- The numbers exist twice: `RELEASE_RECORD` and the tower document's
  `release.numbers`; M8 folds the step onto the record.
- `demo-launch`'s human is `GO_FOR_LAUNCH=GO`: a proof of the mechanism.
- `ADK_RECORD=1` and `record-evals` spend real calls; one eval run per role
  is a handful of requests, inside the free tier.
- The dev-worker fixture in the tree was recorded under a prompt the tree
  no longer has; the original is one `git log -- roles/dev-worker/prompt.md`
  away (the fixture's own `prompt.md` is the ticket text the CLI was
  given, not the role prompt).
- `record-evals` attempts at M7 close: ops-triage 1/1, release 1/1, product
  3 — attempt 1 asked a question on the complete ticket (status codes), the
  prompt gained "ready does not mean exhaustive" and passed; attempt 3 was a
  re-record after `ci/prompts.sh` rejected the word "make" in that new
  paragraph, so the fixture's `instruction_sha256` matches the prompt in
  the tree. One eval pass per role costs 2–5 requests.
- ADK's loader reads a `.env` up the agent's parents: at L1 that is where the
  key comes from; at L0 nothing constructs a model. Verified at build.
- Three more `ci` checks (`evals`, `promote`, `prompts`), one socketed
  target (`demo-launch`), a workflow job, `PYTHONPATH` in two scripts.

## Golden-rule check

Stranger with podman, git, sh; no key, no account. `./go demo` gains no
stage and no network call: 360 s warm at M6 plus the workbench build delta
(measured at close). `ci` gains three checks that run in the image on
committed fixtures with no plane — a missing fixture is a NO-GO that names
the L1 command, never a silent skip. `demo-triage` and `promote` need no
socket; `demo-launch` is optional, ≈150 s warm by ADR 0014's arithmetic,
off the timed path. The ADK is pulled at image build, pinned, and the
README says which part answers from a recording. Passes; the clean-container
figure is recorded at M7 close.
