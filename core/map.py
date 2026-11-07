"""The project map (docs/adr/0054): stdlib only, no model, no service.

    python3 core/map.py build --repo DIR [--rev REV] [--tickets DIR] [--targets FILE] [--exclude GLOBS] --out FILE
    python3 core/map.py slice --map FILE --base SHA --ticket FILE
    python3 core/map.py drift --repo DIR [--targets FILE] [--tickets DIR] [--exclude GLOBS] [--known NAME]...
    python3 core/map.py after-merge --clone-url URL --merge-sha SHA [--tickets DIR] [--targets FILE]
                                    [--exclude GLOBS] --out FILE

GLOBS is one space-separated list. Without --targets, the ./go targets are
what `make help` lists in the current directory.

`build` reads one commit of a git repository, never its working tree, and
writes a SQLite file from scratch: the same commit gives the same rows. The
file carries the commit's sha; `slice` refuses a map whose sha is not the
base it is asked about (ADR 0054 §2). `drift` reads the working tree, as a
self-check does, and prints one line per citation that names nothing.
`after-merge` is the merge step's half (§4): clone, build at the merge,
and file one docs ticket through the Tracker when the merge touched paths
a page or an ADR cites. Every refusal is one line on stderr and exit 1.
"""

import argparse
import ast
import fnmatch
import json
import os
import posixpath
import re
import sqlite3
import subprocess  # nosec B404 - git and make: tower.py's sh() runs scripts only (docs/adr/0054 §6)
import sys
import tempfile

try:
    from core.tower import sh
except ImportError:  # run as a script: core/ is sys.path[0]
    from tower import sh

SCHEMA = "1"
SHA = re.compile(r"^[0-9a-f]{40}$")
ADR = re.compile(r"(^|/)adrs?/\d{4}-[^/]*\.md$")
TICKET_ID = re.compile(r"^(\d+)\.md$")
TEST = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|[^/]*\.(test|spec)\.[cm]?js)$")
JS = re.compile(r"\.[cm]?js$")
HISTORY = re.compile(r"\bticket[ /](\d{4})\b", re.IGNORECASE)
# Citations (§3): a link target, a backticked path, a ./go or make target,
# a backticked KEY= assignment.
LINK = re.compile(r"\]\(([^)\s]+)\)")
TICK = re.compile(r"`([^`\n]+)`")
COMMAND = re.compile(r"(?:^|[\s`(])(\./go|make) ([a-z][a-z0-9-]*)")
KEY = re.compile(r"(?<![A-Za-z0-9_$.-])([A-Z][A-Z0-9_]*[A-Z0-9])=")
WORD = re.compile(r"[A-Z][A-Z0-9_]*[A-Z0-9]")
NOT_A_PATH = re.compile(r"[<>${}=@\s|;\"'…]|\.\.\.|://|^[-/~:]|^\./go$")
JS_SYMBOL = re.compile(
    r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?"
    r"(?:function\s*\*?\s*([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)"
    r"|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=)"
    r"|^(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=")
JS_IMPORT = re.compile(r"""(?:require\s*\(\s*|import\s*\(\s*|from\s+|^\s*import\s+)['"](\.{1,2}/[^'"]+)['"]""",
                       re.MULTILINE)


class Refused(Exception):
    """One line on stderr, exit 1."""


def run(argv, data=None, ok=(0,)):
    """Run ARGV, never a shell line: the one process call; stdout as bytes."""
    done = subprocess.run(argv, input=data, capture_output=True, check=False)  # nosec B603 - an argv list, no shell, ADR 0052 §3
    if done.returncode not in ok:
        raise Refused(f"{' '.join(argv[:3])} failed: {done.stderr.decode(errors='replace').strip()}")
    return done.stdout


def git(repo, *args, data=None, ok=(0,)):
    return run(["git", "-C", repo, *args], data=data, ok=ok)  # nosec B607 - the workbench's git


