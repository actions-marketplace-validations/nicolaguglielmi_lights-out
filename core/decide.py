"""The Decide port (docs/adr/0091 §1, §5): closed questions over one text,
stdlib only. No provider is named here: the adapter is `adapters/$DECIDE`.

    python3 core/decide.py ask             request on stdin, answer on stdout
    python3 core/decide.py check <request> answer on stdin; exit 0 if it
                                           meets the port's contract

`ask` checks the request, runs the adapter (or, with DECIDE=replay, reads
the recording), checks the answer and prints it. Exit 1 with one stderr
line on a refusal or a failure; exit 3 with one line when DECIDE=replay has
no recording, which the callers tell apart (§5). DECIDE_RECORD=1 writes a
live answer to DECIDE_FIXTURES (default fixtures/decide) under the sha256 of
the canonical request.
"""

import hashlib
import json
import math
import os
import re
import subprocess  # nosec B404 - the adapter's verb, an argv list
import sys
import time
from datetime import datetime, timezone

FIXTURES = "fixtures/decide"
# Provenance, external: the Decisions API's limits (docs/adr/0091 Context),
# taken by the port so every adapter has the same bound (§1).
MAX_QUESTIONS = 1000
MIN_OPTIONS, MAX_OPTIONS = 2, 255
KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TYPES = ("yes_no", "choice", "score")
# The arithmetic tolerance of the contract's sums and formulas (§1).
EPS = 0.001
NO_RECORDING = 3


class Refused(Exception):
    pass


class NotRecorded(Exception):
    pass


def canonical(request):
    return json.dumps(request, sort_keys=True, indent=2)


def key_for(request):
    return hashlib.sha256(canonical(request).encode()).hexdigest()


def check_request(req):
    """The request's questions, or Refused naming what is wrong (§1)."""
    if not isinstance(req, dict):
        raise Refused("the request is not a JSON object")
    text = req.get("input")
    if not isinstance(text, str) or not text.strip():
        raise Refused("the request has no input text")
    qs = req.get("questions")
    if not isinstance(qs, dict) or not qs:
        raise Refused("the request has no questions")
    if len(qs) > MAX_QUESTIONS:
        raise Refused(f"the request has {len(qs)} questions, over the port's {MAX_QUESTIONS}")
    for k, q in qs.items():
        if not KEY.match(k):
            raise Refused(f'question key "{k[:70]}" is not [A-Za-z0-9_-]{{1,64}}')
        if not isinstance(q, dict) or q.get("type") not in TYPES:
            raise Refused(f"question {k}: type is not one of {', '.join(TYPES)}")
        if not isinstance(q.get("instructions"), str) or not q["instructions"].strip():
            raise Refused(f"question {k} has no instructions")
        crit = q.get("criteria")
        if q["type"] == "yes_no":
            if crit is not None and not (isinstance(crit, dict) and set(crit) <= {"true", "false"}
                                         and all(isinstance(v, str) for v in crit.values())):
                raise Refused(f"question {k}: yes_no criteria are an object of true and false descriptions")
        elif q["type"] == "choice":
            if not (isinstance(crit, dict) and all(isinstance(v, str) for v in crit.values())):
                raise Refused(f"question {k}: choice criteria are an object of option descriptions")
            if not MIN_OPTIONS <= len(crit) <= MAX_OPTIONS:
                raise Refused(f"question {k}: {len(crit)} options, not {MIN_OPTIONS} to {MAX_OPTIONS}")
        else:
            if not (isinstance(crit, list) and all(isinstance(v, str) for v in crit)):
                raise Refused(f"question {k}: score criteria are a list of level descriptions")
            if not MIN_OPTIONS <= len(crit) <= MAX_OPTIONS:
                raise Refused(f"question {k}: {len(crit)} levels, not {MIN_OPTIONS} to {MAX_OPTIONS}")
    return qs


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _dist(k, probs, ids):
    if not isinstance(probs, dict) or set(probs) != set(ids):
        raise Refused(f"answer {k}: probabilities are not over exactly its {len(ids)} options")
    if not all(_num(p) and 0 <= p <= 1 for p in probs.values()):
        raise Refused(f"answer {k}: a probability is outside [0, 1]")
    if abs(sum(probs.values()) - 1) > EPS:
        raise Refused(f"answer {k}: probabilities sum to {sum(probs.values()):.4f}, not 1")
    return max(probs.values())


