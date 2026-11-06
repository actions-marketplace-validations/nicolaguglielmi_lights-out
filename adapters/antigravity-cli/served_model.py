#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The model that answered an agy run, read from its conversation store.

Usage: python3 -I served_model.py <directory of agy conversation stores>

Prints one line: the model id, or `unknown` when none can be read (docs/adr/
0050 §5, docs/adr/0041 §6). agy 1.5.1 reports the served model nowhere else:
not in --output-format json or stream-json (their `init` echoes the requested
--model) and not to hooks (`modelName` is the requested id plus the effort,
`gemini-3.8-flash-medium`). The response's `modelVersion` is kept only in
~/.gemini/antigravity-cli/conversations/<id>.db, an SQLite file whose
`gen_metadata` table holds one protobuf blob per model call, with no
published schema. Verified 2026-11-06 in the spike of docs/adr/0050, by
decoding the wire format against a scripted model that served
`gemini-3.8-flash-spike`: that id was field 19 of field 1 in every row of the
loop's calls, while the requested `gemini-3.8-flash-medium` sat elsewhere
(field 28 of field 3). The most frequent such value across every store is the
answer, as claude-code's rule (docs/adr/0041 §6). Standard library only: it
runs in the workbench, after the container has exited.
"""
import collections
import glob
import os
import sqlite3
import sys


def varint(b, i):
    shift = value = 0
    while i < len(b):
        c = b[i]
        i += 1
        value |= (c & 0x7F) << shift
        shift += 7
        if not c & 0x80:
            return value, i
    raise ValueError("truncated varint")


def fields(b):
    """(field number, wire type, value) for each top-level field of a message;
    value is bytes for length-delimited fields, None for the others."""
    i = 0
    while i < len(b):
        key, i = varint(b, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            _, i = varint(b, i)
            yield number, wire, None
        elif wire == 1:
            i += 8
            yield number, wire, None
        elif wire == 5:
            i += 4
            yield number, wire, None
        elif wire == 2:
            n, i = varint(b, i)
            if i + n > len(b):
                raise ValueError("truncated field")
            yield number, wire, b[i:i + n]
            i += n
        else:
            raise ValueError("wire type %d" % wire)


def served_in(blob):
    """The strings at field 1 > field 19 of one gen_metadata blob."""
    out = []
    try:
        for n1, w1, v1 in fields(blob):
            if n1 != 1 or w1 != 2:
                continue
            for n2, w2, v2 in fields(v1):
                if n2 == 19 and w2 == 2:
                    out.append(v2.decode())
    except (ValueError, UnicodeDecodeError):
        return []
    return [s for s in out if s and s.isprintable()]


def main(directory):
    counts = collections.Counter()
    for path in sorted(glob.glob(os.path.join(directory, "*.db"))):
        try:
            db = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
            rows = db.execute("select data from gen_metadata").fetchall()
            db.close()
        except sqlite3.Error:
            continue
        for (blob,) in rows:
            if isinstance(blob, bytes):
                counts.update(served_in(blob))
    print(counts.most_common(1)[0][0] if counts else "unknown")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: served_model.py <directory>")
    main(sys.argv[1])
