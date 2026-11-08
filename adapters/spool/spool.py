#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The spool EventBus (docs/adr/0060 §2): standard library only.

    python3 -I spool.py publish '<data>'
    python3 -I spool.py pull
    python3 -I spool.py ack <ackId>
    python3 -I spool.py ready

The verbs' .sh files call this; core/ and adapters/inproc/run.sh call the
.sh files. One file, SPOOL_FILE (default .crew/spool.sqlite, relative to
the working directory, which ./go makes the repository root), one table of
messages in publish order. The contract is docs/adr/0019 §3's: publish
appends one message; pull leases the oldest message that is not leased, or
whose lease has expired, and prints "<ackId> <data>" on one line, or nothing
when there is none; ack deletes the message that ackId leased, and an ackId
that leases nothing (acked already, or never) is success, as a Pub/Sub ack
is best-effort. A lease lasts SPOOL_ACK_DEADLINE seconds, then the message
is delivered again: at-least-once, and the tower drops an event whose step
is no longer the document's (docs/adr/0019 §2). Silent on success; one
stderr line and exit 1 on failure.
"""

import os
import secrets
import sqlite3
import sys
import time

# Seconds a pulled message stays leased: the pubsub-emulator subscription's
# ackDeadlineSeconds (adapters/pubsub-emulator/lib.sh), the API's maximum,
# for the same reason: a whole step runs between pull and ack.
ACK_DEADLINE = 600
# Seconds a verb waits on another process's lock before failing. A decision:
# one message is a few hundred bytes, any wait near this long is a stuck
# process.
LOCK_TIMEOUT = 30


class Failed(Exception):
    """One line for stderr; the verb exits 1."""


def connect():
    path = os.environ.get("SPOOL_FILE") or ".crew/spool.sqlite"
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        db = sqlite3.connect(path, timeout=LOCK_TIMEOUT, isolation_level=None)
        db.execute("CREATE TABLE IF NOT EXISTS messages ("
                   "seq INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, "
                   "ack_id TEXT, lease_until REAL)")
    except (OSError, sqlite3.Error) as e:
        raise Failed(f"cannot open {path}: {e}") from e
    return db


def deadline():
    raw = os.environ.get("SPOOL_ACK_DEADLINE") or str(ACK_DEADLINE)
    if not raw.isdigit() or int(raw) < 1:
        raise Failed(f"SPOOL_ACK_DEADLINE={raw} is not a whole number of seconds")
    return int(raw)


def publish(data):
    # pull prints one line per message, and inproc reads one line.
    if "\n" in data or "\r" in data:
        raise Failed("a message is one line; this one has a line break")
    try:
        connect().execute("INSERT INTO messages (data) VALUES (?)", (data,))
    except sqlite3.Error as e:
        raise Failed(f"publish: {e}") from e


def pull():
    lease = deadline()
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        now = time.time()
        row = db.execute("SELECT seq, data FROM messages WHERE lease_until IS NULL OR lease_until <= ? "
                         "ORDER BY seq LIMIT 1", (now,)).fetchone()
        if row is None:
            db.execute("COMMIT")
            return
        ack_id = secrets.token_hex(16)
        db.execute("UPDATE messages SET ack_id = ?, lease_until = ? WHERE seq = ?", (ack_id, now + lease, row[0]))
        db.execute("COMMIT")
    except sqlite3.Error as e:
        raise Failed(f"pull: {e}") from e
    sys.stdout.write(f"{ack_id} {row[1]}\n")


def ack(ack_id):
    try:
        connect().execute("DELETE FROM messages WHERE ack_id = ?", (ack_id,))
    except sqlite3.Error as e:
        raise Failed(f"ack: {e}") from e


def ready():
    deadline()
    connect().close()


VERBS = {"publish": (publish, 1), "pull": (pull, 0), "ack": (ack, 1), "ready": (ready, 0)}
USAGE = {"publish": " '<json>'", "pull": "", "ack": " <ackId>", "ready": ""}


def main(argv):
    verb = argv[1] if len(argv) > 1 else ""
    if verb not in VERBS:
        sys.stderr.write("usage: spool.py publish '<json>' | pull | ack <ackId> | ready\n")
        return 1
    run, nargs = VERBS[verb]
    args = argv[2:]
    if len(args) != nargs or not all(args):
        sys.stderr.write(f"usage: {verb}.sh{USAGE[verb]}\n")
        return 1
    try:
        run(*args)
    except Failed as e:
        sys.stderr.write(f"{verb}-spool: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
