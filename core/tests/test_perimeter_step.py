"""core/steps/perimeter.sh (docs/adr/0090, second amendment A6): the architect
searches the workload's files only, so a step with no workload refuses before
running the role, naming WORKLOAD in STEP_WHY, and writes nothing."""

import json
import os
import subprocess  # nosec B404 - the step under test is a script
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class PerimeterStepScope(unittest.TestCase):
    def run_step(self, workload):
        ticket = f"t{os.getpid()}"  # its own .crew/<ticket>, absent before the run
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp, "doc.json")
            doc.write_text(json.dumps({"id": ticket, "kind": "intake", "state": "drafted",
                                       "proposal": [{"n": 1, "title": "t", "problem": "p", "criteria": ["c"]}]}))
            why = Path(tmp, "why")
            env = {k: v for k, v in os.environ.items() if k not in ("WORKLOAD", "INTAKE_SCOPE")}
            env.update(TICKET=ticket, DOC_FILE=str(doc), AGENT_HARNESS="replay", STEP_WHY=str(why))
            if workload is not None:
                env["WORKLOAD"] = workload
            ran = subprocess.run(["sh", "core/steps/perimeter.sh"], cwd=REPO, env=env,  # nosec B603 B607
                                 capture_output=True, text=True, check=False)
            return ran, (why.read_text() if why.is_file() else ""), (REPO / ".crew" / ticket).exists()

    def test_no_workload_refuses_naming_it(self):
        ran, why, wrote = self.run_step(None)
        self.assertEqual(ran.returncode, 1, ran.stdout + ran.stderr)
        self.assertIn("WORKLOAD", why)
        self.assertFalse(wrote, "the step wrote under .crew/ before refusing")
        self.assertEqual(ran.stdout, "", "a refused step prints no result")

    def test_a_workload_outside_any_repository_refuses(self):
        with tempfile.TemporaryDirectory() as outside:
            ran, why, wrote = self.run_step(outside)
        self.assertEqual(ran.returncode, 1, ran.stdout + ran.stderr)
        self.assertIn("WORKLOAD", why)
        self.assertFalse(wrote)


if __name__ == "__main__":
    unittest.main()
