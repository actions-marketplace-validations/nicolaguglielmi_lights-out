"""The provider scoreboard (docs/adr/0088): stdlib only.

    python3 core/scoreboard.py --data <dataset> [--logbook <file> ...] --html <out>

Rows, one per ticket and dev-worker (provider, harness, model), from a
curated dataset (lights-out/scoreboard-data/1, every row naming its
handoff and run) and from run logbooks (ADR 0047 §2, read as ./go dora
reads them). Grouped by that triple: tickets, merged, merged at the first
attempt, reworks, NO-GOs by gate and reason, budget stops, tokens and cost
per ticket. A figure no source gives is "not recorded", never filled in.

On success prints `<groups>\t<not run>\t<tickets>` on stdout, one line per
group on stderr, and writes the page; on a refusal prints the one-line
reason on stdout and exits 1. core/scoreboard.sh turns that into the
gate contract's line.
"""

import argparse
import html
import json
import os
import re
import sys

SCHEMA = "lights-out/scoreboard-data/1"
BASES = ("ledger", "list", "cached")
BOUNDS = ("at most", "about", "exactly")
BUDGET_STOPS = ("TOKEN_BUDGET", "SPEND_BUDGET")
STOPS = {"budget": "SPEND_BUDGET", "cap": "REWORK_CAP"}
NOGO = re.compile(r"^NO-GO: (\S+) — (.*)$")


class Refused(Exception):
    """A record the scoreboard will not show; the message is the reason."""


def parse_nogo(line):
    """§4: `NO-GO: <gate> — <reason>`; the tower's summary gives its inner gate."""
    m = NOGO.match(line)
    if not m:
        return {"gate": "unparsed", "reason": line}
    gate, reason = m.groups()
    inner = re.match(r"^(\S+): (NO-GO: .*)$", reason)
    if gate == "gates" and inner:
        return parse_nogo(inner.group(2))
    return {"gate": gate, "reason": reason}


def _key(r):
    return (r["provider"], r["harness"], r["model"])


def _need(cond, why):
    if not cond:
        raise Refused(why)


def load_dataset(data):
    """§2, §5: rows, totals, not_run and scope of a dataset, or Refused."""
    _need(isinstance(data, dict) and data.get("schema") == SCHEMA,
          f"schema is not {SCHEMA}: {data.get('schema') if isinstance(data, dict) else type(data).__name__}")
    scope = data.get("scope")
    _need(isinstance(scope, str) and scope.strip(), "the dataset has no scope")
    rows = data.get("rows") or []
    for r in rows:
        src = r.get("source") or {}
        for part in ("handoff", "run"):
            _need(isinstance(src.get(part), str) and src[part].strip(),
                  f"row {r.get('ticket')} ({r.get('provider')}) has no source.{part}: a number with no source does not enter")
    groups = {_key(r) for r in rows}
    totals = data.get("totals") or []
    for t in totals:
        _need(_key(t) in groups, f"a total for {'/'.join(map(str, _key(t)))}, a group with no rows")
        _need(t.get("basis") in BASES and t.get("bound") in BOUNDS,
              f"a total for {t.get('provider')} has basis {t.get('basis')} or bound {t.get('bound')} outside {BASES} {BOUNDS}")
    not_run = data.get("not_run") or []
    run = {r["provider"] for r in rows}
    for n in not_run:
        _need(n.get("provider") not in run, f"{n.get('provider')} is both run and not run")
    return rows, totals, not_run, scope


def _tokens(tasks):
    runs = []
    for t in tasks:
        runs.extend(t.get("members") or [t])
    tin = sum((r.get("tokens") or {}).get("input") or 0 for r in runs)
    tout = sum((r.get("tokens") or {}).get("output") or 0 for r in runs)
    return runs, {"input": tin, "output": tout, "cached": None}


