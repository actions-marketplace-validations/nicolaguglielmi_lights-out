"""How a repository customizes its agents (docs/adr/0073): stdlib only.

    python3 core/agents.py check SOURCE
    python3 core/agents.py instructions --role ROLE SOURCE [--part head|tail|json]
    python3 core/agents.py mcp --harness H --out DIR SOURCE [--adapters DIR]
    python3 core/agents.py calls --allow FILE --hooks FILE
    python3 core/agents.py lines SOURCE
    python3 core/agents.py gate SOURCE

and, for the two steps that read the contract at a commit, one call each:

    python3 core/agents.py crew --contract DIR --repo GIT --rev BASE --role ROLE
        --harness H --member M --out DIR [--adapters DIR]
    python3 core/agents.py review --contract DIR --repo GIT --base BASE --head HEAD
        --role ROLE --ticket FILE --out FILE

SOURCE is `--contract DIR`, the platform's local contract, or `--repo GIT
--rev SHA --prefix P`, the contract at one commit, P being its path inside
that repository ("" or ending in "/"). A commit is read through map.git,
never from a working tree (§2, §6): the base decides, not what a prepare
script or an earlier attempt left on disk. `crew` and `review` take the
local contract's directory only for its path inside its repository.

Two files shape the agents, both high risk (policy/merge.env):

    <P>roles/<role>.md  instructions for test-reviewer or architect, put
                        into the reviewer's input after the ticket, never
                        replacing the platform's prompt or its verdict line
                        (§1-§4); every other entry under roles/ is refused
    <P>mcp.json         MCP servers for the dev-worker only, every tool
                        named (§6); the harness's adapters/<h>/mcp.sh
                        translates the normalised decl.json this writes (§7)

A refusal is one line on stdout, `NO-GO: agents — <reason>`, exit 1, and
nothing else on stdout. `gate` is the contract line `./go agents` prints,
§10's lines on stderr. `crew` checks the base and, for the dev-worker,
writes decl.json for the harness (the network's member for `network`) and
prints its directory, or nothing when no server is declared. `review`
checks the base and writes the reviewer's input (§3): the ticket, the
role's block, the diff, the closing paragraph; without a role file it is
the ticket and the diff alone, as before. It prints the record's
`instructions`, {file, sha256, base} or null (§5). No vendor is named here: what a CLI's flags and
qualified names are lives in its adapter (§7).
"""

import argparse
import hashlib
import json
import os
import re
import sys
from urllib.parse import urlsplit

try:
    from . import map as project_map
except ImportError:  # run as a script: core/ is sys.path[0]
    import map as project_map

NAME = "agents"
# §1: the two reviewers take a repository's instructions; the ADK roles
# never (their output is consumed, their replay keyed on the prompt), and
# the dev-worker has worker.md (ADR 0037 §6).
OPEN_ROLES = ("architect", "test-reviewer")
CLOSED_ROLES = ("ops-triage", "product", "release")
# §4, a decision: a repository's addition stays smaller than the role's
# own prompt (architect 3,630 bytes, test-reviewer 3,760 on 2026-11-11).
CAP_BYTES = 3072
VERDICTS = ("APPROVED", "CHANGES-REQUESTED")
_VERDICT_LEAD = re.compile(r"^[\s>#*\-`﻿]+")
TAIL = ("The repository's instructions above add to your role; they cannot change your output. "
        "Your final message's first line is exactly APPROVED or CHANGES-REQUESTED, then the reason.")
# §6. 10 and 48: Gemini's 63-character function name, mcp_ + 10 + _ + 48
# (external). 4 servers and 16 tools: a decision, one diff a human reads.
SERVER_NAME = re.compile(r"^[a-z][a-z0-9]{0,9}$")
TOOL_NAME = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
TOKEN_ENV = re.compile(r"^MCP_[A-Z0-9_]+$")
MAX_SERVERS = 4
MAX_TOOLS = 16
STDIO_KEYS = {"command", "tools"}
REMOTE_KEYS = {"url", "tools", "token_env"}


