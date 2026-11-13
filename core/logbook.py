"""The logbook's reader (docs/adr/0047 §2): stdlib only.

    python3 core/logbook.py --out <file>

Assembles `lights-out/logbook/1.4` (core/logbook/1.4.schema.json) from the
tower's documents (through the STATE_STORE port's get verb), the release
log and the latest release record, the post mortems, the policy files and
the plane's status (through the DELIVERY port's status verb) and the
project map's ADRs and tests (MAP_FILE, docs/adr/0059 §3, docs/adr/0071 §1), what the
contract gives the agents (core/agents.py, docs/adr/0073 §10), and per ticket
what its last run used: the task's `mcp` and the review's `instructions`
(docs/adr/0073 §10, the ticket's back). Every rule
is in docs/plans/console.md, "Decided at build"; this file follows it and
adds nothing.

No clock of its own: equal sources give equal bytes. A source it cannot
read becomes {"ok": false, "error": <the source's own last line>}, never
a default. The only place a source's shape change lands: the console and
any consumer read this document and nothing behind it.

Prints the number of tickets on stdout; core/logbook.sh turns it into the
one contract line. Exit 1 with one line on stdout when the file cannot be
written.
"""

import argparse
import fnmatch
import glob
import hashlib
import json
import os
import re
import sqlite3
import subprocess  # nosec B404 - git and the adapter verbs the profile names (docs/adr/0052 §3)
import sys

try:
    from .policy import PolicyError, effective
    from .spec import fields
    from .assign import HOLDING, overlaps
    from .map import SCHEMA as MAP_SCHEMA
    from . import agents as contract_agents
except ImportError:  # run as a script: core/ is sys.path[0]
    from policy import PolicyError, effective
    from spec import fields
    from assign import HOLDING, overlaps
    from map import SCHEMA as MAP_SCHEMA
    import agents as contract_agents

SCHEMA = "lights-out/logbook/1.4"
# The kanban's columns, the tower's states in its table's order (docs/adr/
# 0055 §7); a state outside the list gets a column after them.
COLUMNS = ("requested", "questions", "spec-ready", "opened", "pr-opened", "review", "ci-passed", "ci-failed",
           "needs-human", "merged", "main-green", "held", "rolled-back")
_DECIMAL = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_PROVENANCE = re.compile(r"^#\s*Provenance, (measurement|external|decision):\s*(.*)$")
_KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
# A gate's one line (CLAUDE.md, the gate output contract).
_GATE_LINE = re.compile(r"^(GO|NO-GO): ([a-z0-9-]+)(?: — .*)?$")
VERIFY_KEYS = ("ERROR_RATE_MAX_DELTA", "LATENCY_P95_MAX_DELTA")


def env(name, default=""):
    return os.environ.get(name) or default


def unread(error):
    return {"ok": False, "error": error or "unreadable, no reason given"}


def is_unread(value):
    return isinstance(value, dict) and value.get("ok") is False


def run(*argv):
    """(returncode, stdout, last stderr line) of argv, from the working directory."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=30)  # nosec B603 - an argv list, no shell, ADR 0052 §3
    except subprocess.TimeoutExpired:
        return 124, "", f"{argv[1] if len(argv) > 1 else argv[0]}: timed out after 30s"
    lines = p.stderr.strip().splitlines()
    return p.returncode, p.stdout, lines[-1] if lines else f"{' '.join(argv)}: exit {p.returncode}"


def read_json(path):
    """The file's JSON, None when absent, unread when not JSON."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        return unread(f"{path} is not JSON")


def pick(obj, keys):
    if not isinstance(obj, dict):
        return None
    return {k: obj.get(k) for k in keys}


# --- source ---------------------------------------------------------------


def source():
    rc, out, _ = run("git", "rev-parse", "HEAD")
    return {
        "commit": out.strip() if rc == 0 and out.strip() else None,
        "level": env("LEVEL"),
        "workload": env("WORKLOAD"),
        "code_host": env("CODE_HOST"),
    }


# --- the project map's ADRs (docs/adr/0059 §3) -----------------------------


