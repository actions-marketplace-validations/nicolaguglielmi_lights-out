"""The control plane's state machine (docs/adr/0019 §1, §2): stdlib only.

Vendor-free: it only calls the STATE_STORE and EVENT_BUS adapter verbs the
profile names, and the step scripts under $TOWER_STEPS. core/tower.sh is
its entry point (docs/adr/0052 §3); callers keep calling that.

    python3 core/tower.py open <ticket>          write the document at `opened`, publish `assign`
    python3 core/tower.py request <ticket>       write the document at `requested`, publish `clarify`
    python3 core/tower.py answer <ticket>        record ANSWER on the open question, publish `answer`
    python3 core/tower.py step <ticket> <step>   apply one step: precondition, effect, write, publish next
    python3 core/tower.py resume <ticket>        request again the step whose last attempt failed
    python3 core/tower.py task <run.json>        print the task fields a role's run leaves in the document

The document is plain JSON, one per ticket, id = ticket id. A step's
precondition is the state it starts from; an event whose precondition is
not the document's current state is dropped with one stderr line and exit
0 -- the idempotency rule, covering a duplicate event and a redelivery
after a slow step. A step script gets the document on $DOC_FILE (plus
TICKET, PR_NUMBER, BASE_SHA, HEAD_SHA) and prints a JSON object on stdout:
at least {"state": "<next>"}, plus the fields it recorded, deep-merged
into the document. A step that exits non-zero, prints no state, or whose
next event cannot be published leaves the state and every other field as
they were, appends one history entry {step, state, at, error: <why>}, and
exits 1: no retries, no timeouts of the tower's own (docs/adr/0034 §1).
`resume` requires that entry to be the last one and appends {step:
"resume", resumed: <step>} before publishing the step again (docs/adr/0034
§2). Every history entry carries the document's `attempt` once it has one
(docs/adr/0038 §9). All output is on stderr, one `[tower]` line each.

Before `opened` (docs/adr/0055 §1, §2): `request` starts a ticket at
`requested`, with who requested and through what (REQUEST_BY, default
`unauthenticated`; REQUEST_VIA, default `cli`; docs/adr/0059 §4); `questions` waits for a person, and `answer` writes the
person's ANSWER (ANSWER_BY, default `unauthenticated`; ANSWER_VIA, default
`cli`) on the last question, which must be unanswered, then requests the
`answer` step. A step result that carries `task` is also appended, with
the document's attempt, to `tasks` (§5): every attempt's run is kept.
"""

import json
import os
import subprocess  # nosec B404 - adapter verbs and steps are scripts (docs/adr/0052 §3)
import sys
import tempfile
from datetime import datetime, timezone

COLLECTION = "tickets"
USAGE = ("usage: tower.sh open <ticket> | request <ticket> | answer <ticket> | step <ticket> <step>"
         " | resume <ticket> | task <run.json>")

# The transition table. PRECONDITION: step -> the state it starts from.
# NEXT: state -> the step requested once the document is there; a state
# that is not a key is terminal. ci/board.sh checks the board against both.
PRECONDITION = {
    "clarify": "requested",
    "answer": "questions",
    "spec": "spec-ready",
    "assign": "opened",
    "ci": "pr-opened",
    "review": "review",
    "merge": "ci-passed",
    "mainline": "merged",
    "release": "main-green",
    "rework": "ci-failed",
}
NEXT = {
    "requested": "clarify",
    "spec-ready": "spec",
    "opened": "assign",
    "pr-opened": "ci",
    "review": "review",
    "ci-passed": "merge",
    "merged": "mainline",
    "main-green": "release",
    "ci-failed": "rework",
}
# Refused while main is red (docs/adr/0056 §5): the `mainline`/`main`
# document core/mainline.py keeps.
BLOCKED_BY_RED_MAIN = ("assign", "rework", "release")