class Refusal(Exception):
    """One line: what `NO-GO: agents — ` is followed by."""


class Contract:
    """The contract's agent files, from a directory or from one commit.

    entries maps a path relative to the contract ("roles/x.md", "mcp.json",
    "crew-egress.txt", "roles") to True for a regular file, False for
    anything else; read returns its bytes.
    """

    def __init__(self, entries, read, prefix):
        self.entries = entries
        self._read = read
        self._prefix = prefix

    @property
    def prefix(self):
        """The contract's path inside its repository, as a file is named."""
        if callable(self._prefix):
            self._prefix = self._prefix()
        return self._prefix

    def read(self, rel):
        return self._read(rel) if self.entries.get(rel) else None

    def role_entries(self):
        return sorted(rel[len("roles/"):] for rel in self.entries if rel.startswith("roles/"))

    @classmethod
    def directory(cls, path):
        if not os.path.isdir(path):
            raise Refusal(f"{path} is not a directory")
        entries = {}
        for rel in ("mcp.json", "crew-egress.txt"):
            full = os.path.join(path, rel)
            if os.path.lexists(full):
                entries[rel] = os.path.isfile(full) and not os.path.islink(full)
        roles = os.path.join(path, "roles")
        if os.path.lexists(roles):
            if not os.path.isdir(roles) or os.path.islink(roles):
                entries["roles"] = False
            else:
                for name in os.listdir(roles):
                    full = os.path.join(roles, name)
                    entries[f"roles/{name}"] = os.path.isfile(full) and not os.path.islink(full)

        def read(rel):
            with open(os.path.join(path, rel), "rb") as fh:
                return fh.read()

        def prefix():
            try:
                return project_map.git(path, "rev-parse", "--show-prefix").decode().strip()
            except project_map.Refused:
                return path.rstrip("/") + "/"
        return cls(entries, read, prefix)

    @classmethod
    def commit(cls, repo, rev, prefix):
        if prefix and not prefix.endswith("/"):
            raise Refusal(f"--prefix {prefix} must be empty or end in /")
        try:
            sha = project_map.git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").decode().strip()
        except project_map.Refused:
            raise Refusal(f"{rev} is not a commit of {repo}") from None
        listing = project_map.git(repo, "ls-tree", "-z", "--full-tree", sha, "--",
                                  f"{prefix}roles", f"{prefix}roles/", f"{prefix}mcp.json",
                                  f"{prefix}crew-egress.txt").decode()
        entries = {}
        for item in filter(None, listing.split("\0")):
            meta, path = item.split("\t", 1)
            mode, kind, _ = meta.split(" ")
            rel = path[len(prefix):]
            if rel == "roles" and kind == "tree":
                continue
            entries[rel] = kind == "blob" and mode in ("100644", "100755")

        def read(rel):
            return project_map.git(repo, "cat-file", "blob", f"{sha}:{prefix}{rel}")
        return cls(entries, read, prefix)


# --- role instructions (§1-§4) ---------------------------------------------

