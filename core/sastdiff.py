"""The sast gate's verdict on the diff (docs/adr/0072 §1): stdlib only, no process.

    python3 core/sastdiff.py read <line-file>
    python3 core/sastdiff.py diff <json-out> <where> <prefix> <head-root> <head-line> <base-root> <base-line> < renames

The runner's line (ADR 0072 §1, amending ADR 0030 §3) is the last non-empty
line of its stdout: `{"findings": N, "items": [{"rule", "file", "line"}]}`,
`file` relative to the directory the runner ran from. A runner that predates
ADR 0072 prints `{"findings": N}` only.

`read`, for gates/sast.sh: exit 0 with `<N> items` or `<N> none` (no `items`,
an old runner) on stdout, or exit 1 with the reason the line is not a runner
line.

`diff`: each side's items fingerprinted as (rule, repository path, sha256 of
the flagged line's text with all whitespace removed). <prefix> is the run
directory's path from the repository root ('' or ending in '/'); <head-root>
and <base-root> are the run directories on disk, where the flagged line is
read: the trees the runner scanned. Base paths are mapped through the
renames on stdin, `git diff -M --name-status -z <base> <head>`. <base-line>
`-` is a base with nothing to scan (the empty tree). Counted as a multiset:
a fingerprint HEAD has more times than the base is new. Exit 0 with `none new
(<m> inherited)`, or exit 1 with `this diff introduces <n> finding(s); list
on stderr`, or exit 2 when it cannot judge; the lists on stderr; <json-out> gets findings, where, new and
inherited, each item with its repository path and HEAD's line.
"""

import hashlib
import json
import os
import posixpath
import sys

USAGE = ("usage: sastdiff.py read <line-file> | "
         "diff <json-out> <where> <prefix> <head-root> <head-line> <base-root> <base-line> < renames")


class Malformed(Exception):
    """The runner's line breaks the contract; the message says how."""


def runner_line(text):
    """The parsed runner line: (findings, items or None). Raises Malformed."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise Malformed("SAST_CMD printed nothing on stdout")
    last = lines[-1].strip()
    try:
        doc = json.loads(last)
    except ValueError:
        raise Malformed(f"SAST_CMD did not print valid JSON on stdout: {last}") from None
    if not isinstance(doc, dict):
        raise Malformed(f"SAST_CMD did not print a JSON object on stdout: {last}")
    n = doc.get("findings")
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise Malformed(f"SAST_CMD's findings is not a count: {last}")
    if "items" not in doc:
        return n, None
    items = doc["items"]
    if not isinstance(items, list):
        raise Malformed("SAST_CMD's items is not a list")
    if len(items) != n:
        raise Malformed(f"SAST_CMD reports {n} finding(s) and {len(items)} item(s)")
    for i, item in enumerate(items):
        ok = (isinstance(item, dict)
              and isinstance(item.get("rule"), str) and item["rule"]
              and isinstance(item.get("file"), str) and item["file"]
              and isinstance(item.get("line"), int) and not isinstance(item["line"], bool)
              and item["line"] >= 0)
        if not ok:
            raise Malformed(f"SAST_CMD's item {i + 1} is not {{rule, file, line}}: {json.dumps(item)}")
    return n, items


def renames(raw):
    """old path -> new path, from `git diff -M --name-status -z`."""
    fields = raw.split("\0")
    out, i = {}, 0
    while i < len(fields):
        status = fields[i]
        if not status:
            i += 1
            continue
        if status[0] in "RC":
            if i + 2 < len(fields) and status[0] == "R":
                out[fields[i + 1]] = fields[i + 2]
            i += 3
        else:
            i += 2
    return out


def norm(path):
    path = posixpath.normpath(path)
    return "" if path == "." else path


def line_text(root, rel, number):
    """The flagged line's text, all whitespace removed; '' when it is not there."""
    try:
        with open(os.path.join(root, rel), "rb") as f:
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return ""
    if number < 1 or number > len(lines):
        return ""
    return "".join(lines[number - 1].split())


def fingerprints(items, root, prefix, moved=None):
    """[(fingerprint, item with its repository path)], in the runner's order."""
    out = []
    for item in items:
        rel = norm(item["file"])
        path = norm(prefix + rel)
        if moved:
            path = moved.get(path, path)
        digest = hashlib.sha256(line_text(root, rel, item["line"]).encode()).hexdigest()
        out.append(((item["rule"], path, digest), {"rule": item["rule"], "file": path, "line": item["line"]}))
    return out


def judge(head, base):
    """(new, inherited) lists of HEAD's items: per fingerprint, the first
    min(head, base) are inherited, the rest new."""
    left = {}
    for key, _ in base:
        left[key] = left.get(key, 0) + 1
    new, inherited = [], []
    for key, item in head:
        if left.get(key, 0) > 0:
            left[key] -= 1
            inherited.append(item)
        else:
            new.append(item)
    return new, inherited


def read_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def show(item):
    return f"  {item['rule']} {item['file']}:{item['line']}"


def main(argv):
    if len(argv) == 2 and argv[0] == "read":
        try:
            n, items = runner_line(read_file(argv[1]))
        except (Malformed, OSError) as e:
            print(e)
            return 1
        print(f"{n} {'none' if items is None else 'items'}")
        return 0
    if len(argv) != 8 or argv[0] != "diff":
        print(USAGE, file=sys.stderr)
        return 2
    out, where, prefix, head_root, head_line, base_root, base_line = argv[1:]
    try:
        n, head_items = runner_line(read_file(head_line))
        base_items = [] if base_line == "-" else runner_line(read_file(base_line))[1]
    except (Malformed, OSError) as e:
        print(e)
        return 2
    if head_items is None or base_items is None:
        print("a runner line has no items; gates/sast.sh judges HEAD whole")
        return 2
    head = fingerprints(head_items, head_root, prefix)
    base = fingerprints(base_items, base_root, prefix, renames(sys.stdin.read()))
    new, inherited = judge(head, base)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"findings": n, "where": where, "new": new, "inherited": inherited}, f)
        f.write("\n")
    if inherited:
        print(f"sast: {len(inherited)} finding(s) inherited from the base, not gating (docs/adr/0072 §1):", file=sys.stderr)
        for item in inherited:
            print(show(item), file=sys.stderr)
    if new:
        print(f"sast: {len(new)} finding(s) introduced by this diff:", file=sys.stderr)
        for item in new:
            print(show(item), file=sys.stderr)
        print(f"this diff introduces {len(new)} finding(s); list on stderr")
        return 1
    print(f"none new ({len(inherited)} inherited)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