def adrs():
    """{map_sha, items} from MAP_FILE, read-only; unread when there is none."""
    path = env("MAP_FILE", ".crew/map.sqlite")
    if not os.path.isfile(path):
        return unread(f"no project map at {path}: ./go map builds it")
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
            if meta.get("schema") != MAP_SCHEMA:
                return unread(f"{path} has map schema {meta.get('schema')}, the logbook reads {MAP_SCHEMA}: "
                              "./go map rebuilds it")
            nodes = {i: (kind, name) for i, kind, name in db.execute("SELECT id, kind, name FROM node")}
            rows = db.execute("SELECT n.id, n.name, n.title, d.status, d.text FROM node n JOIN doc d ON d.node = n.id "
                              "WHERE n.kind = 'adr' ORDER BY n.name").fetchall()
            files, links = {}, {}
            for src, target in db.execute("SELECT src, target FROM cite WHERE kind = 'path' AND ok = 1"):
                files.setdefault(src, set()).add(target)
            for src, dst in db.execute("SELECT src, dst FROM edge WHERE kind = 'mentions'"):
                links.setdefault(src, set()).add(dst)
                links.setdefault(dst, set()).add(src)
        finally:
            db.close()
    except sqlite3.Error as exc:
        return unread(f"{path} is not a project map: {exc}")

    def number(name):
        return os.path.basename(name)[:4]

    items = []
    for i, name, title, status, text in rows:
        near = [nodes[j] for j in links.get(i, ()) if j in nodes]
        items.append({"number": number(name), "path": name, "title": title, "status": status, "text": text,
                      "files": sorted(files.get(i, ())),
                      "adrs": sorted({number(n) for k, n in near if k == "adr"}),
                      "tickets": sorted({n for k, n in near if k == "ticket"})})
    return {"map_sha": meta.get("sha"), "items": items}


def map_tests():
    """{path: sorted tests} for every file the project map knows, from its
    `tests` edges (docs/adr/0054, docs/adr/0071 §1); None when the map is
    unread, as `adrs` says why."""
    path = env("MAP_FILE", ".crew/map.sqlite")
    if not os.path.isfile(path):
        return None
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
            if meta.get("schema") != MAP_SCHEMA:
                return None
            out = {name: [] for (name,) in db.execute("SELECT name FROM node WHERE kind IN ('file', 'test')")}
            for test, target in db.execute("SELECT t.name, f.name FROM edge e JOIN node t ON t.id = e.src "
                                           "JOIN node f ON f.id = e.dst WHERE e.kind = 'tests'"):
                out.setdefault(target, []).append(test)
        finally:
            db.close()
    except sqlite3.Error:
        return None
    return {k: sorted(set(v)) for k, v in out.items()}


def governing(book_adrs, tickets):
    """Each ticket's `adrs`, the ADRs citing a file its perimeter matches;
    each ADR's `tickets` gains the tickets it governs."""
    items = book_adrs.get("items") if isinstance(book_adrs, dict) else None
    for t in tickets if isinstance(tickets, list) else []:
        globs = t["perimeter"] if isinstance(t.get("perimeter"), list) else []
        t["adrs"] = sorted(a["number"] for a in items or []
                           if any(fnmatch.fnmatchcase(f, g) for f in a["files"] for g in globs))
        for a in items or []:
            if a["number"] in t["adrs"]:
                a["tickets"] = sorted(set(a["tickets"]) | {t["id"]})


# --- releases -------------------------------------------------------------


# What an answer records beside who and how (docs/adr/0079 §1); null when
# a record from before it has none.
ANSWER_WHY = ("reason", "brief_sha256", "brief_author")


def answer_of(obj):
    """{answer, by, via, at, reason, brief_sha256, brief_author} from a
    record's promoted/rejected object, else None."""
    for key, answer in (("promoted", "GO"), ("rejected", "NO-GO")):
        a = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(a, dict) and all(k in a for k in ("by", "via", "at")):
            return dict({"answer": answer, "by": a["by"], "via": a["via"], "at": a["at"]},
                        **{k: a.get(k) for k in ANSWER_WHY})
    return None


def release_entry(record, at, ticket, answer, origin):
    return {
        "version": record.get("version"),
        "stable": record.get("stable"),
        "image": record.get("image"),
        "stages": record.get("stages") or [],
        "verdict": record.get("verdict"),
        "held_at": record.get("held_at"),
        "reason": record.get("reason"),
        "at": at,
        "ticket": ticket,
        "answer": answer,
        "from": origin,
    }


def releases(record):
    path = env("RELEASES_LOG", ".crew/releases.jsonl")
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for n, raw in enumerate(fh, 1):
                if not raw.strip():
                    continue
                try:
                    lines.append(json.loads(raw))
                except ValueError:
                    return unread(f"{path} line {n} is not JSON")
    out = []
    for i, line in enumerate(lines):
        if line.get("kind") != "release" or not isinstance(line.get("record"), dict):
            continue
        rec = line["record"]
        answer = None
        for later in lines[i + 1:]:
            if later.get("kind") == "release":
                break
            if later.get("kind") == "answer" and later.get("version") == rec.get("version"):
                answer = {k: later.get(k) for k in ("answer", "by", "via", "at") + ANSWER_WHY}
                break
        out.append(release_entry(rec, line.get("at"), line.get("ticket"), answer, "releases.jsonl"))
    if isinstance(record, dict) and not is_unread(record) and record.get("verdict") in ("held", "rolled-back"):
        last = out[-1] if out else None
        if last is None or (last["version"], last["verdict"]) != (record.get("version"), record.get("verdict")):
            out.append(release_entry(record, None, None, answer_of(record), "release.json"))
    return out


