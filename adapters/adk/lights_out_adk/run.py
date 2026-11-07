"""One input in, three files out (docs/adr/0020 §1): runs a role's
root_agent on the text of INPUT as the first user message, then each
string of the optional ANSWERS file (a JSON list) as a later user message
of the same session (docs/adr/0055 §2), and writes
OUT/calls.json (the tool calls, in order), OUT/final.md (the final text)
and OUT/run.json, which says the provider and the model that answered,
not the one requested (docs/adr/0040 §3). Called by adapters/adk/run.sh;
never by core directly.

  ROLE=ops-triage INPUT=alert.json OUT=dir python3 -m lights_out_adk.run

Under replay, a run that fails because no recording exists for INPUT says
so in run.json, `no_recording: true`, so the caller can tell it from any
other failure (docs/adr/0055 §3).
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


def no_recording(error: BaseException) -> bool:
    """Whether the replay model's own NoRecording is anywhere in the chain."""
    from lights_out_adk.replay import NoRecording

    seen = set()
    while error is not None and id(error) not in seen:
        if isinstance(error, NoRecording):
            return True
        seen.add(id(error))
        error = error.__cause__ or error.__context__
    return False


async def run(role: str, input_text: str, answers: list[str] = ()) -> tuple[list[dict], str, dict]:
    package = f"agents.{role.replace('-', '_')}"
    root_agent = importlib.import_module(package).root_agent
    runner = InMemoryRunner(agent=root_agent, app_name=root_agent.name)
    session = await runner.session_service.create_session(app_name=root_agent.name, user_id="lights-out")
    calls: list[dict] = []
    final = ""
    turns = 0
    tokens = {"input": 0, "output": 0, "total": 0}
    served = None
    for text_in in [input_text, *answers]:
        message = types.Content(role="user", parts=[types.Part(text=text_in)])
        async for event in runner.run_async(user_id="lights-out", session_id=session.id, new_message=message):
            if event.author == "user":
                continue
            for fc in event.get_function_calls():
                calls.append({"name": fc.name, "args": dict(fc.args or {})})
            if getattr(event, "model_version", None):
                served = event.model_version
            if event.usage_metadata is not None:
                turns += 1
                for k, v in _tokens(event.usage_metadata).items():
                    tokens[k] += v
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(p.text or "" for p in event.content.parts if p.text)
                if text:
                    final = text
    # The model that answered, not the one requested (docs/adr/0018,
    # 0040 §3): the last non-empty model_version the responses carried.
    return calls, final, {"model": served or "unknown", "turns": turns, "tokens": tokens}


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
    stats: dict = {"model": None, "turns": 0, "tokens": {"input": 0, "output": 0, "total": 0}}
    replay = os.environ.get("AGENT_HARNESS", "replay") == "replay"
    unrecorded = False
    try:
        answers = json.loads(Path(os.environ["ANSWERS"]).read_text()) if os.environ.get("ANSWERS") else []
        if not isinstance(answers, list) or not all(isinstance(a, str) for a in answers):
            raise ValueError(f"ANSWERS {os.environ['ANSWERS']} is not a JSON list of strings")
        calls, final, stats = asyncio.run(run(role, input_path.read_text(), answers))
    except Exception as e:  # one stderr line, the adapter convention
        print(f"harness-adk: {role}: {type(e).__name__}: {e}", file=sys.stderr)
        exit_code = 1
        unrecorded = replay and no_recording(e)
    (out / "calls.json").write_text(json.dumps(calls, indent=2) + "\n")
    (out / "final.md").write_text(final + ("\n" if final and not final.endswith("\n") else ""))
    run_json = {
        "harness": "adk",
        "provider": None if replay else os.environ.get("MODEL_PROVIDER") or None,
        "model": None if replay else stats["model"],
        "thinking": os.environ.get("THINKING") or None,
        "turns": stats["turns"],
        "tokens": stats["tokens"],
        "duration_s": round(time.time() - start, 1),
        "exit_code": exit_code,
    }
    if unrecorded:
        run_json["no_recording"] = True
    if replay:
        # A replay never claims a model or tokens it did not use (docs/adr/
        # 0017 §2, 0040 §3): provider and model are null, and the fixture's
        # own provider, model and numbers move under `recorded`.
        run_json["source"] = "fixtures/adk"
        run_json["recorded"] = {
            "provider": None,
            "model": stats["model"] if stats["model"] != "unknown" else None,
            "turns": run_json["turns"],
            "tokens": run_json["tokens"],
        }
        run_json["turns"] = 0
        run_json["tokens"] = {"input": 0, "output": 0, "total": 0}
        try:
            root_agent = importlib.import_module(f"agents.{role.replace('-', '_')}").root_agent
            recorded = getattr(root_agent.model, "recorded", None) or {}
            run_json["recorded"]["provider"] = recorded.get("provider")
            if recorded.get("model"):
                run_json["recorded"]["model"] = recorded["model"]
        except Exception:
            pass
    (out / "run.json").write_text(json.dumps(run_json, indent=2) + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
