# SPDX-License-Identifier: Apache-2.0
"""The logic of the gates under gates/ (docs/adr/0084 §2).

Each gate's `.sh` keeps its path, arguments, environment and guards, and
ends in `verdict core.gates.<x>` (ci/lib.sh), which runs the module as
`python3 -m core.gates.<x>` from the repository root. What every module
shares is here and nothing else:

- `NoGo(reason, *details)`, the gate's NO-GO, and `main(judge, argv)`,
  which runs `judge(argv)` and prints the verdict for `verdict`: a GO's
  detail on one line (or nothing), or a NO-GO's reason on the first line
  and one detail a line after it; it returns 0 for GO and 1 for NO-GO.
  Everything else a module says goes to stderr.
- `proc(argv, ...)`, the package's one process call: an argument list,
  never a shell line (docs/adr/0052 §3); and `adapter(directory)`, a
  port's verbs over it, `sh <directory>/<verb>.sh`, for the conformance
  suites (a suite takes any callable of that shape, so its tests hand it a
  fake port).

Not shipped in the `lights-out-gates` wheel (pyproject.toml lists the
top of core/ only, docs/adr/0061): these gates need an engine, a plane or
a code host.
"""

import subprocess  # nosec B404 - adapter verbs, git and the gates' tools, argv lists only (docs/adr/0084 §2)
import secrets
import sys
import time

PIPE = subprocess.PIPE
DEVNULL = subprocess.DEVNULL


class NoGo(Exception):
    """A gate's NO-GO: a one-line reason, then details for stderr."""

    def __init__(self, reason, *details):
        super().__init__(reason)
        self.reason = " ".join(str(reason).split("\n"))
        self.details = [str(d) for d in details]


def say(*parts):
    """One line on stderr, where everything but the verdict goes."""
    print(*parts, file=sys.stderr, flush=True)


def proc(argv, **kwargs):
    """subprocess.run on an argument list, never raising on an exit code."""
    return subprocess.run(argv, check=False, **kwargs)  # nosec B603 B607 - an argv list, no shell, ADR 0084 §2


def adapter(directory):
    """verb(name, *args, data=None, env=None) -> (exit code, stdout, stderr),
    text: `sh DIRECTORY/<name>.sh ARGS...` with DATA (bytes) on stdin, or
    nothing, in ENV (the whole environment) or this process's."""
    def verb(name, *args, data=None, env=None):
        feed = {"input": data} if data is not None else {"stdin": DEVNULL}
        got = proc(["sh", f"{directory}/{name}.sh", *args], capture_output=True, env=env, **feed)
        return got.returncode, got.stdout.decode("utf-8", "replace"), got.stderr.decode("utf-8", "replace")
    return verb


def run_id():
    """Date and random hex, so runs never collide (the suites' run id)."""
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + secrets.token_hex(4)


def main(judge, argv=None):
    """Run judge(argv), print its verdict on stdout, return the exit code."""
    try:
        detail = judge(sys.argv[1:] if argv is None else argv)
    except NoGo as no:
        print(no.reason)
        for d in no.details:
            for line in d.splitlines():
                if line.strip():
                    print(line)
        return 1
    if detail:
        print(" ".join(str(detail).split("\n")))
    return 0