# --- tickets --------------------------------------------------------------


def ticket_file_facts(path):
    """(first `# ` line without it, the `- Origin:` value or None)."""
    title, origin = None, None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if title is None and line.startswith("# "):
                title = line[2:].strip()
            elif origin is None and line.startswith("- Origin: "):
                origin = line[len("- Origin: "):].strip()
    return title, origin


def perimeter(path):
    """The globs under `## Perimeter`, as core/perimeter.sh reads them: each
    `- ` line up to the next `## `, backticks dropped."""
    globs, inside = [], False
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("## Perimeter"):
                inside = True
            elif inside and line.startswith("## "):
                break
            elif inside and line.startswith("- "):
                globs.append(line[2:].lstrip(" ").replace("`", ""))
    return globs or unread(f"ticket {path} has no ## Perimeter section")


TASK_KEYS = ("role", "harness", "provider", "model", "thinking", "turns", "tokens", "duration_s",
             "input_sha256", "replayed")


def outcome(doc, tid, rels):
    history = doc.get("history") or []
    last = history[-1] if history else {}
    state = doc.get("state")
    if isinstance(last, dict) and last.get("error"):
        return {"verdict": "stranded", "judge": "step", "line": last["error"]}
    if state == "needs-human":
        r = (doc.get("rework") or [{}])[-1]
        return {"verdict": "needs-human", "judge": r.get("judge"), "line": r.get("line")}
    release = doc.get("release") or {}
    if state == "rolled-back":
        return {"verdict": "NO-GO", "judge": "verify", "line": release.get("verdict")}
    if state == "held":
        answered = None
        if isinstance(rels, list):
            for r in rels:
                if r["ticket"] == tid and r["version"] == release.get("version") and r["answer"]:
                    answered = r["answer"]
        if answered and answered["answer"] == "GO":
            return {"verdict": "GO", "judge": "human",
                    "line": f"promoted by {answered['by']} via {answered['via']}"}
        if answered:
            return {"verdict": "NO-GO", "judge": "human",
                    "line": f"rejected by {answered['by']} via {answered['via']}"}
        return {"verdict": "GO", "judge": "verify", "line": release.get("verdict")}
    ci = doc.get("ci") or {}
    if ci.get("verdict") == "NO-GO":
        return {"verdict": "NO-GO", "judge": "gates", "line": ci.get("line")}
    review = doc.get("review") or {}
    if review.get("verdict") == "changes-requested":
        reason = review.get("reason") or ""
        return {"verdict": "NO-GO", "judge": "review", "line": reason.splitlines()[0] if reason else ""}
    return {"verdict": "pending", "judge": None, "line": None}


def tickets(rels):
    store = env("STATE_STORE")
    if not store:
        return unread("STATE_STORE not set; run this via ./go logbook")
    get = f"adapters/{store}/get.sh"
    out = []
    for path in sorted(glob.glob(os.path.join(env("TICKETS_DIR", "tickets"), "*.md"))):
        tid = os.path.basename(path)[:-3]
        rc, stdout, err = run("sh", get, "tickets", tid)
        if rc == 1:
            continue  # absent: the tower never opened this ticket
        if rc != 0:
            return unread(err)
        try:
            doc = json.loads(stdout)
        except ValueError:
            return unread(f"{get} printed no JSON for {tid}")
        file_title, origin = ticket_file_facts(path)
        with open(path, encoding="utf-8") as fh:
            declared = fields(fh.read())
        history = doc.get("history") or []
        spec = pick(doc.get("spec"), ("title", "sha256", "criteria", "by", "verdict", "line", "at"))
        out.append({
            "id": tid,
            "title": (spec or {}).get("title") or file_title or tid,
            "origin": origin,
            "feature": declared["feature"],
            "priority": declared["priority"],
            "perimeter": perimeter(path),
            "state": doc.get("state"),
            "attempt": doc.get("attempt"),
            "opened_at": history[0].get("at") if history else None,
            "updated_at": history[-1].get("at") if history else None,
            "outcome": outcome(doc, tid, rels),
            "spec": spec,
            "task": pick(doc.get("task"), TASK_KEYS + ("mcp",)),
            "rework": [judged(r) for r in doc.get("rework") or []],
            "pr": pick(doc.get("pr"), ("number", "url", "base_sha", "head_sha")),
            "ci": ci_entry(doc),
            "review": pick(doc.get("review"), ("role", "verdict", "reason", "harness", "model", "instructions")),
            "merge": pick(doc.get("merge"), ("sha", "head_sha")),
            "map": pick(doc.get("map"), ("sha", "docs_ticket")),
            "release": pick(doc.get("release"), ("version", "image", "verdict", "numbers")),
            "history": history,
            "questions": doc.get("questions") or [],
            "product": pick(doc.get("product"), TASK_KEYS[1:] + ("consulted", "why")),
            "tasks": attempts(doc),
            "timeline": timeline(doc, tid, rels, perimeter(path)),
        })
    return out


