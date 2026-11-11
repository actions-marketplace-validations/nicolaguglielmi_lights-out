"""Tests for core/network.py and `./go network`, written from
docs/adr/0071 §4-§6 and the interface contract the session fixed for the third
slice of M17, never from the implementation.

The view is text: a first line, three headings at column 0 (`graph`, `stream`,
`files by perimeter`), and fact lines, each starting with a space; the
chosen attempt's patch sits between two column-0 marker lines. Each test
builds a logbook in a temp file (the 1.3 golden does not exist until the
reader writes it, so the logbook here is fixtures/logbook/golden-1.2.json with
the 1.3 fields added by hand from ADR 0071 §1 and the stub's tower documents,
for ticket 0010 and ticket 0004) and runs `python3 core/network.py --logbook`
as a process, from the repository root. Only the monkeypatch tests call
`network.main(argv)` in-process (the repository's own convention: tower.main,
logbook.main), because a patched TABLE cannot cross a process.

Not asserted, because the ADR does not say: the words of any sentence (they
are TABLE.words, and the test reads them from there), the glyph that marks an
added or removed line, how a truncated patch is announced, what a 1.3 ticket
with no gate record prints.
"""

import contextlib
import copy
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core import network

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_12 = ROOT / "fixtures" / "logbook" / "golden-1.2.json"
STUB = ROOT / "fixtures" / "logbook" / "stub"
HEADINGS = ["graph", "stream", "files by perimeter"]
WITHHELD_1 = "withheld: the secrets gate did not say GO on attempt 1"
GATE_LINE = re.compile(r"^(GO|NO-GO): ([a-z0-9-]+)( — .*)?$")


def rows(lines):
    """gate rows from a gate run's lines, as ADR 0071 §1 defines them."""
    out = []
    for line in lines:
        m = GATE_LINE.match(line)
        out.append({"gate": m.group(2) if m else None, "verdict": m.group(1) if m else None, "line": line})
    return out


def netbook():
    """The golden's 1.2 logbook with the 1.3 fields: ticket 0010 (the network
    ticket of the stub), ticket 0004 with its attempt in flight and the patch
    withheld, and nothing else changed."""
    book = json.loads(GOLDEN_12.read_text(encoding="utf-8"))
    book["schema"] = "lights-out/logbook/1.3"
    for t in book["tickets"]:
        if isinstance(t.get("ci"), dict):
            t["ci"]["gates"] = None
        for r in t.get("rework") or []:
            r["gates"] = None
        t["files"] = []
    src = json.loads((STUB / "state" / "tickets.0010.json").read_text(encoding="utf-8"))
    base = copy.deepcopy([t for t in book["tickets"] if t["id"] == "0002"][0])
    ci = {k: v for k, v in src["ci"].items() if k != "lines"}
    ci["gates"] = rows(src["ci"]["lines"])
    rework = {k: v for k, v in src["rework"][0].items() if k != "lines"}
    rework["gates"] = rows(src["rework"][0]["lines"])
    t10 = dict(base, id="0010", title="Notify the waitlist", state="held", attempt=2, adrs=["0002"],
               perimeter=["app/backend/notify/*", "tests/test_notify.py"], updated_at="2026-11-02T07:30:00Z",
               opened_at="2026-11-02T06:00:00Z", tasks=copy.deepcopy(src["tasks"]), task=src["task"], ci=ci,
               rework=[rework], review=src["review"], release=src["release"], merge=src["merge"], pr=src["pr"],
               outcome={"judge": "human", "line": "promoted by bob via cli", "verdict": "GO"},
               files=[{"path": "app/backend/notify/send.py", "glob": "app/backend/notify/*", "member": "impl",
                       "attempts": [1, 2], "tests": ["tests/test_notify.py"], "adrs": ["0002"], "held_by": []},
                      {"path": "tests/test_notify.py", "glob": "tests/test_notify.py", "member": "tests",
                       "attempts": [1], "tests": [], "adrs": [], "held_by": []}])
    book["tickets"].append(t10)
    book["releases"].append({
        "answer": {"answer": "GO", "at": "2026-11-02T07:45:00Z", "by": "bob", "via": "cli"},
        "at": "2026-11-02T07:29:00Z", "from": "releases.jsonl", "held_at": 25, "image": "img-n", "stable": "0.1.0",
        "stages": [{"numbers": ["slo: a"], "pct": 5, "verdict": "GO"}, {"numbers": ["slo: b"], "pct": 25, "verdict": "GO"}],
        "ticket": "0010", "verdict": "held", "version": "0.2.5-n"})
    t4 = [t for t in book["tickets"] if t["id"] == "0004"][0]
    t4["attempt"] = 1
    t4["tasks"] = [{"role": "dev-worker", "harness": "replay", "model": "stub-model", "attempt": 1, "members": None,
                    "patch": {"ok": False, "error": WITHHELD_1},
                    "files": [{"path": "app/backend/migrations/0002_rename.py", "added": 1, "removed": 0, "member": None}]}]
    t4["files"] = [{"path": "app/backend/migrations/0002_rename.py", "glob": "app/backend/migrations/*", "member": None,
                    "attempts": [1], "tests": None, "adrs": [], "held_by": []}]
    return book


