"""The architect role's intake task (docs/adr/0090 §3): proposes each
proposed ticket's perimeter from the project map. Its review of a diff
runs on a coding harness (docs/adr/0021); this is a conversation over the
map, the shape of the ADK roles (docs/adr/0020 §1). The map is
INTAKE_MAP, a core/map.py file the perimeter step builds, read through
find_files and never sent in the message: the replay key stays the
proposal."""

import os
import sqlite3
from urllib.parse import quote

from lights_out_adk.agent import build

# Provenance, decision: docs/adr/0090 §3, enough paths for one query to
# show a directory's files without filling the conversation with the map.
FIND_MAX = 40
KINDS = ("file", "test", "page", "adr")


def find_files(query: str) -> dict:
    """Search the project map for paths containing QUERY (case-insensitive):
    files, tests, pages and ADRs, at most 40, sorted. Use a directory, a
    module or a word of the ticket, then narrow it."""
    path = os.environ.get("INTAKE_MAP", "")
    if not path or not os.path.isfile(path):
        return {"error": "no project map for this run", "paths": []}
    db = sqlite3.connect(f"file:{quote(os.path.abspath(path))}?mode=ro", uri=True)
    try:
        rows = db.execute(
            "SELECT name FROM node WHERE kind IN (?, ?, ?, ?) AND instr(lower(name), lower(?)) > 0 ORDER BY name",
            (*KINDS, query or ""),
        ).fetchall()
    finally:
        db.close()
    paths = [r[0] for r in rows]
    return {"paths": paths[:FIND_MAX], "more": max(0, len(paths) - FIND_MAX)}


def propose_perimeter(ticket: int, paths: list[str]) -> dict:
    """Propose the perimeter of proposed ticket number TICKET: the paths, or
    globs, a developer may change to satisfy it, and nothing else."""
    return {"status": "recorded", "ticket": ticket, "paths": paths}


root_agent = build("architect", [find_files, propose_perimeter], prompt_file="perimeter.md")
