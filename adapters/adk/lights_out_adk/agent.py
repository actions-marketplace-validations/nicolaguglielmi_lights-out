"""build(role, tools): the one LlmAgent shape the three roles share
(docs/adr/0020 §1, §3). Instruction from roles/<role>/prompt.md, thinking
from roles/<role>/role.env, model from the profile. The tools are the
role's decisions; each returns its arguments echoed, nothing else runs."""

from __future__ import annotations

from typing import Callable

from google.adk.agents.llm_agent import LlmAgent
from google.adk.planners.built_in_planner import BuiltInPlanner
from google.genai import types

from .model import select_model
from .roles import load_role

_LEVELS = {
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}


def build(role_name: str, tools: list[Callable]) -> LlmAgent:
    role = load_role(role_name)
    return LlmAgent(
        name=role_name.replace("-", "_"),
        model=select_model(role_name, role.thinking, role.instruction_sha256),
        instruction=role.instruction,
        planner=BuiltInPlanner(thinking_config=types.ThinkingConfig(thinking_level=_LEVELS[role.thinking])),
        tools=tools,
    )
