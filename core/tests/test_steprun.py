"""Tests for a stopped ADK run in the ledger (docs/adr/0090, Amendment
2026-11-14, A2 and A3), written from the ADR, never from the
implementation.

A3: the tower gives every step a second file, STEP_RUN. A step that fails
after a role ran writes the run there, {<field>: <task of run.json>}; the
tower appends its ledger entry to `spend` with `failed` set to the run's
`stop` (or "the run failed"), in the same write as the failed history
entry. A step that writes nothing changes nothing.
A2: the intake and perimeter steps, and clarify, refuse a run that
stopped, with the stop in STEP_WHY, and hand the run to STEP_RUN.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from core import intake, spec
from core.tests import test_tower as tt

STOP = "ADK_MAX_TURNS=10"
ARCHITECT_RUN = {"harness": "adk", "replayed": False, "provider": "gemini", "model": "m",
                 "tokens": {"input": 10, "output": 2, "total": 12}, "duration_s": 1.0}


def writes_run(obj, why=None):
    """A failing step's script: writes OBJ to STEP_RUN (and WHY to STEP_WHY), exits 1."""
    body = ""
    if obj is not None:
        body += f"printf '%s\\n' '{json.dumps(obj)}' > \"$STEP_RUN\"\n"
    if why:
        body += f"printf '%s\\n' '{why}' > \"$STEP_WHY\"\n"
    return body + "exit 1\n"


class StepRun(tt.TowerCase):
    def drafted(self, **fields):
        self.put_doc({"id": "0001", "kind": "intake", "state": "drafted",
                      "history": [{"step": "interview", "state": "drafted", "at": "t0"}], **fields})

    def test_every_step_gets_a_step_run_file_path(self):
        self.drafted()
        self.step_script("perimeter", 'printf "%s" "$STEP_RUN" > seen\nexit 1\n')
        self.run_tower("step", "0001", "perimeter")
        seen = (self.root / "seen").read_text()
        self.assertTrue(seen, "STEP_RUN is not set for the step")
        self.assertTrue(os.path.isabs(seen) or "/" in seen, seen)

    def test_a_stopped_run_is_in_the_ledger_and_the_state_does_not_move(self):
        self.drafted()
        self.step_script("perimeter", writes_run({"architect": dict(ARCHITECT_RUN, stop=STOP)},
                                                 why="the architect role failed: " + STOP + " reached"))
        code, _ = self.run_tower("step", "0001", "perimeter")
        self.assertEqual(code, 1)
        doc = self.doc()
        self.assertEqual(doc["state"], "drafted")
        self.assertEqual(self.published(), [])
        last = doc["history"][-1]
        self.assertEqual((last["step"], last["state"]), ("perimeter", "drafted"))
        self.assertEqual(last["error"], "step exited 1: the architect role failed: " + STOP + " reached")
        self.assertEqual(len(doc["spend"]), 1)
        entry = doc["spend"][0]
        self.assertEqual(entry["role"], "architect")
        self.assertEqual(entry["step"], "perimeter")
        self.assertEqual(entry["failed"], STOP)
        self.assertEqual(entry["tokens"]["total"], 12)

    def test_the_error_is_as_before_without_a_step_why(self):
        self.drafted()
        self.step_script("perimeter", writes_run({"architect": dict(ARCHITECT_RUN, stop=STOP)}))
        self.run_tower("step", "0001", "perimeter")
        self.assertEqual(self.doc()["history"][-1]["error"], "step exited 1")

    def test_a_run_without_a_stop_is_the_run_failed(self):
        self.drafted()
        self.step_script("perimeter", writes_run({"architect": ARCHITECT_RUN}))
        self.run_tower("step", "0001", "perimeter")
        self.assertEqual(self.doc()["spend"][0]["failed"], "the run failed")

    def test_the_product_field_is_the_product_role(self):
        self.put_doc({"id": "0001", "state": "requested", "history": []})
        self.step_script("clarify", writes_run({"product": dict(ARCHITECT_RUN, stop="ADK_MAX_TURNS=16")}))
        self.run_tower("step", "0001", "clarify")
        entry = self.doc()["spend"][0]
        self.assertEqual((entry["role"], entry["step"], entry["failed"]), ("product", "clarify", "ADK_MAX_TURNS=16"))

    def test_a_failing_step_that_writes_nothing_adds_no_spend(self):
        self.drafted()
        self.step_script("perimeter", writes_run(None, why="no luck"))
        self.run_tower("step", "0001", "perimeter")
        doc = self.doc()
        self.assertNotIn("spend", doc)
        self.assertEqual(doc["history"][-1]["error"], "step exited 1: no luck")

    def test_an_earlier_ledger_is_kept_and_the_entry_appended(self):
        earlier = {"step": "interview", "role": "product", "harness": "adk", "tokens": {"total": 1}}
        self.drafted(spend=[earlier])
        self.step_script("perimeter", writes_run({"architect": dict(ARCHITECT_RUN, stop=STOP)}))
        self.run_tower("step", "0001", "perimeter")
        spend = self.doc()["spend"]
        self.assertEqual(len(spend), 2)
        self.assertEqual(spend[0], earlier)
        self.assertEqual(spend[1]["role"], "architect")

    def test_each_failure_adds_its_own_entry(self):
        self.drafted()
        self.step_script("perimeter", writes_run({"architect": dict(ARCHITECT_RUN, stop=STOP)}))
        self.run_tower("step", "0001", "perimeter")
        self.run_tower("step", "0001", "perimeter")
        self.assertEqual(len(self.doc()["spend"]), 2)


