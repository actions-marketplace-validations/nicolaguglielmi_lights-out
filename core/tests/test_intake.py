"""Tests for core/intake.py, written from docs/adr/0090 §1-§5, never from
the implementation: the raw request's file (`new`), what the product role's
interview run turns into (`interview`, `answers`), the architect's perimeter
proposal over the gate's own check (`perimeter`), the Markdown a proposed
ticket becomes (`compose`, judged by core.spec.check) and the validation of
a person's decisions (`decide`). The run directory is synthetic: the files
a harness leaves in `out/` (calls.json, run.json), which is all the parser
reads. ci/intake.sh proves the same contract through the tower."""

import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import decide, intake, spec

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


# --- docs/adr/0091 §6: the perimeter asked file by file ----------------------

TITLES = {1: "Cancel a seat", 2: "Waitlist a member"}


def two_tickets():
    return {"id": "0105", "kind": "intake", "state": "drafted", "proposal": [
        {"n": n, "title": title, "problem": f"problem {n}", "criteria": [GWT], "feature": None, "priority": None}
        for n, title in TITLES.items()]}


def yes_no_answer(p):
    return {"type": "yes_no", "p_yes": p, "confidence": max(p, 1 - p)}


def decided(ps, **extra):
    """A Decide answer to perimeter_request(two_tickets(), ...): {key: p_yes}."""
    return dict({"answers": {k: yes_no_answer(p) for k, p in ps.items()}, "adapter": "gemini-decisions",
                 "replayed": False, "provider": "gemini", "model": "gemini-decision-1",
                 "tokens": {"input": 100, "output": 0}, "duration_s": 0.5}, **extra)


class Map(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "map.sqlite")

    def build(self, nodes):
        db = sqlite3.connect(self.path)
        db.execute("CREATE TABLE node (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, "
                   "title TEXT NOT NULL DEFAULT '', UNIQUE (kind, name))")
        db.executemany("INSERT INTO node (kind, name) VALUES (?, ?)", nodes)
        db.commit()
        db.close()
        return self.path


class Candidates(Map):
    NODES = [("file", "app/b.py"), ("file", "app/a.py"), ("test", "app/tests/test_a.py"), ("page", "app/index.html"),
             ("adr", "docs/adr/0001-x.md"), ("file", "other/z.py"), ("file", "application/y.py"),
             ("symbol", "app/a.py::f"), ("route", "app/route"), ("ticket", "tickets/0001.md"), ("file", "README.md")]

    def test_the_files_tests_pages_and_adrs_under_the_scope_sorted(self):
        got = intake.candidates(self.build(self.NODES), "app")
        self.assertEqual(got, ["app/a.py", "app/b.py", "app/index.html", "app/tests/test_a.py"])

    def test_a_scope_is_a_directory_not_a_prefix_of_a_name(self):
        self.assertNotIn("application/y.py", intake.candidates(self.build(self.NODES), "app"))

    def test_no_scope_is_every_candidate_kind_and_no_other(self):
        got = intake.candidates(self.build(self.NODES), "")
        self.assertEqual(got, sorted(["README.md", "app/a.py", "app/b.py", "app/index.html", "app/tests/test_a.py",
                                      "application/y.py", "docs/adr/0001-x.md", "other/z.py"]))

    def test_slashes_around_the_scope_do_not_matter_and_a_file_is_its_own_scope(self):
        path = self.build(self.NODES)
        self.assertEqual(intake.candidates(path, "/app/"), intake.candidates(path, "app"))
        self.assertEqual(intake.candidates(path, "other/z.py"), ["other/z.py"])

    def test_a_scope_with_nothing_in_it_is_empty(self):
        self.assertEqual(intake.candidates(self.build(self.NODES), "nowhere"), [])

    def test_each_name_once(self):
        self.assertEqual(intake.candidates(self.build([("file", "a/x.py"), ("test", "a/x.py")]), "a"), ["a/x.py"])


