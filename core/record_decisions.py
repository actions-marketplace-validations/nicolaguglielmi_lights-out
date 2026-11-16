"""Record the decisions L0 replays (docs/adr/0091 §5, §8), live, at L1:
`./go record-decisions PROFILE=l1`. Stdlib only; every call goes through
core/decide.py and core/screen.py, as the steps make them.

Recorded into fixtures/decide/ (DECIDE_RECORD=1, DECIDE from the profile):
  - the screen of each text of fixtures/screen/labelled.json;
  - the screen of fixtures/intake/request.md and of tickets/0001.md, the
    demo intake's words and the demo ticket's body;
  - the demo intake's perimeter asked file by file: the proposal the
    architect's recording holds (fixtures/adk/architect/), the questions
    over the workload's map at HEAD.

With MEASURE=<n> (the M58 comparison, nothing recorded): each of those
requests is asked again n times on DECIDE, and once on DECIDE_COMPARE when
it is set (e.g. structured), and one line per call is appended to
.crew/m58/measure.jsonl: what, adapter, answers, tokens, seconds. With
MEASURE_SEARCH=1 the architect also proposes the demo intake's perimeter
once by search (docs/adr/0090 §3), live and unrecorded, for the same log.
"""

import glob
import json
import os
import subprocess  # nosec B404 - core/*.py and core/map.py, argv lists
import sys
import tempfile
import time

LABELLED = "fixtures/screen/labelled.json"
TEXTS = ("fixtures/intake/request.md", "tickets/0001.md")
ARCHITECT = "fixtures/adk/architect"
OUT = ".crew/m58/measure.jsonl"


def py(args, stdin=None, env=None):
    r = subprocess.run([sys.executable] + args, input=stdin, capture_output=True, text=True,  # nosec B603
                       check=False, env=env or dict(os.environ))
    return r.returncode, r.stdout, r.stderr.strip().splitlines()[-1:] or [""]


def screens(tmp):
    """(name, request) for every text the screen is recorded on."""
    sys.path.insert(0, "core")
    import screen  # the same request the step makes

    out = []
    with open(LABELLED, encoding="utf-8") as fh:
        for sample in json.load(fh):
            path = os.path.join(tmp, sample["id"] + ".txt")
            with open(path, "w", encoding="utf-8", newline="") as fh2:
                # As an intake file holds it (docs/adr/0090 §1): one final newline.
                fh2.write(sample["text"].rstrip("\r\n") + "\n")
            out.append((f"screen:{sample['id']}", path))
    out += [(f"screen:{p}", p) for p in TEXTS]
    return [(name, screen.request(open(p, "rb").read().decode("utf-8", errors="replace"))) for name, p in out]


def perimeter(tmp):
    """(name, request) of the demo intake's perimeter, asked file by file."""
    recs = sorted(glob.glob(os.path.join(ARCHITECT, "*.json")))
    if len(recs) != 1:
        raise SystemExit(f"record-decisions: want one recording in {ARCHITECT}, found {len(recs)}")
    with open(recs[0], encoding="utf-8") as fh:
        proposal = json.loads(json.load(fh)["input"])
    doc = os.path.join(tmp, "doc.json")
    with open(doc, "w", encoding="utf-8") as fh:
        json.dump({"id": "demo", "proposal": proposal}, fh)
    targets, smap = os.path.join(tmp, "targets"), os.path.join(tmp, "map.sqlite")
    open(targets, "w").close()
    rc, _, err = py(["core/map.py", "build", "--repo", ".", "--targets", targets, "--out", smap])
    if rc:
        raise SystemExit(f"record-decisions: the map: {err[0]}")
    rc, out, err = py(["core/intake.py", "perimeter-request", doc, smap, "app"])
    if rc:
        raise SystemExit(f"record-decisions: the perimeter request: {err[0]}")
    req = json.loads(out)
    with open(os.path.join(tmp, "input.json"), "w", encoding="utf-8") as fh:
        fh.write(req["input"])
    return [("perimeter:demo-intake", req)]