class IntakeRefusesAStop(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def run_dir(self, run, name="run"):
        d = self.tmp / name
        (d / "out").mkdir(parents=True)
        (d / "out" / "run.json").write_text(json.dumps(run))
        (d / "run.err").write_text(f"harness-adk: x: {STOP} reached\n")
        return str(d)

    def stopped(self):
        return dict(ARCHITECT_RUN, stop=STOP, exit_code=1, turns=10)

    def test_interview_refuses_a_stopped_run(self):
        with self.assertRaises(intake.Refused) as cm:
            intake.interview({"id": "0100"}, self.run_dir(self.stopped()), 1, {"AGENT_HARNESS": "replay"})
        self.assertIn(STOP, str(cm.exception))

    def test_perimeter_refuses_a_stopped_run_even_at_l0(self):
        doc = {"id": "0100", "proposal": [{"n": 1, "title": "t", "problem": "p", "criteria": ["c"]}]}
        with self.assertRaises(intake.Refused) as cm:
            intake.perimeter(doc, self.run_dir(self.stopped()), 1, {"AGENT_HARNESS": "replay"}, lambda text: "GO: spec")
        self.assertIn(STOP, str(cm.exception))

    def cli(self, cmd, run, tmp_name):
        d = self.run_dir(run, tmp_name)
        doc = self.tmp / f"{tmp_name}.json"
        doc.write_text(json.dumps({"id": "0100", "proposal": [{"n": 1, "title": "t", "problem": "p", "criteria": ["c"]}]}))
        why, step_run = self.tmp / f"{tmp_name}.why", self.tmp / f"{tmp_name}.run"
        env = {"AGENT_HARNESS": "replay", "STEP_WHY": str(why), "STEP_RUN": str(step_run)}
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = intake.main([cmd, str(doc), d, "1"], env)
        return code, out.getvalue(), why, step_run

    def test_the_interview_cli_writes_the_reason_and_the_run(self):
        code, out, why, step_run = self.cli("interview", self.stopped(), "i")
        self.assertEqual((code, out), (1, ""))
        self.assertIn(STOP, why.read_text())
        run = json.loads(step_run.read_text())
        self.assertEqual(list(run), ["product"])
        self.assertEqual(run["product"]["stop"], STOP)
        self.assertEqual(run["product"]["harness"], "adk")
        self.assertEqual(run["product"]["tokens"]["total"], 12)

    def test_the_perimeter_cli_writes_the_reason_and_the_run(self):
        code, out, why, step_run = self.cli("perimeter", self.stopped(), "p")
        self.assertEqual((code, out), (1, ""))
        self.assertIn(STOP, why.read_text())
        run = json.loads(step_run.read_text())
        self.assertEqual(list(run), ["architect"])
        self.assertEqual(run["architect"]["stop"], STOP)
        self.assertEqual(run["architect"]["model"], "m")

    def test_a_missing_recording_is_not_a_run_to_charge(self):
        code, _, _, step_run = self.cli("interview", {"harness": "adk", "no_recording": True, "exit_code": 1}, "n")
        self.assertEqual(code, 1)
        self.assertFalse(step_run.exists(), "a run that never happened was written to STEP_RUN")


class ClarifyWritesTheRun(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def call(self, run):
        d = self.tmp / "run"
        (d / "out").mkdir(parents=True)
        (d / "out" / "run.json").write_text(json.dumps(run))
        (d / "run.err").write_text("harness-adk: product: failed\n")
        (self.tmp / "request.md").write_text("# 0001 — t\n")
        (self.tmp / "doc.json").write_text("{}")
        step_run = self.tmp / "step-run"
        env = {"AGENT_HARNESS": "replay", "STEP_RUN": str(step_run)}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = spec.main(["clarify", str(self.tmp / "request.md"), str(self.tmp / "doc.json"), str(d), "1"], env)
        return code, step_run

    def test_a_stopped_product_run_is_written_to_step_run(self):
        code, step_run = self.call(dict(ARCHITECT_RUN, stop="ADK_MAX_TURNS=16", exit_code=1))
        self.assertEqual(code, 1)
        run = json.loads(step_run.read_text())
        self.assertEqual(list(run), ["product"])
        self.assertEqual(run["product"]["stop"], "ADK_MAX_TURNS=16")

    def test_a_failed_product_run_is_written_to_step_run(self):
        code, step_run = self.call(dict(ARCHITECT_RUN, exit_code=1))
        self.assertEqual(code, 1)
        self.assertEqual(list(json.loads(step_run.read_text())), ["product"])

    def test_no_recording_writes_nothing(self):
        # The L0 fallback of ADR 0055 §3 is not a failure and charges nothing.
        code, step_run = self.call({"harness": "adk", "no_recording": True, "exit_code": 1})
        self.assertEqual(code, 0)
        self.assertFalse(step_run.exists())


if __name__ == "__main__":
    unittest.main()
