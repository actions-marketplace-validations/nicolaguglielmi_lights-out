"""Tests for core/logbook.py's timeline, written from docs/adr/0055 §6 and
docs/plans/console.md "1.1: the dev phase", never from the implementation:
one row per phase in the history's order, each naming its record, and no
row for a phase with no record. ci/logbook.sh proves the whole document
against its golden; these pin each rule on its own."""

import unittest

from core import logbook

H = lambda step, state, at, **more: dict(step=step, state=state, at=at, **more)  # noqa: E731


def phases(rows):
    return [r["phase"] for r in rows]


class Before(unittest.TestCase):
    """request, product, question, answer, spec."""

    def doc(self):
        return {
            "state": "opened",
            "history": [H("request", "requested", "t0"), H("clarify", "questions", "t1"),
                        H("answered", "questions", "t2"), H("answer", "spec-ready", "t3"),
                        H("spec", "questions", "t4"), H("answered", "questions", "t5"),
                        H("answer", "spec-ready", "t6"), H("spec", "opened", "t7")],
            "questions": [
                {"question": "who is promoted?", "from": "product", "asked_at": "t1", "answer": "the first",
                 "answered_by": "alice", "answered_via": "console", "answered_at": "t2"},
                {"question": "no ## Perimeter section", "from": "spec", "asked_at": "t4", "answer": "added",
                 "answered_by": "bob", "answered_via": "cli", "answered_at": "t5"}],
            "product": {"harness": "adk", "model": "m", "turns": 4, "tokens": {"total": 9}, "replayed": True,
                        "consulted": True},
            "spec": {"criteria": ["a", "b"], "by": "product", "verdict": "GO", "line": "GO: spec", "at": "t7"},
        }

    def test_the_phases_follow_the_history(self):
        rows = logbook.timeline(self.doc(), "0009", [], ["src/*"])
        self.assertEqual(phases(rows), ["request", "product", "question", "answer", "product", "spec", "answer",
                                        "product", "spec"])

    def test_every_row_names_its_record_and_its_time(self):
        for r in logbook.timeline(self.doc(), "0009", [], ["src/*"]):
            self.assertTrue(r["record"], r)
            self.assertIn("at", r)
            self.assertIn("verdict", r)
            self.assertIn("line", r)

    def test_questions_and_answers_carry_who_and_how(self):
        rows = logbook.timeline(self.doc(), "0009", [], [])
        q = [r for r in rows if r["phase"] == "question"][0]
        self.assertEqual((q["line"], q["at"], q["by"]), ("who is promoted?", "t1", "product"))
        a = [r for r in rows if r["phase"] == "answer"]
        self.assertEqual([(r["line"], r["by"], r["via"], r["at"]) for r in a],
                         [("the first", "alice", "console", "t2"), ("added", "bob", "cli", "t5")])

    def test_the_spec_rows_say_go_and_no_go_with_the_reason(self):
        rows = [r for r in logbook.timeline(self.doc(), "0009", [], []) if r["phase"] == "spec"]
        self.assertEqual([r["verdict"] for r in rows], ["NO-GO", "GO"])
        self.assertEqual(rows[0]["line"], "NO-GO: spec — no ## Perimeter section")
        self.assertEqual(rows[1]["line"], "GO: spec")

    def test_the_last_product_run_carries_its_cost(self):
        rows = [r for r in logbook.timeline(self.doc(), "0009", [], []) if r["phase"] == "product"]
        self.assertEqual([r["verdict"] for r in rows], ["questions", "spec-ready", "spec-ready"])
        self.assertNotIn("turns", rows[0])
        self.assertEqual((rows[-1]["turns"], rows[-1]["model"], rows[-1]["line"]), (4, "m", "confirmed 2 criteria"))

    def test_a_product_not_consulted_says_why(self):
        doc = {"history": [H("request", "requested", "t0"), H("clarify", "spec-ready", "t1")],
               "product": {"consulted": False, "why": "no recording"}, "spec": {"criteria": ["x"], "by": "request"}}
        row = logbook.timeline(doc, "0001", [], [])[1]
        self.assertEqual((row["phase"], row["line"]), ("product", "not consulted: no recording"))

    def test_a_ticket_opened_directly_says_so(self):
        rows = logbook.timeline({"history": [H("open", "opened", "t0")]}, "0001", [], [])
        self.assertEqual(phases(rows), ["open"])
        self.assertIn("no request", rows[0]["line"])


