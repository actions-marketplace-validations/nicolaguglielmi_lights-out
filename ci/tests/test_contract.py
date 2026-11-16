"""Tests for ci/checks/contract.py, written from ci/contract.sh's header,
docs/adr/0011 §4, docs/adr/0038 §5, docs/adr/0062 §1-§3 and docs/adr/0094,
never from the implementation.

The meta-gate judges a gate on its stdout alone: exactly one line, `GO:
<name>` (or `GO: <name> — <detail>`) with exit 0, or `NO-GO: <name> —
<reason>` with exit 1, no ANSI escape. A ci/ check `./go ci` already ran is
judged on its record; every other gate is run cold. Gate basenames are
unique across ci/, gates/ and verify/.
"""

import os
import shutil
import tempfile
import unittest

from ci.checks import contract


class Shape(unittest.TestCase):
    def test_the_two_good_lines(self):
        self.assertIsNone(contract.shape("x", 0, "GO: x\n"))
        self.assertIsNone(contract.shape("x", 0, "GO: x — in workbench\n"))
        self.assertIsNone(contract.shape("x", 1, "NO-GO: x — a reason\n"))
        self.assertIsNone(contract.shape("x", 0, "GO: x"))

    def test_line_count(self):
        self.assertEqual(contract.shape("x", 0, "GO: x\nGO: x\n"), "lines=2")
        self.assertEqual(contract.shape("x", 0, "GO: x\n\n"), "lines=2")
        self.assertEqual(contract.shape("x", 0, ""), "lines=0")

    def test_ansi(self):
        self.assertEqual(contract.shape("x", 0, "GO: x — \x1b[31mred\n"), "ansi")

    def test_exit_code_must_match(self):
        self.assertEqual(contract.shape("x", 1, "GO: x\n"), "GO,exit=1")
        self.assertEqual(contract.shape("x", 0, "NO-GO: x — r\n"), "NO-GO,exit=0")
        self.assertEqual(contract.shape("x", 2, "NO-GO: x — r\n"), "NO-GO,exit=2")

    def test_format(self):
        for out in ("GO: someone-else\n", "NO-GO: x —\n", "NO-GO: x\n", "GO: x —\n", "GO: x - dash\n", "ok\n",
                    "GO: xy\n"):
            self.assertEqual(contract.shape("x", 0 if out.startswith("GO") else 1, out), "format", out)


class Records(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def rec(self, gate, out="GO: %s\n", rc="0\n"):
        if out is not None:
            with open(os.path.join(self.dir, gate + ".out"), "w") as fh:
                fh.write(out % gate if "%s" in out else out)
        if rc is not None:
            with open(os.path.join(self.dir, gate + ".rc"), "w") as fh:
                fh.write(rc)

    def test_usable(self):
        self.rec("good")
        self.assertTrue(contract.usable(self.dir, "good"))
        self.rec("one", rc="1\n")
        self.assertTrue(contract.usable(self.dir, "one"))
        self.rec("max", rc="255\n")
        self.assertTrue(contract.usable(self.dir, "max"))

    def test_unusable(self):
        self.assertFalse(contract.usable("", "good"))
        self.rec("no-rc", rc=None)
        self.rec("no-out", out=None)
        self.rec("word", rc="zero\n")
        self.rec("two", rc="0\n0\n")
        self.rec("big", rc="256\n")
        self.rec("long", rc="0000\n")
        self.rec("empty", rc="")
        self.rec("neg", rc="-1\n")
        for gate in ("no-rc", "no-out", "word", "two", "big", "long", "empty", "neg", "missing"):
            self.assertFalse(contract.usable(self.dir, gate), gate)


class Discovery(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def put(self, rel):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()

    def test_every_gate_but_the_lib_and_the_contract_in_order(self):
        for rel in ("ci/lib.sh", "ci/contract.sh", "ci/b.sh", "ci/a.sh", "gates/g.sh", "verify/v.sh", "ci/x.py",
                    "gates/sub/deep.sh"):
            self.put(rel)
        files, dupes = contract.discover(self.dir)
        self.assertEqual(files, ["ci/a.sh", "ci/b.sh", "gates/g.sh", "verify/v.sh"])
        self.assertEqual(dupes, [])

    def test_a_missing_directory_is_skipped_and_a_name_twice_is_named(self):
        for rel in ("ci/same.sh", "gates/same.sh"):
            self.put(rel)
        files, dupes = contract.discover(self.dir)
        self.assertEqual(files, ["ci/same.sh", "gates/same.sh"])
        self.assertEqual(dupes, ["same"])


class Planted(unittest.TestCase):
    def test_the_planted_run_is_read_gate_by_gate(self):
        line = "NO-GO: contract — gate(s) violate the output contract: two-lines(lines=2) ansi(ansi) go-exit-1(GO,exit=1)\n"
        self.assertEqual(contract.rejected(line), {"two-lines": "lines=2", "ansi": "ansi", "go-exit-1": "GO,exit=1"})
        self.assertEqual(contract.rejected("GO: contract\n"), {})

    def test_what_the_planted_run_must_say(self):
        got = dict(contract.PLANTED_REJECTED)
        flaws = contract.planted_flaws(got)
        self.assertEqual(flaws, [])
        got["good"] = "lines=2"
        del got["ansi"]
        got["two-lines"] = "format"
        flaws = contract.planted_flaws(got)
        self.assertIn("record ansi accepted", flaws)
        self.assertIn("record good rejected", flaws)
        self.assertIn("record two-lines wrong-why", flaws)


class Probes(unittest.TestCase):
    """The lib's own side of the contract, on the real ci/lib.sh and on
    broken ones: nogo's details (ADR 0038 §5), record_check (ADR 0062 §1-§2)."""

    def test_the_real_lib(self):
        self.assertIsNone(contract.details_flaw("ci/lib.sh"))
        self.assertIsNone(contract.record_flaw("ci/lib.sh"))

    def test_broken_libs_are_caught(self):
        for broken in contract.BROKEN_NOGO.values():
            d = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, d, True)
            with open(d + "/lib.sh", "w") as fh:
                fh.write(broken)
            self.assertIsNotNone(contract.details_flaw(d + "/lib.sh"), broken)

    def test_a_record_check_that_records_nothing_is_caught(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open("ci/lib.sh") as fh:
            lib = fh.read()
        with open(d + "/lib.sh", "w") as fh:
            fh.write(lib + '\nrecord_check() { sh "$1"; }\n')
        self.assertIn("NAME.out", contract.record_flaw(d + "/lib.sh") or "")


if __name__ == "__main__":
    unittest.main()
