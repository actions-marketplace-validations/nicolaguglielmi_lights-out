# SPDX-License-Identifier: Apache-2.0
"""Tests for lights_out_adk.roles' turn cap (docs/adr/0090, Amendment
2026-11-14, A1), written from the ADR, never from the implementation:
every ADK role declares ADK_MAX_TURNS in roles/<name>/role.env, with its
provenance, and load_role refuses a role that does not, naming the file."""
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lights_out_adk import roles

REPO = Path(__file__).resolve().parents[4]
# ADR 0090 A1's table.
TABLE = {"product": 16, "architect": 10, "ops-triage": 4, "release": 4}
PROVENANCE = re.compile(r"^#\s*Provenance, (measurement|external|decision):")


def comment_block_above(path, key):
    """The contiguous comment lines directly above the line that sets KEY."""
    lines = Path(path).read_text().splitlines()
    at = [i for i, line in enumerate(lines) if line.strip().startswith(key + "=")]
    assert at, f"{path} does not set {key}"
    block = []
    i = at[0] - 1
    while i >= 0 and lines[i].startswith("#"):
        block.append(lines[i])
        i -= 1
    return block


class RoleEnvFiles(unittest.TestCase):
    def test_each_adk_role_declares_the_cap_of_the_table(self):
        for name, want in TABLE.items():
            with self.subTest(role=name):
                values = roles.read_env(REPO / "roles" / name / "role.env")
                self.assertEqual(values.get("ADK_MAX_TURNS"), str(want))

    def test_each_cap_is_preceded_by_its_provenance(self):
        for name in TABLE:
            with self.subTest(role=name):
                block = comment_block_above(REPO / "roles" / name / "role.env", "ADK_MAX_TURNS")
                self.assertTrue(any(PROVENANCE.match(line) for line in block),
                                f"no 'Provenance, <kind>:' line above ADK_MAX_TURNS in {name}: {block}")

    def test_load_role_reads_the_cap_of_the_table(self):
        with mock.patch.dict(os.environ, {"LIGHTS_OUT_ROOT": str(REPO)}):
            for name, want in TABLE.items():
                with self.subTest(role=name):
                    prompt = "perimeter.md" if name == "architect" else "prompt.md"
                    role = roles.load_role(name, prompt)
                    self.assertIsInstance(role.max_turns, int)
                    self.assertEqual(role.max_turns, want)

    def test_the_coding_harness_cap_is_not_the_adk_cap(self):
        # MAX_TURNS=60 stays the architect's coding-harness cap (A1).
        with mock.patch.dict(os.environ, {"LIGHTS_OUT_ROOT": str(REPO)}):
            self.assertNotEqual(roles.load_role("architect", "perimeter.md").max_turns, 60)


class LoadRoleRefuses(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "roles" / "scout").mkdir(parents=True)
        (self.root / "roles" / "scout" / "prompt.md").write_text("be brief\n")

    def load(self, env_text):
        (self.root / "roles" / "scout" / "role.env").write_text(env_text)
        with mock.patch.dict(os.environ, {"LIGHTS_OUT_ROOT": str(self.root)}):
            return roles.load_role("scout")

    def refused(self, env_text):
        with self.assertRaises(ValueError) as cm:
            self.load(env_text)
        self.assertIn("roles/scout/role.env", str(cm.exception))
        self.assertIn("ADK_MAX_TURNS", str(cm.exception))

    def test_a_declared_cap_is_an_int(self):
        role = self.load("THINKING=low\nADK_MAX_TURNS=7\n")
        self.assertEqual(role.max_turns, 7)
        self.assertIsInstance(role.max_turns, int)

    def test_a_missing_cap_is_refused(self):
        self.refused("THINKING=low\nTIMEOUT_S=900\n")

    def test_a_zero_cap_is_refused(self):
        self.refused("THINKING=low\nADK_MAX_TURNS=0\n")

    def test_a_negative_cap_is_refused(self):
        self.refused("THINKING=low\nADK_MAX_TURNS=-3\n")

    def test_a_non_integer_cap_is_refused(self):
        for bad in ("many", "2.5", ""):
            with self.subTest(value=bad):
                self.refused(f"THINKING=low\nADK_MAX_TURNS={bad}\n")


if __name__ == "__main__":
    unittest.main()
