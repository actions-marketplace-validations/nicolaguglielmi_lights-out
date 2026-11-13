# SPDX-License-Identifier: Apache-2.0
"""gates/codehost-conformance.sh's suite: the CodeHost port (docs/adr/0043
§5, in the shape of docs/adr/0026 and 0041). Written from the ADR and the
port's contract, never from an adapter.

    python3 -m core.gates.codehost

It drives whichever CODE_HOST is set, only through its eight verbs, plus
plain git for the commits it makes and the clones it reads back. Ten cases,
in this order, the first disagreement a NO-GO naming the case:
   1 bootstrap, then its postcondition: the host's default branch is at the
     workload's HEAD
   2 clone-url.sh, a clone of it, and a .git/config with no credential
   3 push.sh of conformance/<run id>, one commit adding one file
   4 open-pr.sh twice, which must return the same PR number
   5 status.sh pending, then a 200-character success (longer than the 140
     the largest host accepts, ADR 0043 §3), then await.sh -> success; await.sh gets
     2 s for the pending status, which must not end it, and 60 s for the
     success
   6 pr.sh: exactly number, state, merged, head_sha, merge_sha: open, not
     merged, the head as pushed, merge_sha null
   7 a second commit is pushed, the PR's head awaited 60 s (30 polls, 2 s
     apart, pr.sh and the host's refs/pull/<n>/head when it shows one); a
     merge at the old head must exit 1, print nothing and leave the PR
     unmerged
   8 a merge at the new head (exit 1 retried 3 times, 5 s apart: a host
     computes mergeability after a push) prints "<merge> <head>"; pr.sh
     agrees, and the merge commit's second parent is that head, on the
     default branch (docs/adr/0019 §5)
   9 the same merge again prints the same line (docs/adr/0019 §9)
  10 no secret appears in anything the suite captured from the verbs and
     its git commands: the values CONFORMANCE_SECRETS holds, one a line,
     which the wrapper sets because only it may name a host (docs/adr/0024
     §1, ci/vendor-free.sh); the scan is first shown to find a secret it is
     handed and none in a file that holds none.
The numbers are decisions of this suite, none a measurement. Every run
leaves its branch, its PR and its merge commit on the host; cleanup is the
suite's temporary directory.
"""

import json
import os
import re
import shutil
import tempfile
import time

from . import DEVNULL, PIPE, NoGo, adapter, main, proc, run_id, say

VERBS = ("bootstrap", "clone-url", "push", "open-pr", "status", "await", "pr", "merge")
GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "conformance", "GIT_AUTHOR_EMAIL": "conformance@localhost",
           "GIT_COMMITTER_NAME": "conformance", "GIT_COMMITTER_EMAIL": "conformance@localhost"}
UNSET = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")


