"""The range a PR gate judges is the one the caller names (docs/adr/0015 §2,
docs/adr/0053 §2).

Written from the two ADRs, not from the gates. `BASE` and `HEAD` name
commits in the caller's checkout. ADR 0053 §2 has `test-proof` take the
PR's test files from the range's head onto a throwaway worktree of the
merge-base: the head is the commit the caller named, however it was named,
so `HEAD=HEAD~1`, `HEAD=HEAD`, a branch and a full id that name the same
commit get the same verdict. In the throwaway worktree `HEAD` is the base.

The gate runs in-process (`TOOLCHAIN_IMAGE=workbench`, docs/adr/0042 §2):
git, sh and python3, no engine.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TEST_CMD = 'for t in tests/*.sh; do sh "$t" || exit 1; done'


class GateRange(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-range-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        # c0: the code and a test that passes.
        self.write("value.txt", "1\n")
        self.write("tests/value.sh", '[ "$(cat value.txt)" = 1 ]\n')
        self.write(".lights-out/keep", "")
        self.c0 = self.commit("the value and its test")
        # c1, the base: a change no test reads.
        self.write("README", "one\n")
        self.c1 = self.commit("a readme")
        # c2, the head: a feature and the test that proves it.
        self.write("extra.txt", "x\n")
        self.write("tests/extra.sh", "[ -f extra.txt ]\n")
        self.c2 = self.commit("extra, with its test")
        self.git("branch", "feature", self.c2)
        # c3: something after the range.
        self.write("README", "two\n")
        self.c3 = self.commit("the readme again")

    def git(self, *args):
        p = subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=self.repo,
                           capture_output=True, text=True, check=True)
        return p.stdout.strip()

    def write(self, rel, text):
        f = self.repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)

    def commit(self, message):
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def gate(self, base, head):
        env = {k: v for k, v in os.environ.items()
               if k not in ("GATES_OUT", "TOOLCHAIN_ISOLATE", "WORKLOAD_ATTACHED", "NOGO_DETAILS", "TICKET")}
        env.update(BASE=base, HEAD=head, WORKLOAD=str(self.repo),
                   WORKLOAD_CONTRACT=str(self.repo / ".lights-out"),
                   WORKLOAD_TEST_PATHS="tests/*.sh", WORKLOAD_TEST_ROOT="",
                   TEST_CMD=TEST_CMD, TOOLCHAIN_IMAGE="workbench", NO_COLOR="1")
        p = subprocess.run(["sh", "gates/test-proof.sh"], cwd=ROOT, env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True)
        return p.returncode, p.stdout

    def test_the_range_named_by_ids_is_go(self):
        rc, out = self.gate(self.c1, self.c2)
        self.assertEqual((rc, out.count("\n")), (0, 1), out)
        self.assertTrue(out.startswith("GO: test-proof"), out)
        self.assertIn(self.c1[:7], out)

    def test_a_head_named_from_HEAD_is_the_same_commit(self):
        want = self.gate(self.c1, self.c2)
        # c3 is checked out: HEAD~1 is c2.
        self.assertEqual(self.gate(self.c1, "HEAD~1"), want)

    def test_HEAD_itself_as_the_head(self):
        want = self.gate(self.c1, self.c2)
        self.git("checkout", "-q", "--detach", self.c2)
        self.assertEqual(self.gate(self.c1, "HEAD"), want)

    def test_a_base_named_from_HEAD(self):
        want = self.gate(self.c1, self.c2)
        # c3 is checked out: HEAD~2 is c1, HEAD~1 is c2.
        self.assertEqual(self.gate("HEAD~2", "HEAD~1"), want)

    def test_a_branch_as_the_head(self):
        self.assertEqual(self.gate(self.c1, "feature"), self.gate(self.c1, self.c2))

    def test_a_head_that_names_nothing_is_one_no_go_line(self):
        rc, out = self.gate(self.c1, "no-such-ref")
        self.assertEqual((rc, out.count("\n")), (1, 1), out)
        self.assertTrue(out.startswith("NO-GO: test-proof — "), out)

    def test_a_test_that_passes_on_the_base_is_still_no_go(self):
        # A change with a test that passes without it (only tests changed
        # would be GO by absence of subject, so the commit changes code too).
        self.write("README", "three\n")
        self.write("tests/readme.sh", "[ -f README ]\n")
        c4 = self.commit("a change, and a test that proves nothing about it")
        rc, out = self.gate(self.c3, "HEAD")
        self.assertEqual(rc, 1, out)
        self.assertTrue(out.startswith("NO-GO: test-proof — "), out)
        self.assertEqual(self.gate(self.c3, c4), (rc, out))


if __name__ == "__main__":
    unittest.main()
