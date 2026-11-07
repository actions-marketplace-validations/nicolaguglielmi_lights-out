"""Two tickets never hold the same file (docs/adr/0053 §5): stdlib only.

    python3 core/assign.py <ticket>      TRACKER and STATE_STORE from the profile

Run by core/steps/assign.sh before anything is cloned. Reads the ticket
from the Tracker and its `## Perimeter` (core/perimeter.sh's rules), and
the StateStore document perimeters/held, {"tickets": {<id>: [<glob>, ...]}},
written by earlier assigns. A listed ticket holds its perimeter while its
own document is in a HOLDING state: a PR is open and unmerged. When no
holder's glob overlaps one of this ticket's, the ticket's entry is written
(holders that no longer hold are dropped) and the exit is 0. Otherwise one
line names the holder and the two globs, nothing is written, and the exit
is 1: the tower records the failed attempt, the document stays `opened`,
and `./go resume` asks again (docs/adr/0034). Every line is on stderr: the
step's stdout is its JSON.
"""

import fnmatch
import json
import os
import subprocess  # nosec B404 - only for PIPE; tower.py's sh() runs the verbs
import sys

try:
    from core.tower import compact, sh, text
except ImportError:  # run as a script: core/ is on sys.path
    from tower import compact, sh, text

COLLECTION, DOC = "perimeters", "held"
# From pr-opened until merged: the open, unmerged states of core/tower.py's
# table, and needs-human, where the rework cap leaves an open PR.
HOLDING = ("pr-opened", "ci-failed", "ci-passed", "review", "needs-human")
WILD = "*?["


def say(line):
    print(line, file=sys.stderr, flush=True)


def perimeter(ticket_text):
    """The list items of `## Perimeter`, backticks dropped."""
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


def literal_prefix(glob):
    cut = [i for i in (glob.find(c) for c in WILD) if i >= 0]
    return glob[:min(cut)] if cut else glob


def literal_suffix(glob):
    cut = max(glob.rfind(c) for c in "*?]")
    return glob[cut + 1:]


def overlaps(a, b):
    """Could one path match both globs? Never False when one does."""
    a_lit, b_lit = literal_prefix(a) == a, literal_prefix(b) == b
    if a_lit and b_lit:
        return a == b
    if a_lit or b_lit:
        literal, glob = (a, b) if a_lit else (b, a)
        return fnmatch.fnmatchcase(literal, glob)
    pa, pb, sa, sb = literal_prefix(a), literal_prefix(b), literal_suffix(a), literal_suffix(b)
    return (pa.startswith(pb) or pb.startswith(pa)) and (sa.endswith(sb) or sb.endswith(sa))


class Refused(Exception):
    pass


def store_get(store, collection, doc_id):
    """The document, or None when absent; Refused when the store did not answer."""
    got = sh(f"adapters/{store}/get.sh", collection, doc_id, stdout=subprocess.PIPE, text=True)
    if got.returncode == 1:
        return None
    if got.returncode != 0:
        raise Refused(f"the store did not answer for {collection}/{doc_id}")
    try:
        return json.loads(got.stdout)
    except ValueError:
        raise Refused(f"{collection}/{doc_id} is not JSON") from None


def claim(ticket, env):
    got = sh(f"adapters/{env['TRACKER']}/get.sh", ticket, stdout=subprocess.PIPE, text=True)
    if got.returncode != 0:
        raise Refused(f"{env['TRACKER']} has no ticket {ticket}")
    mine = perimeter(got.stdout)
    if not mine:
        raise Refused(f"{ticket} has no ## Perimeter: what it would hold is unknown (docs/adr/0021 §5)")
    store = env["STATE_STORE"]
    held = (store_get(store, COLLECTION, DOC) or {}).get("tickets") or {}
    keep = {}
    for holder, globs in sorted(held.items()):
        if holder == ticket:
            continue
        state = text((store_get(store, "tickets", holder) or {}).get("state"))
        if state not in HOLDING:
            continue
        keep[holder] = globs
        for a in mine:
            for b in globs:
                if overlaps(a, b):
                    raise Refused(f"{ticket} waits: its perimeter overlaps {holder}'s ({a} ~ {b}), "
                                  f"held while {holder} is {state}; ./go resume TICKET={ticket} "
                                  f"once {holder} has merged")
    keep[ticket] = mine
    put = sh(f"adapters/{store}/put.sh", COLLECTION, DOC,
             input=compact({"tickets": keep}) + "\n", text=True)
    if put.returncode != 0:
        raise Refused(f"could not write {COLLECTION}/{DOC}")
    say(f"[assign] {ticket} holds {len(mine)} perimeter glob{'s' if len(mine) > 1 else ''}; "
        f"{len(keep) - 1} other open ticket{'s' if len(keep) != 2 else ''} hold theirs")


def main(argv, env=None):
    env = os.environ if env is None else env
    if len(argv) != 1 or not argv[0]:
        say("usage: assign.py <ticket>")
        return 2
    for var in ("TRACKER", "STATE_STORE"):
        if not env.get(var):
            say(f"assign: {var} not set; run this via ./go, not directly")
            return 2
    try:
        claim(argv[0], env)
    except Refused as refused:
        say(f"[assign] {refused}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
