"""Tests for core/spec.py, written from docs/adr/0055 §2-§4 and docs/adr/0059
§4, never from the implementation: the spec gate's rules and order, what the
product role's run turns into, the composed spec and the spec step's two
outcomes, and the draft the console's editor writes from a request's fields
(`draft`: fields in, the ticket's Markdown out, judged by the gate's own
rules)."""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core import spec

ROOT = Path(__file__).resolve().parents[2]
DROP = object()  # a field left out of the request, as opposed to one that is empty
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
GOOD = """# 0099 — a request

## Problem

Something is wrong.

## Acceptance criteria

Given a event at capacity
When a new member signs up
Then they join the waiting list instead of getting a 409

Given a waiting list with one member, when an attendee cancels, then the
first member on the list is promoted to attendee

## Perimeter

- `src/events/*.py`
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
        text = GOOD.replace(GOOD[GOOD.index("Given a event"):GOOD.index("## Perimeter")], "\n")
        self.assertIn("has no criterion", spec.check(text))

    def test_a_criterion_without_when_or_then(self):
        self.assertIn("When", spec.check(GOOD.replace("When a new member", "And a new member")))
        self.assertIn("Then", spec.check(GOOD.replace("Then they join", "So they join")))

    def test_the_words_must_come_in_order(self):
        text = GOOD.replace("Given a event at capacity\nWhen a new member signs up\nThen they join",
                            "Then they join\nWhen a new member signs up\nGiven a event at capacity and")
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
        self.assertIsNone(spec.check(GOOD.replace("Given a event at capacity", "Given a fast event")))

    def test_no_perimeter_section(self):
        self.assertEqual(spec.check(without(GOOD, "## Perimeter")), "no ## Perimeter section")

    def test_a_perimeter_with_no_path(self):
        self.assertIn("declares no path", spec.check(GOOD.replace("- `src/events/*.py`", "none yet")))

    def test_the_first_failure_is_the_criteria_before_the_perimeter(self):
        text = without(GOOD, "## Perimeter").replace("Then they join", "So they join")
        self.assertIn("Then", spec.check(text))


class Fields(unittest.TestCase):
    """§7: Feature and Priority are optional; present, they must be well formed."""

    def with_header(self, *lines):
        return GOOD.replace("# 0099 — a request\n", "# 0099 — a request\n\n" + "\n".join(lines) + "\n", 1)

    def test_absent_fields_pass_and_read_as_none(self):
        self.assertIsNone(spec.check(GOOD))
        self.assertEqual(spec.fields(GOOD), {"feature": None, "priority": None})

    def test_well_formed_fields_pass_and_are_read(self):
        text = self.with_header("- Status: open", "- Feature: waiting-list", "- Priority: P1")
        self.assertIsNone(spec.check(text))
        self.assertEqual(spec.fields(text), {"feature": "waiting-list", "priority": "P1"})

    def test_every_priority_from_p0_to_p3(self):
        for p in ("P0", "P1", "P2", "P3"):
            self.assertIsNone(spec.check(self.with_header(f"- Priority: {p}")), p)

    def test_a_malformed_value_is_named(self):
        for line in ("- Priority: P4", "- Priority: high", "- Priority: p1", "- Feature: Waiting List",
                     "- Feature: waiting--list", "- Feature: -x", "- Feature:"):
            field, value = line[2:].split(":", 1)
            why = spec.check(self.with_header(line))
            self.assertIsNotNone(why, line)
            self.assertIn(f'- {field}: "{value.strip()}"', why)

    def test_a_field_set_twice(self):
        self.assertIn("2 times", spec.check(self.with_header("- Priority: P1", "- Priority: P2")))

    def test_a_field_after_the_first_section_is_not_a_header(self):
        text = GOOD.replace("Something is wrong.", "Something is wrong.\n\n- Priority: urgent")
        self.assertIsNone(spec.check(text))
        self.assertIsNone(spec.fields(text)["priority"])


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
        self.assertNotIn("Given a event", out)
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


class Draft(unittest.TestCase):
    """docs/adr/0059 §4: `draft <fields.json> <tickets dir> [<out dir>]` writes
    `<out dir, default tickets dir>/<id>.md` under the next free id, with an
    exclusive create, prints the id, and refuses bad fields in one stderr line
    with nothing written. The Markdown it writes is judged by the gate."""

    FIELDS = {
        "title": "A waiting list when a room is full",
        "context": "A full room refuses every further signup.",
        "criteria": [
            {"given": "a room at capacity", "when": "a new member signs up",
             "then": "they join the waiting list and see their position"},
            {"given": "a waiting list with one member", "when": "an attendee cancels",
             "then": "the first member on the list becomes an attendee"},
        ],
        "perimeter": ["src/queue/*", "docs/queue.md"],
        "feature": "waiting-list",
        "priority": "P1",
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.tickets = self.dir / "tickets"
        self.tickets.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def fields(self, **change):
        fields = json.loads(json.dumps(self.FIELDS))
        for key, value in change.items():
            if value is DROP:
                fields.pop(key, None)
            else:
                fields[key] = value
        return fields

    def write_fields(self, fields):
        path = self.dir / "fields.json"
        path.write_text(fields if isinstance(fields, str) else json.dumps(fields), encoding="utf-8")
        return path

    def call(self, fields, out=None):
        """(exit code, stdout, stderr) of `draft`, the fields as a file."""
        argv = ["draft", str(self.write_fields(fields)), str(self.tickets)] + ([str(out)] if out else [])
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = spec.main(argv, {})
        return code, stdout.getvalue(), stderr.getvalue()

    def cli(self, *argv):
        """The command line itself: python3 core/spec.py ..."""
        return subprocess.run([sys.executable, str(ROOT / "core" / "spec.py"), *argv],
                              capture_output=True, text=True, cwd=ROOT, check=False)

    def drafted(self, fields, out=None):
        """The id and the Markdown of a draft that must succeed."""
        code, stdout, stderr = self.call(fields, out=out)
        self.assertEqual((code, stderr), (0, ""), stderr)
        ticket = stdout.strip()
        self.assertRegex(ticket, r"^\d{4}$")
        return ticket, (Path(out or self.tickets) / f"{ticket}.md").read_text(encoding="utf-8")

    def listing(self, where=None):
        return sorted(p.name for p in Path(where or self.tickets).iterdir())

    # --- the id -----------------------------------------------------------

    def test_the_first_ticket_is_0001(self):
        ticket, _ = self.drafted(self.fields())
        self.assertEqual(ticket, "0001")
        self.assertEqual(self.listing(), ["0001.md"])

    def test_the_id_is_printed_alone_on_stdout(self):
        code, stdout, _ = self.call(self.fields())
        self.assertEqual((code, stdout.splitlines()), (0, ["0001"]))

    def test_the_id_is_the_next_after_the_highest_four_digit_name(self):
        for name in ("0001.md", "0002.md", "0007.md"):
            (self.tickets / name).write_text("# t\n")
        self.assertEqual(self.drafted(self.fields())[0], "0008")

    def test_a_gap_is_not_filled(self):
        for name in ("0003.md", "0004.md"):
            (self.tickets / name).write_text("# t\n")
        self.assertEqual(self.drafted(self.fields())[0], "0005")

    def test_the_id_is_zero_padded_to_four_digits(self):
        (self.tickets / "0009.md").write_text("# t\n")
        self.assertEqual(self.drafted(self.fields())[0], "0010")
        (self.tickets / "0099.md").write_text("# t\n")
        self.assertEqual(self.drafted(self.fields())[0], "0100")

    def test_only_names_of_four_digits_and_md_count(self):
        (self.tickets / "0003.md").write_text("# t\n")
        for name in ("README.md", "notes.txt", "0099.txt", "12.md", "abcd.md", "0050.md.bak"):
            (self.tickets / name).write_text("x\n")
        self.assertEqual(self.drafted(self.fields())[0], "0004")

    def test_two_drafts_in_a_row_get_two_ids(self):
        self.assertEqual(self.drafted(self.fields())[0], "0001")
        self.assertEqual(self.drafted(self.fields(title="Another"))[0], "0002")
        self.assertEqual(self.listing(), ["0001.md", "0002.md"])

    # --- where it writes --------------------------------------------------

    def test_the_file_goes_to_the_tickets_dir_by_default(self):
        ticket, text = self.drafted(self.fields())
        self.assertTrue(text.startswith(f"# {ticket} — {self.FIELDS['title']}\n"))

    def test_an_out_dir_takes_the_file_and_the_tickets_dir_only_names_the_id(self):
        out = self.dir / "out"
        out.mkdir()
        (out / "0050.md").write_text("# not a ticket of the tickets dir\n")
        (self.tickets / "0004.md").write_text("# t\n")
        ticket, text = self.drafted(self.fields(), out=out)
        self.assertEqual(ticket, "0005")
        self.assertEqual(self.listing(out), ["0005.md", "0050.md"])
        self.assertEqual(self.listing(), ["0004.md"])
        self.assertIn("0005", text.splitlines()[0])

    def test_an_existing_file_is_never_overwritten(self):
        out = self.dir / "out"
        out.mkdir()
        (out / "0001.md").write_text("keep me\n")
        code, stdout, stderr = self.call(self.fields(), out=out)
        self.assertEqual((code, stdout), (1, ""))
        self.assertTrue(stderr.startswith("spec: "), stderr)
        self.assertEqual(len(stderr.splitlines()), 1, stderr)
        self.assertEqual((out / "0001.md").read_text(), "keep me\n")
        self.assertEqual(self.listing(out), ["0001.md"])
        self.assertEqual(self.listing(), [])

    # --- what it writes ---------------------------------------------------

    def test_the_markdown_of_a_full_request(self):
        _, text = self.drafted(self.fields())
        self.assertEqual(text, (
            "# 0001 — A waiting list when a room is full\n"
            "\n"
            "- Status: open\n"
            "- Feature: waiting-list\n"
            "- Priority: P1\n"
            "\n"
            "## Problem\n"
            "\n"
            "A full room refuses every further signup.\n"
            "\n"
            "## Acceptance criteria\n"
            "\n"
            "Given a room at capacity\n"
            "When a new member signs up\n"
            "Then they join the waiting list and see their position\n"
            "\n"
            "Given a waiting list with one member\n"
            "When an attendee cancels\n"
            "Then the first member on the list becomes an attendee\n"
            "\n"
            "## Perimeter\n"
            "\n"
            "- `src/queue/*`\n"
            "- `docs/queue.md`\n"))

    def test_the_text_ends_in_exactly_one_newline(self):
        _, text = self.drafted(self.fields())
        self.assertTrue(text.endswith("`\n"))
        self.assertFalse(text.endswith("\n\n"))

    def test_only_the_title_is_required(self):
        _, text = self.drafted({"title": "Just a title"})
        lines = text.splitlines()
        self.assertEqual(lines[0], "# 0001 — Just a title")
        self.assertIn("- Status: open", lines)
        self.assertEqual([line for line in lines if line.startswith(("- Feature:", "- Priority:"))], [])
        at = lines.index("## Problem")
        self.assertEqual(lines[at + 1:at + 3], ["", "(no context given)"])
        self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))

    def test_empty_context_feature_and_priority_leave_their_lines_out(self):
        _, text = self.drafted(self.fields(context="", feature="", priority=""))
        lines = text.splitlines()
        self.assertEqual([line for line in lines if line.startswith(("- Feature:", "- Priority:"))], [])
        self.assertIn("(no context given)", lines)
        self.assertNotIn("A full room", text)

    def test_no_criterion_and_no_perimeter_leave_empty_sections(self):
        _, text = self.drafted(self.fields(criteria=[], perimeter=[]))
        lines = text.splitlines()
        self.assertEqual([line for line in lines if line.startswith("## ")],
                         ["## Problem", "## Acceptance criteria", "## Perimeter"])
        between = lines[lines.index("## Acceptance criteria") + 1:lines.index("## Perimeter")]
        self.assertEqual([line for line in between if line.strip()], [])
        self.assertEqual([line for line in lines[lines.index("## Perimeter") + 1:] if line.strip()], [])

    def test_the_context_is_kept_line_for_line_under_the_problem(self):
        _, text = self.drafted(self.fields(context="First line.\nSecond line, with a comma."))
        lines = text.splitlines()
        problem = lines[lines.index("## Problem"):lines.index("## Acceptance criteria")]
        self.assertIn("First line.", problem)
        self.assertIn("Second line, with a comma.", problem)
        self.assertLess(problem.index("First line."), problem.index("Second line, with a comma."))

    def test_each_criterion_is_three_lines_and_a_blank_line_apart(self):
        _, text = self.drafted(self.fields())
        lines = text.splitlines()
        block = lines[lines.index("## Acceptance criteria") + 2:lines.index("## Perimeter") - 1]
        self.assertEqual([line.split(" ", 1)[0] for line in block],
                         ["Given", "When", "Then", "", "Given", "When", "Then"])

    def test_every_path_is_a_backticked_list_item_in_order(self):
        _, text = self.drafted(self.fields(perimeter=["b/*.py", "a/x.py", "README.md"]))
        lines = text.splitlines()
        self.assertEqual(lines[lines.index("## Perimeter") + 2:], ["- `b/*.py`", "- `a/x.py`", "- `README.md`"])

    def test_feature_and_priority_are_written_verbatim_for_the_gate_to_judge(self):
        code, _, err = self.call(self.fields(feature="Not A Slug", priority="urgent"))
        self.assertEqual((code, err), (0, ""))
        text = (self.tickets / "0001.md").read_text()
        self.assertIn("- Feature: Not A Slug\n", text)
        self.assertIn("- Priority: urgent\n", text)

    def test_text_that_is_not_ascii_is_kept(self):
        _, text = self.drafted(self.fields(title="Più posti", context="Café — à la carte"))
        self.assertIn("Più posti", text.splitlines()[0])
        self.assertIn("Café — à la carte", text)

    # --- the gate judges the draft ----------------------------------------

    def judged(self, **change):
        """The gate's reason for the draft of these fields, or None."""
        _, text = self.drafted(self.fields(**change))
        return spec.check(text)

    def test_a_draft_of_good_fields_passes_the_gate(self):
        self.assertIsNone(self.judged())

    def test_a_title_only_draft_does_not_pass_the_gate(self):
        _, text = self.drafted({"title": "Just a title"})
        self.assertIsNotNone(spec.check(text))

    def test_the_gate_passes_it_through_its_command_line_too(self):
        ticket, _ = self.drafted(self.fields())
        proc = self.cli("check", str(self.tickets / f"{ticket}.md"))
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_no_criterion_fails(self):
        self.assertIn("has no criterion", self.judged(criteria=[]))

    def test_a_then_with_no_outcome_fails(self):
        self.assertIsNotNone(self.judged(criteria=[{"given": "a room", "when": "someone signs up", "then": ""}]))

    def test_a_vague_outcome_fails_and_is_named(self):
        why = self.judged(criteria=[{"given": "a room", "when": "someone signs up", "then": "it works"}])
        self.assertIn("names no observable outcome", why)

    def test_no_perimeter_path_fails(self):
        self.assertIn("declares no path", self.judged(perimeter=[]))

    def test_a_bad_feature_fails_and_is_named(self):
        for bad in ("Waiting List", "waiting--list", "-x", "waiting_list"):
            why = self.judged(feature=bad)
            self.assertIsNotNone(why, bad)
            self.assertIn("Feature", why)

    def test_a_bad_priority_fails_and_is_named(self):
        for bad in ("urgent", "P4", "p1", "high"):
            why = self.judged(priority=bad)
            self.assertIsNotNone(why, bad)
            self.assertIn("Priority", why)

    def test_every_good_feature_and_priority_passes(self):
        for priority in ("P0", "P1", "P2", "P3"):
            self.assertIsNone(self.judged(priority=priority), priority)
        for feature in ("venues", "waiting-list", "v2", "a1-b2-c3"):
            self.assertIsNone(self.judged(feature=feature), feature)

    # --- bad fields --------------------------------------------------------

    def refused(self, fields):
        code, stdout, stderr = self.call(fields)
        self.assertEqual((code, stdout), (1, ""), stderr)
        self.assertTrue(stderr.startswith("spec: "), stderr)
        self.assertEqual(len(stderr.strip().splitlines()), 1, stderr)
        self.assertEqual(self.listing(), [], "a refused draft wrote something")

    def test_no_title_is_refused(self):
        self.refused(self.fields(title=DROP))

    def test_an_empty_or_blank_title_is_refused(self):
        for title in ("", "   ", "\t\n"):
            self.refused(self.fields(title=title))

    def test_a_title_that_is_not_a_string_is_refused(self):
        for title in (5, None, ["a"], {"a": "b"}):
            self.refused(self.fields(title=title))

    def test_criteria_that_are_not_a_list_of_objects_are_refused(self):
        for criteria in ("Given a, when b, then c", {"given": "a", "when": "b", "then": "c"},
                         ["Given a, when b, then c"], [1], [None], [["a", "b", "c"]]):
            self.refused(self.fields(criteria=criteria))

    def test_a_perimeter_that_is_not_a_list_of_strings_is_refused(self):
        for perimeter in ("src/*", {"a": "b"}, ["src/*", 3], [None], [["src/*"]]):
            self.refused(self.fields(perimeter=perimeter))

    def test_fields_that_are_not_an_object_are_refused(self):
        for fields in ([], "title", None, ["title"]):
            self.refused(json.dumps(fields))

    def test_a_missing_fields_file_is_refused(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = spec.main(["draft", str(self.dir / "absent.json"), str(self.tickets)], {})
        self.assertEqual((code, stdout.getvalue()), (1, ""))
        self.assertTrue(stderr.getvalue().startswith("spec: "), stderr.getvalue())
        self.assertEqual(self.listing(), [])

    def test_a_file_that_is_not_json_writes_nothing_and_fails(self):
        fields = self.write_fields("{not json")
        proc = self.cli("draft", str(fields), str(self.tickets))
        self.assertEqual((proc.returncode, proc.stdout), (1, ""))
        self.assertEqual(self.listing(), [])

    def test_the_usage_is_exit_two(self):
        for argv in (["draft"], ["draft", str(self.dir / "fields.json")]):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(spec.main(argv, {}), 2)
        self.assertEqual(self.listing(), [])

    # --- the command line the console runs ---------------------------------

    def test_the_command_line_is_python3_core_spec_py_draft(self):
        fields = self.write_fields(self.FIELDS)
        out = self.dir / "cli-out"
        out.mkdir()
        (self.tickets / "0012.md").write_text("# t\n")
        done = self.cli("draft", str(fields), str(self.tickets), str(out))
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "0013\n", ""))
        self.assertEqual(self.listing(out), ["0013.md"])
        self.assertEqual(self.listing(), ["0012.md"])
        fields = self.write_fields({"context": "no title"})
        refused = self.cli("draft", str(fields), str(self.tickets), str(out))
        self.assertEqual((refused.returncode, refused.stdout), (1, ""))
        self.assertTrue(refused.stderr.startswith("spec: "), refused.stderr)
        self.assertEqual(self.listing(out), ["0013.md"])


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