def from_logbook(book, name):
    """§3: rows from a run logbook, and how many tickets only replayed."""
    rows, replayed = [], 0
    commit = (book.get("source") or {}).get("commit") or "?"
    spend = (book.get("spend") or {}).get("tickets") or {}
    for t in book.get("tickets") or []:
        tasks = [x for x in t.get("tasks") or [] if isinstance(x, dict)]
        if not tasks:
            continue
        runs, tokens = _tokens(tasks)
        if all(r.get("replayed") for r in runs):
            replayed += 1
            continue
        last = tasks[-1]
        if last.get("members"):
            members = last["members"]
            provider = "+".join(sorted({m.get("provider") for m in members if m.get("provider")}))
            model = "+".join(sorted({m.get("model") for m in members if m.get("model")}))
            harness = "network"
        else:
            provider, harness, model = last.get("provider"), last.get("harness"), last.get("model")
        merged = bool((t.get("merge") or {}).get("sha"))
        nogos = [parse_nogo(x["line"]) for x in t.get("rework") or [] if str(x.get("line") or "").startswith("NO-GO:")]
        final = (t.get("ci") or {}).get("line") or ""
        if not merged and final.startswith("NO-GO:"):
            nogos.append(parse_nogo(final))
        outcome = t.get("outcome") or {}
        stop = {"kind": STOPS.get(outcome["stop"], outcome["stop"]), "line": outcome.get("line")} if outcome.get("stop") else None
        rows.append({
            "ticket": t.get("id"), "provider": provider, "harness": harness, "model": model,
            "merged": merged, "attempts": t.get("attempt") or 0, "reworks": len(t.get("rework") or []),
            "nogos": nogos, "stop": stop, "tokens": tokens,
            "cost_usd": {"ledger": (spend.get(t.get("id")) or {}).get("cost_usd"), "list": None, "cached": None},
            "source": {"handoff": f"logbook {name}", "run": f"{commit} tickets/{t.get('id')}"},
        })
    return rows, replayed


def board(rows, totals):
    """§6: one group per (provider, harness, model), in first-seen order."""
    groups = []
    for key in dict.fromkeys(_key(r) for r in rows):
        mine = [r for r in rows if _key(r) == key]
        n = len(mine)
        nogos = {}
        for r in mine:
            for x in r.get("nogos") or []:
                nogos.setdefault(x["gate"], []).append(x["reason"])
        counted = [r["tokens"] for r in mine
                   if (r.get("tokens") or {}).get("input") is not None and r["tokens"].get("output") is not None]
        tokens = {"value": round(sum(t["input"] + t["output"] for t in counted) / len(counted)), "over": len(counted)} \
            if counted else None
        mytotals = [t for t in totals if _key(t) == key]
        cost = {}
        for basis in BASES:
            total = [t for t in mytotals if t["basis"] == basis]
            values = [(r.get("cost_usd") or {}).get(basis) for r in mine]
            if total:
                cost[basis] = {"usd": round(total[0]["usd"] / n, 6), "bound": total[0]["bound"]}
            elif all(v is not None for v in values):
                cost[basis] = {"usd": round(sum(values) / n, 6), "bound": "exactly"}
            else:
                cost[basis] = None
        groups.append({
            "provider": key[0], "harness": key[1], "model": key[2], "tickets": n,
            "merged": sum(1 for r in mine if r.get("merged")),
            "first_attempt": sum(1 for r in mine if r.get("merged") and not r.get("reworks")),
            "reworks": sum(r.get("reworks") or 0 for r in mine),
            "nogos": nogos,
            "budget_stops": sum(1 for r in mine if (r.get("stop") or {}).get("kind") in BUDGET_STOPS),
            "tokens_per_ticket": tokens, "cost_per_ticket": cost,
            "footnotes": [t["note"] for t in mytotals if t.get("note")],
        })
    return groups


def _usd(c):
    if not c:
        return "not recorded"
    prefix = {"at most": "≤ ", "about": "~"}.get(c["bound"], "")
    return f"{prefix}${c['usd']:.2f}"


def _name(g):
    return f"{g['provider']} · {g['harness']} · {g['model']}"


