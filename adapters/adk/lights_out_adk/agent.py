"""build(role, tools): the one LlmAgent shape the three roles share
(docs/adr/0020 §1, §3). Instruction from roles/<role>/prompt.md, thinking
from roles/<role>/role.env, model and provider from the profile (docs/
adr/0040). The tools are the role's decisions; each returns its arguments
echoed, nothing else runs."""

from __future__ import annotations

from typing import Callable

from google.adk.agents.llm_agent import LlmAgent

from .model import planner_for, select_model
from .replay import model_turns
from .roles import load_role


class TurnCapReached(RuntimeError):
    """A run asked for one model turn more than its role's ADK_MAX_TURNS."""


def cap_callback(max_turns: int):
    """The before-model callback that stops a run before turn max_turns + 1
    (docs/adr/0090, amendment A2): the request carries every model turn so
    far, replayed ones included, so the whole conversation is counted."""

    def before_model(callback_context, llm_request):
        if model_turns(llm_request) >= max_turns:
            raise TurnCapReached(f"ADK_MAX_TURNS={max_turns} reached")
        return None

    return before_model


def build(role_name: str, tools: list[Callable], prompt_file: str = "prompt.md") -> LlmAgent:
    role = load_role(role_name, prompt_file)
    return LlmAgent(
        name=role_name.replace("-", "_"),
        model=select_model(role_name, role.thinking, role.instruction_sha256, role.max_turns),
        instruction=role.instruction,
        planner=planner_for(role.thinking),
        tools=tools,
        before_model_callback=cap_callback(role.max_turns),
    )
