"""Tests for core/audit.py, written from docs/adr/0019 §6 (with the owner's
2026-09-16 addition), docs/adr/0021 §9 and docs/adr/0038 §9, never from the
implementation.

Each test runs the audit in-process in a temp root whose StateStore stub
prints state/doc.json and whose CodeHost stub prints state/host.json; a
missing file is the verb's exit 1. ci/tower.sh case (f) proves the same
audit on documents the tower itself wrote.
"""

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from core import audit

ENV = {"TICKET": "0001", "STATE_STORE": "stub-state", "CODE_HOST": "stub-host"}

# A ticket released and rolled back, every link present and agreeing.
RELEASED = {
    "id": "0001", "state": "rolled-back",
    "spec": {"sha256": "5pec", "title": "Add a reminder"},
    "task": {"role": "dev-worker", "harness": "replay", "model": "m-1"},
    "pr": {"number": 1, "url": "http://host/pr/1", "head_sha": "h1", "base_sha": "b1"},
    "ci": {"verdict": "GO: gates", "head_sha": "h1", "risk_level": "low", "decision": "auto-merge"},
    "merge": {"sha": "m1", "head_sha": "h1"},
    "release": {"version": "0.2.0", "verdict": "NO-GO: launchpad — 5%: slo", "image": "img@sha256:1",
                "numbers": ["slo: error_rate 0.3", "slo: p95 0.2"]},
}
HOST_MERGED = {"state": "closed", "merged": True, "head_sha": "h1", "merge_sha": "m1"}
HOST_OPEN = {"state": "open", "merged": False, "head_sha": "h1", "merge_sha": None}


def at(state, **changes):
    """RELEASED moved to STATE, with top-level fields replaced (None drops one)."""
    doc = copy.deepcopy(RELEASED)
    doc["state"] = state
    for key, value in changes.items():
        if value is None:
            doc.pop(key, None)
        else:
            doc[key] = value
    return doc