def ci_entry(doc):
    """The ticket's ci, judged; its `why` only on a NO-GO, for the attempt
    the ticket is at (docs/adr/0078 §2)."""
    ci = pick(doc.get("ci"), ("verdict", "failed", "risk_level", "decision", "line", "details", "head_sha", "lines",
                              "sast"))
    if ci is None:
        return None
    return judged(ci, doc.get("attempt"), ci.get("verdict") == "NO-GO")


def gate_rows(lines):
    """[{gate, verdict, line}] from a judge's gate lines, by the gate output
    contract; a line off the contract keeps its text with gate and verdict
    None (docs/adr/0071 §1). None when there are no lines."""
    if not isinstance(lines, list):
        return None
    rows = []
    for line in lines:
        m = _GATE_LINE.match(line) if isinstance(line, str) else None
        rows.append({"gate": m.group(2) if m else None, "verdict": m.group(1) if m else None, "line": line})
    return rows


def secrets_go(gates):
    """Whether the attempt's secrets gate said GO (docs/adr/0071 §1)."""
    return any(g.get("gate") == "secrets" and g.get("verdict") == "GO" for g in gates or [])


def withheld(attempt):
    return unread(f"withheld: the secrets gate did not say GO on attempt {attempt}")


def why(entry, attempt, judge):
    """Why an attempt was rejected (docs/adr/0078 §2-§3): the gate, its
    line, its details and the new SAST findings, the last two withheld
    until the same attempt's secrets gate said GO."""
    gates = gate_rows(entry.get("lines")) or []
    gate = entry.get("failed") if isinstance(entry.get("failed"), str) and entry.get("failed") else None
    if gate is None:
        gate = next((g["gate"] for g in gates if g["verdict"] == "NO-GO"), None)
    shown = secrets_go(gates)
    details, sast = entry.get("details"), entry.get("sast")
    return {
        "attempt": attempt,
        "judge": entry.get("judge") or judge,
        "gate": gate,
        "line": entry.get("line"),
        "details": (details if isinstance(details, list) else []) if shown else withheld(attempt),
        "sast": None if sast is None else sast if shown else withheld(attempt),
    }


def judged(entry, attempt=None, rejected=True):
    """A ci or rework entry with `gates` in place of its raw `lines`, and
    its `why` when it rejected the attempt (docs/adr/0078 §2): its 1.3
    `details` null where `why` withholds them."""
    if not isinstance(entry, dict):
        return entry
    out = {k: v for k, v in entry.items() if k != "lines"}
    out["gates"] = gate_rows(entry.get("lines"))
    out["why"] = why(entry, entry.get("attempt", attempt), "gates") if rejected else None
    if out["why"] and is_unread(out["why"]["details"]):
        out["details"] = None
    if out["why"] and is_unread(out["why"]["sast"]):
        out["sast"] = None
    return out


def shown_patch(patch, gates, attempt):
    """The attempt's patch only once its secrets gate said GO, else why not
    (docs/adr/0071 §1): a key a worker pasted never reaches a snapshot."""
    if patch is None:
        return None
    if secrets_go(gates):
        return patch
    return unread(f"withheld: the secrets gate did not say GO on attempt {attempt}")


def attempts(doc):
    """Every attempt's run (tower `tasks`), with its workers, its patch as
    shown_patch allows and its files (docs/adr/0071 §1)."""
    rework = {r.get("attempt"): r for r in doc.get("rework") or [] if isinstance(r, dict)}
    ci = doc.get("ci") if isinstance(doc.get("ci"), dict) else None
    # The ci on the document judged the PR's head: it vouches for the last
    # attempt only when that is the head it judged.
    head = (doc.get("pr") or {}).get("head_sha") if isinstance(doc.get("pr"), dict) else None
    if ci is not None and ci.get("head_sha") and head and ci.get("head_sha") != head:
        ci = None
    out = []
    for t in doc.get("tasks") or []:
        row = pick(t, TASK_KEYS + ("attempt",))
        if row is None:
            out.append(t)
            continue
        n = row["attempt"]
        source = rework.get(n) or (ci if ci is not None and n == doc.get("attempt") else None)
        row["members"] = t.get("members")
        row["patch"] = shown_patch(t.get("patch"), gate_rows((source or {}).get("lines")), n)
        row["files"] = t.get("files")
        out.append(row)
    return out


