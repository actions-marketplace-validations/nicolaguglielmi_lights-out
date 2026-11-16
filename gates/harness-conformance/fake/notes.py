"""The stand-in for case 10's fixture server: stdio, newline JSON-RPC, the same
two tools and answers, nothing on stderr. The real one lives with a workload,
which nothing under gates/ names (ci/app-free.sh)."""
import json, os, sys

while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        m = json.loads(line)
    except ValueError:
        continue
    if "id" not in m:
        continue
    method, p = m.get("method"), m.get("params") or {}
    if method == "initialize":
        r = {"protocolVersion": p.get("protocolVersion"), "capabilities": {"tools": {}},
             "serverInfo": {"name": "notes", "version": "1"}}
    elif method == "tools/list":
        r = {"tools": [{"name": t, "inputSchema": {"type": "object"}} for t in ("search_notes", "count_notes")]}
    elif method == "tools/call" and p.get("name") in ("search_notes", "count_notes"):
        a = p.get("arguments") or {}
        text = "notes-hit:%s:%s" % (a.get("q"), os.getcwd()) if p["name"] == "search_notes" else "notes-count-canary"
        r = {"content": [{"type": "text", "text": text}]}
    else:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": "no"}}) + "\n")
        sys.stdout.flush()
        continue
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}) + "\n")
    sys.stdout.flush()