def search(tmp):
    """The architect's search path on the same proposal, live, unrecorded."""
    out = os.path.join(tmp, "search")
    env = dict(os.environ, ROLE="architect", INPUT=os.path.join(tmp, "input.json"), OUT=out, THINKING="high",
               INTAKE_MAP=os.path.join(tmp, "map.sqlite"), INTAKE_SCOPE="app", TIMEOUT_S="900")
    env.pop("ADK_RECORD", None)
    began = time.time()
    r = subprocess.run(["sh", "adapters/adk/run.sh"], capture_output=True, text=True, check=False, env=env)  # nosec B603 B607
    secs = round(time.time() - began, 3)
    run = json.load(open(os.path.join(out, "run.json"))) if os.path.isfile(os.path.join(out, "run.json")) else {}
    calls = json.load(open(os.path.join(out, "calls.json"))) if os.path.isfile(os.path.join(out, "calls.json")) else []
    return {"what": "perimeter:demo-intake", "adapter": "search", "run": 0, "rc": r.returncode,
            "error": (r.stderr.strip().splitlines() or [None])[-1] if r.returncode else None,
            "calls": calls, "tokens": run.get("tokens"), "turns": run.get("turns"), "model": run.get("model"),
            "seconds": secs}


def ask(req, env):
    began = time.time()
    rc, out, err = py(["core/decide.py", "ask"], json.dumps(req), env)
    return rc, (json.loads(out) if rc == 0 else None), err[0], round(time.time() - began, 3)


def main():
    if os.environ.get("DECIDE", "replay") == "replay":
        print("NO-GO: record-decisions — recording a replay is circular; PROFILE=l1")
        return 1
    measure = int(os.environ.get("MEASURE") or 0)
    with tempfile.TemporaryDirectory(prefix="lights-out-decisions-") as tmp:
        work = screens(tmp) + perimeter(tmp)
        failed = []
        if not measure:
            env = dict(os.environ, DECIDE_RECORD="1")
            for name, req in work:
                rc, _, line, secs = ask(req, env)
                print(f"[record-decisions] {name}: {'recorded' if rc == 0 else line} ({secs} s)", file=sys.stderr)
                if rc:
                    failed.append(name)
        else:
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            runs = [(os.environ["DECIDE"], n) for n in range(measure)]
            if os.environ.get("DECIDE_COMPARE"):
                runs.append((os.environ["DECIDE_COMPARE"], 0))
            with open(OUT, "a", encoding="utf-8") as log:
                for adapter, n in runs:
                    env = dict(os.environ, DECIDE=adapter)
                    env.pop("DECIDE_RECORD", None)
                    for name, req in work:
                        rc, ans, line, secs = ask(req, env)
                        log.write(json.dumps({"what": name, "adapter": adapter, "run": n, "rc": rc, "error": line if rc else None,
                                              "answers": (ans or {}).get("answers"), "tokens": (ans or {}).get("tokens"),
                                              "model": (ans or {}).get("model"), "seconds": secs}) + "\n")
                        log.flush()
                        print(f"[record-decisions] measure {adapter} #{n} {name}: rc {rc} ({secs} s)", file=sys.stderr)
                        if rc:
                            failed.append(f"{adapter}:{name}")
                if os.environ.get("MEASURE_SEARCH") == "1":
                    got = search(tmp)
                    log.write(json.dumps(got) + "\n")
                    print(f"[record-decisions] measure search: rc {got['rc']} ({got['seconds']} s)", file=sys.stderr)
                    if got["rc"]:
                        failed.append("search")
    if failed:
        print(f"NO-GO: record-decisions — {len(failed)} failed: {', '.join(failed[:5])}")
        return 1
    print(f"GO: record-decisions — {len(work)} requests" + (f", measured {OUT}" if measure else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