def ticket_files(ticket, adrs_items, holds, tests_of):
    """One row per path any attempt of TICKET touched (docs/adr/0071 §1):
    the perimeter glob, the worker, the attempts, the tests the map knows,
    the ADRs citing it and who holds it. None where the source is unread."""
    globs = ticket["perimeter"] if isinstance(ticket.get("perimeter"), list) else []
    adrs_items = None if is_unread(adrs_items) else adrs_items
    holds = None if is_unread(holds) else holds
    rows = {}
    tasks = [t for t in ticket.get("tasks") or [] if isinstance(t, dict)]
    for t in sorted(tasks, key=lambda t: t.get("attempt") if isinstance(t.get("attempt"), int) else -1):
        for f in t.get("files") or []:
            row = rows.setdefault(f["path"], {"path": f["path"], "attempts": []})
            row["member"] = f.get("member")
            if t.get("attempt") not in row["attempts"]:
                row["attempts"].append(t.get("attempt"))
    out = []
    for path in sorted(rows):
        row = rows[path]
        out.append({
            "path": path,
            "glob": next((g for g in globs if fnmatch.fnmatchcase(path, g)), None),
            "member": row["member"],
            "attempts": sorted(a for a in row["attempts"] if a is not None),
            "tests": None if tests_of is None or path not in tests_of else tests_of[path],
            "adrs": None if adrs_items is None else sorted(a["number"] for a in adrs_items if path in a["files"]),
            "held_by": None if not isinstance(holds, list) else sorted(
                h["ticket"] for h in holds if h["holding"] and any(fnmatch.fnmatchcase(path, g) for g in h["globs"])),
        })
    return out


def kanban(tickets):
    """One column per state, every ticket on one card in its state's column,
    P0 first and unprioritised last, then the oldest, then the id (§7)."""
    if not isinstance(tickets, list):
        return tickets
    states = list(COLUMNS) + sorted({t["state"] for t in tickets if t["state"] not in COLUMNS}, key=str)
    rank = {f"P{n}": n for n in range(4)}

    def order(t):
        return rank.get(t["priority"], 4), t["opened_at"] or "~", t["id"]

    return [{"state": st, "tickets": [t["id"] for t in sorted(tickets, key=order) if t["state"] == st]}
            for st in states]


def perimeters_held(tickets):
    """M27's record of who holds which files (docs/adr/0053 §5): the
    StateStore's perimeters/held, each holder with its ticket's state now
    and whether that state holds."""
    store = env("STATE_STORE")
    if not store or not isinstance(tickets, list):
        return unread("STATE_STORE not set; run this via ./go logbook") if not store else tickets
    rc, stdout, err = run("sh", f"adapters/{store}/get.sh", "perimeters", "held")
    if rc == 1:
        return []
    if rc != 0:
        return unread(err)
    try:
        held = (json.loads(stdout) or {}).get("tickets") or {}
    except (ValueError, AttributeError):
        return unread("perimeters/held is not a JSON object")
    states = {t["id"]: t["state"] for t in tickets}
    return [{"ticket": tid, "globs": globs, "state": states.get(tid), "holding": states.get(tid) in HOLDING}
            for tid, globs in sorted(held.items())]


def waiting(ticket, holds):
    """A ticket at `opened` whose last assign was refused waits (ADR 0053
    §5-§6); the holders are the holding tickets whose globs overlap its own
    perimeter now, none when the refusal was the base's."""
    history = ticket.get("history") or []
    last = history[-1] if history else {}
    if ticket.get("state") != "opened" or last.get("step") != "assign" or not last.get("error"):
        return None
    refused = [h for h in history if h.get("step") == "assign" and h.get("error")]
    mine = ticket.get("perimeter") if isinstance(ticket.get("perimeter"), list) else []
    holders = sorted({h["ticket"] for h in holds if isinstance(holds, list) and h["holding"]
                      and h["ticket"] != ticket["id"] and any(overlaps(a, b) for a in mine for b in h["globs"])})
    return {"since": refused[0].get("at"), "refusals": len(refused), "holders": holders,
            "record": "tower history, perimeters/held"}


def docs_to_realign(tickets):
    """M28's docs tickets (docs/adr/0054 §4): each merge that left docs to
    realign, with the ticket it filed and that ticket's state."""
    if not isinstance(tickets, list):
        return tickets
    states = {t["id"]: t["state"] for t in tickets}
    return [{"ticket": t["id"], "merge_sha": t["map"].get("sha"), "docs_ticket": t["map"]["docs_ticket"],
             "docs_ticket_state": states.get(t["map"]["docs_ticket"])}
            for t in tickets if isinstance(t.get("map"), dict) and t["map"].get("docs_ticket")]


# --- the timeline (docs/adr/0055 §6) -----------------------------------------


