"""Tests for the delivery measures, written from docs/adr/0082, never from
the implementation: the ADR's fixture logbook and its hand-computed values.
"""

import copy
import json
import os
import subprocess  # nosec B404 - the command under test is a script
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from core import dora

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NOW = "2026-11-30T00:00:00Z"


def ticket(tid, step, at):
    return {"id": tid, "history": [{"step": step, "state": "x", "at": at}]}


def release(version, tid, at, verdict, started, answer=None, answer_at=None):
    stages = [{"pct": 5, "verdict": "GO"}, {"pct": 25, "verdict": verdict}]
    if started:
        stages[-1]["started_at"] = started
    return {"version": version, "ticket": tid, "at": at, "verdict": verdict, "stages": stages,
            "answer": {"answer": answer, "by": "someone", "via": "cli", "at": answer_at} if answer else None,
            "from": "releases.jsonl" if at else "release.json"}


FIXTURE = {
    "tickets": [
        ticket("0101", "request", "2026-11-10T08:00:00Z"),
        ticket("0102", "open", "2026-11-11T09:00:00Z"),
        ticket("0103", "request", "2026-11-12T10:00:00Z"),
        ticket("0104", "request", "2026-10-01T00:00:00Z"),
    ],
    "releases": [
        release("1.1.0", "0101", "2026-11-10T12:00:00Z", "held", "2026-11-10T11:55:00Z", "GO", "2026-11-10T14:00:00Z"),
        release("1.2.0", "0102", "2026-11-11T12:00:00Z", "rolled-back", "2026-11-11T11:58:00Z"),
        release("1.2.1", "0102", "2026-11-12T12:00:00Z", "held", "2026-11-12T11:55:00Z", "GO", "2026-11-12T13:00:00Z"),
        release("1.3.0", "0103", "2026-11-13T12:00:00Z", "held", "2026-11-13T11:50:00Z", "NO-GO", "2026-11-13T12:30:00Z"),
        release("1.4.0", None, "2026-11-14T12:00:00Z", "held", "2026-11-14T11:55:00Z"),
        release("1.4.1", None, "2026-11-15T10:00:00Z", "held", "2026-11-15T09:55:00Z", "GO", "2026-11-15T11:00:00Z"),
        release("1.0.0", "0104", "2026-10-02T00:00:00Z", "rolled-back", "2026-10-01T23:58:00Z"),
        release("1.4.2", None, None, "held", None),
    ],
}


class Fixture(unittest.TestCase):
    """§3 and the ADR's table: every measure, by hand."""

    def setUp(self):
        self.got = dora.measures(copy.deepcopy(FIXTURE), 30, NOW)

    def test_the_window(self):
        self.assertEqual((self.got["window_days"], self.got["from"], self.got["to"]),
                         (30, "2026-10-31T00:00:00Z", NOW))
        self.assertEqual(self.got["schema"], "dora/1")

    def test_deployment_frequency(self):
        m = self.got["measures"]["deployment_frequency"]
        self.assertTrue(m["measured"])
        self.assertEqual(m["count"], 3)
        self.assertAlmostEqual(m["per_day"], 0.1)

    def test_lead_time(self):
        m = self.got["measures"]["lead_time"]
        self.assertTrue(m["measured"])
        self.assertEqual((m["median_s"], m["n"], m["without_ticket"]), (61200, 2, 1))

    def test_change_fail_rate(self):
        m = self.got["measures"]["change_fail_rate"]
        self.assertTrue(m["measured"])
        self.assertEqual((m["failed"], m["decided"], m["pending"]), (2, 5, 1))
        self.assertAlmostEqual(m["rate"], 0.4)

    def test_recovery_time(self):
        m = self.got["measures"]["recovery_time"]
        self.assertTrue(m["measured"])
        self.assertEqual((m["median_s"], m["n"], m["unmeasured"]), (1260, 2, 0))


