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
                                         "held_at": 25, "image": "img@sha", "sbom": None, "dast": None,
                                         "reason": None})

    def test_the_record_names_the_sbom_attestation_when_the_registry_gives_one(self):
        # docs/adr/0072 §2: the release record gains `sbom`, the digest of the attestation.
        self.call("record", "held", "25", "[]", "img@sha", "sha256:att")
        self.assertEqual(self.record()["sbom"], "sha256:att")
        self.call("record", "held", "25", "[]", "img@sha", "")
        self.assertIsNone(self.record()["sbom"])

    def test_the_record_keeps_the_staging_dast_line(self):
        # docs/adr/0072 §3-§4: the gate's stdout line is stored in the release record.
        line = "GO: dast — canary v2: nothing new (3 inherited from v1)"
        self.call("record", "held", "25", "[]", "img@sha", "", line)
        self.assertEqual(self.record()["dast"], line)


class Stage(ReleasesCase):
    def test_a_stage_appends_its_pct_verdict_and_slo_lines(self):
        # docs/adr/0020 §4: one entry per verified stage with its verdict and the `slo:` lines behind it;
        # docs/adr/0080 §1: and its times and its numbers as structures.
        code, out = self.call("stage", json.dumps([{"pct": 5, "verdict": "GO: slo", "numbers": []}]), "25",
                              "NO-GO: slo — error_rate", stdin="noise\nslo: error_rate canary=1.0\nslo: p99 ok\n")
        self.assertEqual(code, 0)
        entries = json.loads(out)
        self.assertEqual(entries[0], {"pct": 5, "verdict": "GO: slo", "numbers": []})
        last = entries[1]
        self.assertEqual({k: last[k] for k in ("pct", "verdict", "numbers")},
                         {"pct": 25, "verdict": "NO-GO: slo — error_rate",
                          "numbers": ["slo: error_rate canary=1.0", "slo: p99 ok"]})
        self.assertIsNone(last["started_at"])
        self.assertRegex(last["judged_at"], STAMP)
        self.assertEqual(last["slo"], [])  # both lines are off the shape: nothing parsed, both kept in numbers

    def stage(self, stderr, started_at="2026-11-12T10:00:00Z", env=None):
        argv = ["stage", "[]", "5", "GO: slo"] + ([started_at] if started_at is not None else [])
        code, out = self.call(*argv, stdin=stderr, env={**self.env, **(env or {})})
        self.assertEqual(code, 0)
        return json.loads(out)[0]

    def test_the_times_started_at_is_the_argument_and_judged_at_a_utc_stamp(self):
        entry = self.stage("")
        self.assertEqual(entry["started_at"], "2026-11-12T10:00:00Z")
        self.assertRegex(entry["judged_at"], STAMP)
        self.assertIsNone(self.stage("", started_at=None)["started_at"])
        self.assertIsNone(self.stage("", started_at="")["started_at"])

    def test_slo_is_one_object_per_line_in_order_with_the_numbers_the_line_prints(self):
        lines = ["slo: traffic canary(v2)=12.5 stable(v1)=250.0",
                 "slo: error_rate canary(v2)=0.004 stable(v1)=0.000",
                 "slo: latency_p95 canary(v2)=0.31 stable(v1)=0.25"]
        entry = self.stage("noise\n" + "\n".join(lines) + "\n", env={"ERROR_RATE_MAX_DELTA": "0.01",
                                                                      "LATENCY_P95_MAX_DELTA": "0.2"})
        self.assertEqual(entry["numbers"], lines)  # unchanged
        self.assertEqual(entry["slo"], [
            {"query": "traffic", "canary": 12.5, "stable": 250.0, "delta": -237.5, "max_delta": None},
            {"query": "error_rate", "canary": 0.004, "stable": 0.0, "delta": 0.004, "max_delta": 0.01},
            {"query": "latency_p95", "canary": 0.31, "stable": 0.25, "delta": 0.06, "max_delta": 0.2}])
        for row in entry["slo"]:
            for key in ("canary", "stable", "delta", "max_delta"):
                self.assertIn(type(row[key]), (float, type(None)))

    def test_delta_is_rounded_to_three_decimals(self):
        entry = self.stage("slo: error_rate canary(v2)=0.30000 stable(v1)=0.10000\n")
        self.assertEqual(entry["slo"][0]["delta"], 0.2)
        entry = self.stage("slo: error_rate canary(v2)=0.0123456 stable(v1)=0.0000001\n")
        self.assertEqual(entry["slo"][0]["delta"], round(0.0123456 - 0.0000001, 3))

    def test_no_data_is_null_and_so_is_the_delta(self):
        entry = self.stage("slo: error_rate canary(v2)=no data stable(v1)=0.000\n"
                           "slo: latency_p95 canary(v2)=0.2 stable(v1)=no data\n"
                           "slo: traffic canary(v2)=no data stable(v1)=no data\n")
        self.assertEqual([(r["canary"], r["stable"], r["delta"]) for r in entry["slo"]],
                         [(None, 0.0, None), (0.2, None, None), (None, None, None)])
        self.assertEqual(len(entry["numbers"]), 3)

    def test_max_delta_comes_from_the_policy_env_per_query(self):
        line = "slo: error_rate canary(v2)=0.1 stable(v1)=0.0\nslo: latency_p95 canary(v2)=0.1 stable(v1)=0.0\n"
        entry = self.stage(line, env={"ERROR_RATE_MAX_DELTA": "0.05", "LATENCY_P95_MAX_DELTA": "0.5"})
        self.assertEqual([r["max_delta"] for r in entry["slo"]], [0.05, 0.5])
        for env in ({}, {"ERROR_RATE_MAX_DELTA": "", "LATENCY_P95_MAX_DELTA": ""}):
            self.assertEqual([r["max_delta"] for r in self.stage(line, env=env)["slo"]], [None, None])
        # one set, the other not
        entry = self.stage(line, env={"ERROR_RATE_MAX_DELTA": "0.05"})
        self.assertEqual([r["max_delta"] for r in entry["slo"]], [0.05, None])

    def test_traffic_and_other_queries_have_no_max_delta_whatever_the_env(self):
        entry = self.stage("slo: traffic canary(v2)=1.0 stable(v1)=2.0\nslo: saturation canary(v2)=1.0 stable(v1)=2.0\n",
                           env={"ERROR_RATE_MAX_DELTA": "0.05", "LATENCY_P95_MAX_DELTA": "0.5"})
        self.assertEqual([(r["query"], r["max_delta"]) for r in entry["slo"]], [("traffic", None), ("saturation", None)])

    def test_a_line_off_the_shape_adds_nothing_to_slo_but_stays_in_numbers(self):
        lines = ["slo: error_rate 0.001", "slo: error_rate canary(v2)=abc stable(v1)=0.0",
                 "slo: error_rate canary(v2)=0.1 stable(v1)=0.0"]
        entry = self.stage("\n".join(lines) + "\nnot an slo line canary(v2)=0.1 stable(v1)=0.0\n")
        self.assertEqual(entry["numbers"], lines)
        self.assertEqual([r["query"] for r in entry["slo"]], ["error_rate"])
        self.assertEqual(entry["slo"][0]["canary"], 0.1)

    def test_in_progress_is_recorded_and_never_logged(self):
        self.call("record", "in-progress", "", "[]", "")
        self.assertEqual(self.record()["verdict"], "in-progress")
        self.assertIsNone(self.record()["held_at"])
        self.assertEqual(self.log(), [])

    def test_every_final_record_is_appended_with_time_and_ticket(self):
        self.call("record", "rolled-back", "", "[]", "")
        self.env["RELEASE_TICKET"] = "0001"
        self.call("record", "held", "25", "[]", "")
        first, second = self.log()
        self.assertEqual((first["kind"], first["ticket"], first["record"]["verdict"]), ("release", None, "rolled-back"))
        self.assertEqual((second["ticket"], second["record"]), ("0001", self.record()))
        self.assertRegex(second["at"], STAMP)


