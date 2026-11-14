# SPDX-License-Identifier: Apache-2.0
"""Tests for the architect's find_files (docs/adr/0090, Amendment
2026-11-14, A4), written from the ADR, never from the implementation: one
call takes at most 10 queries and answers each with at most 40 sorted
paths and how many more matched, in the order asked. Amendment 2026-11-14
(second), A6 and A7: only paths under INTAKE_SCOPE (a directory; the path
itself or anything under scope + "/"; empty or unset = every path) are
answered, and the process answers at most SEARCHES_MAX = 2 calls, the third
and later with a budget error that tells the role to propose now."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[4]


BUDGET = {"error": "search budget of 2 used: propose now with propose_perimeter", "results": []}


def module():
    env = {"LIGHTS_OUT_ROOT": str(REPO), "AGENT_HARNESS": "replay", "MODEL_PROVIDER": "", "MODEL": ""}
    with mock.patch.dict(os.environ, env):
        from agents.architect import agent  # built at import, under the replay profile
    return agent


class FindFiles(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.map = self.dir / "map.sqlite"
        db = sqlite3.connect(self.map)
        db.execute("CREATE TABLE node (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,"
                   " title TEXT NOT NULL DEFAULT '', UNIQUE (kind, name))")
        rows = [("file", "api/orders.py"), ("file", "api/Seats.py"), ("test", "tests/test_orders.py"),
                ("page", "docs/orders.html"), ("adr", "docs/adr/0001-orders.md"),
                ("file", "api/other.py"), ("target", "orders-target"), ("symbol", "orders.cancel")]
        rows += [("file", f"bulk/item{i:03d}.py") for i in range(55)]
        # The harness's own paths beside a workload's, and siblings whose
        # names merely start with the scope's.
        rows += [("file", "api/backend/x.py"), ("file", "apis/y.py"), ("file", "apiary.py"),
                 ("file", "core/tower.py"), ("file", "roles/architect/perimeter.md"),
                 ("file", "fixtures/logbook/stub/x.json"), ("test", "core/tests/test_tower.py"),
                 ("page", "docs/architect.html"), ("adr", "docs/adr/0090-logbook-x.md")]
        db.executemany("INSERT INTO node (kind, name) VALUES (?, ?)", rows)
        db.commit()
        db.close()
        self.agent = module()
        self.find = self.agent.find_files
        # The budget is per process: each case starts with a fresh one.
        getattr(self.agent, "reset_searches", lambda: None)()

    def call(self, queries, with_map=True, scope=""):
        env = {"INTAKE_MAP": str(self.map) if with_map else str(self.dir / "absent.sqlite"), "INTAKE_SCOPE": scope}
        with mock.patch.dict(os.environ, env):
            return self.find(queries)

    def test_each_query_is_answered_in_the_order_asked(self):
        got = self.call(["seats", "orders"])
        self.assertEqual([r["query"] for r in got["results"]], ["seats", "orders"])

    def test_paths_contain_the_query_case_insensitively_and_sorted(self):
        got = self.call(["ORDERS", "seats"])
        self.assertEqual(got["results"][0]["paths"],
                         ["api/orders.py", "docs/adr/0001-orders.md", "docs/orders.html", "tests/test_orders.py"])
        self.assertEqual(got["results"][1]["paths"], ["api/Seats.py"])
        self.assertEqual(got["results"][0]["more"], 0)

    def test_only_files_tests_pages_and_adrs_are_searched(self):
        paths = self.call(["orders"])["results"][0]["paths"]
        self.assertNotIn("orders-target", paths)
        self.assertNotIn("orders.cancel", paths)

    def test_at_most_forty_paths_and_how_many_more(self):
        got = self.call(["bulk/"])["results"][0]
        self.assertEqual(len(got["paths"]), 40)
        self.assertEqual(got["paths"], sorted(got["paths"]))
        self.assertEqual(got["more"], 15)

    def test_a_query_nothing_matches_is_empty_not_an_error(self):
        got = self.call(["zzz"])
        self.assertEqual(got["results"], [{"query": "zzz", "paths": [], "more": 0}])

    def test_ten_queries_are_allowed(self):
        got = self.call([f"q{i}" for i in range(10)])
        self.assertNotIn("error", got)
        self.assertEqual(len(got["results"]), 10)

    def test_more_than_ten_queries_is_an_error_with_no_results(self):
        got = self.call([f"q{i}" for i in range(11)])
        self.assertIn("error", got)
        self.assertFalse(got.get("results"))

    def test_no_map_is_an_error(self):
        got = self.call(["seats"], with_map=False)
        self.assertIn("error", got)
        self.assertFalse(got.get("results"))

    # --- A6: the scope -----------------------------------------------------

    def test_a_scope_never_returns_a_path_outside_it(self):
        got = self.call(["tower", "architect", "logbook", "x"], scope="api")
        for r in got["results"]:
            for p in r["paths"]:
                self.assertTrue(p == "api" or p.startswith("api/"), f"{p} is outside the scope for {r['query']!r}")
        self.assertEqual(got["results"][3]["paths"], ["api/backend/x.py"])
        for r in got["results"][:3]:
            self.assertEqual(r["paths"], [])

    def test_a_scope_is_a_directory_not_a_prefix_of_a_name(self):
        got = self.call(["y.py", "apiary", "api"], scope="api")
        self.assertEqual(got["results"][0]["paths"], [])
        self.assertEqual(got["results"][1]["paths"], [])
        paths = got["results"][2]["paths"]
        self.assertNotIn("apis/y.py", paths)
        self.assertNotIn("apiary.py", paths)
        self.assertIn("api/orders.py", paths)

    def test_an_empty_scope_returns_every_path(self):
        got = self.call(["tower", "x.py"], scope="")
        self.assertEqual(got["results"][0]["paths"], ["core/tests/test_tower.py", "core/tower.py"])
        self.assertIn("api/backend/x.py", got["results"][1]["paths"])
        self.assertIn("apis/y.py", self.call(["y.py"])["results"][0]["paths"])

    def test_more_counts_what_the_scope_leaves(self):
        self.assertEqual(self.call(["bulk/"], scope="bulk")["results"][0]["more"], 15)
        self.assertEqual(self.call(["bulk/"], scope="api")["results"][0], {"query": "bulk/", "paths": [], "more": 0})

    # --- A7: the budget ----------------------------------------------------

    def test_the_budget_is_two_searches(self):
        self.assertEqual(self.agent.SEARCHES_MAX, 2)
        self.assertTrue(callable(getattr(self.agent, "reset_searches", None)))

    def test_the_first_two_calls_answer_and_the_third_is_the_budget_error(self):
        first, second = self.call(["orders"]), self.call(["seats"])
        self.assertNotIn("error", first)
        self.assertNotIn("error", second)
        self.assertEqual(self.call(["orders"]), BUDGET)
        self.assertEqual(self.call(["seats"]), BUDGET)

    def test_resetting_the_budget_answers_again(self):
        for _ in range(3):
            self.call(["orders"])
        getattr(self.agent, "reset_searches", lambda: None)()
        self.assertNotIn("error", self.call(["orders"]))


if __name__ == "__main__":
    unittest.main()