def _content(file, raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Refusal(f"{file}: not UTF-8 (ADR 0073 §4)") from None
    if len(raw) > CAP_BYTES:
        raise Refusal(f"{file}: {len(raw):,} bytes, over the cap of {CAP_BYTES:,} (ADR 0073 §4)")
    for line in text.splitlines():
        if _VERDICT_LEAD.sub("", line).startswith(VERDICTS):
            raise Refusal(f"{file}: a role file cannot write the verdict line")
    return text


def roles(contract):
    """{role: (file, bytes)} for the accepted role files; anything else refuses."""
    accepted = " and ".join(f"{r}.md" for r in reversed(OPEN_ROLES))
    if contract.entries.get("roles") is False:
        raise Refusal(f"{contract.prefix}roles: not a directory; it holds {accepted} only (ADR 0073 §1)")
    found = {}
    for name in contract.role_entries():
        file = f"{contract.prefix}roles/{name}"
        stem = name[:-3] if name.endswith(".md") else None
        if not contract.entries[f"roles/{name}"]:
            raise Refusal(f"{file}: not a file; roles/ holds {accepted} only (ADR 0073 §1)")
        if stem == "dev-worker":
            raise Refusal(f"{file}: the dev-worker's per-repository file is {contract.prefix}worker.md"
                          " (ADR 0037 §6); one role, one file (ADR 0073 §1)")
        if stem in CLOSED_ROLES:
            raise Refusal(f"{file}: the {stem} role takes no repository instructions (ADR 0073 §1)")
        if stem not in OPEN_ROLES:
            raise Refusal(f"{file}: not a role file; roles/ holds {accepted} only (ADR 0073 §1)")
        raw = contract.read(f"roles/{name}")
        _content(file, raw)
        found[stem] = (file, raw)
    return found


def instruction(contract, role):
    """(file, bytes) of ROLE's file, None without one; refuses as roles() does.

    A role that takes no instructions has no file roles() would accept, so
    it gets None as well, once the rest of roles/ is checked.
    """
    return roles(contract).get(role)


def head(role, file, raw):
    """§3's block: the platform's heading, then the file, ending in a newline."""
    text = raw.decode("utf-8")
    if not text.endswith("\n"):
        text += "\n"
    sha = hashlib.sha256(raw).hexdigest()
    return f"## This repository's instructions for the {role} ({file}, sha256 {sha[:12]})\n\n{text}"


# --- MCP servers (§6) --------------------------------------------------------

def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise Refusal(f"mcp.json: the key {key} appears twice")
        out[key] = value
    return out


def egress(contract):
    """The base's crew-egress.txt entries, comment lines aside (ADR 0046 §5)."""
    raw = contract.read("crew-egress.txt")
    if raw is None:
        return set()
    words = set()
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.lstrip().startswith("#"):
            words.update(w.lower() for w in line.split())
    return words


def _tools(name, tools):
    if not isinstance(tools, list) or not tools:
        raise Refusal(f"mcp.json server {name}: tools must be a non-empty list of tool names (ADR 0073 §6)")
    seen = {}
    for tool in tools:
        if not isinstance(tool, str) or not TOOL_NAME.match(tool):
            raise Refusal(f"mcp.json server {name}: tool {json.dumps(tool)} does not match "
                          f"{TOOL_NAME.pattern}; name each tool exactly, no wildcard (ADR 0073 §6)")
        if tool in seen.values():
            raise Refusal(f"mcp.json server {name}: tool {tool} is listed twice (ADR 0073 §6)")
        # Codex turns every character outside [A-Za-z0-9_] into _ (Verified).
        same = re.sub(r"[^A-Za-z0-9_]", "_", tool)
        if same in seen:
            raise Refusal(f"mcp.json server {name}: tools {seen[same]} and {tool} become the same name {same}"
                          " in a harness's naming (ADR 0073 §6)")
        seen[same] = tool
    return list(tools)


def _server(name, spec, allowed):
    if not isinstance(name, str) or not SERVER_NAME.match(name):
        raise Refusal(f"mcp.json server {json.dumps(name)}: a name matches {SERVER_NAME.pattern} (ADR 0073 §6)")
    if not isinstance(spec, dict):
        raise Refusal(f"mcp.json server {name}: not an object (ADR 0073 §6)")
    if "command" in spec and "url" in spec:
        raise Refusal(f"mcp.json server {name}: command or url, not both (ADR 0073 §6)")
    if "command" not in spec and "url" not in spec:
        raise Refusal(f"mcp.json server {name}: no command and no url (ADR 0073 §6)")
    keys = STDIO_KEYS if "command" in spec else REMOTE_KEYS
    unknown = sorted(set(spec) - keys)
    if unknown:
        raise Refusal(f"mcp.json server {name}: unknown key {unknown[0]}; a {'stdio' if keys is STDIO_KEYS else 'remote'}"
                      f" server has {', '.join(sorted(keys))} only (ADR 0073 §6)")
    tools = _tools(name, spec.get("tools"))
    if keys is STDIO_KEYS:
        command = spec["command"]
        if not isinstance(command, list) or not command or not all(isinstance(a, str) and a for a in command):
            raise Refusal(f"mcp.json server {name}: command must be a non-empty list of non-empty strings"
                          " (ADR 0073 §6)")
        return {"name": name, "transport": "stdio", "command": list(command), "tools": tools}
    url = spec["url"]
    if not isinstance(url, str):
        raise Refusal(f"mcp.json server {name}: url must be a string (ADR 0073 §6)")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise Refusal(f"mcp.json server {name}: {url} is not a url (ADR 0073 §6)") from None
    if parts.scheme != "https":
        raise Refusal(f"mcp.json server {name}: {url} is not https (ADR 0073 §6)")
    if not parts.hostname or port is None:
        raise Refusal(f"mcp.json server {name}: {url} names no explicit port (ADR 0073 §6)")
    if parts.username is not None or parts.password is not None:
        raise Refusal(f"mcp.json server {name}: {url} carries a credential; name it with token_env (ADR 0073 §6)")
    token_env = spec.get("token_env")
    if not isinstance(token_env, str) or not TOKEN_ENV.match(token_env):
        raise Refusal(f"mcp.json server {name}: token_env {json.dumps(token_env)} does not match"
                      f" {TOKEN_ENV.pattern} (ADR 0073 §6)")
    endpoint = f"{parts.hostname}:{port}"
    if endpoint.lower() not in allowed:
        raise Refusal(f"mcp.json server {name}: {endpoint} is not in crew-egress.txt (ADR 0046 §5)")
    return {"name": name, "transport": "http", "url": url, "endpoint": endpoint, "token_env": token_env,
            "tools": tools}


def servers(contract):
    """The declared servers, normalised and sorted by name; [] without mcp.json."""
    if contract.entries.get("mcp.json") is False:
        raise Refusal("mcp.json: not a file (ADR 0073 §6)")
    raw = contract.read("mcp.json")
    if raw is None:
        return []
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, ValueError) as exc:
        raise Refusal(f"mcp.json: not JSON: {str(exc).splitlines()[0]}") from None
    unknown = sorted(set(doc) - {"servers"}) if isinstance(doc, dict) else []
    if unknown:
        raise Refusal(f"mcp.json: unknown key {unknown[0]}; the file holds servers only (ADR 0073 §6)")
    if not isinstance(doc, dict) or not isinstance(doc.get("servers"), dict):
        raise Refusal('mcp.json: the file is one object, {"servers": {<name>: {...}}}, and nothing else'
                      " (ADR 0073 §6)")
    declared = doc["servers"]
    if not declared:
        raise Refusal("mcp.json declares no server; without servers there is no file (ADR 0073 §6)")
    if len(declared) > MAX_SERVERS:
        raise Refusal(f"mcp.json: {len(declared)} servers, over the limit of {MAX_SERVERS} (ADR 0073 §6)")
    allowed = egress(contract)
    out = [_server(name, declared[name], allowed) for name in sorted(declared)]
    total = sum(len(s["tools"]) for s in out)
    if total > MAX_TOOLS:
        raise Refusal(f"mcp.json: {total} tools, over the limit of {MAX_TOOLS} in all (ADR 0073 §6)")
    return out