class Running(ReleasesCase):
    """docs/adr/0080 §2: the in-progress record names the running stage."""

    def test_running_writes_the_in_progress_record_with_the_running_stage_and_the_stages_so_far(self):
        code, _ = self.call("running", json.dumps(STAGES), "50", "2026-11-12T10:00:00Z", "60", "img@sha")
        self.assertEqual(code, 0)
        rec = self.record()
        self.assertEqual(rec["verdict"], "in-progress")
        self.assertEqual(rec["running"], {"pct": 50, "started_at": "2026-11-12T10:00:00Z", "judge_after_s": 60})
        self.assertIs(type(rec["running"]["pct"]), int)
        self.assertIs(type(rec["running"]["judge_after_s"]), int)
        self.assertEqual(rec["stages"], STAGES)
        self.assertEqual((rec["version"], rec["stable"], rec["image"]), ("v2", "v1", "img@sha"))

    def test_running_appends_nothing_to_the_log(self):
        self.call("running", "[]", "5", "2026-11-12T10:00:00Z", "60", "img@sha")
        self.call("running", "[]", "25", "2026-11-12T10:01:00Z", "60", "img@sha", "GO: dast — x")
        self.assertEqual(self.log(), [])
        self.assertEqual(self.record()["running"]["pct"], 25)

    def test_the_next_running_replaces_the_last_and_a_final_record_has_none(self):
        self.call("running", "[]", "5", "2026-11-12T10:00:00Z", "60", "img@sha")
        self.call("record", "held", "5", "[]", "img@sha")
        self.assertNotIn("running", self.record())
        self.assertEqual(len(self.log()), 1)
        self.call("running", "[]", "5", "2026-11-12T10:00:00Z", "60", "img@sha")
        self.call("record", "rolled-back", "", "[]", "img@sha")
        self.assertNotIn("running", self.record())

    def test_running_without_its_arguments_is_a_usage_error(self):
        self.assertEqual(self.call("running", "[]", "5")[0], 2)