class NotMeasured(unittest.TestCase):
    """§4: never estimated, always the reason."""

    def test_no_started_at_leaves_recovery_unmeasured_and_the_rest_unchanged(self):
        book = copy.deepcopy(FIXTURE)
        for r in book["releases"]:
            for s in r["stages"]:
                s.pop("started_at", None)
        got = dora.measures(book, 30, NOW)["measures"]
        self.assertFalse(got["recovery_time"]["measured"])
        self.assertIn("started_at", got["recovery_time"]["why"])
        self.assertEqual(got["deployment_frequency"]["count"], 3)
        self.assertEqual(got["lead_time"]["median_s"], 61200)
        self.assertAlmostEqual(got["change_fail_rate"]["rate"], 0.4)

    def test_an_empty_logbook_measures_only_the_frequency_at_zero(self):
        got = dora.measures({"tickets": [], "releases": []}, 30, NOW)["measures"]
        self.assertTrue(got["deployment_frequency"]["measured"])
        self.assertEqual(got["deployment_frequency"]["count"], 0)
        self.assertEqual(got["deployment_frequency"]["per_day"], 0)
        for key in ("lead_time", "change_fail_rate", "recovery_time"):
            self.assertFalse(got[key]["measured"], key)
            self.assertTrue(got[key]["why"], key)

    def test_unread_releases_leave_all_four_unmeasured_with_the_error(self):
        book = dict(copy.deepcopy(FIXTURE), releases={"ok": False, "error": "x-unreadable"})
        got = dora.measures(book, 30, NOW)["measures"]
        for key in ("deployment_frequency", "lead_time", "change_fail_rate", "recovery_time"):
            self.assertFalse(got[key]["measured"], key)
            self.assertIn("x-unreadable", got[key]["why"], key)


class Window(unittest.TestCase):
    def test_one_day_ending_after_the_no_go(self):
        got = dora.measures(copy.deepcopy(FIXTURE), 1, "2026-11-13T12:30:00Z")["measures"]
        self.assertEqual(got["deployment_frequency"]["count"], 1)
        self.assertAlmostEqual(got["deployment_frequency"]["per_day"], 1.0)
        self.assertEqual((got["lead_time"]["median_s"], got["lead_time"]["n"]), (100800, 1))
        self.assertAlmostEqual(got["change_fail_rate"]["rate"], 1.0)
        self.assertEqual(got["recovery_time"]["median_s"], 2400)

    def test_an_answer_after_the_end_is_not_given_yet(self):
        got = dora.measures(copy.deepcopy(FIXTURE), 1, "2026-11-13T12:15:00Z")["measures"]
        self.assertFalse(got["change_fail_rate"]["measured"])


class Command(unittest.TestCase):
    """§5: core/dora.sh keeps the gate contract."""

    def run_cmd(self, **env):
        full = dict(os.environ, **env)
        full.pop("NOGO_DETAILS", None)
        return subprocess.run(["sh", "core/dora.sh"], cwd=REPO, env=full, capture_output=True, text=True,
                              check=False)  # nosec B603 B607 - a fixed argv

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        # Dates relative to the real clock: the command's window ends now.
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        book = {"tickets": [ticket("0101", "request", recent)],
                "releases": [release("1.0.0", "0101", recent, "held", recent, "GO", recent)]}
        self.book = os.path.join(self.tmp, "logbook.json")
        with open(self.book, "w", encoding="utf-8") as fh:
            json.dump(book, fh)
        self.out = os.path.join(self.tmp, "dora.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_one_go_line_and_the_file(self):
        ran = self.run_cmd(DORA_LOGBOOK=self.book, DORA_OUT=self.out, WINDOW_DAYS="30")
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(len(ran.stdout.splitlines()), 1, ran.stdout)
        self.assertTrue(ran.stdout.startswith("GO: dora — "), ran.stdout)
        with open(self.out, encoding="utf-8") as fh:
            written = json.load(fh)
        self.assertEqual(written["measures"]["deployment_frequency"]["count"], 1)

    def test_a_missing_logbook_is_one_no_go_line(self):
        ran = self.run_cmd(DORA_LOGBOOK=os.path.join(self.tmp, "absent.json"), DORA_OUT=self.out)
        self.assertEqual(ran.returncode, 1)
        self.assertEqual(len(ran.stdout.splitlines()), 1, ran.stdout)
        self.assertTrue(ran.stdout.startswith("NO-GO: dora — "), ran.stdout)

    def test_a_window_that_is_not_a_whole_number_is_refused_by_name(self):
        for bad in ("0", "x", "1.5"):
            ran = self.run_cmd(DORA_LOGBOOK=self.book, DORA_OUT=self.out, WINDOW_DAYS=bad)
            self.assertEqual(ran.returncode, 1, bad)
            self.assertEqual(len(ran.stdout.splitlines()), 1, ran.stdout)
            self.assertIn("WINDOW_DAYS", ran.stdout)


if __name__ == "__main__":
    unittest.main()