def declaration(found):
    """decl.json: the servers and the sha256 of their canonical form."""
    canon = json.dumps(found, sort_keys=True, separators=(",", ":"))
    return {"sha256": hashlib.sha256(canon.encode()).hexdigest(), "servers": found}


def mcp_harnesses(adapters):
    """The harnesses that honour mcp.json: those with an mcp.sh (§7), discovered."""
    try:
        names = os.listdir(adapters)
    except OSError:
        return []
    return sorted(h for h in names if os.path.isfile(os.path.join(adapters, h, "mcp.sh")))


# --- what a run used, and what the contract declares (§9, §10) ---------------

def calls(allow_lines, hook_lines):
    """run.json's calls and denied, from the allow file and hooks.log: a named tool
    never called is not a call (servers[].tools says what was offered)."""
    allow = []
    for n, line in enumerate(allow_lines, 1):
        if not line.strip():
            continue
        words = line.split()
        if len(words) != 3:
            raise Refusal(f"allow line {n} is not `<qualified name> <server> <tool>`")
        allow.append(tuple(words))
    counts, denied = {}, {}
    names = {q for q, _, _ in allow}
    for line in hook_lines:
        words = line.split(" ", 2)
        if len(words) < 2:
            continue
        verdict, tool_name = words[0], words[1]
        if verdict == "ALLOW" and tool_name in names:
            counts[tool_name] = counts.get(tool_name, 0) + 1
        elif verdict == "DENY" and tool_name.startswith("mcp_"):
            denied[tool_name] = denied.get(tool_name, 0) + 1
    seen, out = set(), []
    for q, server, tool in allow:
        if q not in seen and counts.get(q):
            seen.add(q)
            out.append({"server": server, "tool": tool, "count": counts.get(q, 0)})
    return {"calls": out, "denied": [{"tool_name": t, "count": denied[t]} for t in sorted(denied)]}