# The task fields copied from a role's run.json (docs/adr/0047 §2, P1):
# who ran it and what it cost, as the harness reported it, or under replay
# as the recorded run did -- the rule `model` follows. A key the harness
# does not report is null, never a guess.
RUN_KEYS = ("model", "provider", "thinking", "turns", "tokens", "duration_s", "input_sha256")


def task(run):
    """{harness, replayed, model, provider, ...} from a run.json object."""
    recorded = run.get("recorded") if isinstance(run.get("recorded"), dict) else {}
    out = {"harness": text(run.get("harness")) or "unknown", "replayed": run.get("harness") == "replay"}
    for key in RUN_KEYS:
        value = run.get(key)
        if value is None or value is False:
            value = recorded.get(key)
        out[key] = None if value is False else value
    return out


class Refused(Exception):
    """One `[tower]` line on stderr and an exit code."""

    def __init__(self, line, code=1):
        super().__init__(line)
        self.line = line
        self.code = code


def text(value):
    """A field as `jq -r '<path> // empty'` prints it: null and false are absent."""
    if value is None or value is False:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def dig(doc, *keys):
    """doc[k1][k2]..., or None where any level is missing or not an object."""
    for key in keys:
        if not isinstance(doc, dict):
            return None
        doc = doc.get(key)
    return doc


def merge(left, right):
    """jq's `left * right`: objects merge recursively, anything else is replaced."""
    if not (isinstance(left, dict) and isinstance(right, dict)):
        return right
    out = dict(left)
    for key, value in right.items():
        out[key] = merge(out[key], value) if key in out else value
    return out


def attempt(doc):
    """{attempt: n} once the document has one (docs/adr/0038 §9), {} before."""
    value = doc.get("attempt")
    if value is None or value is False:
        return {}
    return {"attempt": value}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compact(doc):
    """The document as `jq -c` writes it."""
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def say(line):
    print(line, file=sys.stderr, flush=True)


def sh(script, *args, **kwargs):
    """Run SCRIPT with sh, an argument list and never a shell line: the one process call."""
    # The script is an adapter verb the profile names (docs/adr/0024) or a
    # TOWER_STEPS step; sh is the workbench's.
    return subprocess.run(["sh", script, *args], check=False, **kwargs)  # nosec B603 B607 - an argv list, no shell, ADR 0052 §3


