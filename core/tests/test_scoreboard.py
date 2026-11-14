"""Tests for the provider scoreboard, written from docs/adr/0088, never from
the implementation: the ADR's four-row dataset, its four-ticket logbook and
the committed M24 dataset, with the values computed by hand there.
"""

import copy
import json
import os
import subprocess  # nosec B404 - the command under test is a script
import tempfile
import unittest

from core import scoreboard

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
M24 = os.path.join(REPO, "docs", "scoreboard", "m24-tenacity.json")


def row(ticket, group, merged, attempts, reworks, tokens, nogos=(), stop=None):
    provider, harness, model = group
    return {"ticket": ticket, "provider": provider, "harness": harness, "model": model,
            "merged": merged, "attempts": attempts, "reworks": reworks,
            "nogos": [{"gate": g, "reason": r} for g, r in nogos], "stop": stop,
            "tokens": {"input": tokens[0], "output": tokens[1], "cached": None},
            "cost_usd": {"ledger": None, "list": None, "cached": None},
            "source": {"handoff": f"handoff-{ticket}.md §2", "run": f"tower tickets/{ticket}"}}


A = ("prov-a", "h-a", "m-a")
B = ("prov-b", "h-b", "m-b")
DATASET = {
    "schema": "lights-out/scoreboard-data/1",
    "scope": "4 tickets on one test repository, one run per ticket and provider",
    "rows": [
        row("t-1", A, True, 1, 0, (1000, 100)),
        row("t-2", A, True, 2, 1, (3000, 300), nogos=[("mutation", "3/4 (0.750 < 0.800)")]),
        row("t-3", B, False, 0, 0, (5000, 500), stop={"kind": "TOKEN_BUDGET", "line": "over TOKEN_BUDGET (2600000)"}),
        row("t-4", B, True, 1, 0, (2000, 0)),
    ],
    "totals": [
        {"provider": "prov-a", "harness": "h-a", "model": "m-a", "basis": "list", "usd": 1.00, "bound": "at most",
         "note": "list price, every input token uncached", "source": "handoff-a.md §3"},
        {"provider": "prov-b", "harness": "h-b", "model": "m-b", "basis": "ledger", "usd": 4.00, "bound": "exactly",
         "note": "the ledger misses the budget-stopped runs", "source": "handoff-b.md §2"},
        {"provider": "prov-b", "harness": "h-b", "model": "m-b", "basis": "list", "usd": 10.00, "bound": "at most",
         "note": "list price over every run", "source": "handoff-b.md §2"},
    ],
    "not_run": [{"provider": "prov-c", "harness": "h-c", "why": "no key", "source": "handoff-b.md §5"}],
}


def group(groups, provider):
    found = [g for g in groups if g["provider"] == provider]
    assert len(found) == 1, (provider, groups)
    return found[0]


