"""Tests for core/assign.py, written from docs/adr/0053 §5, never from the
implementation.

Before the tower's `assign` step clones anything, a ticket's `## Perimeter`
is checked against the perimeters held by open tickets, recorded in one
StateStore document, `perimeters/held`. A ticket holds its perimeter while
its own document is in pr-opened, ci-failed, ci-passed, review or
needs-human; an overlap refuses the ticket (exit 1, nothing written), which
then waits at `opened`. The stub ports are file-backed, as in test_tower.py.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from core import assign

ENV = {"TRACKER": "stub-tracker", "STATE_STORE": "stub-state"}

STUBS = {
    "adapters/stub-tracker/get.sh": 'f="tickets/$1.md"\n[ -f "$f" ] || exit 1\ncat "$f"\n',
    "adapters/stub-state/get.sh": '[ ! -f fail-get ] || exit 2\nf="state/$1.$2.json"\n[ -f "$f" ] || exit 1\ncat "$f"\n',
    "adapters/stub-state/put.sh": '[ ! -f fail-put ] || exit 1\ncat > "state/$1.$2.json"\n',
}


def ticket(ticket_id, *globs):
    lines = [f"# {ticket_id} — a ticket", "", "## Problem", "", "- `not/a/glob.py`", ""]
    if globs:
        lines += ["## Perimeter", ""] + [f"- `{g}`" for g in globs] + [""]
    lines += ["## Notes", "", "- `also/not/a/glob.py`", ""]
    return "\n".join(lines)


class Perimeter(unittest.TestCase):
    def test_list_items_of_the_section_backticks_dropped(self):
        text = "## Perimeter\n\n- `svc/a.py`\n- svc/b/*\n-   `svc/c.md`\n\n## Notes\n\n- `x`\n"
        self.assertEqual(assign.perimeter(text), ["svc/a.py", "svc/b/*", "svc/c.md"])

    def test_no_section_is_empty(self):
        self.assertEqual(assign.perimeter("# t\n\n## Notes\n\n- `x`\n"), [])


class Overlaps(unittest.TestCase):
    def test_two_literals_overlap_only_when_equal(self):
        self.assertTrue(assign.overlaps("svc/a.py", "svc/a.py"))
        self.assertFalse(assign.overlaps("svc/a.py", "svc/b.py"))

    def test_a_literal_and_a_glob_overlap_when_the_glob_matches_it(self):
        self.assertTrue(assign.overlaps("svc/backend/tests/test_billing_client.py",
                                        "svc/backend/tests/test_billing_*.py"))
        self.assertTrue(assign.overlaps("svc/backend/tests/test_*.py", "svc/backend/tests/test_x.py"))
        self.assertFalse(assign.overlaps("svc/backend/tests/conftest.py",
                                         "svc/backend/tests/test_billing_*.py"))

    def test_star_crosses_slash(self):
        self.assertTrue(assign.overlaps("svc/*", "svc/backend/orders/db.py"))

    def test_two_globs_with_compatible_prefixes_and_suffixes_overlap(self):
        self.assertTrue(assign.overlaps("svc/*", "svc/backend/*.py"))
        self.assertTrue(assign.overlaps("svc/backend/*.py", "*.py"))
        self.assertTrue(assign.overlaps("*", "docs/*.md"))

    def test_two_globs_with_disjoint_prefixes_do_not(self):
        self.assertFalse(assign.overlaps("svc/*", "docs/*"))

    def test_two_globs_with_disjoint_suffixes_do_not(self):
        self.assertFalse(assign.overlaps("docs/*.md", "docs/*.txt"))

    def test_question_mark_and_classes_are_wildcards(self):
        self.assertTrue(assign.overlaps("svc/a?.py", "svc/ab.py"))
        self.assertTrue(assign.overlaps("svc/[ab].py", "svc/a.py"))
        self.assertFalse(assign.overlaps("svc/[ab].py", "svc/c.py"))

    def test_symmetric(self):
        pairs = [("svc/*", "docs/*"), ("svc/a.py", "svc/*"), ("docs/*.md", "docs/*.txt")]
        for a, b in pairs:
            self.assertEqual(assign.overlaps(a, b), assign.overlaps(b, a), (a, b))


class Holding(unittest.TestCase):
    def test_the_open_unmerged_states_hold(self):
        self.assertEqual(set(assign.HOLDING),
                         {"pr-opened", "ci-failed", "ci-passed", "review", "needs-human"})


class AssignCase(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for path, body in STUBS.items():
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text("set -eu\n" + body)
        (self.root / "state").mkdir()
        (self.root / "tickets").mkdir()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def write_ticket(self, ticket_id, *globs):
        (self.root / "tickets" / f"{ticket_id}.md").write_text(ticket(ticket_id, *globs))

    def set_state(self, ticket_id, state):
        (self.root / "state" / f"tickets.{ticket_id}.json").write_text(
            json.dumps({"id": ticket_id, "state": state}))

    def held(self):
        path = self.root / "state" / "perimeters.held.json"
        return json.loads(path.read_text())["tickets"] if path.exists() else None

    def put_held(self, tickets):
        (self.root / "state" / "perimeters.held.json").write_text(json.dumps({"tickets": tickets}))

    def run_assign(self, ticket_id, env=ENV):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = assign.main([ticket_id], dict(env))
        self.assertEqual(out.getvalue(), "", "assign.py must leave stdout to the step's JSON")
        return code, err.getvalue()


class Claim(AssignCase):
    def test_first_ticket_claims_its_perimeter(self):
        self.write_ticket("0001", "svc/a.py", "svc/tests/test_a.py")
        code, _ = self.run_assign("0001")
        self.assertEqual(code, 0)
        self.assertEqual(self.held(), {"0001": ["svc/a.py", "svc/tests/test_a.py"]})

    def test_disjoint_tickets_both_claim(self):
        self.write_ticket("0001", "svc/a.py")
        self.write_ticket("0002", "docs/*")
        self.assertEqual(self.run_assign("0001")[0], 0)
        self.set_state("0001", "pr-opened")
        self.assertEqual(self.run_assign("0002")[0], 0)
        self.assertEqual(self.held(), {"0001": ["svc/a.py"], "0002": ["docs/*"]})

    def test_an_overlap_with_a_holding_ticket_is_refused_naming_both(self):
        self.write_ticket("0001", "svc/backend/tests/test_billing_*.py")
        self.write_ticket("0002", "svc/backend/tests/test_billing_client.py")
        self.put_held({"0001": ["svc/backend/tests/test_billing_*.py"]})
        self.set_state("0001", "ci-failed")
        code, err = self.run_assign("0002")
        self.assertEqual(code, 1)
        self.assertIn("0002 waits", err)
        self.assertIn("0001", err)
        self.assertIn("svc/backend/tests/test_billing_client.py", err)
        self.assertIn("svc/backend/tests/test_billing_*.py", err)
        self.assertIn("ci-failed", err)
        self.assertEqual(self.held(), {"0001": ["svc/backend/tests/test_billing_*.py"]},
                         "a refused ticket writes nothing")

    def test_every_holding_state_holds(self):
        for state in ("pr-opened", "ci-failed", "ci-passed", "review", "needs-human"):
            self.write_ticket("0001", "svc/a.py")
            self.write_ticket("0002", "svc/a.py")
            self.put_held({"0001": ["svc/a.py"]})
            self.set_state("0001", state)
            self.assertEqual(self.run_assign("0002")[0], 1, state)

    def test_a_merged_or_finished_holder_releases_and_is_dropped(self):
        for state in ("merged", "rolled-back", "held", "opened"):
            self.write_ticket("0002", "svc/a.py")
            self.put_held({"0001": ["svc/a.py"]})
            self.set_state("0001", state)
            code, _ = self.run_assign("0002")
            self.assertEqual(code, 0, state)
            self.assertEqual(self.held(), {"0002": ["svc/a.py"]}, state)

    def test_a_holder_with_no_document_is_dropped(self):
        self.write_ticket("0002", "svc/a.py")
        self.put_held({"0001": ["svc/a.py"]})
        self.assertEqual(self.run_assign("0002")[0], 0)
        self.assertEqual(self.held(), {"0002": ["svc/a.py"]})

    def test_a_ticket_never_waits_for_itself(self):
        self.write_ticket("0001", "svc/a.py", "svc/b.py")
        self.put_held({"0001": ["svc/a.py"]})
        self.set_state("0001", "pr-opened")
        self.assertEqual(self.run_assign("0001")[0], 0)
        self.assertEqual(self.held(), {"0001": ["svc/a.py", "svc/b.py"]})

    def test_a_ticket_without_a_perimeter_is_refused(self):
        self.write_ticket("0003")
        code, err = self.run_assign("0003")
        self.assertEqual(code, 1)
        self.assertIn("## Perimeter", err)
        self.assertIsNone(self.held())

    def test_an_unknown_ticket_is_refused(self):
        code, err = self.run_assign("0404")
        self.assertEqual(code, 1)
        self.assertIn("0404", err)

    def test_a_store_that_does_not_answer_is_refused_not_read_as_empty(self):
        self.write_ticket("0001", "svc/a.py")
        (self.root / "fail-get").touch()
        code, _ = self.run_assign("0001")
        self.assertEqual(code, 1)

    def test_a_failed_write_is_refused(self):
        self.write_ticket("0001", "svc/a.py")
        (self.root / "fail-put").touch()
        self.assertEqual(self.run_assign("0001")[0], 1)

    def test_usage_and_environment(self):
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            self.assertEqual(assign.main([], dict(ENV)), 2)
            self.assertEqual(assign.main(["0001"], {}), 2)


if __name__ == "__main__":
    unittest.main()