class PerimeterRequest(unittest.TestCase):
    PATHS = ["app/a.py", "app/b.py", "app/c.py"]

    def test_one_yes_no_question_per_ticket_and_path_keyed_by_ticket_and_index(self):
        req = intake.perimeter_request(two_tickets(), self.PATHS)
        self.assertEqual(sorted(req), ["input", "questions"])
        self.assertEqual(list(req["questions"]), [f"t{n}-f{i}" for n in (1, 2) for i in (1, 2, 3)])
        for q in req["questions"].values():
            self.assertEqual(q["type"], "yes_no")
            self.assertEqual(sorted(q["criteria"]), ["false", "true"])
            self.assertTrue(q["criteria"]["true"] and q["criteria"]["false"])

    def test_the_input_is_the_architects_first_message(self):
        doc = two_tickets()
        self.assertEqual(intake.perimeter_request(doc, self.PATHS)["input"], intake.proposal_input(doc))

    def test_each_instruction_quotes_its_path_in_backticks_with_the_ticket_and_its_title(self):
        req = intake.perimeter_request(two_tickets(), self.PATHS)
        for n, title in TITLES.items():
            for i, path in enumerate(self.PATHS, 1):
                text = req["questions"][f"t{n}-f{i}"]["instructions"]
                self.assertIn(f"`{path}`", text)
                self.assertIn(title, text)
                self.assertIn(f"ticket {n}", text)
                self.assertNotIn("`", text.replace(f"`{path}`", ""))

    def test_the_port_accepts_the_request(self):
        decide.check_request(intake.perimeter_request(two_tickets(), self.PATHS))

    def test_the_order_of_the_paths_is_the_order_given(self):
        req = intake.perimeter_request(two_tickets(), ["z.py", "a.py"])
        self.assertIn("`z.py`", req["questions"]["t1-f1"]["instructions"])
        self.assertIn("`a.py`", req["questions"]["t1-f2"]["instructions"])

    def test_no_ticket_or_no_path_is_refused(self):
        for doc in ({}, {"proposal": []}, {"proposal": ["x", 3]}, {"proposal": None}):
            with self.assertRaises(intake.Refused, msg=repr(doc)):
                intake.perimeter_request(doc, self.PATHS)
        with self.assertRaises(intake.Refused):
            intake.perimeter_request(two_tickets(), [])

    def test_a_thousand_questions_pass_and_a_thousand_and_one_are_refused(self):
        one = {"proposal": [two_tickets()["proposal"][0]]}
        self.assertEqual(len(intake.perimeter_request(one, [f"f{i}.py" for i in range(1000)])["questions"]), 1000)
        with self.assertRaises(intake.Refused):
            intake.perimeter_request(one, [f"f{i}.py" for i in range(1001)])
        self.assertEqual(len(intake.perimeter_request(two_tickets(), [f"f{i}.py" for i in range(500)])["questions"]), 1000)
        with self.assertRaises(intake.Refused):
            intake.perimeter_request(two_tickets(), [f"f{i}.py" for i in range(501)])


class Threshold(unittest.TestCase):
    def test_reads_perimeter_confidence_from_the_policy_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decide.env"
            path.write_text("# PERIMETER_CONFIDENCE=0.1\nSCREEN_CONFIDENCE=0.8\nPERIMETER_CONFIDENCE=0.65\n")
            self.assertEqual(intake.confidence_threshold(str(path)), 0.65)
            path.write_text("SCREEN_CONFIDENCE=0.8\n")
            with self.assertRaises(intake.Refused):
                intake.confidence_threshold(str(path))

    def test_the_repos_policy_says_seven_tenths(self):
        self.assertEqual(intake.confidence_threshold(str(ROOT / "policy" / "decide.env")), 0.7)


