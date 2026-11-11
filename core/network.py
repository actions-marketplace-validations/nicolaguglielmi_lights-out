# SPDX-License-Identifier: Apache-2.0
"""The governed network in text (docs/adr/0071 §4, §5): stdlib only.

    python3 core/network.py --logbook <file> [--ticket <id>] [--attempt <n>]
    python3 core/network.py --table

Reads one logbook file and nothing else. Prints, for one ticket and one of
its attempts, the facts the console's #network screen draws, in the same
words: the graph (the tower, the six roles, the attempt's workers, each
gate's verdict, the review, the rework loop, the canary stages, the human
gate), the stream of attempts with their files and gate lines, the chosen
attempt's patch, and the files by perimeter. Every sentence that is not a
logbook value printed verbatim comes from TABLE["words"]; the console
embeds TABLE as #network-words and ./go ci proves the copy equal.

A view, not a gate: stdout is the view, no colour, no clock, the same bytes
for the same logbook. Exit 1 with one stderr line and nothing on stdout when
the logbook is absent, not JSON or not major 1; exit 2 likewise for a ticket
or an attempt the logbook does not hold.
"""
import argparse
import json
import sys

# roles: the six roles/ directories (ci/roles.sh); gates: the Makefile's
# GATES, in its order. ci/logbook.sh proves both, and the page's copy.
TABLE = {
    "roles": ["architect", "dev-worker", "ops-triage", "product", "release", "test-reviewer"],
    "gates": ["risk", "secrets", "test-weakening", "deps", "sast", "test", "mutation", "test-proof"],
    "words": {
        "heading": "ticket {id} — {title} · attempt {attempt}",
        "heading_none": "ticket {id} — {title} · no attempt yet",
        "tower": "tower: the ticket is at {state}",
        "role_ran": "role {role}: ran for this ticket",
        "role_idle": "role {role}: did not run for this ticket",
        "worker": "worker {id}: {harness}, {model}",
        "no_model": "no model",
        "replayed": ", replayed",
        "hand_written": ", hand-written: no model ran",
        "no_worker": "worker: none recorded for attempt {attempt}",
        "gate": "gate {gate}: {verdict}",
        "gate_off": "gate line off the contract: {line}",
        "not_run": "gate {gate}: not run, an earlier gate said NO-GO",
        "not_run_yet": "gate {gate}: not run yet",
        "gates_summary": "gate gates: {line}",
        "review": "review: {verdict} by {role}",
        "review_back": "review: sent attempt {attempt} back",
        "review_none": "review: not reached on attempt {attempt}",
        "review_none_yet": "review: not reached",
        "rework": "rework: {count} sent back to the dev-worker, at most {max} attempts",
        "rework_nomax": "rework: {count} sent back to the dev-worker",
        "stage": "canary {pct}%: {line}",
        "stage_none": "canary: not reached",
        "human": "human gate: {line} via {via}",
        "human_waiting": "human gate: waiting for go-for-launch",
        "human_rolled_back": "human gate: not reached, the canary rolled back",
        "human_none": "human gate: not reached",
        "attempt": "attempt {attempt}, by {who}",
        "attempt_sent_back": "sent back: {line}",
        "file": "{path} +{added} −{removed}",
        "file_binary": "{path}, binary",
        "file_by": ", by {member}",
        "patch": "patch: {bytes} bytes",
        "patch_cut": "patch: {bytes} bytes, cut at {shown} bytes",
        "patch_none": "patch: not recorded",
        "no_attempt": "no attempt yet",
        "old_logbook": "this logbook ({version}) records no patches or gate lines",
        "patch_begin": "--- patch of attempt {attempt} ---",
        "patch_end": "--- end of patch ---",
        "perimeter": "perimeter {glob}",
        "perimeter_empty": "perimeter {glob}: no file touched",
        "perimeter_adrs": "ADRs governing the perimeter: {adrs}",
        "outside": "outside the perimeter",
        "file_row": "{path}: by {member}, attempts {attempts}, tests {tests}, ADRs {adrs}, held by {held}",
        "none": "none",
        "who_unknown": "a worker the logbook does not record",
        "single": "the single worker",
        "unknown_to_map": "not in the project map",
        "unread": "could not read {what}: {error}",
    },
}
SECTIONS = ("graph", "stream", "files by perimeter")


class Refused(Exception):
    def __init__(self, line, code):
        super().__init__(line)
        self.line, self.code = line, code


def w(key, **kw):
    return TABLE["words"][key].format(**kw)


def unread(v):
    return isinstance(v, dict) and v.get("ok") is False


def minor(book):
    schema = str(book.get("schema") or "")
    try:
        return int(schema.rsplit(".", 1)[1])
    except (IndexError, ValueError):
        return 0


