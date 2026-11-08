"""The light tier of the gates (docs/adr/0061): git and Python only, no engine.

    python3 -m core gates --light [BASE=<ref> HEAD=<ref> | STAGED=1] [WORKLOAD=<dir>]
                                  [TICKET=<file>] [TEST_ON_HOST=1] [GATES_OUT=<dir>]

(`lights-out gates --light ...` once the package is installed.) Of the ten
gates of the full judgement it runs at most six, in this order: risk,
perimeter, test-weakening, test, test-proof, spec; secrets, deps, sast and
mutation need the image and never run here. By default no code of the
repository runs (risk, test-weakening); TICKET adds perimeter and spec,
TEST_ON_HOST=1 adds test then test-proof, both or neither (§4). The first
NO-GO stops the rest. One line, in `line()`: never `GO: gates`.

The logic is core/'s own entry points, called as the shell wrappers call
them: risk.classify with policy.effective, testdiff's `weakening` and
`subject`, spec's `check`, and core/perimeter.sh. What is new is glue: the
range, git with the wrappers' flags, and the host run of TEST_CMD in
throwaway checkouts outside the repository. Nothing is written to the
repository or its .git; GATES_OUT is the one place anything is written.
"""

import contextlib
import io
import os
import posixpath
import shutil
import subprocess  # nosec B404 - git, sh and the contract's TEST_CMD (docs/adr/0061 §3)
import sys
import tempfile

try:
    from . import policy, risk, spec, testdiff
except ImportError:  # run as a script: core/ is sys.path[0]
    import policy
    import risk
    import spec
    import testdiff

NAME = "gates-light"
# The eight of `make gates` (the Makefile's GATES) and the two the tower runs
# around them, perimeter and spec (docs/adr/0061 §4).
TOTAL = 10
ORDER = ("risk", "secrets", "test-weakening", "deps", "sast", "test", "mutation", "test-proof")
KEYS = ("BASE", "HEAD", "STAGED", "WORKLOAD", "TICKET", "TEST_ON_HOST", "GATES_OUT")
HERE = os.path.dirname(os.path.abspath(__file__))
PERIMETER = os.path.join(HERE, "perimeter.sh")


class Refused(Exception):
    """A NO-GO before or outside any gate: one line, no gate named."""


class NoGo(Exception):
    """A gate's NO-GO: its name, its reason, the details for stderr."""

    def __init__(self, gate, reason, details=()):
        super().__init__(reason)
        self.gate, self.reason, self.details = gate, reason, list(details)


def run(argv, cwd=None, data=None, env=None):
    """ARGV, an argument list: the one process call (docs/adr/0061 §3)."""
    try:
        return subprocess.run(argv, cwd=cwd, input=data, env=env, capture_output=True, check=False)  # nosec B603 - an argv list: git, sh and the contract TEST_CMD (ADR 0061 §3)
    except OSError as exc:
        raise Refused(f"{argv[0]} could not run: {exc.strerror}") from None


def git_try(repo, *args, data=None):
    """(exit code, stdout as text) of git in REPO, never coloured or quoted."""
    done = run(["git", "-C", repo, "-c", "color.ui=never", "-c", "core.quotePath=false", *args], data=data)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def git(repo, *args, data=None):
    rc, out = git_try(repo, *args, data=data)
    if rc != 0:
        raise Refused(f"git {args[0]} failed in {repo}")
    return out


def commit_of(repo, ref):
    rc, out = git_try(repo, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}")
    return out.strip() if rc == 0 else None


def say(*lines):
    for line in lines:
        print(line, file=sys.stderr)