def oldbook():
    """The same logbook as a 1.2 reader wrote it: no members, patches, files or
    gate rows, and the schema says 1.2."""
    book = netbook()
    book["schema"] = "lights-out/logbook/1.2"
    for t in book["tickets"]:
        t.pop("files", None)
        for task in t.get("tasks") or []:
            for key in ("members", "patch", "files"):
                task.pop(key, None)
        for entry in ([t["ci"]] if isinstance(t.get("ci"), dict) else []) + list(t.get("rework") or []):
            entry.pop("gates", None)
    return book


def verdict_of(text):
    """GO, NO-GO or not run: how a gate fact line says it after `gate <name>: `."""
    return re.match(r"(NO-GO|GO|not run)", text).group(1)


def ticket_of(book, ident):
    return [t for t in book["tickets"] if t["id"] == ident][0]


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, book, name="logbook.json"):
        path = self.dir / name
        path.write_text(json.dumps(book, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        return path

    def cli(self, *args):
        ran = subprocess.run([sys.executable, "core/network.py", *args], cwd=ROOT, capture_output=True)
        return ran.returncode, ran.stdout, ran.stderr

    def view(self, book, *args):
        """(code, stdout text, stderr text) of `core/network.py --logbook <book> ARGS`."""
        code, out, err = self.cli("--logbook", str(self.write(book)), *args)
        return code, out.decode("utf-8"), err.decode("utf-8")

    def ok(self, book, *args):
        code, out, err = self.view(book, *args)
        self.assertEqual(code, 0, err)
        return out

    def inproc(self, book, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = network.main(["--logbook", str(self.write(book)), *args])
        return code, out.getvalue(), err.getvalue()


def parse(out):
    """The view's parts: the first line, the three regions, the patch block, and the fact lines of each region."""
    lines = out.split("\n")
    at = {h: lines.index(h) for h in HEADINGS if h in lines}
    patch_start = next((i for i, l in enumerate(lines) if re.fullmatch(r"--- patch of attempt \d+ ---", l)), None)
    patch_end = next((i for i, l in enumerate(lines) if l == "--- end of patch ---"), None)
    block = set(range(patch_start, patch_end + 1)) if patch_start is not None and patch_end is not None else set()

    def region(a, b):
        return [(i, l) for i, l in enumerate(lines[a:b], a) if i not in block]
    bounds = [at.get("graph"), at.get("stream"), at.get("files by perimeter"), len(lines)]
    facts = lambda part: [l.strip() for _, l in part if l.startswith(" ")]  # noqa: E731
    graph = region(bounds[0] + 1, bounds[1]) if None not in bounds[:2] else []
    stream = region(bounds[1] + 1, bounds[2]) if None not in bounds[1:3] else []
    files = region(bounds[2] + 1, bounds[3]) if bounds[2] is not None else []
    patch = lines[patch_start + 1:patch_end] if block else None
    return {"lines": lines, "first": lines[0], "at": at, "patch_at": (patch_start, patch_end), "patch": patch,
            "graph": facts(graph), "stream": facts(stream), "files": facts(files)}


class Defaults(Case):
    """ADR 0071 §2, §4: the default ticket is the newest updated_at (null last,
    ties to the highest id), the default attempt is the latest."""

    def test_the_default_ticket_is_the_newest_and_a_ticket_with_no_attempt_says_so(self):
        book = netbook()
        newest = max((t for t in book["tickets"]), key=lambda t: (t["updated_at"] or "", t["id"]))
        out = self.ok(book)
        self.assertEqual(parse(out)["first"], f"ticket {newest['id']} — {newest['title']} · no attempt yet")
        self.assertEqual(newest["id"], "0009")

    def test_a_tie_goes_to_the_highest_id(self):
        book = netbook()
        for t in book["tickets"]:
            t["updated_at"] = "2026-11-01T00:00:00Z"
        out = self.ok(book)
        self.assertTrue(parse(out)["first"].startswith("ticket 0010 — "), parse(out)["first"])

    def test_a_null_updated_at_comes_last(self):
        book = netbook()
        ticket_of(book, "0009")["updated_at"] = None
        newest = max((t for t in book["tickets"] if t["updated_at"]), key=lambda t: (t["updated_at"], t["id"]))
        self.assertNotEqual(newest["id"], "0009")
        self.assertTrue(parse(self.ok(book))["first"].startswith(f"ticket {newest['id']} — "), parse(self.ok(book))["first"])
        for t in book["tickets"]:
            t["updated_at"] = None
        self.assertTrue(parse(self.ok(book))["first"].startswith("ticket 0010 — "))

    def test_the_default_attempt_is_the_latest(self):
        book = netbook()
        ticket_of(book, "0009")["updated_at"] = "2020-01-01T00:00:00Z"
        out = self.ok(book, "--ticket", "0010")
        self.assertEqual(parse(out)["first"], "ticket 0010 — Notify the waitlist · attempt 2")

    def test_ticket_and_attempt_pick_what_they_name(self):
        book = netbook()
        self.assertEqual(parse(self.ok(book, "--ticket", "0010", "--attempt", "1"))["first"],
                         "ticket 0010 — Notify the waitlist · attempt 1")
        self.assertEqual(parse(self.ok(book, "--ticket", "0010", "--attempt", "2"))["first"],
                         "ticket 0010 — Notify the waitlist · attempt 2")
        self.assertEqual(parse(self.ok(book, "--ticket", "0004"))["first"], "ticket 0004 — Rename a column · attempt 1")

    def test_headings_are_at_column_zero_and_in_order(self):
        for args in ((), ("--ticket", "0010"), ("--ticket", "0010", "--attempt", "1"), ("--ticket", "0004")):
            p = parse(self.ok(netbook(), *args))
            self.assertEqual(list(p["at"]), HEADINGS, args)
            self.assertEqual(sorted(p["at"].values()), list(p["at"].values()), args)

    def test_the_first_line_is_at_column_zero_and_is_not_a_fact(self):
        for args in ((), ("--ticket", "0010")):
            first = parse(self.ok(netbook(), *args))["first"]
            self.assertTrue(first.startswith("ticket "), first)
            self.assertFalse(first.startswith(" "))


class Graph(Case):
    """ADR 0071 §2, §4: the graph's state, one fact line per role, per worker,
    per gate."""

    def graph(self, *args, book=None):
        return parse(self.ok(book or netbook(), "--ticket", "0010", *args))["graph"]

    def table(self):
        return network.TABLE

    def test_one_role_line_per_role_of_the_table_in_the_table_s_order(self):
        roles = [f for f in self.graph() if f.startswith("role ")]
        self.assertEqual([re.match(r"role ([^:]+):", f).group(1) for f in roles], self.table()["roles"])
        self.assertEqual(len(roles), 6)

    def test_a_role_the_record_names_reads_differently_from_one_it_does_not(self):
        tails = {}
        for f in self.graph():
            m = re.match(r"role ([^:]+):(.*)$", f)
            if m:
                tails[m.group(1)] = m.group(2).strip()
        ran = {"dev-worker", "test-reviewer"}  # tasks[].role and review.role of ticket 0010
        self.assertTrue(ran <= set(tails))
        ran_tails = {tails[r] for r in ran}
        idle_tails = {v for k, v in tails.items() if k not in ran}
        self.assertTrue(ran_tails and idle_tails)
        self.assertFalse(ran_tails & idle_tails, f"a role that ran reads like one that did not: {tails}")

    def test_product_ran_only_when_it_was_consulted(self):
        def tail(book):
            for f in self.graph(book=book):
                if f.startswith("role product:"):
                    return f
        book = netbook()
        before = tail(book)
        ticket_of(book, "0010")["product"] = {"consulted": True, "harness": "replay", "model": "m"}
        self.assertNotEqual(tail(book), before)

    def test_one_worker_line_per_member_of_the_attempt_in_order(self):
        workers = [f for f in self.graph() if f.startswith("worker ")]
        self.assertEqual([re.match(r"worker ([^:]+):", f).group(1) for f in workers], ["impl", "tests"])

    def test_a_worker_line_carries_harness_and_model_and_the_hand_written_one_has_no_model(self):
        workers = {re.match(r"worker ([^:]+):", f).group(1): f for f in self.graph() if f.startswith("worker ")}
        self.assertIn("replay", workers["impl"])
        self.assertIn("gemini-3.8-flash", workers["impl"])
        self.assertIn("replay", workers["tests"])
        self.assertNotIn("gemini", workers["tests"])
        self.assertNotEqual(workers["impl"].split(":", 1)[1], workers["tests"].split(":", 1)[1])

    def test_a_single_worker_attempt_draws_one_worker(self):
        graph = parse(self.ok(netbook(), "--ticket", "0004"))["graph"]
        workers = [f for f in graph if f.startswith("worker ")]
        self.assertEqual(len(workers), 1)
        self.assertIn("stub-model", workers[0])

    def test_the_latest_attempt_s_gates_are_the_eight_in_the_makefile_order_all_go(self):
        gates = [re.match(r"gate ([^:]+): (.+)$", f).groups() for f in self.graph() if f.startswith("gate ")]
        self.assertEqual([g for g, _ in gates], self.table()["gates"])
        self.assertEqual({verdict_of(v) for _, v in gates}, {"GO"})
        self.assertEqual(len(gates), 8)

    def test_the_rejected_attempt_lights_its_own_gates_then_the_ones_not_run(self):
        gates = [re.match(r"gate ([^:]+): (.+)$", f).groups() for f in self.graph("--attempt", "1") if f.startswith("gate ")]
        self.assertEqual([g for g, _ in gates], self.table()["gates"])
        self.assertEqual([verdict_of(v) for _, v in gates], ["GO"] * 6 + ["NO-GO", "not run"])

    def test_gates_run_before_the_table_s_gates_not_run_and_in_the_order_run(self):
        book = netbook()
        t = ticket_of(book, "0010")
        t["ci"]["gates"] = rows(["GO: sast — x", "GO: risk — low, review", "NO-GO: secrets — a key"])
        gates = [re.match(r"gate ([^:]+): (.+)$", f).groups() for f in self.graph(book=book) if f.startswith("gate ")]
        names = [g for g, _ in gates]
        self.assertEqual(names[:3], ["sast", "risk", "secrets"])
        self.assertEqual(sorted(names[3:]), sorted(set(self.table()["gates"]) - {"sast", "risk", "secrets"}))
        self.assertEqual([g for g in names[3:]], [g for g in self.table()["gates"] if g not in ("sast", "risk", "secrets")])
        self.assertTrue(all(v.startswith("not run") for _, v in gates[3:]))

    def test_not_run_comes_from_the_table_words(self):
        words = self.table()["words"]
        self.assertIn("not_run", words)
        template = words["not_run"]
        try:
            sentence = template.format()
        except (KeyError, IndexError):
            self.skipTest("not_run takes arguments; the sentence cannot be rebuilt here")
        lines = [f for f in self.graph("--attempt", "1") if f.startswith("gate test-proof:")]
        self.assertEqual(len(lines), 1)
        self.assertIn(sentence, lines[0])

    def test_the_canary_stages_and_the_human_gate_show_what_the_logbook_holds(self):
        graph = "\n".join(self.graph())
        self.assertIn("bob", graph)
        self.assertIn("cli", graph)
        self.assertIn("25", graph)

    def test_a_human_no_go_and_a_waiting_gate_differ_from_a_go(self):
        def graph_of(change):
            book = netbook()
            change([r for r in book["releases"] if r["ticket"] == "0010"][0])
            return "\n".join(self.graph(book=book))
        go = graph_of(lambda r: None)
        no_go = graph_of(lambda r: r["answer"].update(answer="NO-GO", by="carol"))
        waiting = graph_of(lambda r: r.update(answer=None))
        self.assertEqual(len({go, no_go, waiting}), 3)
        self.assertIn("carol", no_go)
        self.assertNotIn("bob", waiting)

    def test_a_ticket_that_never_reached_a_release_differs_from_one_that_did(self):
        book = netbook()
        reached = "\n".join(self.graph(book=book))
        book["releases"] = [r for r in book["releases"] if r["ticket"] != "0010"]
        ticket_of(book, "0010")["release"] = None
        self.assertNotEqual("\n".join(self.graph(book=book)), reached)

    def test_the_rework_loop_shows_only_when_there_was_a_rework(self):
        book = netbook()
        with_rework = "\n".join(self.graph(book=book))
        ticket_of(book, "0010")["rework"] = []
        self.assertNotEqual("\n".join(self.graph(book=book)), with_rework)


class Stream(Case):
    """ADR 0071 §4: attempts newest first, each with its files and its gate
    lines verbatim; the chosen attempt's patch, verbatim, between two markers;
    then the files by perimeter."""

    def test_the_stream_holds_every_gate_line_verbatim_newest_attempt_first(self):
        src = json.loads((STUB / "state" / "tickets.0010.json").read_text(encoding="utf-8"))
        p = parse(self.ok(netbook(), "--ticket", "0010"))
        stream = "\n".join(p["stream"])
        for line in src["ci"]["lines"] + src["rework"][0]["lines"]:
            self.assertIn(line, stream)
        newest = stream.index(src["ci"]["lines"][-1])
        oldest = stream.index(src["rework"][0]["lines"][-1])
        self.assertLess(newest, oldest, "attempt 2 is listed before attempt 1")

    def test_the_stream_names_each_attempt_s_files(self):
        stream = "\n".join(parse(self.ok(netbook(), "--ticket", "0010"))["stream"])
        self.assertIn("app/backend/notify/send.py", stream)
        self.assertIn("tests/test_notify.py", stream)
        # attempt 1 touched both files, attempt 2 send.py alone: send.py is listed under both
        self.assertGreaterEqual(stream.count("app/backend/notify/send.py"), 2)

    def test_the_patch_of_the_default_attempt_sits_between_the_markers_verbatim(self):
        book = netbook()
        want = ticket_of(book, "0010")["tasks"][1]["patch"]["text"]
        p = parse(self.ok(book, "--ticket", "0010"))
        self.assertEqual(p["lines"][p["patch_at"][0]], "--- patch of attempt 2 ---")
        self.assertEqual(p["lines"][p["patch_at"][1]], "--- end of patch ---")
        self.assertEqual("\n".join(p["patch"]).rstrip("\n"), want.rstrip("\n"))

    def test_attempt_picks_the_patch(self):
        book = netbook()
        want = ticket_of(book, "0010")["tasks"][0]["patch"]["text"]
        p = parse(self.ok(book, "--ticket", "0010", "--attempt", "1"))
        self.assertEqual(p["lines"][p["patch_at"][0]], "--- patch of attempt 1 ---")
        self.assertEqual("\n".join(p["patch"]).rstrip("\n"), want.rstrip("\n"))

    def test_the_patch_block_is_after_stream_and_before_the_files(self):
        p = parse(self.ok(netbook(), "--ticket", "0010"))
        self.assertGreater(p["patch_at"][0], p["at"]["stream"])
        self.assertLess(p["patch_at"][1], p["at"]["files by perimeter"])

    def test_the_lines_of_a_patch_are_not_facts(self):
        book = netbook()
        ticket_of(book, "0010")["tasks"][1]["patch"]["text"] = " an indented patch line\n+added\n context\n"
        p = parse(self.ok(book, "--ticket", "0010"))
        for fact in p["graph"] + p["stream"] + p["files"]:
            self.assertNotEqual(fact, "an indented patch line")

    def test_a_withheld_patch_shows_its_reason_and_no_markers(self):
        out = self.ok(netbook(), "--ticket", "0004")
        self.assertIn(WITHHELD_1, out)
        self.assertNotIn("--- patch of attempt", out)
        self.assertNotIn("--- end of patch ---", out)

    def test_a_withheld_patch_is_never_printed_even_if_the_logbook_held_text(self):
        book = netbook()
        ticket_of(book, "0004")["tasks"][0]["patch"] = {"ok": False, "error": WITHHELD_1, "text": "AKIA-LEAK"}
        self.assertNotIn("AKIA-LEAK", self.ok(book, "--ticket", "0004"))

    def test_no_patch_at_all_prints_no_markers(self):
        book = netbook()
        for task in ticket_of(book, "0010")["tasks"]:
            task["patch"] = None
        out = self.ok(book, "--ticket", "0010")
        self.assertNotIn("--- patch of attempt", out)

    def test_the_patch_is_printed_whole_even_when_it_is_long(self):
        book = netbook()
        text = "".join(f"+line {n:05d}\n" for n in range(5000))
        ticket_of(book, "0010")["tasks"][1]["patch"] = {"text": text, "bytes": len(text), "truncated": False}
        p = parse(self.ok(book, "--ticket", "0010"))
        self.assertEqual("\n".join(p["patch"]).rstrip("\n"), text.rstrip("\n"))


class Files(Case):
    """ADR 0071 §4: the files by perimeter, with who holds them, which tests
    cover them and which ADRs govern them; a glob no file matched says so."""

    def files(self, *args, book=None):
        return parse(self.ok(book or netbook(), "--ticket", "0010", *args))["files"]

    def test_the_perimeter_and_each_file_show(self):
        text = "\n".join(self.files())
        for want in ("app/backend/notify/*", "app/backend/notify/send.py", "tests/test_notify.py", "0002"):
            self.assertIn(want, text)

    def test_the_tests_that_cover_a_file_show(self):
        book = netbook()
        before = "\n".join(self.files(book=book))
        self.assertNotIn("tests/test_other.py", before)
        ticket_of(book, "0010")["files"][0]["tests"] = ["tests/test_notify.py", "tests/test_other.py"]
        self.assertIn("tests/test_other.py", "\n".join(self.files(book=book)))

    def test_a_glob_no_file_matched_says_so(self):
        book = netbook()
        ticket_of(book, "0010")["perimeter"].append("docs/never-touched/*")
        with_glob = self.files(book=book)
        self.assertTrue(any("docs/never-touched/*" in f for f in with_glob))
        without = self.files()
        self.assertFalse(any("docs/never-touched/*" in f for f in without))

    def test_a_holder_shows(self):
        book = netbook()
        self.assertNotIn("0003", "\n".join(self.files(book=book)))
        ticket_of(book, "0010")["files"][0]["held_by"] = ["0003"]
        self.assertIn("0003", "\n".join(self.files(book=book)))

    def test_an_adr_that_governs_a_file_shows(self):
        book = netbook()
        ticket_of(book, "0010")["files"][1]["adrs"] = ["0042"]
        self.assertIn("0042", "\n".join(self.files(book=book)))

    def test_an_unread_map_shows_the_top_level_error_where_tests_and_adrs_would_be(self):
        book = netbook()
        error = "no map; run ./go map"
        book["adrs"] = {"ok": False, "error": error}
        for row in ticket_of(book, "0010")["files"]:
            row["tests"] = None
            row["adrs"] = None
        self.assertIn(error, "\n".join(self.files(book=book)))

    def test_unread_perimeters_held_show_their_error(self):
        book = netbook()
        error = "the held file is down"
        book["perimeters_held"] = {"ok": False, "error": error}
        for row in ticket_of(book, "0010")["files"]:
            row["held_by"] = None
        self.assertIn(error, "\n".join(self.files(book=book)))

    def test_a_ticket_with_no_files_still_prints_the_section(self):
        p = parse(self.ok(netbook(), "--ticket", "0009"))
        self.assertIn("files by perimeter", p["at"])


class Exits(Case):
    """ADR 0071 §4: exit 1 for a logbook that is absent, not JSON or not major 1,
    exit 2 for a ticket or attempt it does not hold; stdout empty and one
    stderr line either way."""

    def refused(self, args, want):
        got, out, err = self.cli(*args)
        self.assertEqual(got, want, (args, err))
        self.assertEqual(out, b"", args)
        self.assertEqual(len(err.decode().splitlines()), 1, (args, err))
        self.assertTrue(err.strip())

    def test_an_absent_file_is_exit_1(self):
        self.refused(["--logbook", str(self.dir / "absent.json")], 1)

    def test_a_file_that_is_not_json_is_exit_1(self):
        path = self.dir / "garbage.json"
        path.write_text("not a logbook\n")
        self.refused(["--logbook", str(path)], 1)

    def test_an_empty_file_is_exit_1(self):
        path = self.dir / "empty.json"
        path.write_text("")
        self.refused(["--logbook", str(path)], 1)

    def test_major_2_is_exit_1(self):
        book = netbook()
        book["schema"] = "lights-out/logbook/2.0"
        self.refused(["--logbook", str(self.write(book))], 1)

    def test_a_schema_that_is_no_logbook_is_exit_1(self):
        for schema in ("something/else/1.0", None, 1, "lights-out/logbook/"):
            book = netbook()
            book["schema"] = schema
            with self.subTest(schema=schema):
                self.refused(["--logbook", str(self.write(book))], 1)

    def test_a_json_that_is_not_an_object_is_exit_1(self):
        path = self.dir / "list.json"
        path.write_text("[]\n")
        self.refused(["--logbook", str(path)], 1)

    def test_no_logbook_argument_is_not_a_view(self):
        got, out, _ = self.cli()
        self.assertNotEqual(got, 0)
        self.assertEqual(out, b"")

    def test_every_1_x_is_read(self):
        for minor in ("1.0", "1.1", "1.2", "1.3", "1.9"):
            book = netbook()
            book["schema"] = f"lights-out/logbook/{minor}"
            with self.subTest(minor=minor):
                self.assertEqual(self.view(book, "--ticket", "0010")[0], 0)

    def test_an_unknown_ticket_is_exit_2(self):
        path = self.write(netbook())
        self.refused(["--logbook", str(path), "--ticket", "9999"], 2)
        self.refused(["--logbook", str(path), "--ticket", "10"], 2)

    def test_an_unknown_attempt_is_exit_2(self):
        path = self.write(netbook())
        for attempt in ("0", "3", "7", "-1"):
            with self.subTest(attempt=attempt):
                self.refused(["--logbook", str(path), "--ticket", "0010", "--attempt", attempt], 2)

    def test_an_attempt_of_a_ticket_with_none_is_exit_2(self):
        self.refused(["--logbook", str(self.write(netbook())), "--ticket", "0009", "--attempt", "1"], 2)

    def test_a_good_view_prints_nothing_on_stderr(self):
        code, out, err = self.cli("--logbook", str(self.write(netbook())), "--ticket", "0010")
        self.assertEqual(code, 0)
        self.assertTrue(out)
        self.assertEqual(err, b"")

    def test_a_logbook_with_a_ticket_in_error_still_answers_for_the_others(self):
        book = netbook()
        ticket_of(book, "0009")["perimeter"] = {"ok": False, "error": "no ## Perimeter section"}
        self.assertEqual(self.view(book, "--ticket", "0010")[0], 0)
        self.assertEqual(self.view(book, "--ticket", "0009")[0], 0)


class Bytes(Case):
    """ADR 0071 §4: no colour, no clock; equal logbooks and arguments give
    equal bytes."""

    ARGS = [(), ("--ticket", "0010"), ("--ticket", "0010", "--attempt", "1"), ("--ticket", "0004"),
            ("--ticket", "0001"), ("--ticket", "0009")]

    def test_two_runs_are_byte_equal(self):
        path = str(self.write(netbook()))
        for args in self.ARGS:
            a = self.cli("--logbook", path, *args)
            b = self.cli("--logbook", path, *args)
            with self.subTest(args=args):
                self.assertEqual(a[0], 0, a[2])
                self.assertEqual(a, b)

    def test_the_same_logbook_in_another_file_gives_the_same_bytes(self):
        book = netbook()
        a = self.cli("--logbook", str(self.write(book, "a.json")), "--ticket", "0010")
        b = self.cli("--logbook", str(self.write(book, "b.json")), "--ticket", "0010")
        self.assertEqual(a, b)

    def test_no_escape_byte_anywhere_whatever_the_environment(self):
        path = str(self.write(netbook()))
        for args in self.ARGS:
            for env in ({}, {"NO_COLOR": "1"}, {"TERM": "xterm-256color", "COLORTERM": "truecolor", "FORCE_COLOR": "1",
                                                "CLICOLOR_FORCE": "1"}):
                ran = subprocess.run([sys.executable, "core/network.py", "--logbook", path, *args], cwd=ROOT,
                                     capture_output=True, env={**os.environ, **env})
                with self.subTest(args=args, env=env):
                    self.assertEqual(ran.returncode, 0, ran.stderr)
                    self.assertNotIn(b"\x1b", ran.stdout)
                    self.assertNotIn(b"\x1b", ran.stderr)

    def test_the_view_does_not_depend_on_the_clock_or_the_file_s_age(self):
        book = netbook()
        path = self.write(book)
        a = self.cli("--logbook", str(path), "--ticket", "0010")
        os.utime(path, (1, 1))
        self.assertEqual(a, self.cli("--logbook", str(path), "--ticket", "0010"))

    def test_the_view_is_text_that_ends_with_a_newline(self):
        out = self.cli("--logbook", str(self.write(netbook())), "--ticket", "0010")[1]
        out.decode("utf-8")
        self.assertTrue(out.endswith(b"\n"))

    def test_the_stdout_is_the_same_in_process_and_as_a_process(self):
        book = netbook()
        code, out, _ = self.inproc(book, "--ticket", "0010")
        self.assertEqual(code, 0)
        self.assertEqual(out.encode("utf-8"), self.cli("--logbook", str(self.write(book)), "--ticket", "0010")[1])


class OneSourceForTheWords(Case):
    """ADR 0071 §5: every sentence that is not a logbook value printed verbatim
    comes from TABLE["words"]; a copy with one template changed changes the
    output."""

    def run_with(self, words, book, *args):
        saved = dict(network.TABLE["words"])
        network.TABLE["words"].update(words)
        try:
            return self.inproc(book, *args)
        finally:
            network.TABLE["words"].clear()
            network.TABLE["words"].update(saved)

    def books(self):
        """(label, logbook, argv) for every view the fixtures can draw."""
        out = []
        for label, book in (("1.3", netbook()), ("1.2", oldbook())):
            for t in book["tickets"]:
                out.append((f"{label} {t['id']}", book, ["--ticket", t["id"]]))
                for n in sorted({task["attempt"] for task in t.get("tasks") or []}):
                    out.append((f"{label} {t['id']} attempt {n}", book, ["--ticket", t["id"], "--attempt", str(n)]))
        book = netbook()
        t10 = ticket_of(book, "0010")
        t10["tasks"][1]["patch"] = dict(t10["tasks"][1]["patch"], truncated=True)
        t10["perimeter"].append("docs/never-touched/*")
        t10["rework"].append({"attempt": 2, "judge": "review", "head_sha": "h10b", "line": "CHANGES-REQUESTED — test-reviewer",
                              "details": [], "at": "2026-11-02T06:50:00Z", "gates": rows(["GO: risk — low"])})
        t10["rework"].append({"attempt": 3, "judge": "main", "head_sha": "h10c", "line": "NO-GO: gates — red", "details": [],
                              "at": "2026-11-02T06:51:00Z", "gates": None})
        out.append(("truncated patch, three reworks, an unmatched glob", book, ["--ticket", "0010"]))
        book = netbook()
        book["adrs"] = {"ok": False, "error": "no map"}
        book["perimeters_held"] = {"ok": False, "error": "no held file"}
        book["releases"] = {"ok": False, "error": "no release log"}
        for row in ticket_of(book, "0010")["files"]:
            row.update(tests=None, adrs=None, held_by=None)
        out.append(("every source unread", book, ["--ticket", "0010"]))
        book = netbook()
        ticket_of(book, "0010")["release"] = None
        book["releases"] = [r for r in book["releases"] if r["ticket"] != "0010"]
        out.append(("no release", book, ["--ticket", "0010"]))
        book = netbook()
        [r for r in book["releases"] if r["ticket"] == "0010"][0]["answer"] = None
        out.append(("waiting for the human", book, ["--ticket", "0010"]))
        book = netbook()
        [r for r in book["releases"] if r["ticket"] == "0010"][0]["answer"]["answer"] = "NO-GO"
        out.append(("a human NO-GO", book, ["--ticket", "0010"]))
        return out

    def test_the_table_has_the_words_the_two_degradations_need(self):
        words = network.TABLE["words"]
        self.assertIsInstance(words, dict)
        for key in ("old_logbook", "not_run"):
            self.assertIn(key, words)
        for key, template in words.items():
            self.assertIsInstance(template, str, key)
            self.assertTrue(template.strip(), key)
        self.assertIn("{version}", words["old_logbook"])

    def test_changing_not_run_changes_the_output(self):
        book = netbook()
        before = self.inproc(book, "--ticket", "0010", "--attempt", "1")
        after = self.run_with({"not_run": "@@NOT-RUN@@"}, book, "--ticket", "0010", "--attempt", "1")
        self.assertEqual(before[0], 0)
        self.assertIn("@@NOT-RUN@@", after[1])
        self.assertNotEqual(before[1], after[1])

    def test_changing_old_logbook_changes_the_output_of_a_1_2_logbook(self):
        book = oldbook()
        before = self.inproc(book, "--ticket", "0010")
        after = self.run_with({"old_logbook": "@@OLD {version}@@"}, book, "--ticket", "0010")
        self.assertEqual(before[0], 0)
        self.assertIn("@@OLD 1.2@@", after[1])
        self.assertNotEqual(before[1], after[1])

    def test_every_template_is_printed_by_some_view_of_the_fixtures(self):
        """A word the views never print is a word that should not be in the
        table; one a fixture here cannot reach is a fixture to add. The
        failure lists which."""
        views = self.books()
        unused = []
        for key in sorted(network.TABLE["words"]):
            sentinel = f"@@{key.upper()}@@"
            seen = False
            for label, book, argv in views:
                code, out, _ = self.run_with({key: sentinel}, book, *argv)
                if code == 0 and sentinel in out:
                    seen = True
                    break
            if not seen:
                unused.append(key)
        self.assertEqual(unused, [], f"no view of the fixtures prints these templates: {unused}")


class OldLogbook(Case):
    """ADR 0071 §6: a 1.2 logbook degrades without an error."""

    def test_the_gates_are_one_summary_line_with_the_ci_verdict_and_line(self):
        graph = parse(self.ok(oldbook(), "--ticket", "0010"))["graph"]
        gates = [f for f in graph if f.startswith("gate ")]
        self.assertEqual(len(gates), 1, gates)
        self.assertTrue(gates[0].startswith("gate gates:"), gates[0])
        self.assertIn("GO", gates[0])
        self.assertIn("GO: gates — risk low, review", "\n".join(graph))

    def test_the_rejected_attempt_shows_the_rework_entry_s_line(self):
        book = oldbook()
        graph = parse(self.ok(book, "--ticket", "0010", "--attempt", "1"))["graph"]
        gates = [f for f in graph if f.startswith("gate ")]
        self.assertEqual(len(gates), 1)
        self.assertIn("NO-GO", gates[0])
        self.assertIn(ticket_of(book, "0010")["rework"][0]["line"], "\n".join(graph))

    def test_no_per_gate_edge_is_inferred(self):
        graph = parse(self.ok(oldbook(), "--ticket", "0010"))["graph"]
        self.assertFalse([f for f in graph if re.match(r"gate (risk|secrets|mutation|test-proof)\b", f)])

    def test_the_old_logbook_sentence_is_printed_with_its_version(self):
        out = self.ok(oldbook(), "--ticket", "0010")
        self.assertIn(network.TABLE["words"]["old_logbook"].format(version="1.2"), out)

    def test_no_patch_and_no_gate_lines_are_printed(self):
        out = self.ok(oldbook(), "--ticket", "0010")
        self.assertNotIn("--- patch of attempt", out)
        self.assertNotIn("GO: mutation — score 92%", out)

    def test_the_perimeter_still_shows(self):
        p = parse(self.ok(oldbook(), "--ticket", "0010"))
        self.assertIn("app/backend/notify/*", "\n".join(p["files"]))

    def test_the_workers_come_from_the_tasks_one_each(self):
        graph = parse(self.ok(oldbook(), "--ticket", "0010"))["graph"]
        self.assertEqual(len([f for f in graph if f.startswith("worker ")]), 1)

    def test_a_1_3_view_does_not_carry_the_old_logbook_sentence(self):
        sentence = network.TABLE["words"]["old_logbook"].format(version="1.2")
        self.assertNotIn(sentence, self.ok(netbook(), "--ticket", "0010"))

    def test_the_summary_edge_is_for_old_logbooks_only(self):
        graph = parse(self.ok(netbook(), "--ticket", "0010"))["graph"]
        self.assertFalse([f for f in graph if f.startswith("gate gates:")])

    def test_the_golden_1_2_itself_is_read_without_an_error(self):
        code, out, err = self.cli("--logbook", str(GOLDEN_12))
        self.assertEqual(code, 0, err)
        self.assertEqual(err, b"")
        self.assertIn(network.TABLE["words"]["old_logbook"].format(version="1.2").encode(), out)


class Table(Case):
    """ADR 0071 §5: `--table` prints TABLE; its roles are the directories of
    roles/, its gates the Makefile's GATES line."""

    def test_table_prints_the_table_as_the_contract_says(self):
        code, out, err = self.cli("--table")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.decode("utf-8"), json.dumps(network.TABLE, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        self.assertEqual(err, b"")

    def test_table_is_one_object_of_roles_gates_and_words(self):
        table = json.loads(self.cli("--table")[1])
        self.assertEqual(sorted(table), ["gates", "roles", "words"])
        self.assertIsInstance(table["roles"], list)
        self.assertIsInstance(table["gates"], list)
        self.assertIsInstance(table["words"], dict)

    def test_the_roles_are_the_directories_of_roles(self):
        want = sorted(p.parent.name for p in (ROOT / "roles").glob("*/role.env"))
        self.assertEqual(len(want), 6)
        self.assertEqual(network.TABLE["roles"], want)
        self.assertEqual(sorted(p.name for p in (ROOT / "roles").iterdir() if p.is_dir()), want)

    def test_the_gates_are_the_makefile_s_gates_line_in_order(self):
        text = (ROOT / "Makefile").read_text(encoding="utf-8")
        line = re.search(r"^GATES := (.*)$", text, re.M).group(1)
        self.assertEqual(network.TABLE["gates"], line.split())
        self.assertEqual(len(network.TABLE["gates"]), 8)

    def test_table_needs_no_logbook_and_writes_nothing_else(self):
        code, out, err = self.cli("--table")
        self.assertEqual(code, 0)
        self.assertTrue(out.endswith(b"\n"))
        self.assertNotIn(b"\x1b", out)

    def test_table_is_byte_equal_twice(self):
        self.assertEqual(self.cli("--table"), self.cli("--table"))


if __name__ == "__main__":
    unittest.main()