def describe(contract):
    """§10's lines for a contract; refuses as check does."""
    found = roles(contract)
    declared = servers(contract)
    lines = [f"{role}: +{len(raw):,} bytes from {file}" for role, (file, raw) in sorted(found.items())]
    if not declared:
        lines.append("dev-worker MCP: none")
    for s in declared:
        if s["transport"] == "stdio":
            how = f"stdio: {' '.join(s['command'])}"
        else:
            how = f"remote: {s['url']}, token {s['token_env']}"
        lines.append(f"dev-worker MCP: {s['name']} ({how}) — tools {', '.join(s['tools'])}")
    return lines, found, declared


def contract_prefix(contract_dir):
    """The local contract's path inside its repository: where a commit holds it."""
    try:
        return project_map.git(contract_dir, "rev-parse", "--show-prefix").decode().strip()
    except project_map.Refused:
        raise Refusal(f"{contract_dir} is not inside a git repository") from None


def write_declaration(declared, harness, adapters, out):
    """decl.json in OUT for HARNESS, which must have an mcp.sh (§8)."""
    have = mcp_harnesses(adapters)
    if harness not in have:
        raise Refusal(f"{harness} cannot give the dev-worker MCP servers (ADR 0073 §8); "
                      f"use one of: {' '.join(have) or '(no adapters/<h>/mcp.sh found)'}")
    os.makedirs(out, exist_ok=True)
    tmp = os.path.join(out, "decl.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(declaration(declared), sort_keys=True, indent=2) + "\n")
    os.replace(tmp, os.path.join(out, "decl.json"))


def review_input(contract, role, repo, base, head_rev, ticket):
    """(input bytes, instructions record) for the reviewer (§3, §5)."""
    roles(contract)
    servers(contract)
    got = instruction(contract, role)
    parts = [ticket]
    if got is not None:
        parts += [b"\n---\n\n", head(role, *got).encode("utf-8")]
    parts += [b"\n---\n\nDiff:\n\n```diff\n", project_map.git(repo, "diff", f"{base}..{head_rev}"), b"```\n"]
    if got is not None:
        parts += [b"\n---\n\n", (TAIL + "\n").encode("utf-8")]
    record = None if got is None else {"file": got[0], "sha256": hashlib.sha256(got[1]).hexdigest(), "base": base}
    return b"".join(parts), record


def lines_for(contract_dir):
    """§10's lines for the platform's local contract: what the logbook reads."""
    return describe(Contract.directory(contract_dir))[0]


# --- the command line ----------------------------------------------------------

def _source(args):
    if args.contract is not None:
        if args.repo is not None or args.rev is not None or args.prefix is not None:
            raise Refusal("--contract, or --repo --rev --prefix, not both")
        return Contract.directory(args.contract)
    if args.repo is None or args.rev is None or args.prefix is None:
        raise Refusal("a source is --contract DIR, or --repo GIT --rev SHA --prefix P")
    return Contract.commit(args.repo, args.rev, args.prefix)


def _with_source(parser):
    parser.add_argument("--contract")
    parser.add_argument("--repo")
    parser.add_argument("--rev")
    parser.add_argument("--prefix")


def _read_lines(path, missing_ok):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except FileNotFoundError:
        if missing_ok:
            return []
        raise Refusal(f"{path} does not exist") from None


def run(args):
    if args.verb == "calls":
        # No hooks.log means no tool call reached the guard.
        found = calls(_read_lines(args.allow, False), _read_lines(args.hooks, True))
        print(json.dumps(found, sort_keys=True))
        return 0
    if args.verb == "crew":
        contract = Contract.commit(args.repo, args.rev, contract_prefix(args.contract))
        roles(contract)
        declared = servers(contract)
        if args.role == "dev-worker" and declared:
            write_declaration(declared, args.member if args.harness == "network" else args.harness,
                              args.adapters, args.out)
            print(args.out)
        return 0
    if args.verb == "review":
        contract = Contract.commit(args.repo, args.base, contract_prefix(args.contract))
        with open(args.ticket, "rb") as fh:
            text, record = review_input(contract, args.role, args.repo, args.base, args.head, fh.read())
        with open(args.out, "wb") as fh:
            fh.write(text)
        print(json.dumps(record))
        return 0
    contract = _source(args)
    if args.verb == "check":
        roles(contract)
        servers(contract)
    elif args.verb == "instructions":
        got = instruction(contract, args.role)
        if args.part == "json":
            print(json.dumps(None if got is None else {"file": got[0], "sha256": hashlib.sha256(got[1]).hexdigest()}))
        elif got is not None:
            sys.stdout.write(head(args.role, *got) if args.part == "head" else TAIL + "\n")
    elif args.verb == "mcp":
        declared = servers(contract)
        if declared:
            write_declaration(declared, args.harness, args.adapters, args.out)
    elif args.verb == "lines":
        for line in describe(contract)[0]:
            print(line)
    elif args.verb == "gate":
        lines, found, declared = describe(contract)
        for line in lines:
            print(line, file=sys.stderr)
        tools = sum(len(s["tools"]) for s in declared)
        print(f"GO: {NAME} — {len(found)} role files, {len(declared)} MCP servers, {tools} tools")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("check", "lines", "gate"):
        _with_source(verbs.add_parser(verb))
    p = verbs.add_parser("instructions")
    _with_source(p)
    p.add_argument("--role", required=True)
    p.add_argument("--part", choices=("head", "tail", "json"), default="head")
    p = verbs.add_parser("mcp")
    _with_source(p)
    p.add_argument("--harness", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--adapters", default="adapters")
    p = verbs.add_parser("crew")
    for flag in ("--contract", "--repo", "--rev", "--role", "--harness", "--member", "--out"):
        p.add_argument(flag, required=True)
    p.add_argument("--adapters", default="adapters")
    p = verbs.add_parser("review")
    for flag in ("--contract", "--repo", "--base", "--head", "--role", "--ticket", "--out"):
        p.add_argument(flag, required=True)
    p = verbs.add_parser("calls")
    p.add_argument("--allow", required=True)
    p.add_argument("--hooks", required=True)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Refusal as exc:
        reason = str(exc)
    except project_map.Refused as exc:
        reason = str(exc).splitlines()[0] if str(exc) else "git failed"
    except OSError as exc:
        reason = f"{exc.filename}: {exc.strerror}"
    print(f"NO-GO: {NAME} — {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
