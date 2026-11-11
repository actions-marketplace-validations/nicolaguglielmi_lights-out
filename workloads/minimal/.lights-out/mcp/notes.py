#!/usr/bin/env python3
"""The fixture MCP server of docs/adr/0073 (case 10 of gates/harness-conformance.sh).

A stdio server, standard library only: newline-delimited JSON-RPC on stdin and
stdout, nothing else on stdout and nothing at all on stderr; end of input ends
it. Two read-only tools:

    search_notes(q)  answers "notes-hit:<q>:<cwd>", cwd being where it runs
    count_notes()    answers "notes-count-canary"

mcp.json names only search_notes, so count_notes is the tool a harness must
hide or deny: its answer must never reach a model.

Both eras of the protocol are served, as core/mcp.py serves them (Claude Code
2.1.311 spoke 2026-07-28 in ADR 0069's proof; the other two CLIs are not
established): a request carrying the modern per-request `_meta` is answered
statelessly under 2026-07-28; `initialize` selects a legacy revision for the
rest of the process, the one the client asked for when it is known.
"""

import json
import os
import sys

NAME = "notes"
VERSION = "1"
MODERN = ("2026-07-28",)
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
META = "io.modelcontextprotocol/"
PARSE, INVALID, NOT_FOUND, INVALID_PARAMS, UNSUPPORTED = -32700, -32600, -32601, -32602, -32022

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
TOOLS = [
    {"name": "search_notes", "title": "Search the notes",
     "description": "Search this repository's notes for a query.",
     "inputSchema": {"type": "object", "required": ["q"],
                     "properties": {"q": {"type": "string", "description": "What to search for"}}},
     "annotations": READ_ONLY},
    {"name": "count_notes", "title": "Count the notes",
     "description": "How many notes this repository has.",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": READ_ONLY},
]


class RpcError(Exception):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


def answer(name, arguments):
    if not isinstance(arguments, dict):
        raise RpcError(INVALID_PARAMS, "arguments must be an object")
    if name == "search_notes":
        q = arguments.get("q")
        if not isinstance(q, str):
            raise RpcError(INVALID_PARAMS, "search_notes takes q, a string")
        return "notes-hit:%s:%s" % (q, os.getcwd())
    if name == "count_notes":
        return "notes-count-canary"
    raise RpcError(INVALID_PARAMS, "Unknown tool: %s" % name)


class Server:
    def __init__(self):
        self.legacy = None  # the revision `initialize` negotiated, for the rest of the process

    def handle(self, message):
        """The response to MESSAGE, or None for a notification."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return error(message.get("id") if isinstance(message, dict) else None, INVALID, "not a JSON-RPC 2.0 request")
        if "id" not in message:
            return None
        rid, method = message["id"], message["method"]
        params = message.get("params") or {}
        try:
            if not isinstance(params, dict):
                raise RpcError(INVALID_PARAMS, "params must be an object")
            if method == "initialize":
                asked = params.get("protocolVersion")
                self.legacy = asked if asked in LEGACY else LEGACY[0]
                return result(rid, {"protocolVersion": self.legacy, "capabilities": {"tools": {}},
                                    "serverInfo": {"name": NAME, "version": VERSION}})
            modern = self.modern(params)
            if method == "ping":
                body = {}
            elif method == "server/discover":
                body = {"supportedVersions": list(MODERN + LEGACY), "capabilities": {"tools": {}}}
            elif method == "tools/list":
                body = {"tools": TOOLS}
            elif method == "tools/call":
                text = answer(params.get("name"), params.get("arguments", {}))
                body = {"content": [{"type": "text", "text": text}], "isError": False}
            else:
                raise RpcError(NOT_FOUND, "Method not found: %s" % method)
            if modern:
                body = dict({"resultType": "complete"}, **body,
                            _meta={META + "serverInfo": {"name": NAME, "version": VERSION}})
            return result(rid, body)
        except RpcError as exc:
            return error(rid, exc.code, exc.message, exc.data)

    def modern(self, params):
        """True when the request is modern; raises when it is neither modern nor after initialize."""
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        asked = meta.get(META + "protocolVersion")
        if asked is None:
            if self.legacy:
                return False
            raise RpcError(INVALID_PARAMS, "missing _meta %sprotocolVersion and no initialize before it" % META)
        if asked not in MODERN:
            raise RpcError(UNSUPPORTED, "Unsupported protocol version",
                           {"supported": list(MODERN + LEGACY), "requested": asked})
        return True


def result(rid, body):
    return {"jsonrpc": "2.0", "id": rid, "result": body}


def error(rid, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": err}


def main():
    server = Server()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply = error(None, PARSE, "Parse error")
        else:
            reply = error(None, INVALID, "batches are not served") if isinstance(message, list) else server.handle(message)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
