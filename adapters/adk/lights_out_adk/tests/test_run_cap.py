# SPDX-License-Identifier: Apache-2.0
"""Tests for lights_out_adk.run's turn cap (docs/adr/0090, Amendment
2026-11-14, A2), written from the ADR, never from the implementation.

Live: a role whose model never stops asking for a tool, under
cap_callback(3), must stop with exactly three model calls, exit 1, one
stderr line, and a run.json that says how many turns it took and why it
stopped. This is the planted overrun: it fails where the cap does not
exist. Replay: a recording over the role's cap is refused, and refused as
something other than `no_recording`. Each run is a subprocess, so no
module state leaks between cases."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from lights_out_adk import replay

REPO = Path(__file__).resolve().parents[4]
ADK = REPO / "adapters" / "adk"

AGENT_PY = textwrap.dedent('''
    import os
    from typing import AsyncGenerator

    from google.adk.agents.llm_agent import LlmAgent
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    from lights_out_adk.agent import cap_callback
    from lights_out_adk.replay import model_turns


    class FakeLlm(BaseLlm):
        model: str = "fake"

        @classmethod
        def supported_models(cls):
            return ["fake"]

        async def generate_content_async(self, llm_request, stream=False) -> AsyncGenerator[LlmResponse, None]:
            with open(os.environ["COUNT_FILE"], "a") as fh:
                fh.write("call\\n")
            usage = types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10, candidates_token_count=2, total_token_count=12)
            end_after = int(os.environ.get("END_AFTER", "0"))
            if end_after and model_turns(llm_request) >= end_after:
                part = types.Part(text="done")
            else:
                part = types.Part(function_call=types.FunctionCall(name="ping", args={}))
            yield LlmResponse(content=types.Content(role="model", parts=[part]),
                              usage_metadata=usage, model_version="fake-1")


    def ping() -> dict:
        """A trivial tool."""
        return {"pong": True}


    root_agent = LlmAgent(name="capped", model=FakeLlm(), instruction="never stop", tools=[ping],
                          before_model_callback=cap_callback(3))
''')


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.out = self.dir / "out"

    def run_module(self, role, input_text, pythonpath, **env):
        (self.dir / "input.md").write_text(input_text)
        full = dict(os.environ, ROLE=role, INPUT=str(self.dir / "input.md"), OUT=str(self.out),
                    PYTHONPATH=pythonpath, LIGHTS_OUT_ROOT=str(REPO), THINKING="low", **env)
        for k in ("ANSWERS", "ADK_RECORD"):
            full.pop(k, None)
        got = subprocess.run([sys.executable, "-m", "lights_out_adk.run"], env=full, cwd=str(self.dir),
                             capture_output=True, text=True, timeout=120, check=False)
        run = json.loads((self.out / "run.json").read_text()) if (self.out / "run.json").is_file() else None
        return got, run


class LiveCap(Base):
    def setUp(self):
        super().setUp()
        pkg = self.dir / "pkg" / "agents" / "capped"
        pkg.mkdir(parents=True)
        (self.dir / "pkg" / "agents" / "__init__.py").write_text("")
        (pkg / "__init__.py").write_text("from . import agent\nfrom .agent import root_agent\n")
        (pkg / "agent.py").write_text(AGENT_PY)
        self.count = self.dir / "count"
        self.count.write_text("")
        self.path = f"{self.dir / 'pkg'}{os.pathsep}{ADK}"

    def calls(self):
        return len(self.count.read_text().splitlines())

    def live(self, **env):
        return self.run_module("capped", "go on forever", self.path, AGENT_HARNESS="gemini",
                               COUNT_FILE=str(self.count), **env)

    def test_a_role_that_never_stops_is_stopped_at_its_cap(self):
        got, run = self.live()
        self.assertEqual(got.returncode, 1, got.stderr)
        self.assertEqual(self.calls(), 3, "the model must be asked exactly ADK_MAX_TURNS times, no more")

    def test_it_says_so_in_one_stderr_line(self):
        got, _ = self.live()
        lines = [line for line in got.stderr.splitlines() if "ADK_MAX_TURNS=3 reached" in line]
        self.assertEqual(len(lines), 1, got.stderr)
        self.assertEqual(len([line for line in got.stderr.splitlines() if line.strip()]), 1, got.stderr)

    def test_run_json_carries_the_turns_taken_and_the_stop(self):
        _, run = self.live()
        self.assertIsNotNone(run, "a stopped run writes no run.json")
        self.assertEqual(run["turns"], 3)
        self.assertEqual(run["stop"], "ADK_MAX_TURNS=3")
        self.assertEqual(run["exit_code"], 1)
        self.assertNotIn("no_recording", run)

    def test_the_tokens_spent_so_far_are_reported(self):
        _, run = self.live()
        self.assertEqual(run["tokens"], {"input": 30, "output": 6, "total": 36})

    def test_a_run_that_ends_under_the_cap_is_not_stopped(self):
        got, run = self.live(END_AFTER="2")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(self.calls(), 3)
        self.assertEqual(run["turns"], 3)
        self.assertNotIn("stop", run)

    def test_a_run_that_ends_well_under_the_cap_takes_the_turns_it_needs(self):
        got, run = self.live(END_AFTER="1")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(run["turns"], 2)
        self.assertNotIn("stop", run)


class ReplayOverCap(Base):
    """The product role's cap is 16 (A1's table); the recording is planted
    under a temp ADK_FIXTURES, never under the repo's fixtures/."""

    INPUT = "# Intake request\n\nPeople cannot cancel.\n"

    def plant(self, turns):
        fixtures = self.dir / "fixtures"
        (fixtures / "product").mkdir(parents=True)
        responses = [
            {"content": {"role": "model", "parts": [{"text": f"turn {i}"}]}} for i in range(turns)
        ]
        (fixtures / "product" / f"{replay.key_for(self.INPUT)}.json").write_text(
            json.dumps({"input": self.INPUT, "responses": responses, "model": "m", "provider": "gemini"}))
        return fixtures

    def replayed(self, turns):
        fixtures = self.plant(turns)
        return self.run_module("product", self.INPUT, str(ADK), AGENT_HARNESS="replay", ADK_FIXTURES=str(fixtures))

    def test_a_recording_over_the_cap_is_refused(self):
        got, run = self.replayed(17)
        self.assertEqual(got.returncode, 1, got.stderr)
        self.assertIn("ADK_MAX_TURNS=16", got.stderr)
        self.assertIn("over its", got.stderr)
        self.assertIsNotNone(run)
        self.assertNotIn("no_recording", run)

    def test_it_is_not_replayed_in_part(self):
        _, run = self.replayed(17)
        self.assertEqual((self.out / "final.md").read_text().strip(), "")
        self.assertEqual(json.loads((self.out / "calls.json").read_text()), [])
        self.assertEqual(run["recorded"]["turns"], 0)

    def test_a_recording_at_the_cap_replays(self):
        got, run = self.replayed(16)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertNotIn("no_recording", run)
        self.assertNotIn("stop", run)


if __name__ == "__main__":
    unittest.main()