class AuditCase(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        for name, verb, file in (("stub-state", "get", "doc"), ("stub-host", "pr", "host")):
            (root / "adapters" / name).mkdir(parents=True)
            (root / "adapters" / name / f"{verb}.sh").write_text(
                f'f=state/{file}.json\n[ -f "$f" ] || exit 1\ncat "$f"\n')
        (root / "state").mkdir()
        self.root = root
        os.chdir(root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def run_audit(self, doc, host, env=ENV):
        for name, value in (("doc", doc), ("host", host)):
            path = self.root / "state" / f"{name}.json"
            path.unlink(missing_ok=True)
            if value is not None:
                path.write_text(value if isinstance(value, str) else json.dumps(value))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = audit.main(dict(env))
        return code, out.getvalue(), err.getvalue()

    def assertRefused(self, doc, host, *words):
        code, out, _ = self.run_audit(doc, host)
        self.assertEqual(code, 1, out)
        self.assertEqual(out.count("\n"), 1, out)
        for word in words:
            self.assertIn(word, out)


class CompleteChains(AuditCase):
    def test_a_released_chain_passes_and_prints_every_link(self):
        code, out, err = self.run_audit(RELEASED, HOST_MERGED)
        self.assertEqual((code, out), (0, ""))
        lines = err.splitlines()
        self.assertTrue(lines[0].startswith("deploy   0.2.0 rolled-back — NO-GO: launchpad"))
        self.assertIn("slo: error_rate 0.3", err)
        self.assertIn("slo: p95 0.2", err)
        self.assertIn("image: img@sha256:1", err)
        self.assertIn("← merge  m1 (code host agrees)", err)
        self.assertIn("← PR     #1 http://host/pr/1 (gates GO: gates, risk low, auto-merge; head h1)", err)
        self.assertIn("← ticket 0001 (dev-worker, harness replay, model m-1)", err)
        self.assertEqual(lines[-1], '  ← spec   sha256:5pec "Add a reminder"')

    def test_links_are_in_chain_order(self):
        _, _, err = self.run_audit(RELEASED, HOST_MERGED)
        order = [err.index(word) for word in ("deploy", "← merge", "← PR", "← ticket", "← spec")]
        self.assertEqual(order, sorted(order))

    def test_held_is_a_release_too(self):
        code, _, err = self.run_audit(at("held"), HOST_MERGED)
        self.assertEqual(code, 0)
        self.assertIn("deploy   0.2.0 held", err)

    def test_a_merge_not_released_needs_no_release(self):
        code, _, err = self.run_audit(at("merged", release=None), HOST_MERGED)
        self.assertEqual(code, 0)
        self.assertIn("merge    m1 (code host agrees), not released", err)

    def test_a_pr_that_stopped_needs_no_merge(self):
        for state in ("pr-opened", "ci-failed", "needs-human", "review"):
            with self.subTest(state=state):
                doc = at(state, release=None, merge=None)
                if state == "pr-opened":
                    doc.pop("ci")
                code, out, err = self.run_audit(doc, HOST_OPEN)
                self.assertEqual(code, 0, out)
                self.assertIn(f"PR       stopped at {state}", err)

    def test_no_model_reads_none(self):
        doc = at("held", task={"role": "dev-worker", "harness": "replay", "model": None})
        _, _, err = self.run_audit(doc, HOST_MERGED)
        self.assertIn("model none)", err)

    def test_a_review_is_a_link(self):
        doc = at("merged", release=None,
                 ci=dict(RELEASED["ci"], decision="review"),
                 review={"role": "test-reviewer", "verdict": "approved", "reason": "tests cover it"})
        code, _, err = self.run_audit(doc, HOST_MERGED)
        self.assertEqual(code, 0)
        self.assertIn("← review test-reviewer (approved): tests cover it", err)

    def test_rejected_attempts_print_newest_first(self):
        doc = at("held", rework=[
            {"attempt": 1, "head_sha": "h0", "judge": "gates", "line": "NO-GO: mutation"},
            {"attempt": 2, "head_sha": "h0b", "judge": "review", "line": "changes-requested"}])
        _, _, err = self.run_audit(doc, HOST_MERGED)
        first = err.index("← rework attempt 2 (head h0b), review: changes-requested")
        second = err.index("← rework attempt 1 (head h0), gates: NO-GO: mutation")
        self.assertLess(first, second)


class MissingLinks(AuditCase):
    def test_no_document(self):
        self.assertRefused(None, HOST_MERGED, "no document for ticket 0001 in stub-state")

    def test_a_document_that_is_not_json(self):
        self.assertRefused("{oops", HOST_MERGED, "no document for ticket 0001")

    def test_no_state(self):
        doc = at("held")
        doc.pop("state")
        self.assertRefused(doc, HOST_MERGED, "has no state")

    def test_only_opened_has_no_chain(self):
        self.assertRefused({"id": "0001", "state": "opened"}, HOST_OPEN, "only opened: no PR, no chain yet")

    def test_each_link_a_released_chain_needs(self):
        for path in (".release.verdict", ".release.version", ".merge.sha", ".merge.head_sha",
                     ".ci.verdict", ".ci.head_sha", ".pr.number", ".pr.head_sha",
                     ".spec.sha256", ".spec.title", ".task.harness"):
            with self.subTest(path=path):
                doc = copy.deepcopy(RELEASED)
                outer, inner = path.strip(".").split(".")
                doc[outer][inner] = None
                self.assertRefused(doc, HOST_MERGED, "missing link(s) in the record:", path)

    def test_every_missing_link_is_named_once(self):
        doc = at("held", merge=None)
        code, out, _ = self.run_audit(doc, HOST_MERGED)
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), "missing link(s) in the record: .merge.sha .merge.head_sha")

    def test_a_reviewed_merge_needs_the_review(self):
        for state in ("ci-passed", "ci-failed", "needs-human", "merged", "held"):
            with self.subTest(state=state):
                doc = at(state, ci=dict(RELEASED["ci"], decision="review"))
                host = HOST_MERGED if state in ("merged", "held") else HOST_OPEN
                self.assertRefused(doc, host, ".review.verdict", ".review.reason")

    def test_review_itself_has_no_review_yet(self):
        doc = at("review", release=None, merge=None, ci=dict(RELEASED["ci"], decision="review"))
        self.assertEqual(self.run_audit(doc, HOST_OPEN)[0], 0)

    def test_the_judged_sha_is_the_merged_sha(self):
        self.assertRefused(at("held", ci=dict(RELEASED["ci"], head_sha="hX")), HOST_MERGED,
                           "CI judged hX but the PR was opened at h1")
        self.assertRefused(at("held", merge={"sha": "m1", "head_sha": "hY"}), HOST_MERGED,
                           "merged head hY is not the PR head h1")

    def test_the_ports_and_ticket_must_be_set(self):
        for var in ENV:
            with self.subTest(var=var):
                env = {k: v for k, v in ENV.items() if k != var}
                code, out, _ = self.run_audit(RELEASED, HOST_MERGED, env=env)
                self.assertEqual(code, 1)
                self.assertIn(f"{var} not set", out)


class TheCodeHostDisagrees(AuditCase):
    def test_unreachable_host(self):
        self.assertRefused(RELEASED, None, "code host stub-host unreachable or PR #1 unknown to it")

    def test_host_that_does_not_answer_json(self):
        self.assertRefused(RELEASED, "<html>", "code host stub-host", "JSON")

    def test_record_merged_host_open(self):
        self.assertRefused(RELEASED, HOST_OPEN,
                           "state store says rolled-back, code host says PR #1 is open and not merged")

    def test_record_and_host_name_different_merges(self):
        self.assertRefused(RELEASED, dict(HOST_MERGED, merge_sha="m2"),
                           "state store records merge m1, code host records m2")

    def test_record_open_host_merged(self):
        doc = at("ci-failed", release=None, merge=None)
        self.assertRefused(doc, HOST_MERGED, "state store says ci-failed, code host says PR #1 "
                           "is already merged as m1")

    def test_record_and_host_name_different_heads(self):
        doc = at("pr-opened", release=None, merge=None, ci=None)
        self.assertRefused(doc, dict(HOST_OPEN, head_sha="h2"),
                           "state store records PR head h1, code host has h2")


if __name__ == "__main__":
    unittest.main()
