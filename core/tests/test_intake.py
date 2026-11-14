"""Tests for core/intake.py, written from docs/adr/0090 §1-§5, never from
the implementation: the raw request's file (`new`), what the product role's
interview run turns into (`interview`, `answers`), the architect's perimeter
proposal over the gate's own check (`perimeter`), the Markdown a proposed
ticket becomes (`compose`, judged by core.spec.check) and the validation of
a person's decisions (`decide`). The run directory is synthetic: the files
a harness leaves in `out/` (calls.json, run.json), which is all the parser
reads. ci/intake.sh proves the same contract through the tower."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core import intake, spec

ROOT = Path(__file__).resolve().parents[2]
LAST = "\n\nThat was the last question this interview allows: propose the tickets now."
GWT = "Given a member with a seat, when they cancel it, then the seat count of the event goes up by one"
GWT2 = "Given a member without a seat, when they cancel it, then the response status is 404"
REPLAY = {"AGENT_HARNESS": "replay"}


def asked(n, answered=True):
    q = {"question": f"question {n}?", "from": "product", "asked_at": "2026-11-14T10:00:00Z"}
    if answered:
        q.update(answer=f"answer {n}", answered_by="ci", answered_via="cli", answered_at="2026-11-14T10:01:00Z")
    return q


def ask(text="Who cancels?"):
    return {"name": "ask_product_owner", "args": {"question": text}}


def propose(title="Cancel a seat", problem="People cannot give a seat back.", criteria=None, feature="", priority=""):
    return {"name": "propose_ticket", "args": {
        "title": title, "problem": problem, "criteria": [GWT] if criteria is None else criteria,
        "feature": feature, "priority": priority}}


class RunDir(unittest.TestCase):
    """A synthetic run directory under a temp root."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def run_dir(self, calls=None, run=None, name="run"):
        d = self.tmp / name
        (d / "out").mkdir(parents=True, exist_ok=True)
        if calls is not None:
            (d / "out" / "calls.json").write_text(json.dumps(calls))
        (d / "out" / "run.json").write_text(json.dumps(run if run is not None else {"harness": "adk", "model": "m"}))
        return str(d)


class New(RunDir):
    """§1: `new` writes the client's words and nothing else."""

    def new(self, text, *args, tickets=None):
        tickets = tickets or self.tmp / "tickets"
        tickets.mkdir(exist_ok=True)
        src = self.tmp / "text.md"
        src.write_bytes(text.encode())
        got = subprocess.run([sys.executable, str(ROOT / "core" / "intake.py"), "new", str(src), str(tickets), *args],
                             cwd=ROOT, capture_output=True, text=True)
        return got, tickets

    def test_writes_the_text_byte_for_byte_with_one_final_newline(self):
        text = "We need  seats back.\r\n\r\n  Indented second paragraph, no final newline"
        got, tickets = self.new(text, "0007")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual((tickets / "0007.intake.md").read_bytes(), text.encode() + b"\n")

    def test_a_text_that_ends_in_a_newline_is_not_given_a_second(self):
        got, tickets = self.new("one line\n", "0007")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual((tickets / "0007.intake.md").read_bytes(), b"one line\n")

    def test_without_an_id_it_takes_the_next_free_one_counting_intakes(self):
        tickets = self.tmp / "tickets"
        tickets.mkdir()
        (tickets / "0003.md").write_text("# 0003 — x\n")
        got, _ = self.new("first", tickets=tickets)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertTrue((tickets / "0004.intake.md").is_file())
        got, _ = self.new("second", tickets=tickets)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertTrue((tickets / "0005.intake.md").is_file())

    def test_refuses_an_id_whose_ticket_exists(self):
        tickets = self.tmp / "tickets"
        tickets.mkdir()
        (tickets / "0007.md").write_text("# 0007 — x\n")
        got, _ = self.new("text", "0007", tickets=tickets)
        self.assertEqual(got.returncode, 1)
        self.assertFalse((tickets / "0007.intake.md").exists())

    def test_refuses_an_id_whose_intake_exists_and_leaves_it_alone(self):
        tickets = self.tmp / "tickets"
        tickets.mkdir()
        (tickets / "0007.intake.md").write_text("the first words\n")
        got, _ = self.new("other words", "0007", tickets=tickets)
        self.assertEqual(got.returncode, 1)
        self.assertEqual((tickets / "0007.intake.md").read_text(), "the first words\n")

    def test_refuses_empty_text(self):
        got, tickets = self.new("", "0007")
        self.assertEqual(got.returncode, 1)
        self.assertFalse((tickets / "0007.intake.md").exists())

    def test_the_specs_next_id_skips_an_id_taken_by_an_intake(self):
        tickets = self.tmp / "tickets"
        tickets.mkdir()
        (tickets / "0001.md").write_text("# 0001 — x\n")
        (tickets / "0002.intake.md").write_text("words\n")
        self.assertEqual(spec.next_id(str(tickets)), "0003")


