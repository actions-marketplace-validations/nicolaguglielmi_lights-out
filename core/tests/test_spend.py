"""Tests for the cost and the budget, written from docs/adr/0083, never from
the implementation: the ADR's price table, report fixture and budget cases.
"""

import contextlib
import io
import json
import os
import re
import subprocess  # nosec B404 - the scripts under test
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import spend, tower

REPO = Path(__file__).resolve().parents[2]

PRICES = {"prices": [
    {"provider": "prov", "model": "model-a", "input": 1.00, "output": 5.00,
     "source": "https://example.invalid/a", "checked": "2026-11-12"},
    {"provider": "prov", "model": "model-b", "input": 0.75, "output": 3.75, "until": "2026-12-31",
     "source": "https://example.invalid/b", "checked": "2026-11-12"},
    {"provider": "prov", "model": "model-b", "input": 1.50, "output": 7.50, "from": "2027-01-01",
     "source": "https://example.invalid/b", "checked": "2026-11-12"},
]}


def run(model, tin=None, tout=None, **more):
    out = {"harness": "h", "provider": "prov", "model": model, "replayed": False}
    if tin is not None or tout is not None:
        out["tokens"] = {"input": tin, "output": tout, "total": (tin or 0) + (tout or 0)}
    out.update(more)
    return out


class Cost(unittest.TestCase):
    """§1-§2."""

    def setUp(self):
        self.prices = spend.parse_prices(PRICES)

    def cost(self, r, day="2026-11-12"):
        return spend.cost(r, self.prices, day)

    def test_input_and_output_at_the_price(self):
        self.assertEqual(self.cost(run("model-a", 2_000_000, 100_000)), (2.5, None))

    def test_the_period_of_the_day(self):
        self.assertEqual(self.cost(run("model-b", 1_000_000, 1_000_000), "2026-12-31"), (4.5, None))
        self.assertEqual(self.cost(run("model-b", 1_000_000, 1_000_000), "2027-01-01"), (9.0, None))

    def test_a_replayed_run_costs_nothing(self):
        self.assertEqual(self.cost(run("model-z", 5, 5, replayed=True)), (0, None))

    def test_no_price_is_unknown_naming_the_model(self):
        usd, why = self.cost(run("model-z", 100, 10))
        self.assertIsNone(usd)
        self.assertIn("prov/model-z", why)

    def test_no_tokens_is_unknown(self):
        usd, why = self.cost(run("model-a"))
        self.assertIsNone(usd)
        self.assertTrue(why)

    def test_a_network_is_the_sum_of_its_members(self):
        net = {"harness": "network", "model": "model-a", "replayed": False,
               "members": [run("model-a", 1_000_000, 0), run("model-a", 0, 100_000)]}
        self.assertEqual(self.cost(net), (1.5, None))
        net["members"].append(run("model-z", 1, 1))
        usd, why = self.cost(net)
        self.assertIsNone(usd)
        self.assertIn("model-z", why)


class CommittedTable(unittest.TestCase):
    """§1: every committed price has its source and the day it was read."""

    def test_every_entry_is_complete_and_no_periods_overlap(self):
        with open(REPO / "profiles" / "prices.json", encoding="utf-8") as fh:
            table = json.load(fh)
        entries = table["prices"]
        self.assertTrue(entries)
        for e in entries:
            for key in ("provider", "model", "input", "output", "source", "checked"):
                self.assertIn(key, e)
            self.assertGreaterEqual(e["input"], 0)
            self.assertGreaterEqual(e["output"], 0)
            self.assertTrue(e["source"].startswith("https://"), e["source"])
            self.assertRegex(e["checked"], r"^\d{4}-\d{2}-\d{2}$")
        spend.parse_prices(table)  # the reader accepts it
        by_model = {}
        for e in entries:
            by_model.setdefault((e["provider"], e["model"]), []).append((e.get("from") or "0000-00-00",
                                                                         e.get("until") or "9999-99-99"))
        for periods in by_model.values():
            periods.sort()
            for (_, end), (start, _) in zip(periods, periods[1:]):
                self.assertLess(end, start)


