"""The release record and the release log (docs/adr/0020 §4, docs/adr/0047
§2 P2 and §3): stdlib only. core/launchpad.sh and core/promote.sh call it
(docs/adr/0052 §3); the shell keeps the plane and the human, this file the
JSON.

    python3 core/releases.py record VERDICT HELD_AT STAGES IMAGE
        write RELEASE_RECORD (CANARY_VERSION, STABLE_VERSION); a final
        verdict, `held` or `rolled-back`, is also appended to RELEASES_LOG
        with the time and RELEASE_TICKET (null for a release run directly)
    python3 core/releases.py brief
        print the brief rendered from RELEASE_RECORD, the L0 brief: no
        model at L0, the release role writes it from L1
    python3 core/releases.py plane < STATUS
        exit 0 when the plane (the DELIVERY port's status.sh output on
        stdin, docs/adr/0026 §2) runs RELEASE_RECORD's held canary at the
        weight it was held at (ticket 0008); else exit 1 and print why
    python3 core/releases.py answer GO|NO-GO
        record who answered (GO_FOR_LAUNCH_BY, default `unauthenticated`;
        GO_FOR_LAUNCH_VIA, default `cli`) into RELEASE_RECORD, `promoted`
        on GO and `rejected` on NO-GO, and one line of RELEASES_LOG

RELEASE_RECORD keeps only the latest record; the log keeps them all and is
never rewritten, only appended.
"""

import json
import os
import sys
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def paths(env):
    return env.get("RELEASE_RECORD") or ".crew/release.json", env.get("RELEASES_LOG") or ".crew/releases.jsonl"


def append(log, line):
    os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_record(path, record):
    """As `jq .` writes it: two-space indent, the shape incident copies verbatim."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def record(env, verdict, held_at, stages, image):
    path, log = paths(env)
    rec = {"version": env.get("CANARY_VERSION", ""), "stable": env.get("STABLE_VERSION", ""),
           "stages": json.loads(stages), "verdict": verdict,
           "held_at": json.loads(held_at) if held_at else None, "image": image}
    write_record(path, rec)
    if verdict != "in-progress":
        append(log, {"kind": "release", "at": now(), "ticket": env.get("RELEASE_TICKET") or None, "record": rec})


def brief(rec):
    lines = [f"# Promotion brief: {rec['version']}", "",
             f"Promote `{rec['version']}` (`{rec['image']}`), replacing stable `{rec['stable']}`.", "", "## Stages"]
    for stage in rec.get("stages") or []:
        lines.append(f"- {stage['pct']}%: {stage['verdict']}")
        lines.extend(f"  - {n}" for n in stage.get("numbers") or [])
    lines += ["", "## Not verified", "- 100% of traffic: not observed yet; that is what this decision starts.",
              "", "Recommendation: GO — every stage passed verify; the numbers above are the evidence."]
    return "\n".join(lines)


def raw(value):
    """A value as `jq -r` prints it."""
    if isinstance(value, str):
        return value
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return json.dumps(value)


def plane(env, status):
    """Why the plane is not the held record, or None when it is."""
    path = paths(env)[0]
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    held_at = rec.get("held_at")
    if held_at is None or held_at is False:
        return f"{path} is held but names no held_at"
    try:
        status = json.loads(status)
    except ValueError:
        status = None
    if not isinstance(status, dict):
        return f"adapters/{env.get('DELIVERY', '')}/status.sh did not print JSON"
    canary = status.get("canary")
    canary = "none" if canary is None or canary is False else raw(canary)
    if canary != raw(rec.get("version")) or raw(status.get("weight")) != raw(held_at):
        return (f"the record holds {raw(rec.get('version'))} at {raw(held_at)}%, the plane has canary "
                f"{canary} at {raw(status.get('weight'))}%; nothing moved")
    return None


def answer(env, said):
    path, log = paths(env)
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    at, by, via = now(), env.get("GO_FOR_LAUNCH_BY") or "unauthenticated", env.get("GO_FOR_LAUNCH_VIA") or "cli"
    if said == "GO":
        rec["promoted"] = {"weight": 100, "at": at, "by": by, "via": via}
    else:
        rec["rejected"] = {"at": at, "by": by, "via": via}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
    append(log, {"kind": "answer", "at": at, "version": rec.get("version"), "answer": said, "by": by, "via": via})


def main(argv, env=None):
    env = os.environ if env is None else env
    cmd = argv[0] if argv else ""
    if cmd == "record" and len(argv) == 5:
        record(env, *argv[1:])
    elif cmd == "brief" and len(argv) == 1:
        with open(paths(env)[0], encoding="utf-8") as fh:
            print(brief(json.load(fh)))
    elif cmd == "plane" and len(argv) == 1:
        why = plane(env, sys.stdin.read())
        if why:
            print(why)
            return 1
    elif cmd == "answer" and len(argv) == 2 and argv[1] in ("GO", "NO-GO"):
        answer(env, argv[1])
    else:
        print("usage: releases.py record VERDICT HELD_AT STAGES IMAGE | brief | plane | answer GO|NO-GO", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
