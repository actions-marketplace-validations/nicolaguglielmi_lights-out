"""The delivery measures, from the logbook (docs/adr/0082): stdlib only.

    python3 core/dora.py --logbook <file> --window-days <n> --out <file>

Reads the logbook's `releases` and `tickets`, writes {schema, window_days,
from, to, measures} to --out, one line per measure on stderr, and prints
on stdout how many of the four were measured. A logbook it cannot read, or
a window that is not a whole number of 1 or more, is exit 1 with the
reason on stdout. core/dora.sh is its entry point.
"""

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

SCHEMA = "dora/1"
KEYS = ("deployment_frequency", "lead_time", "change_fail_rate", "recovery_time")


def when(value):
    """A logbook time as an aware datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def stamp(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def unread(source):
    """The logbook's error for an unread source, else None (docs/adr/0047 §2)."""
    if isinstance(source, dict) and source.get("ok") is False:
        return str(source.get("error") or "unreadable")
    return None


def no(why):
    return {"measured": False, "why": why}


def answer_of(release, end):
    """(answer, at) when the release was answered by END, else (None, None)."""
    a = release.get("answer")
    if not isinstance(a, dict):
        return None, None
    at = when(a.get("at"))
    if at is None or at > end:
        return None, None
    return a.get("answer"), at


def measures(book, window_days, now):
    end = when(now) if isinstance(now, str) else now
    start = end - timedelta(days=window_days)
    out = {"schema": SCHEMA, "window_days": window_days, "from": stamp(start), "to": stamp(end), "measures": {}}
    m = out["measures"]
    releases, tickets = book.get("releases"), book.get("tickets")
    rel_err, tick_err = unread(releases), unread(tickets)
    if rel_err:
        why = f"the logbook could not read the releases: {rel_err}"
        m.update({k: no(why) for k in KEYS})
        return out
    timed = [r for r in releases or [] if isinstance(r, dict) and when(r.get("at"))]
    first = {}
    if not tick_err:
        for t in tickets or []:
            history = t.get("history") if isinstance(t, dict) else None
            if history and isinstance(history[0], dict) and when(history[0].get("at")):
                first[t.get("id")] = when(history[0]["at"])

    def inside(moment):
        return moment is not None and start <= moment <= end

    # Deployment frequency: GO answers in the window.
    gone = []
    for r in timed:
        said, at = answer_of(r, end)
        if said == "GO" and inside(at):
            gone.append((r, at))
    m["deployment_frequency"] = {"measured": True, "count": len(gone), "per_day": len(gone) / window_days}

    # Lead time: request (or open) to the GO, for releases that name a ticket.
    samples, without = [], 0
    for r, at in gone:
        if not r.get("ticket"):
            without += 1
        elif r.get("ticket") in first:
            samples.append((at - first[r["ticket"]]).total_seconds())
    if tick_err:
        m["lead_time"] = no(f"the logbook could not read the tickets: {tick_err}")
    elif samples:
        m["lead_time"] = {"measured": True, "median_s": round(statistics.median(samples)), "n": len(samples),
                          "without_ticket": without}
    else:
        m["lead_time"] = no("no release of a ticket reached 100% in the window")

    # Change fail rate: failed over decided, releases by their own time.
    decided, failed, pending = 0, [], 0
    for r in timed:
        if not inside(when(r["at"])):
            continue
        said, at = answer_of(r, end)
        if r.get("verdict") == "rolled-back":
            decided += 1
            failed.append((r, when(r["at"])))
        elif said in ("GO", "NO-GO"):
            decided += 1
            if said == "NO-GO":
                failed.append((r, at))
        else:
            pending += 1
    if decided:
        m["change_fail_rate"] = {"measured": True, "rate": len(failed) / decided, "failed": len(failed),
                                 "decided": decided, "pending": pending}
    else:
        m["change_fail_rate"] = no("no release was decided in the window")

    # Recovery time: the failed canary's last stage start to its rollback.
    spans, unmeasured = [], 0
    for r, back in failed:
        stages = r.get("stages") or []
        began = when(stages[-1].get("started_at")) if stages and isinstance(stages[-1], dict) else None
        if began is None:
            unmeasured += 1
        else:
            spans.append((back - began).total_seconds())
    if spans:
        m["recovery_time"] = {"measured": True, "median_s": round(statistics.median(spans)), "n": len(spans),
                              "unmeasured": unmeasured}
    elif failed:
        m["recovery_time"] = no("no failed release in the window carries its last stage's started_at "
                                "(docs/adr/0080 adds it)")
    else:
        m["recovery_time"] = no("no release failed in the window")
    return out


def duration(seconds):
    if seconds < 3600:
        return f"{seconds / 60:.0f} min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} days"


def lines(result):
    m = result["measures"]

    def said(key, text):
        label = key.replace("_", " ")
        return f"[dora] {label}: " + (text if m[key]["measured"] else f"not measured — {m[key]['why']}")

    f, lt, cfr, rt = (m[k] for k in KEYS)
    return [
        f"[dora] window: {result['window_days']} days, {result['from']} to {result['to']}",
        said("deployment_frequency", f"{f.get('count')} promoted to 100%, {f.get('per_day', 0):.3f} per day"),
        said("lead_time", f"median {duration(lt.get('median_s', 0))} from request to 100% over {lt.get('n')} "
                          f"release(s), {lt.get('without_ticket')} without a ticket"),
        said("change_fail_rate", f"{cfr.get('rate', 0):.0%}: {cfr.get('failed')} of {cfr.get('decided')} decided "
                                 f"release(s) rolled back, {cfr.get('pending')} pending"),
        said("recovery_time", f"median {duration(rt.get('median_s', 0))} from the failing stage's start to the "
                              f"rollback over {rt.get('n')} release(s), {rt.get('unmeasured')} unmeasured"),
    ]


def main(argv):
    p = argparse.ArgumentParser(prog="dora.py")
    p.add_argument("--logbook", required=True)
    p.add_argument("--window-days", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--now", default=None)
    a = p.parse_args(argv)
    raw = a.window_days
    if not raw.isdigit() or int(raw) < 1:
        print(f"WINDOW_DAYS={raw!r} is not a whole number of days, 1 or more")
        return 1
    try:
        with open(a.logbook, encoding="utf-8") as fh:
            book = json.load(fh)
    except OSError as exc:
        print(f"cannot read the logbook {a.logbook}: {exc.strerror}")
        return 1
    except ValueError:
        print(f"the logbook {a.logbook} is not JSON")
        return 1
    if not isinstance(book, dict):
        print(f"the logbook {a.logbook} is not a JSON object")
        return 1
    now = when(a.now) if a.now else datetime.now(timezone.utc).replace(microsecond=0)
    result = measures(book, int(raw), now)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for line in lines(result):
        print(line, file=sys.stderr)
    print(sum(1 for k in KEYS if result["measures"][k]["measured"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
