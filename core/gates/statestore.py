# SPDX-License-Identifier: Apache-2.0
"""gates/statestore-conformance.sh's suite: the StateStore port (docs/adr/0060
§4; the contract is docs/adr/0019 §2). Written from the ADRs, never from an
adapter.

    python3 -m core.gates.statestore

It drives whichever STATE_STORE is set, only through `sh
adapters/$STATE_STORE/{get,put,delete}.sh <collection> <id>`, documents on
stdin, never as arguments. Eight cases, in this order, the first
disagreement a NO-GO naming the case:
  1 get of an absent document exits 1 with nothing on stdout
  2 a document holding every JSON type round-trips, equal as a JSON value
  3 put replaces the whole document: no merge
  4 one id in two collections is two documents
  5 put of non-JSON and of a JSON array exits non-zero and leaves the stored
    document unchanged
  6 a 65,536-letter ASCII string round-trips (ADR 0060 §4: above any tower
    document seen, below the 128 KiB Linux allows one argument)
  7 delete, then get exits 1; the other collection's document is still there
  8 delete of an absent document exits 0
Documents are compared as JSON values, every value the verb printed against
the one that was put: pretty or compact, keys in any order, but printed
once. The ids are the tower's: 0001, main and a 40-hex one. It writes only
collections conformance-<run id> and conformance-<run id>-b, and deletes
every document it may have written on any exit, ignoring errors.
"""

import json
import os
import secrets

from . import NoGo, adapter, main, run_id, say

TYPES = {
    "string": "quote \" backslash \\ newline \n tab \t u-umlaut é ü 日本語 😀",
    "empty_string": "",
    "integer": 42,
    "negative": -7,
    "non_integer": 1.5,
    "yes": True,
    "no": False,
    "nothing": None,
    "array": [1, "two", {"three": [3, {"four": None}]}, None, False, 2.5],
    "object": {"nested": {"deeper": ["x", {"y": [True]}]}, "empty_array": [], "empty_object": {}},
    "empty_array": [],
    "empty_object": {},
}
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BIG = {"big": "".join(LETTERS[i % len(LETTERS)] for i in range(65536))}


def values(text):
    """Every JSON value in TEXT, in order, or None when TEXT is not JSON."""
    found, i, decoder = [], 0, json.JSONDecoder()
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i == len(text):
            return found
        try:
            value, i = decoder.raw_decode(text, i)
        except ValueError:
            return None
        found.append(value)


def same(doc, text):
    """TEXT holds DOC, once, as a JSON value."""
    return values(text) == [doc]


def snip(text):
    return text.encode("utf-8")[:200].decode("utf-8", "ignore").replace("\n", " ")


