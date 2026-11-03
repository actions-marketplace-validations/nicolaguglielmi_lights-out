# Handoff: M18 "the model is a choice", 2026-11-03, branch `claude/bold-bouman-b4b874`, not pushed, not merged

The owner reviews. Plan: `docs/PLAN.md` §16 M18 (status note added); decision: `docs/adr/0040-the-model-is-a-choice.md` (0039 was taken the same day by the Gitea-runner ADR; §16's numbers after it shift by one).

## Acceptance, run for real

All runs from a full clone of the branch at `<worktree>/.crew/m18-run` (a worktree cannot drive git through the workbench, M13's finding 1), `.env` holding only `APP_PORT=9000`, no key of any provider, warm images, other sessions sharing the host.

```
./go ci          → GO: ci, 25 checks in 73 s, ci/model-free.sh among them (GO: model-free);
                   evals ran the 23 ADK unit tests (replay, model, offline LiteLLM transformation) in the workbench
./go demo        → GO: demo, milestone M9, 359s to rollback (budget 900s, plan §2)
./go demo-triage → GO: demo-triage, three alerts replayed at L0; each incident.json's run says
                   provider null, model null, source fixtures/adk, recorded {provider gemini, model gemini-3.8-flash}
```

By hand: `sh ci/model-free.sh` → `GO: model-free`; with a planted `# gemini-3.8-flash` under `roles/` → `NO-GO: model-free — core/, gates/, verify/ or roles/ names a model or a key`, the hit on stderr. `adapters/gemini-cli/run.sh` refuses, before any container, `MODEL_PROVIDER=anthropic` (names the M19 harnesses), an empty `MODEL`, a placeholder `GEMINI_API_KEY`, and a `THINKING` outside its `thinking.env`. Offline, with litellm 1.106.6: `reasoning_effort` low/medium/high reaches Claude as `thinking {type: adaptive}` + `output_config.effort <same>` and OpenAI as `reasoning_effort <same>`; the map is 1:1 (`adapters/adk/lights_out_adk/tests/test_model.py`).

Measured: workbench image 1.56 GB → 1.75 GB with litellm (+190 MB); a from-scratch `uv sync` of the new lock took 6 s on this line.

## What changed

- `MODEL_PROVIDER` (gemini|anthropic|openai) and `MODEL` in `profiles/l1..l3.env` (gemini, gemini-3.8-flash), empty in `l0.env`, overridable in `.env`; `.env.example` gains `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and commented pairs (`claude-sonnet-5-5`, `gpt-6.1-sol`); gitleaks allowlists the three key lines in `.env`.
- Thinking maps `adapters/adk/thinking.env` and `adapters/gemini-cli/thinking.env`, one line per provider and level with its source; roles keep `THINKING` and budgets only.
- `adapters/adk/lights_out_adk/model.py`: Gemini through ADK's `Gemini` plus the planner; Claude and OpenAI through `LiteLlm(model="<provider>/<id>", reasoning_effort=…, api_key=…)` with no planner (LiteLlm ignores `thinking_config`), imported only on that branch so L0 never loads litellm; `RecordingLlm`/`ReplayLlm` unchanged in shape, recordings gain `provider`; `run.json` of both harnesses carries `provider` and the served `model` (null at L0, the fixture's under `recorded`).
- `adapters/gemini-cli`: `-m "$MODEL"` and the alias keyed on it, Gemini only until M19.
- `ci/model-free.sh` in `CI_CHECKS`; `record-evals` scans each set provider key; `litellm==1.106.6` pinned in `workbench/pyproject.toml` and `uv.lock`, `LITELLM_LOCAL_MODEL_COST_MAP=True` set by the adk adapter so litellm fetches nothing at import.
- README, `docs/reference.md`, `docs/ARCHITECTURE.md`, `docs/PLAN.md` §16 updated.

## Found (contradicts the plan or the brief)

1. Plan §16 numbers M18 as ADR 0039; 0039 went to the Gitea-runner ADR the same day. M18 is 0040 and M19–M23 shift to 0041–0045 (PLAN.md headings renumbered).
2. The done-when command `./go record-evals PROFILE=l1 MODEL_PROVIDER=anthropic` cannot work alone: the profile's `MODEL=gemini-3.8-flash` would still apply. The ADR rejects a default id per provider, so the command names both: `MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5` (PLAN.md amended).
3. ADK 2.9.1's `LiteLlm` does not read the planner's `thinking_config`: a planner beside it is a lever that looks wired and is not (ADR 0018's bug shape). The level travels as `reasoning_effort`; the test asserts no planner on those providers.
4. `record-evals` grepped the fixtures for `$GEMINI_API_KEY`; with that key empty (an Anthropic-only `.env`) the grep matches every file and would have deleted a valid recording. Fixed in the Makefile.
5. Subagents started from this session get an isolated worktree cut from the committed HEAD: the gate-writer could not act on uncommitted work and the gate and tests were written here from the ADR; the architect and doc-scribe wrote by absolute path and were fine.

## Not done, and open decisions for the owner

- **The one item left to you:** no non-Gemini recording exists. `./go record-evals PROFILE=l1 MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5` and the same with `MODEL_PROVIDER=openai MODEL=gpt-6.1-sol` are implemented and documented, not run: they spend your keys. After a run, `fixtures/adk/<role>/*.json` carry `"provider": "anthropic"`, and `./go demo-triage` at L0 shows it under `recorded`. The plan's done-when stays open on that point until then.
- At L1 with `anthropic|openai` the three ADK roles run but the crew step refuses (gemini-cli is Gemini only), so `./go e2e PROFILE=l1` stops at dev-worker until M19.
- `MAX_TURNS` and `TOKEN_BUDGET` in `roles/` are Gemini measurements; other tokenizers count differently. They bind only gemini-cli for now; re-measure per provider in M19.
- `docs/reference.md` still says "Only L0 exists today. Levels L1–L3 describe the plan." under the levels table, which predates L1; not touched here.

## First thing M19 should look at

`adapters/gemini-cli/run.sh`'s provider refusal and `docs/adr/0040` §4: the `claude-code` and `codex` harnesses take `MODEL_PROVIDER`, `MODEL` and the provider's key from the same profile, map `THINKING` in their own `thinking.env`, and write `provider` and the served `model` into `run.json` like the two harnesses do now; the conformance suite should assert exactly that.
