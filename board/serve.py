#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""board: the flight readiness board, served (docs/adr/0035).

    GET /            board/index.html; its explainer needs nothing else
    GET /state.json  what the plane says now

Read-only. /state.json is built from the same port verbs the tower and
launchpad call (the profile's STATE_STORE get, FLAGS evaluate, DELIVERY
status) and from the release record on disk; it never calls put, set,
shift or rollback. A probe that cannot read answers {"ok": false,
"error": <the adapter's own last stderr line>}, never a default value.
One background loop refreshes the snapshot every BOARD_POLL_S seconds, so
any number of open tabs cost the plane one probe round.

BOARD_STATIC=1 serves the page alone, for hosting the explainer where no
plane runs (board/Dockerfile, Cloud Run): no probe ever starts and
/state.json answers 404, which the page reads as "no live view here".
"""
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "board" / "index.html"
# Provenance, decision: the page polls every 2 s and a probe round takes
# about 1 s with the plane up (two `compose exec` in status.sh); 2 s keeps
# a canary shift visible within one beat of a stage without a busy loop.
POLL_S = float(os.environ.get("BOARD_POLL_S", "2"))
STATIC = os.environ.get("BOARD_STATIC") == "1"


def run(*argv, timeout=15):
    """(returncode, stdout, last stderr line) of argv run from the repo root."""
    try:
        p = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"
    lines = p.stderr.strip().splitlines()
    return p.returncode, p.stdout.strip(), lines[-1] if lines else f"exit {p.returncode}"


def adapter(port, verb):
    name = os.environ.get(port, "")
    if not name:
        return None
    return f"adapters/{name}/{verb}.sh"


def ticket_meta(path):
    """Title and declared perimeter of tickets/<id>.md (core/perimeter.sh's section)."""
    title, perimeter, inside = path.stem, [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# ") and title == path.stem:
            title = line[2:].strip()
        elif line.startswith("## Perimeter"):
            inside = True
        elif inside and line.startswith("## "):
            break
        elif inside and line.lstrip().startswith("- "):
            perimeter.append(line.lstrip()[2:].strip().strip("`").split("`")[0])
    return title, perimeter


def probe_tickets():
    get = adapter("STATE_STORE", "get")
    if get is None:
        return {"ok": False, "error": "STATE_STORE not set; run via ./go board"}
    out = []
    for path in sorted((ROOT / "tickets").glob("*.md")):
        rc, stdout, err = run("sh", get, "tickets", path.stem)
        if rc == 1:
            continue  # absent: the tower never opened this ticket
        if rc != 0:
            return {"ok": False, "error": err}
        try:
            doc = json.loads(stdout)
        except ValueError:
            return {"ok": False, "error": f"{get} printed no JSON for {path.stem}"}
        title, perimeter = ticket_meta(path)
        out.append({"id": path.stem, "title": title, "perimeter": perimeter, "doc": doc})
    return {"ok": True, "value": out}


def probe_flag(flag, version=""):
    evaluate = adapter("FLAGS", "evaluate")
    if evaluate is None:
        return {"ok": False, "error": "FLAGS not set; run via ./go board"}
    rc, stdout, err = run("sh", evaluate, flag, *([version] if version else []))
    return {"ok": True, "value": stdout} if rc == 0 else {"ok": False, "error": err}


def probe_delivery():
    status = adapter("DELIVERY", "status")
    if status is None:
        return {"ok": False, "error": "DELIVERY not set; run via ./go board"}
    rc, stdout, err = run("sh", status)
    if rc != 0:
        return {"ok": False, "error": err}
    try:
        return {"ok": True, "value": json.loads(stdout)}
    except ValueError:
        return {"ok": False, "error": f"{status} printed no JSON"}


def probe_file(path):
    p = ROOT / path
    if not p.is_file():
        return {"ok": False, "error": f"no {path} yet"}
    stat = p.stat()
    text = p.read_text(encoding="utf-8")
    try:
        value = json.loads(text) if path.endswith(".json") else text
    except ValueError:
        return {"ok": False, "error": f"{path} is not JSON"}
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime))
    return {"ok": True, "value": value, "at": at}


def snapshot():
    delivery = probe_delivery()
    kill = os.environ.get("WORKLOAD_KILL_SWITCH", "")
    canary = (delivery.get("value") or {}).get("canary") if delivery["ok"] else None
    stable = (delivery.get("value") or {}).get("stable") if delivery["ok"] else None
    return {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": os.environ.get("LEVEL", ""),
        "workload": os.environ.get("WORKLOAD", ""),
        "adapters": {p: os.environ.get(p, "") for p in (
            "STATE_STORE", "EVENT_BUS", "CODE_HOST", "DELIVERY", "METRICS", "FLAGS", "REGISTRY", "AGENT_HARNESS")},
        "tickets": probe_tickets(),
        "delivery": delivery,
        "freeze": probe_flag("release-freeze"),
        "kill_switch": {
            "flag": kill,
            "canary": probe_flag(kill, canary) if kill and canary else None,
            "stable": probe_flag(kill, stable) if kill and stable else None,
        },
        "record": probe_file(os.environ.get("RELEASE_RECORD", ".crew/release.json")),
        "brief": probe_file(os.environ.get("PROMOTE_OUT", ".crew/promote") + "/brief.md"),
    }


state = {"snapshot": None}


def refresh():
    while True:
        try:
            state["snapshot"] = snapshot()
        except Exception as exc:  # the board must keep serving its explainer
            state["snapshot"] = {"error": f"board: snapshot failed: {exc}"}
        time.sleep(POLL_S)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            body, kind = PAGE.read_bytes(), "text/html; charset=utf-8"
        elif path == "/state.json" and not STATIC:
            snap = state["snapshot"] or {"error": "board: first probe round still running"}
            body, kind = json.dumps(snap).encode(), "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    # Cloud Run names the port in PORT; ./go board publishes 8099.
    listen = int(os.environ.get("BOARD_LISTEN") or os.environ.get("PORT") or "8099")
    shown = os.environ.get("BOARD_PORT", str(listen))
    if not STATIC:
        threading.Thread(target=refresh, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", listen), Handler)
    print(f"board: http://localhost:{shown}  ({'explainer only' if STATIC else 'read-only'}; Ctrl-C to stop)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