class Suite:
    def __init__(self, store, verb):
        self.store, self.verb = store, verb
        rid = run_id()
        self.col, self.colb = f"conformance-{rid}", f"conformance-{rid}-b"
        self.sha = secrets.token_hex(20)
        self.rc, self.out = 0, ""
        say(f"[statestore-conformance] run {rid} on STATE_STORE={store}, collections {self.col} and {self.colb}")

    def call(self, name, collection, doc_id, data=None):
        """The verb's exit code; its stdout in self.out, its stderr relayed."""
        self.rc, self.out, err = self.verb(name, collection, doc_id, data=data)
        for line in err.splitlines():
            say(f"  [{name}] {line}")
        return self.rc

    def put(self, collection, doc_id, doc):
        text = doc if isinstance(doc, str) else json.dumps(doc, ensure_ascii=False)
        return self.call("put", collection, doc_id, data=(text + "\n").encode())

    def absent(self, collection, doc_id):
        return self.call("get", collection, doc_id) == 1 and self.out == ""

    def holds(self, collection, doc_id, doc):
        """get exits 0 and prints DOC; the exit code in self.rc."""
        return self.call("get", collection, doc_id) == 0 and same(doc, self.out)

    def cleanup(self):
        for doc_id in ("0001", "main", self.sha):
            self.verb("delete", self.col, doc_id)
        self.verb("delete", self.colb, "0001")

    def run(self):
        col, colb, sha = self.col, self.colb, self.sha
        if not self.absent(col, "0001"):
            raise NoGo(f"case1 absent: get of a document never written exited {self.rc} and printed "
                       f"[{snip(self.out)}], want exit 1 and nothing on stdout")
        say("[statestore-conformance] case 1 get of an absent document: GO")

        rc = self.put(col, "0001", TYPES)
        if rc:
            raise NoGo(f"case2 roundtrip: put exited {rc} on a document holding every JSON type")
        if not self.holds(col, "0001", TYPES):
            if self.rc:
                raise NoGo(f"case2 roundtrip: get exited {self.rc} right after the put")
            raise NoGo(f"case2 roundtrip: get printed [{snip(self.out)}], which is not, as a JSON value, "
                       "the document that was put")
        say("[statestore-conformance] case 2 every JSON type round-trips: GO")

        first, second = {"alpha": 1, "beta": {"x": 1}, "keep": "old"}, {"gamma": [2], "beta": "new"}
        for which, doc in (("first", first), ("second", second)):
            rc = self.put(col, "main", doc)
            if rc:
                raise NoGo(f"case3 replace: put exited {rc} on the {which} document")
        if not self.holds(col, "main", second):
            raise NoGo(f"case3 replace: after two puts get exited {self.rc} and printed [{snip(self.out)}], want "
                       "exactly the second document: put replaces, it does not merge")
        say("[statestore-conformance] case 3 put replaces: GO")

        doc_a, doc_b = {"where": "a"}, {"where": "b"}
        for c, doc in ((col, doc_a), (colb, doc_b)):
            rc = self.put(c, "0001", doc)
            if rc:
                raise NoGo(f"case4 collections: put exited {rc} in {c}")
        if not self.holds(col, "0001", doc_a):
            raise NoGo(f"case4 collections: {col}/0001 reads [{snip(self.out)}] after {colb}/0001 was written, "
                       "want its own document: the collection is ignored")
        if not self.holds(colb, "0001", doc_b):
            raise NoGo(f"case4 collections: {colb}/0001 reads [{snip(self.out)}], want its own document")
        say("[statestore-conformance] case 4 one id in two collections is two documents: GO")

        keep = {"keep": "me"}
        rc = self.put(col, sha, keep)
        if rc:
            raise NoGo(f"case5 refuse: put exited {rc} on a valid document")
        for text, what in (("this is not JSON {", "text that is not JSON"), ("[1,2,3]", "a JSON array")):
            if self.put(col, sha, text) == 0:
                raise NoGo(f"case5 refuse: put of {what} exited 0, want non-zero")
            if not self.holds(col, sha, keep):
                raise NoGo(f"case5 refuse: after the refused put of {what} get exited {self.rc} and printed "
                           f"[{snip(self.out)}], want the stored document unchanged")
        say("[statestore-conformance] case 5 non-JSON and an array are refused, the document unchanged: GO")

        rc = self.put(col, sha, BIG)
        if rc:
            raise NoGo(f"case6 large: put exited {rc} on a 65,536-character string")
        if not self.holds(col, sha, BIG):
            raise NoGo(f"case6 large: get exited {self.rc} and printed {len(self.out.encode())} bytes starting "
                       f"[{snip(self.out)}], want the 65,536-character string back")
        say("[statestore-conformance] case 6 a 65,536-letter string round-trips: GO")

        rc = self.call("delete", col, "0001")
        if rc:
            raise NoGo(f"case7 delete: delete of an existing document exited {rc}")
        if not self.absent(col, "0001"):
            raise NoGo(f"case7 delete: after delete, get exited {self.rc} and printed [{snip(self.out)}], "
                       "want exit 1 and nothing on stdout")
        if not self.holds(colb, "0001", doc_b):
            raise NoGo(f"case7 delete: deleting {col}/0001 left {colb}/0001 reading [{snip(self.out)}] "
                       f"(exit {self.rc}), want its own document")
        say("[statestore-conformance] case 7 delete: GO")

        for doc_id, what in (("0001", "a document deleted a moment ago"), ("never-written", "an id never written")):
            rc = self.call("delete", col, doc_id)
            if rc:
                raise NoGo(f"case8 delete-absent: delete of {what} exited {rc}, want 0")
        say("[statestore-conformance] case 8 delete of an absent document: GO")
        return f"{self.store}, 8 cases"


def judge(argv, env=None, verb=None):
    env = os.environ if env is None else env
    store = env.get("STATE_STORE", "")
    if not store:
        raise NoGo("STATE_STORE is not set; a profile sets it: run this via ./go statestore-conformance")
    if verb is None:
        for v in ("get", "put", "delete"):
            if not os.path.isfile(f"adapters/{store}/{v}.sh"):
                raise NoGo(f"adapters/{store}/{v}.sh is missing: a state store ships get, put and delete "
                           "(docs/adr/0019 §2)")
        verb = adapter(f"adapters/{store}")
    suite = Suite(store, verb)
    try:
        return suite.run()
    finally:
        suite.cleanup()


if __name__ == "__main__":
    raise SystemExit(main(judge))
