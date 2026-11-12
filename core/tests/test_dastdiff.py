"""Tests for core/dastdiff.py, written from docs/adr/0072 decision 3 and
docs/adr/0052 §2, never from the implementation.

The module is exercised through its CLI, the only contract the spec gives:

  dastdiff.py diff <stable-report> <canary-report>
      Each report is ZAP's traditional JSON report. An alert is the tuple
      (pluginid, method, path of the uri without query, scheme and host),
      one per instance, compared as a set, at every risk level.
      exit 0, stdout `<m>`: no new tuple, m inherited tuples.
      exit 1, stdout `<n>`: n new tuples, each listed on stderr.
      exit 2, one-line reason on stdout naming `stable` or `canary`: a side
      cannot be read. Wrong usage also exits 2.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "core", "dastdiff.py")


def cli(*args):
    """Run the CLI from the repository root: (exit code, stdout, stderr)."""
    p = subprocess.run(  # noqa: S603  # nosec B603 - fixed argv, no shell
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        cwd=ROOT,
        check=False,
    )
    return p.returncode, p.stdout.decode(), p.stderr.decode()


def alert(pluginid, *instances, risk="1", name="An alert"):
    """A ZAP alert; instances are (method, uri) pairs."""
    return {
        "pluginid": pluginid,
        "alert": name,
        "riskcode": risk,
        "instances": [{"uri": u, "method": m} for m, u in instances],
    }


def report(*alerts, host="http://stable.test"):
    """A ZAP report with one site holding the alerts."""
    return {"site": [{"@name": host, "alerts": list(alerts)}]}


class Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name

    def raw(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def js(self, name, obj):
        return self.raw(name, json.dumps(obj))

    def diff(self, stable, canary):
        """Diff two report objects."""
        return cli("diff", self.js("stable.json", stable), self.js("canary.json", canary))

    def assertVerdict(self, got, code, count):
        rc, out, _ = got
        self.assertEqual(rc, code)
        self.assertEqual(out, f"{count}\n")


class Verdict(Tmp):
    def test_identical_reports_are_clean_with_the_count(self):
        r = report(alert("10020", ("GET", "http://h/a")), alert("10021", ("GET", "http://h/b")))
        self.assertVerdict(self.diff(r, r), 0, 2)

    def test_canary_adds_a_plugin(self):
        s = report(alert("10020", ("GET", "http://h/a")))
        c = report(alert("10020", ("GET", "http://h/a")), alert("10038", ("GET", "http://h/a")))
        rc, out, err = self.diff(s, c)
        self.assertEqual((rc, out), (1, "1\n"))
        self.assertIn("10038", err)
        self.assertIn("GET", err)
        self.assertIn("/a", err)

    def test_same_plugin_on_a_new_path_is_new(self):
        s = report(alert("10020", ("GET", "http://h/a")))
        c = report(alert("10020", ("GET", "http://h/a"), ("GET", "http://h/b")))
        rc, out, err = self.diff(s, c)
        self.assertEqual((rc, out), (1, "1\n"))
        self.assertIn("10020", err)
        self.assertIn("/b", err)

    def test_same_plugin_and_path_with_another_method_is_new(self):
        s = report(alert("10020", ("GET", "http://h/a")))
        c = report(alert("10020", ("POST", "http://h/a")))
        rc, out, err = self.diff(s, c)
        self.assertEqual((rc, out), (1, "1\n"))
        self.assertIn("POST", err)

    def test_each_new_tuple_is_on_its_own_stderr_line(self):
        s = report()
        c = report(alert("10001", ("GET", "http://h/x")), alert("10002", ("GET", "http://h/y")))
        rc, out, err = self.diff(s, c)
        self.assertEqual((rc, out), (1, "2\n"))
        lines = [ln for ln in err.splitlines() if ln.strip()]
        self.assertTrue(any("10001" in ln and "/x" in ln for ln in lines))
        self.assertTrue(any("10002" in ln and "/y" in ln for ln in lines))

    def test_query_strings_are_ignored(self):
        s = report(alert("10020", ("GET", "http://h/a?x=1")))
        c = report(alert("10020", ("GET", "http://h/a?y=2")))
        self.assertVerdict(self.diff(s, c), 0, 1)

    def test_hosts_and_ports_are_ignored(self):
        s = report(
            alert("10020", ("GET", "http://stable.test:8080/a")), host="http://stable.test:8080"
        )
        c = report(alert("10020", ("GET", "https://canary.test/a")), host="https://canary.test")
        self.assertVerdict(self.diff(s, c), 0, 1)

    def test_empty_path_equals_slash(self):
        s = report(alert("10020", ("GET", "http://stable.test")))
        c = report(alert("10020", ("GET", "http://canary.test/")))
        self.assertVerdict(self.diff(s, c), 0, 1)

    def test_empty_path_with_query_equals_slash(self):
        s = report(alert("10020", ("GET", "http://stable.test?x=1")))
        c = report(alert("10020", ("GET", "http://canary.test:81/")))
        self.assertVerdict(self.diff(s, c), 0, 1)

    def test_informational_risk_counts(self):
        c = report(alert("10094", ("GET", "http://h/a"), risk="0"))
        self.assertVerdict(self.diff(report(), c), 1, 1)

    def test_every_risk_level_counts(self):
        for risk in ("0", "1", "2", "3"):
            with self.subTest(risk=risk):
                c = report(alert("10020", ("GET", "http://h/a"), risk=risk))
                self.assertVerdict(self.diff(report(), c), 1, 1)

    def test_risk_level_is_not_part_of_the_tuple(self):
        s = report(alert("10020", ("GET", "http://h/a"), risk="0"))
        c = report(alert("10020", ("GET", "http://h/a"), risk="3"))
        self.assertVerdict(self.diff(s, c), 0, 1)

    def test_duplicate_canary_instances_count_once_in_inherited(self):
        s = report(alert("10020", ("GET", "http://h/a")))
        c = report(
            alert(
                "10020",
                ("GET", "http://h/a?x=1"),
                ("GET", "http://h/a?y=2"),
                ("GET", "http://h/a"),
            )
        )
        self.assertVerdict(self.diff(s, c), 0, 1)

    def test_duplicate_canary_instances_count_once_in_new(self):
        c = report(alert("10020", ("GET", "http://h/a?x=1"), ("GET", "http://h/a?y=2")))
        self.assertVerdict(self.diff(report(), c), 1, 1)

    def test_duplicates_across_alerts_and_sites_count_once(self):
        c = {
            "site": [
                {
                    "alerts": [
                        alert("10020", ("GET", "http://h/a")),
                        alert("10020", ("GET", "http://h/a")),
                    ]
                },
                {"alerts": [alert("10020", ("GET", "http://other/a"))]},
            ]
        }
        self.assertVerdict(self.diff(report(), c), 1, 1)

    def test_stable_only_tuples_are_neither_new_nor_inherited(self):
        s = report(alert("10020", ("GET", "http://h/a")), alert("10021", ("GET", "http://h/gone")))
        c = report(alert("10020", ("GET", "http://h/a")))
        self.assertVerdict(self.diff(s, c), 0, 1)

    def test_only_stable_tuples_leaves_zero(self):
        s = report(alert("10020", ("GET", "http://h/a")))
        self.assertVerdict(self.diff(s, report()), 0, 0)

    def test_exit_1_prints_only_the_new_count(self):
        s = report(alert("10020", ("GET", "http://h/a")))
        c = report(alert("10020", ("GET", "http://h/a")), alert("10021", ("GET", "http://h/b")))
        self.assertVerdict(self.diff(s, c), 1, 1)

    def test_empty_reports(self):
        self.assertVerdict(self.diff(report(), report()), 0, 0)
        self.assertVerdict(self.diff({"site": []}, {"site": []}), 0, 0)

    def test_empty_stable_with_alerting_canary(self):
        c = report(alert("10020", ("GET", "http://h/a")))
        self.assertVerdict(self.diff({"site": []}, c), 1, 1)

    def test_extra_report_fields_are_tolerated(self):
        r = report(alert("10020", ("GET", "http://h/a")))
        r["@programName"] = "ZAP"
        r["@version"] = "2.17.0"
        self.assertVerdict(self.diff(r, r), 0, 1)


GOOD = report(alert("10020", ("GET", "http://h/a")))

# Each case is a name and the text of an unreadable report.
BAD_REPORTS = {
    "empty file": "",
    "not json": "<html>not json</html>",
    "json array": "[]",
    "json string": '"x"',
    "json null": "null",
    "no site": "{}",
    "site not a list": json.dumps({"site": {}}),
    "alert without pluginid": json.dumps(
        {"site": [{"alerts": [{"alert": "x", "riskcode": "1", "instances": []}]}]}
    ),
    "instances not a list": json.dumps(
        {"site": [{"alerts": [{"pluginid": "1", "alert": "x", "riskcode": "1", "instances": "no"}]}]}
    ),
    "alert without instances": json.dumps(
        {"site": [{"alerts": [{"pluginid": "1", "alert": "x", "riskcode": "1"}]}]}
    ),
    "instance without uri": json.dumps(
        {
            "site": [
                {
                    "alerts": [
                        {
                            "pluginid": "1",
                            "alert": "x",
                            "riskcode": "1",
                            "instances": [{"method": "GET"}],
                        }
                    ]
                }
            ]
        }
    ),
}


class Unreadable(Tmp):
    def check_side(self, side, text):
        good = self.js("good.json", GOOD)
        bad = self.raw("bad.json", text)
        args = (good, bad) if side == "canary" else (bad, good)
        rc, out, _ = cli("diff", *args)
        self.assertEqual(rc, 2)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertIn(side, out)

    def test_each_unreadable_shape_on_each_side(self):
        for side in ("stable", "canary"):
            for name, text in BAD_REPORTS.items():
                with self.subTest(side=side, shape=name):
                    self.check_side(side, text)

    def test_missing_file_on_each_side(self):
        good = self.js("good.json", GOOD)
        gone = os.path.join(self.tmp, "does-not-exist.json")
        for side, args in (("stable", (gone, good)), ("canary", (good, gone))):
            with self.subTest(side=side):
                rc, out, _ = cli("diff", *args)
                self.assertEqual(rc, 2)
                self.assertEqual(len(out.splitlines()), 1)
                self.assertIn(side, out)

    def test_both_sides_unreadable_still_exits_2(self):
        bad = self.raw("bad.json", "")
        rc, out, _ = cli("diff", bad, bad)
        self.assertEqual(rc, 2)
        self.assertEqual(len(out.splitlines()), 1)

    def test_unreadable_canary_is_never_a_verdict(self):
        # A canary that cannot be read must not look like "nothing new".
        stable = self.js("stable.json", GOOD)
        canary = self.raw("canary.json", "{}")
        rc, out, _ = cli("diff", stable, canary)
        self.assertNotEqual(rc, 0)
        self.assertNotRegex(out.strip(), r"^\d+$")


class Usage(Tmp):
    def test_no_arguments(self):
        self.assertEqual(cli()[0], 2)

    def test_unknown_subcommand(self):
        r = self.js("r.json", GOOD)
        self.assertEqual(cli("frobnicate", r, r)[0], 2)

    def test_diff_with_missing_operands(self):
        r = self.js("r.json", GOOD)
        self.assertEqual(cli("diff")[0], 2)
        self.assertEqual(cli("diff", r)[0], 2)


if __name__ == "__main__":
    unittest.main()
