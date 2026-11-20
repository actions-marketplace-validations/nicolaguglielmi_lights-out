"""Tests for core/await-head.sh, written from its header, never from its body.

The spec: `await-head.sh <repository> <seconds>` exits 0 once git resolves
HEAD in the repository, 1 if it does not within the seconds. It waits only
where waiting can help: a file git replaced (.git/HEAD after git switch, the
branch's ref after a commit) that a podman machine shows a few seconds late.
A directory with no .git directory, or a repository with no commit yet, is
answered at once. Nothing on stdout.

Here the lag is planted by hand: the file is moved away and put back by a
timer, which is what the bind mount shows while it lags.
"""

import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "core" / "await-head.sh"

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


class AwaitHead(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "r"
        self.repo.mkdir()

    def git(self, *args):
        subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=self.repo, check=True,
                       env={**os.environ, **GIT_ENV}, capture_output=True)

    def committed(self):
        self.git("init", "-q", "-b", "main")
        (self.repo / "f").write_text("a\n")
        self.git("add", "f")
        self.git("commit", "-q", "-m", "a")

    def run_it(self, seconds):
        t = time.monotonic()
        p = subprocess.run(["sh", str(SCRIPT), str(self.repo), str(seconds)],
                           env={**os.environ, **GIT_ENV}, capture_output=True, text=True, timeout=60)
        return p, time.monotonic() - t

    def lag(self, rel, back_after):
        """Hide REL under .git and put it back after BACK_AFTER seconds."""
        f = self.repo / ".git" / rel
        hidden = self.tmp / "hidden"
        f.rename(hidden)
        timer = threading.Timer(back_after, hidden.rename, args=(f,))
        timer.start()
        self.addCleanup(timer.cancel)

    def test_a_repository_whose_head_resolves_answers_at_once(self):
        self.committed()
        p, took = self.run_it(10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertLess(took, 1)
        self.assertEqual(p.stdout, "")

    def test_head_back_after_a_lag_is_awaited(self):
        self.committed()
        self.lag("HEAD", 2)
        p, took = self.run_it(10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertGreaterEqual(took, 2)
        self.assertLess(took, 10)
        self.assertEqual(p.stdout, "")

    def test_the_branch_ref_back_after_a_lag_is_awaited(self):
        self.committed()
        self.lag("refs/heads/main", 2)
        p, took = self.run_it(10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertGreaterEqual(took, 2)
        self.assertLess(took, 10)

    def test_a_lag_longer_than_the_bound_is_a_failure(self):
        self.committed()
        self.lag("HEAD", 30)
        p, took = self.run_it(2)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertGreaterEqual(took, 2)
        self.assertLess(took, 8)
        self.assertEqual(p.stdout, "")

    def test_a_directory_that_is_not_a_repository_answers_at_once(self):
        p, took = self.run_it(10)
        self.assertEqual(p.returncode, 1)
        self.assertLess(took, 1)

    def test_a_repository_with_no_commit_answers_at_once(self):
        self.git("init", "-q", "-b", "main")
        p, took = self.run_it(10)
        self.assertEqual(p.returncode, 1)
        self.assertLess(took, 1)


if __name__ == "__main__":
    unittest.main()