def version(book):
    """The logbook's version, `1.2` of `lights-out/logbook/1.2`."""
    return str(book.get("schema") or "").rsplit("/", 1)[-1]


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            book = json.load(fh)
    except OSError as exc:
        raise Refused(f"network: cannot read the logbook {path}: {exc.strerror}", 1)
    except ValueError:
        raise Refused(f"network: {path} is not JSON", 1)
    schema = book.get("schema") if isinstance(book, dict) else None
    if not isinstance(schema, str) or not schema.startswith("lights-out/logbook/1."):
        raise Refused(f"network: {path} is not a lights-out/logbook/1.x logbook (schema {schema})", 1)
    return book


def tickets(book):
    return book["tickets"] if isinstance(book.get("tickets"), list) else []


def default_ticket(book):
    """The newest updated (docs/adr/0071 §2), ties the highest id."""
    ts = tickets(book)
    if not ts:
        return None
    return max(ts, key=lambda t: (t.get("updated_at") is not None, t.get("updated_at") or "", t["id"]))["id"]


def attempts_of(t):
    seen = {x.get("attempt") for x in t.get("tasks") or [] if isinstance(x, dict)}
    seen |= {r.get("attempt") for r in t.get("rework") or [] if isinstance(r, dict)}
    seen.add(t.get("attempt"))
    return sorted(n for n in seen if isinstance(n, int))


def task_of(t, n):
    for x in t.get("tasks") or []:
        if isinstance(x, dict) and x.get("attempt") == n:
            return x
    return t.get("task") if n is not None and n == t.get("attempt") and isinstance(t.get("task"), dict) else None


def rework_of(t, n):
    return next((r for r in t.get("rework") or [] if isinstance(r, dict) and r.get("attempt") == n), None)


def judge_of(t, n):
    """The record that judged attempt n: its rework entry, or the ticket's ci for the latest."""
    r = rework_of(t, n)
    if r is not None:
        return r
    ci = t.get("ci")
    return ci if isinstance(ci, dict) and n == t.get("attempt") else None


def workers(task):
    """[{id, harness, model, replayed, hand_written}] of one attempt."""
    if not isinstance(task, dict):
        return []
    if isinstance(task.get("members"), list):
        return [{"id": m.get("id"), "harness": m.get("harness"), "model": m.get("model"),
                 "replayed": m.get("replayed") is True, "hand_written": m.get("hand_written") is True}
                for m in task["members"]]
    return [{"id": task.get("role") or "dev-worker", "harness": task.get("harness"), "model": task.get("model"),
             "replayed": task.get("replayed") is True, "hand_written": task.get("hand_written") is True}]


def worker_fact(m):
    text = w("worker", id=m["id"], harness=m["harness"] or "unknown", model=m["model"] or w("no_model"))
    return text + (w("replayed") if m["replayed"] else "") + (w("hand_written") if m["hand_written"] else "")


def gate_edges(t, n):
    """[{gate, verdict, text}] for attempt n: the gates that ran, in run
    order, then the table's gates that did not."""
    judge = judge_of(t, n)
    rows = judge.get("gates") if isinstance(judge, dict) else None
    if rows is None and judge is not None:
        # A record from before 1.3: one summary edge. A rework entry the
        # reviewer or main's check wrote follows a gates GO (docs/adr/0038).
        back = rework_of(t, n)
        if back is not None and back.get("judge") != "gates":
            return [{"gate": "gates", "verdict": "GO", "text": w("gates_summary", line="GO")}]
        verdict = "NO-GO" if back is not None else judge.get("verdict")
        return [{"gate": "gates", "verdict": verdict if verdict in ("GO", "NO-GO") else "not-run",
                 "text": w("gates_summary", line=judge.get("line") or "—")}]
    out, failed = [], False
    for g in rows or []:
        if g.get("gate") is None:
            out.append({"gate": None, "verdict": None, "text": w("gate_off", line=g.get("line"))})
            continue
        failed = failed or g.get("verdict") == "NO-GO"
        out.append({"gate": g["gate"], "verdict": g["verdict"], "text": w("gate", gate=g["gate"], verdict=g["verdict"])})
    ran = {g["gate"] for g in out}
    for g in TABLE["gates"]:
        if g not in ran:
            out.append({"gate": g, "verdict": "not-run", "text": w("not_run" if failed else "not_run_yet", gate=g)})
    return out


def rework_max(book):
    for x in book.get("thresholds") if isinstance(book.get("thresholds"), list) else []:
        if x.get("key") == "REWORK_MAX_ATTEMPTS" and str(x.get("value", "")).isdigit():
            return int(x["value"])
    return None


