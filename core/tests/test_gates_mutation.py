"""Tests for core/gates/mutation.py, written from docs/adr/0015 §3,
docs/adr/0042 §1, docs/adr/0074 §3-§4 and gates/mutation.sh's header, never
from the implementation.

Only the new side of each hunk under the scope is mutated, the workload's
prefix and test root dropped; lines a JUDGED tree already holds are not
mutated again; no line is GO by absence of subject; the score is the last
non-empty stdout line, GO at or above baseline - margin, NO-GO below with
the survivors as details.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest

from core.gates import NoGo, mutation
from core.tests.gitrepo import Repo

SRC = "".join(f"line {i}\n" for i in range(1, 11))


def edit(text, changes):
    """TEXT with line numbers in CHANGES replaced."""
    lines = text.splitlines(keepends=True)
    for n, new in changes.items():
        lines[n - 1] = new + "\n"
    return "".join(lines)


class Runner:
    def __init__(self, rc=0, out='{"total": 4, "killed": 4, "survived": 0, "score": 1.0}\n', noise=""):
        self.rc, self.out, self.noise = rc, out, noise
        self.calls = []

    def __call__(self, cmd, lines, log):
        self.calls.append((cmd, lines))
        with open(log, "w") as fh:
            fh.write(self.noise)
        return self.rc, self.out


def policy(baseline="0.5", margin="0.1"):
    def write(env, out):
        with open(out, "w") as fh:
            fh.write(f"MUTATION_BASELINE={baseline}\nMUTATION_MARGIN={margin}\n")
        return None
    return write


class MutationTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.out = tempfile.mkdtemp()
        self.base = self.repo.commit({"svc/pkg/a.py": SRC, "svc/pkg/b.py": SRC, "svc/other/c.py": SRC})
        self.env = {"WORKLOAD": os.path.join(self.repo.dir, "svc"), "WORKLOAD_MUTATION_SCOPE": "pkg",
                    "WORKLOAD_TEST_ROOT": "", "GATES_OUT": self.out, "MUTATION_CMD": "run it"}

    def gate(self, head, runner=None, pol=None, base=None, **env):
        self.runner = runner or Runner()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                got = ("GO", mutation.judge([base or self.base, head, "workbench"], env=dict(self.env, **env),
                                            run=self.runner, policy=pol or policy()))
            except NoGo as no:
                got = ("NO-GO", no.reason, no.details)
        self.err = err.getvalue()
        return got

    def lines(self):
        return self.runner.calls[0][1] if self.runner.calls else None

    def record(self):
        with open(os.path.join(self.out, "mutation.json")) as fh:
            return json.load(fh)

    def test_new_side_of_hunks_under_scope_only(self):
        head = self.repo.commit({"svc/pkg/a.py": edit(SRC, {2: "x", 3: "y", 7: "z"}),
                                 "svc/other/c.py": edit(SRC, {1: "q"})})
        self.assertEqual(self.gate(head), ("GO", "in workbench"))
        self.assertEqual(self.lines(), "pkg/a.py=2-3,7-7")
        self.assertEqual(self.runner.calls[0][0], "run it")

    def test_groups_sorted_by_path_space_separated(self):
        head = self.repo.commit({"svc/pkg/b.py": edit(SRC, {5: "x"}), "svc/pkg/a.py": SRC + "new\nmore\n"})
        self.gate(head)
        self.assertEqual(self.lines(), "pkg/a.py=11-12 pkg/b.py=5-5")

    def test_test_root_is_dropped_too(self):
        head = self.repo.commit({"svc/pkg/a.py": edit(SRC, {1: "x"})})
        self.gate(head, WORKLOAD_MUTATION_SCOPE="pkg", WORKLOAD_TEST_ROOT="pkg/")
        self.assertEqual(self.lines(), "a.py=1-1")

    def test_pure_deletion_is_nothing_to_mutate(self):
        head = self.repo.commit({"svc/pkg/a.py": "".join(SRC.splitlines(keepends=True)[:5])})
        self.assertEqual(self.gate(head), ("GO", "in workbench, nothing ran"))
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.record(), {"total": 0, "score": None})
        self.assertIn("GO by absence of subject, nothing ran", self.err)

    def test_nothing_to_mutate_reads_no_policy(self):
        head = self.repo.commit({"svc/other/c.py": edit(SRC, {1: "q"})})
        self.assertEqual(self.gate(head, pol=lambda env, out: "broken policy")[0], "GO")

    def test_score_at_threshold_is_go_below_is_no_go_with_survivors(self):
        head = self.repo.commit({"svc/pkg/a.py": edit(SRC, {1: "x"})})
        at = Runner(out='{"total": 10, "killed": 4, "survived": 6, "score": 0.4}\n')
        self.assertEqual(self.gate(head, at, policy("0.5", "0.1")), ("GO", "in workbench"))
        below = Runner(out='{"total": 10, "killed": 3, "survived": 7, "score": 0.3}\n',
                       noise="cosmic noise\nSURVIVOR pkg/a.py:1 ReplaceBinaryOperator\nSURVIVOR pkg/a.py:2 X\n")
        got = self.gate(head, below, policy("0.5", "0.1"))
        self.assertEqual(got[:2], ("NO-GO", "in workbench: 3/10 mutants on changed lines killed (0.300 < 0.400); "
                                            "survivors on stderr"))
        self.assertEqual(got[2], ["pkg/a.py:1 ReplaceBinaryOperator", "pkg/a.py:2 X"])
        self.assertIn("cosmic noise", self.err)
        self.assertEqual(self.record()["killed"], 3)

    def test_no_score_is_no_go_zero_mutants_go(self):
        head = self.repo.commit({"svc/pkg/a.py": edit(SRC, {1: "x"})})
        got = self.gate(head, Runner(out='{"total": 3, "killed": 0, "score": null}\n'))
        self.assertIn("(none < 0.400)", got[1])
        self.assertEqual(self.gate(head, Runner(out='{"total": 0, "killed": 0, "score": null}\n')),
                         ("GO", "in workbench"))
        self.assertIn("after running the mutation command", self.err)

    def test_the_last_non_empty_line_is_the_score(self):
        head = self.repo.commit({"svc/pkg/a.py": edit(SRC, {1: "x"})})
        out = 'npm ci output\n{"total": 9, "score": 0.0}\n{"total": 2, "killed": 2, "score": 1.0}\n\n  \n'
        self.assertEqual(self.gate(head, Runner(out=out))[0], "GO")
        self.assertEqual(self.record()["total"], 2)

    def test_malformed_output(self):
        head = self.repo.commit({"svc/pkg/a.py": edit(SRC, {1: "x"})})
        got = self.gate(head, Runner(out="no json here\n"))
        self.assertTrue(got[1].startswith("in workbench: malformed mutation run output"), got)
        self.assertFalse(os.path.exists(os.path.join(self.out, "mutation.json")))

    def test_toolchain_and_run_failures(self):
        head = self.repo.commit({"svc/pkg/a.py": edit(SRC, {1: "x"})})
        self.assertIn("the toolchain itself failed", self.gate(head, Runner(rc=125))[1])
        self.assertIn("failed before scoring", self.gate(head, Runner(rc=2))[1])

    def test_policy_failure_and_empty_baseline(self):
        head = self.repo.commit({"svc/pkg/a.py": edit(SRC, {1: "x"})})
        self.assertEqual(self.gate(head, pol=lambda e, o: "MUTATION_MARGIN: no provenance")[1],
                         "MUTATION_MARGIN: no provenance")
        self.assertEqual(self.gate(head, pol=policy(""))[1], "MUTATION_BASELINE is empty")
        self.assertIn("not a number", self.gate(head, pol=policy("x"))[1])

    def test_judged_lines_are_not_mutated_again(self):
        judged = self.repo.commit({"svc/pkg/a.py": edit(SRC, {2: "x", 3: "y"})})
        head = self.repo.commit({"svc/pkg/a.py": edit(SRC, {2: "x", 3: "y", 8: "w"})})
        got = self.gate(head, JUDGED=judged)
        self.assertEqual(self.lines(), "pkg/a.py=8-8")
        short = self.repo.git("rev-parse", "--short", judged)
        self.assertEqual(got, ("GO", f"in workbench, 2 lines judged at {short}"))
        self.assertIn("2 changed line(s)", self.err)

    def test_all_lines_judged_is_nothing_ran(self):
        judged = self.repo.commit({"svc/pkg/a.py": edit(SRC, {2: "x"})})
        head = self.repo.commit({"svc/pkg/b.py": SRC}, "no change under scope")
        got = self.gate(head, JUDGED=judged)
        self.assertEqual(got[0], "GO")
        self.assertTrue(got[1].endswith("nothing ran"))

    def test_judged_must_be_a_commit_and_an_ancestor(self):
        head = self.repo.commit({"svc/pkg/a.py": edit(SRC, {1: "x"})})
        self.assertIn("not a commit", self.gate(head, JUDGED="nope")[1])
        self.repo.git("checkout", "-q", "-b", "side", self.base)
        side = self.repo.commit({"svc/pkg/b.py": edit(SRC, {1: "s"})})
        self.assertIn("not an ancestor of HEAD", self.gate(head, JUDGED=side)[1])

    def test_not_a_repository(self):
        got = self.gate("HEAD", WORKLOAD=tempfile.mkdtemp())
        self.assertIn("is not inside a git repository", got[1])

    def test_unjudged_and_runs(self):
        self.assertEqual(mutation.runs({5, 1, 2, 3, 9}), [(1, 3), (5, 5), (9, 9)])
        # OTHERS are what HEAD still adds against each judged tree: a line one
        # of them lacks is a line that tree already has.
        self.assertEqual(mutation.unjudged({"a": [(1, 4)]}, [{"a": [(2, 3)]}]), ({"a": [(2, 3)]}, 2))
        self.assertEqual(mutation.unjudged({"a": [(1, 4)], "b": [(1, 1)]}, [{"a": [(2, 3)]}, {"a": [(3, 3)]}]),
                         ({"a": [(3, 3)]}, 4))


if __name__ == "__main__":
    unittest.main()