def row(phase, at, line, record, verdict=None, **more):
    return dict({"phase": phase, "at": at, "verdict": verdict, "line": line, "record": record}, **more)


def cost(task):
    t = task or {}
    return {k: t.get(k) for k in ("attempt", "harness", "model", "turns", "tokens", "duration_s", "replayed")}


def timeline(doc, tid, rels, globs):
    """One row per phase, in the order the tower's history holds them; each
    names the record it comes from. A phase with no record has no row."""
    history = [h for h in doc.get("history") or [] if isinstance(h, dict)]
    questions = [q for q in doc.get("questions") or [] if isinstance(q, dict)]
    asked = {src: [q for q in questions if q.get("from") == src] for src in ("product", "spec")}
    answered = [q for q in questions if q.get("answer")]
    tasks = {t.get("attempt"): t for t in doc.get("tasks") or [] if isinstance(t, dict)}
    spec, product = doc.get("spec") or {}, doc.get("product") or {}
    last = {h.get("step"): i for i, h in enumerate(history)}
    rows = []
    for i, h in enumerate(history):
        step, at, state = h.get("step"), h.get("at"), h.get("state")
        if h.get("error") and step == "assign":
            rows.append(row("wait", at, f"assign refused ({h['error']}): the ticket waits at opened for "
                            "./go resume (docs/adr/0053 §5-§6)", "tower history", "waiting"))
            continue
        if h.get("error"):
            rows.append(row(step, at, h["error"], "tower history", "failed", attempt=h.get("attempt")))
            continue
        if step == "request":
            who = {"by": h["by"], "via": h.get("via")} if h.get("by") else {}
            rows.append(row("request", at, "requested", "tower history", **who))
        elif step == "open":
            rows.append(row("open", at, "opened directly: no request, no spec gate", "tower history"))
        elif step in ("clarify", "answer"):
            latest = i == last.get(step) and i >= max(last.get("clarify", -1), last.get("answer", -1))
            if latest and product.get("consulted") is False:
                line = f"not consulted: {product.get('why')}"
            elif state == "questions":
                line = "asked a question"
            else:
                line = f"confirmed {len(spec.get('criteria') or [])} criteria" if latest else "confirmed the criteria"
            rows.append(row("product", at, line, "tower product", state,
                            **(cost(dict(product, attempt=None)) if latest else {})))
            if state == "questions" and asked["product"]:
                q = asked["product"].pop(0)
                rows.append(row("question", q.get("asked_at"), q.get("question"), "tower questions", by="product"))
        elif step == "answered" and answered:
            q = answered.pop(0)
            rows.append(row("answer", q.get("answered_at"), q.get("answer"), "tower questions",
                            by=q.get("answered_by"), via=q.get("answered_via")))
        elif step == "spec":
            if state == "opened":
                rows.append(row("spec", at, spec.get("line") if i == last["spec"] else "GO: spec", "tower spec", "GO"))
            else:
                q = asked["spec"].pop(0) if asked["spec"] else {}
                rows.append(row("spec", at, f"NO-GO: spec — {q.get('question')}", "tower spec", "NO-GO"))
        elif step in ("assign", "rework"):
            n = h.get("attempt")
            if step == "assign":
                pr = doc.get("pr") or {}
                refused = [e for e in history[:i] if e.get("step") == "assign" and e.get("error")]
                waited = {"refusals": len(refused), "since": refused[0].get("at")} if refused else None
                rows.append(row("assign", at, f"PR #{pr.get('number')}" if pr.get("number") else "assigned",
                                "tower history", perimeter=globs, wait=waited))
            else:
                rw = [r for r in doc.get("rework") or [] if isinstance(r, dict)]
                prior = rw[n - 2] if isinstance(n, int) and 0 <= n - 2 < len(rw) else {}
                rows.append(row("rework", at, prior.get("line"), "tower rework", attempt=n, judge=prior.get("judge")))
            task = tasks.get(n) or (doc.get("task") if not tasks and n == doc.get("attempt") else None)
            if task:
                rows.append(row("attempt", at, None, "tower tasks" if tasks else "tower task", **cost(dict(task, attempt=n))))
        elif step == "ci":
            ci = doc.get("ci") or {}
            current = i == last["ci"]
            rows.append(row("gates", at, ci.get("line") if current else None, "tower ci", state, attempt=h.get("attempt")))
            if current:
                shown = why(ci, doc.get("attempt"), "gates")["details"] if ci.get("verdict") == "NO-GO" else ci.get("details")
                rows += [row("gate", at, d, "tower ci details") for d in (shown if isinstance(shown, list) else [])]
        elif step == "review":
            r = doc.get("review") or {}
            rows.append(row("review", at, (r.get("reason") or "").split("\n")[0] or None if i == last["review"] else None,
                            "tower review", r.get("verdict") if i == last["review"] else state))
        elif step == "merge":
            rows.append(row("merge", at, (doc.get("merge") or {}).get("sha"), "tower merge", state))
        elif step == "release":
            rel = doc.get("release") or {}
            mine = [r for r in rels if r["ticket"] == tid and r["version"] == rel.get("version")] \
                if isinstance(rels, list) else []
            for stage in (mine[-1]["stages"] if mine else []):
                said = str(stage.get("verdict") or "")
                # A stage judged after docs/adr/0080 §1 has its own time and numbers.
                more = {"slo": stage["slo"]} if isinstance(stage.get("slo"), list) else {}
                rows.append(row("canary", stage.get("judged_at") or mine[-1]["at"], said, "release log",
                                "GO" if said.startswith("GO") else "NO-GO",
                                pct=stage.get("pct"), numbers=stage.get("numbers") or [], **more))
            rows.append(row("release", at, rel.get("verdict"), "tower release", state))
            answer = mine[-1]["answer"] if mine else None
            if answer:
                rows.append(row("sign-off", answer.get("at"), f"{answer.get('answer')} by {answer.get('by')}",
                                "release log", answer.get("answer"), via=answer.get("via"), reason=answer.get("reason")))
        elif step == "resume":
            rows.append(row("resume", at, f"{h.get('resumed')} requested again", "tower history"))
    end = outcome(doc, tid, rels)
    if end["verdict"] != "pending":
        rows.append(row("outcome", None, end["line"], f"outcome, judged by {end['judge']}", end["verdict"]))
    return rows


