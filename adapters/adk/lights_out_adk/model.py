"""Which model a role runs on (docs/adr/0040 §1, §3): the profile's
MODEL_PROVIDER (gemini|anthropic|openai) and MODEL (the exact id), both
overridable from .env, never a role's. AGENT_HARNESS=replay means
fixtures/adk/<role>/ and no provider at all; otherwise Gemini goes
through ADK's own Gemini model with the thinking planner, Claude and
OpenAI through ADK's LiteLlm wrapper with the mapped reasoning effort
and no planner (LiteLlm ignores thinking_config, verified on google-adk
2.9.1). RecordingLlm wraps either when ADK_RECORD=1. The thinking map is
adapters/adk/thinking.env, one line per provider and level."""

from __future__ import annotations

import os
from pathlib import Path

from google.adk.models.base_llm import BaseLlm
from google.adk.models.google_llm import Gemini
from google.adk.planners.base_planner import BasePlanner
from google.adk.planners.built_in_planner import BuiltInPlanner
from google.genai import types

from .replay import RecordingLlm, ReplayLlm
from .roles import read_env, repo_root

PROVIDERS = ("gemini", "anthropic", "openai")
KEY_VAR = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
THINKING_ENV = Path(__file__).resolve().parents[1] / "thinking.env"
PLACEHOLDER = "replace-me"


class NoKey(RuntimeError):
    pass


class BadProvider(RuntimeError):
    pass


class NoModel(RuntimeError):
    pass


class ThinkingMapMissing(RuntimeError):
    pass


def fixtures_dir() -> str:
    return os.environ.get("ADK_FIXTURES", str(repo_root() / "fixtures" / "adk"))


def is_replay() -> bool:
    return os.environ.get("AGENT_HARNESS", "replay") == "replay"


def thinking_map(provider: str, level: str) -> str:
    """The value the request carries for a role's THINKING on a provider,
    from adapters/adk/thinking.env; a missing line names file and key."""
    key = f"{provider.upper()}_{level.upper()}"
    values = read_env(THINKING_ENV) if THINKING_ENV.is_file() else {}
    if key not in values or not values[key]:
        raise ThinkingMapMissing(f"{THINKING_ENV} has no {key}= line (docs/adr/0040 §2)")
    return values[key]


def provider_from_env() -> tuple[str, str, str]:
    """(provider, model id, key) for a live run, refusing in one line
    naming the variable (docs/adr/0040 §1)."""
    provider = os.environ.get("MODEL_PROVIDER", "")
    if provider not in PROVIDERS:
        raise BadProvider(
            f"MODEL_PROVIDER={provider!r} is not one of {', '.join(PROVIDERS)}; "
            "set it in the profile or .env (docs/adr/0040 §1)"
        )
    model_id = os.environ.get("MODEL", "")
    if not model_id:
        raise NoModel(f"MODEL is empty: set the exact {provider} model id in the profile or .env (docs/adr/0040 §1)")
    var = KEY_VAR[provider]
    key = os.environ.get(var, "")
    if not key or key == PLACEHOLDER:
        raise NoKey(
            f"MODEL_PROVIDER={provider} needs a real {var} in .env (see .env.example); "
            "at L0 (PROFILE=l0) the roles replay recorded responses instead"
        )
    return provider, model_id, key


def planner_for(thinking: str) -> BasePlanner | None:
    """Gemini's thinking level travels on ADK's planner; LiteLlm gets
    reasoning_effort instead and no planner, so exactly one reasoning
    setting travels per request (docs/adr/0040 §3). None at replay."""
    if is_replay():
        return None
    provider = os.environ.get("MODEL_PROVIDER", "")
    if provider != "gemini":
        return None
    level = types.ThinkingLevel[thinking_map("gemini", thinking).upper()]
    return BuiltInPlanner(thinking_config=types.ThinkingConfig(thinking_level=level))


def select_model(role: str, thinking: str, instruction_sha256: str | None = None) -> BaseLlm:
    if is_replay():
        return ReplayLlm(role=role, fixtures_dir=fixtures_dir(), instruction_sha256=instruction_sha256)
    provider, model_id, key = provider_from_env()
    if provider == "gemini":
        real: BaseLlm = Gemini(model=model_id, client_kwargs={"api_key": key})
    else:
        # Imported here only: L0 never loads litellm (docs/adr/0040 §3).
        from google.adk.models.lite_llm import LiteLlm

        real = LiteLlm(
            model=f"{provider}/{model_id}",
            reasoning_effort=thinking_map(provider, thinking),
            api_key=key,
        )
    if os.environ.get("ADK_RECORD") in ("1", "extend"):
        # The wrapper carries the requested model id: ADK copies it into
        # every request; the recording says which provider answered.
        return RecordingLlm(
            model=real.model, provider=provider, role=role, fixtures_dir=fixtures_dir(),
            inner=real, instruction_sha256=instruction_sha256,
            extend=os.environ.get("ADK_RECORD") == "extend",
        )
    return real