def call(main, argv, stdin=""):
    """(exit code, stdout) of a core/ module's own main(), the wrapper's way."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = main(argv, stdin=io.StringIO(stdin)) if stdin is not None else main(argv)
    return rc, out.getvalue().strip()


class Range:
    """The judged change: BASE..HEAD, or HEAD against the index (STAGED=1)."""

    def __init__(self, top, base, head, staged):
        self.top, self.staged = top, staged
        if staged:
            if base or head:
                raise Refused("STAGED=1 judges the staged changes on HEAD; it takes no BASE or HEAD")
            self.head = None
            self.base = commit_of(top, "HEAD")
            if not self.base:
                raise Refused("STAGED=1 needs a commit to stage on; the repository has none")
            if not git(top, "diff", "--cached", "--name-only", self.base).strip():
                raise Refused("STAGED=1, and nothing is staged")
            return
        self.head = commit_of(top, head or "HEAD")
        if not self.head:
            raise Refused(f"HEAD={head} is not a commit of the repository" if head
                          else "the repository has no commit to judge")
        if base:
            rc, kind = git_try(top, "cat-file", "-t", base)
            if rc == 0 and kind.strip() == "tree":
                self.base = base
            else:
                rc, out = git_try(top, "merge-base", base, self.head)
                if rc != 0:
                    raise Refused(f"BASE={base} has no merge-base with {self.head[:7]}")
                self.base = out.strip()
        else:
            self.base = commit_of(top, f"{self.head}~1") or git(top, "hash-object", "-t", "tree", "--stdin").strip()

    def diff(self, *flags):
        return git(self.top, "diff", *flags, *(("--cached", self.base) if self.staged else (self.base, self.head)))

    def empty_base(self):
        return git_try(self.top, "cat-file", "-t", self.base)[1].strip() == "tree"


class Contract:
    """The workload.env and policy.env that judge (docs/adr/0033, 0061 §7)."""

    def __init__(self, rng, prefix):
        revs = (rng.base,) if rng.staged else (rng.base, rng.head)
        for rev in revs:
            for where in (f"{prefix}.lights-out/", prefix):
                rc, text = git_try(rng.top, "cat-file", "-p", f"{rev}:{where}workload.env")
                if rc == 0:
                    self.where, self.text = where, text
                    self.env = risk.parse_policy(text)
                    rc, overrides = git_try(rng.top, "cat-file", "-p", f"{rev}:{where}policy.env")
                    self.overrides = overrides if rc == 0 else ""
                    return
        raise Refused(f"no {prefix}.lights-out/workload.env at the base or the head; lights-out init drafts one")


def platform_policy():
    """The package's own merge.env: installed beside the code, or policy/ in a clone."""
    for path in (os.path.join(HERE, "platform_policy", "merge.env"),
                 os.path.join(HERE, os.pardir, "policy", "merge.env")):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read()
    raise Refused("the platform policy, merge.env, is missing from this installation")


def gate_risk(rng, contract):
    try:
        rules, looser = policy.effective(platform_policy(), contract.text, contract.overrides)
    except policy.PolicyError as exc:
        where = {"platform": "merge.env", "workload": "workload.env"}.get(exc.source, "policy.env")
        raise NoGo("risk", f"{contract.where}{where}: {exc}") from None
    say(*(f"policy: {contract.where}policy.env: {report}" for report in looser))
    try:
        got = risk.classify([line for line in rng.diff("--no-renames", "--numstat").splitlines() if line], rules)
    except ValueError as exc:
        raise NoGo("risk", f"core/risk.py could not classify the range: {exc}") from None
    signals = ",".join("{}({})".format(s["name"], " ".join(s["paths"])) for s in got["signals"])
    say(f"risk: level={got['level']} decision={got['decision']} signals={signals or 'none'}")
    return got


def gate_perimeter(rng, ticket):
    done = run(["sh", PERIMETER, ticket], data=rng.diff("--no-renames", "--name-only").encode())
    if done.returncode != 0:
        why = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise NoGo("perimeter", why[-1] if why else "core/perimeter.sh refused the change")