class Reason(ReleasesCase):
    """docs/adr/0080 §3: a rolled-back record says why."""

    def test_rolled_back_takes_the_reason_from_the_env(self):
        env = {**self.env, "RELEASE_REASON": "5%: error_rate 1.000"}
        self.call("record", "rolled-back", "", "[]", "img@sha", env=env)
        self.assertEqual(self.record()["reason"], "5%: error_rate 1.000")
        self.assertEqual(self.log()[-1]["record"]["reason"], "5%: error_rate 1.000")
        self.assertNotIn("running", self.record())

    def test_rolled_back_without_a_reason_has_the_key_null(self):
        self.call("record", "rolled-back", "", "[]", "img@sha")
        self.assertIn("reason", self.record())
        self.assertIsNone(self.record()["reason"])

    def test_a_held_record_has_reason_null_even_with_the_env_set(self):
        self.call("record", "held", "25", "[]", "img@sha", env={**self.env, "RELEASE_REASON": "stale words"})
        self.assertIn("reason", self.record())
        self.assertIsNone(self.record()["reason"])

    def test_in_progress_has_no_reason(self):
        self.call("record", "in-progress", "", "[]", "", env={**self.env, "RELEASE_REASON": "stale words"})
        self.assertIsNone(self.record().get("reason"))


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


