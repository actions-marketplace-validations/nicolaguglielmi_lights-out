"""The intake interview (docs/adr/0090): stdlib only. The logic of the
intake, interview, intake-answer and perimeter steps and of the
confirmation; core/tower.py and the step scripts are its entry points
(docs/adr/0052 §3).

    python3 core/intake.py new <text file> <tickets dir> [<id>]
        the client's words to <tickets dir>/<id>.intake.md, exclusive
        create, the id the next free one when not given; prints the id (§1)
    python3 core/intake.py first <doc.json> <tickets dir>
        the interview's first user message on stdout: `# Intake request`,
        a blank line, the raw text (§2)
    python3 core/intake.py answers <doc.json>
        the answers so far, as later user turns: a JSON list (§2)
    python3 core/intake.py interview <doc.json> <run dir> <exit code>
        the interview/intake-answer step's result: `intake-questions` or
        `drafted` (§2, §4)
    python3 core/intake.py proposal <doc.json>
        the architect's first message: the proposed tickets as JSON (§3)
    python3 core/intake.py perimeter <doc.json> <run dir> <exit code>
        the perimeter step's result: `proposed`, each ticket checked by
        gates/spec.sh (§3)
    python3 core/intake.py compose <ticket.json> <id> <intake id>
        the Markdown a proposed ticket becomes (§5)

A step result is the JSON object core/tower.py merges into the document.
A refusal is one stderr line and exit 1, which fails the step (ADR 0034);
its line is also written to $STEP_WHY when the tower gives one (§6).
"""

import json
import os
import re
import subprocess  # nosec B404 - gates/spec.sh, an argv list (docs/adr/0052 §3)
import sys
import tempfile
from datetime import datetime, timezone

try:
    from .tower import task
    from . import spec
except ImportError:  # run as a script: core/ is sys.path[0]
    from tower import task
    import spec

# Provenance, decision: docs/adr/0090 §2, one question per topic of the
# interview's agenda (who, the main scenario, out of scope, how we know it
# works, constraints).
CAP = 5
LAST = "That was the last question this interview allows: propose the tickets now."
FIRST = "# Intake request"
SUFFIX = ".intake.md"
DECISIONS = ("ask_product_owner", "propose_ticket", "confirm_acceptance")
EDITABLE = ("title", "problem", "criteria", "perimeter", "feature", "priority")
_ID = re.compile(r"^\d{4}$")


class Refused(Exception):
    """A refusal; RUN, when given, is the step result's run field the tower
    ledgers for a stopped run (`{"architect": {...}}`, amendment A3)."""

    def __init__(self, message, run=None):
        super().__init__(message)
        self.run = run


def stopped(field, run):
    """The STEP_RUN object of a role's run that failed: its task and its stop."""
    return {field: dict(task(run), stop=run.get("stop"))}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def intake_file(tickets_dir, tid):
    return os.path.join(tickets_dir, f"{tid}{SUFFIX}")


# --- §1 the client's words -------------------------------------------------


def new(text, tickets_dir, tid=None):
    """Write TEXT to <tickets dir>/<id>.intake.md, exclusive create; return the id."""
    body = (text or "").rstrip("\r\n")
    if not body.strip():
        raise Refused("an intake needs the client's words; the text is empty")
    tid = tid or spec.next_id(tickets_dir)
    if not _ID.match(tid):
        raise Refused(f'"{tid}" is not a four-digit id')
    if os.path.exists(os.path.join(tickets_dir, f"{tid}.md")):
        raise Refused(f"{tickets_dir}/{tid}.md exists: {tid} is a ticket")
    os.makedirs(tickets_dir, exist_ok=True)
    try:
        with open(intake_file(tickets_dir, tid), "x", encoding="utf-8", newline="") as fh:
            fh.write(body + "\n")
    except FileExistsError:
        raise Refused(f"{intake_file(tickets_dir, tid)} exists: another intake took {tid}") from None
    return tid


