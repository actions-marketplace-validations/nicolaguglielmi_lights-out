"""Tests for the python mutation scorer, written from ADR 0042 §1 (the
mutation command prints one line `{"total","killed","survived","score"}`,
`total` counting valid mutants only, and is non-zero when a tool failed)
and from cosmic-ray 8.7.0's two sources of an "incompetent" result, read in
the installed package, never from the scorer:

  - cosmic_ray/testing.py `run_tests`: the test command could not be run
    at all (`subprocess.Popen(shlex.split(command))` raised, for instance a
    `VAR=value cmd` line, which is not a program without a shell). The
    work item's worker outcome is `normal`. This is the tool failing, not
    a mutant: no test ever ran.
  - cosmic_ray/mutating.py: applying the mutation raised. The worker
    outcome is `exception`. The mutant is invalid and leaves the
    population, as before.

Found in M24 phase C (2026-11-11): on tenacity, every mutant of a real
production change came back `incompetent` from the first source, the
scorer printed `{"total": 0}`, and the mutation gate answered GO by absence
of subject. Here, beside the runners and outside them (`./go init` copies
runners/ only), because core/ never names the contract directory or a
bundled workload (ci/app-free.sh). Black box: each case pipes a dump into `python3 <scorer>` and
judges stdout, stderr and the exit code. Every python copy of the scorer
is held to the same cases.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# lights-out's own copy in its contract is not listed: `self` runs this with
# the base's contract in the working tree (docs/adr/0033), and that copy is
# held to the stack's, as committed, by ci/init.sh case (g) (docs/adr/0049).
SCORERS = [
    ROOT / "stacks" / "python" / "runners" / "score.py",
    ROOT / "workloads" / "minimal" / "tests" / "mutation" / "score.py",
    ROOT / "app" / "backend" / "tests" / "mutation" / "score.py",
]


def item(job, line=10, op="core/NumberReplacer"):
    return {
        "job_id": job,
        "mutations": [{"module_path": "pkg/mod.py", "operator_name": op,
                       "occurrence": 0, "start_pos": [line, 4], "end_pos": [line, 5]}],
    }


def result(worker, test):
    return {"worker_outcome": worker, "output": "", "test_outcome": test, "diff": ""}


def dump(*rows):
    return "".join(json.dumps(r) + "\n" for r in rows)


KILLED = result("normal", "killed")
SURVIVED = result("normal", "survived")
SKIPPED = result("skipped", None)
CANNOT_RUN = result("normal", "incompetent")   # cosmic_ray/testing.py
BAD_MUTANT = result("exception", "incompetent")  # cosmic_ray/mutating.py


class PythonScorer(unittest.TestCase):
    def run_scorer(self, scorer, text):
        return subprocess.run([sys.executable, str(scorer)], input=text,
                              capture_output=True, text=True, check=False)

    def test_copies_exist(self):
        for scorer in SCORERS:
            self.assertTrue(scorer.is_file(), scorer)

    def test_valid_mutants_scored(self):
        text = dump([item("a"), KILLED], [item("b"), KILLED], [item("c", 12), SURVIVED],
                    [item("d"), SKIPPED], [item("e"), None])
        for scorer in SCORERS:
            with self.subTest(scorer=str(scorer.relative_to(ROOT))):
                p = self.run_scorer(scorer, text)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1]),
                                 {"total": 3, "killed": 2, "survived": 1, "score": 2 / 3})
                self.assertIn("SURVIVOR pkg/mod.py:12 core/NumberReplacer", p.stderr)

    def test_invalid_mutant_left_out(self):
        text = dump([item("a"), KILLED], [item("b"), BAD_MUTANT])
        for scorer in SCORERS:
            with self.subTest(scorer=str(scorer.relative_to(ROOT))):
                p = self.run_scorer(scorer, text)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1]),
                                 {"total": 1, "killed": 1, "survived": 0, "score": 1.0})

    def test_test_command_that_could_not_run_is_a_tool_failure(self):
        # Every mutant on the changed lines, as on tenacity: not a score of 0
        # valid mutants, a failure of the run.
        text = dump([item("a"), CANNOT_RUN], [item("b"), CANNOT_RUN], [item("c"), SKIPPED])
        for scorer in SCORERS:
            with self.subTest(scorer=str(scorer.relative_to(ROOT))):
                p = self.run_scorer(scorer, text)
                self.assertNotEqual(p.returncode, 0, p.stdout)
                self.assertEqual(p.stdout.strip(), "", "no score line when the tool failed")
                self.assertIn("test command", p.stderr)

    def test_one_mutant_whose_test_command_could_not_run_fails_the_run(self):
        text = dump([item("a"), KILLED], [item("b"), SURVIVED], [item("c"), CANNOT_RUN])
        for scorer in SCORERS:
            with self.subTest(scorer=str(scorer.relative_to(ROOT))):
                p = self.run_scorer(scorer, text)
                self.assertNotEqual(p.returncode, 0, p.stdout)
                self.assertEqual(p.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