class AnswerWhy(ReleasesCase):
    """docs/adr/0079 §1: reason, brief_sha256 and brief_author beside by and via."""

    BRIEF = "Release v2: stages 5% and 25% GO. Recommend promoting.\n".encode()

    def setUp(self):
        super().setUp()
        self.call("record", "held", "25", "[]", "")
        self.out_dir = Path(self._tmp.name) / "promote"
        self.out_dir.mkdir()
        self.env["PROMOTE_OUT"] = str(self.out_dir)

    def brief(self, author="alice <alice@example.org>\nsecond line\n"):
        (self.out_dir / "brief.md").write_bytes(self.BRIEF)
        if author is not None:
            (self.out_dir / "brief.author").write_text(author)

    def answered(self, answer):
        self.assertEqual(self.call("answer", answer)[0], 0)
        key = "promoted" if answer == "GO" else "rejected"
        line = self.log()[-1]
        self.assertEqual(line["kind"], "answer")
        return self.record()[key], line

    def test_go_records_reason_brief_sha_and_author_in_record_and_log(self):
        import hashlib
        self.brief()
        self.env["GO_FOR_LAUNCH_REASON"] = "  numbers hold at 25%  \n"
        want = {"reason": "numbers hold at 25%", "brief_sha256": hashlib.sha256(self.BRIEF).hexdigest(),
                "brief_author": "alice <alice@example.org>"}
        entry, line = self.answered("GO")
        self.assertEqual({k: entry[k] for k in want}, want)
        self.assertEqual({k: line[k] for k in want}, want)

    def test_no_go_records_them_in_rejected_and_the_log(self):
        import hashlib
        self.brief()
        self.env["GO_FOR_LAUNCH_REASON"] = "p99 too close to the limit"
        want = {"reason": "p99 too close to the limit", "brief_sha256": hashlib.sha256(self.BRIEF).hexdigest(),
                "brief_author": "alice <alice@example.org>"}
        entry, line = self.answered("NO-GO")
        self.assertEqual({k: entry[k] for k in want}, want)
        self.assertEqual({k: line[k] for k in want}, want)
        self.assertNotIn("promoted", self.record())

    def test_an_empty_or_blank_or_absent_reason_is_null(self):
        self.brief()
        for reason in (None, "", "   \n\t"):
            self.call("record", "held", "25", "[]", "")
            env = dict(self.env)
            env.pop("GO_FOR_LAUNCH_REASON", None)
            if reason is not None:
                env["GO_FOR_LAUNCH_REASON"] = reason
            self.assertEqual(self.call("answer", "NO-GO", env=env)[0], 0, reason)
            self.assertIsNone(self.record()["rejected"]["reason"], repr(reason))
            self.assertIsNone(self.log()[-1]["reason"], repr(reason))

    def test_without_a_brief_the_sha_and_author_are_null(self):
        entry, line = self.answered("GO")
        for got in (entry, line):
            self.assertIsNone(got["brief_sha256"])
            self.assertIsNone(got["brief_author"])
            self.assertIn("brief_author", got)
            self.assertIn("brief_sha256", got)

    def test_a_brief_without_an_author_gives_a_sha_and_a_null_author(self):
        import hashlib
        self.brief(author=None)
        entry, _ = self.answered("GO")
        self.assertEqual(entry["brief_sha256"], hashlib.sha256(self.BRIEF).hexdigest())
        self.assertIsNone(entry["brief_author"])

    def test_the_existing_fields_stay(self):
        self.brief()
        self.env.update(GO_FOR_LAUNCH_BY="ada@example.org", GO_FOR_LAUNCH_VIA="console")
        entry, line = self.answered("NO-GO")
        self.assertEqual((entry["by"], entry["via"]), ("ada@example.org", "console"))
        self.assertEqual((line["by"], line["via"], line["answer"]), ("ada@example.org", "console", "NO-GO"))


if __name__ == "__main__":
    unittest.main()


class ErrorRateWithTraffic(ReleasesCase):
    """docs/adr/0080 §1: an error_rate with no data on a side whose traffic
    is above zero is 0, as verify/slo.sh judges it; with no traffic, or no
    traffic line, it stays null."""

    def slo(self, stderr):
        code, out = self.call("stage", "[]", "5", "NO-GO: slo", "t", stdin=stderr,
                              env=dict(self.env, ERROR_RATE_MAX_DELTA="0.01"))
        self.assertEqual(code, 0)
        return {m["query"]: m for m in json.loads(out)[0]["slo"]}

    def test_no_data_with_traffic_is_zero(self):
        got = self.slo("slo: traffic canary(v2)=0.192 stable(v1)=4.291\n"
                       "slo: error_rate canary(v2)=1.000 stable(v1)=no data\n")
        self.assertEqual((got["error_rate"]["stable"], got["error_rate"]["delta"]), (0.0, 1.0))

    def test_no_data_without_traffic_stays_null(self):
        got = self.slo("slo: traffic canary(v2)=0.192 stable(v1)=no data\n"
                       "slo: error_rate canary(v2)=1.000 stable(v1)=no data\n")
        self.assertEqual((got["error_rate"]["stable"], got["error_rate"]["delta"]), (None, None))
        got = self.slo("slo: error_rate canary(v2)=no data stable(v1)=0.000\n")
        self.assertIsNone(got["error_rate"]["canary"])

    def test_latency_no_data_stays_null_even_with_traffic(self):
        got = self.slo("slo: traffic canary(v2)=1.0 stable(v1)=1.0\n"
                       "slo: latency_p95 canary(v2)=no data stable(v1)=0.1\n")
        self.assertIsNone(got["latency_p95"]["canary"])

