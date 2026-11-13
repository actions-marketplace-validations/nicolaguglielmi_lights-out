"""Tests for core/gates/deps.py, written from docs/adr/0032 and
gates/deps.sh's header, never from the implementation.

The verdict is on the diff: a finding is (ecosystem, package, advisory id),
only one HEAD has and the base does not is NO-GO; inherited ones are listed,
never gating; a lockfile new at HEAD is judged whole; the scanner's exit 0
or 1 is a scan, anything else a NO-GO, except 128 on a lockfile with no
package.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest

from core.gates import NoGo, deps
from core.tests.gitrepo import Repo


def osv_json(*findings):
    """osv-scanner's JSON for (ecosystem, package, id) findings."""
    packages = [{"package": {"ecosystem": e, "name": n, "version": "1"}, "vulnerabilities": [{"id": i}]}
                for e, n, i in findings]
    return json.dumps({"results": [{"source": {"path": "x"}, "packages": packages}]})


class FakeScanner:
    """Answers per lockfile text: a line `VULN eco pkg id` is a finding."""

    def __init__(self, rc=None, err=""):
        self.calls = []
        self.rc = rc
        self.err = err

    def __call__(self, files, out_path):
        self.calls.append([os.path.basename(f) for f in files])
        found = []
        for f in files:
            with open(f) as fh:
                found += [tuple(ln.split()[1:4]) for ln in fh if ln.startswith("VULN ")]
        with open(out_path, "w") as fh:
            fh.write(osv_json(*found))
        if self.rc is not None:
            return self.rc, self.err
        return (1 if found else 0), ""


class DepsTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.out = tempfile.mkdtemp()
        self.env = {"WORKLOAD": self.repo.dir, "WORKLOAD_LOCKFILES": "uv.lock", "GATES_OUT": self.out}

    def gate(self, base, head, scanner=None, **env):
        scanner = scanner or FakeScanner()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                result = ("GO", deps.judge([base, head], env=dict(self.env, **env), scanner=scanner))
            except NoGo as no:
                result = ("NO-GO", no.reason)
        self.err = err.getvalue()
        return result

    def record(self):
        with open(os.path.join(self.out, "deps.json")) as fh:
            return json.load(fh)

    def test_new_advisory_is_no_go_inherited_is_not(self):
        base = self.repo.commit({"uv.lock": "pkg a\nVULN PyPI old GHSA-1\n"})
        head = self.repo.commit({"uv.lock": "pkg a\nVULN PyPI old GHSA-1\nVULN PyPI new GHSA-2\n"})
        self.assertEqual(self.gate(base, head),
                         ("NO-GO", "this diff introduces 1 advisory finding(s); list on stderr"))
        self.assertIn("1 advisory finding(s) inherited from the base", self.err)
        self.assertIn("  PyPI old GHSA-1", self.err)
        self.assertIn("1 advisory finding(s) introduced by this diff:\n  PyPI new GHSA-2", self.err)
        self.assertEqual(self.record(), {"lockfiles": [f"{self.repo.dir}/uv.lock"], "new": 1, "inherited": 1,
                                         "verdict": "NO-GO"})

    def test_only_inherited_is_go(self):
        base = self.repo.commit({"uv.lock": "VULN PyPI old GHSA-1\n"})
        head = self.repo.commit({"uv.lock": "VULN PyPI old GHSA-1\nother\n"})
        self.assertEqual(self.gate(base, head), ("GO", None))
        self.assertEqual(self.record()["verdict"], "GO")
        self.assertEqual(self.record()["inherited"], 1)

    def test_the_same_package_with_another_advisory_is_new(self):
        base = self.repo.commit({"uv.lock": "VULN PyPI p GHSA-1\n"})
        head = self.repo.commit({"uv.lock": "VULN PyPI p GHSA-1\nVULN PyPI p GHSA-9\n"})
        self.assertEqual(self.gate(base, head)[0], "NO-GO")

    def test_a_fix_removing_an_advisory_is_go(self):
        base = self.repo.commit({"uv.lock": "VULN PyPI p GHSA-1\n"})
        head = self.repo.commit({"uv.lock": "clean\n"})
        self.assertEqual(self.gate(base, head), ("GO", None))
        self.assertEqual(self.record()["new"], 0)

    def test_lockfile_new_at_head_is_judged_whole(self):
        base = self.repo.commit({"README": "x"})
        head = self.repo.commit({"uv.lock": "VULN PyPI p GHSA-1\n"})
        scanner = FakeScanner()
        self.assertEqual(self.gate(base, head, scanner)[0], "NO-GO")
        self.assertIn("uv.lock is new at HEAD, judged whole", self.err)
        self.assertEqual(scanner.calls, [["uv.lock"]])

    def test_sides_come_from_git_not_the_working_tree(self):
        base = self.repo.commit({"uv.lock": "clean\n"})
        head = self.repo.commit({"uv.lock": "clean too\n"})
        with open(os.path.join(self.repo.dir, "uv.lock"), "w") as fh:
            fh.write("VULN PyPI dirty GHSA-7\n")
        self.assertEqual(self.gate(base, head), ("GO", None))

    def test_several_lockfiles_in_subdirectories(self):
        base = self.repo.commit({"a/uv.lock": "clean\n", "b/package-lock.json": "clean\n"})
        head = self.repo.commit({"b/package-lock.json": "VULN npm left-pad GHSA-3\n"})
        scanner = FakeScanner()
        got = self.gate(base, head, scanner, WORKLOAD_LOCKFILES="a/uv.lock:b/package-lock.json")
        self.assertEqual(got[0], "NO-GO")
        self.assertEqual(scanner.calls, [["uv.lock", "package-lock.json"]] * 2)
        self.assertIn("scanning 2 lockfile(s)", self.err)
        self.assertEqual(len(self.record()["lockfiles"]), 2)

    def test_untracked_lockfile_is_no_go(self):
        base = self.repo.commit({"uv.lock": "x"})
        self.assertEqual(self.gate(base, base, WORKLOAD_LOCKFILES="nope.lock"),
                         ("NO-GO", f"{self.repo.dir}/nope.lock is not tracked at {base} (from WORKLOAD_LOCKFILES)"))

    def test_empty_list_and_empty_entry(self):
        base = self.repo.commit({"uv.lock": "x"})
        self.assertEqual(self.gate(base, base, WORKLOAD_LOCKFILES=""), ("NO-GO", "WORKLOAD_LOCKFILES is empty"))
        for value in ("uv.lock::uv.lock", ":uv.lock"):
            with self.subTest(value=value):
                self.assertEqual(self.gate(base, base, WORKLOAD_LOCKFILES=value),
                                 ("NO-GO", "WORKLOAD_LOCKFILES names an empty entry"))
        self.assertEqual(self.gate(base, base, WORKLOAD_LOCKFILES="uv.lock:")[0], "GO")

    def test_scanner_failure_is_no_go_with_its_error(self):
        base = self.repo.commit({"uv.lock": "x"})
        got = self.gate(base, base, FakeScanner(rc=2, err="network down\n"))
        self.assertEqual(got, ("NO-GO", "osv-scanner exited 2; error on stderr"))
        self.assertIn("network down", self.err)

    def test_no_package_sources_is_nothing_to_judge(self):
        base = self.repo.commit({"uv.lock": "VULN PyPI p GHSA-1\n"})
        got = self.gate(base, base, FakeScanner(rc=128, err="found 0 packages\nNo package sources found\n"))
        self.assertEqual(got, ("GO", None))
        self.assertIn("list no package", self.err)
        self.assertEqual(self.gate(base, base, FakeScanner(rc=128, err="other"))[0], "NO-GO")

    def test_unreadable_scanner_output_is_no_go(self):
        base = self.repo.commit({"uv.lock": "x"})

        def garbage(files, out_path):
            with open(out_path, "w") as fh:
                fh.write("not json")
            return 0, ""
        self.assertIn("cannot be read", self.gate(base, base, garbage)[1])

    def test_tuples_reads_osv_shape_and_tolerates_absences(self):
        path = os.path.join(self.out, "t.json")
        with open(path, "w") as fh:
            fh.write(json.dumps({"results": [{"packages": [
                {"package": {"ecosystem": "PyPI", "name": "a"}, "vulnerabilities": [{"id": "X"}, {"id": "Y"}]},
                {"package": {"ecosystem": "PyPI", "name": "b"}},
                {"package": {"name": "c"}, "vulnerabilities": [{"id": "Z"}]}]}, {}]}))
        self.assertEqual(deps.tuples(path), {"PyPI a X", "PyPI a Y", "null c Z"})


if __name__ == "__main__":
    unittest.main()