class After(unittest.TestCase):
    """assign, attempts, gates, rework, review, merge, canary, sign-off, outcome."""

    def doc(self):
        return {
            "state": "rolled-back", "attempt": 2,
            "history": [H("open", "opened", "t0"), H("assign", "pr-opened", "t1", attempt=1),
                        H("ci", "ci-failed", "t2", attempt=1), H("rework", "pr-opened", "t3", attempt=2),
                        H("ci", "ci-passed", "t4", attempt=2), H("merge", "merged", "t5", attempt=2),
                        H("release", "rolled-back", "t6", attempt=2)],
            "pr": {"number": 7},
            "tasks": [{"attempt": 1, "harness": "replay", "turns": 3, "tokens": {"total": 10}},
                      {"attempt": 2, "harness": "replay", "turns": 5, "tokens": {"total": 20}}],
            "rework": [{"attempt": 1, "judge": "gates", "line": "NO-GO: mutation — 0.5"}],
            "ci": {"verdict": "GO", "line": "GO: gates", "details": ["GO: risk", "GO: test"]},
            "merge": {"sha": "m1"},
            "release": {"version": "v2", "verdict": "NO-GO: launchpad — 5%: error_rate → rolled back"},
        }

    def rels(self):
        return [{"ticket": "0001", "version": "v2", "at": "r1", "answer": None,
                 "stages": [{"pct": 5, "verdict": "NO-GO: launchpad — 5%", "numbers": ["slo: x"]}]},
                {"ticket": "0002", "version": "v2", "at": "r2", "answer": None, "stages": [{"pct": 5, "verdict": "GO"}]}]

    def test_the_chain_in_order(self):
        rows = logbook.timeline(self.doc(), "0001", self.rels(), ["src/*"])
        self.assertEqual(phases(rows), ["open", "assign", "attempt", "gates", "rework", "attempt", "gates", "gate",
                                        "gate", "merge", "canary", "release", "outcome"])

    def test_assign_holds_the_perimeter_and_no_wait_when_never_refused(self):
        row = [r for r in logbook.timeline(self.doc(), "0001", [], ["src/*"]) if r["phase"] == "assign"][0]
        self.assertEqual((row["line"], row["perimeter"], row["wait"]), ("PR #7", ["src/*"], None))

    def test_refused_assigns_are_wait_rows_and_the_assign_says_how_long(self):
        doc = self.doc()
        doc["history"][1:1] = [H("assign", "opened", "w1", error="step exited 1"),
                               H("resume", "opened", "w2", resumed="assign"),
                               H("assign", "opened", "w3", error="step exited 1")]
        rows = logbook.timeline(doc, "0001", [], ["src/*"])
        waits = [r for r in rows if r["phase"] == "wait"]
        self.assertEqual([(r["at"], r["verdict"]) for r in waits], [("w1", "waiting"), ("w3", "waiting")])
        self.assertIn("step exited 1", waits[0]["line"])
        assign = [r for r in rows if r["phase"] == "assign"][0]
        self.assertEqual(assign["wait"], {"refusals": 2, "since": "w1"})

    def test_each_attempt_has_its_own_cost(self):
        rows = [r for r in logbook.timeline(self.doc(), "0001", [], []) if r["phase"] == "attempt"]
        self.assertEqual([(r["attempt"], r["turns"], r["tokens"]["total"]) for r in rows], [(1, 3, 10), (2, 5, 20)])

    def test_rework_carries_the_verdict_that_sent_it_back(self):
        row = [r for r in logbook.timeline(self.doc(), "0001", [], []) if r["phase"] == "rework"][0]
        self.assertEqual((row["attempt"], row["line"], row["judge"]), (2, "NO-GO: mutation — 0.5", "gates"))

    def test_only_the_last_ci_run_has_its_line_and_gate_rows(self):
        rows = [r for r in logbook.timeline(self.doc(), "0001", [], []) if r["phase"] in ("gates", "gate")]
        self.assertEqual([(r["phase"], r["line"]) for r in rows],
                         [("gates", None), ("gates", "GO: gates"), ("gate", "GO: risk"), ("gate", "GO: test")])
        self.assertEqual([r["verdict"] for r in rows if r["phase"] == "gates"], ["ci-failed", "ci-passed"])

    def test_the_canary_rows_come_from_this_ticket_s_release_only(self):
        rows = [r for r in logbook.timeline(self.doc(), "0001", self.rels(), []) if r["phase"] == "canary"]
        self.assertEqual([(r["pct"], r["verdict"], r["numbers"]) for r in rows], [(5, "NO-GO", ["slo: x"])])
        self.assertEqual(rows[0]["record"], "release log")

    def test_no_release_log_no_canary_rows(self):
        rows = logbook.timeline(self.doc(), "0001", {"ok": False, "error": "x"}, [])
        self.assertNotIn("canary", phases(rows))
        self.assertIn("release", phases(rows))

    def test_a_human_answer_is_the_sign_off(self):
        doc = dict(self.doc(), state="held", release={"version": "v3", "verdict": "GO: launchpad — held"})
        rels = [{"ticket": "0001", "version": "v3", "at": "r", "stages": [{"pct": 25, "verdict": "GO"}],
                 "answer": {"answer": "GO", "by": "alice", "via": "console", "at": "r9"}}]
        rows = logbook.timeline(doc, "0001", rels, [])
        sign = [r for r in rows if r["phase"] == "sign-off"][0]
        self.assertEqual((sign["verdict"], sign["line"], sign["via"], sign["at"]), ("GO", "GO by alice", "console", "r9"))
        self.assertEqual(rows[-1]["phase"], "outcome")
        self.assertEqual(rows[-1]["verdict"], "GO")

    def test_the_outcome_is_last_and_names_its_judge(self):
        last = logbook.timeline(self.doc(), "0001", [], [])[-1]
        self.assertEqual((last["phase"], last["verdict"]), ("outcome", "NO-GO"))
        self.assertIn("verify", last["record"])

    def test_a_pending_ticket_has_no_outcome_row(self):
        self.assertNotIn("outcome", phases(logbook.timeline({"state": "requested",
                                                             "history": [H("request", "requested", "t0")]}, "1", [], [])))

    def test_a_failed_step_is_a_row_and_a_resume_too(self):
        doc = {"state": "pr-opened", "history": [H("open", "opened", "t0"),
                                                 H("ci", "pr-opened", "t1", error="step exited 1"),
                                                 H("resume", "pr-opened", "t2", resumed="ci")]}
        rows = logbook.timeline(doc, "1", [], [])
        self.assertEqual([(r["phase"], r["verdict"], r["line"]) for r in rows[1:3]],
                         [("ci", "failed", "step exited 1"), ("resume", None, "ci requested again")])

    def test_review_shows_its_verdict_and_first_line(self):
        doc = {"state": "ci-failed", "history": [H("open", "opened", "t0"), H("review", "ci-failed", "t1")],
               "review": {"verdict": "changes-requested", "reason": "first\nsecond"}}
        row = logbook.timeline(doc, "1", [], [])[1]
        self.assertEqual((row["phase"], row["verdict"], row["line"]), ("review", "changes-requested", "first"))


