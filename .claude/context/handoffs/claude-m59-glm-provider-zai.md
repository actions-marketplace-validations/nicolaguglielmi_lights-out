# Handoff — M59, GLM by Z.ai and a budget per provider (ADR 0092)

Branch to land: **`claude/m59-glm-provider-zai`** (head below), on b4b1590
(= origin/main when the session started). Not merged; the coordinator lands it.

`claude/m59-glm-provider-c48c75` on origin is the same work with one commit
whose `ci/harness-shape.sh` self-check fixture tripped gitleaks'
`generic-api-key` rule (`api.zother.example:8443`): self, stranger and ci went
red on it, in history, so no later commit can fix it. A force-push was refused
here, so the corrected history went to the new name. **Do not land
`-c48c75`; the owner may delete it.**

## Acceptance

- `./go ci` from a full clone under `.crew/m59/full`, on 3d37429 (the head
  before this handoff): **GO**, 53 checks, 6 min 40 s. Also GO on 563b2a6
  (21 min, host shared with other sessions).
- GitHub Actions on 3d37429, all five push workflows **green**: ci
  43846506458 (`GO: harness-conformance — antigravity-cli (gemini),
  claude-code (anthropic), claude-code (zai), codex (openai), gemini-cli
  (gemini), against a scripted model, 398 s`; engine-compat `GO: demo,
  milestone M9, 889s to rollback (budget 900s)`), stranger 43846506468 (`GO:
  demo … 665s`), podman 43846506431 (`GO: harness-conformance — claude-code
  (anthropic), claude-code (zai) … 141 s`), package 43846506477, self
  43846506528. `site` did not trigger (no console change on this branch); it
  ran green on the first push (43836282852).
- engine-compat's demo took 889 s of the 900 s budget on this run (stranger:
  665 s, the previous push: 786 s). Runner variance as far as I can tell;
  nothing here touches the demo's path, but it is close.
- `./go demo` locally: not run. The one plane slot was held by M60's checkout
  (`.crew/m60/before`, rootful podman) the whole session; it was left alone.
  The demo is proven by the push workflows above (stranger, ci engine-compat).

## What changed, in five lines

1. `MODEL_PROVIDER=zai` (`ZAI_API_KEY`, `glm-5.3`): claude-code through
   `https://api.z.ai/api/anthropic` (`adapters/claude-code/conformance.zai.env`,
   the key as `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY` emptied), the ADK roles
   through LiteLLM with the effort in `extra_body`; codex, gemini-cli and
   antigravity-cli refuse zai naming claude-code.
2. A harness may run several providers: one `conformance.<provider>.env` each;
   the suite runs every file, `ci/harness-shape.sh` checks them, doctor reads them.
3. `TOKEN_BUDGET_<PROVIDER>` in `role.env`, read by `core/spend.py token-budget`
   for crew and review, and by the logbook (run in flight, role matrix, 80%
   warning). Dev-worker on Gemini: 3,900,000 (M24: 60 turns × 63,415 a call).
4. `profiles/prices.json` gains `cached_input` on every row and the GLM row;
   `tokens.cached` from gemini-cli, claude-code and ADK; the ledger prices it
   and writes `cost_basis`. M24's ten Gemini runs: $3.550083 (was $20.847788).
5. ADR 0092, amendments noted in 0040, 0041, 0083, 0087; docs, PLAN (Italian).

## Sources (each read 2026-11-16)

- Z.ai OpenAI-compatible API: https://docs.z.ai/guides/overview/quick-start,
  https://docs.z.ai/api-reference/llm/chat-completion (`reasoning_effort`
  low|high|max on GLM-5.3, `prompt_tokens_details.cached_tokens`).
- Z.ai with Claude Code: https://docs.z.ai/scenario-example/develop-tools/claude
  (`ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic`, `ANTHROPIC_AUTH_TOKEN`).
- Key types: https://docs.z.ai/devpack/notice/api-key-management (Standard vs
  Coding Plan keys, separate since 2026-10-16); https://docs.z.ai/devpack/quick-start.
