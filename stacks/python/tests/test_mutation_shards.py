"""The python runner's shards (docs/adr/0074, amendment of 2026-11-11).

Written from the amendment: with MUTATION_SHARDS=n the runner deals the
pending mutants to n shards and the score line and the survivors are the
ones a single shard gives; a shard count that is not a positive integer is
refused. Runs the real runner, cosmic-ray included, on a package made here.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "runners" / "mutation.sh"

CALC = """\
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
"""

# add and clamp are tested, is_positive is not: its mutants survive.
TESTS = """\
import unittest

from pkg.calc import add, clamp


class T(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_clamp(self):
        self.assertEqual(clamp(-1, 0, 9), 0)
        self.assertEqual(clamp(10, 0, 9), 9)
        self.assertEqual(clamp(0, 0, 9), 0)
        self.assertEqual(clamp(9, 0, 9), 9)
        self.assertEqual(clamp(4, 0, 9), 4)
"""


def run(cwd, shards):
    env = dict(os.environ, MUTATION_SHARDS=shards)
    env.pop("MUTATION_LINES", None)
    return subprocess.run(
        ["sh", str(RUNNER), "pkg", "python3 -m unittest discover -s tests -t ."],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=900,
    )


class Shards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="mutation-shards-")
        root = Path(cls.tmp.name)
        (root / "pkg").mkdir()
        (root / "pkg" / "__init__.py").write_text("")
        (root / "pkg" / "calc.py").write_text(CALC)
        (root / "tests").mkdir()
        (root / "tests" / "__init__.py").write_text("")
        (root / "tests" / "test_calc.py").write_text(TESTS)
        cls.root = root
        cls.one = run(root, "1")
        cls.three = run(root, "3")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def survivors(self, result):
        return sorted(l for l in result.stderr.splitlines() if l.startswith("SURVIVOR "))

    def test_one_shard_scores(self):
        self.assertEqual(self.one.returncode, 0, self.one.stderr[-2000:])
        score = json.loads(self.one.stdout.strip().splitlines()[-1])
        self.assertGreater(score["total"], 0)
        self.assertGreater(score["survived"], 0)
        self.assertGreater(score["killed"], 0)

    def test_three_shards_give_the_same_score_line(self):
        self.assertEqual(self.three.returncode, 0, self.three.stderr[-2000:])
        self.assertEqual(self.three.stdout.strip().splitlines()[-1],
                         self.one.stdout.strip().splitlines()[-1])

    def test_three_shards_give_the_same_survivors(self):
        self.assertEqual(self.survivors(self.three), self.survivors(self.one))
        self.assertTrue(all(":calc.py:" in s or "calc.py:" in s for s in self.survivors(self.three)))

    def test_three_shards_ran_as_three(self):
        self.assertIn("in 3 shards", self.three.stderr)
        self.assertNotIn("shards", self.one.stderr.replace("MUTATION_SHARDS", ""))

    def test_the_tree_is_left_as_it_was(self):
        self.assertEqual((self.root / "pkg" / "calc.py").read_text(), CALC)

    def test_a_shard_count_that_is_not_a_positive_integer_is_refused(self):
        for bad in ("0", "two", "-1"):
            with self.subTest(shards=bad):
                result = run(self.root, bad)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"MUTATION_SHARDS={bad} is not a positive integer", result.stderr)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