class Dataset(unittest.TestCase):
    """§2, §5, §6: the ADR's four-row dataset."""

    def setUp(self):
        self.rows, self.totals, self.not_run, self.scope = scoreboard.load_dataset(copy.deepcopy(DATASET))
        self.groups = scoreboard.board(self.rows, self.totals)

    def test_two_groups_run(self):
        self.assertEqual(sorted((g["provider"], g["harness"], g["model"]) for g in self.groups), [A, B])

    def test_prov_a(self):
        g = group(self.groups, "prov-a")
        self.assertEqual((g["tickets"], g["merged"], g["first_attempt"], g["reworks"], g["budget_stops"]),
                         (2, 2, 1, 1, 0))
        self.assertEqual(g["nogos"], {"mutation": ["3/4 (0.750 < 0.800)"]})
        self.assertEqual(g["tokens_per_ticket"], {"value": 2200, "over": 2})
        self.assertEqual(g["cost_per_ticket"]["list"], {"usd": 0.5, "bound": "at most"})
        self.assertIsNone(g["cost_per_ticket"]["ledger"])
        self.assertIsNone(g["cost_per_ticket"]["cached"])
        self.assertEqual(g["footnotes"], ["list price, every input token uncached"])

    def test_prov_b(self):
        g = group(self.groups, "prov-b")
        self.assertEqual((g["tickets"], g["merged"], g["first_attempt"], g["reworks"], g["budget_stops"]),
                         (2, 1, 1, 0, 1))
        self.assertEqual(g["nogos"], {})
        self.assertEqual(g["tokens_per_ticket"], {"value": 3750, "over": 2})
        self.assertEqual(g["cost_per_ticket"]["ledger"], {"usd": 2.0, "bound": "exactly"})
        self.assertEqual(g["cost_per_ticket"]["list"], {"usd": 5.0, "bound": "at most"})
        self.assertIsNone(g["cost_per_ticket"]["cached"])
        joined = " ".join(g["footnotes"])
        self.assertIn("the ledger misses the budget-stopped runs", joined)
        self.assertIn("list price over every run", joined)

    def test_not_run_is_kept_with_its_reason(self):
        self.assertEqual([(n["provider"], n["harness"], n["why"]) for n in self.not_run], [("prov-c", "h-c", "no key")])

    def test_rows_from_complete_rows_when_no_total(self):
        data = copy.deepcopy(DATASET)
        data["totals"] = []
        for r, c in zip(data["rows"], (0.25, 0.75, 1.0, 2.0)):
            r["cost_usd"]["ledger"] = c
        data["rows"][3]["cost_usd"]["list"] = 9.0
        rows, totals, _, _ = scoreboard.load_dataset(data)
        groups = scoreboard.board(rows, totals)
        self.assertEqual(group(groups, "prov-a")["cost_per_ticket"]["ledger"], {"usd": 0.5, "bound": "exactly"})
        self.assertEqual(group(groups, "prov-b")["cost_per_ticket"]["ledger"], {"usd": 1.5, "bound": "exactly"})
        # one prov-b row has no list figure: not recorded, never filled in
        self.assertIsNone(group(groups, "prov-b")["cost_per_ticket"]["list"])

    def test_tokens_over_the_rows_that_carry_them(self):
        data = copy.deepcopy(DATASET)
        data["rows"][3]["tokens"] = {"input": None, "output": None, "cached": None}
        rows, totals, _, _ = scoreboard.load_dataset(data)
        self.assertEqual(group(scoreboard.board(rows, totals), "prov-b")["tokens_per_ticket"], {"value": 5500, "over": 1})

    def test_lines_name_every_group_and_the_provider_not_run(self):
        text = "\n".join(scoreboard.lines(self.groups, self.not_run, self.scope, 0))
        self.assertIn(self.scope, text)
        for word in ("prov-a", "prov-b", "prov-c", "not run", "no key", "mutation"):
            self.assertIn(word, text)

    def test_the_page(self):
        page = scoreboard.page(self.groups, self.not_run, self.scope, self.rows, 0, "the-dataset.json")
        for s in (DATASET["scope"], "not a benchmark", "not run", "no key",
                  "the ledger misses the budget-stopped runs", "3/4 (0.750 &lt; 0.800)", "TOKEN_BUDGET"):
            self.assertIn(s, page)
        for r in DATASET["rows"]:
            self.assertIn(r["source"]["handoff"], page)
            self.assertIn(r["source"]["run"], page)
        self.assertNotIn("<script", page.lower())
        self.assertNotRegex(page, r'(src|href)="https?:')
        self.assertIn("prefers-color-scheme: dark", page)