def entry(step, role, model, tin, tout, secs, at, attempt=1, replayed=False, prices=None):
    prices = prices or spend.parse_prices(PRICES)
    r = run(model, tin, tout, replayed=replayed, duration_s=secs, role=role)
    usd, why = spend.cost(r, prices, at[:10])
    return {"step": step, "attempt": attempt, "role": role, "harness": "h", "provider": "prov", "model": model,
            "replayed": replayed, "tokens": r.get("tokens"), "duration_s": secs, "cost_usd": usd,
            "cost_unknown": why, "at": at}


def h(*ats):
    return [{"step": "x", "state": "y", "at": at} for at in ats]


DOCS = {
    "0201": {"id": "0201", "history": h("2026-11-10T09:00:00Z", "2026-11-11T10:00:00Z"), "spend": [
        entry("assign", "dev-worker", "model-a", 2_000_000, 100_000, 300, "2026-11-10T10:00:00Z"),
        entry("review", "test-reviewer", "model-a", 400_000, 20_000, 60, "2026-11-10T10:10:00Z"),
        entry("rework", "dev-worker", "model-a", 1_000_000, 40_000, 200, "2026-11-11T09:00:00Z", attempt=2),
    ]},
    "0202": {"id": "0202", "history": h("2026-11-11T11:00:00Z", "2026-11-11T12:30:00Z"), "spend": [
        entry("assign", "dev-worker", "model-z", 100, 10, 50, "2026-11-11T12:00:00Z"),
        entry("review", "test-reviewer", "model-a", 10, 10, 5, "2026-11-11T12:05:00Z", replayed=True),
    ]},
}


class Report(unittest.TestCase):
    """§5 and the ADR's two documents, by hand."""

    def setUp(self):
        self.got = spend.report(DOCS)

    def check(self, row, usd, runs, unknown, **more):
        self.assertAlmostEqual(row["cost_usd"], usd)
        self.assertEqual((row["runs"], row["unknown"]), (runs, unknown))
        for key, value in more.items():
            self.assertEqual(row[key], value, key)

    def test_per_ticket(self):
        self.check(self.got["tickets"]["0201"], 4.20, 3, 0, agent_s=560, elapsed_s=90000)
        self.check(self.got["tickets"]["0202"], 0.0, 2, 1, agent_s=50, elapsed_s=5400)

    def test_per_role(self):
        self.check(self.got["roles"]["dev-worker"], 3.70, 3, 1, agent_s=550)
        self.check(self.got["roles"]["test-reviewer"], 0.50, 2, 0, agent_s=60)

    def test_per_day(self):
        self.check(self.got["days"]["2026-11-10"], 3.00, 2, 0)
        self.check(self.got["days"]["2026-11-11"], 1.20, 3, 1)

    def test_in_all(self):
        self.check(self.got["total"], 4.20, 5, 1)


class Budget(unittest.TestCase):
    """§4: at or over a limit, or any unknown cost under one, stops."""

    def limits(self, ticket="", day=""):
        return spend.parse_limits(f"SPEND_BUDGET_TICKET_USD={ticket}\nSPEND_BUDGET_DAY_USD={day}\n")

    def test_the_ticket_limit(self):
        mine = DOCS["0201"]["spend"]
        line = spend.stop(mine, [], self.limits(ticket="4.20"))
        self.assertIn("SPEND_BUDGET_TICKET_USD", line)
        self.assertEqual(spend.stop(mine, [], self.limits(ticket="4.21")), "")

    def test_the_day_limit_counts_only_the_day(self):
        docs = {"0201": DOCS["0201"]}
        today = spend.on_day(docs, "2026-11-11")
        self.assertEqual(len(today), 1)
        self.assertIn("SPEND_BUDGET_DAY_USD", spend.stop([], today, self.limits(day="1.20")))
        self.assertEqual(spend.stop([], today, self.limits(day="1.21")), "")

    def test_an_unknown_cost_stops_either_limit(self):
        mine = DOCS["0202"]["spend"]
        today = spend.on_day(DOCS, "2026-11-11")
        self.assertIn("unknown", spend.stop(mine, [], self.limits(ticket="100")))
        self.assertIn("unknown", spend.stop([], today, self.limits(day="100")))

    def test_empty_limits_never_stop(self):
        self.assertEqual(spend.stop(DOCS["0202"]["spend"], spend.on_day(DOCS, "2026-11-11"), self.limits()), "")

    def test_a_malformed_limit_is_refused_by_name(self):
        for bad in ("x", "0", "-1"):
            with self.assertRaises(ValueError) as caught:
                self.limits(day=bad)
            self.assertIn("SPEND_BUDGET_DAY_USD", str(caught.exception))


