"""The incident artefact of a triage (docs/adr/0020 §3): stdlib only.

core/triage.sh runs the ops-triage role on an alert; this judges what the
role left and writes `incident.json` = {alert, title, hypotheses (by
rank), proposal: {action: rollback|hold, version, reason}, run}. The role
proposes; nothing here acts on the proposal. Refused: fewer than two
ranked hypotheses, a proposal without file_incident before it, a rollback
of a version the alert did not name.

    python3 core/triage.py alert <alert.json>
    python3 core/triage.py check <alert.json> <out-dir> <incident.json>

Exit 0, or exit 1 with the reason on stdout; `check` prints the incident
on stderr and writes nothing on a refusal.
"""

import json
import os
import sys

SEQUENCES = (["file_incident", "propose_rollback"], ["file_incident", "propose_hold"])


class Refused(Exception):
    pass


def load_alert(path):
    """The alert, which must be a JSON object naming a version."""
    try:
        with open(path, encoding="utf-8") as f:
            alert = json.load(f)
    except OSError:
        raise Refused(f"no alert at {path}") from None
    except ValueError:
        raise Refused(f"{path} is not JSON") from None
    if not isinstance(alert, dict) or not alert.get("version"):
        raise Refused(f"{path} names no version")
    return alert


def hypotheses_of(call):
    """The incident's hypotheses, refused unless at least two carry distinct numeric ranks."""
    hypotheses = (call.get("args") or {}).get("hypotheses") or []
    if len(hypotheses) < 2:
        raise Refused(f"an incident needs at least two ranked hypotheses, got {len(hypotheses)}")
    ranks = [h.get("rank") if isinstance(h, dict) else None for h in hypotheses]
    numeric = all(isinstance(r, (int, float)) and not isinstance(r, bool) for r in ranks)
    if not numeric or len(set(ranks)) != len(ranks):
        raise Refused("hypotheses are not uniquely ranked")
    return sorted(hypotheses, key=lambda h: h["rank"])


def judge(alert, calls, run):
    """The incident document from the role's tool calls, or Refused."""
    names = [c.get("name") if isinstance(c, dict) else None for c in calls]
    if names not in SEQUENCES:
        got = " ".join(str(n) for n in names)
        raise Refused(f"expected file_incident then one proposal, got: {got or 'nothing'}")
    filed, proposed = calls
    hypotheses = hypotheses_of(filed)
    args = proposed.get("args") or {}
    action = "rollback" if proposed["name"] == "propose_rollback" else "hold"
    proposal = {"action": action, "version": args.get("version"), "reason": args.get("reason")}
    if action == "rollback" and proposal["version"] != alert["version"]:
        shown = proposal["version"] or ""
        raise Refused(f'rollback proposed for "{shown}", the alert is about {alert["version"]}')
    title = (filed.get("args") or {}).get("title") or ""
    return {"alert": alert, "title": title, "hypotheses": hypotheses, "proposal": proposal, "run": run}


def interpolated(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def summary(case, doc, path):
    proposal = doc["proposal"]
    lines = [f'[triage] {case}: incident "{doc["title"]}"']
    lines += [f"         {interpolated(h.get('rank'))}. {interpolated(h.get('cause'))} — "
              f"{interpolated(h.get('evidence'))}" for h in doc["hypotheses"]]
    lines.append(f"         proposal: {proposal['action']} {proposal['version'] or ''} — "
                 f"{interpolated(proposal['reason'])}")
    lines.append(f"         written to {path}")
    return lines


def check(alert_path, out_dir, incident_path):
    alert = load_alert(alert_path)
    calls_path = os.path.join(out_dir, "calls.json")
    if not os.path.isfile(calls_path):
        raise Refused("the ops-triage role left no calls.json")
    try:
        with open(calls_path, encoding="utf-8") as f:
            calls = json.load(f)
        with open(os.path.join(out_dir, "run.json"), encoding="utf-8") as f:
            run = json.load(f)
    except OSError as e:
        raise Refused(f"the ops-triage role left no {os.path.basename(e.filename)}") from None
    except ValueError:
        raise Refused("the ops-triage role left calls.json or run.json that is not JSON") from None
    if not isinstance(calls, list):
        raise Refused("the ops-triage role's calls.json is not a list of calls")
    doc = judge(alert, calls, run)
    with open(incident_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    case = os.path.basename(alert_path)
    case = case[:-len(".json")] if case.endswith(".json") and case != ".json" else case
    for line in summary(case, doc, incident_path):
        print(line, file=sys.stderr)


def main(argv):
    try:
        if len(argv) == 2 and argv[0] == "alert":
            load_alert(argv[1])
        elif len(argv) == 4 and argv[0] == "check":
            check(*argv[1:])
        else:
            print("usage: triage.py alert <alert> | check <alert> <out-dir> <incident>")
            return 1
    except Refused as refused:
        print(refused)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