# --- thresholds -----------------------------------------------------------


def provenance(path, key):
    """{kind, text} from the comment block directly above KEY= in path, else None."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    for i, raw in enumerate(lines):
        m = _KEY_LINE.match(raw.strip())
        if not m or m.group(1) != key:
            continue
        block = []
        j = i - 1
        while j >= 0 and lines[j].strip().startswith("#"):
            block.insert(0, lines[j].strip())
            j -= 1
        for k, c in enumerate(block):
            pm = _PROVENANCE.match(c)
            if pm:
                rest = [b.lstrip("#").strip() for b in block[k + 1:]]
                text = " ".join(t for t in [pm.group(2).strip()] + rest if t)
                return {"kind": pm.group(1), "text": text}
        return None
    return None


def keys_in(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return {m.group(1): m.group(2) for m in (_KEY_LINE.match(l.strip()) for l in fh) if m}
    except OSError:
        return {}


def thresholds():
    contract = env("WORKLOAD_CONTRACT")
    if not contract:
        return unread("WORKLOAD_CONTRACT not set; run this via ./go logbook")
    platform, workload_env, overrides = "policy/merge.env", f"{contract}/workload.env", f"{contract}/policy.env"
    try:
        with open(platform, encoding="utf-8") as fh:
            platform_text = fh.read()
        with open(workload_env, encoding="utf-8") as fh:
            workload_text = fh.read()
        overrides_text = ""
        if os.path.isfile(overrides):
            with open(overrides, encoding="utf-8") as fh:
                overrides_text = fh.read()
        policy, _ = effective(platform_text, workload_text, overrides_text)
    except OSError as exc:
        return unread(f"{exc.filename}: {exc.strerror}")
    except PolicyError as exc:
        where = {"platform": platform, "workload": workload_env}.get(exc.source, overrides)
        return unread(f"{where}: {exc}")
    overridden = keys_in(overrides)
    out = []
    for key, value in policy.items():
        if not _DECIMAL.match(value):
            continue
        if key in overridden:
            path, over = overrides, True
        elif key == "MUTATION_BASELINE":
            path, over = workload_env, False
        else:
            path, over = platform, False
        judge = "verify" if key in VERIFY_KEYS else "gates"
        out.append({"key": key, "value": value, "file": path, "overridden": over, "judge": judge,
                    "provenance": provenance(path, key)})
    rework = "policy/rework.env"
    value = keys_in(rework).get("REWORK_MAX_ATTEMPTS")
    if value is None:
        return unread(f"{rework} sets no REWORK_MAX_ATTEMPTS")
    out.append({"key": "REWORK_MAX_ATTEMPTS", "value": value, "file": rework, "overridden": False,
                "judge": "rework", "provenance": provenance(rework, "REWORK_MAX_ATTEMPTS")})
    return out


# --- agents ---------------------------------------------------------------


def agents():
    """{lines}: what the local contract gives the agents, the wording `./go
    agents` prints (docs/adr/0073 §10); unread, as thresholds, on a refusal."""
    contract = env("WORKLOAD_CONTRACT")
    if not contract:
        return unread("WORKLOAD_CONTRACT not set; run this via ./go logbook")
    try:
        return {"lines": contract_agents.lines_for(contract)}
    except contract_agents.Refusal as exc:
        return unread(f"NO-GO: agents — {exc}")
    except OSError as exc:
        return unread(f"{exc.filename}: {exc.strerror}")


# --- post mortems ---------------------------------------------------------


def postmortems():
    out = []
    base = env("POSTMORTEM_DIR", ".crew/postmortem")
    for path in sorted(glob.glob(os.path.join(base, "*", "postmortem.json"))):
        pm = read_json(path)
        if is_unread(pm) or not isinstance(pm, dict):
            return pm if is_unread(pm) else unread(f"{path} is not an object")
        run_ = pm.get("run") or {}
        recorded = run_.get("recorded")
        replayed = bool(run_.get("source") and isinstance(recorded, dict))
        who = recorded if replayed else run_
        out.append({
            "name": pm.get("incident"),
            "title": pm.get("title"),
            "window": pm.get("window"),
            "release": pm.get("release"),
            "chain": pm.get("chain"),
            "timeline": pm.get("timeline") or [],
            "causes": pm.get("causes") or [],
            "actions": [pick(a, ("n", "title", "ticket")) for a in pm.get("actions") or []],
            "run": {"provider": who.get("provider"), "model": who.get("model"), "replayed": replayed},
        })
    return out


# --- launch ---------------------------------------------------------------


def plane():
    delivery = env("DELIVERY")
    if not delivery:
        return unread("DELIVERY not set; run this via ./go logbook")
    status = f"adapters/{delivery}/status.sh"
    rc, out, err = run("sh", status)
    if rc != 0:
        return unread(err)
    try:
        value = json.loads(out)
    except ValueError:
        return unread(f"{status} printed no JSON")
    return {k: value.get(k) for k in ("stable", "canary", "weight")}


def brief():
    out_dir = env("PROMOTE_OUT", ".crew/promote")
    path = os.path.join(out_dir, "brief.md")
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        data = fh.read()
    author = None
    try:
        with open(os.path.join(out_dir, "brief.author"), encoding="utf-8") as fh:
            author = fh.readline().rstrip("\n") or None
    except OSError:
        pass
    return {"text": data.decode("utf-8"), "sha256": hashlib.sha256(data).hexdigest(), "author": author}


def launch(record):
    p = plane()
    b = brief()
    pressable, preparable, reason = False, False, None
    if record is None:
        reason = "no release record; run ./go release"
    elif is_unread(record):
        reason = record["error"]
    else:
        v = record.get("version")
        answered = answer_of(record)
        if record.get("verdict") != "held":
            reason = f"release {v} is {record.get('verdict')}, nothing to promote"
        elif "promoted" in record or "rejected" in record:
            a = answered or {"answer": "GO" if "promoted" in record else "NO-GO", "by": "?", "via": "?"}
            reason = f"release {v} was already answered {a['answer']} by {a['by']} via {a['via']}"
        elif is_unread(p):
            reason = f"the plane cannot be read: {p['error']}"
        elif p.get("canary") != v or p.get("weight") != record.get("held_at"):
            reason = (f"the record holds {v} at {record.get('held_at')}%, "
                      f"the plane has canary {p.get('canary') or 'none'} at {p.get('weight')}%")
        elif b is None or (v or "") not in b["text"]:
            preparable, reason = True, f"no brief for {v} yet; prepare it"
        else:
            pressable = True
    return {"record": record, "plane": p, "brief": b, "pressable": pressable,
            "preparable": preparable, "disabled_reason": reason}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    record = read_json(env("RELEASE_RECORD", ".crew/release.json"))
    rels = releases(record)
    held = tickets(rels)
    holds = perimeters_held(held)
    for t in held if isinstance(held, list) else []:
        t["wait"] = waiting(t, holds)
    decisions = adrs()
    governing(decisions, held)
    items = decisions.get("items") if isinstance(decisions, dict) and not is_unread(decisions) else None
    tests_of = map_tests() if items is not None else None
    for t in held if isinstance(held, list) else []:
        t["files"] = ticket_files(t, items, holds, tests_of)
    book = {
        "schema": SCHEMA,
        "source": source(),
        "tickets": held,
        "kanban": kanban(held),
        "releases": rels,
        "postmortems": postmortems(),
        "thresholds": thresholds(),
        "agents": agents(),
        "launch": launch(record),
        "perimeters_held": holds,
        "docs_to_realign": docs_to_realign(held),
        "adrs": decisions,
    }
    text = json.dumps(book, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    tmp = args.out + ".tmp"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, args.out)
    except OSError as exc:
        print(f"cannot write {args.out}: {exc.strerror}")
        return 1
    print(len(book["tickets"]) if isinstance(book["tickets"], list) else 0)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