class PerimeterDecided(unittest.TestCase):
    PATHS = ["app/a.py", "app/b.py", "app/c.py", "app/d.py", "app/e.py"]

    def setUp(self):
        self.doc = two_tickets()
        self.req = intake.perimeter_request(self.doc, self.PATHS)
        self.seen = []

    def check(self, markdown):
        self.seen.append(markdown)
        return f"GO: spec — draft {len(self.seen)}"

    def quiet(self, **override):
        ps = {f"t{n}-f{i}": 0.02 for n in (1, 2) for i in range(1, 6)}
        ps.update(override)
        return ps

    def decide(self, ps, threshold=0.7, **extra):
        return intake.perimeter_decided(self.doc, self.req, decided(ps, **extra), check=self.check, threshold=threshold)

    def test_in_when_yes_and_confident_uncertain_when_not_confident_neither_otherwise(self):
        got = self.decide(self.quiet(**{"t1-f1": 0.9, "t1-f2": 0.1, "t1-f3": 0.6, "t1-f4": 0.4, "t1-f5": 0.95, "t2-f5": 0.9}))
        one, two = got["proposal"]
        self.assertEqual(one["perimeter"], ["app/a.py", "app/e.py"])  # 0.9 and 0.95; 0.1 is a confident no
        self.assertEqual(one["uncertain"], ["app/c.py", "app/d.py"])  # 0.6 and 0.4 are under 0.7
        self.assertEqual((two["perimeter"], two["uncertain"]), (["app/e.py"], []))

    def test_the_boundaries(self):
        one = self.decide(self.quiet(**{"t1-f1": 0.7, "t1-f2": 0.3, "t1-f3": 0.6996, "t1-f4": 0.5, "t1-f5": 0.31}))["proposal"][0]
        self.assertEqual(one["perimeter"], ["app/a.py"])  # confidence 0.7 is enough
        # a no at confidence exactly 0.7 is a confident no: in neither list
        self.assertEqual(one["uncertain"], ["app/c.py", "app/d.py", "app/e.py"])

    def test_p_of_one_half_is_in_when_the_threshold_allows(self):
        one = self.decide(self.quiet(**{"t1-f1": 0.5, "t1-f2": 0.49}), threshold=0.5)["proposal"][0]
        self.assertEqual(one["perimeter"], ["app/a.py"])
        self.assertEqual(one["uncertain"], [])

    def test_the_threshold_moves_the_split(self):
        ps = self.quiet(**{"t1-f1": 0.75})
        self.assertEqual(self.decide(ps, threshold=0.7)["proposal"][0]["perimeter"], ["app/a.py"])
        got = self.decide(ps, threshold=0.8)["proposal"][0]
        self.assertEqual((got["perimeter"], got["uncertain"]), ([], ["app/a.py"]))

    def test_the_default_threshold_is_the_policys(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "policy").mkdir()
            (Path(tmp) / "policy" / "decide.env").write_text("PERIMETER_CONFIDENCE=0.9\n")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                got = intake.perimeter_decided(self.doc, self.req, decided(self.quiet(**{"t1-f1": 0.85})), check=self.check)
            finally:
                os.chdir(cwd)
        self.assertEqual((got["proposal"][0]["perimeter"], got["proposal"][0]["uncertain"]), ([], ["app/a.py"]))

    def test_uncertain_is_most_probable_first_then_by_path(self):
        got = self.decide(self.quiet(**{"t1-f1": 0.6, "t1-f2": 0.65, "t1-f3": 0.4, "t1-f4": 0.65, "t1-f5": 0.55}))
        self.assertEqual(got["proposal"][0]["uncertain"], ["app/b.py", "app/d.py", "app/a.py", "app/e.py", "app/c.py"])

    def test_the_perimeter_is_in_path_order_whatever_the_order_of_the_answers(self):
        ps = {f"t1-f{i}": 0.95 for i in (5, 3, 1, 4, 2)}
        ps.update({f"t2-f{i}": 0.02 for i in range(1, 6)})
        self.assertEqual(self.decide(ps)["proposal"][0]["perimeter"], self.PATHS)

    def test_each_ticket_has_its_own_answers(self):
        one, two = self.decide(self.quiet(**{"t1-f1": 0.9, "t2-f2": 0.9}))["proposal"]
        self.assertEqual((one["perimeter"], two["perimeter"]), (["app/a.py"], ["app/b.py"]))
        self.assertEqual((one["n"], two["n"], one["title"], two["title"]), (1, 2, TITLES[1], TITLES[2]))

    def test_the_result_is_a_proposed_intake_consulted_by_decide(self):
        got = self.decide(self.quiet())
        self.assertEqual(got["state"], "proposed")
        self.assertEqual(sorted(got), ["architect", "proposal", "state"])
        a = got["architect"]
        self.assertEqual((a["consulted"], a["by"], a["questions"]), (True, "decide", 10))
        self.assertEqual((a["harness"], a["replayed"], a["provider"], a["model"]),
                         ("gemini-decisions", False, "gemini", "gemini-decision-1"))

    def test_a_replayed_answer_is_a_replayed_run(self):
        ans = decided(self.quiet(), adapter="replay", replayed=True, provider=None, model=None,
                      tokens={"input": 0, "output": 0}, recorded={"adapter": "gemini-decisions", "provider": "gemini",
                                                                  "model": "gemini-decision-1",
                                                                  "tokens": {"input": 640, "output": 0}})
        a = intake.perimeter_decided(self.doc, self.req, ans, check=self.check, threshold=0.7)["architect"]
        self.assertEqual((a["harness"], a["replayed"], a["by"], a["consulted"]), ("replay", True, "decide", True))

    def test_the_gate_checks_every_composed_draft(self):
        got = self.decide(self.quiet(**{"t1-f1": 0.9, "t2-f3": 0.9}))
        self.assertEqual(len(self.seen), 2)
        self.assertEqual([t["check"] for t in got["proposal"]], ["GO: spec — draft 1", "GO: spec — draft 2"])
        self.assertIn("- `app/a.py`", self.seen[0])
        self.assertNotIn("app/c.py", self.seen[0])
        self.assertIn("- `app/c.py`", self.seen[1])
        self.assertIn(TITLES[1], self.seen[0])
        self.assertIn(TITLES[2], self.seen[1])

    def test_a_draft_is_the_ticket_composed_with_its_perimeter(self):
        got = self.decide(self.quiet(**{"t1-f2": 0.9}))
        t = {k: v for k, v in got["proposal"][0].items() if k != "check"}
        self.assertEqual(self.seen[0], intake.compose(t, "draft", "0105"))

    def test_an_intake_without_a_proposal_is_refused(self):
        with self.assertRaises(intake.Refused):
            intake.perimeter_decided({"id": "x", "proposal": []}, self.req, decided({}), check=self.check, threshold=0.7)