def test_paths(contract, gate):
    paths = contract.env.get("WORKLOAD_TEST_PATHS", "")
    if not paths:
        raise NoGo(gate, "WORKLOAD_TEST_PATHS is empty (docs/adr/0053 §1)")
    return paths


def gate_weakening(rng, contract, prefix, ticket):
    diff = rng.diff("--no-color", "--no-ext-diff", "-M", "-U0")
    rc, out = call(testdiff.main, ["weakening", test_paths(contract, "test-weakening"), prefix, ticket or ""], diff)
    if rc != 0:
        lines = out.splitlines() or ["core/testdiff.py failed; see stderr"]
        raise NoGo("test-weakening", lines[0], lines[1:])
    say(f"test-weakening: {out}")


def checkout(rng, rev, into, staged=False):
    """A throwaway checkout of REV outside the repository (§4): a shared clone,
    with the staged patch applied when STAGED says so."""
    done = run(["git", "clone", "-q", "--shared", "--no-checkout", rng.top, into])
    if done.returncode != 0:
        raise Refused("could not make a throwaway checkout of the repository")
    git(into, "checkout", "-q", "--detach", rev)
    if staged:
        patch = git(rng.top, "diff", "--cached", "--binary", rng.base)
        rc, _ = git_try(into, "apply", "--whitespace=nowarn", data=patch.encode())
        if rc != 0:
            raise Refused("the staged changes do not apply on HEAD")
    return into


def suite(contract, tree, prefix, gate):
    """TEST_CMD's exit code, run on this host from the workload's test root."""
    cmd = contract.env.get("TEST_CMD", "")
    if not cmd:
        raise NoGo(gate, "TEST_CMD is empty (docs/adr/0042 §1)")
    cwd = os.path.join(tree, prefix, contract.env.get("WORKLOAD_TEST_ROOT", ""))
    if not os.path.isdir(cwd):
        raise NoGo(gate, f"the test root {prefix}{contract.env.get('WORKLOAD_TEST_ROOT', '')} is not in the checkout")
    done = run(["sh", "-c", cmd], cwd=cwd, env=dict(os.environ, NO_COLOR="1"))
    sys.stderr.write(done.stdout.decode("utf-8", "replace") + done.stderr.decode("utf-8", "replace"))
    return done.returncode


def gate_test(rng, contract, prefix, tmp):
    head = checkout(rng, rng.base if rng.staged else rng.head, os.path.join(tmp, "head"), rng.staged)
    rc = suite(contract, head, prefix, "test")
    if rc != 0:
        raise NoGo("test", f"on the host: the test command failed (exit {rc}), see stderr")
    return head


def gate_proof(rng, contract, prefix, head, tmp):
    if rng.empty_base():
        return "nothing ran: the base is the empty tree, nothing to fail on"
    names = rng.diff("--no-renames", "--name-only")
    rc, out = call(testdiff.main, ["subject", test_paths(contract, "test-proof"), prefix], names)
    if rc == 3:
        return f"nothing ran: {out}"
    if rc != 0:
        raise NoGo("test-proof", f"could not list the changed tests: {out}")
    tests = out.splitlines()
    base = checkout(rng, rng.base, os.path.join(tmp, "base"))
    for path in tests:
        src, dst = os.path.join(head, path), os.path.join(base, path)
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
        elif os.path.isfile(dst):
            os.remove(dst)
    short = rng.base[:7]
    if suite(contract, base, prefix, "test-proof") == 0:
        raise NoGo("test-proof", f"on the host: the changed tests pass on the base {short} too, "
                   "so they do not prove the change", tests)
    return f"on the host, the changed tests fail on the base {short}"


def gate_spec(ticket):
    rc, out = call(spec.main, ["check", ticket], stdin=None)
    if rc != 0:
        raise NoGo("spec", out or "core/spec.py failed; see stderr")


