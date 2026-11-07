"""Tests for core/spec.py, written from docs/adr/0055 §2-§4, never from the
implementation: the spec gate's rules and order, what the product role's
run turns into, the composed spec and the spec step's two outcomes."""

import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from core import spec

STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
GOOD = """# 0099 — a request

## Problem

Something is wrong.

## Acceptance criteria

Given a meetup at capacity
When a new member signs up
Then they join the waiting list instead of getting a 409

Given a waiting list with one member, when an attendee cancels, then the
first member on the list is promoted to attendee

## Perimeter

- `app/backend/meetups/*.py`
"""


def without(text, heading):
    out, skip = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            skip = line.startswith(heading)
        if not skip:
            out.append(line)
    return "\n".join(out) + "\n"


class Gate(unittest.TestCase):
    """§4: GWT in order, an observable outcome, a declared perimeter."""

    def test_a_testable_spec_with_a_perimeter_passes(self):
        self.assertIsNone(spec.check(GOOD))

    def test_every_committed_ticket_with_a_perimeter_passes(self):
        for path in sorted(Path("tickets").glob("*.md")):
            text = path.read_text()
            if re.search(r"^## Perimeter", text, re.M):
                self.assertIsNone(spec.check(text), path)

    def test_the_recorded_criteria_of_the_product_role_pass(self):
        for path in sorted(Path("fixtures/adk/product").glob("*.json")):
            for response in json.loads(path.read_text())["responses"]:
                for part in (response.get("content") or {}).get("parts") or []:
                    call = part.get("function_call") or {}
                    if call.get("name") == "confirm_acceptance":
                        doc = {"spec": {"criteria": call["args"]["criteria"]}}
                        self.assertIsNone(spec.check(spec.compose(GOOD, doc)), path)

    def test_no_criteria_section(self):
        self.assertIn("no ## Acceptance criteria", spec.check(without(GOOD, "## Acceptance")))

    def test_an_empty_criteria_section(self):
        text = GOOD.replace(GOOD[GOOD.index("Given a meetup"):GOOD.index("## Perimeter")], "\n")
        self.assertIn("has no criterion", spec.check(text))

    def test_a_criterion_without_when_or_then(self):
        self.assertIn("When", spec.check(GOOD.replace("When a new member", "And a new member")))
        self.assertIn("Then", spec.check(GOOD.replace("Then they join", "So they join")))

    def test_the_words_must_come_in_order(self):
        text = GOOD.replace("Given a meetup at capacity\nWhen a new member signs up\nThen they join",
                            "Then they join\nWhen a new member signs up\nGiven a meetup at capacity and")
        self.assertIsNotNone(spec.check(text))

    def test_a_then_with_no_outcome(self):
        self.assertIn("no outcome", spec.check(GOOD.replace(
            "Then they join the waiting list instead of getting a 409", "Then")))

    def test_a_vague_outcome_is_named(self):
        for vague in ("it works", "the signup is handled correctly", "it behaves as expected",
                      "the page loads Fast", "errors are handled"):
            why = spec.check(GOOD.replace("they join the waiting list instead of getting a 409", vague))
            self.assertIsNotNone(why, vague)
            self.assertIn("names no observable outcome", why)

    def test_a_vague_word_inside_another_word_is_not_vague(self):
        text = GOOD.replace("they join the waiting list", "the breakfast workshop keeps its list")
        self.assertIsNone(spec.check(text))

    def test_a_vague_word_before_then_is_not_judged(self):
        self.assertIsNone(spec.check(GOOD.replace("Given a meetup at capacity", "Given a fast meetup")))

    def test_no_perimeter_section(self):
        self.assertEqual(spec.check(without(GOOD, "## Perimeter")), "no ## Perimeter section")

    def test_a_perimeter_with_no_path(self):
        self.assertIn("declares no path", spec.check(GOOD.replace("- `app/backend/meetups/*.py`", "none yet")))

    def test_the_first_failure_is_the_criteria_before_the_perimeter(self):
        text = without(GOOD, "## Perimeter").replace("Then they join", "So they join")
        self.assertIn("Then", spec.check(text))


class Answers(unittest.TestCase):
    """§2: answered questions become later turns; a spec gate's carries its reason."""

    def test_only_answered_questions_in_order(self):
        doc = {"questions": [{"question": "q1", "from": "product", "answer": "a1"},
                             {"question": "no perimeter", "from": "spec", "answer": "added it"},
                             {"question": "q3", "from": "product"}]}
        got = spec.answers(doc)
        self.assertEqual(got[0], "a1")
        self.assertEqual(len(got), 2)
        self.assertIn("no perimeter", got[1])
        self.assertIn("added it", got[1])

    def test_no_questions_no_answers(self):
        self.assertEqual(spec.answers({}), [])


