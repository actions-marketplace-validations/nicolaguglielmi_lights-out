# SPDX-License-Identifier: Apache-2.0
"""Tests for lights_out_adk.run's conversation (docs/adr/0055 §2, §3),
written from the ADR, never from the implementation: ANSWERS are later
turns of one session, so a recorded conversation replays as it was
recorded, and a replay with no recording says so in run.json. Driven over
the product role's two committed recordings; the input text is read from
the recording itself, never retyped."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lights_out_adk import run as adk_run

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "adk" / "product"


def recording(turns):
    for path in sorted(FIXTURES.glob("*.json")):
        rec = json.loads(path.read_text())
        if len(rec["responses"]) == turns:
            return rec
    raise AssertionError(f"no product recording with {turns} responses under {FIXTURES}")


class Conversation(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def main(self, input_text, answers=None):
        (self.dir / "input.md").write_text(input_text)
        env = {"ROLE": "product", "INPUT": str(self.dir / "input.md"), "OUT": str(self.dir / "out"),
               "AGENT_HARNESS": "replay", "THINKING": "medium"}
        if answers is not None:
            (self.dir / "answers.json").write_text(json.dumps(answers))
            env["ANSWERS"] = str(self.dir / "answers.json")
        with mock.patch.dict(os.environ, env):
            code = adk_run.main()
        out = self.dir / "out"
        return code, json.loads((out / "calls.json").read_text()), json.loads((out / "run.json").read_text())

    def test_the_request_alone_replays_the_recorded_question(self):
        code, calls, run = self.main(recording(4)["input"])
        self.assertEqual(code, 0)
        self.assertEqual([c["name"] for c in calls], ["ask_product_owner"])
        self.assertNotIn("no_recording", run)

    def test_an_answer_is_the_next_turn_and_replays_the_recorded_criteria(self):
        code, calls, _ = self.main(recording(4)["input"], ["Yes, the first on the list takes the seat."])
        self.assertEqual(code, 0)
        self.assertEqual([c["name"] for c in calls], ["ask_product_owner", "confirm_acceptance"])
        self.assertTrue(calls[-1]["args"]["criteria"])

    def test_a_request_with_criteria_confirms_at_once(self):
        code, calls, _ = self.main(recording(2)["input"], [])
        self.assertEqual((code, [c["name"] for c in calls]), (0, ["confirm_acceptance"]))

    def test_no_recording_is_said_in_run_json(self):
        code, calls, run = self.main("# 9999 — a request nobody recorded\n")
        self.assertEqual((code, calls), (1, []))
        self.assertIs(run["no_recording"], True)

    def test_an_exhausted_recording_is_another_failure(self):
        code, _, run = self.main(recording(2)["input"], ["one answer too many"])
        self.assertEqual(code, 1)
        self.assertNotIn("no_recording", run)

    def test_answers_must_be_a_list_of_strings(self):
        code, _, run = self.main(recording(4)["input"], {"not": "a list"})
        self.assertEqual(code, 1)
        self.assertNotIn("no_recording", run)


if __name__ == "__main__":
    unittest.main()
