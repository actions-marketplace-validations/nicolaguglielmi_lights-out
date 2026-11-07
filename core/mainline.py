"""Main always green without a queue (docs/adr/0056): stdlib only.

    python3 core/mainline.py rejudge   from core/steps/merge.sh, before the adapter's merge
    python3 core/mainline.py check     the `mainline` step (core/steps/mainline.sh)

`rejudge` (§1): a PR judged on a base main has since moved merges without
its gates running again unless a first-parent commit after that base
touched a path in the ticket's `## Perimeter`. Prints nothing to merge,
or the `ci-failed` JSON that sends the ticket to rework.

`check` (§3, §4): judges main's head against the last green main, in
groups of at most MAINLINE_GROUP_MAX commits, with the tree gates and the
judges of the last green main. A red group is bisected; its culprit is
reverted through the CodeHost port's own verbs and main is judged again.
The `mainline`/`main` document in the StateStore holds the last green
commit, the reverts and, while main is red, why. Prints the ticket's next
state: `main-green`, or `ci-failed` when its own merge was the culprit.

Every line is on stderr; stdout is the step's JSON. Reads its ports
through their adapter verbs, from the tower's checkout (the cwd).
"""

import fnmatch
import json
import math
import os
import subprocess  # nosec B404 - git and adapter verbs, argv lists only (docs/adr/0052 §3)
import sys
import tempfile
from datetime import datetime, timezone

try:
    from core.tower import compact, dig, sh, text
except ImportError:  # run as a script: core/ is sys.path[0]
    from tower import compact, dig, sh, text

COLLECTION, DOC = "mainline", "main"
# The gates whose subject is the whole tree (§3): the diff gates already
# judged each PR's own diff.
TREE_GATES = "sast test"
POLICY = "policy/mainline.env"
IDENTITY = ["-c", "user.name=lights-out-tower", "-c", "user.email=tower@lights-out.invalid"]


class Failed(Exception):
    """The step fails: one line on stderr, exit 1, nothing merged or recorded as done."""


def say(line):
    print(line, file=sys.stderr, flush=True)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- pure rules (unit-tested from the ADR) ---

def perimeter(ticket_text):
    """The list items of `## Perimeter`, backticks dropped (core/perimeter.sh)."""
    found, out = False, []
    for line in ticket_text.splitlines():
        if line.startswith("## "):
            if found:
                break
            found = line.startswith("## Perimeter")
            continue
        if found and line.startswith("- "):
            out.append(line[2:].strip().replace("`", ""))
    return out


def in_perimeter(path, globs):
    """core/perimeter.sh's case patterns: `*` crosses `/`, as fnmatchcase does."""
    return any(fnmatch.fnmatchcase(path, glob) for glob in globs)


def overlaps(globs, moved):
    """Every (commit, path) a commit touched inside the perimeter, in order."""
    return [(commit, path) for commit, paths in moved for path in paths if in_perimeter(path, globs)]


def group(commits, limit):
    """The next group the check judges: the oldest `limit` commits."""
    return list(commits[:limit])


def first_red(commits, is_green):
    """The first red commit; commits[-1] is known red, the one before commits[0] green.

    Binary search, so is_green runs at most ceil(log2(len(commits))) times.
    """
    lo, hi = -1, len(commits) - 1  # lo green (or before the list), hi red
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if is_green(commits[mid]):
            lo = mid
        else:
            hi = mid
    return commits[hi]


def bisect_runs(n):
    return math.ceil(math.log2(n)) if n > 1 else 0


# --- git and the ports ---

def run(argv, **kwargs):
    """An argv list, never a shell line."""
    return subprocess.run(argv, check=False, **kwargs)  # nosec B603 B607 - argv list, ADR 0052 §3