def same(a, b):
    """jq's ==: a boolean equals only a boolean, 1 equals 1.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


class Suite:
    def __init__(self, host, verb, workload, secrets, work, sleep):
        self.host, self.verb, self.workload, self.secrets, self.work, self.sleep = \
            host, verb, workload, secrets, work, sleep
        self.rid = run_id()
        self.branch = f"conformance/{self.rid}"
        self.clone = os.path.join(work, "clone")
        self.captured = []  # (label, stdout + stderr)
        self.rc, self.out = 0, ""
        self.env = {k: v for k, v in os.environ.items() if k not in UNSET}
        self.env.update(GIT_ENV)

    def keep(self, label, rc, out, err):
        self.captured.append((label, out + err))
        for line in err.splitlines():
            say(f"  [{label}] {line}")
        self.rc, self.out = rc, out
        return rc

    def call(self, name, *args, env=None):
        return self.keep(name, *self.verb(name, *args, env=dict(self.env, **(env or {}))))

    def git(self, label, *args):
        got = proc(["git", *args], env=self.env, stdin=DEVNULL, stdout=PIPE, stderr=PIPE)
        return self.keep(label, got.returncode, got.stdout.decode("utf-8", "replace"),
                         got.stderr.decode("utf-8", "replace"))

    def local_git(self, *args):
        """git in the suite's own clone: not captured, a failure the suite's own."""
        got = proc(["git", "-C", self.clone, *args], env=self.env, stdout=PIPE, stderr=PIPE, text=True)
        if got.returncode != 0:
            raise NoGo(f"git {' '.join(args)} failed in the suite's own clone", got.stderr)
        return got.stdout.strip()

    def first_field(self):
        return (self.out.splitlines() or [""])[0].split("\t")[0]

    def lines(self):
        return self.out.count("\n") + (1 if self.out and not self.out.endswith("\n") else 0)

    def pr(self):
        """pr.sh's JSON object, or None."""
        try:
            data = json.loads(self.out)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def leaked(self, text):
        return any(s and s in text for s in self.secrets)

    def wait_pr_head(self, number, sha):
        for _ in range(30):
            self.call("pr", number)
            got = self.pr() if self.rc == 0 else None
            if got and got.get("head_sha") == sha:
                self.git("ls-remote", "ls-remote", self.url, f"refs/pull/{number}/head")
                pull_head = self.first_field()
                if not pull_head or pull_head == sha:
                    return True
            self.sleep(2)
        return False

    def run(self):
        say(f"[codehost-conformance] run {self.rid} on CODE_HOST={self.host}, branch {self.branch}")
        if self.call("bootstrap"):
            raise NoGo(f"case1 bootstrap: adapters/{self.host}/bootstrap.sh exited {self.rc}")
        got = proc(["git", "-C", self.workload, "rev-parse", "HEAD"], env=self.env, stdout=PIPE, stderr=PIPE, text=True)
        if got.returncode != 0:
            raise NoGo(f"case1 bootstrap: git -C {self.workload} rev-parse HEAD failed; WORKLOAD is not a repository")
        workload_head = got.stdout.strip()
        self.call("clone-url")
        if self.rc != 0 or self.lines() != 1:
            raise NoGo(f"case1 bootstrap: clone-url.sh exited {self.rc} and printed {self.lines()} lines, "
                       "want exit 0 and one line")
        self.url = self.out.rstrip("\n")
        if self.git("ls-remote", "ls-remote", self.url, "HEAD"):
            raise NoGo("case1 bootstrap: git ls-remote of clone-url.sh's URL failed")
        if self.first_field() != workload_head:
            raise NoGo(f"case1 bootstrap: the host's default branch is at [{self.first_field()}], "
                       f"the workload's HEAD is {workload_head}")
        say("[codehost-conformance] case 1 bootstrap: GO")

        if self.git("clone", "clone", "-q", self.url, self.clone):
            raise NoGo("case2 clone: git clone of clone-url.sh's URL failed")
        with open(os.path.join(self.clone, ".git", "config"), encoding="utf-8", errors="replace") as fh:
            cfg = fh.read()
        if re.search(r"://[^/\s]*@", cfg):
            raise NoGo("case2 clone: the clone's .git/config holds a URL with user information in it")
        if self.leaked(cfg) or re.search(r"extraheader|password|\[credential", cfg, re.I):
            raise NoGo("case2 clone: the clone's .git/config holds a credential")
        got = proc(["git", "-C", self.clone, "symbolic-ref", "--short", "HEAD"], env=self.env, stdout=PIPE,
                   stderr=PIPE, text=True)
        if got.returncode != 0:
            raise NoGo("case2 clone: the clone has no branch checked out; the host's default branch is not a branch")
        default = got.stdout.strip()
        say("[codehost-conformance] case 2 clone-url and a clone without a credential: GO")

        name = f"conformance-{self.rid}.txt"
        self.local_git("checkout", "-q", "-b", self.branch)
        with open(os.path.join(self.clone, name), "w") as fh:
            fh.write(f"conformance run {self.rid}, first commit\n")
        self.local_git("add", "--", name)
        self.local_git("-c", "commit.gpgsign=false", "commit", "-q", "-m", f"conformance {self.rid}: first commit")
        head1 = self.local_git("rev-parse", "HEAD")
        if self.call("push", self.clone, self.branch):
            raise NoGo(f"case3 push: adapters/{self.host}/push.sh exited {self.rc}")
        if self.git("ls-remote", "ls-remote", self.url, f"refs/heads/{self.branch}") or self.first_field() != head1:
            raise NoGo(f"case3 push: {self.branch} on the host is not at the pushed head {head1}")
        say("[codehost-conformance] case 3 push: GO")

        pr_file = os.path.join(self.work, "pr.json")
        with open(pr_file, "w") as fh:
            fh.write(json.dumps({"title": f"conformance {self.rid}", "body": "Opened by gates/codehost-conformance.sh "
                                 "on a throwaway repository; safe to ignore."}) + "\n")
        if self.call("open-pr", self.branch, pr_file):
            raise NoGo(f"case4 open-pr: exit {self.rc} on the first call")
        line1 = self.out.rstrip("\n")
        if not re.fullmatch(r"[0-9].* .+", line1, re.S):
            raise NoGo(f"case4 open-pr: stdout was [{line1}], want '<number> <url>'")
        number = line1.split(" ", 1)[0]
        if not number.isdigit():
            raise NoGo(f"case4 open-pr: [{number}] is not a PR number")
        if self.call("open-pr", self.branch, pr_file):
            raise NoGo(f"case4 open-pr: exit {self.rc} on the second call")
        line2 = self.out.rstrip("\n")
        if line2.split(" ", 1)[0] != number:
            raise NoGo(f"case4 open-pr: the second call returned [{line2}], the first PR {number}: a retried ticket "
                       "would open a second PR")
        say(f"[codehost-conformance] case 4 open-pr is idempotent (PR #{number}): GO")

        if self.call("status", head1, "pending", "conformance", "waiting for the suite"):
            raise NoGo(f"case5 status: status.sh pending exited {self.rc}")
        if self.call("await", head1, "conformance", env={"AWAIT_TIMEOUT": "2", "AWAIT_INTERVAL": "1"}) != 1:
            raise NoGo(f"case5 await: await.sh exited {self.rc} while the only status was pending, "
                       "want it to wait and exit 1")
        if self.call("status", head1, "success", "conformance", "0123456789" * 20):
            raise NoGo(f"case5 status: status.sh exited {self.rc} on a 200-character success description")
        self.call("await", head1, "conformance", env={"AWAIT_TIMEOUT": "60", "AWAIT_INTERVAL": "2"})
        if self.rc != 0 or self.out.rstrip("\n") != "success":
            raise NoGo(f"case5 await: after pending then success, await.sh exited {self.rc} and printed "
                       f"[{self.out.rstrip()}], want exit 0 and success")
        say("[codehost-conformance] case 5 status and await: GO")

        if self.call("pr", number):
            raise NoGo(f"case6 pr: pr.sh exited {self.rc}")
        want = {"number": int(number), "state": "open", "merged": False, "head_sha": head1, "merge_sha": None}
        got = self.pr()
        if got is None or sorted(got) != sorted(want) or not all(same(got[k], want[k]) for k in want):
            raise NoGo(f"case6 pr: pr.sh printed [{self.out.rstrip()}], want exactly number, state, merged, head_sha "
                       f"and merge_sha: PR {number} open, not merged, head {head1}, merge_sha null")
        say("[codehost-conformance] case 6 pr before the merge: GO")

        with open(os.path.join(self.clone, name), "a") as fh:
            fh.write(f"conformance run {self.rid}, second commit\n")
        self.local_git("add", "--", name)
        self.local_git("-c", "commit.gpgsign=false", "commit", "-q", "-m", f"conformance {self.rid}: second commit")
        head2 = self.local_git("rev-parse", "HEAD")
        if head2 == head1:
            raise NoGo("case7: the second commit did not change the head")
        if self.call("push", self.clone, self.branch):
            raise NoGo(f"case7 push: adapters/{self.host}/push.sh exited {self.rc} on the second commit")
        if not self.wait_pr_head(number, head2):
            raise NoGo(f"case7 stale-merge: after 60 s the host still reports another head for PR {number} than the "
                       f"pushed {head2}")
        if self.call("merge", number, head1) != 1:
            raise NoGo(f"case7 stale-merge: merge.sh at the old head {head1} exited {self.rc}, want 1")
        if self.out:
            raise NoGo(f"case7 stale-merge: merge.sh refused the old head and still printed [{self.out.rstrip()}] "
                       "on stdout")
        self.call("pr", number)
        got = self.pr() if self.rc == 0 else None
        if not got or got.get("merged") is not False or got.get("merge_sha") is not None or \
                got.get("head_sha") != head2:
            raise NoGo(f"case7 stale-merge: after the refused merge pr.sh printed [{self.out.rstrip()}], want the PR "
                       f"unmerged, merge_sha null, head {head2}")
        say("[codehost-conformance] case 7 a merge at a stale head is refused: GO")

        for attempt in (1, 2, 3):
            if self.call("merge", number, head2) == 0:
                break
            if attempt == 3:
                raise NoGo(f"case8 merge: merge.sh at the new head {head2} exited {self.rc} after {attempt} attempts")
            say(f"[codehost-conformance] case 8 merge: exit {self.rc} on attempt {attempt} of 3, trying again in 5 s")
            self.sleep(5)
        merge_line = self.out.rstrip("\n")
        if self.lines() != 1:
            raise NoGo(f"case8 merge: merge.sh printed {self.lines()} lines, want exactly '<merge> <head>'")
        merge_sha, _, judged = merge_line.partition(" ")
        if not re.fullmatch(r"[0-9a-f]*", merge_sha):
            raise NoGo(f"case8 merge: [{merge_sha}] is not a commit id")
        if len(merge_sha) != 40:
            raise NoGo(f"case8 merge: [{merge_sha}] is not a 40-character commit id")
        if judged != head2:
            raise NoGo(f"case8 merge: merge.sh printed head [{judged}], want the merged head {head2}")
        self.call("pr", number)
        got = self.pr() if self.rc == 0 else None
        if not got or got.get("merged") is not True or got.get("merge_sha") != merge_sha or got.get("head_sha") != head2:
            raise NoGo(f"case8 merge: pr.sh printed [{self.out.rstrip()}] after the merge, want merged, merge_sha "
                       f"{merge_sha}, head {head2}")
        if self.git("fetch", "-C", self.clone, "fetch", "-q", "origin"):
            raise NoGo("case8 merge: git fetch origin failed after the merge")
        got = proc(["git", "-C", self.clone, "rev-list", "--parents", "-n", "1", merge_sha], env=self.env,
                   stdout=PIPE, stderr=PIPE, text=True)
        if got.returncode != 0:
            raise NoGo(f"case8 merge: the merge commit {merge_sha} is not in a fetch of the host")
        parents = got.stdout.split()[1:]
        if len(parents) != 2:
            raise NoGo(f"case8 merge: the merge commit {merge_sha} has {len(parents)} parents, want 2: ADR 0019 §5 "
                       "needs a merge commit, never a squash or a rebase")
        if parents[1] != head2:
            raise NoGo(f"case8 merge: the merge commit's second parent is {parents[1]}, want the judged head {head2} "
                       "(docs/adr/0019 §5)")
        if proc(["git", "-C", self.clone, "merge-base", "--is-ancestor", merge_sha, f"origin/{default}"],
                env=self.env).returncode != 0:
            raise NoGo(f"case8 merge: the merge commit {merge_sha} is not on origin/{default} after the merge")
        say(f"[codehost-conformance] case 8 merge at the judged head (merge {merge_sha}): GO")

        if self.call("merge", number, head2):
            raise NoGo(f"case9 re-merge: merge.sh on the merged PR exited {self.rc}, want 0")
        if self.out.rstrip("\n") != merge_line:
            raise NoGo(f"case9 re-merge: merge.sh printed [{self.out.rstrip()}], the first merge printed [{merge_line}]")
        say("[codehost-conformance] case 9 a merge twice is one merge: GO")

        self.case10()
        say("[codehost-conformance] case 10 no secret in the captured output: GO")
        return f"{self.host}, PR #{number} merged"

    def case10(self):
        if not any(text for _, text in self.captured):
            raise NoGo("case10: the suite captured no adapter output; the scan would prove nothing")
        for s in self.secrets:
            if s and not self.leaked(f"before {s} after\n"):
                raise NoGo("case10: the scan did not find a secret in a file that holds it")
        if self.leaked("nothing to see\n"):
            raise NoGo("case10: the scan found a secret in a file that holds none")
        where = [label for label, text in self.captured if self.leaked(text)]
        if where:
            raise NoGo(f"case10: a secret appears in the output of: {' '.join(where)}")


def judge(argv, env=None, verb=None, sleep=time.sleep):
    env = os.environ if env is None else env
    host = env.get("CODE_HOST", "")
    if not host:
        raise NoGo("CODE_HOST is not set; a profile sets it: run this via ./go codehost-conformance")
    if verb is None:
        for v in VERBS:
            if not os.path.isfile(f"adapters/{host}/{v}.sh"):
                raise NoGo(f"adapters/{host}/{v}.sh is missing: a code host ships the eight verbs (docs/adr/0043 §5)")
        verb = adapter(f"adapters/{host}")
    if not env.get("WORKLOAD"):
        raise NoGo("WORKLOAD is not set; run this via ./go codehost-conformance")
    secrets = [s for s in env.get("CONFORMANCE_SECRETS", "").splitlines() if s]
    if not secrets:
        raise NoGo(f"CODE_HOST={host}: no secret is known for case 10 to look for (CONFORMANCE_SECRETS is empty); "
                   "the case would prove nothing")
    work = tempfile.mkdtemp()
    try:
        return Suite(host, verb, env["WORKLOAD"], secrets, work, sleep).run()
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(judge))
