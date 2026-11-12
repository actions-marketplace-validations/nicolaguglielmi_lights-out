"""The dast gate's verdict, canary against stable (docs/adr/0072 §3): stdlib only, no process.

    python3 core/dastdiff.py diff <stable-report> <canary-report>

Each report is ZAP's traditional JSON report (`zap-baseline.py -J`). An alert
is the tuple (plugin id, method, path without query), one per instance, the
scheme, host and port stripped: the stable and the canary answer at
different addresses. Every risk level counts (no severity floor, ADR 0015
§4). Exit 0 with the number of the canary's tuples the stable also has,
exit 1 with the number it has and the stable does not (listed on stderr),
or exit 2 with the reason a report cannot be read: a canary that cannot be
judged (ADR 0066).
"""

import json
import sys
from urllib.parse import urlsplit

USAGE = "usage: dastdiff.py diff <stable-report> <canary-report>"


class Unreadable(Exception):
    """A report that is not ZAP's JSON; the message says which side and why."""


def alerts(path, side):
    """{(pluginid, method, path): alert name} of one report."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        raise Unreadable(f"the {side} report cannot be read: {e}") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("site"), list):
        raise Unreadable(f"the {side} report has no site list")
    out = {}
    for site in doc["site"]:
        found = site.get("alerts", []) if isinstance(site, dict) else None
        if not isinstance(found, list):
            raise Unreadable(f"the {side} report has a site without an alerts list")
        for alert in found:
            if not isinstance(alert, dict) or not isinstance(alert.get("pluginid"), str) \
                    or not isinstance(alert.get("instances"), list):
                raise Unreadable(f"the {side} report has an alert without pluginid or instances")
            for inst in alert["instances"]:
                if not isinstance(inst, dict) or not isinstance(inst.get("uri"), str):
                    raise Unreadable(f"the {side} report has an instance without a uri")
                key = (alert["pluginid"], str(inst.get("method", "")), urlsplit(inst["uri"]).path or "/")
                out.setdefault(key, str(alert.get("alert", "")))
    return out


def main(argv):
    if len(argv) != 3 or argv[0] != "diff":
        print(USAGE, file=sys.stderr)
        return 2
    try:
        stable = alerts(argv[1], "stable")
        canary = alerts(argv[2], "canary")
    except Unreadable as e:
        print(e)
        return 2
    new = sorted(k for k in canary if k not in stable)
    inherited = sorted(k for k in canary if k in stable)
    if inherited:
        print(f"dast: {len(inherited)} alert(s) the stable raises too, not gating:", file=sys.stderr)
        for k in inherited:
            print(f"  {k[0]} {k[1]} {k[2]} {canary[k]}", file=sys.stderr)
    if new:
        print(f"dast: {len(new)} alert(s) the canary raises and the stable does not:", file=sys.stderr)
        for k in new:
            print(f"  {k[0]} {k[1]} {k[2]} {canary[k]}", file=sys.stderr)
        print(len(new))
        return 1
    print(len(inherited))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
