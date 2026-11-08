"""The audit chain (docs/adr/0019 §6): stdlib only.

Rebuilds deploy → merge → PR → ticket → spec from the ticket's document
and prints it on stderr, one link per line. Exit 0 prints nothing on
stdout; exit 1 prints one line naming what is missing or disagrees, the
reason core/audit.sh puts on its NO-GO. Two kinds of NO-GO: a missing link
(a field the chain needs is absent, or the sha CI judged is not the sha
that was merged), and a divergence between the record and the code host
(owner addition, 2026-09-16: an audit that reads only its own archive
confirms itself). A document whose CI decision was `review` and whose
state is past it must carry the review (docs/adr/0021 §9); each rejected
attempt is printed, newest first (docs/adr/0038 §9). Reads the store and
the code host through their adapter verbs; vendor-free.

    TICKET=<id> STATE_STORE=<adapter> CODE_HOST=<adapter> python3 core/audit.py
"""

import json
import os
import subprocess  # nosec B404 - only for PIPE; tower.py's sh() runs the verbs
import sys

try:
    from .tower import dig, sh, text
except ImportError:  # run as a script: core/ is sys.path[0]
    from tower import dig, sh, text

# States past each point of the chain, so the links it needs.
RELEASED = ("rolled-back", "held")
MERGED = ("merged", "main-green") + RELEASED
JUDGED = ("ci-passed", "review", "ci-failed", "needs-human") + MERGED
# Past the review: "review" itself means the reviewer has not run yet.
REVIEWED = ("ci-passed", "ci-failed", "needs-human") + MERGED


class Refused(Exception):
    pass


def field(doc, path):
    """`jq -r '<path> // empty'` for a dotted path such as .pr.number."""
    return text(dig(doc, *path.strip(".").split(".")))


def interpolated(value):
    """A value inside a jq string interpolation: null prints as null."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def adapter_json(argv, unreachable):
    got = sh(*argv, stdout=subprocess.PIPE, text=True)
    if got.returncode != 0:
        raise Refused(unreachable)
    try:
        value = json.loads(got.stdout)
    except ValueError:
        raise Refused(f"{unreachable}: it did not answer JSON") from None
    if not isinstance(value, dict):
        raise Refused(f"{unreachable}: it did not answer a JSON object")
    return value


def missing_links(doc, ticket):
    """The fields the chain needs at this state that the document lacks, in chain order."""
    state = field(doc, ".state")
    if not state:
        raise Refused(f"document for {ticket} has no state")
    if state == "opened":
        raise Refused(f"ticket {ticket} is only opened: no PR, no chain yet")
    need = []
    if state in RELEASED:
        need += [".release.verdict", ".release.version", ".merge.sha"]
    if state in MERGED:
        need += [".merge.sha", ".merge.head_sha", ".ci.verdict"]
    if state in JUDGED:
        need += [".ci.verdict", ".ci.head_sha"]
    if state in REVIEWED and field(doc, ".ci.decision") == "review":
        need += [".review.verdict", ".review.reason"]
    need += [".pr.number", ".pr.head_sha", ".spec.sha256", ".spec.title", ".task.harness"]
    missing = []
    for path in need:
        if not field(doc, path) and path not in missing:
            missing.append(path)
    return missing


def check(doc, host):
    """The record against itself and against the code host's view of the PR."""
    state = field(doc, ".state")
    number = field(doc, ".pr.number")
    pr_head = field(doc, ".pr.head_sha")
    ci_head = field(doc, ".ci.head_sha")
    merge_head = field(doc, ".merge.head_sha")
    if ci_head and ci_head != pr_head:
        raise Refused(f"CI judged {ci_head} but the PR was opened at {pr_head}")
    if merge_head and merge_head != pr_head:
        raise Refused(f"merged head {merge_head} is not the PR head {pr_head} that CI judged")
    if host is None:
        return
    host_merged = field(host, ".merged")
    host_merge = field(host, ".merge_sha")
    # A merge the main check reverted (docs/adr/0056 §4) is merged on the
    # code host while the ticket is back at ci-failed for its rework.
    if state in MERGED or field(doc, ".mainline.judge") == "main":
        if host_merged != "true":
            raise Refused(f"state store says {state}, code host says PR #{number} is "
                          f"{field(host, '.state')} and not merged")
        if host_merge != field(doc, ".merge.sha"):
            raise Refused(f"state store records merge {field(doc, '.merge.sha')}, "
                          f"code host records {host_merge}")
    else:
        if host_merged == "true":
            raise Refused(f"state store says {state}, code host says PR #{number} is "
                          f"already merged as {host_merge}")
        if field(host, ".head_sha") != pr_head:
            raise Refused(f"state store records PR head {pr_head}, code host has "
                          f"{field(host, '.head_sha')}")