- GLM-5.3: https://docs.z.ai/guides/llm/glm-5.3 (1M context, 128K output, tools).
- Prices: https://docs.z.ai/guides/overview/pricing (glm-5.3 1.40 / 0.26 / 4.40);
  https://aistudio.google.com/docs/pricing; https://platform.claude.com/docs/en/about-claude/pricing;
  https://developers.openai.com/api/docs/pricing.
- LiteLLM 1.106.6 and google-adk 2.9.1, read in the workbench image
  (`litellm/llms/zai/chat/transformation.py`; `lite_llm.py` ~996–1038, 2486).
- Claude Code 2.1.311 against a local listener: `output_config.effort` and a
  bearer `Authorization` for `--model glm-5.3`.

## Found that contradicts the plan or the brief

- **Codex cannot drive GLM on documented ground.** Codex 0.166.0 speaks the
  Responses API only; Z.ai names `https://api.z.ai/api/v1` once, with no
  reference. Not wired (ADR 0092 §3).
- **Z.ai's Anthropic endpoint is documented under the Coding Plan.** The key
  guide implies a Standard key works there ("keep the same endpoint"); no page
  says it outright. Only the live check proves it.
- **GLM-5.3 has no `medium`.** The map is low→low, medium→high, high→max.
- **LiteLLM's zai provider refuses `reasoning_effort`**: it travels in
  `extra_body`, tested offline against a local listener.
- **Whether Z.ai honours `output_config.effort`** on the Anthropic endpoint is
  not documented; conformance proves only what leaves the harness.
- **Shell-boundary debt raised** for `gates/harness-conformance.sh` (693 → 709)
  and `proof.sh` (738 → 767), against the header's "never raised": the per-file
  loop could not fit otherwise without moving the suite to Python (ADR 0084 §5's
  next slice). crew.sh and review.sh were kept under their debt by moving the
  budget lookup to `core/spend.py`.
- **antigravity-cli undercounted every cached Gemini token** (found by the
  stub's new cached part): agy 1.5.1 reports cache reads as
  `cache_read_tokens`, outside `input_tokens` and `total_tokens` (checked
  against a local endpoint in the pinned image). `run.json` and the budget
  hook now add them back (3d37429); ADR 0092 §6 says so.
- Cache writes on Claude are priced as input (1.25x on the bill): understated,
  named in the ADR. Codex does not report `tokens.cached` yet.

## The live check (not run: needs the owner's approval)

The owner first puts a Standard key from https://z.ai/manage-apikey/apikey-list
in `.env` as **`ZAI_API_KEY`** (never in chat), and the plane slot must be free:

```
./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=claude-code MODEL_PROVIDER=zai MODEL=glm-5.3
```

One dev-worker attempt on ticket 0001 through claude-code and api.z.ai, then
the gates; it writes `fixtures/0001/dev-worker/claude-code/` (not to commit).
Estimate, at glm-5.3's list price (1.40 in, 0.26 cached, 4.40 out per million):

- like Sonnet in M24 (4–13 turns at ~19k): 80k–250k in, 5k–20k out → **$0.13–$0.44**;
- like Gemini in M24 (30–57 calls at ~45k): 1.4M–2.6M in → $2.0–$3.7 uncached,
  $0.5–$1.0 with 90% cached;
- **ceiling: the default `TOKEN_BUDGET` 2,600,000** (zai has no budget of its
  own) → at most ~$3.64 input + ~$0.18 output ≈ **$3.82**, one attempt.

What it proves: a Standard key at `/api/anthropic`, Claude Code's tool loop on
GLM, `tokens.cached` from Z.ai, the ledger's price and basis. It also gives GLM
its first `TOKEN_BUDGET` measurement.

## First thing for the next milestone

Land this branch, then run the live check with the owner's approval; if GLM
spends like Gemini, set `TOKEN_BUDGET_ZAI` from its measure. Site text to hand
to the `site/index.html` owner: "Gemini, Claude, OpenAI or GLM by Z.ai" where
the page lists the providers, and the spend line "cached input at the vendor's
cached rate".