def line(level, decision, ran, host, ticket):
    """The GO line, exactly as docs/adr/0061 §5 words it."""
    text = (f"GO: {NAME} — risk {level}, {decision}; {len(ran)} of {TOTAL} gates ran; "
            "secrets, deps, sast, mutation need the image")
    if not host:
        text += "; test, test-proof need TEST_ON_HOST=1"
    if not ticket:
        text += "; perimeter, spec need TICKET="
    return text


def parse(argv):
    args = {}
    for arg in argv:
        key, eq, value = arg.partition("=")
        if not eq or key not in KEYS:
            raise Refused(f"'{arg}' is not an argument lights-out gates --light takes; one of "
                          + " ".join(f"{k}=" for k in KEYS))
        args[key] = value
    return args


def workload_prefix(value):
    norm = posixpath.normpath(value or ".")
    if posixpath.isabs(norm) or norm == ".." or norm.startswith("../"):
        raise Refused(f"WORKLOAD={value} is not a directory inside the repository")
    return "" if norm == "." else norm + "/"


def judge(argv):
    """(the one line, the exit code, the verdict) for `gates --light ARGV`."""
    verdict = {"RISK_LEVEL": "unknown", "RISK_DECISION": "unknown"}
    ran = []
    args = {}
    try:
        args = parse(argv)
        on = {k: args.get(k, "") not in ("", "0") for k in ("STAGED", "TEST_ON_HOST")}
        rc, top = git_try(os.getcwd(), "rev-parse", "--show-toplevel")
        if rc != 0:
            raise Refused("lights-out gates --light runs inside a git repository")
        top = top.strip()
        ticket = os.path.abspath(args["TICKET"]) if args.get("TICKET") else None
        if ticket and not os.path.isfile(ticket):
            raise Refused(f"TICKET={args['TICKET']}: no such file")
        prefix = workload_prefix(args.get("WORKLOAD"))
        rng = Range(top, args.get("BASE"), args.get("HEAD"), on["STAGED"])
        contract = Contract(rng, prefix)
        got = gate_risk(rng, contract)
        verdict.update(RISK_LEVEL=got["level"], RISK_DECISION=got["decision"])
        ran.append("risk")
        if ticket:
            gate_perimeter(rng, ticket)
            ran.append("perimeter")
        gate_weakening(rng, contract, prefix, ticket)
        ran.append("test-weakening")
        if on["TEST_ON_HOST"]:
            with tempfile.TemporaryDirectory(prefix="lights-out-light-") as tmp:
                head = gate_test(rng, contract, prefix, tmp)
                ran.append("test")
                say("test: on the host, the suite passed on the head")
                say(f"test-proof: {gate_proof(rng, contract, prefix, head, tmp)}")
                ran.append("test-proof")
        if ticket:
            gate_spec(ticket)
            ran.append("spec")
        out, code = line(got["level"], got["decision"], ran, on["TEST_ON_HOST"], ticket), 0
        verdict["GATES"] = "GO"
    except NoGo as exc:
        say(*exc.details)
        ran.append(exc.gate)
        out, code = f"NO-GO: {NAME} — {exc.gate}: {exc.reason}", 1
        verdict.update(GATES="NO-GO", FAILED=exc.gate)
    except Refused as exc:
        out, code = f"NO-GO: {NAME} — {exc}", 1
        verdict["GATES"] = "NO-GO"
    verdict["RAN"] = " ".join(ran)
    if args.get("GATES_OUT"):
        write_verdict(args["GATES_OUT"], verdict)
    return " ".join(out.split("\n")), code, verdict


def write_verdict(where, verdict):
    """verdict.env in `make gates`' shape, plus RAN (docs/adr/0061 §6)."""
    os.makedirs(where, exist_ok=True)
    keys = ("GATES", "FAILED", "RISK_LEVEL", "RISK_DECISION", "RAN")
    with open(os.path.join(where, "verdict.env"), "w", encoding="utf-8") as fh:
        fh.writelines(f"{k}={verdict[k]}\n" for k in keys if k in verdict)