class Tower:
    def __init__(self, ticket, env):
        self.ticket = ticket
        self.store_adapter = env["STATE_STORE"]
        self.bus = env["EVENT_BUS"]
        self.steps = env.get("TOWER_STEPS") or "core/steps"

    def store_get(self):
        """The document, or None when the store has none (get.sh exit non-zero)."""
        got = sh(f"adapters/{self.store_adapter}/get.sh", COLLECTION, self.ticket,
                 stdout=subprocess.PIPE, text=True)
        if got.returncode != 0:
            return None
        try:
            doc = json.loads(got.stdout)
        except ValueError:
            doc = None
        if not isinstance(doc, dict):
            raise Refused(f"[tower] {self.ticket}: the stored document is not a JSON object")
        return doc

    def store_put(self, doc):
        put = sh(f"adapters/{self.store_adapter}/put.sh", COLLECTION, self.ticket,
                 input=compact(doc) + "\n", text=True)
        return put.returncode == 0

    def publish(self, step):
        message = compact({"ticket": self.ticket, "step": step})
        return sh(f"adapters/{self.bus}/publish.sh", message).returncode == 0

    def red_main(self):
        """Why main is NO-GO (docs/adr/0056 §5), or "" when it is not red."""
        got = sh(f"adapters/{self.store_adapter}/get.sh", "mainline", "main",
                 stdout=subprocess.PIPE, text=True)
        try:
            main = json.loads(got.stdout) if got.returncode == 0 else {}
        except ValueError:
            main = {}
        if not isinstance(main, dict) or main.get("state") != "red":
            return ""
        return f"main is NO-GO since {text(main.get('green')) or 'unknown'}: {text(main.get('line'))}"

    def tell(self, line):
        say(f"[tower] {self.ticket}: {line}")

    def get(self):
        doc = self.store_get()
        if doc is None:
            raise Refused(f"[tower] {self.ticket}: no document; open the ticket first")
        return doc

    def record_failure(self, doc, step, state, why):
        """Append the failed attempt to doc's history and write it; the state does not move."""
        failed = dict(doc)
        failed["history"] = (doc.get("history") or []) + [
            {"step": step, "state": state, "at": now(), **attempt(doc), "error": why}]
        if not self.store_put(failed):
            self.tell(f"could not record the failed {step} either")
        self.tell(f"resume with ./go resume TICKET={self.ticket}")

    def open(self):
        doc = {"id": self.ticket, "state": "opened",
               "history": [{"step": "open", "state": "opened", "at": now()}]}
        if not self.store_put(doc):
            raise Refused(f"[tower] {self.ticket}: could not write the document")
        if not self.publish("assign"):
            raise Refused(f"[tower] {self.ticket}: could not publish assign")
        self.tell("opened, assign requested")

    def request(self, env):
        by, via = env.get("REQUEST_BY") or "unauthenticated", env.get("REQUEST_VIA") or "cli"
        doc = {"id": self.ticket, "state": "requested",
               "history": [{"step": "request", "state": "requested", "at": now(), "by": by, "via": via}]}
        if not self.store_put(doc):
            raise Refused(f"[tower] {self.ticket}: could not write the document")
        if not self.publish("clarify"):
            raise Refused(f"[tower] {self.ticket}: could not publish clarify")
        self.tell(f"requested by {by} via {via}, clarify requested")

    def answer(self, env):
        said = (env.get("ANSWER") or "").strip()
        if not said:
            raise Refused(f"[tower] {self.ticket}: no ANSWER; nothing recorded", 2)
        doc = self.get()
        have = text(doc.get("state")) or "none"
        questions = [dict(q) for q in doc.get("questions") or [] if isinstance(q, dict)]
        if have != "questions" or not questions or questions[-1].get("answer"):
            raise Refused(f"[tower] {self.ticket}: no open question (state {have}); nothing recorded")
        at = now()
        by, via = env.get("ANSWER_BY") or "unauthenticated", env.get("ANSWER_VIA") or "cli"
        questions[-1].update(answer=said, answered_by=by, answered_via=via, answered_at=at)
        doc = dict(doc, questions=questions, history=(doc.get("history") or []) + [
            {"step": "answered", "state": have, "at": at, "by": by, "via": via}])
        if not self.store_put(doc):
            raise Refused(f"[tower] {self.ticket}: could not record the answer; nothing requested")
        if not self.publish("answer"):
            self.tell("could not publish answer")
            self.record_failure(doc, "answer", have, "could not publish answer")
            raise Refused(None)
        self.tell(f"answered by {by} via {via}, answer requested")

    def step(self, step):
        want = PRECONDITION.get(step)
        if want is None:
            raise Refused(f'[tower] {self.ticket}: unknown step "{step}"', 2)
        doc = self.get()
        have = text(doc.get("state")) or "none"
        if have != want:
            self.tell(f"{step} already applied (state {have}), ignoring")
            return
        script = f"{self.steps}/{step}.sh"
        if not os.path.isfile(script):
            raise Refused(f"[tower] {self.ticket}: no {script}")
        red = self.red_main() if step in BLOCKED_BY_RED_MAIN else ""
        if red:
            self.tell(f"{step} refused: {red}; state stays {have}")
            self.record_failure(doc, step, have, red)
            raise Refused(None)

        self.tell(f"{step} (state {have})")
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as doc_file:
            doc_file.write(compact(doc) + "\n")
            doc_file.flush()
            env = dict(os.environ, TICKET=self.ticket, DOC_FILE=doc_file.name,
                       PR_NUMBER=text(dig(doc, "pr", "number")),
                       BASE_SHA=text(dig(doc, "pr", "base_sha")),
                       HEAD_SHA=text(dig(doc, "pr", "head_sha")))
            ran = sh(script, stdout=subprocess.PIPE, text=True, env=env)
        if ran.returncode != 0:
            rc = ran.returncode if ran.returncode > 0 else 128 - ran.returncode
            self.tell(f"step {step} failed; state stays {have}")
            self.record_failure(doc, step, have, f"step exited {rc}")
            raise Refused(None)
        try:
            result = json.loads(ran.stdout)
        except ValueError:
            result = None
        new_state = text(result.get("state")) if isinstance(result, dict) else ""
        if not new_state:
            self.tell(f"step {step} printed no state; state stays {have}")
            self.record_failure(doc, step, have, "step printed no state")
            raise Refused(None)

        updated = merge(doc, result)
        if isinstance(result.get("task"), dict):
            updated["tasks"] = (doc.get("tasks") or []) + [dict(result["task"], **attempt(updated))]
        updated["history"] = (updated.get("history") or []) + [
            {"step": step, "state": result["state"], "at": now(), **attempt(updated)}]
        if not self.store_put(updated):
            raise Refused(f"[tower] {self.ticket}: could not write the document after {step}")
        self.tell(f"{step} → {new_state}")

        following = NEXT.get(new_state)
        if following is None:
            self.tell(f"{new_state} is terminal, nothing requested")
        elif not self.publish(following):
            self.tell(f"could not publish {following}")
            self.record_failure(updated, following, new_state, f"could not publish {following}")
            raise Refused(None)

    def resume(self):
        doc = self.get()
        have = text(doc.get("state")) or "none"
        history = doc.get("history") or []
        last = history[-1] if history else {}
        why = text(dig(last, "error"))
        step = text(dig(last, "step"))
        if not why:
            raise Refused(f"[tower] {self.ticket}: not stranded: state {have}, last history entry "
                          f"{step or 'none'} did not fail; nothing to resume")
        if PRECONDITION.get(step) != have:
            raise Refused(f"[tower] {self.ticket}: the failed step {step} does not start from "
                          f"state {have}; not resuming")
        # Written before publishing: a step that starts at once (a job at L2)
        # must not have its write overwritten by this one. A failed publish
        # records itself, so the ticket stays resumable.
        doc = dict(doc, history=history + [
            {"step": "resume", "state": have, "at": now(), **attempt(doc), "resumed": step}])
        if not self.store_put(doc):
            raise Refused(f"[tower] {self.ticket}: could not record the resume; nothing requested")
        if not self.publish(step):
            self.tell(f"could not publish {step}")
            self.record_failure(doc, step, have, f"could not publish {step}")
            raise Refused(None)
        self.tell(f"{step} requested again (state {have}; last attempt: {why})")


def main(argv, env=None):
    env = os.environ if env is None else env
    if argv[:1] == ["task"] and len(argv) == 2:
        try:
            with open(argv[1], encoding="utf-8") as fh:
                print(compact(task(json.load(fh))))
        except (OSError, ValueError, AttributeError) as exc:
            say(f"tower: cannot read the run {argv[1]}: {exc}")
            return 1
        return 0
    for var in ("STATE_STORE", "EVENT_BUS"):
        if not env.get(var):
            say(f"tower: {var} not set; run this via ./go, not directly")
            return 2
    cmd = argv[0] if argv else ""
    ticket = argv[1] if len(argv) > 1 else ""
    if not cmd or not ticket or cmd not in ("open", "request", "answer", "step", "resume"):
        say(USAGE)
        return 2
    tower = Tower(ticket, env)
    try:
        if cmd == "open":
            tower.open()
        elif cmd == "request":
            tower.request(env)
        elif cmd == "answer":
            tower.answer(env)
        elif cmd == "step":
            tower.step(argv[2] if len(argv) > 2 else "")
        else:
            tower.resume()
    except Refused as refused:
        if refused.line:
            say(refused.line)
        return refused.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
