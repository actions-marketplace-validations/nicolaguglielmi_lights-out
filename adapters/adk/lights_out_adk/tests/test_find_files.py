# SPDX-License-Identifier: Apache-2.0
"""Tests for the architect's find_files (docs/adr/0090, Amendment
2026-11-14, A4), written from the ADR, never from the implementation: one
call takes at most 10 queries and answers each with at most 40 sorted
paths and how many more matched, in the order asked."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[4]


def tool():
    env = {"LIGHTS_OUT_ROOT": str(REPO), "AGENT_HARNESS": "replay", "MODEL_PROVIDER": "", "MODEL": ""}
    with mock.patch.dict(os.environ, env):
        from agents.architect import agent  # built at import, under the replay profile
    return agent.find_files


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
        db.executemany("INSERT INTO node (kind, name) VALUES (?, ?)", rows)
        db.commit()
        db.close()
        self.find = tool()

    def call(self, queries, with_map=True):
        env = {"INTAKE_MAP": str(self.map)} if with_map else {"INTAKE_MAP": str(self.dir / "absent.sqlite")}
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


if __name__ == "__main__":
    unittest.main()