STUBS = {
    "adapters/stub-state/get.sh": 'f="state/$1.$2.json"\n[ -f "$f" ] || exit 1\ncat "$f"\n',
    "adapters/stub-state/put.sh": 'cat > "state/$1.$2.json"\n',
    "adapters/stub-bus/publish.sh": 'printf \'%s\\n\' "$1" >> bus.log\n',
}
ENV = {"STATE_STORE": "stub-state", "EVENT_BUS": "stub-bus", "TOWER_STEPS": "steps"}


class Tower(unittest.TestCase):
    """§3 and §4, through core/tower.py in a temp root."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for path, body in STUBS.items():
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text("set -eu\n" + body)
        for d in ("state", "steps", "profiles", "policy", "tickets"):
            (self.root / d).mkdir()
        (self.root / "profiles" / "prices.json").write_text(json.dumps(PRICES))
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def tower(self, *argv):
        with contextlib.redirect_stderr(io.StringIO()):
            return tower.main(list(argv), dict(ENV))

    def put(self, doc):
        (self.root / "tickets" / f"{doc['id']}.md").write_text(f"# {doc['id']}\n")
        (self.root / "state" / f"tickets.{doc['id']}.json").write_text(json.dumps(doc))

    def doc(self, tid="0001"):
        return json.loads((self.root / "state" / f"tickets.{tid}.json").read_text())

    def policy(self, ticket="", day=""):
        (self.root / "policy" / "rework.env").write_text(
            f"REWORK_MAX_ATTEMPTS=4\nSPEND_BUDGET_TICKET_USD={ticket}\nSPEND_BUDGET_DAY_USD={day}\n")

    def step(self, name, result):
        (self.root / "steps" / f"{name}.sh").write_text(
            'printf "%s" "${SPEND_STOP:-}" > stop.txt\n' f"echo '{json.dumps(result)}'\n")

    def today_at(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_a_step_with_three_runs_appends_three_entries_with_the_cost(self):
        self.put({"id": "0001", "state": "opened", "history": []})
        self.step("assign", {"state": "pr-opened", "attempt": 1,
                             "task": run("model-a", 2_000_000, 100_000, role="dev-worker"),
                             "review": run("model-a", 400_000, 20_000, role="test-reviewer"),
                             "product": dict(run("model-a", 1_000_000, 0), consulted=True)})
        self.assertEqual(self.tower("step", "0001", "assign"), 0)
        got = self.doc()["spend"]
        self.assertEqual([e["role"] for e in got], ["dev-worker", "test-reviewer", "product"])
        self.assertEqual([e["cost_usd"] for e in got], [2.5, 0.5, 1.0])
        self.assertEqual(got[0]["tokens"], {"input": 2_000_000, "output": 100_000, "total": 2_100_000})
        self.assertEqual((got[0]["step"], got[0]["attempt"], got[0]["model"]), ("assign", 1, "model-a"))
        self.assertRegex(got[0]["at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertIsNone(got[0]["cost_unknown"])

    def test_an_unpriced_run_is_recorded_with_its_reason(self):
        self.put({"id": "0001", "state": "opened", "history": []})
        self.step("assign", {"state": "pr-opened", "attempt": 1, "task": run("model-z", 1, 1, role="dev-worker")})
        self.tower("step", "0001", "assign")
        got = self.doc()["spend"][0]
        self.assertIsNone(got["cost_usd"])
        self.assertIn("model-z", got["cost_unknown"])

    def test_no_run_and_an_unconsulted_product_append_nothing(self):
        self.put({"id": "0001", "state": "requested", "history": []})
        self.step("clarify", {"state": "spec-ready", "product": dict(run("model-a", 1, 1), consulted=False)})
        self.tower("step", "0001", "clarify")
        self.assertFalse(self.doc().get("spend"))

    def test_rework_over_the_ticket_limit_gets_the_line(self):
        self.policy(ticket="1.00")
        self.put({"id": "0001", "state": "ci-failed", "attempt": 1, "history": [],
                  "spend": [entry("assign", "dev-worker", "model-a", 2_000_000, 100_000, 1, self.today_at())]})
        self.step("rework", {"state": "needs-human"})
        self.tower("step", "0001", "rework")
        self.assertIn("SPEND_BUDGET_TICKET_USD", (self.root / "stop.txt").read_text())

    def test_rework_under_the_limit_gets_no_line(self):
        self.policy(ticket="3.00")
        self.put({"id": "0001", "state": "ci-failed", "attempt": 1, "history": [],
                  "spend": [entry("assign", "dev-worker", "model-a", 2_000_000, 100_000, 1, self.today_at())]})
        self.step("rework", {"state": "pr-opened", "attempt": 2})
        self.tower("step", "0001", "rework")
        self.assertEqual((self.root / "stop.txt").read_text(), "")

    def test_assign_over_the_day_limit_stays_opened(self):
        self.policy(day="2.00")
        self.put({"id": "0002", "state": "held", "history": [],
                  "spend": [entry("assign", "dev-worker", "model-a", 2_000_000, 100_000, 1, self.today_at())]})
        self.put({"id": "0001", "state": "opened", "history": []})
        self.step("assign", {"state": "pr-opened", "attempt": 1})
        self.assertEqual(self.tower("step", "0001", "assign"), 1)
        doc = self.doc()
        self.assertEqual(doc["state"], "opened")
        self.assertIn("SPEND_BUDGET_DAY_USD", doc["history"][-1]["error"])
        self.assertFalse((self.root / "stop.txt").exists(), "the step ran")
        self.assertFalse((self.root / "bus.log").exists(), "something was published")

    def test_yesterday_does_not_count_for_the_day(self):
        self.policy(day="2.00")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.put({"id": "0002", "state": "held", "history": [],
                  "spend": [entry("assign", "dev-worker", "model-a", 2_000_000, 100_000, 1, yesterday)]})
        self.put({"id": "0001", "state": "opened", "history": []})
        self.step("assign", {"state": "pr-opened", "attempt": 1})
        self.assertEqual(self.tower("step", "0001", "assign"), 0)
        self.assertEqual(self.doc()["state"], "pr-opened")


class ReworkStep(unittest.TestCase):
    """§4: core/steps/rework.sh with SPEND_STOP records the attempt and stops."""

    def test_needs_human_with_the_budget_line_and_no_crew(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "doc.json"
            doc.write_text(json.dumps({"id": "9999", "state": "ci-failed", "attempt": 1,
                                       "pr": {"head_sha": "a" * 40},
                                       "ci": {"verdict": "NO-GO", "line": "NO-GO: test — 1 failed", "details": []}}))
            line = "spend budget: ticket 9999 spent $5.00, SPEND_BUDGET_TICKET_USD=4.00"
            env = dict(os.environ, TICKET="9999", DOC_FILE=str(doc), SPEND_STOP=line, ROLE="dev-worker")
            ran = subprocess.run(["sh", "core/steps/rework.sh"], cwd=REPO, env=env, capture_output=True,
                                 text=True, check=False)  # nosec B603 B607 - a fixed argv
            self.assertEqual(ran.returncode, 0, ran.stderr)
            out = json.loads(ran.stdout)
            self.assertEqual(out["state"], "needs-human")
            self.assertEqual(out["budget"]["line"], line)
            self.assertEqual([r["line"] for r in out["rework"]], ["NO-GO: test — 1 failed"])
            self.assertFalse((REPO / ".crew" / "9999").exists(), "a crew ran")


class Command(unittest.TestCase):
    """§5: core/spend.sh keeps the gate contract."""

    def run_cmd(self, env):
        return subprocess.run(["sh", "core/spend.sh"], cwd=REPO, env=env, capture_output=True, text=True,
                              check=False)  # nosec B603 B607 - a fixed argv

    def test_no_ticket_is_one_go_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            ran = self.run_cmd(dict(os.environ, STATE_STORE="sqlite", TICKETS_DIR=tmp))
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(len(ran.stdout.splitlines()), 1, ran.stdout)
        self.assertTrue(re.match(r"^GO: spend — 0 tickets", ran.stdout), ran.stdout)

    def test_no_state_store_is_one_no_go_line(self):
        env = dict(os.environ)
        env.pop("STATE_STORE", None)
        ran = self.run_cmd(env)
        self.assertEqual(ran.returncode, 1)
        self.assertEqual(len(ran.stdout.splitlines()), 1, ran.stdout)
        self.assertTrue(ran.stdout.startswith("NO-GO: spend — "), ran.stdout)


if __name__ == "__main__":
    unittest.main()
