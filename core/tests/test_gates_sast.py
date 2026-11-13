"""Tests for core/gates/sast.py, written from docs/adr/0072 §1 and
gates/sast.sh's header, never from the implementation.

HEAD is scanned; with no finding it is GO and the base is not scanned. With
findings the base is scanned (nothing for the empty tree, HEAD's scan for an
empty range, a worktree of the merge-base otherwise) and only a finding HEAD
has more times than the base is NO-GO. A runner with no `items` judges HEAD
whole. Exit 125 is the toolchain; a failed scan with no finding is a NO-GO.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest

from core.gates import NoGo, sast
from core.tests.gitrepo import Repo

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class Scanner:
    """A runner over the checkout it is pointed at: every line holding BAD is
    a finding of rule B1; `items` left out when OLD is set."""

    def __init__(self, test, rc=0, old=False, base_rc=None, garbage=False):
        self.test, self.rc, self.old, self.base_rc, self.garbage = test, rc, old, base_rc, garbage
        self.calls = []

    def __call__(self, cmd, out_path, cwd=None, workload=None):
        root = os.path.join(workload or self.test.env["WORKLOAD"], self.test.env.get("WORKLOAD_TEST_ROOT", ""))
        self.calls.append(workload)
        items = []
        for top, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in sorted(files):
                path = os.path.join(top, f)
                with open(path) as fh:
                    for n, line in enumerate(fh, 1):
                        if "BAD" in line:
                            items.append({"rule": "B1", "file": os.path.relpath(path, root), "line": n})
        line = {"findings": len(items)} if self.old else {"findings": len(items), "items": items}
        with open(out_path, "w") as fh:
            fh.write("noise\n" + ("{not json" if self.garbage else json.dumps(line)) + "\n")
        if workload is not None and self.base_rc is not None:
            return self.base_rc
        return self.rc


class SastTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.out = tempfile.mkdtemp()
        self.env = {"WORKLOAD": self.repo.dir, "WORKLOAD_TEST_ROOT": "", "GATES_OUT": self.out, "SAST_CMD": "scan"}
        self.base = self.repo.commit({"src/a.py": "ok\nBAD old\n", "src/b.py": "ok\n"})

    def gate(self, base, head, scanner=None):
        self.scanner = scanner or Scanner(self)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                got = ("GO", sast.judge([base, head, "workbench"], env=self.env, run=self.scanner))
            except NoGo as no:
                got = ("NO-GO", no.reason)
        self.err = err.getvalue()
        return got

    def record(self):
        with open(os.path.join(self.out, "sast.json")) as fh:
            return json.load(fh)

    def test_inherited_finding_is_go_new_one_is_no_go(self):
        same = self.repo.commit({"src/b.py": "ok\nstill ok\n"})
        self.assertEqual(self.gate(self.base, same), ("GO", "in workbench, none new (1 inherited)"))
        self.assertEqual(len(self.scanner.calls), 2)
        self.assertNotIn(self.repo.dir, self.scanner.calls[1])
        new = self.repo.commit({"src/b.py": "ok\nBAD new\n"})
        self.assertEqual(self.gate(self.base, new),
                         ("NO-GO", "in workbench: this diff introduces 1 finding(s); list on stderr"))
        self.assertEqual(len(self.record()["new"]), 1)
        self.assertIn("introduced by this diff", self.err)

    def test_a_moved_line_is_still_inherited(self):
        head = self.repo.commit({"src/a.py": "first\nok\n\nBAD old\n"})
        self.assertEqual(self.gate(self.base, head)[0], "GO")

    def test_a_renamed_file_keeps_its_findings(self):
        self.repo.git("mv", "src/a.py", "src/c.py")
        head = self.repo.commit({})
        self.assertEqual(self.gate(self.base, head)[0], "GO")

    def test_no_finding_at_head_is_go_without_the_base(self):
        head = self.repo.commit({"src/a.py": "ok\n"})
        self.assertEqual(self.gate(self.base, head), ("GO", "in workbench, none new (0 inherited)"))
        self.assertEqual(len(self.scanner.calls), 1)
        self.assertEqual(self.record(), {"findings": 0, "where": "workbench", "new": [], "inherited": []})

    def test_empty_range_compares_head_with_itself(self):
        self.assertEqual(self.gate(self.base, self.base), ("GO", "in workbench, none new (1 inherited)"))
        self.assertEqual(len(self.scanner.calls), 1)

    def test_empty_tree_base_makes_every_finding_new(self):
        got = self.gate(EMPTY_TREE, self.base)
        self.assertEqual(got[0], "NO-GO")
        self.assertIn("nothing to scan: every finding is new", self.err)

    def test_old_runner_judges_head_whole(self):
        got = self.gate(self.base, self.base, Scanner(self, old=True))
        self.assertEqual(got, ("NO-GO", "in workbench: 1 SAST finding(s) in the workload's scope"))
        self.assertEqual(self.record(), {"findings": 1, "where": "workbench"})
        head = self.repo.commit({"src/a.py": "ok\n"})
        self.assertEqual(self.gate(self.base, head, Scanner(self, old=True)), ("GO", "in workbench"))

    def test_old_runner_on_the_base_judges_head_whole(self):
        head = self.repo.commit({"src/b.py": "x\n"})

        class Mixed(Scanner):
            def __call__(self, cmd, out_path, cwd=None, workload=None):
                self.old = workload is not None
                return super().__call__(cmd, out_path, cwd, workload)
        self.assertEqual(self.gate(self.base, head, Mixed(self))[1], "in workbench: 1 SAST finding(s) in the workload's scope")

    def test_toolchain_failure_and_failed_scan(self):
        got = self.gate(self.base, self.base, Scanner(self, rc=125))
        self.assertEqual(got[1], "in workbench: the toolchain itself failed before the scan ran; see stderr")
        self.assertEqual(self.record(), {"findings": None, "where": "workbench"})
        # A non-zero exit with findings parsed is the findings' verdict.
        self.assertEqual(self.gate(self.base, self.base, Scanner(self, rc=3))[0], "GO")
        head = self.repo.commit({"src/a.py": "ok\n"})
        self.assertIn("SAST_CMD exited 3 with no findings parsed", self.gate(self.base, head, Scanner(self, rc=3))[1])

    def test_failures_on_the_base(self):
        head = self.repo.commit({"src/b.py": "x\n"})
        self.assertIn("failed on the base", self.gate(self.base, head, Scanner(self, base_rc=125))[1])

    def test_unreadable_runner_line(self):
        got = self.gate(self.base, self.base, Scanner(self, garbage=True))
        self.assertEqual(got[0], "NO-GO")
        self.assertEqual(self.record()["findings"], None)

    def test_test_root_scopes_the_run(self):
        self.env["WORKLOAD_TEST_ROOT"] = "src/"
        head = self.repo.commit({"src/b.py": "BAD\n"})
        self.assertEqual(self.gate(self.base, head)[0], "NO-GO")
        self.assertEqual(self.record()["new"][0]["file"], "src/b.py")

    def test_base_worktree_is_removed(self):
        head = self.repo.commit({"src/b.py": "x\n"})
        self.gate(self.base, head)
        self.assertEqual(len(self.repo.git("worktree", "list").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
