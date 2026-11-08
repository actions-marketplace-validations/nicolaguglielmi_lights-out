#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The sqlite StateStore (docs/adr/0060 §1): standard library only.

    python3 -I store.py get <collection> <id>
    python3 -I store.py put <collection> <id> < document.json
    python3 -I store.py delete <collection> <id>
    python3 -I store.py ready

The verbs' .sh files call this; core/ calls the .sh files. One file,
STATE_FILE (default .crew/state.sqlite, relative to the working directory,
which ./go makes the repository root), one table keyed (collection, id)
holding each document as JSON text. The contract is docs/adr/0019 §2's,
unchanged: get prints the document as plain JSON and exits 0, exits 1 and
prints nothing when it is absent, exits 2 with one stderr line on any other
failure; put replaces the whole document with the JSON object on stdin,
exits 1 with one stderr line (the stored document untouched) when stdin is
not one; delete removes it, and an absent document is success. ready
creates the file and its table. The file lives under .crew/, so it outlives
./go down; no harness container mounts .crew/ (docs/adr/0041 §4).
"""

import json
import os
import sqlite3
import sys

# Seconds a verb waits on another process's lock before failing. A decision:
# the tower writes one small document at a time (docs/adr/0019 §2), so any
# wait near this long means a stuck process, not a busy one.
LOCK_TIMEOUT = 30


class Failed(Exception):
    """One line for stderr; the verb exits with its own failure code."""


def connect():
    path = os.environ.get("STATE_FILE") or ".crew/state.sqlite"
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        db = sqlite3.connect(path, timeout=LOCK_TIMEOUT, isolation_level=None)
        db.execute("CREATE TABLE IF NOT EXISTS documents ("
                   "collection TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, "
                   "PRIMARY KEY (collection, id))")
    except (OSError, sqlite3.Error) as e:
        raise Failed(f"cannot open {path}: {e}") from e
    return db


def _no_constant(name):
    raise ValueError(f"{name} is not JSON")


def document(raw):
    """The JSON object in raw, compact; Failed when raw is not one."""
    try:
        doc = json.loads(raw.decode("utf-8"), parse_constant=_no_constant)
    except (UnicodeDecodeError, ValueError) as e:
        raise Failed(f"stdin is not a JSON object: {e}") from e
    if not isinstance(doc, dict):
        raise Failed(f"stdin is not a JSON object: a {type(doc).__name__}")
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def get(collection, doc_id):
    try:
        row = connect().execute("SELECT body FROM documents WHERE collection = ? AND id = ?",
                                (collection, doc_id)).fetchone()
    except sqlite3.Error as e:
        raise Failed(f"reading {collection}/{doc_id}: {e}") from e
    if row is None:
        return 1
    sys.stdout.write(row[0] + "\n")
    return 0


def put(collection, doc_id):
    body = document(sys.stdin.buffer.read())
    try:
        connect().execute("INSERT OR REPLACE INTO documents (collection, id, body) VALUES (?, ?, ?)",
                          (collection, doc_id, body))
    except sqlite3.Error as e:
        raise Failed(f"writing {collection}/{doc_id}: {e}") from e
    return 0


def delete(collection, doc_id):
    try:
        connect().execute("DELETE FROM documents WHERE collection = ? AND id = ?", (collection, doc_id))
    except sqlite3.Error as e:
        raise Failed(f"deleting {collection}/{doc_id}: {e}") from e
    return 0


def ready():
    connect().close()
    return 0


VERBS = {"get": (get, 2, 2), "put": (put, 2, 1), "delete": (delete, 2, 1), "ready": (ready, 0, 1)}


def main(argv):
    verb = argv[1] if len(argv) > 1 else ""
    if verb not in VERBS:
        sys.stderr.write("usage: store.py get|put|delete <collection> <id> | store.py ready\n")
        return 2
    run, nargs, failure = VERBS[verb]
    args = argv[2:]
    if len(args) != nargs or not all(args):
        sys.stderr.write(f"usage: {verb}.sh" + (" <collection> <id>" if nargs else "") + "\n")
        return failure
    try:
        return run(*args)
    except Failed as e:
        sys.stderr.write(f"{verb}-sqlite: {e}\n")
        return failure


if __name__ == "__main__":
    sys.exit(main(sys.argv))