class Refusals(unittest.TestCase):
    """§2, §5: each refusal is one reason, naming what it refuses."""

    def refused(self, data, *words):
        with self.assertRaises(scoreboard.Refused) as cm:
            scoreboard.load_dataset(data)
        for w in words:
            self.assertIn(w, str(cm.exception))

    def test_a_row_with_an_empty_handoff(self):
        data = copy.deepcopy(DATASET)
        data["rows"][1]["source"]["handoff"] = ""
        self.refused(data, "t-2", "prov-a")

    def test_a_row_with_no_run(self):
        data = copy.deepcopy(DATASET)
        del data["rows"][2]["source"]["run"]
        self.refused(data, "t-3", "prov-b")

    def test_a_total_for_a_group_with_no_rows(self):
        data = copy.deepcopy(DATASET)
        data["totals"].append(dict(data["totals"][0], provider="prov-z"))
        self.refused(data, "prov-z")

    def test_a_provider_both_run_and_not_run(self):
        data = copy.deepcopy(DATASET)
        data["not_run"].append({"provider": "prov-a", "harness": "h-a", "why": "x", "source": "y"})
        self.refused(data, "prov-a")

    def test_no_scope(self):
        data = copy.deepcopy(DATASET)
        del data["scope"]
        self.refused(data, "scope")

    def test_an_unknown_schema(self):
        data = copy.deepcopy(DATASET)
        data["schema"] = "lights-out/scoreboard-data/9"
        self.refused(data, "schema")


def task(attempt, tokens, replayed=False):
    return {"attempt": attempt, "role": "dev-worker", "harness": "h", "provider": "p", "model": "m",
            "replayed": replayed, "tokens": {"input": tokens[0], "output": tokens[1], "total": sum(tokens)}}


LOGBOOK = {
    "schema": "lights-out/logbook/1.5",
    "source": {"commit": "c0ffee1234"},
    "tickets": [
        {"id": "L1", "attempt": 2, "tasks": [task(1, (100, 10)), task(2, (200, 21))],
         "rework": [{"attempt": 1, "line": "NO-GO: gates — mutation: NO-GO: mutation — 1/2 killed (0.500 < 0.769)"}],
         "ci": {"line": "GO: gates"}, "merge": {"sha": "m1"},
         "outcome": {"verdict": "GO", "judge": "human", "line": "promoted"}},
        {"id": "L2", "attempt": 1, "tasks": [task(1, (40, 4), replayed=True)], "rework": [], "ci": None, "merge": None,
         "outcome": {"verdict": "pending", "judge": None, "line": None}},
        {"id": "L3", "attempt": 3, "tasks": [task(1, (50, 5))],
         "rework": [{"attempt": 1, "line": "NO-GO: test — 2 failed"}, {"attempt": 2, "line": "CHANGES-REQUESTED — reviewer"}],
         "ci": {"line": "CHANGES-REQUESTED — reviewer"}, "merge": None,
         "outcome": {"verdict": "needs-human", "judge": "review", "stop": "budget",
                     "line": "SPEND_BUDGET_TICKET_USD=$1.00 reached"}},
        {"id": "L4", "attempt": None, "tasks": [], "rework": [], "ci": None, "merge": None,
         "outcome": {"verdict": "pending", "judge": None, "line": None}},
    ],
    "spend": {"tickets": {"L1": {"cost_usd": 0.5}, "L2": {"cost_usd": 0}, "L3": {"cost_usd": 0.3}}},
}


