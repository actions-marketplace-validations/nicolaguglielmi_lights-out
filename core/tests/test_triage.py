"""Tests for core/triage.py, written from docs/adr/0020 §3 (the incident
artefact and the three refusals), never from the implementation.

Each test writes an alert and the role's out directory (calls.json,
run.json) in a temp dir and runs the judge in-process. The toolset is the
ADR's: file_incident(title, hypotheses:[{rank, cause, evidence}]),
propose_rollback(version, reason), propose_hold(reason).
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from core import triage

ALERT = {"headline": "canary error rate 1.0", "version": "0.2.0-canary", "stable": "0.1.0",
         "stage": {"pct": 5, "verdict": "NO-GO: slo", "numbers": ["slo: error_rate 1.0"]}}
RUN = {"provider": "gemini", "model": "m-1"}
HYPOTHESES = [{"rank": 2, "cause": "a slow database", "evidence": "stable is fine"},
              {"rank": 1, "cause": "the canary's change", "evidence": "only the canary fails"}]


def file_incident(hypotheses=HYPOTHESES, title="Canary fails"):
    return {"name": "file_incident", "args": {"title": title, "hypotheses": hypotheses}}


def rollback(version="0.2.0-canary"):
    return {"name": "propose_rollback", "args": {"version": version, "reason": "it is the canary"}}


HOLD = {"name": "propose_hold", "args": {"reason": "stable fails too"}}


class TriageCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        (self.dir / "out").mkdir()
        self.alert = self.dir / "real-alert.json"
        self.alert.write_text(json.dumps(ALERT))
        self.incident = self.dir / "incident.json"

    def tearDown(self):
        self._tmp.cleanup()

    def run_check(self, calls, run=RUN):
        out_dir = self.dir / "out"
        if calls is not None:
            (out_dir / "calls.json").write_text(calls if isinstance(calls, str) else json.dumps(calls))
        if run is not None:
            (out_dir / "run.json").write_text(json.dumps(run))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = triage.main(["check", str(self.alert), str(out_dir), str(self.incident)])
        return code, out.getvalue().strip(), err.getvalue()

    def assertRefused(self, calls, *words, run=RUN):
        code, out, _ = self.run_check(calls, run)
        self.assertEqual(code, 1, out)
        for word in words:
            self.assertIn(word, out)
        self.assertFalse(self.incident.exists(), "a refusal wrote an incident")


class TheIncident(TriageCase):
    def test_a_rollback_of_the_alerted_version(self):
        code, out, err = self.run_check([file_incident(), rollback()])
        self.assertEqual((code, out), (0, ""))
        doc = json.loads(self.incident.read_text())
        self.assertEqual(list(doc), ["alert", "title", "hypotheses", "proposal", "run"])
        self.assertEqual(doc["alert"], ALERT)
        self.assertEqual(doc["title"], "Canary fails")
        self.assertEqual([h["rank"] for h in doc["hypotheses"]], [1, 2])
        self.assertEqual(doc["hypotheses"][0], HYPOTHESES[1])
        self.assertEqual(doc["proposal"], {"action": "rollback", "version": "0.2.0-canary",
                                           "reason": "it is the canary"})
        self.assertEqual(doc["run"], RUN)
        self.assertIn('[triage] real-alert: incident "Canary fails"', err)
        self.assertLess(err.index("1. the canary's change — only the canary fails"),
                        err.index("2. a slow database — stable is fine"))
        self.assertIn("proposal: rollback 0.2.0-canary — it is the canary", err)
        self.assertIn(f"written to {self.incident}", err)

    def test_a_hold_names_no_version(self):
        code, _, err = self.run_check([file_incident(), HOLD])
        self.assertEqual(code, 0)
        proposal = json.loads(self.incident.read_text())["proposal"]
        self.assertEqual(proposal, {"action": "hold", "version": None, "reason": "stable fails too"})
        self.assertIn("proposal: hold  — stable fails too", err)

    def test_a_hold_may_name_any_version(self):
        hold = {"name": "propose_hold", "args": {"version": "9.9.9", "reason": "r"}}
        self.assertEqual(self.run_check([file_incident(), hold])[0], 0)

    def test_an_untitled_incident_has_an_empty_title(self):
        call = {"name": "file_incident", "args": {"hypotheses": HYPOTHESES}}
        self.assertEqual(self.run_check([call, HOLD])[0], 0)
        self.assertEqual(json.loads(self.incident.read_text())["title"], "")

    def test_the_artefact_is_json_with_a_final_newline(self):
        self.run_check([file_incident(), rollback()])
        self.assertTrue(self.incident.read_text().endswith("}\n"))


class Refusals(TriageCase):
    def test_fewer_than_two_hypotheses(self):
        for hypotheses in ([], [HYPOTHESES[0]], None):
            with self.subTest(n=hypotheses):
                self.assertRefused([file_incident(hypotheses), HOLD],
                                   "at least two ranked hypotheses, got")

    def test_ranks_are_unique_and_present(self):
        for ranks in ((1, 1), (1, None), (None, None), ("1", 2), (True, 2)):
            with self.subTest(ranks=ranks):
                hypotheses = [dict(h, rank=r) for h, r in zip(HYPOTHESES, ranks)]
                self.assertRefused([file_incident(hypotheses), HOLD], "not uniquely ranked")

    def test_a_proposal_needs_an_incident_before_it(self):
        for calls in ([HOLD], [rollback()], [HOLD, file_incident()], [rollback(), file_incident()], []):
            with self.subTest(calls=[c["name"] for c in calls]):
                self.assertRefused(calls, "expected file_incident then one proposal, got:")

    def test_exactly_one_proposal(self):
        self.assertRefused([file_incident(), HOLD, rollback()], "got: file_incident propose_hold propose_rollback")
        self.assertRefused([file_incident()], "got: file_incident")
        self.assertRefused([], "got: nothing")

    def test_a_rollback_of_another_version(self):
        self.assertRefused([file_incident(), rollback("0.1.0")],
                           'rollback proposed for "0.1.0", the alert is about 0.2.0-canary')
        self.assertRefused([file_incident(), rollback(None)], 'rollback proposed for ""')

    def test_no_calls(self):
        self.assertRefused(None, "left no calls.json")

    def test_no_run(self):
        self.assertRefused([file_incident(), HOLD], "left no run.json", run=None)

    def test_calls_that_are_not_json_or_not_a_list(self):
        self.assertRefused("{oops", "not JSON")
        self.assertRefused({"name": "file_incident"}, "not a list of calls")


class TheAlert(unittest.TestCase):
    def alert(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(text)
        self.addCleanup(Path(f.name).unlink)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = triage.main(["alert", f.name])
        return code, out.getvalue().strip(), f.name

    def test_an_alert_names_a_version(self):
        self.assertEqual(self.alert(json.dumps(ALERT))[0], 0)
        for text in ('{"headline": "h"}', '{"version": ""}', '{"version": null}', "[1]"):
            with self.subTest(text=text):
                code, out, name = self.alert(text)
                self.assertEqual((code, out), (1, f"{name} names no version"))

    def test_an_alert_is_json(self):
        code, out, name = self.alert("not json")
        self.assertEqual((code, out), (1, f"{name} is not JSON"))

    def test_a_missing_alert(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(triage.main(["alert", "/nonexistent/a.json"]), 1)
        self.assertIn("no alert at /nonexistent/a.json", out.getvalue())

    def test_usage(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(triage.main(["judge"]), 1)
        self.assertIn("usage:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