def chain(doc, ticket):
    """The chain as lines, deploy first, each link back to the spec."""
    f = lambda path: field(doc, path)  # noqa: E731 -- the shell's f()
    state = f(".state")
    lines = []
    if state in RELEASED:
        lines.append(f"deploy   {f('.release.version')} {state} — {f('.release.verdict')}")
        lines += ["         " + interpolated(n) for n in (dig(doc, "release", "numbers") or [])]
        lines.append(f"         image: {f('.release.image')}")
        lines.append(f"  ← merge  {f('.merge.sha')} (code host agrees)")
    elif state in ("merged", "main-green"):
        lines.append(f"merge    {f('.merge.sha')} (code host agrees), "
                     f"{'on a green main, ' if state == 'main-green' else ''}not released")
    elif f(".mainline.judge") == "main":
        lines.append(f"PR       stopped at {state}: merged as {f('.merge.sha')}, reverted ({f('.mainline.line')})")
    else:
        lines.append(f"PR       stopped at {state}")
    lines.append(f"  ← PR     #{f('.pr.number')} {f('.pr.url')} (gates {f('.ci.verdict')}, "
                 f"risk {f('.ci.risk_level')}, {f('.ci.decision')}; head {f('.pr.head_sha')})")
    if f(".review.verdict"):
        lines.append(f"  ← review {f('.review.role')} ({f('.review.verdict')}): {f('.review.reason')}")
    for attempt in reversed(doc.get("rework") or []):
        lines.append(f"  ← rework attempt {interpolated(attempt.get('attempt'))} "
                     f"(head {interpolated(attempt.get('head_sha'))}), "
                     f"{interpolated(attempt.get('judge'))}: {interpolated(attempt.get('line'))}")
    lines.append(f"  ← ticket {ticket} ({f('.task.role')}, harness {f('.task.harness')}, "
                 f"model {f('.task.model') or 'none'})")
    lines.append(f"  ← spec   sha256:{f('.spec.sha256')} \"{f('.spec.title')}\"")
    return lines


def audit(env):
    for var, how in (("TICKET", "./go audit TICKET=<id>"), ("STATE_STORE", "./go, not directly"),
                     ("CODE_HOST", "./go, not directly")):
        if not env.get(var):
            raise Refused(f"{var} not set; run this via {how}")
    ticket, store, code_host = env["TICKET"], env["STATE_STORE"], env["CODE_HOST"]
    doc = adapter_json([f"adapters/{store}/get.sh", "tickets", ticket],
                       f"no document for ticket {ticket} in {store}")
    missing = missing_links(doc, ticket)
    if missing:
        raise Refused("missing link(s) in the record: " + " ".join(missing))
    check(doc, None)
    number = field(doc, ".pr.number")
    host = adapter_json([f"adapters/{code_host}/pr.sh", number],
                        f"code host {code_host} unreachable or PR #{number} unknown to it")
    check(doc, host)
    return chain(doc, ticket)


def main(env=None):
    try:
        lines = audit(os.environ if env is None else env)
    except Refused as refused:
        print(refused)
        return 1
    for line in lines:
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