def check_answer(req, ans):
    """None, or Refused naming the first rule ANS breaks for REQ (§1)."""
    qs = check_request(req)
    got = ans.get("answers") if isinstance(ans, dict) else None
    if not isinstance(got, dict):
        raise Refused("the answer has no answers object")
    if set(got) != set(qs):
        missing, extra = sorted(set(qs) - set(got)), sorted(set(got) - set(qs))
        raise Refused(f"answers do not match the questions: missing {missing[:3]}, extra {extra[:3]}")
    for k, q in qs.items():
        a = got[k]
        if not isinstance(a, dict) or a.get("type") != q["type"]:
            raise Refused(f"answer {k} is not of type {q['type']}")
        c = a.get("confidence")
        if not _num(c):
            raise Refused(f"answer {k} has no confidence")
        if q["type"] == "yes_no":
            p = a.get("p_yes")
            if not (_num(p) and 0.01 - 1e-9 <= p <= 0.99 + 1e-9):
                raise Refused(f"answer {k}: p_yes is not in [0.01, 0.99]")
            want = max(p, 1 - p)
        elif q["type"] == "choice":
            want = _dist(k, a.get("probabilities"), list(q["criteria"]))
            if a.get("choice") not in q["criteria"] or a["probabilities"][a["choice"]] < want - EPS:
                raise Refused(f"answer {k}: the choice is not the most probable option")
        else:
            levels = [str(i) for i in range(len(q["criteria"]))]
            want = _dist(k, a.get("probabilities"), levels)
            mean = sum(int(i) * a["probabilities"][i] for i in levels)
            if not _num(a.get("score")) or abs(a["score"] - mean) > EPS:
                raise Refused(f"answer {k}: score is not the probability-weighted level")
        if abs(c - want) > EPS:
            raise Refused(f"answer {k}: confidence {c} is not the winning outcome's probability {want:.4f}")


def fixtures_dir(env):
    return env.get("DECIDE_FIXTURES") or FIXTURES


def replay(req, env):
    key = key_for(req)
    path = os.path.join(fixtures_dir(env), f"{key}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
    except OSError:
        raise NotRecorded(f"no recording of this decision at L0 ({path}); record it at L1 with DECIDE_RECORD=1") from None
    except ValueError:
        raise Refused(f"the recording {path} is not JSON") from None
    held = rec.get("answer") if isinstance(rec, dict) else None
    if not isinstance(held, dict):
        raise Refused(f"the recording {path} holds no answer")
    # A replay never claims what it did not spend (docs/adr/0040 §3).
    return {"answers": held.get("answers"), "adapter": "replay", "replayed": True, "provider": None,
            "model": None, "tokens": {"input": 0, "output": 0}, "duration_s": 0,
            "recorded": {k: held.get(k) for k in ("adapter", "provider", "model", "tokens")}}


def live(req, env):
    name = env.get("DECIDE") or ""
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", name):
        raise Refused(f"DECIDE={name!r} names no adapter; set it in the profile (docs/adr/0091 §1)")
    verb = os.path.join("adapters", name, "decide.sh")
    if not os.path.isfile(verb):
        raise Refused(f"DECIDE={name}: no {verb}")
    began = time.time()
    run = subprocess.run(["sh", verb], input=json.dumps(req), capture_output=True, text=True,  # nosec B603 B607
                         check=False, env=dict(env))
    if run.returncode != 0:
        lines = [x for x in run.stderr.splitlines() if x.strip()]
        raise Refused(f"DECIDE={name}: " + (lines[-1] if lines else f"exit {run.returncode}"))
    try:
        ans = json.loads(run.stdout)
    except ValueError:
        raise Refused(f"DECIDE={name} printed no JSON answer") from None
    if not isinstance(ans, dict):
        raise Refused(f"DECIDE={name} printed no JSON answer")
    ans.setdefault("adapter", name)
    ans.setdefault("duration_s", round(time.time() - began, 3))
    return ans


def record(req, ans, env):
    path = os.path.join(fixtures_dir(env), f"{key_for(req)}.json")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    body = {"request": req, "answer": ans,
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(body, indent=2, sort_keys=True) + "\n")


def ask(req, env=None):
    """The checked answer to REQ; Refused, or NotRecorded at L0 (§5)."""
    env = os.environ if env is None else env
    check_request(req)
    if env.get("DECIDE") == "replay":
        ans = replay(req, env)
    else:
        ans = live(req, env)
    try:
        check_answer(req, ans)
    except Refused as exc:
        raise Refused(f"DECIDE={env.get('DECIDE')}: the answer breaks the port's contract: {exc}") from None
    if env.get("DECIDE_RECORD") == "1" and env.get("DECIDE") != "replay":
        record(req, ans, env)
    return ans


def main(argv):
    cmd = argv[0] if argv else ""
    try:
        if cmd == "ask" and len(argv) == 1:
            req = json.loads(sys.stdin.read())
            print(json.dumps(ask(req), sort_keys=True))
        elif cmd == "check" and len(argv) == 2:
            with open(argv[1], encoding="utf-8") as fh:
                req = json.load(fh)
            check_answer(req, json.loads(sys.stdin.read()))
        else:
            print("usage: decide.py ask < request | check <request file> < answer", file=sys.stderr)
            return 2
    except NotRecorded as exc:
        print(f"decide: {exc}", file=sys.stderr)
        return NO_RECORDING
    except (Refused, OSError, ValueError) as exc:
        print(f"decide: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
