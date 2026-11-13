"""Tests for core/gates/codehost.py, written from docs/adr/0043 §3, §5,
docs/adr/0019 §5-§9 and gates/codehost-conformance.sh's header, never from
the implementation.

A fair host (a bare git repository behind the eight verbs) gets GO with its
PR merged; a host broken in one behaviour gets a NO-GO naming the case;
case 10 finds a secret in a verb's output.
"""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest

from core.gates import NoGo, codehost
from core.tests.gitrepo import ENV, Repo

TOKEN = "tok-secret-4f1c"


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True, text=True, check=True).stdout.strip()


class FakeHost:
    def __init__(self, test, workload, brk=None):
        self.brk = brk
        self.bare = os.path.join(tempfile.mkdtemp(), "host.git")
        test.addCleanup(subprocess.run, ["rm", "-rf", os.path.dirname(self.bare)], check=False)
        git("init", "-q", "--bare", "-b", "main", self.bare)
        self.workload = workload
        self.prs = {}
        self.statuses = {}
        self.n = 6

    def head(self, branch):
        return git("--git-dir", self.bare, "rev-parse", f"refs/heads/{branch}")

    def __call__(self, name, *args, data=None, env=None):
        return getattr(self, name.replace("-", "_"))(*args, env=env or {})

    def bootstrap(self, env):
        if self.brk != "bootstrap-noop":
            git("-C", self.workload, "push", "-q", self.bare, "HEAD:refs/heads/main")
        else:
            git("-C", self.workload, "push", "-q", self.bare, "HEAD~1:refs/heads/main")
        return 0, "", "bootstrapped\n"

    def clone_url(self, env):
        return 0, self.bare + "\n", ""

    def push(self, clone, branch, env):
        git("-C", clone, "push", "-q", "-f", "origin", f"{branch}:{branch}")
        return 0, "", (f"pushed with {TOKEN}\n" if self.brk == "leak" else "")

    def open_pr(self, branch, pr_file, env):
        if branch not in self.prs or self.brk == "open-pr-new":
            self.n += 1
            self.prs[branch] = {"number": self.n, "merged": False, "merge_sha": None}
        return 0, f"{self.prs[branch]['number']} http://fake/pr/{self.prs[branch]['number']}\n", ""

    def find(self, number):
        return next((b, p) for b, p in self.prs.items() if p["number"] == int(number))

    def status(self, sha, state, context, description, env):
        self.statuses[sha] = state
        return 0, "", ""

    def await_(self, sha, context, env):
        state = self.statuses.get(sha)
        if state == "success" or (state == "pending" and self.brk == "await-pending"):
            return 0, "success\n", ""
        return 1, "", "timed out\n"

    def pr(self, number, env):
        branch, p = self.find(number)
        doc = {"number": p["number"], "state": "closed" if p["merged"] else "open", "merged": p["merged"],
               "head_sha": self.head(branch), "merge_sha": p["merge_sha"]}
        if self.brk == "pr-extra":
            doc["title"] = "x"
        return 0, json.dumps(doc) + "\n", ""

    def merge(self, number, sha, env):
        branch, p = self.find(number)
        if p["merged"]:
            if self.brk == "remerge-fails":
                return 1, "", "already merged\n"
            return 0, f"{p['merge_sha']} {p['judged']}\n", ""
        if sha != self.head(branch) and self.brk != "merge-stale":
            return 1, "", "head moved\n"
        work = tempfile.mkdtemp()
        try:
            git("clone", "-q", self.bare, work)
            if self.brk == "squash":
                git("merge", "-q", "--squash", f"origin/{branch}", cwd=work)
                git("commit", "-q", "-m", "squash", cwd=work)
            else:
                git("merge", "-q", "--no-ff", "-m", "merge", sha, cwd=work)
            git("push", "-q", "origin", "main", cwd=work)
            p.update(merged=True, merge_sha=git("rev-parse", "HEAD", cwd=work), judged=sha)
        finally:
            subprocess.run(["rm", "-rf", work], check=False)
        return 0, f"{p['merge_sha']} {sha}\n", ""


setattr(FakeHost, "await", FakeHost.await_)


class CodeHostTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.repo.commit({"README": "one\n"})
        self.repo.commit({"README": "two\n"})

    def suite(self, brk=None, **env):
        host = FakeHost(self, self.repo.dir, brk)
        self.sleeps = []
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                got = ("GO", codehost.judge([], env=dict({"CODE_HOST": "fake", "WORKLOAD": self.repo.dir,
                                                          "GITHUB_TOKEN": TOKEN}, **env),
                                            verb=host, sleep=self.sleeps.append, password=lambda: ""))
            except NoGo as no:
                got = ("NO-GO", no.reason)
        self.err = err.getvalue()
        self.host = host
        return got

    def test_a_fair_host_is_go_with_a_merge_commit(self):
        self.assertEqual(self.suite(), ("GO", "fake, PR #7 merged"))
        main = git("--git-dir", self.host.bare, "rev-list", "--parents", "-n", "1", "main").split()
        self.assertEqual(len(main), 3)
        self.assertIn("case 10 no secret in the captured output: GO", self.err)
        self.assertIn("  [bootstrap] bootstrapped", self.err)

    def test_each_break_names_its_case(self):
        for brk, case in (("bootstrap-noop", "case1 bootstrap"), ("open-pr-new", "case4 open-pr"),
                          ("await-pending", "case5 await"), ("pr-extra", "case6 pr"),
                          ("merge-stale", "case7 stale-merge"), ("squash", "case8 merge"),
                          ("remerge-fails", "case9 re-merge"), ("leak", "case10")):
            with self.subTest(brk=brk):
                verdict, reason = self.suite(brk)
                self.assertEqual(verdict, "NO-GO", reason)
                self.assertTrue(reason.startswith(case + ":"), reason)
        self.assertEqual(self.suite("leak")[1], "case10: a secret appears in the output of: push push")

    def test_merge_is_retried_three_times(self):
        class Busy(FakeHost):
            tries = 0

            def merge(self, number, sha, env):
                if sha == self.head(self.find(number)[0]) and not self.find(number)[1]["merged"]:
                    Busy.tries += 1
                    if Busy.tries < 3:
                        return 1, "", "not mergeable yet\n"
                return super().merge(number, sha, env)
        host = Busy(self, self.repo.dir)
        with contextlib.redirect_stderr(io.StringIO()):
            got = codehost.judge([], env={"CODE_HOST": "fake", "WORKLOAD": self.repo.dir, "GITHUB_TOKEN": TOKEN},
                                 verb=host, sleep=lambda s: None, password=lambda: "")
        self.assertEqual(got, "fake, PR #7 merged")

    def test_no_secret_known_is_no_go(self):
        verdict, reason = self.suite(GITHUB_TOKEN="")
        self.assertIn("no secret is known for case 10", reason)

    def test_preconditions(self):
        self.assertIn("CODE_HOST is not set", self.suite(CODE_HOST="")[1])
        self.assertIn("WORKLOAD is not set", self.suite(WORKLOAD="")[1])

    def test_jq_equality(self):
        self.assertTrue(codehost.same(5, 5.0))
        self.assertFalse(codehost.same(False, 0))
        self.assertFalse(codehost.same(None, False))


if __name__ == "__main__":
    unittest.main()
