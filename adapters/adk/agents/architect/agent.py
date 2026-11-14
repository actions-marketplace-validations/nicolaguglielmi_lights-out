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
# Provenance, decision: docs/adr/0090 amendment A4, ten queries of forty
# paths answer at most 400 paths, about half the 786 files the map held at
# 3924ebf, so one answer stays well under the map itself.
QUERIES_MAX = 10
KINDS = ("file", "test", "page", "adr")
# Provenance, decision: docs/adr/0090 second amendment A7, one search with
# every query the tickets need plus one to look again where a ticket found
# nothing; measured, ten searches without a proposal.
SEARCHES_MAX = 2
BUDGET_USED = {"error": f"search budget of {SEARCHES_MAX} used: propose now with propose_perimeter", "results": []}
_searches = 0


def reset_searches() -> None:
    """A new run's budget (one process is one run; tests reuse the module)."""
    global _searches
    _searches = 0


def in_scope(path: str, scope: str) -> bool:
    """Whether PATH is the workload's (amendment A6): under SCOPE, or SCOPE empty."""
    return not scope or path == scope or path.startswith(scope + "/")


def find_files(queries: list[str]) -> dict:
    """Search the project map once for every query you need, at most 10:
    for each, the paths of files, tests, pages and ADRs that contain it
    (case-insensitive), at most 40, sorted, and how many more matched.
    Put every directory, module and word the tickets need in one call: you
    have two searches in all, then you propose."""
    global _searches
    if _searches >= SEARCHES_MAX:
        return dict(BUDGET_USED)
    _searches += 1
    scope = os.environ.get("INTAKE_SCOPE", "").strip("/")
    path = os.environ.get("INTAKE_MAP", "")
    if not path or not os.path.isfile(path):
        return {"error": "no project map for this run", "results": []}
    if not isinstance(queries, list) or not queries or len(queries) > QUERIES_MAX:
        return {"error": f"give between 1 and {QUERIES_MAX} queries in one list", "results": []}
    db = sqlite3.connect(f"file:{quote(os.path.abspath(path))}?mode=ro", uri=True)
    results = []
    try:
        for query in queries:
            rows = db.execute(
                "SELECT name FROM node WHERE kind IN (?, ?, ?, ?) AND instr(lower(name), lower(?)) > 0 ORDER BY name",
                (*KINDS, str(query or "")),
            ).fetchall()
            paths = [r[0] for r in rows if in_scope(r[0], scope)]
            results.append({"query": query, "paths": paths[:FIND_MAX], "more": max(0, len(paths) - FIND_MAX)})
    finally:
        db.close()
    return {"results": results}


def propose_perimeter(ticket: int, paths: list[str]) -> dict:
    """Propose the perimeter of proposed ticket number TICKET: the paths, or
    globs, a developer may change to satisfy it, and nothing else."""
    return {"status": "recorded", "ticket": ticket, "paths": paths}


root_agent = build("architect", [find_files, propose_perimeter], prompt_file="perimeter.md")
