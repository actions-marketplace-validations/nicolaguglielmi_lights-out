"""Tests for core/gates/testproof.py and core/gates/risk.py, written from
docs/adr/0053 §2, docs/adr/0016 and the two gates' headers, never from the
implementation.

test-proof: the changed tests, taken onto the base, must fail there; GO by
absence of subject runs nothing and checks no toolchain. risk: always GO
when it classified, risk.json written; NO-GO only when it could not.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest

from core.gates import NoGo, risk, testproof
from core.tests.gitrepo import Repo

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class TestProofTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.base = self.repo.commit({"c/keep": "", "code.txt": "1\n", "tests/a.sh": "true\n"})
        self.env = {"WORKLOAD": self.repo.dir, "WORKLOAD_CONTRACT": os.path.join(self.repo.dir, "c"),
                    "WORKLOAD_TEST_PATHS": "tests/*.sh", "TEST_CMD": "the suite"}
        self.ran = []

    def gate(self, head, rc=1, ok=True, base=None, **env):
        def run(cmd, cwd, child):
            with open(os.path.join(child["WORKLOAD"], "tests/a.sh")) as fh:
                self.ran.append((cmd, cwd, child, fh.read(), os.path.exists(os.path.join(child["WORKLOAD"], "code2.txt"))))
            return rc
        self.checked = []

        def check():
            self.checked.append(1)
            return ok, "workbench" if ok else "the engine socket is not available"
        try:
            return "GO", testproof.judge([base or self.base, head], env=dict(self.env, **env), check=check, run=run)
        except NoGo as no:
            return "NO-GO", no.reason, no.details

    def change(self):
        return self.repo.commit({"code2.txt": "x\n", "tests/a.sh": "test -f code2.txt\n"})

    def test_changed_tests_failing_on_the_base_is_go(self):
        head = self.change()
        self.assertEqual(self.gate(head), ("GO", f"in workbench, the changed tests fail on the base {self.base[:7]}"))
        cmd, cwd, child, test_text, code_there = self.ran[0]
        self.assertEqual(cmd, "the suite")
        self.assertEqual(test_text, "test -f code2.txt\n")  # the test from HEAD
        self.assertFalse(code_there)  # the code from the base
        self.assertEqual(cwd, child["WORKLOAD"].rstrip("/"))  # the bundled workload: its worktree
        self.assertTrue(child["COMPOSE_FILE"].startswith("compose.yaml:"))
        self.assertTrue(child["WORKLOAD_CONTRACT"].endswith("/c/"))
        self.assertEqual(len(self.repo.git("worktree", "list").splitlines()), 1)

    def test_passing_on_the_base_is_no_go_listing_the_tests(self):
        head = self.change()
        got = self.gate(head, rc=0)
        self.assertEqual(got[1], f"in workbench: the changed tests pass on the base {self.base[:7]} too, "
                                 "so they do not prove the change")
        self.assertEqual(got[2], ["tests/a.sh"])

    def test_toolchain_failure(self):
        self.assertIn("the toolchain itself failed on the base", self.gate(self.change(), rc=125)[1])

    def test_attached_workload_runs_from_this_checkout(self):
        self.gate(self.change(), WORKLOAD_ATTACHED="1")
        self.assertEqual(self.ran[0][1], os.getcwd())

    def test_absence_of_subject_runs_and_checks_nothing(self):
        cases = [(self.repo.commit({"code.txt": "2\n"}), "nothing ran: no test changed: nothing to fail on the base"),
                 (self.repo.commit({"tests/a.sh": "false\n"}), "nothing ran: only test files changed: no code for them to prove")]
        for head, want in cases:
            with self.subTest(want=want):
                self.assertEqual(self.gate(head, ok=False, base=self.repo.git("rev-parse", f"{head}~1")), ("GO", want))
        self.assertEqual(self.gate(self.base, ok=False, base=EMPTY_TREE),
                         ("GO", "nothing ran: the base is the empty tree, nothing to fail on"))
        self.assertEqual((self.ran, self.checked), ([], []))

    def test_preflight_reason_is_the_no_go(self):
        self.assertEqual(self.gate(self.change(), ok=False)[1], "the engine socket is not available")
        self.assertEqual(self.ran, [])

    def test_contract_errors(self):
        self.assertEqual(self.gate(self.base, WORKLOAD_TEST_PATHS="")[1], "WORKLOAD_TEST_PATHS is empty (docs/adr/0053 §1)")
        self.assertEqual(self.gate(self.base, TEST_CMD="")[1], "TEST_CMD is empty (docs/adr/0042 §1)")
        outside = tempfile.mkdtemp()
        self.assertEqual(self.gate(self.change(), WORKLOAD_CONTRACT=outside)[1], f"{outside} is not inside a git repository")


class RiskTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.out = tempfile.mkdtemp()
        self.policy = os.path.join(self.out, "p.env")
        with open(self.policy, "w") as fh:
            fh.write("RISK_HIGH_MIGRATIONS=db/*\nRISK_HIGH_AUTH=\nRISK_HIGH_PAYMENTS=\nRISK_HIGH_PLATFORM=\n"
                     "RISK_SIZE_MEDIUM_LINES=200\nRISK_SIZE_MEDIUM_FILES=10\nRISK_SIZE_EXCLUDE=\n")
        self.base = self.repo.commit({"a.txt": "a\n"})

    def gate(self, head, policy=None):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                got = ("GO", risk.judge([self.base, head, policy or self.policy],
                                        env={"WORKLOAD": self.repo.dir, "GATES_OUT": self.out}))
            except NoGo as no:
                got = ("NO-GO", no.reason)
        self.err = err.getvalue()
        return got

    def test_high_risk_is_still_go_with_risk_json(self):
        head = self.repo.commit({"db/001.sql": "create table t;\n"})
        self.assertEqual(self.gate(head), ("GO", None))
        with open(os.path.join(self.out, "risk.json")) as fh:
            data = json.load(fh)
        self.assertEqual(data["level"], "high")
        self.assertIn("risk: level=high decision=", self.err)
        self.assertIn("signals=migrations(db/001.sql)", self.err)

    def test_low_risk_names_no_signal(self):
        self.assertEqual(self.gate(self.repo.commit({"a.txt": "b\n"})), ("GO", None))
        self.assertIn("signals=none", self.err)

    def test_unreadable_range_or_policy_is_no_go(self):
        want = f"core/risk.py could not classify the range {self.base}..nope"
        self.assertEqual(self.gate("nope"), ("NO-GO", want))
        head = self.repo.commit({"a.txt": "b\n"})
        self.assertEqual(self.gate(head, policy="/nonexistent")[0], "NO-GO")


if __name__ == "__main__":
    unittest.main()