class Tree:
    """The tracked paths of one commit, or of a working tree, and their text."""

    def __init__(self, paths, read):
        self.paths = sorted(set(paths))
        self.files = set(self.paths)
        self.dirs = {posixpath.dirname(p) for p in self.paths}
        for d in list(self.dirs):
            while d:
                d = posixpath.dirname(d)
                self.dirs.add(d)
        self.dirs.discard("")
        self.top = {d for d in self.dirs if "/" not in d}
        self._read = read
        self._text = {}

    def text(self, path):
        if path not in self._text:
            self._text[path] = self._read(path)
        return self._text[path]

    def exists(self, path):
        return path in self.files or path in self.dirs

    def ends(self, path):
        tail = f"/{path}"
        return any(p.endswith(tail) for p in self.files) or any(d.endswith(tail) for d in self.dirs)

    @classmethod
    def at(cls, repo, rev):
        listing = git(repo, "ls-tree", "-r", "-z", "--name-only", rev).decode()
        paths = [p for p in listing.split("\0") if p]
        blobs = _cat(repo, rev, paths)
        return cls(paths, blobs.get)

    @classmethod
    def worktree(cls, repo):
        listing = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard").decode()
        paths = [p for p in listing.split("\0") if p and os.path.isfile(os.path.join(repo, p))]

        def read(path):
            with open(os.path.join(repo, path), "rb") as handle:
                return _decode(handle.read())
        return cls(paths, read)


