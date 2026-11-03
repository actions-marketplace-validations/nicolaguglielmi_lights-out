# SPDX-License-Identifier: Apache-2.0
"""Tests for lights_out_adk.replay and lights_out_adk.model (docs/adr/0020
§2, §8), written from the ADR, never from the implementation. Run by
`ci/evals.sh` step (c): `python3 -m unittest discover -s
adapters/adk/lights_out_adk/tests -t adapters/adk`.
"""
import asyncio
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from lights_out_adk import model, replay


def _collect(agen):
    """Runs an async generator to completion, returning its yielded items."""

    async def _run():
        out = []
        async for item in agen:
            out.append(item)
        return out

    return asyncio.run(_run())


class KeyForTest(unittest.TestCase):
    def test_json_input_is_canonicalised_regardless_of_key_order(self):
        a = replay.key_for('{"b": 1, "a": 2}')
        b = replay.key_for('{"a": 2, "b": 1}')
        self.assertEqual(a, b)

    def test_plain_text_input_is_stripped(self):
        a = replay.key_for("hello\n")
        b = replay.key_for("hello")
        c = replay.key_for("  hello  ")
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_json_and_differently_formatted_json_share_a_key(self):
        a = replay.key_for('{"a":1,"b":2}')
        b = replay.key_for('{\n  "b": 2,\n  "a": 1\n}\n')
        self.assertEqual(a, b)


class ReplayLlmTest(unittest.TestCase):
    """Builds a real fixture file (the shape ADR 0020 §2 gives) and drives
    ReplayLlm's generate_content_async over it."""

    def setUp(self):
        self.fixtures_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.fixtures_dir, ignore_errors=True)
        self.role = "ops-triage"
        self.input_text = "what should we do about the canary alert?"
        self.key = replay.key_for(self.input_text)

        response_one = LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="one")])
        ).model_dump(exclude_none=True)
        response_two = LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="two")])
        ).model_dump(exclude_none=True)

        role_dir = os.path.join(self.fixtures_dir, self.role)
        os.makedirs(role_dir)
        record = {
            "input": self.input_text,
            "instruction_sha256": "deadbeef",
            "model": "gemini-3.8-flash",
            "recorded_at": "2026-09-16T00:00:00Z",
            "responses": [response_one, response_two],
        }
        with open(
            os.path.join(role_dir, f"{self.key}.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(record, f)

    def _request(self, model_turns):
        """An LlmRequest whose first user content is the fixture's input,
        followed by `model_turns` model-role contents."""
        contents = [
            types.Content(role="user", parts=[types.Part(text=self.input_text)])
        ]
        for i in range(model_turns):
            contents.append(
                types.Content(
                    role="model", parts=[types.Part(text=f"prior turn {i}")]
                )
            )
        return LlmRequest(contents=contents)

    def test_zero_model_turns_yields_the_first_recorded_response(self):
        llm = replay.ReplayLlm(role=self.role, fixtures_dir=self.fixtures_dir)
        got = _collect(llm.generate_content_async(self._request(0)))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].content.parts[0].text, "one")

    def test_one_model_turn_yields_the_second_recorded_response(self):
        llm = replay.ReplayLlm(role=self.role, fixtures_dir=self.fixtures_dir)
        got = _collect(llm.generate_content_async(self._request(1)))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].content.parts[0].text, "two")

    def test_missing_fixture_raises_no_recording_naming_role_key_input_and_command(
        self,
    ):
        llm = replay.ReplayLlm(role=self.role, fixtures_dir=self.fixtures_dir)
        other_text = "a question this fixtures directory never recorded"
        req = LlmRequest(
            contents=[types.Content(role="user", parts=[types.Part(text=other_text)])]
        )
        with self.assertRaises(replay.NoRecording) as ctx:
            _collect(llm.generate_content_async(req))
        message = str(ctx.exception)
        self.assertIn(self.role, message)
        self.assertIn(replay.key_for(other_text), message)
        self.assertIn(other_text[:80], message)
        self.assertIn("./go record-evals PROFILE=l1", message)

    def test_index_beyond_the_recording_raises_recording_exhausted(self):
        llm = replay.ReplayLlm(role=self.role, fixtures_dir=self.fixtures_dir)
        # Two model-role contents already in the request -> index 2, but the
        # fixture holds only two responses (indices 0 and 1).
        with self.assertRaises(replay.RecordingExhausted) as ctx:
            _collect(llm.generate_content_async(self._request(2)))
        message = str(ctx.exception)
        self.assertIn(self.role, message)
        self.assertIn(self.key, message)


class SelectModelTest(unittest.TestCase):
    def test_replay_harness_returns_a_replay_llm_and_never_builds_gemini(self):
        def boom(*_args, **_kwargs):
            raise AssertionError(
                "Gemini must never be constructed under AGENT_HARNESS=replay"
            )

        with mock.patch.object(model, "Gemini", boom), mock.patch.dict(
            os.environ, {"AGENT_HARNESS": "replay"}
        ):
            got = model.select_model("ops-triage", "low")
        self.assertIsInstance(got, replay.ReplayLlm)

    def test_a_real_harness_with_no_key_raises_no_key(self):
        # docs/adr/0040 §1: a live run names its provider and model; the
        # placeholder key of the chosen provider is still refused.
        with mock.patch.dict(
            os.environ,
            {
                "AGENT_HARNESS": "gemini-cli",
                "MODEL_PROVIDER": "gemini",
                "MODEL": "gemini-3.8-flash",
                "GEMINI_API_KEY": "replace-me",
            },
        ):
            with self.assertRaises(model.NoKey):
                model.select_model("ops-triage", "low")


if __name__ == "__main__":
    unittest.main()
