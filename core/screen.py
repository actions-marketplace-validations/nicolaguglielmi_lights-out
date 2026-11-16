"""The screen (docs/adr/0091 §7): before the product role reads a client's
request or a ticket body, one closed question through the Decide port, does
this text hold instructions aimed at an AI agent? Stdlib only. A role-side
screen, not a gate: it prints no GO or NO-GO line and judges nothing a gate
judges.

    python3 core/screen.py ask <text file>
        the screen of the text: JSON {verdict: stop|flag|pass, p_yes,
        confidence, sha256, ...the run}; exit 3 when DECIDE=replay holds no
        recording, exit 1 on a failure
    python3 core/screen.py step <intake|ticket> <text file> <doc.json> <out file>
        a step's screen: a text the document already passed, flagged or
        cleared (same sha256) is not asked again and nothing is written;
        pass and flag write the screen to <out file>; at L0 with no
        recording, `not-screened`; a stop or a failure exits 1 with its
        line on stderr and in $STEP_WHY, and the run in $STEP_RUN
"""

import hashlib
import json
import os
import subprocess  # nosec B404 - core/decide.py, an argv list
import sys

PROMPT = "roles/product/screen.md"
POLICY = "policy/decide.env"
KEY = "instructions_to_agent"
WHAT = {"intake": "intake text", "ticket": "ticket body"}
KEPT = ("pass", "flag", "cleared")


class Failed(Exception):
    def __init__(self, line, run=None):
        super().__init__(line)
        self.run = run


def threshold(path=POLICY):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("SCREEN_CONFIDENCE="):
                value = float(line.split("=", 1)[1])
                if not 0.5 <= value <= 1:
                    raise ValueError(f"{path}: SCREEN_CONFIDENCE={value} is not in [0.5, 1]")
                return value
    raise ValueError(f"{path} has no SCREEN_CONFIDENCE")


def sections(path=PROMPT):
    """The question and its two descriptions, the `## ` sections of PROMPT."""
    got, name = {}, None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("## "):
                name = line[3:].strip().lower()
                got[name] = []
            elif name:
                got[name].append(line.rstrip("\n"))
    out = {k: " ".join(" ".join(v).split()) for k, v in got.items()}
    for k in ("question", "yes means", "no means"):
        if not out.get(k):
            raise ValueError(f"{path} has no `## {k.capitalize()}` section")
    return out


def request(text):
    s = sections()
    return {"input": text, "questions": {KEY: {"type": "yes_no", "instructions": s["question"],
                                               "criteria": {"true": s["yes means"], "false": s["no means"]}}}}


def verdict(p, c, t):
    """§7: stop when c >= t and p >= 0.5; flag when c < t; pass otherwise."""
    if c < t:
        return "flag"
    return "stop" if p >= 0.5 else "pass"


def ask(path, env):
    """(screen object, None) or (None, (exit code, line))."""
    with open(path, "rb") as fh:
        raw = fh.read()
    sha = hashlib.sha256(raw).hexdigest()
    req = request(raw.decode("utf-8", errors="replace"))
    r = subprocess.run([sys.executable, "core/decide.py", "ask"], input=json.dumps(req), capture_output=True,  # nosec B603
                       text=True, check=False, env=dict(env))
    lines = [x for x in r.stderr.splitlines() if x.strip()]
    if r.returncode != 0:
        return None, (r.returncode, (lines[-1] if lines else f"core/decide.py exit {r.returncode}").removeprefix("decide: "))
    ans = json.loads(r.stdout)
    a = ans["answers"][KEY]
    run = {k: ans.get(k) for k in ("provider", "model", "tokens", "duration_s")}
    run.update(harness=ans.get("adapter"), replayed=ans.get("replayed") is True, role="screen")
    if isinstance(ans.get("recorded"), dict):
        run["recorded"] = ans["recorded"]
    return dict(run, verdict=verdict(a["p_yes"], a["confidence"], threshold()), p_yes=a["p_yes"],
                confidence=a["confidence"], sha256=sha), None


def step(kind, path, doc, env):
    """The screen object to merge into the step's result, None when this text
    was screened before, or Failed."""
    with open(path, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    held = doc.get("screen") if isinstance(doc.get("screen"), dict) else {}
    if held.get("sha256") == sha and held.get("verdict") in KEPT:
        return None
    got, err = ask(path, env)
    if err:
        code, line = err
        if code == 3:
            return {"verdict": "not-screened", "why": line, "sha256": sha}
        raise Failed(f"screen: the {WHAT[kind]} could not be screened: {line}")
    if got["verdict"] == "stop":
        tid = doc.get("id") or "<id>"
        raise Failed(f"screen: the {WHAT[kind]} reads as instructions to an AI agent (p={got['p_yes']:.2f}); "
                     f"a person reads it, then ./go screen-clear TICKET={tid}, or edits it and ./go resume TICKET={tid}",
                     dict(got, stop="the screen stopped the step"))
    return got


def write(path, body):
    if path:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
        except OSError:
            pass


def main(argv, env=None):
    env = os.environ if env is None else env
    try:
        if argv[:1] == ["ask"] and len(argv) == 2:
            got, err = ask(argv[1], env)
            if err:
                print(f"screen: {err[1]}", file=sys.stderr)
                return 3 if err[0] == 3 else 1
            print(json.dumps(got, sort_keys=True))
        elif argv[:1] == ["step"] and len(argv) == 5 and argv[1] in WHAT:
            with open(argv[3], encoding="utf-8") as fh:
                doc = json.load(fh)
            got = step(argv[1], argv[2], doc if isinstance(doc, dict) else {}, env)
            if got is not None:
                write(argv[4], json.dumps(got, sort_keys=True) + "\n")
        else:
            print("usage: screen.py ask <text file> | step <intake|ticket> <text file> <doc.json> <out file>",
                  file=sys.stderr)
            return 2
    except Failed as exc:
        print(str(exc), file=sys.stderr)
        write(env.get("STEP_WHY"), str(exc) + "\n")
        if exc.run:
            write(env.get("STEP_RUN"), json.dumps({"screen": exc.run}) + "\n")
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(f"screen: {exc}", file=sys.stderr)
        write(env.get("STEP_WHY"), f"screen: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