def roles_ran(t):
    names = {x.get("role") for x in t.get("tasks") or [] if isinstance(x, dict)}
    for key in ("task", "review"):
        if isinstance(t.get(key), dict):
            names.add(t[key].get("role"))
    if isinstance(t.get("product"), dict) and t["product"].get("consulted") is True:
        names.add("product")
    return names


def human(t):
    rows = [r for r in t.get("timeline") or [] if isinstance(r, dict)]
    signed = [r for r in rows if r.get("phase") == "sign-off"]
    if signed:
        r = signed[-1]
        return {"verdict": r.get("verdict"), "text": w("human", line=r.get("line"), via=r.get("via"))}
    if t.get("state") == "held":
        return {"verdict": "waiting", "text": w("human_waiting")}
    if t.get("state") == "rolled-back":
        return {"verdict": "not-reached", "text": w("human_rolled_back")}
    return {"verdict": "not-reached", "text": w("human_none")}


def review(t, n):
    latest = n == t.get("attempt")
    r = t.get("review")
    if latest and isinstance(r, dict) and r.get("verdict"):
        return {"verdict": r["verdict"], "text": w("review", verdict=r["verdict"], role=r.get("role") or "the reviewer")}
    back = rework_of(t, n)
    if back is not None and back.get("judge") == "review":
        return {"verdict": "changes-requested", "text": w("review_back", attempt=n)}
    return {"verdict": "not-reached", "text": w("review_none", attempt=n) if n is not None else w("review_none_yet")}


def joined(values):
    if values is None:
        return None
    return ", ".join(str(v) for v in values) if values else w("none")