class Kanban(unittest.TestCase):
    """docs/adr/0055 §7: a card's column is its ticket's state; P0 first,
    unprioritised last, then the oldest, then the id."""

    def t(self, tid, state, priority=None, opened=None):
        return {"id": tid, "state": state, "priority": priority, "opened_at": opened}

    def test_every_ticket_is_one_card_in_its_state_s_column(self):
        tickets = [self.t("1", "questions"), self.t("2", "rolled-back"), self.t("3", "questions"), self.t("4", "odd")]
        board = logbook.kanban(tickets)
        where = {tid: col["state"] for col in board for tid in col["tickets"]}
        self.assertEqual(where, {"1": "questions", "2": "rolled-back", "3": "questions", "4": "odd"})
        self.assertEqual(sum(len(c["tickets"]) for c in board), 4)

    def test_the_columns_are_the_tower_s_states_in_order_then_any_other(self):
        board = logbook.kanban([self.t("1", "zeta"), self.t("2", "alpha")])
        self.assertEqual([c["state"] for c in board][:4], ["requested", "questions", "spec-ready", "opened"])
        self.assertEqual([c["state"] for c in board][-3:], ["rolled-back", "alpha", "zeta"])

    def test_priority_then_age_then_id(self):
        tickets = [self.t("a", "opened", None, "t1"), self.t("b", "opened", "P2", "t3"), self.t("c", "opened", "P0", "t9"),
                   self.t("d", "opened", "P2", "t2"), self.t("e", "opened", "P2", "t2"), self.t("f", "opened", "P3", None)]
        col = [c for c in logbook.kanban(tickets) if c["state"] == "opened"][0]
        self.assertEqual(col["tickets"], ["c", "d", "e", "b", "f", "a"])

    def test_an_unread_ticket_list_stays_unread(self):
        unread = {"ok": False, "error": "x"}
        self.assertEqual(logbook.kanban(unread), unread)


