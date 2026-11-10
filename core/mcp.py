"""`lights-out-gates mcp` (docs/adr/0069): a read-only MCP server over stdio.

    lights-out-gates mcp [--repo DIR] [--map FILE]

Standard library only, no model, no network, no plane. The client launches
it and talks newline-delimited JSON-RPC on stdin and stdout; stdout carries
nothing else, every log line goes to stderr, and end of input ends it.

Four tools, all read-only. Three ask the project map (docs/adr/0054) of the
repository at DIR (default: the working directory), FILE by default
`git rev-parse --git-path lights-out/map.sqlite` (inside .git, §6), opened
read-only at every call and refused unless it was built at HEAD:

    adrs_for_path     the ADRs and pages that cite a path: what governs it
    tests_for_path    the tests that cover a path
    tickets_for_path  the tickets whose perimeter or history touched a path

and one asks the spec gate (docs/adr/0055 §4): check_spec, on a draft's
text. A refusal the model can act on (no map, a stale map, a path the map
does not know, a spec that fails) is a tool result with isError; an unknown
tool or a malformed call is a JSON-RPC error.

Both eras of the protocol are served (§4): a request carrying the modern
per-request `_meta` is answered statelessly under 2026-07-28; an
`initialize` selects a legacy revision for the rest of the process.
"""

import json
import os
import posixpath
import sys

try:
    from . import map as project_map
    from . import spec
except ImportError:  # run as a script: core/ is sys.path[0]
    import map as project_map
    import spec

NAME = "lights-out"
MODERN = ("2026-07-28",)
LEGACY = ("2025-11-25",)
META = "io.modelcontextprotocol/"
INVALID_PARAMS, NOT_FOUND, PARSE, INVALID = -32602, -32601, -32700, -32600
UNSUPPORTED = -32022
INSTRUCTIONS = ("Read-only answers from the lights-out project map of this repository, built at HEAD with "
                "`lights-out-gates map` (a stale map is refused, never read): which ADRs govern a path, which "
                "tests cover it, which tickets touched it; and the spec gate on a draft.")

PATH_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["path"],
               "properties": {"path": {"type": "string",
                                       "description": "A path tracked at HEAD, relative to the repository root"}}}
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
TOOLS = [
    {"name": "adrs_for_path", "title": "ADRs that govern a path",
     "description": "The ADRs, and the pages, that cite this path or a directory of two segments or more "
                    "above it, from the project map at HEAD (docs/adr/0054).",
     "inputSchema": PATH_SCHEMA, "annotations": READ_ONLY},
    {"name": "tests_for_path", "title": "Tests that cover a path",
     "description": "The tests that import this path, or the path itself when it is a test, from the "
                    "project map at HEAD.",
     "inputSchema": PATH_SCHEMA, "annotations": READ_ONLY},
    {"name": "tickets_for_path", "title": "Tickets that touched a path",
     "description": "The tickets whose perimeter matches this path or whose commits changed it, from the "
                    "project map at HEAD.",
     "inputSchema": PATH_SCHEMA, "annotations": READ_ONLY},
    {"name": "check_spec", "title": "Check a spec draft",
     "description": "The spec gate on a draft: GO when every acceptance criterion has Given, When and Then "
                    "with an observable outcome and the perimeter declares a path; else NO-GO and the "
                    "first failure (docs/adr/0055 §4).",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["text"],
                     "properties": {"text": {"type": "string", "description": "The draft, Markdown"}}},
     "annotations": READ_ONLY},
]


class Refused(Exception):
    """A tool result with isError: one line the model can act on."""


class RpcError(Exception):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


def version():
    try:
        from importlib.metadata import version as installed
        return installed("lights-out-gates")
    except Exception:  # noqa: BLE001 - from a clone there is no metadata
        return "from a clone"


# --- the answers ---

REBUILD = "lights-out-gates map"


def git_line(repo, *args):
    """One line of git's output in REPO, through the map's one process call (docs/adr/0069 §7)."""
    try:
        return project_map.git(repo, *args).decode().strip()
    except (project_map.Refused, OSError):
        raise Refused(f"{repo} is not a git repository with a commit") from None


