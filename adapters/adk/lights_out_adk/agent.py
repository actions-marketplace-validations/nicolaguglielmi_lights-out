"""build(role, tools): the one LlmAgent shape the three roles share
(docs/adr/0020 §1, §3). Instruction from roles/<role>/prompt.md, thinking
from roles/<role>/role.env, model and provider from the profile (docs/
adr/0040). The tools are the role's decisions; each returns its arguments
echoed, nothing else runs."""

from __future__ import annotations

from typing import Callable

from google.adk.agents.llm_agent import LlmAgent

from .model import planner_for, select_model
from .roles import load_role


def build(role_name: str, tools: list[Callable], prompt_file: str = "prompt.md") -> LlmAgent:
    role = load_role(role_name, prompt_file)
    return LlmAgent(
        name=role_name.replace("-", "_"),
        model=select_model(role_name, role.thinking, role.instruction_sha256),
        instruction=role.instruction,
        planner=planner_for(role.thinking),
        tools=tools,
    )