def _decode(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _cat(repo, rev, paths):
    """{path: text or None for a binary}, every blob of REV in one git call."""
    if not paths:
        return {}
    out = git(repo, "cat-file", "--batch", data="".join(f"{rev}:{p}\n" for p in paths).encode())
    blobs, at = {}, 0
    for path in paths:
        end = out.index(b"\n", at)
        header = out[at:end].split()
        if len(header) < 3 or header[1] != b"blob":
            at = end + 1
            blobs[path] = None
            continue
        size = int(header[2])
        blobs[path] = _decode(out[end + 1:end + 1 + size])
        at = end + 1 + size + 1
    return blobs


# --- what a path is (ADR 0054 §1) ---

def kind_of(path, tickets):
    if path.endswith(".md"):
        if ADR.search(path):
            return "adr"
        if posixpath.dirname(path) == tickets and TICKET_ID.match(posixpath.basename(path)):
            return "ticket"
        if "fixtures" not in path.split("/"):
            return "page"
    if TEST.search(path):
        return "test"
    return "file"


def title_of(text):
    for line in (text or "").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def perimeter(text):
    """The globs of a ticket's `## Perimeter` list (docs/adr/0021 §5), backticks removed."""
    globs, inside = [], False
    for line in (text or "").splitlines():
        if line.startswith("## Perimeter"):
            inside = True
        elif inside and line.startswith("## "):
            break
        elif inside and line.startswith("- "):
            globs.append(line[2:].strip().replace("`", ""))
    return globs


def features(text):
    """The `feature:<name>` labels of a ticket's `- Labels:` line: declared, never guessed."""
    for line in (text or "").splitlines():
        if line.startswith("- Labels:"):
            labels = [label.strip() for label in line[len("- Labels:"):].split(",")]
            return sorted({label[len("feature:"):] for label in labels
                           if label.startswith("feature:") and len(label) > len("feature:")})
    return []


# --- code (§1): ast for Python, a line parser for JS ---

def py_symbols(text):
    try:
        tree = ast.parse(text or "")
    except (SyntaxError, ValueError):
        return []
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        if isinstance(node, ast.ClassDef):
            names.extend(f"{node.name}.{item.name}" for item in node.body
                         if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return names


def py_imports(path, text, tree):
    try:
        parsed = ast.parse(text or "")
    except (SyntaxError, ValueError):
        return []
    found = []
    here = posixpath.dirname(path)
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found += _py_module(alias.name, here, 0, tree)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            found += _py_module(module, here, node.level, tree)
            for alias in node.names:
                found += _py_module(f"{module}.{alias.name}" if module else alias.name, here, node.level, tree)
    return found


def _py_module(module, here, level, tree):
    """The file MODULE names, searched from the importer's directory up to the root."""
    rel = module.replace(".", "/")
    if level:
        roots = [here]
        for _ in range(level - 1):
            roots = [posixpath.dirname(roots[0])]
    else:
        roots, d = [here], here
        while d:
            d = posixpath.dirname(d)
            roots.append(d)
    for root in roots:
        base = posixpath.join(root, rel) if rel else root
        for candidate in (f"{base}.py", posixpath.join(base, "__init__.py")):
            if candidate in tree.files:
                return [candidate]
    return []


def js_symbols(text):
    names = []
    for line in (text or "").splitlines():
        match = JS_SYMBOL.match(line)
        if match:
            names.append(next(group for group in match.groups() if group))
    return names


def js_imports(path, text, tree):
    found = []
    for spec in JS_IMPORT.findall(text or ""):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
        for candidate in (base, f"{base}.js", f"{base}.mjs", f"{base}.cjs", posixpath.join(base, "index.js")):
            if candidate in tree.files:
                found.append(candidate)
                break
    return found


# --- citations (§3) ---

def cited_path(token, page, tree):
    """The repository path a backticked TOKEN names, or None when it names none."""
    token = token.strip().strip("()").rstrip(".,;:")
    token = re.sub(r":\d+(-\d+)?$", "", token)
    if "/" not in token or NOT_A_PATH.search(token):
        return None
    if token.startswith("./"):
        token = token[2:]
    here = posixpath.dirname(page)
    first = token.split("/", 1)[0]
    if first in tree.top:
        return token.rstrip("/")
    if token.startswith("../") or (here and tree.exists(posixpath.join(here, first))):
        return posixpath.normpath(posixpath.join(here, token)).rstrip("/")
    return None


def link_path(target, page):
    """The repository path a Markdown link names, or None for a URL or an anchor."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
        return None
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    target = re.sub(r":\d+(-\d+)?$", "", target)
    return posixpath.normpath(posixpath.join(posixpath.dirname(page), target)).rstrip("/")


def path_ok(path, tree):
    """PATH exists, or ends an existing path: `.lights-out/worker.md` names a workload's contract file."""
    if path.startswith("../") or path == "..":
        return False
    if any(c in path for c in "*?["):
        return any(fnmatch.fnmatchcase(p, path) or fnmatch.fnmatchcase(p, f"*/{path}") for p in tree.paths)
    return tree.exists(path) or tree.ends(path)


def citations(page, text, tree, targets, words):
    """[(kind, target, line, ok)] for one page: paths, ./go or make targets, KEY= names."""
    found = []
    fence = False
    for n, line in enumerate((text or "").splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        for target in LINK.findall(line):
            path = link_path(target, page)
            if path is not None:
                found.append(("path", path, n, path_ok(path, tree)))
        # A shell comment in a code block is prose: `# make a repository`.
        for code in ([line.split(" # ", 1)[0]] if fence else TICK.findall(line)):
            path = None if fence else cited_path(code, page, tree)
            if path is not None:
                found.append(("path", path, n, path_ok(path, tree)))
            for key in KEY.findall(code):
                found.append(("key", key, n, key in words))
            for tool, word in COMMAND.findall(f" {code}"):
                if targets is not None:
                    found.append(("command", f"{tool} {word}", n, word in targets))
    return sorted(set(found), key=lambda c: (c[2], c[0], c[1]))


def config_words(tree):
    """Every NAME a tracked file other than Markdown spells: what a KEY= may name."""
    words = set()
    for path in tree.paths:
        if not path.endswith(".md"):
            words.update(WORD.findall(tree.text(path) or ""))
    return words


def read_targets(path):
    """The ./go targets: one per line in PATH, else what `make help` lists, as ci/prompts.sh reads it."""
    if path:
        with open(path, encoding="utf-8") as handle:
            return {line.strip() for line in handle if line.strip()}
    out = run(["make", "--no-print-directory", "help"]).decode()  # nosec B607 - the workbench's make
    return {line.split()[0] for line in out.splitlines() if re.match(r"^  [a-z]", line)}


def excluded(path, exclude):
    return any(fnmatch.fnmatchcase(path, glob) for glob in exclude)


# --- build (§1, §2) ---

def build(repo, rev, out, tickets="tickets", targets=None, exclude=()):
    """Write the map of REV in REPO to OUT, from scratch; return (sha, {kind: count})."""
    sha = git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").decode().strip()
    tree = Tree.at(repo, sha)
    words = config_words(tree)
    tmp = f"{out}.tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE node (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
                           title TEXT NOT NULL DEFAULT '', UNIQUE (kind, name));
        CREATE TABLE edge (src INTEGER NOT NULL, dst INTEGER NOT NULL, kind TEXT NOT NULL,
                           PRIMARY KEY (src, dst, kind));
        CREATE TABLE cite (src INTEGER NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL,
                           line INTEGER NOT NULL, ok INTEGER NOT NULL);
    """)
    ids = {}

    def node(kind, name, title=""):
        if (kind, name) not in ids:
            cur = db.execute("INSERT INTO node (kind, name, title) VALUES (?, ?, ?)", (kind, name, title))
            ids[(kind, name)] = cur.lastrowid
        return ids[(kind, name)]

    def edge(src, dst, kind):
        db.execute("INSERT OR IGNORE INTO edge VALUES (?, ?, ?)", (src, dst, kind))

    kinds = {p: kind_of(p, tickets) for p in tree.paths}
    path_ids = {}
    for path in tree.paths:
        kind = kinds[path]
        if kind == "ticket":
            text = tree.text(path)
            path_ids[path] = node("ticket", TICKET_ID.match(posixpath.basename(path)).group(1), title_of(text))
        else:
            path_ids[path] = node(kind, path, title_of(tree.text(path)) if kind in ("adr", "page") else "")
    for path in tree.paths:
        src, text = path_ids[path], None
        if path.endswith(".py"):
            text = tree.text(path)
            symbols, imports = py_symbols(text), py_imports(path, text, tree)
        elif JS.search(path):
            text = tree.text(path)
            symbols, imports = js_symbols(text), js_imports(path, text, tree)
        else:
            symbols, imports = [], []
        for symbol in symbols:
            edge(src, node("symbol", f"{path}::{symbol}"), "defines")
        for target in imports:
            if target != path:
                edge(src, path_ids[target], "tests" if kinds[path] == "test" and kinds[target] != "test" else "imports")
        if kinds[path] == "ticket":
            text = tree.text(path)
            for glob in perimeter(text):
                for match in tree.paths:
                    if fnmatch.fnmatchcase(match, glob):
                        edge(src, path_ids[match], "perimeter")
            for feature in features(text):
                edge(node("feature", feature), src, "declares")
        if kinds[path] in ("adr", "page"):
            for kind, target, line, ok in citations(path, tree.text(path), tree, targets, words):
                db.execute("INSERT INTO cite VALUES (?, ?, ?, ?, ?)", (src, kind, target, line, int(ok)))
                if kind != "path":
                    edge(src, node(kind, target), "cites")
    tickets_by_id = {name: i for (kind, name), i in ids.items() if kind == "ticket"}
    for commit in _history(repo, sha):
        for ticket in sorted(set(HISTORY.findall(commit[0]))):
            for path in commit[1]:
                if ticket in tickets_by_id and path in path_ids:
                    edge(tickets_by_id[ticket], path_ids[path], "history")
    db.executemany("INSERT INTO meta VALUES (?, ?)",
                   [("schema", SCHEMA), ("sha", sha), ("tickets", tickets), ("exclude", " ".join(exclude))])
    db.commit()
    counts = dict(db.execute("SELECT kind, count(*) FROM node GROUP BY kind ORDER BY kind").fetchall())
    db.close()
    os.replace(tmp, out)
    return sha, counts


def _history(repo, sha):
    """[(message, [paths])] for every commit reachable from SHA, merges against their first parent."""
    out = git(repo, "log", "--format=%x01%B%x02", "--name-only", "--no-renames",
              "--diff-merges=first-parent", sha).decode(errors="replace")
    commits = []
    for chunk in out.split("\x01")[1:]:
        message, _, names = chunk.partition("\x02")
        commits.append((message, [n for n in names.splitlines() if n]))
    return commits


# --- read (§2) ---

def open_map(path, base):
    """The map at PATH, refused unless it was built at BASE."""
    if not os.path.isfile(path):
        raise Refused(f"no map at {path}; build it with ./go map")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
    except sqlite3.DatabaseError as error:
        db.close()
        raise Refused(f"{path} is not a project map: {error}") from None
    if meta.get("schema") != SCHEMA:
        db.close()
        raise Refused(f"{path} has map schema {meta.get('schema')}, this reader wants {SCHEMA}; rebuild it with ./go map")
    if meta.get("sha") != base:
        db.close()
        raise Refused(f"the map at {path} was built at {meta.get('sha')}, the base is {base}: "
                      "a stale map is never read; rebuild it with ./go map")
    return db


def covered(db, paths):
    """{(kind, name): {paths}} for the pages and ADRs, not excluded, that cite PATHS (§4)."""
    exclude = db.execute("SELECT value FROM meta WHERE key = 'exclude'").fetchone()[0].split()
    rows = db.execute("SELECT n.kind, n.name, c.target FROM cite c JOIN node n ON n.id = c.src "
                      "WHERE c.kind = 'path' AND c.ok = 1").fetchall()
    out = {}
    for kind, name, target in rows:
        if excluded(name, exclude):
            continue
        for path in paths:
            if path == target or (target.count("/") >= 1 and path.startswith(target + "/")):
                out.setdefault((kind, name), set()).add(path)
    return out


def slice_of(db, globs):
    """The slice for the paths GLOBS match: markdown, deterministic (§5)."""
    names = [r[0] for r in db.execute("SELECT name FROM node WHERE kind IN ('file', 'test', 'adr', 'page') ORDER BY name")]
    paths = sorted({n for n in names for g in globs if fnmatch.fnmatchcase(n, g)})
    new = sorted(g for g in globs if not any(fnmatch.fnmatchcase(n, g) for n in names))
    sha = db.execute("SELECT value FROM meta WHERE key = 'sha'").fetchone()[0]
    marks = ",".join("?" * len(paths)) or "''"
    lines = ["## Project map", "",
             f"Built at {sha} from the repository by core/map.py, no model (docs/adr/0054). "
             "For the files of this ticket's perimeter:", ""]
    lines += ["Files:"] + [f"- {p}" for p in paths] + [f"- {g} (no file yet)" for g in new] + [""]
    found = covered(db, paths)
    lines += ["Decisions that govern them (ADRs):"]
    lines += [f"- {n} — cites {', '.join(sorted(v))}" for (k, n), v in sorted(found.items()) if k == "adr"] or ["- none"]
    lines += ["", "Pages that describe them, to keep aligned:"]
    lines += [f"- {n} — cites {', '.join(sorted(v))}" for (k, n), v in sorted(found.items()) if k == "page"] or ["- none"]
    tests = db.execute(f"SELECT DISTINCT t.name, f.name FROM edge e JOIN node t ON t.id = e.src JOIN node f ON f.id = e.dst "  # nosec B608 - placeholders only
                       f"WHERE e.kind = 'tests' AND f.name IN ({marks}) ORDER BY t.name, f.name", paths).fetchall()
    by_test = {}
    for test, path in tests:
        by_test.setdefault(test, []).append(path)
    for path in paths:
        if db.execute("SELECT 1 FROM node WHERE kind = 'test' AND name = ?", (path,)).fetchone():
            by_test.setdefault(path, [])
    lines += ["", "Tests that cover them:"]
    lines += [f"- {t}" + (f" (covers {', '.join(c)})" if c else "") for t, c in sorted(by_test.items())] or ["- none"]
    tickets = db.execute(f"SELECT t.name, t.title, group_concat(DISTINCT e.kind) FROM edge e "  # nosec B608 - placeholders only
                         f"JOIN node t ON t.id = e.src JOIN node f ON f.id = e.dst "
                         f"WHERE e.kind IN ('perimeter', 'history') AND f.name IN ({marks}) "
                         f"GROUP BY t.name ORDER BY t.name", paths).fetchall()
    lines += ["", "Tickets that touched them before:"]
    lines += [f"- {t or n} ({','.join(sorted(k.split(',')))})" for n, t, k in tickets] or ["- none"]
    symbols = db.execute(f"SELECT f.name, s.name FROM edge e JOIN node f ON f.id = e.src JOIN node s ON s.id = e.dst "  # nosec B608 - placeholders only
                         f"WHERE e.kind = 'defines' AND f.name IN ({marks}) ORDER BY f.name, s.id", paths).fetchall()
    by_file = {}
    for path, symbol in symbols:
        by_file.setdefault(path, []).append(symbol.split("::", 1)[1])
    lines += ["", "Symbols they define:"]
    lines += [f"- {p}: {', '.join(s)}" for p, s in by_file.items()] or ["- none"]
    return "\n".join(lines) + "\n"


# --- drift (§3) and the docs ticket (§4) ---

def drift(repo, targets, exclude=(), tickets="tickets", known=()):
    """['<page>:<line>: <kind> <target> names nothing'] over the working tree's pages."""
    tree = Tree.worktree(repo)
    words = config_words(tree) | set(known)
    found = []
    for path in tree.paths:
        if kind_of(path, tickets) != "page" or excluded(path, exclude):
            continue
        found += [(path, line, kind, target)
                  for kind, target, line, ok in citations(path, tree.text(path), tree, targets, words) if not ok]
    # A path git ignores is one a run writes (.crew/, .env), not a claim about the tree.
    paths = sorted({t for _, _, k, t in found if k == "path"})
    ignored = set(git(repo, "check-ignore", "--no-index", "--stdin",
                      data="".join(f"{p}\n{p}/\n" for p in paths).encode(), ok=(0, 1)).decode().splitlines()) if paths else set()
    return [f"{p}:{n}: {k} {t} names nothing" for p, n, k, t in found
            if not (k == "path" and (t in ignored or f"{t}/" in ignored))]


def docs_ticket(db, changed, merge_sha):
    """(title, body) of the docs ticket for a merge that changed CHANGED, or None (§4)."""
    found = {k: v for k, v in covered(db, changed).items() if k[1] not in changed}
    if not found:
        return None
    short = merge_sha[:12]
    title = f"Align the documentation with merge {short}"
    body = ["## Problem", "",
            f"Merge `{merge_sha}` changed files that these pages and ADRs cite, and did not change them:", ""]
    body += [f"- `{n}` ({k}) cites {', '.join(f'`{p}`' for p in sorted(v))}" for (k, n), v in sorted(found.items())]
    body += ["", "## Acceptance criteria", "",
             "Given the pages and ADRs listed above",
             "When each is read against the merged files it cites",
             "Then what it says still holds, or it is corrected in place; an ADR changes only by a dated amendment",
             "", "Given the corrected pages",
             "When their citations are read (docs/adr/0054 §3)",
             "Then every path, `./go` command and `NAME=` key they cite exists", "",
             "## Perimeter", ""]
    body += [f"- `{n}`" for (_, n) in sorted(found)]
    body += ["", "## Notes", "",
             "Filed by the tower's merge step from the project map (docs/adr/0054 §4), no model. "
             "The perimeter is documents only: the code is already merged and judged.", ""]
    return title, "\n".join(body)


def after_merge(args):
    """Clone, build at the merge, file the docs ticket; print the record's `map` field."""
    if not SHA.match(args.merge_sha):
        raise Refused(f"merge {args.merge_sha} is not a full sha")
    exclude = args.exclude.split()
    with tempfile.TemporaryDirectory() as work:
        src = os.path.join(work, "src.git")
        run(["git", "clone", "-q", "--bare", args.clone_url, src])  # nosec B607 - the workbench's git
        sha, _ = build(src, args.merge_sha, args.out, args.tickets, read_targets(args.targets), exclude)
        # What the merge changed: against its first parent, as a code host shows a merge commit.
        changed = git(src, "diff-tree", "-r", "--root", "--no-commit-id", "--name-only", "--no-renames",
                      "-m", "--first-parent", sha).decode().split("\n")
    db = open_map(args.out, sha)
    try:
        ticket = docs_ticket(db, sorted(c for c in changed if c), sha)
    finally:
        db.close()
    filed = None
    if ticket is not None:
        tracker = os.environ.get("TRACKER") or ""
        if not tracker:
            raise Refused("TRACKER not set; run this via ./go, not directly")
        put = sh(f"adapters/{tracker}/put.sh", ticket[0], f"docs merge {sha}",
                 input=ticket[1], capture_output=True, text=True)
        if put.returncode != 0:
            raise Refused(f"the docs ticket was not filed: {put.stderr.strip()}")
        filed = put.stdout.strip()
    print(json.dumps({"map": {"sha": sha, "file": args.out, "docs_ticket": filed}}))


def main(argv):
    parser = argparse.ArgumentParser(prog="core/map.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--repo", required=True)
    b.add_argument("--rev", default="HEAD")
    b.add_argument("--tickets", default="tickets")
    b.add_argument("--targets")
    b.add_argument("--exclude", default="")
    b.add_argument("--out", required=True)
    s = sub.add_parser("slice")
    s.add_argument("--map", required=True)
    s.add_argument("--base", required=True)
    s.add_argument("--ticket", required=True)
    d = sub.add_parser("drift")
    d.add_argument("--repo", required=True)
    d.add_argument("--targets")
    d.add_argument("--exclude", default="")
    d.add_argument("--tickets", default="tickets")
    d.add_argument("--known", action="append", default=[])
    a = sub.add_parser("after-merge")
    a.add_argument("--clone-url", required=True)
    a.add_argument("--merge-sha", required=True)
    a.add_argument("--tickets", default="tickets")
    a.add_argument("--targets")
    a.add_argument("--exclude", default="")
    a.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "build":
            sha, counts = build(args.repo, args.rev, args.out, args.tickets, read_targets(args.targets),
                                args.exclude.split())
            print(f"{sha} " + " ".join(f"{k}={v}" for k, v in counts.items()))
        elif args.cmd == "slice":
            if not os.path.isfile(args.ticket):
                raise Refused(f"no ticket at {args.ticket}")
            with open(args.ticket, encoding="utf-8") as handle:
                globs = perimeter(handle.read())
            if not globs:
                raise Refused(f"{args.ticket} has no ## Perimeter: the map has nothing to slice")
            db = open_map(args.map, args.base)
            try:
                sys.stdout.write(slice_of(db, globs))
            finally:
                db.close()
        elif args.cmd == "drift":
            found = drift(args.repo, read_targets(args.targets), args.exclude.split(), args.tickets, args.known)
            for line in found:
                print(line)
            return 1 if found else 0
        else:
            after_merge(args)
    except Refused as refused:
        print(f"map: {refused}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