def default_map(repo):
    """The map inside .git, one per worktree (docs/adr/0069 §6)."""
    return os.path.join(repo, git_line(repo, "rev-parse", "--git-path", "lights-out/map.sqlite"))


def opened(repo, map_file):
    sha = git_line(repo, "rev-parse", "--verify", "HEAD^{commit}")
    try:
        return project_map.open_map(map_file or default_map(repo), sha, rebuild=REBUILD), sha
    except project_map.Refused as refused:
        raise Refused(str(refused)) from None


def known(db, sha, path):
    if not isinstance(path, str) or not path:
        raise RpcError(INVALID_PARAMS, "path must be a non-empty string")
    path = path.strip()
    clean = posixpath.normpath(path)
    if posixpath.isabs(path) or clean == ".." or clean.startswith("../"):
        raise Refused(f"{path} is outside the repository: give a path relative to its root")
    path = clean
    row = db.execute("SELECT kind FROM node WHERE name = ? AND kind IN ('file', 'test', 'adr', 'page')",
                     (path,)).fetchone()
    if row is None:
        raise Refused(f"{path} is not a tracked file at {sha}")
    return path, row[0]


def listed(items):
    return [f"- {i}" for i in items] or ["- none"]


def adrs_for_path(db, sha, path):
    path, _ = known(db, sha, path)
    found = project_map.covered(db, [path])
    adrs = sorted(n for (k, n) in found if k == "adr")
    pages = sorted(n for (k, n) in found if k == "page")
    return [f"{path} at {sha}:", "ADRs:", *listed(adrs), "Pages:", *listed(pages)]


def tests_for_path(db, sha, path):
    path, kind = known(db, sha, path)
    tests = {r[0] for r in db.execute(
        "SELECT t.name FROM edge e JOIN node t ON t.id = e.src JOIN node f ON f.id = e.dst "
        "WHERE e.kind = 'tests' AND f.name = ?", (path,))}
    if kind == "test":
        tests.add(path)
    tests = sorted(tests)
    return [f"{path} at {sha}:", "Tests:", *listed(tests)]


def tickets_for_path(db, sha, path):
    path, _ = known(db, sha, path)
    rows = db.execute(
        "SELECT t.name, t.title, group_concat(DISTINCT e.kind) FROM edge e JOIN node t ON t.id = e.src "
        "JOIN node f ON f.id = e.dst WHERE e.kind IN ('perimeter', 'history') AND f.name = ? "
        "GROUP BY t.name ORDER BY t.name", (path,)).fetchall()
    tickets = [f"{t if t.startswith(n) else f'{n} {t}'.strip()} ({','.join(sorted(k.split(',')))})"
               for n, t, k in rows]
    return [f"{path} at {sha}:", "Tickets:", *listed(tickets)]


def check_spec(text):
    if not isinstance(text, str):
        raise RpcError(INVALID_PARAMS, "text must be a string")
    why = spec.check(text)
    return [f"NO-GO: spec — {why}" if why else "GO: spec"]


MAP_TOOLS = {"adrs_for_path": adrs_for_path, "tests_for_path": tests_for_path, "tickets_for_path": tickets_for_path}


def call(name, arguments, repo, map_file):
    """The answer's lines for one tool call; Refused or RpcError otherwise."""
    if not isinstance(arguments, dict):
        raise RpcError(INVALID_PARAMS, "arguments must be an object")
    tool = next((t for t in TOOLS if t["name"] == name), None)
    if tool is None:
        raise RpcError(INVALID_PARAMS, f"Unknown tool: {name}")
    allowed = set(tool["inputSchema"]["properties"])
    extra = sorted(set(arguments) - allowed)
    missing = sorted(set(tool["inputSchema"]["required"]) - set(arguments))
    if extra or missing:
        raise RpcError(INVALID_PARAMS, f"{name} takes {', '.join(sorted(allowed))}"
                       + (f"; unknown: {', '.join(extra)}" if extra else "")
                       + (f"; missing: {', '.join(missing)}" if missing else ""))
    if name == "check_spec":
        return check_spec(arguments["text"])
    db, sha = opened(repo, map_file)
    try:
        return MAP_TOOLS[name](db, sha, arguments["path"])
    finally:
        db.close()


