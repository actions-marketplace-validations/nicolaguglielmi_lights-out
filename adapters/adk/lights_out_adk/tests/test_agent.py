# SPDX-License-Identifier: Apache-2.0
"""Tests for lights_out_adk.agent's turn cap (docs/adr/0090, Amendment
2026-11-14, A1, A2), written from the ADR, never from the implementation:
before the model is asked for turn cap + 1, the callback stops the run
with TurnCapReached, and says which cap."""
import asyncio
import inspect
import os
import unittest
from pathlib import Path
from unittest import mock

from google.adk.models.llm_request import LlmRequest
from google.genai import types

from lights_out_adk import agent

REPO = Path(__file__).resolve().parents[4]


def request(model_turns):
    contents = [types.Content(role="user", parts=[types.Part(text="the input")])]
    for i in range(model_turns):
        contents.append(types.Content(role="model", parts=[types.Part(text=f"turn {i}")]))
        contents.append(types.Content(role="user", parts=[types.Part(text=f"result {i}")]))
    return LlmRequest(contents=contents)


def call(callback, req):
    out = callback(mock.Mock(), req)
    if inspect.isawaitable(out):
        out = asyncio.run(out)
    return out


class CapCallback(unittest.TestCase):
    def test_under_the_cap_the_model_is_asked(self):
        cb = agent.cap_callback(3)
        for turns in (0, 1, 2):
            with self.subTest(turns=turns):
                self.assertIsNone(call(cb, request(turns)))

    def test_at_the_cap_the_next_turn_is_refused(self):
        with self.assertRaises(agent.TurnCapReached) as cm:
            call(agent.cap_callback(3), request(3))
        self.assertIn("ADK_MAX_TURNS=3 reached", str(cm.exception))

    def test_past_the_cap_is_refused_too(self):
        with self.assertRaises(agent.TurnCapReached) as cm:
            call(agent.cap_callback(3), request(5))
        self.assertIn("ADK_MAX_TURNS=3 reached", str(cm.exception))

    def test_a_cap_of_one_allows_exactly_one_turn(self):
        cb = agent.cap_callback(1)
        self.assertIsNone(call(cb, request(0)))
        with self.assertRaises(agent.TurnCapReached):
            call(cb, request(1))

    def test_the_message_names_the_cap_it_was_given(self):
        with self.assertRaises(agent.TurnCapReached) as cm:
            call(agent.cap_callback(10), request(10))
        self.assertIn("ADK_MAX_TURNS=10 reached", str(cm.exception))


class Build(unittest.TestCase):
    def test_build_installs_the_roles_cap(self):
        def noop() -> dict:
            """A tool."""
            return {}

        env = {"LIGHTS_OUT_ROOT": str(REPO), "AGENT_HARNESS": "replay", "MODEL_PROVIDER": "", "MODEL": ""}
        with mock.patch.dict(os.environ, env):
            built = agent.build("ops-triage", [noop])
        cb = built.before_model_callback
        self.assertIsNotNone(cb, "build() installed no before_model_callback")
        cbs = cb if isinstance(cb, list) else [cb]
        # ops-triage declares ADK_MAX_TURNS=4 (A1's table).
        for turns in (0, 3):
            for one in cbs:
                self.assertIsNone(call(one, request(turns)))
        with self.assertRaises(agent.TurnCapReached) as cm:
            for one in cbs:
                call(one, request(4))
        self.assertIn("ADK_MAX_TURNS=4 reached", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