def view(book, ticket=None, attempt=None):
    """{heading, graph, stream, patch, files}: every fact of the screen, in
    order; each fact a dict whose `text` is one line of the CLI."""
    tid = ticket if ticket is not None else default_ticket(book)
    t = next((x for x in tickets(book) if x["id"] == tid), None)
    if t is None:
        raise Refused(f"network: the logbook holds no ticket {tid}", 2)
    ns = attempts_of(t)
    if attempt is not None and attempt not in ns:
        raise Refused(f"network: ticket {tid} has no attempt {attempt} (attempts: {joined(ns)})", 2)
    n = attempt if attempt is not None else (ns[-1] if ns else None)
    old = minor(book) < 3
    title = t.get("title") or tid
    title = title[len(tid):].lstrip(" —") if title.startswith(tid) else title
    out = {"ticket": tid, "attempt": n, "old": old,
           "heading": w("heading", id=tid, title=title, attempt=n) if n is not None else w("heading_none", id=tid, title=title)}
    g = [{"kind": "tower", "text": w("tower", state=t.get("state"))}]
    ran = roles_ran(t)
    g += [{"kind": "role", "role": r, "ran": r in ran, "text": w("role_ran" if r in ran else "role_idle", role=r)}
          for r in TABLE["roles"]]
    if n is not None:
        ws = workers(task_of(t, n))
        g += [dict(m, kind="worker", text=worker_fact(m)) for m in ws] or [{"kind": "worker", "id": None, "text": w("no_worker", attempt=n)}]
    # With no attempt yet every gate is still drawn, none of them run.
    g += [dict(e, kind="gate", attempt=n) for e in gate_edges(t, n)]
    g.append(dict(review(t, n), kind="review"))
    rework = [r for r in t.get("rework") or [] if isinstance(r, dict)]
    if rework:
        mx = rework_max(book)
        g.append({"kind": "rework", "count": len(rework), "max": mx,
                  "text": w("rework", count=len(rework), max=mx) if mx is not None else w("rework_nomax", count=len(rework))})
    stages = [r for r in t.get("timeline") or [] if isinstance(r, dict) and r.get("phase") == "canary"]
    g += [{"kind": "stage", "pct": s.get("pct"), "verdict": s.get("verdict"), "text": w("stage", pct=s.get("pct"), line=s.get("line"))}
          for s in stages] or [{"kind": "stage", "pct": None, "verdict": None, "text": w("stage_none")}]
    g.append(dict(human(t), kind="human"))
    out["graph"] = g

    stream = []
    if old:
        stream.append({"kind": "old", "text": w("old_logbook", version=version(book))})
    for k in reversed(ns):
        task = task_of(t, k)
        who = ", ".join(m["id"] for m in workers(task)) or w("who_unknown")
        entry = {"kind": "attempt", "attempt": k, "text": w("attempt", attempt=k, who=who), "items": []}
        for f in (task or {}).get("files") or []:
            text = (w("file_binary", path=f["path"]) if f.get("added") is None
                    else w("file", path=f["path"], added=f["added"], removed=f["removed"]))
            entry["items"].append({"kind": "file", "path": f["path"], "text": text + (w("file_by", member=f["member"]) if f.get("member") else "")})
        judge = judge_of(t, k)
        for row in (judge or {}).get("gates") or []:
            entry["items"].append({"kind": "line", "gate": row.get("gate"), "verdict": row.get("verdict"), "text": row.get("line")})
        back = rework_of(t, k)
        if back is not None:
            entry["items"].append({"kind": "sent-back", "text": w("attempt_sent_back", line=back.get("line"))})
        p = (task or {}).get("patch") if not old else None
        if isinstance(p, dict) and unread(p):
            entry["items"].append({"kind": "patch", "text": p.get("error")})
        elif isinstance(p, dict):
            cut = len(p["text"].encode("utf-8"))
            entry["items"].append({"kind": "patch", "text": w("patch_cut", bytes=p["bytes"], shown=cut) if p.get("truncated")
                                   else w("patch", bytes=p["bytes"])})
        elif not old:
            entry["items"].append({"kind": "patch", "text": w("patch_none")})
        entry["patch"] = p if isinstance(p, dict) and not unread(p) else None
        stream.append(entry)
    if not ns:
        stream.append({"kind": "none", "text": w("no_attempt")})
    out["stream"] = stream
    chosen = next((e for e in stream if e["kind"] == "attempt" and e["attempt"] == n), None)
    out["patch"] = chosen["patch"] if chosen else None

    files = [{"kind": "old", "text": w("old_logbook", version=version(book))}] if old else []
    if unread(book.get("adrs")):
        files.append({"kind": "unread", "text": w("unread", what="the project map", error=book["adrs"]["error"])})
    if unread(book.get("perimeters_held")):
        files.append({"kind": "unread", "text": w("unread", what="who holds which files", error=book["perimeters_held"]["error"])})
    globs = t.get("perimeter")
    rows = t.get("files") if isinstance(t.get("files"), list) else []
    if unread(globs):
        files.append({"kind": "unread", "text": w("unread", what="the perimeter", error=globs["error"])})
        globs = []
    for glob in (globs or []) + ([None] if any(r.get("glob") is None for r in rows) else []):
        mine = [r for r in rows if r.get("glob") == glob]
        label = glob if glob is not None else w("outside")
        if not mine:
            files.append({"kind": "glob", "glob": glob, "text": w("perimeter", glob=label)}) if old else \
                files.append({"kind": "glob", "glob": glob, "text": w("perimeter_empty", glob=label)})
            continue
        files.append({"kind": "glob", "glob": glob, "text": w("perimeter", glob=label)})
        for r in mine:
            tests = joined(r.get("tests"))
            files.append({"kind": "file", "row": r, "text": w(
                "file_row", path=r["path"], member=r.get("member") or w("single"), attempts=joined(r.get("attempts")),
                tests=tests if tests is not None else w("unknown_to_map"),
                adrs=joined(r.get("adrs")) if r.get("adrs") is not None else w("unknown_to_map"),
                held=joined(r.get("held_by")) if r.get("held_by") is not None else w("none"))})
    if isinstance(t.get("adrs"), list):
        files.append({"kind": "adrs", "text": w("perimeter_adrs", adrs=joined(t["adrs"]))})
    out["files"] = files
    return out


def text(v):
    """The CLI's bytes for one view."""
    lines = [v["heading"], SECTIONS[0]]
    lines += ["  " + f["text"] for f in v["graph"]]
    lines.append(SECTIONS[1])
    for e in v["stream"]:
        lines.append("  " + e["text"])
        lines += ["    " + i["text"] for i in e.get("items", [])]
    if v["patch"] is not None:
        lines.append(w("patch_begin", attempt=v["attempt"]))
        lines += v["patch"]["text"].splitlines()
        lines.append(w("patch_end"))
    lines.append(SECTIONS[2])
    for f in v["files"]:
        lines.append(("    " if f["kind"] == "file" else "  ") + f["text"])
    return "\n".join(lines) + "\n"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", action="store_true")
    parser.add_argument("--logbook")
    parser.add_argument("--ticket")
    parser.add_argument("--attempt")
    args = parser.parse_args(argv)
    if args.table:
        sys.stdout.write(json.dumps(TABLE, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        return 0
    try:
        if not args.logbook:
            raise Refused("network: no --logbook given; run it via ./go network", 1)
        book = load(args.logbook)
        attempt = None
        if args.attempt not in (None, ""):
            if not args.attempt.isdigit():
                raise Refused(f"network: ATTEMPT is {args.attempt}, not a number", 2)
            attempt = int(args.attempt)
        out = text(view(book, args.ticket or None, attempt))
    except Refused as refused:
        print(refused.line, file=sys.stderr)
        return refused.code
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
