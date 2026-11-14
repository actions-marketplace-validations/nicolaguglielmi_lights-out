# SPDX-License-Identifier: Apache-2.0
"""gates/sast.sh's judgement (docs/adr/0015 §4 as amended by docs/adr/0072
§1).

    python3 -m core.gates.sast <base> <head> <where>

The workload's SAST_CMD scans HEAD's checkout through `sh
core/toolchain-run.sh` (WHERE is the wrapper's $toolchain_where). Its line
is read by core/sastdiff.py. A HEAD with no finding is GO without scanning
the base. Otherwise the base is scanned too: nothing for the empty tree,
HEAD's own scan when the range is empty, else the merge-base in a worktree
of its own, from the base's copy of this repository when a compose form
names a compose file of this repository (its build context resolves from
the current directory), with WORKLOAD pointed into the worktree. Only a
finding HEAD has more times than the base is NO-GO (core/sastdiff.py's
fingerprints); inherited ones are listed. A runner that prints no `items`,
on either side, predates ADR 0072: HEAD is judged whole, any finding
NO-GO. Exit 125 is the toolchain failing; a non-zero exit with no finding
parsed is the scan failing. $GATES_OUT/sast.json records the verdict
(`findings` null when there was none to read).
"""

import json
import os
import shutil
import tempfile

from .. import sastdiff
from . import PIPE, NoGo, main, proc, say

RUN = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "toolchain-run.sh"))


def toolchain(cmd, out_path, cwd=None, workload=None):
    """CMD through core/toolchain-run.sh, its stdout in OUT_PATH; the exit code."""
    env = dict(os.environ)
    if workload is not None:
        env["WORKLOAD"] = workload
    with open(out_path, "w") as out:
        return proc(["sh", RUN, cmd], cwd=cwd, env=env, stdout=out).returncode


def git(*args, cwd=None):
    return proc(["git", *args], cwd=cwd, stdout=PIPE, stderr=PIPE, text=True)


class Gate:
    def __init__(self, base, head, where, env, run):
        self.base, self.head, self.where, self.env, self.run = base, head, where, env, run
        self.workload = env.get("WORKLOAD", ".")
        self.out_dir = env.get("GATES_OUT") or ".gates-out"

    def record(self, findings, clean=False):
        """sast.json for a verdict sastdiff does not write."""
        data = {"findings": findings, "where": self.where}
        if clean:
            data.update(new=[], inherited=[])
        with open(os.path.join(self.out_dir, "sast.json"), "w") as fh:
            fh.write(json.dumps(data) + "\n")

    def fail(self, reason, findings=None):
        self.record(findings=findings)
        raise NoGo(f"in {self.where}: {reason}")

    def whole(self, count):
        say("sast: the runner prints no items (it predates docs/adr/0072): HEAD judged whole")
        self.record(findings=count)
        if count:
            raise NoGo(f"in {self.where}: {count} SAST finding(s) in the workload's scope")
        return f"in {self.where}"

    def read(self, path):
        """(count, has items) of a runner line, or the reason it is none."""
        n, items = sastdiff.runner_line(sastdiff.read_file(path))
        return n, items is not None

    def judge(self, tmp):
        cmd = self.env.get("SAST_CMD", "")
        tr = (self.env.get("WORKLOAD_TEST_ROOT") or "").rstrip("/")
        tr = tr + "/" if tr else ""
        prefix = git("-C", self.workload, "rev-parse", "--show-prefix").stdout.strip()
        head_out = os.path.join(tmp, "head.out")
        rc = self.run(cmd, head_out)
        if rc == 125:
            self.fail("the toolchain itself failed before the scan ran; see stderr")
        try:
            count, items = self.read(head_out)
        except (sastdiff.Malformed, OSError) as e:
            self.fail(str(e))
        if count == 0 and rc != 0:
            self.fail(f"SAST_CMD exited {rc} with no findings parsed; see stderr")
        if not items:
            return self.whole(count)
        if count == 0:
            self.record(0, clean=True)
            return f"in {self.where}, none new (0 inherited)"

        base_root = base_line = "-"
        moved = ""
        if git("-C", self.workload, "cat-file", "-t", self.base).stdout.strip() == "tree":
            say("sast: the base is a tree with nothing to scan: every finding is new")
        elif self.base == self.head:
            base_root, base_line = f"{self.workload}/{tr}", head_out
        else:
            wt = os.path.join(tmp, "base")
            added = git("-C", self.workload, "worktree", "add", "-q", "--detach", wt, self.base)
            if (added.stdout + added.stderr).strip():
                say((added.stdout + added.stderr).rstrip("\n"))
            if added.returncode != 0:
                raise NoGo(f"in {self.where}: could not check out the base {self.base}")
            try:
                say(f"sast: {count} finding(s) at HEAD; scanning the base {self.base} to tell new from inherited")
                here = None
                if (self.env.get("TOOLCHAIN_IMAGE") or "").startswith("compose:") and \
                        git("-C", self.workload, "rev-parse", "--show-toplevel").stdout == \
                        git("rev-parse", "--show-toplevel").stdout:
                    here = os.path.join(wt, git("rev-parse", "--show-prefix").stdout.strip())
                base_out = os.path.join(tmp, "base.out")
                rc = self.run(cmd, base_out, cwd=here, workload=f"{wt}/{prefix}")
                if rc == 125:
                    raise NoGo(f"in {self.where}: the toolchain itself failed on the base; see stderr")
                try:
                    base_count, base_items = self.read(base_out)
                except (sastdiff.Malformed, OSError) as e:
                    raise NoGo(f"in {self.where}: on the base, {e}") from None
                if base_count == 0 and rc != 0:
                    raise NoGo(f"in {self.where}: SAST_CMD exited {rc} on the base with no findings parsed; see stderr")
                if not base_items:
                    return self.whole(count)
                base_root, base_line = f"{wt}/{prefix}{tr}", base_out
                moved = proc(["git", "-C", self.workload, "diff", "-M", "--name-status", "-z", self.base, self.head],
                             stdout=PIPE).stdout.decode("utf-8", "surrogateescape")
                return self.compare(prefix + tr, f"{self.workload}/{tr}", head_out, base_root, base_line, moved)
            finally:
                git("-C", self.workload, "worktree", "remove", "--force", wt)
        return self.compare(prefix + tr, f"{self.workload}/{tr}", head_out, base_root, base_line, moved)

    def compare(self, prefix, head_root, head_line, base_root, base_line, moved):
        rc, verdict = sastdiff.diff(os.path.join(self.out_dir, "sast.json"), self.where, prefix, head_root,
                                    head_line, base_root, base_line, moved)
        if rc == 0:
            return f"in {self.where}, {verdict}"
        if rc == 1:
            raise NoGo(f"in {self.where}: {verdict}")
        raise NoGo(f"in {self.where}: could not compare the two scans: {verdict}")


def judge(argv, env=None, run=toolchain):
    env = os.environ if env is None else env
    gate = Gate(*argv, env, run)
    os.makedirs(gate.out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp()
    try:
        return gate.judge(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(judge))
