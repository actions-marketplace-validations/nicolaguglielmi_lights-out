"""Tests for core/logbook.py's timeline, written from docs/adr/0055 §6 and
docs/plans/console.md "1.1: the dev phase", never from the implementation:
one row per phase in the history's order, each naming its record, and no
row for a phase with no record. ci/logbook.sh proves the whole document
against its golden; these pin each rule on its own.

The 1.4 additions (docs/adr/0078 §2, §3) are in the last two classes: `why`,
withheld until the same attempt's secrets gate said GO.

The 1.3 additions (docs/adr/0071 §1, §8) are at the end: the `gates` parse,
the rule that withholds a patch the secrets gate did not pass, the `files`
rows of a ticket, and the reader run over the stub sources with one fact
changed at a time."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_the_request_row_carries_who_requested_and_through_what(self):
        """docs/adr/0059 §4: the tower records `by` and `via` on the request."""
        doc = {"history": [H("request", "requested", "t0", by="ada@example.org", via="console"),
                           H("clarify", "questions", "t1")]}
        row = logbook.timeline(doc, "0010", [], [])[0]
        self.assertEqual((row["phase"], row["at"], row["by"], row["via"]),
                         ("request", "t0", "ada@example.org", "console"))

    def test_the_request_row_of_the_cli_says_so_too(self):
        doc = {"history": [H("request", "requested", "t0", by="unauthenticated", via="cli")]}
        row = logbook.timeline(doc, "0010", [], [])[0]
        self.assertEqual((row["by"], row["via"]), ("unauthenticated", "cli"))

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
            "ci": {"verdict": "GO", "line": "GO: gates", "details": ["GO: risk", "GO: test"],
                   "lines": ["GO: risk", "GO: secrets", "GO: test"]},
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


class Agents(unittest.TestCase):
    """docs/adr/0073 §10: a ticket's entry carries what its runs used, the
    task's `mcp` and the review's `instructions`, for the card's back."""

    def test_the_ticket_carries_the_task_s_mcp_and_the_review_s_instructions(self):
        mcp = {"sha256": "cd", "servers": [], "unlisted": "hidden",
               "calls": [{"server": "notes", "tool": "search_notes", "count": 1}], "denied": []}
        instructions = {"file": "contract/roles/test-reviewer.md", "sha256": "ef", "base": "b1"}
        doc = {"state": "review", "history": [H("open", "opened", "t0")],
               "task": {"role": "dev-worker", "harness": "codex", "mcp": mcp},
               "review": {"role": "test-reviewer", "verdict": "approved", "instructions": instructions}}
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "adapters", "s"))
            os.makedirs(os.path.join(root, "tickets"))
            with open(os.path.join(root, "adapters", "s", "get.sh"), "w", encoding="utf-8") as fh:
                fh.write('cat "state/$1.$2.json"\n')
            with open(os.path.join(root, "tickets", "0001.md"), "w", encoding="utf-8") as fh:
                fh.write("# A ticket\n\n## Perimeter\n- a/*\n")
            os.makedirs(os.path.join(root, "state"))
            with open(os.path.join(root, "state", "tickets.0001.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            here = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.dict(os.environ, {"STATE_STORE": "s", "TICKETS_DIR": "tickets"}):
                    (ticket,) = logbook.tickets([])
            finally:
                os.chdir(here)
        self.assertEqual((ticket["task"]["mcp"], ticket["review"]["instructions"]), (mcp, instructions))


class Run(unittest.TestCase):
    """docs/adr/0047 §2: a source it cannot read is the source's own last
    stderr line, never a default."""

    def test_the_code_the_output_and_the_last_stderr_line(self):
        self.assertEqual(logbook.run("sh", "-c", "echo out; echo first >&2; echo last >&2; exit 3"),
                         (3, "out\n", "last"))

    def test_no_stderr_names_the_command_and_its_code(self):
        self.assertEqual(logbook.run("sh", "-c", "exit 2"), (2, "", "sh -c exit 2: exit 2"))



class GateRows(unittest.TestCase):
    """docs/adr/0071 §1: `gates` is parsed from a gate run's lines by the gate
    contract's shape (CLAUDE.md): `GO: <gate>`, `GO: <gate> — <detail>`,
    `NO-GO: <gate> — <reason>`; the line is kept verbatim, and a line off the
    contract gives a gate and a verdict of null."""

    def test_a_bare_go(self):
        self.assertEqual(logbook.gate_rows(["GO: secrets"]), [{"gate": "secrets", "verdict": "GO", "line": "GO: secrets"}])

    def test_a_go_with_a_detail(self):
        line = "GO: sast — in the workbench"
        self.assertEqual(logbook.gate_rows([line]), [{"gate": "sast", "verdict": "GO", "line": line}])

    def test_a_no_go_with_its_reason(self):
        line = "NO-GO: mutation — 3 of 12 mutants survived, score 75% below the baseline of 80%"
        self.assertEqual(logbook.gate_rows([line]), [{"gate": "mutation", "verdict": "NO-GO", "line": line}])

    def test_a_gate_name_is_lowercase_letters_digits_and_hyphens(self):
        rows = logbook.gate_rows(["GO: test-weakening", "GO: test-proof — x", "GO: gate2"])
        self.assertEqual([r["gate"] for r in rows], ["test-weakening", "test-proof", "gate2"])

    def test_a_detail_that_looks_like_a_verdict_does_not_change_the_row(self):
        line = "GO: risk — NO-GO: not really, GO: still risk"
        self.assertEqual(logbook.gate_rows([line]), [{"gate": "risk", "verdict": "GO", "line": line}])

    def test_a_line_off_the_contract_has_no_gate_and_no_verdict_and_is_kept_verbatim(self):
        for line in ("make: *** [gates] Error 1", "", "GO:secrets", "go: secrets", "MAYBE: secrets — x",
                     "GO: UPPER", "GO: x - a hyphen is not the dash", "  GO: x"):
            self.assertEqual(logbook.gate_rows([line]), [{"gate": None, "verdict": None, "line": line}], repr(line))

    def test_the_rows_keep_the_order_the_gates_ran(self):
        lines = ["GO: risk — low, review", "GO: secrets", "not a gate line", "NO-GO: mutation — 2 survived"]
        rows = logbook.gate_rows(lines)
        self.assertEqual([(r["gate"], r["verdict"]) for r in rows],
                         [("risk", "GO"), ("secrets", "GO"), (None, None), ("mutation", "NO-GO")])
        self.assertEqual([r["line"] for r in rows], lines)

    def test_no_lines_is_an_empty_list_of_rows(self):
        self.assertEqual(logbook.gate_rows([]), [])

    def test_anything_that_is_not_a_list_is_none(self):
        for lines in (None, "GO: x", {"0": "GO: x"}, 5):
            self.assertIsNone(logbook.gate_rows(lines), repr(lines))

    def test_a_row_has_exactly_gate_verdict_line(self):
        self.assertEqual(set(logbook.gate_rows(["GO: x"])[0]), {"gate", "verdict", "line"})


class ShownPatch(unittest.TestCase):
    """docs/adr/0071 §1: a patch is shown only if its attempt's `secrets` gate
    said GO; otherwise it is {ok: false, error: "withheld: the secrets gate
    did not say GO on attempt <n>"}. No patch stays null."""

    PATCH = {"text": "diff --git a/x b/x\n", "bytes": 19, "truncated": False}

    def row(self, gate, verdict):
        return {"gate": gate, "verdict": verdict, "line": f"{verdict}: {gate}"}

    def withheld(self, n):
        return {"ok": False, "error": f"withheld: the secrets gate did not say GO on attempt {n}"}

    def test_secrets_go_shows_the_patch_as_it_is(self):
        gates = [self.row("risk", "GO"), self.row("secrets", "GO"), self.row("deps", "GO")]
        self.assertEqual(logbook.shown_patch(self.PATCH, gates, 1), self.PATCH)

    def test_secrets_go_after_other_gates_in_any_position(self):
        self.assertEqual(logbook.shown_patch(self.PATCH, [self.row("risk", "GO"), self.row("deps", "GO"),
                                                          self.row("secrets", "GO")], 2), self.PATCH)

    def test_secrets_no_go_withholds_it(self):
        gates = [self.row("risk", "GO"), self.row("secrets", "NO-GO")]
        self.assertEqual(logbook.shown_patch(self.PATCH, gates, 3), self.withheld(3))

    def test_secrets_not_run_withholds_it(self):
        for gates in ([self.row("perimeter", "NO-GO")], [self.row("risk", "GO")], []):
            self.assertEqual(logbook.shown_patch(self.PATCH, gates, 1), self.withheld(1), gates)

    def test_an_attempt_in_flight_has_no_gates_and_is_withheld(self):
        self.assertEqual(logbook.shown_patch(self.PATCH, None, 1), self.withheld(1))

    def test_another_gate_saying_go_does_not_count(self):
        gates = [self.row("secrets-scan", "GO"), self.row("test-secrets", "GO"), self.row("deps", "GO")]
        self.assertEqual(logbook.shown_patch(self.PATCH, gates, 1), self.withheld(1))

    def test_a_line_off_the_contract_does_not_count(self):
        gates = [{"gate": None, "verdict": None, "line": "GO: secrets but off the contract"}]
        self.assertEqual(logbook.shown_patch(self.PATCH, gates, 1), self.withheld(1))

    def test_the_error_names_the_attempt(self):
        self.assertIn("attempt 4", logbook.shown_patch(self.PATCH, None, 4)["error"])
        self.assertNotIn("attempt 4", logbook.shown_patch(self.PATCH, None, 5)["error"])

    def test_no_patch_stays_null_whatever_the_gates_said(self):
        for gates in (None, [], [self.row("secrets", "GO")], [self.row("secrets", "NO-GO")]):
            self.assertIsNone(logbook.shown_patch(None, gates, 1), gates)

    def test_a_withheld_patch_leaks_nothing_of_the_patch(self):
        got = logbook.shown_patch({"text": "AKIA-A-KEY-THE-WORKER-PASTED", "bytes": 28, "truncated": False}, None, 1)
        self.assertNotIn("AKIA", json.dumps(got))
        self.assertEqual(set(got), {"ok", "error"})


class TicketFiles(unittest.TestCase):
    """docs/adr/0071 §1: one row per path any attempt touched, sorted by path:
    glob, member, attempts, tests, adrs, held_by. `tests` is [] when the map
    knows the file and no test covers it, null when it does not know it or is
    unread; `adrs` and `held_by` are null when their source is unread."""

    UNREAD = {"ok": False, "error": "no map; run ./go map"}

    def task(self, attempt, *files):
        return {"attempt": attempt, "files": [{"path": p, "added": 1, "removed": 0, "member": m} for p, m in files]}

    def ticket(self, tasks, perimeter=("src/*", "tests/test_notify.py")):
        return {"id": "0010", "perimeter": list(perimeter), "tasks": tasks}

    def rows(self, ticket, adrs=(), holds=(), tests_of=None):
        return logbook.ticket_files(ticket, list(adrs), list(holds), {} if tests_of is None else tests_of)

    def test_the_union_of_the_attempts_sorted_by_path(self):
        t = self.ticket([self.task(1, ("tests/test_notify.py", "tests"), ("src/send.py", "impl")),
                         self.task(2, ("src/send.py", "impl"), ("src/extra.py", "impl"))])
        rows = self.rows(t)
        self.assertEqual([r["path"] for r in rows], ["src/extra.py", "src/send.py", "tests/test_notify.py"])
        self.assertEqual({r["path"]: r["attempts"] for r in rows},
                         {"src/extra.py": [2], "src/send.py": [1, 2], "tests/test_notify.py": [1]})

    def test_a_row_has_exactly_the_seven_keys(self):
        row = self.rows(self.ticket([self.task(1, ("src/a.py", None))]))[0]
        self.assertEqual(set(row), {"path", "glob", "member", "attempts", "tests", "adrs", "held_by"})

    def test_attempts_are_ascending_whatever_the_order_of_the_tasks(self):
        t = self.ticket([self.task(3, ("src/a.py", None)), self.task(1, ("src/a.py", None))])
        self.assertEqual(self.rows(t)[0]["attempts"], [1, 3])

    def test_glob_is_the_first_perimeter_glob_that_matches_and_star_crosses_slash(self):
        t = self.ticket([self.task(1, ("src/deep/er/a.py", None), ("src/a.py", None), ("docs/a.md", None))],
                        perimeter=["docs/b.md", "src/a.py", "src/*"])
        got = {r["path"]: r["glob"] for r in self.rows(t)}
        self.assertEqual(got, {"src/a.py": "src/a.py", "src/deep/er/a.py": "src/*", "docs/a.md": None})

    def test_member_comes_from_the_latest_attempt_that_touched_the_path(self):
        t = self.ticket([self.task(1, ("src/a.py", "old")), self.task(2, ("src/a.py", "new"))])
        self.assertEqual(self.rows(t)[0]["member"], "new")
        t = self.ticket([self.task(2, ("src/a.py", "new")), self.task(1, ("src/a.py", "old"))])
        self.assertEqual(self.rows(t)[0]["member"], "new")
        t = self.ticket([self.task(1, ("src/a.py", "m")), self.task(2, ("src/b.py", "n"))])
        self.assertEqual({r["path"]: r["member"] for r in self.rows(t)}, {"src/a.py": "m", "src/b.py": "n"})

    def test_a_single_worker_has_no_member(self):
        self.assertIsNone(self.rows(self.ticket([self.task(1, ("src/a.py", None))]))[0]["member"])

    def test_tests_empty_when_the_map_knows_the_file_and_nothing_covers_it(self):
        t = self.ticket([self.task(1, ("src/a.py", None), ("src/b.py", None), ("src/c.py", None))])
        rows = {r["path"]: r["tests"] for r in self.rows(t, tests_of={"src/a.py": ["tests/test_a.py", "tests/test_a2.py"],
                                                                      "src/b.py": []})}
        self.assertEqual(rows, {"src/a.py": ["tests/test_a.py", "tests/test_a2.py"], "src/b.py": [], "src/c.py": None})

    def test_tests_null_for_every_file_when_the_map_is_unread(self):
        t = self.ticket([self.task(1, ("src/a.py", None), ("src/b.py", None))])
        self.assertEqual([r["tests"] for r in logbook.ticket_files(t, [], [], None)], [None, None])

    def test_adrs_are_the_numbers_of_the_adrs_that_cite_the_path_sorted(self):
        t = self.ticket([self.task(1, ("src/a.py", None), ("src/b.py", None))])
        items = [{"number": "0007", "files": ["src/a.py", "x"]}, {"number": "0002", "files": ["src/a.py"]},
                 {"number": "0003", "files": ["src/other.py"]}]
        got = {r["path"]: r["adrs"] for r in self.rows(t, adrs=items)}
        self.assertEqual(got, {"src/a.py": ["0002", "0007"], "src/b.py": []})

    def test_adrs_null_when_the_adrs_are_unread(self):
        t = self.ticket([self.task(1, ("src/a.py", None))])
        for unread in (None, self.UNREAD):
            with self.subTest(unread=unread):
                self.assertIsNone(logbook.ticket_files(t, unread, [], {})[0]["adrs"])

    def test_held_by_lists_the_holding_tickets_whose_globs_match_sorted(self):
        t = self.ticket([self.task(1, ("src/a.py", None), ("docs/a.md", None))])
        holds = [{"ticket": "0008", "globs": ["src/*"], "state": "pr-opened", "holding": True},
                 {"ticket": "0003", "globs": ["README.md", "src/a.py"], "state": "ci-failed", "holding": True},
                 {"ticket": "0001", "globs": ["src/*"], "state": "rolled-back", "holding": False},
                 {"ticket": "0005", "globs": ["lib/*"], "state": "opened", "holding": True}]
        got = {r["path"]: r["held_by"] for r in self.rows(t, holds=holds)}
        self.assertEqual(got, {"src/a.py": ["0003", "0008"], "docs/a.md": []})

    def test_held_by_null_when_the_holders_are_unread(self):
        t = self.ticket([self.task(1, ("src/a.py", None))])
        for unread in (None, self.UNREAD):
            with self.subTest(unread=unread):
                self.assertIsNone(logbook.ticket_files(t, [], unread, {})[0]["held_by"])

    def test_one_unread_source_does_not_null_the_others(self):
        t = self.ticket([self.task(1, ("src/a.py", None))])
        row = logbook.ticket_files(t, [{"number": "0002", "files": ["src/a.py"]}], self.UNREAD, {"src/a.py": ["tests/t.py"]})[0]
        self.assertEqual((row["tests"], row["adrs"], row["held_by"]), (["tests/t.py"], ["0002"], None))

    def test_no_tasks_no_files(self):
        self.assertEqual(self.rows(self.ticket([])), [])

    def test_tasks_with_no_files_give_no_rows(self):
        t = self.ticket([{"attempt": 1, "files": None}, {"attempt": 2}, self.task(3)])
        self.assertEqual(self.rows(t), [])


ROOT = Path(__file__).resolve().parents[2]
STUB = ROOT / "fixtures" / "logbook" / "stub"
GET_SH = '#!/bin/sh\nset -eu\nd=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)\nf="$d/state/$1.$2.json"\n[ -f "$f" ] || exit 1\ncat "$f"\n'
ENV = {"LEVEL": "l0", "WORKLOAD": "app", "CODE_HOST": "stub-host", "STATE_STORE": "stub-state", "DELIVERY": "stub-delivery",
       "TICKETS_DIR": "tickets", "RELEASE_RECORD": "release.json", "RELEASES_LOG": "releases.jsonl",
       "PROMOTE_OUT": "promote", "POSTMORTEM_DIR": "postmortem", "WORKLOAD_CONTRACT": "contract",
       # The profile's model, the test's own names (docs/adr/0086 §1): no model id of a vendor here.
       "MODEL_PROVIDER": "prov", "MODEL": "model-a", "AGENT_HARNESS": "fake-cli"}


class Reader(unittest.TestCase):
    """The reader over the stub sources (fixtures/logbook/stub), as ci/logbook.sh
    runs it: `python3 core/logbook.py --out FILE` in a temp root, with the
    project map and the plane unread (a source it cannot read is {ok: false},
    never a default). Each case changes one fact of the tower's documents and
    reads what docs/adr/0071 §1 says follows."""

    def read(self, mutate=None, extra=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "adapters" / "stub-state").mkdir(parents=True)
            (root / "adapters" / "stub-state" / "get.sh").write_text(GET_SH)
            for name in ("state", "tickets", "policy", "contract", "promote", "postmortem", "roles"):
                shutil.copytree(STUB / name, root / name)
            # The run in flight (docs/adr/0087 §4): the hooks' count where crew.sh leaves it.
            shutil.copytree(STUB / "crew", root / ".crew")
            for name in ("release.json", "releases.jsonl"):
                shutil.copy(STUB / name, root / name)
            os.symlink(ROOT / "core", root / "core")
            if mutate:
                mutate(root)
            env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
            env.update(ENV)
            env.pop("WINDOW_DAYS", None)
            env.update(extra or {})
            ran = subprocess.run([sys.executable, "core/logbook.py", "--out", "out.json"], cwd=root, env=env,
                                 capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            return json.loads((root / "out.json").read_text(encoding="utf-8"))

    def state(self, root, ticket):
        return root / "state" / f"tickets.{ticket}.json"

    def edit(self, ticket, change):
        def mutate(root):
            path = self.state(root, ticket)
            doc = json.loads(path.read_text(encoding="utf-8"))
            change(doc)
            path.write_text(json.dumps(doc))
        return mutate

    def ticket(self, book, ticket="0010"):
        return [t for t in book["tickets"] if t["id"] == ticket][0]

    def source(self, ticket="0010"):
        return json.loads((STUB / "state" / f"tickets.{ticket}.json").read_text(encoding="utf-8"))

    @classmethod
    def setUpClass(cls):
        cls.book = None

    def base(self):
        if Reader.book is None:
            Reader.book = self.read()
        return Reader.book

    def test_the_schema_is_1_6(self):
        # 1.6 adds the flow, the roles, the burn and the run in flight (docs/adr/0085-0087); additions only.
        self.assertEqual(self.base()["schema"], "lights-out/logbook/1.6")

    def test_ci_and_rework_carry_gates_and_not_the_raw_lines(self):
        t = self.ticket(self.base())
        src = self.source()
        self.assertNotIn("lines", t["ci"])
        self.assertEqual([r["line"] for r in t["ci"]["gates"]], src["ci"]["lines"])
        self.assertEqual([(r["gate"], r["verdict"]) for r in t["ci"]["gates"]],
                         [(g, "GO") for g in ("risk", "secrets", "test-weakening", "deps", "sast", "test", "mutation", "test-proof")])
        self.assertNotIn("lines", t["rework"][0])
        self.assertEqual([r["line"] for r in t["rework"][0]["gates"]], src["rework"][0]["lines"])
        self.assertEqual([r["verdict"] for r in t["rework"][0]["gates"]], ["GO"] * 6 + ["NO-GO"])
        self.assertEqual(t["rework"][0]["gates"][6]["gate"], "mutation")

    def test_a_ticket_with_no_lines_has_gates_null_not_missing(self):
        book = self.base()
        for t in book["tickets"]:
            if t["id"] in ("0010", "0003") or not isinstance(t.get("ci"), dict):
                continue
            self.assertIn("gates", t["ci"], t["id"])
            self.assertIsNone(t["ci"]["gates"], t["id"])
            self.assertNotIn("lines", t["ci"], t["id"])

    def test_members_patch_and_files_pass_through(self):
        t = self.ticket(self.base())
        src = self.source()
        for got, want in zip(t["tasks"], src["tasks"]):
            self.assertEqual(got["members"], want["members"])
            self.assertEqual(got["patch"], want["patch"])
            self.assertEqual(got["files"], want["files"])

    def test_a_task_without_them_says_null_for_each(self):
        def drop(doc):
            for task in doc["tasks"]:
                for key in ("members", "patch", "files"):
                    task.pop(key, None)
        t = self.ticket(self.read(self.edit("0010", drop)))
        for task in t["tasks"]:
            self.assertEqual((task["members"], task["patch"], task["files"]), (None, None, None))
        self.assertEqual(t["files"], [])

    def test_an_attempt_in_flight_has_its_patch_withheld(self):
        task = self.ticket(self.base(), "0004")["tasks"][0]
        self.assertEqual(task["patch"], {"ok": False, "error": "withheld: the secrets gate did not say GO on attempt 1"})
        self.assertEqual(task["files"], self.source("0004")["tasks"][0]["files"])
        self.assertIsNone(task["members"])

    def test_the_withheld_patch_does_not_carry_the_text_anywhere_in_the_logbook(self):
        text = self.source("0004")["tasks"][0]["patch"]["text"]
        self.assertIn("RENAME", text)
        self.assertNotIn("RENAME", json.dumps(self.ticket(self.base(), "0004")))

    def test_secrets_no_go_on_the_rejected_attempt_withholds_that_attempts_patch_only(self):
        def change(doc):
            doc["rework"][0]["lines"][1] = "NO-GO: secrets — a key in notify/send.py"
        t = self.ticket(self.read(self.edit("0010", change)))
        self.assertEqual(t["tasks"][0]["patch"], {"ok": False, "error": "withheld: the secrets gate did not say GO on attempt 1"})
        self.assertEqual(t["tasks"][1]["patch"], self.source()["tasks"][1]["patch"])

    def test_secrets_no_go_on_the_last_attempt_withholds_the_last_patch_only(self):
        def change(doc):
            doc["ci"]["lines"][1] = "NO-GO: secrets — a key in notify/send.py"
        t = self.ticket(self.read(self.edit("0010", change)))
        self.assertEqual(t["tasks"][1]["patch"], {"ok": False, "error": "withheld: the secrets gate did not say GO on attempt 2"})
        self.assertEqual(t["tasks"][0]["patch"], self.source()["tasks"][0]["patch"])

    def test_secrets_not_run_withholds_the_patch(self):
        def change(doc):
            doc["rework"][0]["lines"] = ["NO-GO: perimeter — src/other.py is outside the ticket's perimeter"]
        t = self.ticket(self.read(self.edit("0010", change)))
        self.assertEqual(t["tasks"][0]["patch"]["ok"], False)
        self.assertIn("attempt 1", t["tasks"][0]["patch"]["error"])
        self.assertEqual([(r["gate"], r["verdict"]) for r in t["rework"][0]["gates"]], [("perimeter", "NO-GO")])

    def test_no_lines_at_all_withholds_the_patch_and_gates_are_null(self):
        def change(doc):
            del doc["rework"][0]["lines"]
            del doc["ci"]["lines"]
        t = self.ticket(self.read(self.edit("0010", change)))
        self.assertIsNone(t["rework"][0]["gates"])
        self.assertIsNone(t["ci"]["gates"])
        self.assertEqual([task["patch"]["ok"] for task in t["tasks"]], [False, False])

    def test_a_ci_that_judged_another_head_does_not_vouch_for_the_last_attempt(self):
        def change(doc):
            doc["ci"]["head_sha"] = "an-earlier-head"
        t = self.ticket(self.read(self.edit("0010", change)))
        self.assertEqual(t["tasks"][1]["patch"]["ok"], False)
        self.assertEqual(t["tasks"][0]["patch"], self.source()["tasks"][0]["patch"])

    def test_a_line_off_the_contract_is_a_row_with_nulls_and_does_not_hide_secrets(self):
        def change(doc):
            doc["ci"]["lines"].insert(2, "make: a stray line the gates did not write")
        t = self.ticket(self.read(self.edit("0010", change)))
        row = t["ci"]["gates"][2]
        self.assertEqual(row, {"gate": None, "verdict": None, "line": "make: a stray line the gates did not write"})
        self.assertEqual(t["tasks"][1]["patch"], self.source()["tasks"][1]["patch"])

    def test_files_rows_of_the_network_ticket_without_a_map(self):
        rows = self.ticket(self.base())["files"]
        # The stub's own paths and globs, read from its tower document: no
        # workload path is spelt in core/ (ci/app-free.sh).
        source = self.source()
        globs = [m["perimeter"][0] for m in source["tasks"][0]["members"]]
        self.assertEqual([r["path"] for r in rows], sorted({f["path"] for t in source["tasks"] for f in t["files"]}))
        self.assertEqual([(r["glob"], r["member"], r["attempts"]) for r in rows],
                         [(globs[0], "impl", [1, 2]), (globs[1], "tests", [1])])
        # no project map was given: tests and adrs are unread, not empty
        self.assertEqual([(r["tests"], r["adrs"]) for r in rows], [(None, None), (None, None)])
        self.assertEqual([r["held_by"] for r in rows], [[], []])

    def test_files_name_who_holds_the_path_from_the_perimeters_held(self):
        def change(root):
            path = root / "state" / "perimeters.held.json"
            held = json.loads(path.read_text(encoding="utf-8"))
            held["tickets"]["0003"] = [self.source()["tasks"][0]["members"][0]["perimeter"][0]]
            held["tickets"]["0001"] = ["tests/*"]
            path.write_text(json.dumps(held))
        rows = self.ticket(self.read(change))["files"]
        self.assertEqual(rows[0]["held_by"], ["0003"])
        self.assertEqual(rows[1]["held_by"], [])

    def test_two_runs_over_the_same_sources_write_the_same_bytes(self):
        self.assertEqual(json.dumps(self.read(), sort_keys=True), json.dumps(self.base(), sort_keys=True))


# --- 1.4 (docs/adr/0078): the why of a NO-GO ---------------------------------

def withheld(n):
    return {"ok": False, "error": f"withheld: the secrets gate did not say GO on attempt {n}"}


class WhyOfAnEntry(unittest.TestCase):
    """logbook.why(entry, attempt, judge), ADR 0078 §2 and §3: the entry as the
    tower stores it (keys line, failed, details, sast, lines, judge), the
    attempt it belongs to, and the judge to say when the entry names none."""

    SAST = "NO-GO: sast — in the workbench: this diff introduces 1 finding(s); list on stderr"
    NEW = [{"rule": "B602", "file": "a.py", "line": 7}]

    def entry(self, **more):
        base = {"line": "NO-GO: gates — test: NO-GO: test — 2 failed", "failed": "test",
                "details": ["FAILED t::one", "FAILED t::two"], "sast": None,
                "lines": ["GO: risk — low, review", "GO: secrets", "NO-GO: test — 2 failed"]}
        base.update(more)
        return base

    def test_the_schema_is_1_6(self):
        self.assertEqual(logbook.SCHEMA, "lights-out/logbook/1.6")

    def test_a_ci_that_failed_a_gate_after_secrets_said_go(self):
        self.assertEqual(logbook.why(self.entry(), 2, "gates"),
                         {"attempt": 2, "judge": "gates", "gate": "test",
                          "line": "NO-GO: gates — test: NO-GO: test — 2 failed",
                          "details": ["FAILED t::one", "FAILED t::two"], "sast": None})

    def test_the_result_has_those_six_keys_and_changes_nothing_in_the_entry(self):
        e = self.entry()
        before = json.dumps(e, sort_keys=True)
        self.assertEqual(set(logbook.why(e, 1, "gates")), {"attempt", "judge", "gate", "line", "details", "sast"})
        self.assertEqual(json.dumps(e, sort_keys=True), before)

    def test_the_entrys_judge_wins_over_the_default(self):
        self.assertEqual(logbook.why(self.entry(judge="base"), 1, "gates")["judge"], "base")

    def test_the_default_judge_is_used_when_the_entry_names_none(self):
        self.assertEqual(logbook.why(self.entry(), 1, "gates")["judge"], "gates")
        self.assertEqual(logbook.why(self.entry(), 1, "main")["judge"], "main")

    def test_the_failed_gate_the_record_names_wins_over_the_lines(self):
        self.assertEqual(logbook.why(self.entry(failed="sast"), 1, "gates")["gate"], "sast")

    def test_without_a_failed_the_first_no_go_row_names_the_gate(self):
        for failed in (None, ""):
            e = self.entry(failed=failed, lines=["GO: secrets", "NO-GO: deps — x", "NO-GO: test — y"])
            self.assertEqual(logbook.why(e, 1, "gates")["gate"], "deps", repr(failed))
        e = self.entry()
        del e["failed"]
        self.assertEqual(logbook.why(e, 1, "gates")["gate"], "test")

    def test_a_no_go_gate_name_is_read_by_the_output_contract(self):
        e = self.entry(failed=None, lines=["GO: secrets", "NO-GO: test-weakening — a test lost an assert"])
        self.assertEqual(logbook.why(e, 1, "gates")["gate"], "test-weakening")

    def test_a_line_off_the_contract_names_no_gate(self):
        e = self.entry(failed=None, lines=["GO: secrets", "make: *** [test] Error 1", "NO-GO test"])
        self.assertIsNone(logbook.why(e, 1, "gates")["gate"])

    def test_no_no_go_row_and_no_failed_is_gate_none(self):
        e = self.entry(failed=None, lines=["GO: secrets", "GO: test"])
        self.assertIsNone(logbook.why(e, 1, "gates")["gate"])

    def test_a_review_entry_has_its_reason_lines_shown_and_no_gate(self):
        e = {"line": "NO-GO: review — too broad", "details": ["too broad", "second line"], "judge": "review",
             "lines": ["GO: risk — low, review", "GO: secrets", "GO: test"]}
        got = logbook.why(e, 4, "gates")
        self.assertEqual((got["judge"], got["gate"], got["details"], got["attempt"]),
                         ("review", None, ["too broad", "second line"], 4))
        self.assertEqual(got["line"], "NO-GO: review — too broad")

    def test_secrets_go_with_a_suffix_still_says_go(self):
        e = self.entry(lines=["GO: secrets — 0 findings", "NO-GO: test — 2 failed"])
        self.assertEqual(logbook.why(e, 1, "gates")["details"], ["FAILED t::one", "FAILED t::two"])

    def test_secrets_no_go_withholds_details_with_the_attempt_in_the_reason(self):
        e = self.entry(lines=["GO: risk — low, review", "NO-GO: secrets — a key in notify/send.py"])
        got = logbook.why(e, 3, "gates")
        self.assertEqual(got["details"], withheld(3))
        self.assertEqual(got["gate"], "test")  # the record's `failed` still names it
        self.assertEqual(got["line"], e["line"])

    def test_secrets_not_run_withholds(self):
        e = self.entry(failed=None, lines=["NO-GO: perimeter — src/other.py is outside the ticket's perimeter"])
        got = logbook.why(e, 1, "gates")
        self.assertEqual(got["details"], withheld(1))
        self.assertEqual(got["gate"], "perimeter")

    def test_a_gate_whose_name_only_starts_with_secrets_is_not_secrets(self):
        e = self.entry(lines=["GO: secrets-extra", "NO-GO: test — 2 failed"])
        self.assertEqual(logbook.why(e, 1, "gates")["details"], withheld(1))

    def test_no_lines_at_all_withholds(self):
        for e in (self.entry(lines=[]), self.entry(lines=None)):
            self.assertEqual(logbook.why(e, 2, "gates")["details"], withheld(2))
        e = self.entry()
        del e["lines"]
        self.assertEqual(logbook.why(e, 2, "gates")["details"], withheld(2))

    def test_a_withheld_details_leaves_no_text_in_the_result(self):
        e = self.entry(details=["assert 'sk-live-123' == 'x'"], lines=[])
        self.assertNotIn("sk-live-123", json.dumps(logbook.why(e, 1, "gates")))

    def test_sast_findings_are_shown_with_secrets_go(self):
        e = self.entry(failed="sast", sast=self.NEW, lines=["GO: secrets", self.SAST])
        got = logbook.why(e, 1, "gates")
        self.assertEqual(got["sast"], self.NEW)
        self.assertEqual(got["gate"], "sast")

    def test_sast_findings_are_withheld_with_secrets_no_go(self):
        e = self.entry(failed="sast", sast=self.NEW, lines=["NO-GO: secrets — a key"])
        got = logbook.why(e, 1, "gates")
        self.assertEqual(got["sast"], withheld(1))
        self.assertEqual(got["details"], withheld(1))
        self.assertNotIn("B602", json.dumps(got))

    def test_a_sast_that_is_none_stays_none_even_when_withheld(self):
        for lines in ([], ["GO: secrets"], ["NO-GO: secrets — a key"]):
            self.assertIsNone(logbook.why(self.entry(sast=None, lines=lines), 1, "gates")["sast"], lines)

    def test_an_entry_with_no_sast_key_says_none(self):
        e = self.entry()
        del e["sast"]
        self.assertIsNone(logbook.why(e, 1, "gates")["sast"])


class WhyInTheLogbook(unittest.TestCase):
    """`why` in the assembled ticket, over the stub's tower documents with one
    fact changed (ADR 0078 §2, §3, §5)."""

    read = Reader.read
    edit = Reader.edit
    state = Reader.state
    ticket = Reader.ticket
    source = Reader.source

    @classmethod
    def setUpClass(cls):
        cls.book = None

    def base(self):
        if WhyInTheLogbook.book is None:
            WhyInTheLogbook.book = self.read()
        return WhyInTheLogbook.book

    def gate_rows(self, t):
        return [r for r in t["timeline"] if r["phase"] == "gate"]

    def test_the_schema_is_1_6(self):
        # 1.6 adds the flow, the roles, the burn and the run in flight (docs/adr/0085-0087); additions only.
        self.assertEqual(self.base()["schema"], "lights-out/logbook/1.6")

    def test_0003s_current_ci_why(self):
        t = self.ticket(self.base(), "0003")
        src = self.source("0003")
        self.assertEqual(t["ci"]["why"],
                         {"attempt": 2, "judge": "gates", "gate": "test",
                          "line": "NO-GO: gates — test: NO-GO: test — 2 failed",
                          "details": ["FAILED tests/a.py::one", "FAILED tests/a.py::two"], "sast": None})
        self.assertEqual(t["ci"]["why"]["line"], src["ci"]["line"])
        self.assertEqual(t["ci"]["why"]["details"], src["ci"]["details"])
        self.assertEqual(t["ci"]["details"], src["ci"]["details"])  # the 1.3 field, shown as it was

    def test_0003s_first_rework_entry_why_carries_the_sast_findings(self):
        t = self.ticket(self.base(), "0003")
        src = self.source("0003")["rework"][0]
        self.assertEqual(t["rework"][0]["why"],
                         {"attempt": 1, "judge": "gates", "gate": "sast", "line": src["line"],
                          "details": ["new: B602 README.md:7", "new: B105 README.md:9"],
                          "sast": [{"rule": "B602", "file": "README.md", "line": 7},
                                   {"rule": "B105", "file": "README.md", "line": 9}]})
        self.assertEqual(t["rework"][0]["details"], src["details"])

    def test_0003s_attempt_and_timeline_follow_the_new_stub(self):
        t = self.ticket(self.base(), "0003")
        self.assertEqual(t["attempt"], 2)
        self.assertEqual([r["line"] for r in self.gate_rows(t)], self.source("0003")["ci"]["details"])

    def test_ticket_0002s_recorded_no_gate_lines_so_its_details_are_withheld(self):
        t = self.ticket(self.base(), "0002")
        self.assertEqual(t["rework"][0]["why"]["details"], withheld(1))
        self.assertEqual(t["rework"][0]["why"]["line"], "NO-GO: tests — 1 failed")
        self.assertIsNone(t["rework"][0]["details"])
        self.assertNotIn("test_join", json.dumps(t["rework"][0]))

    def test_0010s_rejected_attempt_is_shown_whole(self):
        t = self.ticket(self.base(), "0010")
        src = self.source("0010")["rework"][0]
        w = t["rework"][0]["why"]
        self.assertEqual((w["attempt"], w["judge"], w["gate"], w["line"], w["details"], w["sast"]),
                         (1, "gates", "mutation", src["line"], src["details"], None))
        self.assertEqual(t["rework"][0]["details"], src["details"])

    def test_a_ci_that_said_go_has_why_none_but_the_key_is_there(self):
        seen = 0
        for t in self.base()["tickets"]:
            if isinstance(t.get("ci"), dict) and t["ci"].get("verdict") == "GO":
                seen += 1
                self.assertIn("why", t["ci"], t["id"])
                self.assertIsNone(t["ci"]["why"], t["id"])
        self.assertGreaterEqual(seen, 2)

    def test_ci_why_is_set_only_for_a_no_go(self):
        for t in self.base()["tickets"]:
            ci = t.get("ci")
            if isinstance(ci, dict) and "why" in ci:
                self.assertEqual(ci["why"] is not None, ci.get("verdict") == "NO-GO", t["id"])

    def test_flipping_a_ci_to_go_takes_its_why_away(self):
        def change(doc):
            doc["ci"]["verdict"] = "GO"
        self.assertIsNone(self.ticket(self.read(self.edit("0003", change)), "0003")["ci"]["why"])

    def test_every_rework_entry_has_a_why_with_its_own_attempt_and_judge(self):
        seen = 0
        for t in self.base()["tickets"]:
            for r in t.get("rework") or []:
                seen += 1
                self.assertIsInstance(r.get("why"), dict, t["id"])
                self.assertEqual(r["why"]["attempt"], r["attempt"], t["id"])
                self.assertEqual(r["why"]["judge"], r["judge"], t["id"])
                self.assertEqual(r["why"]["line"], r["line"], t["id"])
        self.assertGreaterEqual(seen, 5)

    def test_a_review_entry_without_gate_lines_is_withheld_and_names_no_gate(self):
        t = self.ticket(self.base(), "0007")
        w = t["rework"][1]["why"]
        self.assertEqual((w["judge"], w["gate"], w["attempt"]), ("review", None, 4))
        self.assertEqual(w["details"], withheld(4))
        self.assertIsNone(t["rework"][1]["details"])
        # the stub records no gate lines on either of 0007's entries
        self.assertEqual(t["rework"][0]["why"]["details"], withheld(3))
        self.assertIsNone(t["rework"][0]["details"])

    def test_a_review_entry_whose_gates_said_secrets_go_shows_the_reason_lines(self):
        def change(doc):
            doc["rework"][1]["lines"] = ["GO: risk — low, review", "GO: secrets", "GO: test"]
        t = self.ticket(self.read(self.edit("0007", change)), "0007")
        w = t["rework"][1]["why"]
        self.assertEqual((w["judge"], w["gate"], w["details"]), ("review", None, ["too broad", "second line"]))
        self.assertEqual(t["rework"][1]["details"], ["too broad", "second line"])

    def test_secrets_no_go_on_the_current_ci_withholds_its_details_everywhere(self):
        def change(doc):
            doc["ci"]["lines"][1] = "NO-GO: secrets — a key in README.md"
        t = self.ticket(self.read(self.edit("0003", change)), "0003")
        self.assertEqual(t["ci"]["why"]["details"], withheld(2))
        self.assertIsNone(t["ci"]["why"]["sast"])  # null in the record: nothing to withhold
        self.assertIsNone(t["ci"]["details"])
        self.assertEqual(self.gate_rows(t), [])
        self.assertNotIn("FAILED tests/a.py", json.dumps(t))
        # the first rejected attempt is judged on its own gate lines
        self.assertEqual(t["rework"][0]["why"]["details"], ["new: B602 README.md:7", "new: B105 README.md:9"])

    def test_secrets_no_go_on_a_rework_attempt_withholds_that_attempts_details_and_findings_only(self):
        def change(doc):
            doc["rework"][0]["lines"][1] = "NO-GO: secrets — a key in README.md"
        t = self.ticket(self.read(self.edit("0003", change)), "0003")
        w = t["rework"][0]["why"]
        self.assertEqual((w["details"], w["sast"]), (withheld(1), withheld(1)))
        self.assertEqual(w["gate"], "sast")
        self.assertIsNone(t["rework"][0]["details"])
        self.assertNotIn("B602", json.dumps(t["rework"][0]))
        self.assertEqual(t["ci"]["why"]["details"], self.source("0003")["ci"]["details"])
        self.assertEqual(len(self.gate_rows(t)), 2)

    def test_secrets_not_run_withholds_the_ci_details(self):
        def change(doc):
            doc["ci"]["lines"] = ["NO-GO: perimeter — README.md is outside the ticket's perimeter"]
        t = self.ticket(self.read(self.edit("0003", change)), "0003")
        self.assertEqual(t["ci"]["why"]["details"], withheld(2))
        self.assertEqual(self.gate_rows(t), [])

    def test_a_ci_with_no_lines_withholds_where_1_3_showed(self):
        def change(doc):
            del doc["ci"]["lines"]
        t = self.ticket(self.read(self.edit("0003", change)), "0003")
        self.assertEqual(t["ci"]["why"]["details"], withheld(2))
        self.assertIsNone(t["ci"]["details"])
        self.assertEqual(self.gate_rows(t), [])
        self.assertEqual(t["ci"]["why"]["line"], self.source("0003")["ci"]["line"])  # the line stays

    def test_the_gate_comes_from_the_lines_when_the_record_names_none(self):
        def change(doc):
            del doc["ci"]["failed"]
        t = self.ticket(self.read(self.edit("0003", change)), "0003")
        self.assertEqual(t["ci"]["why"]["gate"], "test")

    def test_the_ci_why_attempt_is_the_tickets_attempt(self):
        def change(doc):
            doc["attempt"] = 3
        self.assertEqual(self.ticket(self.read(self.edit("0003", change)), "0003")["ci"]["why"]["attempt"], 3)

    def test_shown_details_are_one_gate_row_each_in_the_timeline(self):
        t = self.ticket(self.base(), "0003")
        rows = self.gate_rows(t)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["line"] for r in rows], t["ci"]["why"]["details"])

    def test_the_old_golden_has_no_why(self):
        # A 1.3 logbook stays readable: why is an addition, never a requirement.
        old = json.loads((ROOT / "fixtures" / "logbook" / "golden-1.3.json").read_text(encoding="utf-8"))
        self.assertEqual(old["schema"], "lights-out/logbook/1.3")
        for t in old["tickets"]:
            self.assertNotIn("why", t.get("ci") or {}, t["id"])


class SpendInTheLogbook(unittest.TestCase):
    """Logbook 1.5's `spend` and the needs-human outcome's `stop`, over the stub
    sources, by hand from docs/adr/0083's amendment of 2026-11-13."""

    read = Reader.read
    edit = Reader.edit
    state = Reader.state
    ticket = Reader.ticket
    source = Reader.source

    @classmethod
    def setUpClass(cls):
        cls.book = None

    def base(self):
        if SpendInTheLogbook.book is None:
            SpendInTheLogbook.book = self.read()
        return SpendInTheLogbook.book

    def row(self, row, usd, runs, unknown, **more):
        self.assertAlmostEqual(row["cost_usd"], usd)
        self.assertEqual((row["runs"], row["unknown"]), (runs, unknown))
        for key, value in more.items():
            self.assertEqual(row[key], value, key)

    def test_per_ticket(self):
        t = self.base()["spend"]["tickets"]
        self.row(t["0003"], 1.1625, 2, 0, agent_s=420, elapsed_s=1200)
        self.row(t["0010"], 0, 2, 1, agent_s=30, elapsed_s=5400)
        elapsed = {"0001": 1800, "0002": 7200, "0004": 300, "0005": 60, "0007": 3000, "0008": 2400, "0009": 607}
        for tid, secs in elapsed.items():
            self.row(t[tid], 0, 0, 0, agent_s=0, elapsed_s=secs)
        self.assertEqual(sorted(t), sorted(list(elapsed) + ["0003", "0010"]))

    def test_per_role_and_per_day_and_in_all(self):
        s = self.base()["spend"]
        self.assertEqual(sorted(s["roles"]), ["dev-worker", "test-reviewer"])
        self.row(s["roles"]["dev-worker"], 1.1625, 3, 0, agent_s=420)
        self.row(s["roles"]["test-reviewer"], 0, 1, 1, agent_s=30)
        self.assertEqual(sorted(s["days"]), ["2026-11-02", "2026-11-03"])
        self.row(s["days"]["2026-11-02"], 0, 2, 1)
        self.row(s["days"]["2026-11-03"], 1.1625, 2, 0)
        self.row(s["total"], 1.1625, 4, 1)

    def test_the_commands_words_and_the_limits(self):
        s = self.base()["spend"]
        self.assertEqual(s["summary"], "9 tickets, 4 runs, $1.16 known, 1 of cost unknown")
        self.assertEqual(s["limits"], {"SPEND_BUDGET_TICKET_USD": 1.0, "SPEND_BUDGET_DAY_USD": None})
        self.assertEqual(s["lines"][-1], "budget: SPEND_BUDGET_TICKET_USD=$1.00, SPEND_BUDGET_DAY_USD no limit")
        self.assertIn("ticket 0003: $1.16 over 2 run(s); agents 0h07m00s, elapsed 0h20m00s", s["lines"])
        self.assertIn("role test-reviewer: $0.00 over 1 run(s), 1 of cost unknown; 0h00m30s", s["lines"])
        self.assertIn("day 2026-11-03: $1.16 over 2 run(s)", s["lines"])
        kinds = [line.split(" ")[0] for line in s["lines"]]
        self.assertEqual(kinds, ["ticket"] * 9 + ["role"] * 2 + ["day"] * 2 + ["burn:", "projection:", "budget:"])

    def test_the_cap_is_the_stop_of_0007_with_its_1_4_line(self):
        t = self.ticket(self.base(), "0007")
        self.assertEqual(t["outcome"]["verdict"], "needs-human")
        self.assertEqual(t["outcome"]["stop"], "cap")
        src = self.source("0007")
        self.assertEqual(t["outcome"]["line"], src["rework"][-1]["line"])
        self.assertEqual(t["outcome"]["judge"], src["rework"][-1].get("judge"))

    def test_the_budget_is_the_stop_and_its_line_the_outcomes(self):
        line = "spend budget: this ticket spent $4.20, at or over SPEND_BUDGET_TICKET_USD=$4.00; the next attempt is not launched"
        book = self.read(self.edit("0007", lambda d: d.update(budget={"line": line})))
        t = self.ticket(book, "0007")
        src = self.source("0007")
        self.assertEqual((t["outcome"]["verdict"], t["outcome"]["stop"], t["outcome"]["line"]), ("needs-human", "budget", line))
        self.assertEqual(t["outcome"]["judge"], src["rework"][-1].get("judge"))

    def test_no_stop_but_at_needs_human(self):
        for t in self.base()["tickets"]:
            if t["state"] != "needs-human":
                self.assertNotIn("stop", t["outcome"], t["id"])

    def test_tickets_unread_make_spend_the_same_error(self):
        book = self.read(lambda root: (root / "adapters" / "stub-state" / "get.sh").write_text("#!/bin/sh\necho broken >&2\nexit 3\n"))
        self.assertEqual(book["tickets"], {"ok": False, "error": "broken"})
        self.assertEqual(book["spend"], book["tickets"])

    def test_a_malformed_limit_is_an_error_naming_the_key_and_the_report_stays(self):
        def bad(root):
            path = root / "policy" / "rework.env"
            path.write_text(path.read_text(encoding="utf-8").replace("SPEND_BUDGET_DAY_USD=", "SPEND_BUDGET_DAY_USD=x"))
        s = self.read(bad)["spend"]
        self.assertIs(s["limits"]["ok"], False)
        self.assertIn("SPEND_BUDGET_DAY_USD", s["limits"]["error"])
        self.assertEqual(s["lines"][-1], "budget: " + s["limits"]["error"])
        self.assertEqual(s["total"]["runs"], 4)


class DoraInTheLogbook(unittest.TestCase):
    """Logbook 1.5's `dora`, over the stub sources, by hand from docs/adr/0082's
    amendment of 2026-11-13: the window ends at the record's last event."""

    read = Reader.read

    @classmethod
    def setUpClass(cls):
        cls.book = None

    def base(self):
        if DoraInTheLogbook.book is None:
            DoraInTheLogbook.book = self.read()
        return DoraInTheLogbook.book

    def test_the_window_ends_at_the_last_event(self):
        d = self.base()["dora"]
        self.assertEqual((d["schema"], d["window_days"], d["from"], d["to"]),
                         ("dora/1", 30, "2026-10-08T08:10:07Z", "2026-11-07T08:10:07Z"))

    def test_the_four_measures_by_hand(self):
        m = self.base()["dora"]["measures"]
        f = m["deployment_frequency"]
        self.assertEqual((f["measured"], f["count"]), (True, 2))
        self.assertAlmostEqual(f["per_day"], 2 / 30)
        self.assertEqual(m["lead_time"], {"measured": True, "median_s": 7650, "n": 2, "without_ticket": 0})
        self.assertEqual(m["change_fail_rate"], {"measured": True, "rate": 0.5, "failed": 2, "decided": 4, "pending": 0})
        self.assertEqual(m["recovery_time"], {"measured": True, "median_s": 90, "n": 1, "unmeasured": 1})

    def test_the_lines_are_the_commands(self):
        from core import dora
        d = self.base()["dora"]
        self.assertEqual(d["lines"], [line[len("[dora] "):] for line in dora.lines(d)])
        self.assertEqual(len(d["lines"]), 5)

    def test_a_window_that_is_not_a_whole_number_is_an_error_naming_it(self):
        for bad in ("0", "x"):
            d = self.read(extra={"WINDOW_DAYS": bad})["dora"]
            self.assertIs(d["ok"], False, bad)
            self.assertIn("WINDOW_DAYS", d["error"], bad)

    def test_another_window(self):
        d = self.read(extra={"WINDOW_DAYS": "7"})["dora"]
        self.assertEqual((d["window_days"], d["from"]), (7, "2026-10-31T08:10:07Z"))

    def test_a_record_with_no_time_is_an_error(self):
        def empty(root):
            for doc in (root / "state").glob("tickets.*.json"):
                doc.unlink()
            (root / "releases.jsonl").write_text("")
        d = self.read(empty)["dora"]
        self.assertIs(d["ok"], False)
        self.assertIn("no time", d["error"])

    def test_releases_unread_make_four_not_measured(self):
        book = self.read(lambda root: (root / "releases.jsonl").write_text("not json\n"))
        self.assertIs(book["releases"]["ok"], False)
        m = book["dora"]["measures"]
        for key in ("deployment_frequency", "lead_time", "change_fail_rate", "recovery_time"):
            self.assertIs(m[key]["measured"], False, key)
            self.assertIn(book["releases"]["error"], m[key]["why"], key)

    def test_the_old_golden_has_neither(self):
        old = json.loads((ROOT / "fixtures" / "logbook" / "golden-1.4.json").read_text(encoding="utf-8"))
        self.assertEqual(old["schema"], "lights-out/logbook/1.4")
        self.assertNotIn("dora", old)
        self.assertNotIn("spend", old)


GATES = ("risk", "secrets", "test-weakening", "deps", "sast", "test", "mutation", "test-proof")
FLOW = ["ticket", "perimeter"] + ["gate"] * 8 + ["pr", "canary", "human", "full"]
NODE_KEYS = {"node", "gate", "verdict", "started_at", "ended_at", "seconds", "line"}


class FlowInTheLogbook(unittest.TestCase):
    """Logbook 1.6's `tickets[].flow`, over the stub sources, by hand from
    docs/adr/0085 §1-§3: fourteen nodes in order, each with its verdict, its
    times from the record, its seconds and its one-line reason."""

    read = Reader.read
    edit = Reader.edit
    state = Reader.state
    ticket = Reader.ticket
    source = Reader.source

    @classmethod
    def setUpClass(cls):
        cls.book = None

    def base(self):
        if FlowInTheLogbook.book is None:
            FlowInTheLogbook.book = self.read()
        return FlowInTheLogbook.book

    def flow(self, book, tid):
        return self.ticket(book, tid)["flow"]

    def node(self, flow, name):
        return [n for n in flow if (n["gate"] if n["node"] == "gate" else n["node"]) == name][0]

    def is_node(self, n, verdict, line=None, started=None, ended=None, seconds=None):
        self.assertEqual((n["verdict"], n["line"], n["started_at"], n["ended_at"], n["seconds"]),
                         (verdict, line, started, ended, seconds), n)

    def test_the_schema_is_1_6(self):
        self.assertEqual(self.base()["schema"], "lights-out/logbook/1.6")
        self.assertEqual(logbook.SCHEMA, "lights-out/logbook/1.6")

    def test_every_ticket_has_fourteen_nodes_in_order_with_seven_keys(self):
        for t in self.base()["tickets"]:
            self.assertEqual([n["node"] for n in t["flow"]], FLOW, t["id"])
            self.assertEqual([n["gate"] for n in t["flow"] if n["node"] == "gate"], list(GATES), t["id"])
            for n in t["flow"]:
                self.assertEqual(set(n), NODE_KEYS, (t["id"], n))
                self.assertIn(n["verdict"], ("GO", "NO-GO", "running", "not-reached"), (t["id"], n))
                if n["node"] != "gate" and n["seconds"] is not None:
                    self.assertTrue(n["started_at"] and n["ended_at"], (t["id"], n))
                if n["node"] != "gate":
                    self.assertIsNone(n["gate"])

    def test_0010_from_the_open_to_100_percent(self):
        f = self.flow(self.base(), "0010")
        src = self.source("0010")
        self.is_node(self.node(f, "ticket"), "GO", "opened directly: no request, no spec gate",
                     "2026-11-02T06:00:00Z", "2026-11-02T06:00:00Z", None)
        self.is_node(self.node(f, "perimeter"), "GO",
                     "PR #10 opened, every file inside " + ", ".join(logbook.perimeter(STUB / "tickets" / "0010.md")),
                     "2026-11-02T06:00:00Z", "2026-11-02T06:05:00Z", 300)
        for gate, line in zip(GATES, src["ci"]["lines"]):
            self.is_node(self.node(f, gate), "GO", line, None, None, src["ci"]["seconds"][gate])
        self.is_node(self.node(f, "pr"), "GO", "merged m10, approved by the test-reviewer",
                     "2026-11-02T06:55:00Z", "2026-11-02T07:06:00Z", 660)
        self.is_node(self.node(f, "canary"), "GO", "held at 25%: 2 stage(s) GO",
                     "2026-11-02T07:08:00Z", "2026-11-02T07:30:00Z", 1320)
        self.is_node(self.node(f, "human"), "GO", "promoted by bob via cli",
                     "2026-11-02T07:30:00Z", "2026-11-02T07:45:00Z", 900)
        self.is_node(self.node(f, "full"), "GO", "100% of the traffic on 0.2.5-n",
                     "2026-11-02T07:45:00Z", "2026-11-02T07:45:00Z", None)

    def without_answer(self, root):
        path = root / "releases.jsonl"
        lines = [l for l in path.read_text(encoding="utf-8").splitlines()
                 if '"version": "0.2.5-n"' not in l or '"kind": "release"' in l]
        path.write_text("\n".join(lines) + "\n")

    def test_0010_held_with_no_answer_waits_for_you(self):
        f = self.flow(self.read(self.without_answer), "0010")
        self.is_node(self.node(f, "human"), "running", "waits for go-for-launch at 25%", "2026-11-02T07:30:00Z", None, None)
        self.is_node(self.node(f, "full"), "not-reached")

    def test_0010_rejected_by_a_person(self):
        def rejected(root):
            # The answer sits after its release line and before the next one, as promote writes it.
            path = root / "releases.jsonl"
            no = json.dumps({"kind": "answer", "at": "2026-11-02T07:50:00Z", "version": "0.2.5-n", "answer": "NO-GO",
                             "by": "carol", "via": "console", "reason": "not this week"})
            out = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if '"version": "0.2.5-n"' in line and '"kind": "answer"' in line:
                    line = no
                out.append(line)
            path.write_text("\n".join(out) + "\n")
        f = self.flow(self.read(rejected), "0010")
        self.is_node(self.node(f, "human"), "NO-GO", "rejected by carol via console: not this week",
                     "2026-11-02T07:30:00Z", "2026-11-02T07:50:00Z", 1200)
        self.is_node(self.node(f, "full"), "not-reached", "rolled back by a person")

    def test_0003_stops_at_test_and_the_rest_is_not_reached(self):
        f = self.flow(self.base(), "0003")
        src = self.source("0003")
        for gate, line in zip(GATES[:5], src["ci"]["lines"]):
            self.is_node(self.node(f, gate), "GO", line, None, None, src["ci"]["seconds"][gate])
        self.is_node(self.node(f, "test"), "NO-GO", "NO-GO: test — 2 failed", None, None, 41)
        for gate in ("mutation", "test-proof"):
            self.is_node(self.node(f, gate), "not-reached", "not run: test said NO-GO first")
        for name in ("pr", "canary", "human", "full"):
            self.is_node(self.node(f, name), "not-reached")
        self.is_node(self.node(f, "perimeter"), "GO", "PR #3 opened, every file inside README.md",
                     "2026-11-03T08:00:00Z", "2026-11-03T08:05:00Z", 300)

    def test_0009_the_spec_gate_said_no_go(self):
        f = self.flow(self.base(), "0009")
        self.is_node(self.node(f, "ticket"), "NO-GO", "NO-GO: spec — no ## Perimeter section",
                     "2026-11-07T08:00:00Z", "2026-11-07T08:10:07Z", 607)
        for n in f[1:]:
            self.assertEqual(n["verdict"], "not-reached", n)

    def test_a_question_of_the_product_role_is_running(self):
        def asked(d):
            d["history"] = d["history"][:2]
            d["questions"] = d["questions"][:1]
            d["questions"][0].pop("answer"), d["questions"][0].pop("answered_by"), d["questions"][0].pop("answered_at")
        f = self.flow(self.read(self.edit("0009", asked)), "0009")
        self.is_node(self.node(f, "ticket"), "running",
                     "the product role asked: Is the first person on the list promoted when a seat frees up?; it waits for an answer",
                     "2026-11-07T08:00:00Z", None, None)

    def test_0005_assign_failed(self):
        f = self.flow(self.base(), "0005")
        self.assertEqual(self.node(f, "ticket")["verdict"], "GO")
        self.is_node(self.node(f, "perimeter"), "NO-GO", "step exited 1", "2026-11-04T07:00:00Z", "2026-11-04T07:01:00Z", 60)
        for n in f[2:]:
            self.assertEqual(n["verdict"], "not-reached", n)

    def test_0004_stranded_at_ci(self):
        f = self.flow(self.base(), "0004")
        self.is_node(self.node(f, "risk"), "NO-GO", "ci step failed: the gates did not run")
        for n in f[3:]:
            self.assertEqual(n["verdict"], "not-reached", n)

    def test_0001_rolled_back_by_the_canary(self):
        f = self.flow(self.base(), "0001")
        self.assertEqual(self.node(f, "canary")["verdict"], "NO-GO")
        self.assertEqual(self.node(f, "canary")["line"], "5%: error_rate 1.000")
        self.is_node(self.node(f, "human"), "not-reached", "the canary rolled back before it")
        self.is_node(self.node(f, "full"), "not-reached")

    def test_0008_review_changes_requested(self):
        f = self.flow(self.base(), "0008")
        for gate in GATES:
            self.is_node(self.node(f, gate), "GO", "GO: ci")
        n = self.node(f, "pr")
        self.assertEqual((n["verdict"], n["line"]), ("NO-GO", "first line"))

    def test_gates_running_at_pr_opened_and_pr_running_at_review(self):
        def opened(d):
            d["state"], d["attempt"], d["ci"], d["rework"] = "pr-opened", 1, None, []
            d["history"] = d["history"][:2]
        f = self.flow(self.read(self.edit("0003", opened)), "0003")
        for gate in GATES:
            self.is_node(self.node(f, gate), "running", "the gates judge attempt 1; the step reports when all have run",
                         "2026-11-03T08:05:00Z", None, None)

        def review(d):
            d["state"] = "review"
            d["history"] = d["history"][:5]
            d["review"], d["merge"], d["release"] = None, None, None
        f = self.flow(self.read(self.edit("0010", review)), "0010")
        self.is_node(self.node(f, "pr"), "running", "the test-reviewer reviews attempt 2 (risk low)",
                     "2026-11-02T06:55:00Z", None, None)

    def test_a_ci_with_seconds_is_kept_on_the_ticket_and_its_rework(self):
        t = self.ticket(self.base(), "0010")
        src = self.source("0010")
        self.assertEqual(t["ci"]["seconds"], src["ci"]["seconds"])
        self.assertEqual(t["rework"][0]["seconds"], src["rework"][0]["seconds"])


ROLE_ORDER = ["architect", "dev-worker", "ops-triage", "product", "release", "test-reviewer"]


class RolesInTheLogbook(unittest.TestCase):
    """Logbook 1.6's `roles` and `roles_summary`, over the stub sources (its roles/
    copies the committed role.env keys), by hand from docs/adr/0086 §1."""

    read = Reader.read
    ticket = Reader.ticket

    @classmethod
    def setUpClass(cls):
        cls.book = None

    def base(self):
        if RolesInTheLogbook.book is None:
            RolesInTheLogbook.book = self.read()
        return RolesInTheLogbook.book

    def row(self, book, role):
        return [r for r in book["roles"] if r["role"] == role][0]

    def test_six_rows_in_the_network_tables_order(self):
        self.assertEqual([r["role"] for r in self.base()["roles"]], ROLE_ORDER)

    def test_configured_from_the_profile_and_role_env(self):
        b = self.base()
        self.assertEqual(self.row(b, "dev-worker")["configured"],
                         {"provider": "prov", "model": "model-a", "harness": "fake-cli", "thinking": "high"})
        self.assertEqual(self.row(b, "product")["configured"],
                         {"provider": "prov", "model": "model-a", "harness": "adk", "thinking": "medium"})
        self.assertEqual({r["role"]: r["configured"]["thinking"] for r in b["roles"]},
                         {"architect": "high", "dev-worker": "high", "ops-triage": "low", "product": "medium", "release": "low",
                          "test-reviewer": "high"})

    def test_budgets(self):
        self.assertEqual({r["role"]: r["budget"] for r in self.base()["roles"]},
                         {"architect": 600000, "dev-worker": 2600000, "ops-triage": None, "product": None, "release": None,
                          "test-reviewer": 1500000})

    def test_the_dev_worker_runs_on_0003(self):
        r = self.row(self.base(), "dev-worker")
        self.assertEqual(r["last"], {"ticket": "0003", "step": "rework", "attempt": 2, "at": "2026-11-03T08:15:00Z",
                                     "harness": "gemini-cli", "provider": "gemini", "model": "gemini-3.8-flash", "replayed": False,
                                     "tokens": {"input": 400000, "output": 10000, "total": 410000}, "cost_usd": 0.3375,
                                     "failed": None})
        self.assertEqual(r["running"], {"ticket": "0003", "tokens": 2210000, "budget": 2600000, "warn": True})
        self.assertEqual((r["used"], r["state"]), (2210000, "running"))
        self.assertEqual(r["line"], "running on 0003: 2,210,000 of 2,600,000 tokens — near the budget")

    def test_without_the_run_in_flight_the_dev_worker_ran(self):
        r = self.row(self.read(lambda root: shutil.rmtree(root / ".crew")), "dev-worker")
        self.assertEqual((r["running"], r["used"], r["state"]), (None, 410000, "ran"))
        self.assertEqual(r["line"], "last ran on 0003 (rework, attempt 2) at 2026-11-03T08:15:00Z: 410,000 tokens of 2,600,000")

    def test_the_test_reviewer_ran_on_0010(self):
        r = self.row(self.base(), "test-reviewer")
        self.assertEqual((r["last"]["ticket"], r["last"]["step"], r["last"]["model"], r["last"]["cost_usd"]), ("0010", "review", "model-x", None))
        self.assertEqual((r["used"], r["state"]), (30900, "ran"))
        self.assertEqual(r["line"], "last ran on 0010 (review, attempt 1) at 2026-11-02T06:40:00Z: 30,900 tokens of 1,500,000")

    def test_the_four_others_are_idle(self):
        for role in ("architect", "ops-triage", "product", "release"):
            r = self.row(self.base(), role)
            self.assertEqual((r["last"], r["running"], r["used"], r["state"], r["line"]),
                             (None, None, None, "idle", "has not run in this record"), role)

    def test_the_summary(self):
        self.assertEqual(self.base()["roles_summary"],
                         "6 roles on 1 provider: prov; last runs on gemini/gemini-3.8-flash, prov/model-x")

    def test_at_l0_no_provider_and_no_model(self):
        b = self.read(extra={"MODEL_PROVIDER": "", "MODEL": "", "AGENT_HARNESS": "replay"})
        r = self.row(b, "dev-worker")
        self.assertEqual(r["configured"], {"provider": None, "model": None, "harness": "replay", "thinking": "high"})
        self.assertEqual(b["roles_summary"],
                         "6 roles on no provider: the profile replays recorded runs; last runs on gemini/gemini-3.8-flash, prov/model-x")

    def test_no_roles_directory_is_an_error(self):
        b = self.read(lambda root: shutil.rmtree(root / "roles"))
        self.assertEqual(b["roles"], {"ok": False, "error": "no roles/ directory: the six roles are its subdirectories"})
        self.assertIsNone(b["roles_summary"])

    def test_an_unreadable_role_env_is_that_rows_error(self):
        b = self.read(lambda root: (root / "roles" / "architect" / "role.env").write_bytes(b"THINKING=\xff\xfe\n"))
        r = self.row(b, "architect")
        self.assertEqual((r["configured"], r["budget"]), (None, None))
        self.assertEqual(r["error"], "roles/architect/role.env is not UTF-8")
        self.assertEqual(self.row(b, "dev-worker")["configured"]["thinking"], "high")


class LiveAndBurnInTheLogbook(unittest.TestCase):
    """Logbook 1.6's `tickets[].live` and `spend.burn`, over the stub sources (its
    crew/0003/out/tokens holds 2,210,000), by hand from docs/adr/0087 §3-§4."""

    read = Reader.read
    edit = Reader.edit
    state = Reader.state
    ticket = Reader.ticket

    @classmethod
    def setUpClass(cls):
        cls.book = None

    def base(self):
        if LiveAndBurnInTheLogbook.book is None:
            LiveAndBurnInTheLogbook.book = self.read()
        return LiveAndBurnInTheLogbook.book

    def tokens(self, n):
        return lambda root: (root / ".crew" / "0003" / "out" / "tokens").write_text(f"{n}\n")

    def test_0003s_run_in_flight(self):
        self.assertEqual(self.ticket(self.base(), "0003")["live"], {
            "role": "dev-worker", "attempt": 3, "tokens": 2210000, "budget": 2600000, "warn": True,
            "line": "dev-worker, attempt 3: 2,210,000 of 2,600,000 tokens (85%) — near TOKEN_BUDGET, the run stops at 2,600,000"})

    def test_no_other_ticket_is_in_flight(self):
        for t in self.base()["tickets"]:
            if t["id"] != "0003":
                self.assertIsNone(t["live"], t["id"])

    def test_the_warning_starts_at_80_percent(self):
        self.assertFalse(self.ticket(self.read(self.tokens(2079999)), "0003")["live"]["warn"])
        live = self.ticket(self.read(self.tokens(2080000)), "0003")["live"]
        self.assertTrue(live["warn"])
        self.assertEqual(live["line"], "dev-worker, attempt 3: 2,080,000 of 2,600,000 tokens (80%) — near TOKEN_BUDGET, the run stops at 2,600,000")

    def test_not_in_flight(self):
        for what, mutate in (
                ("a run.json beside it", lambda root: (root / ".crew" / "0003" / "out" / "run.json").write_text("{}")),
                ("no tokens file", lambda root: (root / ".crew" / "0003" / "out" / "tokens").unlink()),
                ("a count that is not a number", self.tokens("many")),
                ("the ticket at review", self.edit("0003", lambda d: d.update(state="review"))),
                ("an error last", self.edit("0003", lambda d: d["history"].append(
                    {"step": "rework", "state": "ci-failed", "at": "2026-11-03T08:30:00Z", "error": "step exited 1"})))):
            self.assertIsNone(self.ticket(self.read(mutate), "0003")["live"], what)

    def test_no_budget(self):
        def unbudgeted(root):
            path = root / "roles" / "dev-worker" / "role.env"
            path.write_text("".join(l for l in path.read_text(encoding="utf-8").splitlines(True) if not l.startswith("TOKEN_BUDGET=")))
        live = self.ticket(self.read(unbudgeted), "0003")["live"]
        self.assertEqual((live["budget"], live["warn"], live["line"]), (None, False, "dev-worker, attempt 3: 2,210,000 tokens, no budget"))

    def test_the_burn_of_the_stubs_last_day(self):
        b = self.base()["spend"]["burn"]
        self.assertEqual((b["day"], b["first"], b["end"], b["runs"], b["unknown"]),
                         ("2026-11-03", "2026-11-03T08:05:00Z", "2026-11-03T08:15:00Z", 2, 0))
        for key, want in (("spent_usd", 1.1625), ("hours", 1.0), ("per_hour_usd", 1.1625), ("left_h", 15.75), ("projected_usd", 19.471875)):
            self.assertAlmostEqual(b[key], want, places=6, msg=key)
        self.assertEqual({i: v for i, v in enumerate(b["hourly"]) if v}, {8: 1.1625})
        self.assertEqual((b["limit_usd"], b["over"]), (None, None))

    def test_the_burn_lines_before_the_budget(self):
        lines = self.base()["spend"]["lines"]
        self.assertEqual(lines[-3:], [
            "burn: $1.16 per hour on 2026-11-03 ($1.16 known in 2 run(s) from 08:05 to 08:15 UTC, over 1.0 h)",
            "projection: $19.47 by the end of 2026-11-03 UTC at that rate, as of 08:15 UTC; SPEND_BUDGET_DAY_USD no limit",
            "budget: SPEND_BUDGET_TICKET_USD=$1.00, SPEND_BUDGET_DAY_USD no limit"])


if __name__ == "__main__":
    unittest.main()