def first(text):
    """The interview's first user message: its replay key is the raw text alone (§2)."""
    return f"{FIRST}\n\n{text.strip()}\n"


# --- §2 the interview -------------------------------------------------------


def answers(doc):
    """The answered questions' answers, in order; the CAP-th carries LAST."""
    out = [q["answer"] for q in doc.get("questions") or [] if isinstance(q, dict) and q.get("answer")]
    if len(out) >= CAP:
        out[CAP - 1] = f"{out[CAP - 1]}\n\n{LAST}"
    return out


def _run(run_dir):
    run = load(os.path.join(run_dir, "out", "run.json"), {})
    return run if isinstance(run, dict) else {}


def _calls(run_dir):
    calls = load(os.path.join(run_dir, "out", "calls.json"), [])
    return [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []


def _last_line(path):
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [line for line in fh.read().splitlines() if line.strip()]
    except OSError:
        return ""
    return lines[-1] if lines else ""


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def proposed_ticket(args, n):
    """One propose_ticket call's arguments as a proposed ticket, or Refused."""
    title, problem = _text(args.get("title")), _text(args.get("problem"))
    raw = args.get("criteria")
    criteria = [" ".join(c.split()) for c in raw if isinstance(c, str) and c.strip()] if isinstance(raw, list) else []
    if not title:
        raise Refused(f"proposed ticket {n} has no title")
    if not problem:
        raise Refused(f'proposed ticket {n} ("{title[:40]}") has no problem')
    if not criteria:
        raise Refused(f'proposed ticket {n} ("{title[:40]}") has no criterion')
    return {"n": n, "title": title, "problem": problem, "criteria": criteria,
            "feature": _text(args.get("feature")) or None, "priority": _text(args.get("priority")) or None}


def interview(doc, run_dir, rc, env):
    """The interview/intake-answer step's result (docs/adr/0090 §2, §4)."""
    run = _run(run_dir)
    if rc != 0:
        why = _last_line(os.path.join(run_dir, "run.err")) or f"the product role exited {rc}"
        if env.get("AGENT_HARNESS") == "replay" and run.get("no_recording"):
            raise Refused("no recording of this intake's interview at L0 (fixtures/adk/product); record it at L1 "
                          f"with ./go intake ... ADK_RECORD=extend, then ./go resume TICKET={doc.get('id', '<id>')}")
        raise Refused(f"the product role failed: {why}", stopped("product", run))
    calls = [c for c in _calls(run_dir) if c.get("name") in DECISIONS]
    if not calls:
        raise Refused("the product role neither asked nor proposed")
    asks = [i for i, c in enumerate(calls) if c["name"] == "ask_product_owner"]
    after = calls[asks[-1] + 1:] if asks else calls
    proposed = [c for c in after if c["name"] == "propose_ticket"]
    product = dict(task(run), consulted=True)
    if any(c["name"] == "confirm_acceptance" for c in after):
        raise Refused("the product role confirmed one ticket's criteria instead of proposing tickets")
    if proposed:
        tickets = [proposed_ticket(c.get("args") or {}, n) for n, c in enumerate(proposed, 1)]
        return {"state": "drafted", "product": product, "proposal": tickets}
    question = _text((calls[-1].get("args") or {}).get("question"))
    if not question:
        raise Refused("the product role asked an empty question")
    questions = [q for q in doc.get("questions") or [] if isinstance(q, dict)]
    if len(questions) >= CAP:
        raise Refused(f"the product role asked question {len(questions) + 1}, past the cap of {CAP} (docs/adr/0090 §2)")
    questions.append({"question": question, "from": "product", "asked_at": now()})
    return {"state": "intake-questions", "questions": questions, "product": product}


# --- §3 the perimeter -------------------------------------------------------


def proposal_input(doc):
    """The architect's first message: the proposal, perimeter-free, as JSON."""
    items = [{"n": t.get("n"), "title": t.get("title"), "problem": t.get("problem"), "criteria": t.get("criteria")}
             for t in doc.get("proposal") or [] if isinstance(t, dict)]
    return json.dumps(items, indent=2, ensure_ascii=False) + "\n"


def compose(ticket, tid, intake_id):
    """The Markdown of a proposed ticket, the shape of every committed one (§5)."""
    head = ["- Status: open", f"- Intake: {intake_id}"]
    head += [f"- Feature: {ticket['feature']}"] if ticket.get("feature") else []
    head += [f"- Priority: {ticket['priority']}"] if ticket.get("priority") else []
    body = [f"# {tid} — {ticket.get('title') or ''}".rstrip(), ""] + head + [
        "", "## Problem", "", (ticket.get("problem") or "").strip(), "", spec.CRITERIA, ""]
    for c in ticket.get("criteria") or []:
        body += [c, ""]
    body += [spec.PERIMETER, ""] + [f"- `{p}`" for p in ticket.get("perimeter") or []]
    return "\n".join(body).rstrip("\n") + "\n"


def gate_line(markdown):
    """The one line gates/spec.sh prints for MARKDOWN, judged as a file."""
    with tempfile.TemporaryDirectory(prefix="lights-out-intake-") as tmp:
        path = os.path.join(tmp, "draft.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(markdown)
        g = subprocess.run(["sh", "gates/spec.sh", path], capture_output=True, text=True,  # nosec B603 B607
                           check=False, stdin=subprocess.DEVNULL)
    lines = g.stdout.strip().splitlines()
    return lines[-1] if lines else f"gates/spec.sh exit {g.returncode}"


def perimeter(doc, run_dir, rc, env, check=gate_line):
    """The perimeter step's result (docs/adr/0090 §3)."""
    run = _run(run_dir)
    paths = {}
    if rc != 0:
        why = _last_line(os.path.join(run_dir, "run.err")) or f"the architect role exited {rc}"
        if not (env.get("AGENT_HARNESS") == "replay" and run.get("no_recording")):
            raise Refused(f"the architect role failed: {why}", stopped("architect", run))
        architect = dict(task(run), consulted=False, why=why)
    else:
        for c in _calls(run_dir):
            if c.get("name") != "propose_perimeter":
                continue
            args = c.get("args") or {}
            try:
                n = int(args.get("ticket"))
            except (TypeError, ValueError):
                continue
            raw = args.get("paths")
            if isinstance(raw, list):
                paths[n] = [p.strip() for p in raw if isinstance(p, str) and p.strip()]
        architect = dict(task(run), consulted=True)
    out = []
    for t in doc.get("proposal") or []:
        if not isinstance(t, dict):
            continue
        t = dict(t, perimeter=paths.get(t.get("n"), []))
        t["check"] = check(compose(t, "draft", doc.get("id") or ""))
        out.append(t)
    if not out:
        raise Refused("the intake holds no proposed ticket")
    return {"state": "proposed", "architect": architect, "proposal": out}


# --- §5 the confirmation ----------------------------------------------------


def _edit(ticket, fields, n):
    if not isinstance(fields, dict) or set(fields) - set(EDITABLE):
        raise Refused(f"the edit of ticket {n} is not an object of {', '.join(EDITABLE)}")
    out = dict(ticket)
    for key, value in fields.items():
        if key in ("criteria", "perimeter"):
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise Refused(f"the edit of ticket {n}: {key} is not a list of strings")
            out[key] = [" ".join(v.split()) if key == "criteria" else v.strip() for v in value if v.strip()]
        elif value is None or isinstance(value, str):
            out[key] = (value or "").strip() or (None if key in ("feature", "priority") else "")
        else:
            raise Refused(f"the edit of ticket {n}: {key} is not a string")
    if not out.get("title"):
        raise Refused(f"the edit of ticket {n} leaves it without a title")
    return out


def decide(doc, decisions):
    """[(ticket, action)] for the intake's proposal, or Refused (§5)."""
    if doc.get("state") != "proposed":
        raise Refused(f"intake {doc.get('id')} is at {doc.get('state') or 'none'}, not proposed; nothing confirmed")
    proposal = [t for t in doc.get("proposal") or [] if isinstance(t, dict)]
    if not isinstance(decisions, list) or len(decisions) != len(proposal):
        raise Refused(f"DECISIONS must be a JSON list of {len(proposal)} entries, one per proposed ticket")
    out = []
    for t, d in zip(proposal, decisions):
        if d in ("confirm", "drop"):
            out.append((t, d))
        elif isinstance(d, dict) and set(d) == {"edit"}:
            out.append((_edit(t, d["edit"], t.get("n")), "edit"))
        else:
            raise Refused(f'ticket {t.get("n")}: "{json.dumps(d)[:40]}" is not "confirm", "drop" or {{"edit": {{...}}}}')
    return out


def parse_decisions(value):
    """DECISIONS as given: JSON text, or @<file>."""
    value = (value or "").strip()
    if value.startswith("@"):
        try:
            with open(value[1:], encoding="utf-8") as fh:
                value = fh.read()
        except OSError as exc:
            raise Refused(f"cannot read DECISIONS file {value[1:]}: {exc.strerror}") from None
    try:
        return json.loads(value)
    except ValueError:
        raise Refused("DECISIONS is not JSON: a list of \"confirm\", \"drop\" or {\"edit\": {...}}") from None


def write_ticket(ticket, intake_id, tickets_dir):
    """Write a kept ticket under the next free id, exclusive create; return the id."""
    tid = spec.next_id(tickets_dir)
    path = os.path.join(tickets_dir, f"{tid}.md")
    try:
        with open(path, "x", encoding="utf-8") as fh:
            fh.write(compose(ticket, tid, intake_id))
    except FileExistsError:
        raise Refused(f"{path} exists: another request took {tid}") from None
    return tid


# --- the command line -------------------------------------------------------


def write_step_files(env, why, run=None):
    """A refusal's reason to STEP_WHY (§6) and its stopped run to STEP_RUN (amendment A3)."""
    for var, body in (("STEP_WHY", why + "\n"), ("STEP_RUN", json.dumps(run) + "\n" if run else None)):
        if env.get(var) and body:
            try:
                with open(env[var], "w", encoding="utf-8") as fh:
                    fh.write(body)
            except OSError:
                pass


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def main(argv, env=None):
    env = os.environ if env is None else env
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    try:
        if cmd == "new" and len(args) in (2, 3):
            with open(args[0], encoding="utf-8", newline="") as fh:  # byte for byte (§1)
                text = fh.read()
            print(new(text, args[1], args[2] if len(args) == 3 else None))
        elif cmd == "first" and len(args) == 2:
            doc = load(args[0], {})
            sys.stdout.write(first(read(intake_file(args[1], doc.get("id") or ""))))
        elif cmd == "answers" and len(args) == 1:
            print(json.dumps(answers(load(args[0], {})), ensure_ascii=False))
        elif cmd == "interview" and len(args) == 3:
            print(json.dumps(interview(load(args[0], {}), args[1], int(args[2]), env), ensure_ascii=False))
        elif cmd == "proposal" and len(args) == 1:
            sys.stdout.write(proposal_input(load(args[0], {})))
        elif cmd == "perimeter" and len(args) == 3:
            print(json.dumps(perimeter(load(args[0], {}), args[1], int(args[2]), env), ensure_ascii=False))
        elif cmd == "compose" and len(args) == 3:
            sys.stdout.write(compose(load(args[0], {}), args[1], args[2]))
        else:
            print("usage: intake.py new <text> <tickets> [<id>] | first <doc> <tickets> | answers <doc>"
                  " | interview <doc> <run dir> <rc> | proposal <doc> | perimeter <doc> <run dir> <rc>"
                  " | compose <ticket.json> <id> <intake id>", file=sys.stderr)
            return 2
    except (Refused, OSError) as exc:
        line = f"intake: {exc}"
        print(line, file=sys.stderr)
        write_step_files(env, str(exc), getattr(exc, "run", None))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
