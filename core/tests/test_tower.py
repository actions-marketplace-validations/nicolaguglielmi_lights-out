"""Tests for core/tower.py, written from docs/adr/0019 §1-§2, docs/adr/0034,
docs/adr/0038 §9 and docs/adr/0055 §1, §2, §5, never from the
implementation.

Each test runs the machine in-process in a temp root with file-backed stub
ports: a StateStore that keeps one file per document, an EventBus that
appends each published message to bus.log, and a TOWER_STEPS directory the
test fills. A file named fail-put or fail-publish in the root makes that
verb exit 1. ci/tower.sh proves the same machine end to end with the real
merge and rework steps; these pin each rule on its own.
"""

import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from core import tower

STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ENV = {"STATE_STORE": "stub-state", "EVENT_BUS": "stub-bus", "TOWER_STEPS": "steps"}

STUBS = {
    "adapters/stub-state/get.sh": 'f="state/$1.$2.json"\n[ -f "$f" ] || exit 1\ncat "$f"\n',
    "adapters/stub-state/put.sh": '[ ! -f fail-put ] || exit 1\ncat > "state/$1.$2.json"\n',
    "adapters/stub-bus/publish.sh": '[ ! -f fail-publish ] || exit 1\nprintf \'%s\\n\' "$1" >> bus.log\n',
}


