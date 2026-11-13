"""Tests for core/gates/statestore.py, written from docs/adr/0019 §2,
docs/adr/0060 §1, §4 and gates/statestore-conformance.sh's header, never
from the implementation.

A fair store gets GO with 8 cases; a store broken in one behaviour gets a
NO-GO naming the case that behaviour belongs to; every document the suite
wrote is deleted on its way out, GO or NO-GO.
"""

import contextlib
import io
import json
import unittest

from core.gates import NoGo, statestore


class FakeStore:
    """A StateStore in memory, honest unless BREAK names one behaviour."""

    def __init__(self, brk=None, pretty=False):
        self.docs = {}
        self.brk, self.pretty = brk, pretty

    def __call__(self, name, collection, doc_id, data=None):
        key = doc_id if self.brk == "no-collection" else (collection, doc_id)
        if name == "get":
            if key not in self.docs:
                return (0, "{}\n", "") if self.brk == "absent-is-empty" else (1, "", "")
            text = self.docs[key]
            if self.brk == "ascii":
                text = text.encode("ascii", "replace").decode()
            if self.brk == "twice":
                text = text + "\n" + text
            if self.pretty:
                text = json.dumps(json.loads(text), indent=2, sort_keys=True)
            return 0, text + "\n", "a note on stderr"
        if name == "put":
            try:
                doc = json.loads(data.decode())
            except ValueError:
                if self.brk == "refuse-clears":
                    self.docs.pop(key, None)
                return 1, "", "not JSON"
            if not isinstance(doc, dict) and self.brk != "accept-array":
                return 1, "", "not an object"
            if isinstance(doc, dict) and self.brk == "truncate":
                doc = {k: v[:65000] if isinstance(v, str) else v for k, v in doc.items()}
            if self.brk == "merge" and key in self.docs:
                doc = {**json.loads(self.docs[key]), **doc}
            self.docs[key] = json.dumps(doc, ensure_ascii=False)
            return 0, "", ""
        if name == "delete":
            if self.brk == "delete-nothing":
                return 0, "", ""
            if key not in self.docs and self.brk == "delete-absent-fails":
                return 1, "", "no such document"
            self.docs.pop(key, None)
            return 0, "", ""
        raise AssertionError(name)


class StateStoreTest(unittest.TestCase):
    def suite(self, store):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                got = ("GO", statestore.judge([], env={"STATE_STORE": "fake"}, verb=store))
            except NoGo as no:
                got = ("NO-GO", no.reason)
        self.err = err.getvalue()
        return got

    def test_a_fair_store_passes_and_is_left_empty(self):
        for pretty in (False, True):
            store = FakeStore(pretty=pretty)
            self.assertEqual(self.suite(store), ("GO", "fake, 8 cases"))
            self.assertEqual(store.docs, {})
        self.assertIn("case 8 delete of an absent document: GO", self.err)
        self.assertIn("  [get] a note on stderr", self.err)

    def test_each_break_names_its_case(self):
        for brk, case in (("absent-is-empty", "case1 absent"), ("ascii", "case2 roundtrip"),
                          ("twice", "case2 roundtrip"), ("merge", "case3 replace"),
                          ("no-collection", "case4 collections"), ("accept-array", "case5 refuse"),
                          ("refuse-clears", "case5 refuse"), ("truncate", "case6 large"),
                          ("delete-nothing", "case7 delete"), ("delete-absent-fails", "case8 delete-absent")):
            with self.subTest(brk=brk):
                store = FakeStore(brk)
                verdict, reason = self.suite(store)
                self.assertEqual(verdict, "NO-GO", reason)
                self.assertTrue(reason.startswith(case + ":"), reason)
                self.assertNotIn("\n", reason)
                if brk != "delete-nothing":
                    self.assertEqual(store.docs, {}, brk)

    def test_unset_store(self):
        with self.assertRaises(NoGo):
            statestore.judge([], env={})

    def test_values_reads_every_json_value(self):
        self.assertEqual(statestore.values(' {"a": 1}\n[2] 3 '), [{"a": 1}, [2], 3])
        self.assertIsNone(statestore.values('{"a": 1} trailing'))
        self.assertEqual(statestore.values(""), [])
        self.assertTrue(statestore.same({"a": 1.0, "b": [True]}, '{"b": [true], "a": 1}'))
        self.assertFalse(statestore.same({"a": 1}, '{"a": 1}{"a": 1}'))


if __name__ == "__main__":
    unittest.main()
