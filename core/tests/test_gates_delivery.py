"""Tests for core/gates/delivery.py, written from docs/adr/0026, docs/adr/
0057 §9 and gates/delivery-conformance.sh's header, never from the
implementation.

A plane whose launchpad honours the contract gets GO and a conformance
record of the adapter's hash; one broken in one behaviour gets a NO-GO
naming the case; the preflight names its fix; the flags are restored on any
exit.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest

from core.gates import NoGo, delivery
from core.gates.readiness import adapter_hash


class FakePlane:
    def __init__(self, record, brk=None):
        self.record, self.brk = record, brk
        self.freeze, self.ks_on = False, True
        self.stable, self.canary, self.weight = "1.0.0", None, 0
        self.calls = []

    def write(self, **doc):
        with open(self.record, "w") as fh:
            json.dump(doc, fh)

    def run(self, argv, env=None, quiet=False):
        self.calls.append(argv)
        if argv[0] == "make" and argv[2] == "release":
            version, tag = argv[3].split("=", 1)[1], argv[4].split("=", 1)[1]
            if self.brk != "no-rollback":
                self.canary, self.weight = None, 0
            if self.freeze and self.brk != "freeze-ignored":
                return 2, "NO-GO: launchpad — release-freeze is on"
            if tag == "sha-" + "0" * 40 and self.brk != "unsigned-accepted":
                return 2, "NO-GO: launchpad — unsigned image"
            if self.ks_on:
                self.weight = 5 if self.brk == "no-rollback" else 0
                self.write(verdict="rolled-back", stable=self.stable, version=version)
                return 2, "NO-GO: launchpad — 5%: the error rate is over the SLO"
            self.canary, self.weight = version, 25
            self.write(verdict="promoted" if self.brk == "no-hold" else "held", held_at=25, stable=self.stable,
                       version=version)
            return 0, "GO: launchpad — held at 25%"
        if argv[0] == "make" and argv[2] == "promote":
            if self.brk == "promote-fails" or (env or {}).get("GO_FOR_LAUNCH") != "GO":
                return 2, "NO-GO: promote — no"
            self.weight = 100
            return 0, "GO: promote"
        if argv[0] == "git":
            return 0, "abc123"
        verb, args = os.path.basename(argv[1])[:-3], argv[2:]
        if verb == "evaluate":
            on = self.freeze if args[0] == "release-freeze" else self.ks_on
            return 0, "true" if on else "false"
        if verb == "set":
            if args[0] == "release-freeze":
                self.freeze = args[1] == "on"
            else:
                self.ks_on = args[1] == "on"
            return 0, ""
        if verb == "status":
            weight = str(self.weight) if self.brk == "shape" else self.weight
            return 0, json.dumps({"stable": self.stable, "canary": self.canary, "weight": weight})
        raise AssertionError(argv)

    def healthz(self, url):
        return self.canary if self.weight == 100 else self.stable


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, cwd)
        os.makedirs("adapters/canary")
        with open("adapters/canary/rollback.sh", "w") as fh:
            fh.write("echo rollback\n")
        self.env = {"DELIVERY": "canary", "FLAGS": "switches", "WORKLOAD_KILL_SWITCH": "kill", "CANARY_VERSION": "2.0.0",
                    "CANARY_TAG": "sha-1234", "RELEASE_RECORD": "release.json", "CONFORMANCE_DIR": "records"}

    def suite(self, plane=None, **env):
        self.plane = plane or FakePlane("release.json")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                got = ("GO", delivery.judge([], env=dict(self.env, **env), plane=self.plane))
            except NoGo as no:
                got = ("NO-GO", no.reason)
        self.err = err.getvalue()
        return got

    def test_a_fair_plane_is_go_and_recorded(self):
        self.assertEqual(self.suite(), ("GO", None))
        with open("records/delivery-canary.env") as fh:
            record = dict(line.rstrip("\n").split("=", 1) for line in fh)
        self.assertEqual(record["ADAPTER"], "canary")
        self.assertEqual(record["HASH"], adapter_hash("adapters/canary"))
        self.assertRegex(record["AT"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertIn("case6 reports-state", self.err)
        self.assertEqual((self.plane.freeze, self.plane.ks_on), (False, False))
        releases = [c for c in self.plane.calls if c[:3] == ["make", "--no-print-directory", "release"]]
        self.assertEqual(len(releases), 5)
        self.assertEqual(releases[-1][3:], ["CANARY_VERSION=1.0.0", "CANARY_TAG=sha-" + "0" * 40])

    def test_each_break_names_its_case(self):
        for brk, case in (("no-rollback", "case1 rejects-and-rolls-back"), ("no-hold", "case2 promotes"),
                          ("promote-fails", "case2 promotes"), ("freeze-ignored", "case3 respects-the-freeze"),
                          ("unsigned-accepted", "case5 unsigned-image"), ("shape", "preflight")):
            with self.subTest(brk=brk):
                verdict, reason = self.suite(FakePlane("release.json", brk))
                self.assertEqual(verdict, "NO-GO", reason)
                self.assertTrue(reason.startswith(case + ":"), reason)
                self.assertFalse(self.plane.freeze, brk)
                self.assertFalse(os.path.exists("records/delivery-canary.env"))

    def test_preflight_names_the_fix(self):
        plane = FakePlane("release.json")
        plane.freeze = True
        self.assertIn("run: sh adapters/switches/set.sh release-freeze off", self.suite(plane)[1])
        plane = FakePlane("release.json")
        plane.ks_on = False
        self.assertIn("kill 2.0.0 already evaluates false, want true", self.suite(plane)[1])
        plane = FakePlane("release.json")
        plane.weight = 25
        self.assertIn("reports weight 25, want 0; run: sh adapters/canary/rollback.sh", self.suite(plane)[1])

    def test_required_settings(self):
        for key in ("DELIVERY", "FLAGS", "WORKLOAD_KILL_SWITCH", "CANARY_VERSION"):
            with self.subTest(key=key):
                self.assertTrue(self.suite(**{key: ""})[1].startswith(key))

    def test_canary_tag_defaults_to_head(self):
        self.suite(CANARY_TAG="")
        release = next(c for c in self.plane.calls if c[:3] == ["make", "--no-print-directory", "release"])
        self.assertEqual(release[4], "CANARY_TAG=sha-abc123")

    def test_status_shape(self):
        plane = FakePlane("release.json")
        for text, why in (("not json", "did not print valid JSON"), ("[1]", "did not print valid JSON"),
                          ('{"stable": "a", "weight": 0}', "printed keys [stable,weight]"),
                          ('{"stable": "a", "canary": 3, "weight": 0}', "wrong shape"),
                          ('{"stable": "a", "canary": null, "weight": 101}', "wrong shape"),
                          ('{"stable": "a", "canary": null, "weight": 2.5}', "wrong shape")):
            with self.subTest(text=text):
                plane.run = lambda argv, env=None, quiet=False, t=text: (0, t) if "status" in argv[-1] else (0, "false")
                with self.assertRaises(NoGo) as no:
                    delivery.Suite(self.env, plane).status("x")
                self.assertIn(why, no.exception.reason)


if __name__ == "__main__":
    unittest.main()