class Wait(unittest.TestCase):
    """docs/adr/0053 §5-§6 read by the logbook: a ticket at opened whose last
    assign was refused waits; its holders are the holding tickets of
    perimeters/held whose globs overlap its own."""

    def ticket(self, tid="0002", state="opened", last_error=True, perimeter=("src/a.py",)):
        history = [H("open", "opened", "t0"), H("assign", "opened", "t1", error="step exited 1")]
        if not last_error:
            history.append(H("assign", "pr-opened", "t2", attempt=1))
        return {"id": tid, "state": state, "history": history, "perimeter": list(perimeter)}

    def holds(self):
        return [{"ticket": "0001", "globs": ["src/*"], "state": "pr-opened", "holding": True},
                {"ticket": "0003", "globs": ["src/a.py"], "state": "merged", "holding": False},
                {"ticket": "0004", "globs": ["docs/*"], "state": "review", "holding": True}]

    def test_a_refused_ticket_waits_on_the_overlapping_holder(self):
        got = logbook.waiting(self.ticket(), self.holds())
        self.assertEqual((got["since"], got["refusals"], got["holders"]), ("t1", 1, ["0001"]))

    def test_a_refusal_with_no_overlapping_holder_names_none(self):
        self.assertEqual(logbook.waiting(self.ticket(perimeter=("lib/x.py",)), self.holds())["holders"], [])

    def test_no_wait_unless_opened_and_the_last_assign_refused(self):
        self.assertIsNone(logbook.waiting(self.ticket(last_error=False, state="pr-opened"), self.holds()))
        self.assertIsNone(logbook.waiting(self.ticket(state="questions"), self.holds()))
        self.assertIsNone(logbook.waiting({"id": "9", "state": "opened", "history": []}, self.holds()))

    def test_docs_to_realign_come_from_the_merges_map(self):
        tickets = [{"id": "0001", "state": "merged", "map": {"sha": "m1", "docs_ticket": "0014"}},
                   {"id": "0002", "state": "merged", "map": {"sha": "m2", "docs_ticket": None}},
                   {"id": "0014", "state": "requested", "map": None}]
        self.assertEqual(logbook.docs_to_realign(tickets),
                         [{"ticket": "0001", "merge_sha": "m1", "docs_ticket": "0014", "docs_ticket_state": "requested"}])


class Run(unittest.TestCase):
    """docs/adr/0047 §2: a source it cannot read is the source's own last
    stderr line, never a default."""

    def test_the_code_the_output_and_the_last_stderr_line(self):
        self.assertEqual(logbook.run("sh", "-c", "echo out; echo first >&2; echo last >&2; exit 3"),
                         (3, "out\n", "last"))

    def test_no_stderr_names_the_command_and_its_code(self):
        self.assertEqual(logbook.run("sh", "-c", "exit 2"), (2, "", "sh -c exit 2: exit 2"))


if __name__ == "__main__":
    unittest.main()
