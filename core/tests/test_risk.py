"""Unit tests for core/risk.py, one case per docs/adr/0016 §7's bullet list.

The policy values are read from the real policy/merge.env (not hardcoded),
so these tests and the policy file cannot drift apart: a change to a glob
or the size threshold is exercised here on the next run, not silently
missed by a stale copy.
"""

import subprocess
import sys
import unittest
from pathlib import Path

from core.risk import classify, parse_policy

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "policy" / "merge.env"
RISK_PY = REPO_ROOT / "core" / "risk.py"


class ClassifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = parse_policy(POLICY_PATH.read_text())
        cls.threshold = int(cls.policy["RISK_SIZE_MEDIUM_LINES"])

    def test_migration_path_is_high(self):
        # Plan §7 done-when: a PR touching a migration is high risk.
        path = "app/backend/migrations/0004_x.sql"
        result = classify([f"5\t0\t{path}"], self.policy)
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["signals"], [{"name": "migrations", "paths": [path]}])

    def test_auth_path_is_high(self):
        path = "app/backend/meetups/auth.py"
        result = classify([f"3\t1\t{path}"], self.policy)
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["signals"], [{"name": "auth", "paths": [path]}])

    def test_payments_path_is_high_though_unused_today(self):
        # docs/adr/0016 §3: the rule is declared and tested, and fires
        # without a line of payments code existing in the app.
        path = "app/backend/meetups/payments.py"
        result = classify([f"2\t0\t{path}"], self.policy)
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["signals"], [{"name": "payments", "paths": [path]}])

    def test_platform_path_is_high(self):
        # A PR editing a gate must not be able to merge itself
        # (docs/adr/0016 §2) -- gates/risk.sh names itself here.
        path = "gates/risk.sh"
        result = classify([f"1\t1\t{path}"], self.policy)
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["signals"], [{"name": "platform", "paths": [path]}])

    def test_roles_path_is_high(self):
        # docs/adr/0017 §7: a role's prompt and hooks are the platform.
        path = "roles/dev-worker/prompt.md"
        result = classify([f"4\t0\t{path}"], self.policy)
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["signals"], [{"name": "platform", "paths": [path]}])

    def test_fixtures_path_is_high(self):
        # docs/adr/0017 §7: a fixture change changes what L0 replays.
        path = "fixtures/0001/dev-worker/patch"
        result = classify([f"20\t0\t{path}"], self.policy)
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["signals"], [{"name": "platform", "paths": [path]}])

    def test_dot_gemini_path_is_high(self):
        # docs/adr/0017 §7: a project-level .gemini/settings.json in the
        # repo would reconfigure the worker.
        path = ".gemini/settings.json"
        result = classify([f"6\t0\t{path}"], self.policy)
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["signals"], [{"name": "platform", "paths": [path]}])

    def test_docs_only_change_is_medium(self):
        # Comfortably over RISK_SIZE_MEDIUM_LINES, on a path with no signal.
        lines_changed = self.threshold + 50
        path = "docs/notes.md"
        result = classify([f"{lines_changed}\t0\t{path}"], self.policy)
        self.assertEqual(result["level"], "medium")
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["signals"], [{"name": "size", "paths": [path]}])
        self.assertEqual(result["size"]["lines"], lines_changed)

    def test_small_backend_fix_is_low(self):
        # geocoder_client.py: ADR 0016's own example of a changed backend
        # path that is deliberately not a signal (alternatives rejected).
        result = classify(
            ["20\t10\tapp/backend/meetups/geocoder_client.py"], self.policy
        )
        self.assertEqual(result["level"], "low")
        self.assertEqual(result["decision"], "auto-merge")
        self.assertEqual(result["signals"], [])
        self.assertEqual(result["size"]["lines"], 30)

    def test_lockfile_lines_are_excluded_from_size(self):
        # A huge lockfile diff alone must not push size into "medium".
        path = "app/backend/uv.lock"
        result = classify([f"5000\t3000\t{path}"], self.policy)
        self.assertEqual(result["level"], "low")
        self.assertEqual(result["decision"], "auto-merge")
        self.assertEqual(result["signals"], [])
        self.assertEqual(result["size"]["lines"], 0)
        self.assertEqual(result["size"]["excluded"], [path])

    def test_empty_diff_is_low(self):
        result = classify([], self.policy)
        self.assertEqual(result["level"], "low")
        self.assertEqual(result["decision"], "auto-merge")
        self.assertEqual(result["signals"], [])
        self.assertEqual(
            result["size"],
            {"lines": 0, "threshold": self.threshold, "excluded": []},
        )


class CliMalformedInputTests(unittest.TestCase):
    """The malformed-input contract is a CLI/exit-code contract (docs/adr/0016
    §7), so it is tested via subprocess rather than a classify() return
    value: exit 1, one-line stderr, nothing on stdout."""

    def test_malformed_numstat_line_exits_1(self):
        proc = subprocess.run(
            [sys.executable, str(RISK_PY), "--policy", str(POLICY_PATH)],
            input="5\t2\tapp/backend/meetups/app.py\nnot-a-numstat-line\n",
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        stderr_lines = proc.stderr.strip("\n").splitlines()
        self.assertEqual(len(stderr_lines), 1)
        self.assertNotEqual(stderr_lines[0], "")


if __name__ == "__main__":
    unittest.main()
