"""Which model a role runs on (docs/adr/0020 §2): derived from the profile's
AGENT_HARNESS. `replay` means fixtures/adk/<role>/; anything else means
gemini-3.8-flash through GEMINI_API_KEY, wrapped by RecordingLlm when
ADK_RECORD=1. Vertex is M8's."""

from __future__ import annotations

import os

from google.adk.models.base_llm import BaseLlm
from google.adk.models.google_llm import Gemini

from .replay import RecordingLlm, ReplayLlm
from .roles import repo_root

MODEL_ID = "gemini-3.8-flash"


class NoKey(RuntimeError):
    pass


def fixtures_dir() -> str:
    return os.environ.get("ADK_FIXTURES", str(repo_root() / "fixtures" / "adk"))


def select_model(role: str, thinking: str, instruction_sha256: str | None = None) -> BaseLlm:
    harness = os.environ.get("AGENT_HARNESS", "replay")
    if harness == "replay":
        return ReplayLlm(role=role, fixtures_dir=fixtures_dir(), instruction_sha256=instruction_sha256)
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key or key == "replace-me":
        raise NoKey(
            f"AGENT_HARNESS={harness} needs a real GEMINI_API_KEY in .env (see .env.example); "
            "at L0 (PROFILE=l0) the roles replay recorded responses instead"
        )
    real = Gemini(model=MODEL_ID, client_kwargs={"api_key": key})
    if os.environ.get("ADK_RECORD") == "1":
        # The wrapper carries the real model id: ADK copies it into every request.
        return RecordingLlm(model=MODEL_ID, role=role, fixtures_dir=fixtures_dir(), inner=real, instruction_sha256=instruction_sha256)
    return real
