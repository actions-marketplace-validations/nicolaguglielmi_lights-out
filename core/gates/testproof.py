# SPDX-License-Identifier: Apache-2.0
"""gates/test-proof.sh's judgement (docs/adr/0053 §2).

    python3 -m core.gates.testproof <base> <head>

The tests a PR adds or changes (WORKLOAD_TEST_PATHS, §1, as core/testdiff.py
reads them) must fail on the base: in a throwaway worktree of the merge-base,
only those files are taken from HEAD, and the workload's TEST_CMD runs
there through `sh core/toolchain-run.sh` (docs/adr/0042 §2), the bundled
workload from its worktree, an attached one (WORKLOAD_ATTACHED) from this
checkout with its own paths pointed into the worktree. A non-zero exit is
GO; exit 0 is NO-GO, the tests pass without the change, listed as details;
exit 125 the toolchain failing. GO by absence of subject, nothing run and no
toolchain checked: the base is the empty tree, no test changed, or only
tests changed.
"""

import os
import shutil
import tempfile

from .. import testdiff
from . import PIPE, NoGo, main, proc

RUN = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "toolchain-run.sh"))


def git(*args, cwd=None):
    return proc(["git", *args], cwd=cwd, stdout=PIPE, stderr=PIPE, text=True)


def preflight():
    """(ok, $toolchain_where or the preflight's NO-GO reason)."""
    got = proc(["sh", RUN, "--preflight"], stdout=PIPE, text=True)
    return got.returncode == 0, got.stdout.strip()


def toolchain(cmd, cwd, env):
    """CMD through core/toolchain-run.sh from CWD; its stdout goes to stderr."""
    return proc(["sh", RUN, cmd], cwd=cwd, env=env, stdout=2).returncode


def prefix_of(path):
    got = git("-C", path, "rev-parse", "--show-prefix")
    if got.returncode != 0:
        raise NoGo(f"{path} is not inside a git repository")
    return got.stdout.strip()


def judge(argv, env=None, check=preflight, run=toolchain):
    env = os.environ if env is None else env
    base, head = argv
    workload = env.get("WORKLOAD", ".")
    contract_dir = env.get("WORKLOAD_CONTRACT", "")
    if not env.get("WORKLOAD_TEST_PATHS"):
        raise NoGo("WORKLOAD_TEST_PATHS is empty (docs/adr/0053 §1)")
    if not env.get("TEST_CMD"):
        raise NoGo("TEST_CMD is empty (docs/adr/0042 §1)")
    if git("-C", workload, "cat-file", "-t", base).stdout.strip() == "tree":
        return "nothing ran: the base is the empty tree, nothing to fail on"
    prefix = prefix_of(workload)
    contract = prefix_of(contract_dir)
    names = git("-C", workload, "diff", "--no-renames", "--name-only", base, head)
    if names.returncode != 0:
        raise NoGo(f"could not list the changed tests: {names.stderr.strip()}")
    tests, why = testdiff.subject(names.stdout.splitlines(), env["WORKLOAD_TEST_PATHS"], prefix)
    if why:
        return f"nothing ran: {why}"
    ok, where = check()
    if not ok:
        raise NoGo(where)

    tmp = tempfile.mkdtemp()
    wt = os.path.join(tmp, "wt")
    try:
        added = git("-C", workload, "worktree", "add", "--detach", wt, base)
        if added.returncode != 0:
            raise NoGo("git worktree add on the base failed", added.stderr)
        if git("restore", f"--source={head}", "--worktree", "--", *tests, cwd=wt).returncode != 0:
            raise NoGo(f"could not take the tests from {head} onto the base")
        root = os.getcwd() if env.get("WORKLOAD_ATTACHED") else wt
        child = dict(env, WORKLOAD=f"{wt}/{prefix}", WORKLOAD_CONTRACT=f"{wt}/{contract}",
                     COMPOSE_FILE=f"compose.yaml:{wt}/{contract}compose.yaml")
        rc = run(env["TEST_CMD"], root, child)
    finally:
        git("-C", workload, "worktree", "remove", "--force", wt)
        shutil.rmtree(tmp, ignore_errors=True)
    short = base[:7]
    if rc == 125:
        raise NoGo(f"in {where}: the toolchain itself failed on the base; see stderr")
    if rc != 0:
        return f"in {where}, the changed tests fail on the base {short}"
    raise NoGo(f"in {where}: the changed tests pass on the base {short} too, so they do not prove the change", *tests)


if __name__ == "__main__":
    raise SystemExit(main(judge))