# --- the protocol ---

class Server:
    def __init__(self, repo, map_file):
        self.repo, self.map_file = repo, map_file
        self.legacy = None  # the revision `initialize` negotiated, for the rest of the process

    def info(self):
        return {"name": NAME, "version": version()}

    def handle(self, message):
        """The response to MESSAGE, or None for a notification."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return error(message.get("id") if isinstance(message, dict) else None, INVALID, "not a JSON-RPC 2.0 request")
        rid, method = message.get("id"), message["method"]
        if "id" not in message:
            return None
        params = message.get("params") or {}
        try:
            if not isinstance(params, dict):
                raise RpcError(INVALID_PARAMS, "params must be an object")
            if method == "initialize":
                return result(rid, self.initialize(params))
            modern = self.version_of(params)
            if method == "ping":
                body = {}
            elif method == "server/discover":
                body = {"supportedVersions": list(MODERN + LEGACY), "capabilities": {"tools": {}},
                        "instructions": INSTRUCTIONS}
            elif method == "tools/list":
                body = {"tools": TOOLS}
            elif method == "tools/call":
                body = self.tools_call(params)
            else:
                raise RpcError(NOT_FOUND, f"Method not found: {method}")
            if modern:
                body = {"resultType": "complete", **body, "_meta": {f"{META}serverInfo": self.info()}}
            return result(rid, body)
        except RpcError as exc:
            return error(rid, exc.code, exc.message, exc.data)

    def initialize(self, params):
        self.legacy = LEGACY[0]  # the one legacy revision served, whatever the client asked (§7)
        return {"protocolVersion": self.legacy, "capabilities": {"tools": {}}, "serverInfo": self.info(),
                "instructions": INSTRUCTIONS}

    def version_of(self, params):
        """True when the request is modern; raises when it is neither modern nor after initialize."""
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        asked = meta.get(f"{META}protocolVersion")
        if asked is None:
            if self.legacy:
                return False
            raise RpcError(INVALID_PARAMS, f"missing _meta {META}protocolVersion and no initialize before it; "
                                           f"supported: {', '.join(MODERN + LEGACY)}")
        if asked not in MODERN:
            raise RpcError(UNSUPPORTED, "Unsupported protocol version",
                           {"supported": list(MODERN + LEGACY), "requested": asked})
        if not isinstance(meta.get(f"{META}clientCapabilities"), dict):
            raise RpcError(INVALID_PARAMS, f"missing _meta {META}clientCapabilities")
        return True

    def tools_call(self, params):
        name = params.get("name")
        if not isinstance(name, str):
            raise RpcError(INVALID_PARAMS, "tools/call needs a tool name")
        try:
            lines = call(name, params.get("arguments", {}), self.repo, self.map_file)
        except Refused as refused:
            return {"content": [{"type": "text", "text": " ".join(str(refused).split())}], "isError": True}
        return {"content": [{"type": "text", "text": "\n".join(lines)}], "isError": False}


def result(rid, body):
    return {"jsonrpc": "2.0", "id": rid, "result": body}


def error(rid, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": err}


def serve(repo, map_file, stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    server = Server(repo, map_file)
    print(f"lights-out mcp: repository {repo}, map {map_file or 'inside .git'}, read-only", file=sys.stderr)
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply = error(None, PARSE, "Parse error")
        else:
            if isinstance(message, list):
                reply = error(None, INVALID, "batches are not served")
            else:
                reply = server.handle(message)
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0


def main(argv):
    repo, map_file = os.getcwd(), None
    args = list(argv)
    while args:
        flag = args.pop(0)
        if flag in ("--repo", "--map") and args:
            value = args.pop(0)
            if flag == "--repo":
                repo = value
            else:
                map_file = value
        else:
            print(f"lights-out mcp: unknown argument {flag}; usage: lights-out-gates mcp [--repo DIR] [--map FILE]",
                  file=sys.stderr)
            return 2
    repo = os.path.abspath(repo)
    return serve(repo, os.path.abspath(map_file) if map_file else None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