class Clarify(unittest.TestCase):
    """§2, §3: the product role's last decision moves the ticket."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        (self.dir / "out").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def run_with(self, calls=None, run=None, err="", rc=0, doc=None, env=None):
        if calls is not None:
            (self.dir / "out" / "calls.json").write_text(json.dumps(calls))
        if run is not None:
            (self.dir / "out" / "run.json").write_text(json.dumps(run))
        (self.dir / "run.err").write_text(err)
        return spec.clarify(GOOD, doc or {}, str(self.dir), rc, env or {"AGENT_HARNESS": "replay"})

    def test_a_question_moves_to_questions_and_is_kept_after_the_earlier_ones(self):
        doc = {"questions": [{"question": "q1", "answer": "a1"}]}
        got = self.run_with([{"name": "ask_product_owner", "args": {"question": " What then? "}}],
                            {"harness": "adk"}, doc=doc)
        self.assertEqual(got["state"], "questions")
        self.assertEqual(got["questions"][0], {"question": "q1", "answer": "a1"})
        new = got["questions"][1]
        self.assertEqual((new["question"], new["from"]), ("What then?", "product"))
        self.assertRegex(new["asked_at"], STAMP)
        self.assertTrue(got["product"]["consulted"])

    def test_a_confirmation_moves_to_spec_ready_with_the_criteria(self):
        got = self.run_with([{"name": "ask_product_owner", "args": {"question": "q?"}},
                             {"name": "confirm_acceptance", "args": {"criteria": ["Given a, when b, then c", " "]}}],
                            {"harness": "replay", "recorded": {"model": "m", "turns": 4}})
        self.assertEqual(got["state"], "spec-ready")
        self.assertEqual(got["spec"], {"criteria": ["Given a, when b, then c"], "by": "product"})
        self.assertEqual((got["product"]["model"], got["product"]["turns"]), ("m", 4))
        self.assertTrue(got["product"]["replayed"])

    def test_the_last_decision_wins(self):
        got = self.run_with([{"name": "confirm_acceptance", "args": {"criteria": ["x"]}},
                             {"name": "ask_product_owner", "args": {"question": "again?"}}], {})
        self.assertEqual(got["state"], "questions")

    def test_no_decision_empty_question_or_no_criteria_fails(self):
        for calls in ([], [{"name": "other", "args": {}}],
                      [{"name": "ask_product_owner", "args": {"question": " "}}],
                      [{"name": "confirm_acceptance", "args": {"criteria": []}}]):
            with self.assertRaises(spec.Refused):
                self.run_with(calls, {})

    def test_no_recording_at_l0_takes_the_request_and_says_so(self):
        got = self.run_with(run={"harness": "adk", "no_recording": True}, rc=1,
                            err="noise\nharness-adk: product: NoRecording: no recording for this request\n")
        self.assertEqual(got["state"], "spec-ready")
        self.assertFalse(got["product"]["consulted"])
        self.assertIn("NoRecording", got["product"]["why"])
        self.assertEqual(got["spec"]["by"], "request")
        self.assertEqual(len(got["spec"]["criteria"]), 2)

    def test_no_recording_above_l0_or_any_other_failure_fails(self):
        with self.assertRaises(spec.Refused):
            self.run_with(run={"no_recording": True}, rc=1, env={"AGENT_HARNESS": "gemini-cli"})
        with self.assertRaises(spec.Refused):
            self.run_with(run={"harness": "adk"}, rc=1, err="timeout")


class Compose(unittest.TestCase):
    """§4: the request with its criteria replaced by the confirmed ones."""

    def test_the_confirmed_criteria_replace_the_request_s(self):
        out = spec.compose(GOOD, {"spec": {"criteria": ["Given x, when y, then z"]}})
        self.assertIn("Given x, when y, then z", out)
        self.assertNotIn("Given a meetup", out)
        self.assertIn("## Perimeter", out)
        self.assertIn("## Problem", out)
        self.assertIsNone(spec.check(out))

    def test_a_request_without_criteria_gets_the_section(self):
        out = spec.compose(without(GOOD, "## Acceptance"), {"spec": {"criteria": ["Given x, when y, then z"]}})
        self.assertIn("## Acceptance criteria", out)
        self.assertIsNone(spec.check(out))


class Gated(unittest.TestCase):
    """§4: GO opens the ticket; NO-GO goes back to questions with the reason."""

    def test_go_opens(self):
        got = spec.gated({}, "GO: spec")
        self.assertEqual((got["state"], got["spec"]["verdict"], got["spec"]["line"]), ("opened", "GO", "GO: spec"))
        self.assertRegex(got["spec"]["at"], STAMP)

    def test_no_go_asks_the_reason(self):
        got = spec.gated({"questions": [{"question": "q1"}]}, "NO-GO: spec — no ## Perimeter section")
        self.assertEqual(got["state"], "questions")
        self.assertEqual(got["spec"]["verdict"], "NO-GO")
        self.assertEqual(got["questions"][0], {"question": "q1"})
        self.assertEqual((got["questions"][1]["question"], got["questions"][1]["from"]),
                         ("no ## Perimeter section", "spec"))

    def test_no_verdict_fails_the_step(self):
        for line in ("", "GO: other", "maybe"):
            with self.assertRaises(spec.Refused):
                spec.gated({}, line)


class Main(unittest.TestCase):
    def call(self, *argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = spec.main(list(argv), env or {})
        return code, out.getvalue(), err.getvalue()

    def test_check_prints_the_reason_and_exits_one(self):
        with tempfile.TemporaryDirectory() as d:
            good, bad = os.path.join(d, "good.md"), os.path.join(d, "bad.md")
            Path(good).write_text(GOOD)
            Path(bad).write_text(without(GOOD, "## Perimeter"))
            self.assertEqual(self.call("check", good)[:2], (0, ""))
            code, out, _ = self.call("check", bad)
            self.assertEqual((code, out.strip()), (1, "no ## Perimeter section"))

    def test_a_refusal_is_one_stderr_line_and_exit_one(self):
        code, out, err = self.call("gated", "/nonexistent.json", "maybe")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("spec: "))

    def test_usage(self):
        self.assertEqual(self.call()[0], 2)
        self.assertEqual(self.call("check")[0], 2)


if __name__ == "__main__":
    unittest.main()