def git(repo, *args, ok=True):
    got = run(["git", "-C", repo, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if ok and got.returncode != 0:
        raise Failed(f"git {args[0]} failed: {got.stderr.strip().splitlines()[-1] if got.stderr.strip() else got.returncode}")
    return got


def out(repo, *args):
    return git(repo, *args).stdout.strip()


def ancestor(repo, a, b):
    return bool(a) and git(repo, "merge-base", "--is-ancestor", a, b, ok=False).returncode == 0


def adapter(port, verb, *args, **kwargs):
    return sh(f"adapters/{port}/{verb}.sh", *args, **kwargs)


def adapter_out(port, verb, *args, why, **kwargs):
    got = adapter(port, verb, *args, stdout=subprocess.PIPE, text=True, **kwargs)
    if got.returncode != 0:
        raise Failed(why)
    return got.stdout.strip()


def fetch_main(env):
    """Main's head on the code host, fetched into the workload's repository."""
    url = adapter_out(env["CODE_HOST"], "clone-url", why=f"{env['CODE_HOST']} gave no clone URL")
    if git(env["WORKLOAD"], "fetch", "-q", url, "HEAD", ok=False).returncode != 0:
        raise Failed(f"could not fetch main from {env['CODE_HOST']}")
    return out(env["WORKLOAD"], "rev-parse", "FETCH_HEAD")


def first_parent(repo, base, head):
    """First-parent commits after base up to head, oldest first."""
    listed = out(repo, "rev-list", "--first-parent", "--reverse", f"{base}..{head}")
    return listed.split() if listed else []


def touched(repo, commit):
    """The paths commit changed against its first parent: what a merge touched."""
    listed = out(repo, "diff", "--no-renames", "--name-only", f"{commit}^1", commit)
    return listed.splitlines() if listed else []


def parents(repo, commit):
    return out(repo, "rev-list", "--parents", "-n", "1", commit).split()[1:]


def tree(repo, commit):
    return out(repo, "rev-parse", f"{commit}^{{tree}}")


def store_get(env):
    got = adapter(env["STATE_STORE"], "get", COLLECTION, DOC, stdout=subprocess.PIPE, text=True)
    if got.returncode != 0:
        return {}
    try:
        doc = json.loads(got.stdout)
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        raise Failed(f"the stored {COLLECTION}/{DOC} is not a JSON object")
    return doc


def store_put(env, doc):
    if adapter(env["STATE_STORE"], "put", COLLECTION, DOC, input=compact(doc) + "\n", text=True).returncode != 0:
        raise Failed(f"could not write {COLLECTION}/{DOC}")


def group_max():
    try:
        with open(POLICY, encoding="utf-8") as policy:
            for line in policy:
                key, _, value = line.strip().partition("=")
                if key == "MAINLINE_GROUP_MAX" and value.isdigit() and int(value) > 0:
                    return int(value)
    except OSError:
        pass
    raise Failed(f"{POLICY} sets no MAINLINE_GROUP_MAX")


def ticket_doc(env):
    with open(env["DOC_FILE"], encoding="utf-8") as doc_file:
        return json.load(doc_file)


# --- §1: the re-judge rule ---

def rejudge(env):
    doc = ticket_doc(env)
    base = text(dig(doc, "pr", "base_sha"))
    if not base:
        raise Failed(f"{env['DOC_FILE']} has no pr.base_sha")
    repo = env["WORKLOAD"]
    head = fetch_main(env)
    if not ancestor(repo, base, head):
        raise Failed(f"the PR was judged on {base}, which is not on main ({head}): main was rewritten; not merged")
    commits = first_parent(repo, base, head)
    if not commits:
        return None
    ticket = adapter_out(env["TRACKER"], "get", env["TICKET"], why=f"{env['TRACKER']} has no ticket {env['TICKET']}")
    globs = perimeter(ticket)
    if not globs:
        raise Failed(f"ticket {env['TICKET']} has no ## Perimeter (docs/adr/0021 §5)")
    hits = overlaps(globs, [(c, touched(repo, c)) for c in commits])
    if not hits:
        say(f"[merge] main moved by {len(commits)} commit(s) since {base}; none touched the perimeter: "
            f"merging without re-judging (docs/adr/0056 §1)")
        return None
    commit, path = hits[0]
    line = f"NO-GO: base — main moved under the perimeter since {base}: {path} by {commit}"
    say(f"[merge] {line}")
    details = [f"{p} by {c} ({out(repo, 'log', '-1', '--format=%s', c)})" for c, p in hits]
    judged = text(dig(doc, "ci", "head_sha")) or text(dig(doc, "pr", "head_sha"))
    return {"state": "ci-failed",
            "mainline": {"verdict": "NO-GO", "judge": "base", "head_sha": judged, "line": line, "details": details}}


# --- §3, §4: the main check ---

class Judge:
    """Judges commits against the last green main G with G's judges, memoized by tree."""

    def __init__(self, env, green):
        self.env = env
        self.repo = env["WORKLOAD"]
        self.green = green
        self.seen = {}  # (tree, green) -> verdict
        self.known_green(green)

    def known_green(self, commit):
        self.seen[(tree(self.repo, commit), self.green)] = {"go": True, "line": f"GO: same tree as {commit}",
                                                            "details": []}

    def move(self, green):
        """G moved: its tree is green under its own judges."""
        self.green = green
        self.known_green(green)

    def __call__(self, commit):
        key = (tree(self.repo, commit), self.green)
        if key not in self.seen:
            self.seen[key] = self.gates(commit)
        else:
            say(f"[mainline] {commit}: a tree already judged — {self.seen[key]['line']} (docs/adr/0056 §3)")
        return self.seen[key]

    def judges(self):
        contract = out(self.env["WORKLOAD_CONTRACT"], "rev-parse", "--show-prefix")
        own = [f"{contract}workload.env", f"{contract}policy.env", f"{contract}runners"]
        if self.env.get("WORKLOAD_ATTACHED"):
            return own
        return ["Makefile", "profiles", "gates", "ci", "core", "policy"] + own

    def gates(self, commit):
        with tempfile.TemporaryDirectory() as tmp:
            wt, gates_out = os.path.join(tmp, "wt"), os.path.join(tmp, "gates-out")
            git(self.repo, "worktree", "add", "-q", "--detach", wt, commit)
            try:
                present = [j for j in self.judges()
                           if git(wt, "cat-file", "-e", f"{self.green}:{j}", ok=False).returncode == 0
                           or os.path.exists(os.path.join(wt, j))]
                if present:
                    git(wt, "restore", f"--source={self.green}", "--staged", "--worktree", "--", *present)
                where = ["make", "--no-print-directory"]
                where += (["gates", f"WORKLOAD={wt}"] if self.env.get("WORKLOAD_ATTACHED") else ["-C", wt, "gates"])
                made = run(where + [f"GATES={TREE_GATES}", f"BASE={self.green}", f"HEAD={commit}",
                                    f"GATES_OUT={gates_out}", "TOOLCHAIN_ISOLATE=1"],
                           stdout=subprocess.PIPE, text=True)
                verdict = read_env(os.path.join(gates_out, "verdict.env"))
                if verdict.get("GATES") not in ("GO", "NO-GO"):
                    raise Failed(f"the gates left no verdict on {commit}")
                failed = verdict.get("FAILED", "")
                details = read_lines(os.path.join(gates_out, f"{failed}.details")) if failed else []
            finally:
                git(self.repo, "worktree", "remove", "--force", wt, ok=False)
        line = made.stdout.strip().splitlines()[-1] if made.stdout.strip() else f"{verdict['GATES']}: gates"
        say(f"[mainline] {commit} against {self.green}: {line}")
        return {"go": verdict["GATES"] == "GO", "line": line, "details": details}


def read_env(path):
    try:
        with open(path, encoding="utf-8") as env_file:
            return dict(line.rstrip("\n").partition("=")[::2] for line in env_file if "=" in line)
    except OSError:
        return {}


def read_lines(path):
    try:
        with open(path, encoding="utf-8") as lines:
            return [line.rstrip("\n") for line in lines if line.strip()]
    except OSError:
        return []


def revert(env, culprit, verdict):
    """Reverts culprit through the code host's push, open-pr and merge verbs: never a force push (§4)."""
    repo, host = env["WORKLOAD"], env["CODE_HOST"]
    url = adapter_out(host, "clone-url", why=f"{host} gave no clone URL")
    branch = f"revert/{culprit[:12]}"
    with tempfile.TemporaryDirectory() as tmp:
        ws, pr_json = os.path.join(tmp, "ws"), os.path.join(tmp, "pr.json")
        if run(["git", "clone", "-q", url, ws], stderr=subprocess.DEVNULL).returncode != 0:
            raise Failed(f"could not clone main from {host} to revert {culprit}")
        git(ws, "checkout", "-q", "-b", branch)
        mainline = ["-m", "1"] if len(parents(repo, culprit)) > 1 else []
        if run(["git", "-C", ws, *IDENTITY, "revert", "--no-edit", *mainline, culprit],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
            raise Failed(f"the revert of {culprit} does not apply on main")
        head = out(ws, "rev-parse", "HEAD")
        with open(pr_json, "w", encoding="utf-8") as pr:
            json.dump({"title": f"Revert {culprit[:12]}: main is NO-GO",
                       "body": "\n".join([verdict["line"], ""] + verdict["details"]
                                         + ["", "Bisected and reverted by the tower (docs/adr/0056 §4)."])}, pr)
        if adapter(host, "push", ws, branch, stdout=subprocess.DEVNULL).returncode != 0:
            raise Failed(f"could not push {branch} to {host}")
        number = adapter_out(host, "open-pr", branch, pr_json, why=f"could not open the revert PR on {host}").split()[0]
    shas = adapter_out(host, "merge", number, head, why=f"could not merge the revert PR #{number} on {host}").split()
    say(f"[mainline] reverted {culprit} through {host}: PR #{number}, merged as {shas[0]}")
    return shas[0]


def check(env):
    doc = ticket_doc(env)
    merge_sha = text(dig(doc, "merge", "sha"))
    base = text(dig(doc, "pr", "base_sha"))
    if not merge_sha or not base:
        raise Failed(f"{env['DOC_FILE']} has no merge.sha or pr.base_sha")
    repo = env["WORKLOAD"]
    head = fetch_main(env)
    if not ancestor(repo, merge_sha, head):
        raise Failed(f"merge {merge_sha} is not on main ({head})")
    record = store_get(env)
    # A revert that is not on main belongs to a main since rewritten.
    reverted = [r for r in record.get("reverted") or [] if ancestor(repo, text(r.get("revert")), head)]
    mine = next((r for r in reverted if r.get("merge") == merge_sha), None)
    if mine is None:
        green = last_green(repo, record, base, head)
        mine = walk(env, doc, record, reverted, green, head, merge_sha)
    if mine:
        say(f"[mainline] ticket {env['TICKET']}: its merge {merge_sha} was reverted by {mine['revert']}; "
            f"back to the dev-worker with the verdict")
        return {"state": "ci-failed",
                "mainline": {"verdict": "NO-GO", "judge": "main", "head_sha": text(dig(doc, "merge", "head_sha")),
                             "line": f"NO-GO: main — {mine['line']} (merge {merge_sha}, reverted by {mine['revert']})",
                             "details": mine.get("details") or []}}
    say(f"[mainline] ticket {env['TICKET']}: merge {merge_sha} is on a green main")
    return {"state": "main-green", "mainline": {"verdict": "GO", "green": store_get(env).get("green")}}


def last_green(repo, record, base, head):
    """G: the document's green while it is on main, else the PR's base (§3)."""
    green = text(record.get("green"))
    if ancestor(repo, green, head):
        return green
    if green:
        say(f"[mainline] the last green main {green} is not on main any more; starting from the PR's base {base}")
    if not ancestor(repo, base, head):
        raise Failed(f"neither the last green main nor the PR's base {base} is on main ({head})")
    return base


def walk(env, doc, record, reverted, green, head, merge_sha):
    """Judges main from G to its head, group by group; one bisect and revert at most.

    Returns this ticket's entry in `reverted` when its merge was the culprit.
    """
    repo = env["WORKLOAD"]
    judge = Judge(env, green)
    judged = text(dig(doc, "ci", "head_sha"))
    if judged and green == text(dig(doc, "pr", "base_sha")):
        # CI passed that head with the base's judges, which are G's.
        judge.known_green(judged)
    limit = group_max()
    culprit = None
    if record.get("state") == "red" and green != head:
        # Red is lifted by a fix on main, never by a second bisection: the
        # head is judged as it is (§4, §5).
        now_head = judge(head)
        if not now_head["go"]:
            store_put(env, dict(record, head=head, at=now(), reverted=reverted,
                                line=f"{head} is still NO-GO against the last green main {green}: {now_head['line']}"))
            raise Failed(f"main is still NO-GO at {head}: {now_head['line']}; a person fixes main, "
                         f"then ./go resume TICKET={env['TICKET']} (docs/adr/0056 §5)")
        green = head
    while green != head:
        batch = group(first_parent(repo, green, head), limit)
        top = judge(batch[-1])
        if top["go"]:
            green = batch[-1]
            judge.move(green)
            continue
        why = f"{batch[-1]} is NO-GO against the last green main {green}: {top['line']}"
        store_put(env, dict(record, state="red", green=green, head=head, line=why, reverted=reverted, at=now()))
        if culprit:
            raise Failed(f"main is still NO-GO after reverting {culprit}: {why}; a person decides (docs/adr/0056 §4)")
        say(f"[mainline] main is NO-GO: {why}; bisecting {len(batch)} commit(s), "
            f"at most {bisect_runs(len(batch))} more gate run(s)")
        culprit = first_red(batch, lambda c: judge(c)["go"])
        verdict = judge(culprit)
        if any(culprit in (r.get("revert"), r.get("merge")) for r in reverted):
            raise Failed(f"the culprit {culprit} is a revert or already reverted; a person decides (docs/adr/0056 §4)")
        say(f"[mainline] culprit: {culprit} — {verdict['line']}")
        revert_sha = revert(env, culprit, verdict)
        reverted = reverted + [{"merge": culprit, "revert": revert_sha, "line": verdict["line"],
                                "details": verdict["details"], "at": now()}]
        store_put(env, dict(record, state="red", green=green, head=revert_sha, reverted=reverted, at=now(),
                            line=f"{why}; reverted {culprit}, judging main again"))
        head = fetch_main(env)
    store_put(env, dict(record, state="green", green=green, head=head, line="", reverted=reverted, at=now()))
    say(f"[mainline] main is GO at {green}")
    return next((r for r in reverted if r.get("merge") == merge_sha), None)


def main(argv, env=None):
    env = os.environ if env is None else env
    cmd = argv[0] if argv else ""
    need = {"rejudge": ("TICKET", "DOC_FILE", "CODE_HOST", "TRACKER", "WORKLOAD"),
            "check": ("TICKET", "DOC_FILE", "CODE_HOST", "STATE_STORE", "WORKLOAD", "WORKLOAD_CONTRACT")}
    if cmd not in need or len(argv) != 1:
        say("usage: mainline.py rejudge | check")
        return 2
    for var in need[cmd]:
        if not env.get(var):
            say(f"mainline: {var} not set; run this via the tower, not directly")
            return 2
    try:
        result = rejudge(env) if cmd == "rejudge" else check(env)
    except Failed as failed:
        say(f"[mainline] {failed}")
        return 1
    if result is not None:
        print(compact(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