class FromLogbook(unittest.TestCase):
    """§3, §4: rows from a run logbook."""

    def setUp(self):
        self.rows, self.replayed = scoreboard.from_logbook(copy.deepcopy(LOGBOOK), "book.json")
        self.by = {r["ticket"]: r for r in self.rows}

    def test_which_tickets_are_rows(self):
        self.assertEqual(sorted(self.by), ["L1", "L3"])
        self.assertEqual(self.replayed, 1)

    def test_l1(self):
        r = self.by["L1"]
        self.assertEqual((r["provider"], r["harness"], r["model"]), ("p", "h", "m"))
        self.assertEqual((r["merged"], r["attempts"], r["reworks"]), (True, 2, 1))
        self.assertEqual(r["nogos"], [{"gate": "mutation", "reason": "1/2 killed (0.500 < 0.769)"}])
        self.assertIsNone(r["stop"])
        self.assertEqual(r["tokens"], {"input": 300, "output": 31, "cached": None})
        self.assertEqual(r["cost_usd"], {"ledger": 0.5, "list": None, "cached": None})
        self.assertEqual(r["source"], {"handoff": "logbook book.json", "run": "c0ffee1234 tickets/L1"})

    def test_l3(self):
        r = self.by["L3"]
        self.assertEqual((r["merged"], r["reworks"]), (False, 2))
        self.assertEqual(r["nogos"], [{"gate": "test", "reason": "2 failed"}])
        self.assertEqual(r["stop"], {"kind": "SPEND_BUDGET", "line": "SPEND_BUDGET_TICKET_USD=$1.00 reached"})
        self.assertEqual(r["tokens"], {"input": 50, "output": 5, "cached": None})
        self.assertEqual(r["cost_usd"]["ledger"], 0.3)

    def test_the_cap_is_a_stop_but_not_a_budget_stop(self):
        book = copy.deepcopy(LOGBOOK)
        book["tickets"][2]["outcome"]["stop"] = "cap"
        rows, _ = scoreboard.from_logbook(book, "book.json")
        r = [x for x in rows if x["ticket"] == "L3"][0]
        self.assertEqual(r["stop"]["kind"], "REWORK_CAP")
        self.assertEqual(scoreboard.board(rows, [])[0]["budget_stops"], 0)

    def test_the_last_ci_line_counts_when_not_merged(self):
        book = copy.deepcopy(LOGBOOK)
        book["tickets"][2]["ci"] = {"line": "NO-GO: gates — sast: NO-GO: sast — 1 new finding"}
        rows, _ = scoreboard.from_logbook(book, "book.json")
        r = [x for x in rows if x["ticket"] == "L3"][0]
        self.assertEqual(r["nogos"], [{"gate": "test", "reason": "2 failed"}, {"gate": "sast", "reason": "1 new finding"}])

    def test_an_unparsed_line_is_kept_whole(self):
        self.assertEqual(scoreboard.parse_nogo("NO-GO: something odd"), {"gate": "unparsed", "reason": "NO-GO: something odd"})

    def test_a_network_attempt(self):
        book = copy.deepcopy(LOGBOOK)
        book["tickets"][0]["tasks"] = [{"attempt": 1, "harness": "network", "provider": None, "model": None,
                                        "replayed": False, "tokens": None, "members": [
                                            dict(task(1, (10, 1)), provider="q", model="n"), task(1, (20, 2))]}]
        rows, _ = scoreboard.from_logbook(book, "book.json")
        r = [x for x in rows if x["ticket"] == "L1"][0]
        self.assertEqual((r["provider"], r["harness"], r["model"]), ("p+q", "network", "m+n"))
        self.assertEqual(r["tokens"], {"input": 30, "output": 3, "cached": None})

    def test_the_group(self):
        g = scoreboard.board(self.rows, [])
        self.assertEqual(len(g), 1)
        g = g[0]
        self.assertEqual((g["tickets"], g["merged"], g["first_attempt"], g["reworks"], g["budget_stops"]),
                         (2, 1, 0, 3, 1))
        self.assertEqual(g["nogos"], {"mutation": ["1/2 killed (0.500 < 0.769)"], "test": ["2 failed"]})
        self.assertEqual(g["tokens_per_ticket"], {"value": 193, "over": 2})
        self.assertEqual(g["cost_per_ticket"]["ledger"], {"usd": 0.4, "bound": "exactly"})
        self.assertIsNone(g["cost_per_ticket"]["list"])


