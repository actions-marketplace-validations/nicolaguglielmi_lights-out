"""Tests for core/releases.py, written from docs/adr/0020 §4 (the record
and its brief), docs/adr/0047 §2 P2 (the release log) and §3 (who
answered), and ticket 0008 (the record against the plane), never from the
implementation."""

import contextlib
import io
import json
import os
import re
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from core import releases

STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
STAGES = [{"pct": 5, "verdict": "GO", "numbers": ["slo: error_rate 0.001"]},
          {"pct": 25, "verdict": "GO", "numbers": []}]


class ReleasesCase(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        self.env = {"RELEASE_RECORD": "crew/release.json", "RELEASES_LOG": "crew/releases.jsonl",
                    "CANARY_VERSION": "v2", "STABLE_VERSION": "v1", "DELIVERY": "stub-delivery"}

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def call(self, *argv, stdin="", env=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()), \
                unittest.mock.patch("sys.stdin", io.StringIO(stdin)):
            code = releases.main(list(argv), dict(self.env if env is None else env))
        return code, out.getvalue()

    def record(self):
        return json.loads(Path("crew/release.json").read_text())

    def log(self):
        path = Path("crew/releases.jsonl")
        return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


class Record(ReleasesCase):
    def test_the_record_has_the_shape_launchpad_writes(self):
        self.assertEqual(self.call("record", "held", "25", json.dumps(STAGES), "img@sha")[0], 0)
        self.assertEqual(self.record(), {"version": "v2", "stable": "v1", "stages": STAGES, "verdict": "held",
                                         "held_at": 25, "image": "img@sha", "sbom": None})

    def test_the_record_names_the_sbom_attestation_when_the_registry_gives_one(self):
        # docs/adr/0072 §2: the release record gains `sbom`, the digest of the attestation.
        self.call("record", "held", "25", "[]", "img@sha", "sha256:att")
        self.assertEqual(self.record()["sbom"], "sha256:att")
        self.call("record", "held", "25", "[]", "img@sha", "")
        self.assertIsNone(self.record()["sbom"])


class Brief(ReleasesCase):
    def test_the_l0_brief_names_the_version_and_every_stage_with_its_numbers(self):
        self.call("record", "held", "25", json.dumps(STAGES), "img@sha")
        code, out = self.call("brief")
        self.assertEqual(code, 0)
        for needle in ("v2", "img@sha", "v1", "5%: GO", "25%: GO", "slo: error_rate 0.001", "Recommendation: GO"):
            self.assertIn(needle, out)


class Plane(ReleasesCase):
    def setUp(self):
        super().setUp()
        self.call("record", "held", "25", "[]", "")

    def test_the_held_canary_at_its_weight_passes(self):
        self.assertEqual(self.call("plane", stdin='{"canary": "v2", "weight": 25}'), (0, ""))
        self.assertEqual(self.call("plane", stdin='{"canary": "v2", "weight": "25"}')[0], 0)

    def test_another_canary_or_weight_refuses_and_says_what_the_plane_has(self):
        code, out = self.call("plane", stdin='{"canary": null, "weight": 0}')
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), "the record holds v2 at 25%, the plane has canary none at 0%; nothing moved")
        self.assertEqual(self.call("plane", stdin='{"canary": "v2", "weight": 100}')[0], 1)

    def test_no_json_from_the_plane_refuses(self):
        code, out = self.call("plane", stdin="oops")
        self.assertEqual((code, out.strip()), (1, "adapters/stub-delivery/status.sh did not print JSON"))

    def test_a_held_record_without_held_at_refuses(self):
        self.call("record", "held", "", "[]", "")
        code, out = self.call("plane", stdin='{"canary": "v2", "weight": 25}')
        self.assertEqual((code, out.strip()), (1, "crew/release.json is held but names no held_at"))


class Answer(ReleasesCase):
    def setUp(self):
        super().setUp()
        self.call("record", "held", "25", "[]", "")

    def test_go_is_promoted_with_who_and_through_what(self):
        self.env.update(GO_FOR_LAUNCH_BY="ada@example.org", GO_FOR_LAUNCH_VIA="console")
        self.assertEqual(self.call("answer", "GO")[0], 0)
        promoted = self.record()["promoted"]
        self.assertEqual((promoted["weight"], promoted["by"], promoted["via"]), (100, "ada@example.org", "console"))
        last = self.log()[-1]
        self.assertEqual({k: last[k] for k in ("kind", "version", "answer", "by", "via")},
                         {"kind": "answer", "version": "v2", "answer": "GO", "by": "ada@example.org", "via": "console"})

    def test_no_go_is_rejected_by_unauthenticated_from_the_cli_by_default(self):
        self.call("answer", "NO-GO")
        self.assertNotIn("promoted", self.record())
        self.assertEqual({k: self.record()["rejected"][k] for k in ("by", "via")},
                         {"by": "unauthenticated", "via": "cli"})
        self.assertEqual(self.log()[-1]["answer"], "NO-GO")

    def test_anything_else_is_a_usage_error(self):
        self.assertEqual(self.call("answer", "maybe")[0], 2)
        self.assertEqual(self.call("record", "held")[0], 2)
        self.assertEqual(self.call()[0], 2)



if __name__ == "__main__":
    unittest.main()