class Answers(unittest.TestCase):
    """§2: the answers so far, and the cap's last sentence."""

    def test_the_answered_questions_in_order(self):
        doc = {"questions": [asked(1), asked(2), asked(3, answered=False)]}
        self.assertEqual(intake.answers(doc), ["answer 1", "answer 2"])

    def test_no_questions_no_answers(self):
        self.assertEqual(intake.answers({}), [])

    def test_the_fifth_answer_carries_the_last_question_sentence(self):
        doc = {"questions": [asked(n) for n in range(1, 6)]}
        got = intake.answers(doc)
        self.assertEqual(got[:4], [f"answer {n}" for n in range(1, 5)])
        self.assertEqual(got[4], "answer 5" + LAST)

    def test_the_fourth_answer_does_not(self):
        doc = {"questions": [asked(n) for n in range(1, 5)]}
        self.assertEqual(intake.answers(doc)[-1], "answer 4")


class Interview(RunDir):
    """§2: the run decides by its calls; the cap is enforced here."""

    def doc(self, answered=0):
        return {"id": "0100", "kind": "intake", "state": "intake" if not answered else "intake-questions",
                "questions": [asked(n) for n in range(1, answered + 1)]}

    def test_a_question_keeps_the_intake_waiting_for_a_person(self):
        got = intake.interview(self.doc(), self.run_dir([ask("Who cancels?")]), 0, REPLAY)
        self.assertEqual(got["state"], "intake-questions")
        self.assertEqual(len(got["questions"]), 1)
        q = got["questions"][0]
        self.assertEqual((q["question"], q["from"]), ("Who cancels?", "product"))
        self.assertRegex(q["asked_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertIs(got["product"]["consulted"], True)

    def test_the_new_question_is_appended_after_the_answered_ones(self):
        got = intake.interview(self.doc(2), self.run_dir([ask("Third?")]), 0, REPLAY)
        self.assertEqual([q["question"] for q in got["questions"]], ["question 1?", "question 2?", "Third?"])

    def test_a_fifth_question_is_allowed(self):
        got = intake.interview(self.doc(4), self.run_dir([ask("Fifth?")]), 0, REPLAY)
        self.assertEqual(got["state"], "intake-questions")

    def test_a_sixth_question_is_refused(self):
        with self.assertRaises(intake.Refused):
            intake.interview(self.doc(5), self.run_dir([ask("Sixth?")]), 0, REPLAY)

    def test_proposed_tickets_after_the_last_question_are_the_proposal_in_order(self):
        calls = [ask(), propose("First", "p1", [GWT, GWT2], "waiting-list", "P1"), propose("Second", "p2", [GWT])]
        got = intake.interview(self.doc(1), self.run_dir(calls), 0, REPLAY)
        self.assertEqual(got["state"], "drafted")
        self.assertIs(got["product"]["consulted"], True)
        first, second = got["proposal"]
        self.assertEqual(first, {"n": 1, "title": "First", "problem": "p1", "criteria": [GWT, GWT2],
                                 "feature": "waiting-list", "priority": "P1"})
        self.assertEqual(second, {"n": 2, "title": "Second", "problem": "p2", "criteria": [GWT],
                                  "feature": None, "priority": None})

    def test_a_proposal_with_no_question_at_all_is_allowed(self):
        got = intake.interview(self.doc(), self.run_dir([propose()]), 0, REPLAY)
        self.assertEqual(got["state"], "drafted")
        self.assertEqual(len(got["proposal"]), 1)

    def test_a_proposal_may_follow_the_fifth_answer(self):
        got = intake.interview(self.doc(5), self.run_dir([propose()]), 0, REPLAY)
        self.assertEqual(got["state"], "drafted")

    def test_confirm_acceptance_is_refused_in_an_intake(self):
        calls = [{"name": "confirm_acceptance", "args": {"criteria": [GWT]}}]
        with self.assertRaises(intake.Refused):
            intake.interview(self.doc(), self.run_dir(calls), 0, REPLAY)

    def test_no_decision_is_refused(self):
        with self.assertRaises(intake.Refused):
            intake.interview(self.doc(), self.run_dir([]), 0, REPLAY)

    def test_an_empty_question_is_refused(self):
        for text in ("", "   "):
            with self.assertRaises(intake.Refused, msg=repr(text)):
                intake.interview(self.doc(), self.run_dir([ask(text)]), 0, REPLAY)

    def test_a_proposed_ticket_missing_a_title_a_problem_or_a_criterion_is_refused(self):
        for bad in (propose(title=""), propose(problem=""), propose(criteria=[]), propose(criteria=[" "])):
            with self.assertRaises(intake.Refused, msg=json.dumps(bad["args"])):
                intake.interview(self.doc(), self.run_dir([bad]), 0, REPLAY)

    def test_at_l0_without_a_recording_it_is_refused_naming_it(self):
        run = self.run_dir(None, {"harness": "adk", "no_recording": True})
        with self.assertRaises(intake.Refused) as cm:
            intake.interview(self.doc(), run, 1, REPLAY)
        self.assertIn("no recording", str(cm.exception))

    def test_a_failed_run_that_is_not_a_missing_recording_is_refused(self):
        with self.assertRaises(intake.Refused):
            intake.interview(self.doc(), self.run_dir(None, {"harness": "adk"}), 1, {})


class Perimeter(RunDir):
    """§3: the architect's paths per ticket, each draft judged by the gate."""

    PROPOSAL = [
        {"n": 1, "title": "Cancel a seat", "problem": "p1", "criteria": [GWT], "feature": None, "priority": None},
        {"n": 2, "title": "Who is coming", "problem": "p2", "criteria": [GWT2], "feature": "roster", "priority": "P2"},
    ]

    def doc(self):
        return {"id": "0100", "kind": "intake", "state": "drafted", "proposal": [dict(t) for t in self.PROPOSAL]}

    @staticmethod
    def fake(seen):
        def check(text):
            seen.append(text)
            why = spec.check(text)
            return "GO: spec" if why is None else f"NO-GO: spec — {why}"
        return check

    def call(self, calls, run=None, rc=0, env=None):
        seen = []
        got = intake.perimeter(self.doc(), self.run_dir(calls, run), rc, env or REPLAY, self.fake(seen))
        return got, seen

    def test_each_ticket_gets_its_paths_and_its_check_line(self):
        calls = [{"name": "propose_perimeter", "args": {"ticket": 1, "paths": ["src/a.py"]}},
                 {"name": "propose_perimeter", "args": {"ticket": 2, "paths": ["src/roster.py", "tests/test_roster.py"]}}]
        got, seen = self.call(calls)
        self.assertEqual(got["state"], "proposed")
        self.assertIs(got["architect"]["consulted"], True)
        one, two = got["proposal"]
        self.assertEqual(one["perimeter"], ["src/a.py"])
        self.assertEqual(two["perimeter"], ["src/roster.py", "tests/test_roster.py"])
        self.assertEqual((one["check"], two["check"]), ("GO: spec", "GO: spec"))
        self.assertEqual((one["title"], two["feature"]), ("Cancel a seat", "roster"))
        self.assertEqual(len(seen), 2)
        self.assertIn("src/a.py", seen[0])

    def test_the_last_call_naming_a_ticket_wins(self):
        calls = [{"name": "propose_perimeter", "args": {"ticket": 1, "paths": ["src/old.py"]}},
                 {"name": "propose_perimeter", "args": {"ticket": 1, "paths": ["src/new.py"]}}]
        got, _ = self.call(calls)
        self.assertEqual(got["proposal"][0]["perimeter"], ["src/new.py"])

    def test_a_ticket_no_call_names_has_an_empty_perimeter_and_the_gates_no_go(self):
        calls = [{"name": "propose_perimeter", "args": {"ticket": 1, "paths": ["src/a.py"]}}]
        got, _ = self.call(calls)
        two = got["proposal"][1]
        self.assertEqual(two["perimeter"], [])
        self.assertTrue(two["check"].startswith("NO-GO: spec — "), two["check"])
        self.assertIn("Perimeter", two["check"])

    def test_at_l0_without_a_recording_the_step_does_not_fail(self):
        run = {"harness": "adk", "no_recording": True}
        got, seen = self.call(None, run=run, rc=1)
        self.assertEqual(got["state"], "proposed")
        self.assertIs(got["architect"]["consulted"], False)
        self.assertTrue(got["architect"]["why"])
        for t in got["proposal"]:
            self.assertEqual(t["perimeter"], [])
            self.assertTrue(t["check"].startswith("NO-GO: spec — "), t["check"])
        self.assertEqual(len(seen), 2)


class Compose(unittest.TestCase):
    """§5: the Markdown a proposed ticket becomes, judged by the unchanged gate."""

    def ticket(self, **over):
        t = {"n": 1, "title": "Cancel a seat", "problem": "People cannot give a seat back.",
             "criteria": [GWT, GWT2], "feature": "waiting-list", "priority": "P1",
             "perimeter": ["src/a.py", "tests/test_a.py"]}
        t.update(over)
        return t

    def test_the_shape_of_a_committed_ticket(self):
        text = intake.compose(self.ticket(), "0106", "0105")
        lines = text.splitlines()
        self.assertEqual(lines[0], "# 0106 — Cancel a seat")
        for line in ("- Status: open", "- Intake: 0105", "- Feature: waiting-list", "- Priority: P1",
                     "## Problem", "## Acceptance criteria", "## Perimeter",
                     "- `src/a.py`", "- `tests/test_a.py`"):
            self.assertIn(line, lines)
        self.assertTrue(text.endswith("\n"))
        self.assertLess(lines.index("## Problem"), lines.index("## Acceptance criteria"))
        self.assertLess(lines.index("## Acceptance criteria"), lines.index("## Perimeter"))
        self.assertEqual(spec.criteria_of(text), [GWT, GWT2])

    def test_feature_and_priority_lines_only_when_set(self):
        text = intake.compose(self.ticket(feature=None, priority=None), "0106", "0105")
        self.assertNotIn("- Feature:", text)
        self.assertNotIn("- Priority:", text)
        self.assertIn("- Intake: 0105", text)

    def test_a_complete_ticket_passes_the_spec_gate(self):
        text = intake.compose(self.ticket(), "0106", "0105")
        self.assertIsNone(spec.check(text))
        self.assertEqual(spec.fields(text), {"feature": "waiting-list", "priority": "P1"})

    def test_an_empty_perimeter_is_the_gates_no_go(self):
        why = spec.check(intake.compose(self.ticket(perimeter=[]), "0106", "0105"))
        self.assertIsNotNone(why)
        self.assertIn("Perimeter", why)

    def test_a_vague_criterion_is_the_gates_no_go_too(self):
        vague = "Given a member with a seat, when they cancel it, then it works correctly"
        why = spec.check(intake.compose(self.ticket(criteria=[vague]), "0106", "0105"))
        self.assertIn("works", why)


class Decide(unittest.TestCase):
    """§5: one entry per proposed ticket, in order; anything else is refused."""

    def doc(self, state="proposed", n=3):
        return {"id": "0105", "kind": "intake", "state": state,
                "proposal": [{"n": i + 1, "title": f"t{i + 1}", "problem": "p", "criteria": [GWT],
                              "feature": None, "priority": None, "perimeter": ["src/x.py"]} for i in range(n)]}

    def test_a_valid_list_is_accepted(self):
        got = intake.decide(self.doc(), ["confirm", "drop", {"edit": {"perimeter": ["src/x.py"]}}])
        self.assertEqual(len(got), 3)

    def test_every_replaceable_field_may_be_edited(self):
        edit = {"title": "t", "problem": "p", "criteria": [GWT], "perimeter": ["a.py"], "feature": "f", "priority": "P0"}
        self.assertEqual(len(intake.decide(self.doc(n=1), [{"edit": edit}])), 1)

    def test_dropping_every_ticket_is_a_valid_confirmation(self):
        self.assertEqual(len(intake.decide(self.doc(), ["drop"] * 3)), 3)

    def test_a_list_of_another_length_is_refused(self):
        for decisions in (["confirm"] * 2, ["confirm"] * 4, []):
            with self.assertRaises(intake.Refused, msg=repr(decisions)):
                intake.decide(self.doc(), decisions)

    def test_an_unknown_entry_is_refused(self):
        for entry in ("keep", "CONFIRM", 1, None, {"delete": {}}, {"edit": "x"}):
            with self.assertRaises(intake.Refused, msg=repr(entry)):
                intake.decide(self.doc(), ["confirm", "confirm", entry])

    def test_not_a_list_is_refused(self):
        with self.assertRaises(intake.Refused):
            intake.decide(self.doc(), {"confirm": 1})

    def test_an_intake_not_at_proposed_is_refused(self):
        for state in ("intake", "intake-questions", "drafted", "confirmed"):
            with self.assertRaises(intake.Refused, msg=state):
                intake.decide(self.doc(state), ["confirm"] * 3)


if __name__ == "__main__":
    unittest.main()