class Committed(unittest.TestCase):
    """§9: the M24 dataset loads and says what the handoffs say."""

    def setUp(self):
        with open(M24, encoding="utf-8") as f:
            self.rows, self.totals, self.not_run, self.scope = scoreboard.load_dataset(json.load(f))
        self.groups = scoreboard.board(self.rows, self.totals)

    def test_anthropic(self):
        g = group(self.groups, "anthropic")
        # The model id is the dataset's to name, not core/'s (docs/adr/0040 §5).
        self.assertEqual(g["harness"], "claude-code")
        self.assertTrue(g["model"])
        self.assertEqual((g["tickets"], g["merged"], g["first_attempt"], g["reworks"], g["budget_stops"]),
                         (10, 10, 8, 2, 0))
        self.assertEqual(list(g["nogos"]), ["mutation"])
        self.assertEqual(len(g["nogos"]["mutation"]), 2)

    def test_gemini(self):
        g = group(self.groups, "gemini")
        self.assertEqual(g["harness"], "gemini-cli")
        self.assertTrue(g["model"])
        self.assertEqual((g["tickets"], g["merged"], g["first_attempt"], g["reworks"], g["budget_stops"]),
                         (10, 7, 7, 0, 3))
        self.assertEqual(sorted(r["ticket"] for r in self.rows if r["provider"] == "gemini" and r["stop"]),
                         ["tenacity-04", "tenacity-09", "tenacity-10"])
        self.assertTrue(all(r["stop"]["kind"] == "TOKEN_BUDGET" for r in self.rows if r["stop"]))
        self.assertTrue(g["footnotes"])

    def test_openai_not_run(self):
        self.assertEqual([n["provider"] for n in self.not_run], ["openai"])
        self.assertNotIn("openai", [r["provider"] for r in self.rows])


class Command(unittest.TestCase):
    """§7: core/scoreboard.sh keeps the gate contract."""

    def run_sh(self, **env):
        full = dict(os.environ, **env)
        return subprocess.run(["sh", "core/scoreboard.sh"], cwd=REPO, env=full, capture_output=True, text=True,
                              timeout=60, check=False)

    def test_go_on_the_adr_dataset(self):
        with tempfile.TemporaryDirectory() as d:
            data = os.path.join(d, "data.json")
            out = os.path.join(d, "out", "index.html")
            with open(data, "w", encoding="utf-8") as f:
                json.dump(DATASET, f)
            p = self.run_sh(SCOREBOARD_DATA=data, SCOREBOARD_OUT=out, SCOREBOARD_LOGBOOKS="")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout, f"GO: scoreboard — 2 groups run, 1 not run, 4 tickets; {out}\n")
            self.assertTrue(os.path.isfile(out))
            self.assertIn("prov-c", p.stderr)

    def test_a_logbook_adds_its_rows(self):
        with tempfile.TemporaryDirectory() as d:
            data, book, out = (os.path.join(d, n) for n in ("data.json", "book.json", "index.html"))
            with open(data, "w", encoding="utf-8") as f:
                json.dump(DATASET, f)
            with open(book, "w", encoding="utf-8") as f:
                json.dump(LOGBOOK, f)
            p = self.run_sh(SCOREBOARD_DATA=data, SCOREBOARD_OUT=out, SCOREBOARD_LOGBOOKS=book)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout, f"GO: scoreboard — 3 groups run, 1 not run, 6 tickets; {out}\n")
            self.assertIn("1 replayed", p.stderr)

    def test_no_go_on_a_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.run_sh(SCOREBOARD_DATA=os.path.join(d, "absent.json"), SCOREBOARD_OUT=os.path.join(d, "o.html"))
            self.assertEqual(p.returncode, 1)
            self.assertEqual(len(p.stdout.splitlines()), 1)
            self.assertTrue(p.stdout.startswith("NO-GO: scoreboard — "), p.stdout)
            self.assertIn("absent.json", p.stdout)

    def test_no_go_on_a_refused_row(self):
        with tempfile.TemporaryDirectory() as d:
            data = copy.deepcopy(DATASET)
            data["rows"][0]["source"]["run"] = ""
            path = os.path.join(d, "data.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            p = self.run_sh(SCOREBOARD_DATA=path, SCOREBOARD_OUT=os.path.join(d, "o.html"))
            self.assertEqual(p.returncode, 1)
            self.assertEqual(len(p.stdout.splitlines()), 1)
            self.assertIn("t-1", p.stdout)


if __name__ == "__main__":
    unittest.main()