class TowerCase(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for path, body in STUBS.items():
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text("set -eu\n" + body)
        (self.root / "state").mkdir()
        (self.root / "steps").mkdir()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def run_tower(self, *argv, env=ENV):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = tower.main(list(argv), dict(env))
        return code, err.getvalue()

    def doc(self, ticket="0001"):
        path = self.root / "state" / f"tickets.{ticket}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def put_doc(self, doc, ticket="0001"):
        (self.root / "state" / f"tickets.{ticket}.json").write_text(json.dumps(doc))

    def published(self):
        log = self.root / "bus.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def step_script(self, step, body):
        (self.root / "steps" / f"{step}.sh").write_text(body)

    def fail(self, verb):
        (self.root / f"fail-{verb}").touch()

    def heal(self, verb):
        (self.root / f"fail-{verb}").unlink()


class Open(TowerCase):
    def test_writes_the_document_at_opened_and_requests_assign(self):
        code, err = self.run_tower("open", "0001")
        self.assertEqual(code, 0)
        doc = self.doc()
        self.assertEqual(doc["id"], "0001")
        self.assertEqual(doc["state"], "opened")
        self.assertEqual(len(doc["history"]), 1)
        entry = doc["history"][0]
        self.assertEqual((entry["step"], entry["state"]), ("open", "opened"))
        self.assertRegex(entry["at"], STAMP)
        self.assertEqual(self.published(), [{"ticket": "0001", "step": "assign"}])
        self.assertIn("[tower] 0001: opened, assign requested", err)

    def test_the_message_is_compact_json(self):
        self.run_tower("open", "0001")
        self.assertEqual((self.root / "bus.log").read_text(), '{"ticket":"0001","step":"assign"}\n')

    def test_an_unwritable_document_requests_nothing(self):
        self.fail("put")
        code, err = self.run_tower("open", "0001")
        self.assertEqual(code, 1)
        self.assertEqual(self.published(), [])
        self.assertIn("could not write the document", err)

    def test_an_unpublished_assign_is_a_failure(self):
        self.fail("publish")
        code, err = self.run_tower("open", "0001")
        self.assertEqual(code, 1)
        self.assertIn("could not publish assign", err)


class Usage(TowerCase):
    def test_the_ports_must_be_named(self):
        for missing in ("STATE_STORE", "EVENT_BUS"):
            env = {k: v for k, v in ENV.items() if k != missing}
            code, err = self.run_tower("open", "0001", env=env)
            self.assertEqual(code, 2, missing)
            self.assertIn(f"{missing} not set", err)
            self.assertIsNone(self.doc())

    def test_a_command_and_a_ticket_are_required(self):
        for argv in ((), ("open",), ("request",), ("close", "0001"), ("", "0001")):
            code, err = self.run_tower(*argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("usage:", err)

    def test_tower_steps_defaults_to_core_steps(self):
        env = {k: v for k, v in ENV.items() if k != "TOWER_STEPS"}
        self.put_doc({"id": "0001", "state": "opened", "history": []})
        code, err = self.run_tower("step", "0001", "assign", env=env)
        self.assertEqual(code, 1)
        self.assertIn("no core/steps/assign.sh", err)


class Transitions(unittest.TestCase):
    """The states and steps of docs/adr/0019 §1, with rework from docs/adr/0038
    and the three states before `opened` from docs/adr/0055 §1, and the main check between merge and
    release from docs/adr/0056 §2."""

    def test_each_step_starts_from_its_state(self):
        self.assertEqual(tower.PRECONDITION, {
            "clarify": "requested", "answer": "questions", "spec": "spec-ready",
            "assign": "opened", "ci": "pr-opened", "review": "review",
            "merge": "ci-passed", "mainline": "merged", "release": "main-green",
            "rework": "ci-failed"})

    def test_each_state_requests_the_next_step_or_nothing(self):
        self.assertEqual(tower.NEXT, {
            "requested": "clarify", "spec-ready": "spec", "opened": "assign",
            "pr-opened": "ci", "review": "review", "ci-passed": "merge",
            "merged": "mainline", "main-green": "release", "ci-failed": "rework"})
        for waiting in ("questions", "rolled-back", "held", "needs-human"):
            self.assertNotIn(waiting, tower.NEXT)

    def test_release_no_longer_starts_from_merged(self):
        # ADR 0056 §2: a merged ticket waits for the main check, not for release.
        self.assertNotEqual(tower.PRECONDITION["release"], "merged")
        self.assertNotEqual(tower.NEXT["merged"], "release")


class Step(TowerCase):
    def opened(self, **fields):
        self.put_doc({"id": "0001", "state": "opened",
                      "history": [{"step": "open", "state": "opened", "at": "t0"}], **fields})

    def test_unknown_step_is_refused_and_touches_nothing(self):
        self.opened()
        before = self.doc()
        code, err = self.run_tower("step", "0001", "deploy")
        self.assertEqual(code, 2)
        self.assertIn('unknown step "deploy"', err)
        self.assertEqual(self.doc(), before)

    def test_no_document_is_a_failure(self):
        code, err = self.run_tower("step", "0001", "assign")
        self.assertEqual(code, 1)
        self.assertIn("no document; open the ticket first", err)

    def test_a_document_that_is_not_an_object_is_a_failure(self):
        (self.root / "state" / "tickets.0001.json").write_text("[1, 2]")
        code, err = self.run_tower("step", "0001", "assign")
        self.assertEqual(code, 1)
        self.assertIn("not a JSON object", err)

    def test_an_event_whose_precondition_is_not_the_state_is_dropped(self):
        self.put_doc({"id": "0001", "state": "pr-opened", "history": []})
        self.step_script("assign", "touch ran\necho '{\"state\": \"pr-opened\"}'\n")
        before = self.doc()
        code, err = self.run_tower("step", "0001", "assign")
        self.assertEqual(code, 0)
        self.assertIn("[tower] 0001: assign already applied (state pr-opened), ignoring", err)
        self.assertFalse((self.root / "ran").exists())
        self.assertEqual(self.doc(), before)
        self.assertEqual(self.published(), [])

    def test_a_document_without_state_reads_as_none(self):
        self.put_doc({"id": "0001", "history": []})
        code, err = self.run_tower("step", "0001", "assign")
        self.assertEqual(code, 0)
        self.assertIn("(state none)", err)

    def test_a_missing_step_script_is_a_failure(self):
        self.opened()
        code, err = self.run_tower("step", "0001", "assign")
        self.assertEqual(code, 1)
        self.assertIn("no steps/assign.sh", err)

    def test_the_step_gets_the_document_and_the_pr_range(self):
        self.put_doc({"id": "0001", "state": "pr-opened", "history": [],
                      "pr": {"number": 7, "base_sha": "b1", "head_sha": "h1"}})
        self.step_script("ci", 'cp "$DOC_FILE" seen.json\n'
                         'printf "%s|%s|%s|%s" "$TICKET" "$PR_NUMBER" "$BASE_SHA" "$HEAD_SHA" > seen.env\n'
                         "echo '{\"state\": \"ci-failed\"}'\n")
        code, _ = self.run_tower("step", "0001", "ci")
        self.assertEqual(code, 0)
        self.assertEqual((self.root / "seen.env").read_text(), "0001|7|b1|h1")
        seen = json.loads((self.root / "seen.json").read_text())
        self.assertEqual(seen["pr"]["number"], 7)
        self.assertEqual(seen["state"], "pr-opened")

    def test_no_pr_yet_means_empty_pr_variables(self):
        self.opened()
        self.step_script("assign", 'printf "[%s][%s][%s]" "$PR_NUMBER" "$BASE_SHA" "$HEAD_SHA" > seen.env\n'
                         "echo '{\"state\": \"pr-opened\"}'\n")
        self.run_tower("step", "0001", "assign")
        self.assertEqual((self.root / "seen.env").read_text(), "[][][]")

    def test_the_result_is_merged_deep_and_recorded(self):
        self.put_doc({"id": "0001", "state": "pr-opened", "history": [{"step": "open"}],
                      "attempt": 2, "pr": {"number": 7, "url": "u", "head_sha": "h1"},
                      "task": {"harness": "replay"}})
        self.step_script("ci", "echo '{\"state\": \"ci-passed\", \"pr\": {\"head_sha\": \"h2\"},"
                         " \"ci\": {\"verdict\": \"GO: gates\"}}'\n")
        code, err = self.run_tower("step", "0001", "ci")
        self.assertEqual(code, 0)
        doc = self.doc()
        self.assertEqual(doc["state"], "ci-passed")
        self.assertEqual(doc["pr"], {"number": 7, "url": "u", "head_sha": "h2"})
        self.assertEqual(doc["ci"], {"verdict": "GO: gates"})
        self.assertEqual(doc["task"], {"harness": "replay"})
        self.assertEqual(len(doc["history"]), 2)
        entry = doc["history"][-1]
        self.assertEqual({k: entry[k] for k in ("step", "state", "attempt")},
                         {"step": "ci", "state": "ci-passed", "attempt": 2})
        self.assertRegex(entry["at"], STAMP)
        self.assertNotIn("error", entry)
        self.assertIn("[tower] 0001: ci → ci-passed", err)
        self.assertEqual(self.published(), [{"ticket": "0001", "step": "merge"}])

    def test_a_release_requested_for_a_merged_ticket_is_dropped(self):
        # ADR 0056 §2: release starts from main-green; a merged ticket is mainline's.
        self.put_doc({"id": "0001", "state": "merged", "history": []})
        self.step_script("release", "touch ran\necho '{\"state\": \"rolled-back\"}'\n")
        before = self.doc()
        code, err = self.run_tower("step", "0001", "release")
        self.assertEqual(code, 0)
        self.assertIn("release already applied (state merged), ignoring", err)
        self.assertFalse((self.root / "ran").exists())
        self.assertEqual(self.doc(), before)

    def test_a_terminal_state_requests_nothing(self):
        self.put_doc({"id": "0001", "state": "main-green", "history": []})
        self.step_script("release", "echo '{\"state\": \"rolled-back\"}'\n")
        code, err = self.run_tower("step", "0001", "release")
        self.assertEqual(code, 0)
        self.assertEqual(self.doc()["state"], "rolled-back")
        self.assertEqual(self.published(), [])
        self.assertIn("rolled-back is terminal, nothing requested", err)

    def test_every_transition_requests_what_the_table_says(self):
        for step, start in tower.PRECONDITION.items():
            for state in ("pr-opened", "review", "ci-passed", "ci-failed", "merged", "main-green", "held"):
                with self.subTest(step=step, state=state):
                    (self.root / "bus.log").unlink(missing_ok=True)
                    self.put_doc({"id": "0001", "state": start, "history": []})
                    self.step_script(step, f"echo '{{\"state\": \"{state}\"}}'\n")
                    self.assertEqual(self.run_tower("step", "0001", step)[0], 0)
                    want = [{"ticket": "0001", "step": tower.NEXT[state]}] if state in tower.NEXT else []
                    self.assertEqual(self.published(), want)

    def test_history_carries_attempt_only_once_the_document_has_one(self):
        self.opened()
        self.step_script("assign", "echo '{\"state\": \"pr-opened\", \"attempt\": 1}'\n")
        self.run_tower("step", "0001", "assign")
        history = self.doc()["history"]
        self.assertNotIn("attempt", history[0])
        self.assertEqual(history[-1]["attempt"], 1)

    def test_a_failed_step_leaves_the_document_and_records_why(self):
        self.opened(pr={"number": 7})
        self.step_script("assign", "echo '{\"state\": \"pr-opened\", \"pr\": {\"number\": 9}}'\nexit 3\n")
        before = self.doc()
        code, err = self.run_tower("step", "0001", "assign")
        self.assertEqual(code, 1)
        doc = self.doc()
        self.assertEqual({k: v for k, v in doc.items() if k != "history"},
                         {k: v for k, v in before.items() if k != "history"})
        self.assertEqual(doc["history"][:-1], before["history"])
        entry = doc["history"][-1]
        self.assertEqual({k: entry[k] for k in ("step", "state", "error")},
                         {"step": "assign", "state": "opened", "error": "step exited 3"})
        self.assertNotIn("attempt", entry)
        self.assertEqual(self.published(), [])
        self.assertIn("step assign failed; state stays opened", err)
        self.assertIn("resume with ./go resume TICKET=0001", err)

    def test_a_failure_entry_carries_the_attempt(self):
        self.put_doc({"id": "0001", "state": "ci-failed", "attempt": 2, "history": []})
        self.step_script("rework", "exit 1\n")
        self.run_tower("step", "0001", "rework")
        self.assertEqual(self.doc()["history"][-1]["attempt"], 2)

    def test_a_step_that_prints_no_state_failed(self):
        for out in ("", "not json", '{"verdict": "GO"}', '{"state": ""}', '{"state": null}', '["ci"]'):
            with self.subTest(out=out):
                self.opened()
                self.step_script("assign", f"printf '%s' '{out}'\n")
                code, err = self.run_tower("step", "0001", "assign")
                self.assertEqual(code, 1)
                self.assertEqual(self.doc()["state"], "opened")
                self.assertEqual(self.doc()["history"][-1]["error"], "step printed no state")
                self.assertIn("step assign printed no state; state stays opened", err)

    def test_an_unpublished_next_step_is_recorded_on_the_new_state(self):
        self.put_doc({"id": "0001", "state": "pr-opened", "history": []})
        self.step_script("ci", "echo '{\"state\": \"ci-passed\"}'\n")
        self.fail("publish")
        code, err = self.run_tower("step", "0001", "ci")
        self.assertEqual(code, 1)
        doc = self.doc()
        self.assertEqual(doc["state"], "ci-passed")
        self.assertEqual([h["step"] for h in doc["history"]], ["ci", "merge"])
        failed = doc["history"][-1]
        self.assertEqual((failed["state"], failed["error"]), ("ci-passed", "could not publish merge"))
        self.assertIn("could not publish merge", err)

    def test_an_unwritable_result_is_a_failure(self):
        self.put_doc({"id": "0001", "state": "pr-opened", "history": []})
        self.step_script("ci", "echo '{\"state\": \"ci-passed\"}'\n")
        self.fail("put")
        code, err = self.run_tower("step", "0001", "ci")
        self.assertEqual(code, 1)
        self.assertEqual(self.doc()["state"], "pr-opened")
        self.assertEqual(self.published(), [])
        self.assertIn("could not write the document after ci", err)

    def test_an_unrecordable_failure_says_so(self):
        self.opened()
        self.step_script("assign", "exit 1\n")
        self.fail("put")
        code, err = self.run_tower("step", "0001", "assign")
        self.assertEqual(code, 1)
        self.assertIn("could not record the failed assign either", err)


class RedMain(TowerCase):
    """docs/adr/0056 §5: a red `mainline`/`main` document refuses assign, rework and release before
    they run, records the refusal as a failed attempt with the reason, and leaves every other step
    alone. The `mainline` step is one of those: it is what turns the document green again."""

    GREEN = "3f2a9c1"
    LINE = "NO-GO: gates — test: undefined call(s) foo in 9d41e07"
    REFUSED = (("assign", "opened"), ("rework", "ci-failed"), ("release", "main-green"))
    ALLOWED = (("ci", "pr-opened"), ("review", "review"), ("merge", "ci-passed"), ("mainline", "merged"))

    def main_doc(self, **fields):
        doc = {"state": "red", "green": self.GREEN, "head": "9d41e07", "line": self.LINE,
               "reverted": [], "at": "t", **fields}
        (self.root / "state" / "mainline.main.json").write_text(json.dumps(doc))

    def ticket_at(self, step, state):
        fields = {} if step == "assign" else {"attempt": 2}
        self.put_doc({"id": "0001", "state": state, "history": [{"step": "open", "state": "opened", "at": "t0"}],
                      **fields})

    def runs(self, step):
        """The step script touches `ran` and moves the ticket to `held`."""
        self.step_script(step, "touch ran\necho '{\"state\": \"held\"}'\n")

    def reset(self):
        (self.root / "ran").unlink(missing_ok=True)
        (self.root / "bus.log").unlink(missing_ok=True)

    def test_every_step_is_classified(self):
        # A step added to the table later must be decided here, refused on a red main or not.
        self.assertEqual(dict(self.REFUSED + self.ALLOWED), tower.PRECONDITION)

    def test_a_red_main_refuses_assign_rework_and_release_before_they_run(self):
        self.main_doc()
        for step, start in self.REFUSED:
            with self.subTest(step=step):
                self.reset()
                self.ticket_at(step, start)
                self.runs(step)
                before = self.doc()
                code, _ = self.run_tower("step", "0001", step)
                self.assertEqual(code, 1)
                self.assertFalse((self.root / "ran").exists(), "the step script must not run")
                self.assertEqual(self.published(), [])
                doc = self.doc()
                self.assertEqual(doc["state"], start, "the state stays")
                self.assertEqual({k: v for k, v in doc.items() if k != "history"},
                                 {k: v for k, v in before.items() if k != "history"})
                self.assertEqual(doc["history"][:-1], before["history"])
                entry = doc["history"][-1]
                self.assertEqual((entry["step"], entry["state"]), (step, start))
                self.assertRegex(entry["at"], STAMP)
                self.assertTrue(entry["error"].startswith("main is NO-GO"), entry["error"])
                self.assertIn(self.GREEN, entry["error"], "since which green main")
                self.assertIn(self.LINE, entry["error"], "and why")
                if step != "assign":
                    self.assertEqual(entry["attempt"], 2)
                else:
                    self.assertNotIn("attempt", entry)

    def test_the_refused_step_is_requested_again_once_main_is_green(self):
        for step, start in self.REFUSED:
            with self.subTest(step=step):
                self.reset()
                self.main_doc()
                self.ticket_at(step, start)
                self.runs(step)
                self.assertEqual(self.run_tower("step", "0001", step)[0], 1)
                self.main_doc(state="green")
                code, _ = self.run_tower("resume", "0001")
                self.assertEqual(code, 0)
                self.assertEqual(self.published(), [{"ticket": "0001", "step": step}])
                self.assertEqual(self.doc()["history"][-1]["resumed"], step)
                self.assertEqual(self.run_tower("step", "0001", step)[0], 0)
                self.assertTrue((self.root / "ran").exists())
                self.assertEqual(self.doc()["state"], "held")

    def test_a_green_absent_or_unmarked_main_runs_the_step(self):
        for label, doc in (("green", {"state": "green", "green": self.GREEN}), ("no state", {"head": "x"}),
                           ("absent", None)):
            for step, start in self.REFUSED:
                with self.subTest(main=label, step=step):
                    self.reset()
                    path = self.root / "state" / "mainline.main.json"
                    path.unlink(missing_ok=True)
                    if doc is not None:
                        path.write_text(json.dumps(doc))
                    self.ticket_at(step, start)
                    self.runs(step)
                    self.assertEqual(self.run_tower("step", "0001", step)[0], 0)
                    self.assertTrue((self.root / "ran").exists())
                    self.assertEqual(self.doc()["state"], "held")
                    self.assertNotIn("error", self.doc()["history"][-1])

    def test_no_other_step_is_refused(self):
        self.main_doc()
        for step, start in self.ALLOWED:
            with self.subTest(step=step):
                self.reset()
                self.ticket_at(step, start)
                self.runs(step)
                self.assertEqual(self.run_tower("step", "0001", step)[0], 0)
                self.assertTrue((self.root / "ran").exists())
                self.assertEqual(self.doc()["state"], "held")
                self.assertNotIn("error", self.doc()["history"][-1])

    def test_an_event_for_a_step_already_applied_is_dropped_not_refused(self):
        self.main_doc()
        self.put_doc({"id": "0001", "state": "pr-opened", "history": []})
        self.runs("assign")
        before = self.doc()
        code, err = self.run_tower("step", "0001", "assign")
        self.assertEqual(code, 0)
        self.assertIn("assign already applied (state pr-opened), ignoring", err)
        self.assertEqual(self.doc(), before)

    def test_only_mainline_main_is_read(self):
        # A red document under another id, or with the arguments swapped, is not main's.
        for name in ("mainline.other.json", "main.mainline.json", "tickets.main.json"):
            (self.root / "state" / name).write_text(json.dumps({"state": "red", "green": self.GREEN, "line": self.LINE}))
        self.ticket_at("assign", "opened")
        self.runs("assign")
        self.assertEqual(self.run_tower("step", "0001", "assign")[0], 0)
        self.assertTrue((self.root / "ran").exists())


class Resume(TowerCase):
    def stranded(self, state="pr-opened", step="ci", **fields):
        self.put_doc({"id": "0001", "state": state, **fields, "history": [
            {"step": "assign", "state": "pr-opened", "at": "t1"},
            {"step": step, "state": state, "at": "t2", "error": "step exited 1"}]})

    def test_a_stranded_ticket_is_requested_again_after_the_record(self):
        self.stranded(attempt=1)
        code, err = self.run_tower("resume", "0001")
        self.assertEqual(code, 0)
        history = self.doc()["history"]
        self.assertEqual(len(history), 3)
        entry = history[-1]
        self.assertEqual({k: entry[k] for k in ("step", "state", "resumed", "attempt")},
                         {"step": "resume", "state": "pr-opened", "resumed": "ci", "attempt": 1})
        self.assertRegex(entry["at"], STAMP)
        self.assertEqual(self.doc()["state"], "pr-opened")
        self.assertEqual(self.published(), [{"ticket": "0001", "step": "ci"}])
        self.assertIn("ci requested again (state pr-opened; last attempt: step exited 1)", err)

    def test_a_ticket_whose_last_entry_did_not_fail_is_not_stranded(self):
        self.put_doc({"id": "0001", "state": "ci-passed",
                      "history": [{"step": "ci", "state": "ci-passed", "at": "t"}]})
        code, err = self.run_tower("resume", "0001")
        self.assertEqual(code, 1)
        self.assertIn("not stranded: state ci-passed, last history entry ci did not fail", err)
        self.assertEqual(self.published(), [])
        self.assertEqual(len(self.doc()["history"]), 1)

    def test_a_resumed_ticket_is_not_resumed_twice(self):
        self.stranded()
        self.run_tower("resume", "0001")
        code, err = self.run_tower("resume", "0001")
        self.assertEqual(code, 1)
        self.assertIn("last history entry resume did not fail", err)
        self.assertEqual(len(self.published()), 1)

    def test_no_history_is_not_stranded(self):
        self.put_doc({"id": "0001", "state": "opened"})
        code, err = self.run_tower("resume", "0001")
        self.assertEqual(code, 1)
        self.assertIn("last history entry none did not fail", err)

    def test_the_failed_step_must_start_from_the_current_state(self):
        self.stranded(state="ci-passed", step="ci")
        code, err = self.run_tower("resume", "0001")
        self.assertEqual(code, 1)
        self.assertIn("the failed step ci does not start from state ci-passed; not resuming", err)
        self.assertEqual(self.published(), [])

    def test_no_document_is_a_failure(self):
        code, err = self.run_tower("resume", "0001")
        self.assertEqual(code, 1)
        self.assertIn("no document", err)

    def test_an_unwritable_resume_requests_nothing(self):
        self.stranded()
        self.fail("put")
        code, err = self.run_tower("resume", "0001")
        self.assertEqual(code, 1)
        self.assertEqual(self.published(), [])
        self.assertIn("could not record the resume; nothing requested", err)

    def test_an_unpublished_resume_stays_resumable(self):
        self.stranded()
        self.fail("publish")
        code, _ = self.run_tower("resume", "0001")
        self.assertEqual(code, 1)
        history = self.doc()["history"]
        self.assertEqual([h["step"] for h in history[-2:]], ["resume", "ci"])
        self.assertEqual(history[-1]["error"], "could not publish ci")
        self.heal("publish")
        self.assertEqual(self.run_tower("resume", "0001")[0], 0)
        self.assertEqual(self.published(), [{"ticket": "0001", "step": "ci"}])


class JqSemantics(unittest.TestCase):
    """The document rules ADR 0019 §2 states in jq terms."""

    def test_merge_is_recursive_on_objects_and_replaces_anything_else(self):
        self.assertEqual(tower.merge({"a": {"b": 1, "c": 2}, "d": [1]}, {"a": {"c": 3}, "d": [2]}),
                         {"a": {"b": 1, "c": 3}, "d": [2]})
        self.assertEqual(tower.merge({"a": {"b": 1}}, {"a": None}), {"a": None})
        self.assertEqual(tower.merge({"a": 1}, {"a": {"b": 2}}), {"a": {"b": 2}})

    def test_merge_leaves_its_inputs_alone(self):
        left = {"a": {"b": 1}}
        tower.merge(left, {"a": {"c": 2}})
        self.assertEqual(left, {"a": {"b": 1}})

    def test_null_and_false_read_as_absent(self):
        self.assertEqual(tower.text(None), "")
        self.assertEqual(tower.text(False), "")
        self.assertEqual(tower.text(True), "true")
        self.assertEqual(tower.text(0), "0")
        self.assertEqual(tower.text("x"), "x")

    def test_an_attempt_of_zero_is_an_attempt(self):
        self.assertEqual(tower.attempt({"attempt": 0}), {"attempt": 0})
        self.assertEqual(tower.attempt({"attempt": None}), {})
        self.assertEqual(tower.attempt({}), {})


class Request(TowerCase):
    """docs/adr/0055 §1: a request starts at `requested` and asks for clarify."""

    def test_writes_the_document_at_requested_and_requests_clarify(self):
        code, err = self.run_tower("request", "0001")
        self.assertEqual(code, 0)
        doc = self.doc()
        self.assertEqual((doc["id"], doc["state"]), ("0001", "requested"))
        self.assertEqual([(h["step"], h["state"]) for h in doc["history"]], [("request", "requested")])
        self.assertRegex(doc["history"][0]["at"], STAMP)
        self.assertEqual(self.published(), [{"ticket": "0001", "step": "clarify"}])

    def test_an_unpublished_clarify_is_a_failure(self):
        self.fail("publish")
        code, err = self.run_tower("request", "0001")
        self.assertEqual(code, 1)
        self.assertIn("could not publish clarify", err)

    def test_a_spec_gate_go_requests_assign(self):
        self.put_doc({"id": "0001", "state": "spec-ready", "history": []})
        self.step_script("spec", 'echo \'{"state": "opened", "spec": {"verdict": "GO"}}\'\n')
        code, _ = self.run_tower("step", "0001", "spec")
        self.assertEqual(code, 0)
        self.assertEqual(self.doc()["state"], "opened")
        self.assertEqual(self.published(), [{"ticket": "0001", "step": "assign"}])

    def test_questions_requests_nothing(self):
        self.put_doc({"id": "0001", "state": "requested", "history": []})
        self.step_script("clarify", 'echo \'{"state": "questions", "questions": [{"question": "q?"}]}\'\n')
        self.assertEqual(self.run_tower("step", "0001", "clarify")[0], 0)
        self.assertEqual(self.doc()["state"], "questions")
        self.assertEqual(self.published(), [])


class Answer(TowerCase):
    """docs/adr/0055 §2: a person's answer on the open question, then `answer`."""

    def setUp(self):
        super().setUp()
        self.put_doc({"id": "0001", "state": "questions", "history": [],
                      "questions": [{"question": "first?", "answer": "yes"}, {"question": "second?"}]})

    def answer(self, **env):
        return self.run_tower("answer", "0001", env=dict(ENV, **env))

    def test_records_who_answered_how_and_when_then_requests_answer(self):
        code, err = self.answer(ANSWER="  waiting list  ", ANSWER_BY="ada@example.org", ANSWER_VIA="console")
        self.assertEqual(code, 0)
        q = self.doc()["questions"]
        self.assertEqual(q[0], {"question": "first?", "answer": "yes"})
        self.assertEqual({k: q[1][k] for k in ("question", "answer", "answered_by", "answered_via")},
                         {"question": "second?", "answer": "waiting list", "answered_by": "ada@example.org",
                          "answered_via": "console"})
        self.assertRegex(q[1]["answered_at"], STAMP)
        self.assertEqual(self.doc()["state"], "questions")
        self.assertEqual(self.doc()["history"][-1]["step"], "answered")
        self.assertEqual(self.published(), [{"ticket": "0001", "step": "answer"}])

    def test_the_cli_answers_unauthenticated(self):
        self.answer(ANSWER="ok")
        q = self.doc()["questions"][-1]
        self.assertEqual((q["answered_by"], q["answered_via"]), ("unauthenticated", "cli"))

    def test_no_answer_records_nothing(self):
        code, err = self.answer(ANSWER="  ")
        self.assertEqual(code, 2)
        self.assertNotIn("answer", self.doc()["questions"][-1])
        self.assertEqual(self.published(), [])

    def test_only_an_open_question_takes_an_answer(self):
        self.put_doc({"id": "0001", "state": "questions", "history": [],
                      "questions": [{"question": "q?", "answer": "done"}]})
        self.assertEqual(self.answer(ANSWER="again")[0], 1)
        self.put_doc({"id": "0001", "state": "spec-ready", "history": [], "questions": [{"question": "q?"}]})
        code, err = self.answer(ANSWER="late")
        self.assertEqual(code, 1)
        self.assertIn("no open question", err)
        self.assertEqual(self.published(), [])


class Tasks(TowerCase):
    """docs/adr/0055 §5: every attempt's task is kept, with its attempt."""

    def test_each_task_is_appended_with_the_attempt(self):
        self.put_doc({"id": "0001", "state": "opened", "history": []})
        self.step_script("assign", 'echo \'{"state": "pr-opened", "attempt": 1, "task": {"turns": 3}}\'\n')
        self.run_tower("step", "0001", "assign")
        doc = self.doc()
        doc["state"] = "ci-failed"
        self.put_doc(doc)
        self.step_script("rework", 'echo \'{"state": "pr-opened", "attempt": 2, "task": {"turns": 5}}\'\n')
        self.run_tower("step", "0001", "rework")
        self.assertEqual(self.doc()["tasks"], [{"turns": 3, "attempt": 1}, {"turns": 5, "attempt": 2}])
        self.assertEqual(self.doc()["task"], {"turns": 5})

    def test_a_step_without_a_task_keeps_the_list(self):
        self.put_doc({"id": "0001", "state": "ci-passed", "history": [], "tasks": [{"turns": 1}]})
        self.step_script("merge", 'echo \'{"state": "merged"}\'\n')
        self.run_tower("step", "0001", "merge")
        self.assertEqual(self.doc()["tasks"], [{"turns": 1}])


class Task(TowerCase):
    """docs/adr/0047 §2, P1: who ran a role and what it cost, from run.json;
    under replay the recorded run's values, a missing key null."""

    def run_json(self, run):
        (self.root / "run.json").write_text(json.dumps(run))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = tower.main(["task", "run.json"], {})
        return code, json.loads(out.getvalue()) if code == 0 else None

    def test_a_live_run_reports_its_own_fields(self):
        code, task = self.run_json({"harness": "gemini-cli", "model": "m", "provider": "p", "thinking": "low",
                                    "turns": 7, "tokens": {"total": 9}, "duration_s": 3, "input_sha256": "ab"})
        self.assertEqual(code, 0)
        self.assertEqual(task, {"harness": "gemini-cli", "replayed": False, "model": "m", "provider": "p",
                                "thinking": "low", "turns": 7, "tokens": {"total": 9}, "duration_s": 3,
                                "input_sha256": "ab"})

    def test_a_replayed_run_reports_the_recorded_one(self):
        code, task = self.run_json({"harness": "replay", "recorded": {"model": "m", "provider": "p", "turns": 4}})
        self.assertEqual(code, 0)
        self.assertTrue(task["replayed"])
        self.assertEqual((task["model"], task["provider"], task["turns"]), ("m", "p", 4))
        self.assertIsNone(task["tokens"])

    def test_no_harness_is_unknown_and_nothing_is_guessed(self):
        code, task = self.run_json({})
        self.assertEqual(code, 0)
        self.assertEqual(task["harness"], "unknown")
        self.assertEqual({k for k, v in task.items() if v not in (None, False)}, {"harness"})

    def test_an_unreadable_run_is_a_failure(self):
        (self.root / "run.json").write_text("not json")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tower.main(["task", "run.json"], {}), 1)
            self.assertEqual(tower.main(["task", "absent.json"], {}), 1)


if __name__ == "__main__":
    unittest.main()