class Screened(RunDir):
    def test_the_screen_beside_the_run_joins_the_result(self):
        run_dir = self.run_dir()
        screen = {"verdict": "pass", "p_yes": 0.01, "sha256": "ab" * 32}
        Path(run_dir, "screen.json").write_text(json.dumps(screen))
        self.assertEqual(intake.screened({"state": "intake-questions"}, run_dir),
                         {"state": "intake-questions", "screen": screen})

    def test_no_screen_or_one_that_is_not_an_object_leaves_the_result(self):
        run_dir = self.run_dir()
        result = {"state": "drafted", "proposal": []}
        self.assertEqual(intake.screened(result, run_dir), result)
        for body in ("[]", '"pass"', "not json", "null"):
            Path(run_dir, "screen.json").write_text(body)
            self.assertEqual(intake.screened(result, run_dir), result, body)

    def test_the_results_own_keys_are_kept(self):
        run_dir = self.run_dir()
        Path(run_dir, "screen.json").write_text(json.dumps({"verdict": "flag"}))
        got = intake.screened({"state": "s", "questions": [1]}, run_dir)
        self.assertEqual((got["state"], got["questions"], got["screen"]["verdict"]), ("s", [1], "flag"))


class DecidePerimeter(Map):
    """The step asked file by file, through the real port with a stub adapter."""

    ANSWER_PY = (
        "import json, sys\n"
        "req = json.load(sys.stdin)\n"
        "plan = json.load(open('plan.json'))\n"
        "ans = {}\n"
        "for k in req['questions']:\n"
        "    p = plan.get(k, 0.02)\n"
        "    ans[k] = {'type': 'yes_no', 'p_yes': p, 'confidence': max(p, 1 - p)}\n"
        "print(json.dumps({'answers': ans, 'provider': 'prov', 'model': 'mod', 'tokens': {'input': 5, 'output': 0}}))\n")

    def setUp(self):
        super().setUp()
        self._cwd = os.getcwd()
        self.root = Path(self._tmp.name) / "cwd"
        (self.root / "adapters" / "stub").mkdir(parents=True)
        (self.root / "policy").mkdir()
        (self.root / "policy" / "decide.env").write_text("PERIMETER_CONFIDENCE=0.7\nSCREEN_CONFIDENCE=0.8\n")
        (self.root / "core").symlink_to(ROOT / "core")
        (self.root / "adapters" / "stub" / "answer.py").write_text(self.ANSWER_PY)
        (self.root / "adapters" / "stub" / "decide.sh").write_text("exec python3 adapters/stub/answer.py\n")
        (self.root / "plan.json").write_text(json.dumps({"t1-f1": 0.9, "t1-f2": 0.6, "t2-f2": 0.95}))
        self.run_dir = self.root / "run"
        self.run_dir.mkdir()
        self.doc = two_tickets()
        self.map = self.build([("file", "app/a.py"), ("file", "app/b.py"), ("file", "app/c.py"), ("file", "other/z.py")])
        os.chdir(self.root)
        env = mock.patch.dict(os.environ, {"DECIDE": "stub"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(os.chdir, self._cwd)

    def build_more(self, n):
        os.remove(self.map)
        return self.build([("file", f"f{i}.py") for i in range(n)])

    def decide(self, scope="app"):
        with mock.patch.object(intake, "gate_line", return_value="GO: spec"):
            return intake.decide_perimeter(self.doc, self.map, scope, str(self.run_dir))

    def doc_file(self):
        path = self.root / "doc.json"
        path.write_text(json.dumps(self.doc))
        return str(path)

    def test_asks_every_candidate_for_every_ticket_and_composes_the_result(self):
        got = self.decide()
        one, two = got["proposal"]
        self.assertEqual((one["perimeter"], one["uncertain"]), (["app/a.py"], ["app/b.py"]))
        self.assertEqual((two["perimeter"], two["uncertain"]), (["app/b.py"], []))
        a = got["architect"]
        self.assertEqual((a["consulted"], a["by"], a["questions"], a["harness"]), (True, "decide", 6, "stub"))
        self.assertEqual(got["state"], "proposed")

    def test_the_threshold_is_read_from_the_policy(self):
        (self.root / "policy" / "decide.env").write_text("PERIMETER_CONFIDENCE=0.97\n")
        one = self.decide()["proposal"][0]
        self.assertEqual((one["perimeter"], one["uncertain"]), ([], ["app/a.py", "app/b.py"]))

    def test_more_than_a_thousand_questions_search_instead(self):
        self.map = self.build_more(501)
        with self.assertRaises(intake.SearchInstead) as cm:
            self.decide(scope="")
        self.assertIn("search", str(cm.exception))

    def test_exactly_a_thousand_questions_are_asked(self):
        self.map = self.build_more(500)
        self.assertEqual(self.decide(scope="")["architect"]["questions"], 1000)

    def test_no_recording_at_l0_searches_instead(self):
        with mock.patch.dict(os.environ, {"DECIDE": "replay"}), self.assertRaises(intake.SearchInstead) as cm:
            self.decide()
        self.assertIn("search", str(cm.exception))

    def test_a_recording_is_replayed(self):
        req = intake.perimeter_request(self.doc, ["app/a.py", "app/b.py", "app/c.py"])
        ans = {"answers": {k: yes_no_answer(0.02) for k in req["questions"]}, "tokens": {"input": 640, "output": 0},
               "adapter": "gemini-decisions", "provider": "gemini", "model": "gemini-decision-1"}
        ans["answers"]["t1-f3"] = yes_no_answer(0.95)
        decide.record(req, ans, {})
        with mock.patch.dict(os.environ, {"DECIDE": "replay"}):
            got = self.decide()
        self.assertEqual(got["proposal"][0]["perimeter"], ["app/c.py"])
        self.assertEqual((got["architect"]["harness"], got["architect"]["replayed"]), ("replay", True))

    def test_any_other_failure_is_refused_with_the_decision_line(self):
        (self.root / "adapters" / "stub" / "decide.sh").write_text('cat >/dev/null\necho "the key is missing" >&2\nexit 1\n')
        with self.assertRaises(intake.Refused) as cm:
            self.decide()
        self.assertNotIsInstance(cm.exception, intake.SearchInstead)
        self.assertTrue(str(cm.exception).startswith("the architect's decision failed: "))
        self.assertIn("the key is missing", str(cm.exception))
        with mock.patch.dict(os.environ, {"DECIDE": "nothing"}), self.assertRaises(intake.Refused) as cm:
            self.decide()
        self.assertTrue(str(cm.exception).startswith("the architect's decision failed: "))

    def test_main_returns_three_when_the_step_searches_instead(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"DECIDE": "replay"}), contextlib.redirect_stderr(err):
            code = intake.main(["decide-perimeter", self.doc_file(), self.map, "app", str(self.run_dir)], {})
        self.assertEqual(code, 3)
        self.assertIn("search", err.getvalue())

    def test_main_prints_the_decided_result_as_json(self):
        out = io.StringIO()
        with mock.patch.object(intake, "gate_line", return_value="GO"), contextlib.redirect_stdout(out):
            code = intake.main(["decide-perimeter", self.doc_file(), self.map, "app", str(self.run_dir)], {})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["proposal"][0]["perimeter"], ["app/a.py"])

    def test_main_refused_is_one_with_the_line(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"DECIDE": "nothing"}), contextlib.redirect_stderr(err):
            code = intake.main(["decide-perimeter", self.doc_file(), self.map, "app", str(self.run_dir)], {})
        self.assertEqual(code, 1)
        self.assertIn("the architect's decision failed", err.getvalue())

    def test_main_prints_the_request(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(intake.main(["perimeter-request", self.doc_file(), self.map, "app"], {}), 0)
        self.assertEqual(json.loads(out.getvalue()),
                         intake.perimeter_request(self.doc, ["app/a.py", "app/b.py", "app/c.py"]))


if __name__ == "__main__":
    unittest.main()
