"""Cost and time per ticket, and the budget (docs/adr/0083): stdlib only.

    python3 core/spend.py report     cost and time per ticket, role and day,
                                     from every ticket's `spend` ledger

The tower imports the rest: the price of a run (`cost`), the ledger
entries a step's result gives (`entries`), the limits of policy/rework.env
(`limits`) and the stop line (`stop`). core/spend.sh is the command's
entry point. A model with no price is "cost unknown", never a guess.
"""

import glob
import json
import os
import re
import subprocess  # nosec B404 - the state store's adapter verb is a script
import sys
from datetime import datetime

PRICES = "profiles/prices.json"
POLICY = "policy/rework.env"
LIMIT_KEYS = ("SPEND_BUDGET_TICKET_USD", "SPEND_BUDGET_DAY_USD")
# The step result keys that carry a role's run (§3), and the role of one
# whose object does not name it.
RUN_FIELDS = (("task", None), ("review", None), ("product", "product"))
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DECIMAL = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


# --- prices ---------------------------------------------------------------


def parse_prices(table):
    """The price entries of a table object; ValueError naming what is wrong."""
    entries = table.get("prices") if isinstance(table, dict) else None
    if not isinstance(entries, list):
        raise ValueError("no `prices` list")
    out = []
    for n, e in enumerate(entries, 1):
        if not isinstance(e, dict):
            raise ValueError(f"price {n} is not an object")
        for key in ("provider", "model"):
            if not isinstance(e.get(key), str) or not e[key]:
                raise ValueError(f"price {n} has no {key}")
        for key in ("input", "output"):
            if not isinstance(e.get(key), (int, float)) or isinstance(e.get(key), bool) or e[key] < 0:
                raise ValueError(f"price {n} ({e['model']}) has no {key} price of 0 or more")
        for key in ("from", "until"):
            if e.get(key) is not None and not (isinstance(e[key], str) and _DAY.match(e[key])):
                raise ValueError(f"price {n} ({e['model']}) has a {key} that is not YYYY-MM-DD")
        out.append(e)
    return out


def load_prices(path=PRICES):
    """(entries, None), or (None, why) when the table cannot be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            return parse_prices(json.load(fh)), None
    except OSError as exc:
        return None, f"no price table {path} ({exc.strerror})"
    except ValueError as exc:
        return None, f"the price table {path} is malformed: {exc}"


def price(prices, provider, model, day):
    for e in prices:
        if e["provider"] == provider and e["model"] == model \
                and (e.get("from") or "") <= day <= (e.get("until") or "9999-12-31"):
            return e
    return None


def cost(run, prices, day):
    """(usd, None) for a run on DAY (YYYY-MM-DD), or (None, why)."""
    if run.get("replayed") is True:
        return 0, None
    if isinstance(run.get("members"), list):
        total = 0
        for m in run["members"]:
            usd, why = cost(m if isinstance(m, dict) else {}, prices, day)
            if usd is None:
                return None, f"member {m.get('id') if isinstance(m, dict) else '?'}: {why}"
            total += usd
        return round(total, 6), None
    provider, model = run.get("provider"), run.get("model")
    if not provider or not model:
        return None, "the run names no provider or model"
    tokens = run.get("tokens") if isinstance(run.get("tokens"), dict) else {}
    tin, tout = tokens.get("input"), tokens.get("output")
    if not all(isinstance(t, int) and not isinstance(t, bool) for t in (tin, tout)):
        return None, "the run reports no input and output tokens"
    if prices is None:
        return None, "no price table"
    p = price(prices, provider, model, day)
    if p is None:
        return None, f"no price for {provider}/{model} on {day} in {PRICES}"
    return round(tin * p["input"] / 1e6 + tout * p["output"] / 1e6, 6), None


# --- the ledger -----------------------------------------------------------


def entries(step, result, attempt, at, path=PRICES):
    """The ledger entries for the runs a step's RESULT carries (§3)."""
    out, prices, unread = [], None, None
    for key, role in RUN_FIELDS:
        run = result.get(key) if isinstance(result, dict) else None
        if not isinstance(run, dict) or "harness" not in run:
            continue
        if key == "product" and run.get("consulted") is False:
            continue
        if prices is None and unread is None:
            prices, unread = load_prices(path)
        usd, why = cost(run, prices, at[:10])
        if usd is None and unread and why == "no price table":
            why = unread
        out.append({"step": step, "attempt": attempt, "role": run.get("role") or role or key,
                    "harness": run.get("harness"), "provider": run.get("provider"), "model": run.get("model"),
                    "replayed": run.get("replayed") is True, "tokens": run.get("tokens"),
                    "duration_s": run.get("duration_s"), "cost_usd": usd, "cost_unknown": why, "at": at})
    return out


# --- the budget -----------------------------------------------------------


def parse_limits(text):
    """{key: float or None}; ValueError naming the key for a malformed value."""
    got = {}
    for raw in text.splitlines():
        m = _KEY_LINE.match(raw.strip())
        if m and m.group(1) in LIMIT_KEYS:
            got[m.group(1)] = m.group(2).strip()
    out = {}
    for key in LIMIT_KEYS:
        value = got.get(key, "")
        if value == "":
            out[key] = None
        elif not _DECIMAL.match(value) or float(value) <= 0:
            raise ValueError(f"{POLICY}: {key}={value!r} is neither empty nor a positive decimal number of USD")
        else:
            out[key] = float(value)
    return out


