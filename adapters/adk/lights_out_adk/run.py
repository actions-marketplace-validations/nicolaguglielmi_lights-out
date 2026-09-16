"""One input in, three files out (docs/adr/0020 §1): runs a role's
root_agent on the text of INPUT as the single user message and writes
OUT/calls.json (the tool calls, in order), OUT/final.md (the final text)
and OUT/run.json. Called by adapters/adk/run.sh; never by core directly.

  ROLE=ops-triage INPUT=alert.json OUT=dir python3 -m lights_out_adk.run
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import sys
import time
import warnings
from pathlib import Path

from google.adk.runners import InMemoryRunner
from google.genai import types


def _tokens(usage) -> dict:
    if usage is None:
        return {"input": 0, "output": 0, "total": 0}
    return {
        "input": usage.prompt_token_count or 0,
        "output": usage.candidates_token_count or 0,
        "total": usage.total_token_count or 0,
    }


async def run(role: str, input_text: str) -> tuple[list[dict], str, dict]:
    package = f"agents.{role.replace('-', '_')}"
    root_agent = importlib.import_module(package).root_agent
    runner = InMemoryRunner(agent=root_agent, app_name=root_agent.name)
    session = await runner.session_service.create_session(app_name=root_agent.name, user_id="lights-out")
    calls: list[dict] = []
    final = ""
    turns = 0
    tokens = {"input": 0, "output": 0, "total": 0}
    message = types.Content(role="user", parts=[types.Part(text=input_text)])
    async for event in runner.run_async(user_id="lights-out", session_id=session.id, new_message=message):
        if event.author == "user":
            continue
        for fc in event.get_function_calls():
            calls.append({"name": fc.name, "args": dict(fc.args or {})})
        if event.usage_metadata is not None:
            turns += 1
            for k, v in _tokens(event.usage_metadata).items():
                tokens[k] += v
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts if p.text)
            if text:
                final = text
    model = getattr(root_agent.model, "model", str(root_agent.model))
    thinking = root_agent.planner.thinking_config.thinking_level.value.lower() if root_agent.planner else None
    return calls, final, {"model": model, "thinking": thinking, "turns": turns, "tokens": tokens}


def main() -> int:
    # ADK logs every failure with its traceback; the adapter reports one line.
    logging.getLogger("google_adk").setLevel(logging.CRITICAL)
    warnings.filterwarnings("ignore", message=r".*\[EXPERIMENTAL\].*")
    role = os.environ["ROLE"]
    input_path = Path(os.environ["INPUT"])
    out = Path(os.environ["OUT"])
    out.mkdir(parents=True, exist_ok=True)
    start = time.time()
    exit_code = 0
    calls: list[dict] = []
    final = ""
    stats: dict = {"model": None, "thinking": None, "turns": 0, "tokens": {"input": 0, "output": 0, "total": 0}}
    try:
        calls, final, stats = asyncio.run(run(role, input_path.read_text()))
    except Exception as e:  # one stderr line, the adapter convention
        print(f"harness-adk: {role}: {type(e).__name__}: {e}", file=sys.stderr)
        exit_code = 1
    (out / "calls.json").write_text(json.dumps(calls, indent=2) + "\n")
    (out / "final.md").write_text(final + ("\n" if final and not final.endswith("\n") else ""))
    run_json = {
        "harness": "adk",
        "model": stats["model"],
        "thinking": stats["thinking"],
        "turns": stats["turns"],
        "tokens": stats["tokens"],
        "duration_s": round(time.time() - start, 1),
        "exit_code": exit_code,
    }
    if os.environ.get("AGENT_HARNESS", "replay") == "replay":
        # A replay never claims tokens it did not spend (docs/adr/0017 §2):
        # the recorded numbers move under `recorded`.
        run_json["source"] = "fixtures/adk"
        run_json["recorded"] = {"turns": run_json["turns"], "tokens": run_json["tokens"]}
        run_json["turns"] = 0
        run_json["tokens"] = {"input": 0, "output": 0, "total": 0}
    (out / "run.json").write_text(json.dumps(run_json, indent=2) + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