def lines(groups, not_run, scope, replayed):
    """§7: the scope, one line per group, one per provider not run."""
    out = [f"scope: {scope}"]
    for g in groups:
        nogo = ", ".join(f"{k} {len(v)}" for k, v in g["nogos"].items()) or "none"
        tok = f"{g['tokens_per_ticket']['value']:,} tokens per ticket" if g["tokens_per_ticket"] else "tokens not recorded"
        cost = ", ".join(f"{b} {_usd(g['cost_per_ticket'][b])}" for b in BASES)
        out.append(f"{_name(g)}: {g['tickets']} tickets, {g['merged']} merged, {g['first_attempt']} at the first attempt, "
                   f"{g['reworks']} reworks, NO-GO {nogo}, {g['budget_stops']} budget stops; {tok}; per ticket {cost}")
    for n in not_run:
        out.append(f"{n['provider']} · {n['harness']}: not run — {n['why']}")
    if replayed:
        out.append(f"{replayed} replayed ticket(s) not scored: no model was asked")
    return out


CSS = """
:root{--bg:#ffffff;--fg:#1a1f24;--muted:#4a545e;--line:#d0d7de;--card:#f6f8fa;--go:#116329;--nogo:#a40e26;--warn:#7d4e00;--link:#0550ae}
@media (prefers-color-scheme: dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#9da7b3;--line:#30363d;--card:#161b22;--go:#56d364;--nogo:#ff7b72;--warn:#e3b341;--link:#79c0ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;margin:0 0 8px}h2{font-size:19px;margin:36px 0 10px}
p{margin:8px 0;max-width:75ch}.muted{color:var(--muted)}
a{color:var(--link)}code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace}
.scope{border:1px solid var(--line);background:var(--card);border-radius:8px;padding:12px 16px}
.wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.go{color:var(--go);font-weight:600}.nogo{color:var(--nogo);font-weight:600}.stop{color:var(--warn);font-weight:600}
.src{font-size:12px;color:var(--muted)}
sup a{text-decoration:none}
"""


def _e(s):
    return html.escape(str(s), quote=True)


