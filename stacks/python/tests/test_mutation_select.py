"""The python runner's test selection (docs/adr/0076).

Written from the ADR: the clean run records which test executes which
line, each mutant runs the tests that executed its statement, nothing when
none did, the whole suite when a line ran outside any test or coverage is
missing; the score line and the survivors are the whole suite's, with one
shard and with three. Runs the real runner, cosmic-ray included, on a
package made here.
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "runners" / "mutation.sh"

# add and clamp are tested in-process; is_positive by nothing; double only
# through a subprocess that sets its own PYTHONPATH; LIMIT is read at
# import time by a test.
CALC = """\
LIMIT = 10


def add(a, b):
    return a + b


def is_positive(x):
    return x > 0


def clamp(x, low, high):
    if x < low:
        return low
    if x > high:
        return high
    return x


def double(x):
    return x * 2
"""

TESTS = """\
import os
import subprocess
import sys
import unittest
from pathlib import Path

from pkg import calc

ROOT = Path(__file__).resolve().parents[1]


class T(unittest.TestCase):
    def setUp(self):
        runs = os.environ.get("CALC_RUNS")
        if runs:
            with open(runs, "a") as f:
                f.write(self.id() + "\\n")

    def test_add(self):
        self.assertEqual(calc.add(2, 3), 5)

    def test_clamp(self):
        self.assertEqual(calc.clamp(-1, 0, 9), 0)
        self.assertEqual(calc.clamp(10, 0, 9), 9)
        self.assertEqual(calc.clamp(0, 0, 9), 0)
        self.assertEqual(calc.clamp(9, 0, 9), 9)
        self.assertEqual(calc.clamp(4, 0, 9), 4)

    def test_limit(self):
        self.assertEqual(calc.LIMIT, 10)

    def test_double_in_a_subprocess(self):
        p = subprocess.run(
            [sys.executable, "-c", "from pkg.calc import double; print(double(21))"],
            cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT)),
            capture_output=True, text=True, check=False)
        self.assertEqual(p.stdout.strip(), "42", p.stderr)
"""

SUITE = "python3 -m unittest discover -s tests -t ."
COUNTS = re.compile(r"mutation\.sh: (\d+) mutants ran no test, (\d+) a selection, (\d+) the whole suite")


def run(cwd, select=None, shards="1", suite=SUITE, runs=None):
    env = dict(os.environ, MUTATION_SHARDS=shards)
    for key in ("MUTATION_LINES", "MUTATION_SELECT", "CALC_RUNS"):
        env.pop(key, None)
    if select is not None:
        env["MUTATION_SELECT"] = select
    if runs is not None:
        env["CALC_RUNS"] = str(runs)
    return subprocess.run(["sh", str(RUNNER), "pkg", suite], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=1800)


def score(result):
    return result.stdout.strip().splitlines()[-1]


def survivors(result):
    return sorted(l for l in result.stderr.splitlines() if l.startswith("SURVIVOR "))


class Selection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="mutation-select-")
        root = Path(cls.tmp.name) / "repo"
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "__init__.py").write_text("")
        (root / "pkg" / "calc.py").write_text(CALC)
        (root / "tests").mkdir()
        (root / "tests" / "__init__.py").write_text("")
        (root / "tests" / "test_calc.py").write_text(TESTS)
        cls.root = root
        logs = Path(cls.tmp.name)
        cls.whole_runs, cls.select_runs = logs / "whole.runs", logs / "select.runs"
        cls.whole = run(root, select="off", runs=cls.whole_runs)
        cls.one = run(root, runs=cls.select_runs)
        cls.three = run(root, shards="3")
        # -S: no site, so no sitecustomize. Not -I, which also ignores
        # cosmic-ray's PYTHONDONTWRITEBYTECODE and lets stale bytecode hide mutants.
        cls.siteless = run(root, suite="python3 -S -m unittest discover -s tests -t .")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def ok(self, result):
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def counts(self, result):
        m = COUNTS.search(result.stderr)
        self.assertIsNotNone(m, result.stderr[-3000:])
        return tuple(int(n) for n in m.groups())

    def test_the_whole_suite_scores_killed_and_survived(self):
        self.ok(self.whole)
        line = json.loads(score(self.whole))
        self.assertGreater(line["killed"], 0)
        self.assertGreater(line["survived"], 0)
        self.assertIn("every mutant runs the whole suite", self.whole.stderr)

    def test_selection_gives_the_whole_suites_score_line(self):
        self.ok(self.one)
        self.assertEqual(score(self.one), score(self.whole))

    def test_selection_gives_the_whole_suites_survivors(self):
        self.assertEqual(survivors(self.one), survivors(self.whole))

    def test_three_shards_with_selection_give_the_same_score_and_survivors(self):
        self.ok(self.three)
        self.assertIn("in 3 shards", self.three.stderr)
        self.assertEqual(score(self.three), score(self.whole))
        self.assertEqual(survivors(self.three), survivors(self.whole))
        self.assertEqual(self.counts(self.three), self.counts(self.one))

    def test_a_function_no_test_calls_runs_no_test_and_survives(self):
        none, _, _ = self.counts(self.one)
        self.assertGreater(none, 0)
        lines = {s.split()[1].rsplit(":", 1)[1] for s in survivors(self.one)}
        self.assertIn("9", lines)  # is_positive's `return x > 0`

    def test_a_function_only_a_subprocess_reaches_is_killed(self):
        lines = {s.split()[1].rsplit(":", 1)[1] for s in survivors(self.one)}
        self.assertNotIn("21", lines)  # double's `return x * 2`
        _, selected, _ = self.counts(self.one)
        self.assertGreater(selected, 0)

    def test_a_module_constant_runs_the_whole_suite(self):
        _, _, whole = self.counts(self.one)
        self.assertGreater(whole, 0)
        lines = {s.split()[1].rsplit(":", 1)[1] for s in survivors(self.one)}
        self.assertNotIn("1", lines)  # LIMIT = 10

    def test_selection_runs_fewer_tests_than_the_whole_suite(self):
        whole = self.whole_runs.read_text().splitlines()
        selected = self.select_runs.read_text().splitlines()
        self.assertLess(len(selected), len(whole))

    def test_an_interpreter_without_site_has_no_coverage_and_runs_the_whole_suite(self):
        self.ok(self.siteless)
        self.assertIn("no per-test coverage", self.siteless.stderr)
        self.assertEqual(score(self.siteless), score(self.whole))
        self.assertEqual(survivors(self.siteless), survivors(self.whole))

    def test_the_package_is_left_as_it_was(self):
        self.assertEqual((self.root / "pkg" / "calc.py").read_text(), CALC)

    def test_a_select_value_that_is_not_on_or_off_is_refused(self):
        result = run(self.root, select="maybe")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MUTATION_SELECT=maybe is not on or off", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