def limits(path=POLICY):
    """The limits of PATH; a missing file has none."""
    try:
        with open(path, encoding="utf-8") as fh:
            return parse_limits(fh.read())
    except OSError:
        return {key: None for key in LIMIT_KEYS}


def ledger(doc):
    return [e for e in (doc.get("spend") or []) if isinstance(e, dict)] if isinstance(doc, dict) else []


def on_day(docs, day):
    """Every ledger entry of DOCS ({id: doc}) dated DAY (UTC)."""
    return [e for doc in docs.values() for e in ledger(doc) if str(e.get("at") or "")[:10] == day]


def stop(mine, today, lim):
    """The one-line reason the next attempt is not launched, or ""."""
    for key, counted, what in (("SPEND_BUDGET_TICKET_USD", mine, "this ticket"),
                               ("SPEND_BUDGET_DAY_USD", today, "today")):
        limit = lim.get(key)
        if limit is None:
            continue
        unknown = [e for e in counted if e.get("cost_usd") is None]
        if unknown:
            e = unknown[0]
            return (f"spend budget: {key}=${limit:.2f} cannot be checked, {len(unknown)} run(s) of {what} "
                    f"of cost unknown ({e.get('role')}, {e.get('step')}: {e.get('cost_unknown')}); "
                    "the next attempt is not launched")
        spent = sum(e["cost_usd"] for e in counted)
        if spent >= limit:
            return (f"spend budget: {what} spent ${spent:.2f}, at or over {key}=${limit:.2f}; "
                    "the next attempt is not launched")
    return ""


# --- the report -----------------------------------------------------------


def when(at):
    try:
        return datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return None


def add(row, e):
    row["runs"] += 1
    if e.get("cost_usd") is None:
        row["unknown"] += 1
    else:
        row["cost_usd"] = round(row["cost_usd"] + e["cost_usd"], 6)
    # A replayed run reports the recorded run's duration, not its own (§5).
    if "agent_s" in row and e.get("replayed") is not True and isinstance(e.get("duration_s"), (int, float)):
        row["agent_s"] += e["duration_s"]


def report(docs):
    """{tickets, roles, days, total} from DOCS ({id: doc}) (§5)."""
    out = {"tickets": {}, "roles": {}, "days": {}, "total": {"cost_usd": 0, "runs": 0, "unknown": 0}}
    for tid, doc in docs.items():
        history = [h for h in (doc.get("history") or []) if isinstance(h, dict)]
        first, last = (when(history[0].get("at")), when(history[-1].get("at"))) if history else (None, None)
        row = {"cost_usd": 0, "runs": 0, "unknown": 0, "agent_s": 0,
               "elapsed_s": round((last - first).total_seconds()) if first and last else None}
        for e in ledger(doc):
            add(row, e)
            add(out["roles"].setdefault(e.get("role") or "unknown",
                                        {"cost_usd": 0, "runs": 0, "unknown": 0, "agent_s": 0}), e)
            add(out["days"].setdefault(str(e.get("at") or "")[:10] or "unknown",
                                       {"cost_usd": 0, "runs": 0, "unknown": 0}), e)
            add(out["total"], e)
        out["tickets"][tid] = row
    return out


def hms(seconds):
    if seconds is None:
        return "unknown"
    seconds = int(seconds)
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m{seconds % 60:02d}s"


def money(row):
    tail = f", {row['unknown']} of cost unknown" if row["unknown"] else ""
    return f"${row['cost_usd']:.2f} over {row['runs']} run(s){tail}"


def store_docs(store, tickets_dir):
    """{id: doc} for every ticket of TICKETS_DIR the store holds; ValueError on a store error."""
    docs = {}
    for path in sorted(glob.glob(os.path.join(tickets_dir, "*.md"))):
        tid = os.path.basename(path)[:-3]
        got = subprocess.run(["sh", f"adapters/{store}/get.sh", "tickets", tid], capture_output=True,
                             text=True, check=False)  # nosec B603 B607 - an argv list, the store's verb
        if got.returncode == 1:
            continue  # the tower never opened this ticket
        if got.returncode != 0:
            raise ValueError(f"adapters/{store}/get.sh tickets {tid} exited {got.returncode}: "
                             f"{got.stderr.strip().splitlines()[-1] if got.stderr.strip() else 'no reason'}")
        try:
            doc = json.loads(got.stdout)
        except ValueError:
            raise ValueError(f"adapters/{store}/get.sh printed no JSON for {tid}") from None
        if isinstance(doc, dict):
            docs[tid] = doc
    return docs


def main(argv, env=None):
    env = os.environ if env is None else env
    if argv != ["report"]:
        print("usage: spend.py report", file=sys.stderr)
        return 2
    store = env.get("STATE_STORE")
    if not store:
        print("STATE_STORE not set; run this via ./go spend")
        return 1
    try:
        docs = store_docs(store, env.get("TICKETS_DIR") or "tickets")
    except ValueError as exc:
        print(exc)
        return 1
    got = report(docs)

    def say(line):
        print(f"[spend] {line}", file=sys.stderr)

    for tid, row in got["tickets"].items():
        say(f"ticket {tid}: {money(row)}; agents {hms(row['agent_s'])}, elapsed {hms(row['elapsed_s'])}")
    for role, row in sorted(got["roles"].items()):
        say(f"role {role}: {money(row)}; {hms(row['agent_s'])}")
    for day, row in sorted(got["days"].items()):
        say(f"day {day}: {money(row)}")
    t = got["total"]
    print(f"{len(got['tickets'])} tickets, {t['runs']} runs, ${t['cost_usd']:.2f} known, {t['unknown']} of cost unknown")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