def page(groups, not_run, scope, rows, replayed, data_name):
    """§7: one self-contained page, no script, no external resource."""
    notes, out = [], []
    w = out.append
    w('<!doctype html><html lang="en"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width,initial-scale=1">'
      '<meta name="color-scheme" content="light dark">'
      '<title>Provider scoreboard · lights-out</title>'
      f'<style>{CSS}</style></head><body><main>')
    w('<p class="muted"><a href="../">lights-out</a></p><h1>Provider scoreboard</h1>')
    w(f'<p class="scope"><strong>Scope.</strong> {_e(scope)} One run per ticket and provider, so there is no variance '
      'to show. This is not a benchmark: it says what happened on these tickets, NO-GOs and budget stops included, '
      'and where each number comes from.</p>')
    w(f'<p class="muted">Built by <code>./go scoreboard</code> (docs/adr/0088) from <code>{_e(data_name)}</code>.</p>')
    w('<h2>Per provider and harness</h2><div class="wrap"><table><thead><tr><th>Provider · harness · model</th>'
      '<th>Tickets</th><th>Merged</th><th>At the first attempt</th><th>Reworks</th><th>NO-GOs</th><th>Budget stops</th>'
      '<th>Tokens per ticket</th><th>Cost per ticket</th></tr></thead><tbody>')
    for g in groups:
        nogo = sum(len(v) for v in g["nogos"].values())
        refs = []
        for note in g["footnotes"]:
            notes.append(note)
            refs.append(f'<a href="#note-{len(notes)}" id="ref-{len(notes)}">{len(notes)}</a>')
        refs = f'<sup>{",".join(refs)}</sup>' if refs else ""
        cost = "<br>".join(f"{_e(_usd(g['cost_per_ticket'][b]))} <span class=\"muted\">{b}</span>" for b in BASES)
        tok = f"{g['tokens_per_ticket']['value']:,}" if g["tokens_per_ticket"] else "not recorded"
        w(f'<tr><td>{_e(_name(g))}</td><td class="n">{g["tickets"]}</td><td class="n go">{g["merged"]}</td>'
          f'<td class="n">{g["first_attempt"]}</td><td class="n">{g["reworks"]}</td>'
          f'<td class="n{" nogo" if nogo else ""}">{nogo}</td><td class="n{" stop" if g["budget_stops"] else ""}">'
          f'{g["budget_stops"]}</td><td class="n">{tok}</td><td class="n">{cost}{refs}</td></tr>')
    for n in not_run:
        w(f'<tr><td>{_e(n["provider"])} · {_e(n["harness"])}</td><td colspan="8"><strong>not run</strong> — '
          f'{_e(n["why"])} <span class="src">({_e(n["source"])})</span></td></tr>')
    w('</tbody></table></div>')
    w('<p class="muted">Tokens are the dev-worker\'s, over every launch of the ticket, input counting cache reads. '
      'A cost is per ticket: a total over the group\'s tickets, with the bound its source gave it, or not recorded.</p>')
    if notes:
        w('<ol class="muted">' + "".join(f'<li id="note-{i}">{_e(x)} <a href="#ref-{i}">↩</a></li>'
                                         for i, x in enumerate(notes, 1)) + '</ol>')
    w('<h2>NO-GOs, by gate and reason</h2>')
    any_nogo = False
    for g in groups:
        for gate, reasons in g["nogos"].items():
            any_nogo = True
            w(f'<p><span class="nogo">NO-GO: {_e(gate)}</span> × {len(reasons)} — {_e(_name(g))}: '
              + "; ".join(_e(r) for r in reasons) + '</p>')
    if not any_nogo:
        w('<p class="muted">No gate said NO-GO.</p>')
    w('<h2>Every ticket, with its source</h2><div class="wrap"><table><thead><tr><th>Ticket</th><th>Provider</th>'
      '<th>Outcome</th><th>Attempts</th><th>Tokens in / out</th><th>Source</th></tr></thead><tbody>')
    for r in rows:
        if r.get("merged"):
            outcome = '<span class="go">merged</span>'
        elif r.get("stop"):
            outcome = f'<span class="stop">stopped: {_e(r["stop"]["kind"])}</span>'
        else:
            outcome = '<span class="nogo">not merged</span>'
        for x in r.get("nogos") or []:
            outcome += f'<br><span class="nogo">NO-GO: {_e(x["gate"])}</span> {_e(x["reason"])}'
        t = r.get("tokens") or {}
        tok = (f'{t["input"]:,} / {t["output"]:,}' if t.get("input") is not None and t.get("output") is not None
               else "not recorded")
        w(f'<tr><td>{_e(r["ticket"])}</td><td>{_e(r["provider"])} · {_e(r["harness"])}</td><td>{outcome}</td>'
          f'<td class="n">{r.get("attempts", 0)}</td><td class="n">{tok}</td>'
          f'<td class="src">{_e(r["source"]["handoff"])}<br>{_e(r["source"]["run"])}</td></tr>')
    w('</tbody></table></div>')
    if replayed:
        w(f'<p class="muted">{replayed} replayed ticket(s) not scored: no model was asked.</p>')
    w('</main></body></html>\n')
    return "".join(out)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise Refused(f"{path}: {e.strerror}") from e
    except ValueError as e:
        raise Refused(f"{path} is not JSON: {e}") from e


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--logbook", action="append", default=[])
    ap.add_argument("--html", required=True)
    a = ap.parse_args(argv)
    try:
        rows, totals, not_run, scope = load_dataset(_read(a.data))
        replayed = 0
        for book in a.logbook:
            more, r = from_logbook(_read(book), book)
            rows, replayed = rows + more, replayed + r
        groups = board(rows, totals)
        text = page(groups, not_run, scope, rows, replayed, a.data)
        os.makedirs(os.path.dirname(os.path.abspath(a.html)), exist_ok=True)
        with open(a.html, "w", encoding="utf-8") as f:
            f.write(text)
    except Refused as e:
        print(e)
        return 1
    except OSError as e:
        print(f"{a.html}: {e.strerror}")
        return 1
    for line in lines(groups, not_run, scope, replayed):
        print(f"[scoreboard] {line}", file=sys.stderr)
    print(f"{len(groups)}\t{len(not_run)}\t{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
