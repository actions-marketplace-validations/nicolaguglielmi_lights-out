"""Tests for core/gates/harness_proof.py, written from docs/adr/0084's
amendment of 2026-11-16 (A2) and the proof's docstring, never from the
implementation.

The proof's verdicts and its tables are judged here, with no stub and no
suite run: a defect is a row, its verdict the text the suite's NO-GO must
hold, and a row the fake must learn is a defect the fixtures name.
"""

import os
import re
import shutil
import tempfile
import unittest

from core.gates import harness_proof as proof

FAKE = "gates/harness-conformance/fake"


def fixtures_text():
    text = ""
    for root, _, files in os.walk(FAKE):
        for f in files:
            with open(os.path.join(root, f), encoding="utf-8") as fh:
                text += fh.read()
    return text


class Table(unittest.TestCase):
    def test_names_are_unique(self):
        names = [d.name for d in proof.DEFECTS]
        self.assertEqual(len(names), len(set(names)))

    def test_two_good_runs_with_and_without_mcp_sh(self):
        good = [d for d in proof.DEFECTS if d.want == "GO"]
        self.assertEqual([(d.defect, d.tweak) for d in good], [("", None), ("", proof.no_mcp_sh)])
        self.assertIs(proof.DEFECTS[0], good[0])

    def test_every_defect_the_fake_must_do_is_one_the_fixtures_know(self):
        text = fixtures_text()
        for d in proof.DEFECTS:
            if d.defect:
                self.assertRegex(text, r"(?<![\w-])%s(?![\w-])" % re.escape(d.defect), d.name)

    def test_every_no_go_names_what_it_catches(self):
        for d in proof.DEFECTS:
            if d.want != "GO":
                self.assertTrue(d.want.strip(), d.name)
        cases = {d.want.split(":")[0] for d in proof.DEFECTS if d.want.startswith("fake-cli case ")}
        for case in ("0", "1", "2", "3", "5", "6", "8", "9", "10a", "10b", "10c", "10r"):
            self.assertIn("fake-cli case " + case, cases)

    def test_a_defect_planted_in_agents_runs_without_mcp_sh(self):
        for d in proof.DEFECTS:
            if d.defect.startswith("agents-mcp-"):
                self.assertIs(d.tweak, proof.agents_shim, d.name)

    def test_the_probe_rows_open_each_way_at_least_once(self):
        opened = set()
        for row in proof.PROBES:
            self.assertTrue(set(row.open.split()) <= set(proof.WAYS), row.name)
            opened |= set(row.open.split())
        self.assertEqual(opened, set(proof.WAYS))
        self.assertEqual(proof.PROBES[0].open, "")
        self.assertEqual(sum(1 for r in proof.PROBES if r.cut), 1)
        self.assertEqual(sum(1 for r in proof.PROBES if r.nocase), 1)


class Verdicts(unittest.TestCase):
    GO = proof.GO_PREFIX + "12 s"

    def test_the_good_run(self):
        self.assertIsNone(proof.verdict_flaw("good", "GO", 0, self.GO, 2))
        self.assertIn("was refused", proof.verdict_flaw("good", "GO", 1, "NO-GO: harness-conformance — x", 2))
        self.assertIn("was refused", proof.verdict_flaw("good", "GO", 1, self.GO, 2))
        self.assertIn("was refused", proof.verdict_flaw("good", "GO", 0, "GO: harness-conformance — other, 1 s", 2))
        self.assertIn("did not remove egress exactly at its start and on exit",
                      proof.verdict_flaw("good", "GO", 0, self.GO, 1))

    def test_a_defect(self):
        line = proof.NOGO_PREFIX + "fake-cli case 2: hooks.log has no 'DENY <tool> git push' line"
        self.assertIsNone(proof.verdict_flaw("d", "fake-cli case 2:", 1, line, 0))
        self.assertIn("accepted a harness that is wrong (d): exit 0", proof.verdict_flaw("d", "fake-cli case 2:", 0, self.GO, 2))
        self.assertIn("for another reason than expected", proof.verdict_flaw("d", "fake-cli case 3:", 1, line, 0))
        self.assertIn("for another reason than expected",
                      proof.verdict_flaw("d", "harness-conformance", 1, "NO-GO: other — harness-conformance", 0))

    def test_the_probe_must_print_exactly_eight_lines(self):
        want = proof.expected_lines("a b")
        self.assertEqual(want.splitlines()[:3], ["egress-probe a open", "egress-probe b open", "egress-probe c blocked"])
        self.assertEqual(len(want.splitlines()), 8)
        self.assertIsNone(proof.probe_flaw("x", want, want + "\n", "s3cret"))
        self.assertIn("verdict is wrong", proof.probe_flaw("x", want, want + "\nmore\n", "s3cret"))
        self.assertIn("printed what it read", proof.probe_flaw("x", want, want + "\ns3cret\n", "s3cret"))
        self.assertEqual(proof.expected_lines(""), "\n".join("egress-probe %s blocked" % c for c in "abcdefgh"))


class Tree(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.t, True)
        proof.build_tree(self.t)

    def test_the_tree_holds_one_cli_harness_and_its_contract(self):
        from core.gates import harness
        self.assertEqual(harness.discover(self.t + "/adapters"), ["fake-cli"])
        harness.check_contract("fake-cli", self.t + "/adapters")
        for f in ("gates/harness-conformance.sh", "core/gates/harness.py", "ci/lib.sh", "c/mcp.json",
                  "c/mcp/notes.py", "proof-egress.py", "adapters/fake-cli/hooks/guard.sh"):
            self.assertTrue(os.path.isfile(os.path.join(self.t, f)), f)
        self.assertEqual(harness.with_mcp_sh(self.t + "/adapters"), "fake-cli")

    def test_no_egress_key(self):
        from core.gates import NoGo, harness
        proof.no_egress_key(self.t)
        with self.assertRaises(NoGo) as no:
            harness.check_contract("fake-cli", self.t + "/adapters")
        self.assertIn("has no EGRESS=", no.exception.reason)

    def test_no_mcp_sh_keeps_one_on_an_adapter_that_is_no_harness(self):
        from core.gates import harness
        proof.no_mcp_sh(self.t)
        self.assertEqual(harness.with_mcp_sh(self.t + "/adapters"), "fake-replay")
        self.assertEqual(harness.discover(self.t + "/adapters"), ["fake-cli"])

    def test_agents_shim_keeps_the_real_module_beside_it(self):
        proof.agents_shim(self.t)
        self.assertTrue(os.path.isfile(self.t + "/core/agents_real.py"))
        with open(self.t + "/core/agents.py", encoding="utf-8") as fh:
            self.assertIn("agents_real.py", fh.read())

    def test_push_only_guard(self):
        proof.push_only_guard(self.t)
        with open(self.t + "/adapters/fake-cli/hooks/guard.sh", encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("git push", text)
        self.assertNotIn(".env", text)


if __name__ == "__main__":
    unittest.main()
