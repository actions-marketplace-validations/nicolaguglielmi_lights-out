"""The console, frozen (docs/adr/0089): stdlib only.

    python3 core/freeze.py --logbook <file> --out <file> [--page console/index.html] [--label <text>] [--prefix <text>]

Writes the console's own page with the logbook inlined, a fetch of its own
that answers the page's two reads from it and refuses every other request,
a Content-Security-Policy that lets nothing leave the file, and a banner that
says it is a read-only snapshot. The page's screens are never read: whatever
the console renders from the logbook is what the snapshot shows.

No clock of its own: equal inputs give equal bytes. Prints the out path on
success; one line and exit 1 on a refusal.
"""

import argparse
import html
import json
import os
import sys

BEGIN, END = "<!-- frozen: begin -->", "<!-- frozen: end -->"
REFUSAL = "a frozen snapshot: nothing behind it, nothing is sent"
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "img-src data:; font-src data:; connect-src 'none'; form-action 'none'")
STYLE = """#frozen-banner{position:sticky;top:0;z-index:1000;margin:0;padding:8px 16px;font:14px/1.4 system-ui,sans-serif;
background:#fff8c5;color:#3b2300;border-bottom:1px solid #d4a72c}
#frozen-banner b{font-weight:700}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) #frozen-banner{background:#2b2408;color:#f5e6a8;border-color:#7d6514}}
:root[data-theme="dark"] #frozen-banner{background:#2b2408;color:#f5e6a8;border-color:#7d6514}"""
SHIM = """(function () {
  var book = document.getElementById("frozen-logbook").textContent;
  var con = document.getElementById("frozen-console").textContent;
  var refused = JSON.stringify({error: "%s"});
  function answer(body, status, extra) {
    var headers = {"Content-Type": "application/json"};
    for (var k in extra || {}) headers[k] = extra[k];
    return Promise.resolve(new Response(body, {status: status, headers: headers}));
  }
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : input.url;
    var path = new URL(url, "http://frozen.invalid/").pathname;
    var method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
    if (method === "GET" && path === "/v1/logbook.json") return answer(book, 200, {"ETag": '"frozen"'});
    if (method === "GET" && path === "/v1/console.json") return answer(con, 200);
    return answer(refused, 403);
  };
})();""" % REFUSAL


class Refused(Exception):
    """The freeze will not run; the message is the reason."""


def _json(value):
    # §1: no value can close the script element it sits in.
    return json.dumps(value, ensure_ascii=False, sort_keys=False).replace("<", "\\u003c")


def last_event(book):
    """§3: the latest `at` of the tickets' history, the releases and their answers."""
    times = []
    for t in book.get("tickets") or []:
        times += [h.get("at") for h in t.get("history") or [] if isinstance(h, dict)]
    for r in book.get("releases") if isinstance(book.get("releases"), list) else []:
        times.append(r.get("at"))
        times.append((r.get("answer") or {}).get("at"))
    times = [x for x in times if isinstance(x, str) and x]
    return max(times) if times else None


def default_label(book):
    commit = str((book.get("source") or {}).get("commit") or "?")[:7]
    return f"logbook of {commit}, last event {last_event(book) or '?'}"


def freeze(page, logbook_text, label=None, prefix=None):
    """The frozen page, from the console's page and the logbook's text."""
    try:
        book = json.loads(logbook_text)
    except ValueError as e:
        raise Refused(f"the logbook is not JSON: {e}") from e
    schema = book.get("schema") if isinstance(book, dict) else None
    if not isinstance(schema, str) or not schema.startswith("lights-out/logbook/"):
        raise Refused(f"the logbook's schema is {schema}, not lights-out/logbook/*")
    head = page.find("<head")
    body = page.find("<body")
    if head < 0 or body < 0:
        raise Refused("the page has no <head> or no <body>")
    label = label if label is not None else default_label(book)
    if prefix:
        label = f"{prefix}, {label}"
    con = {"mode": "snapshot", "auth": "public", "identity": None, "can_launch": False,
           "reason": "a frozen snapshot: no console behind it", "read_at": last_event(book), "read_error": None,
           "snapshot": label}
    block = (f'{BEGIN}<meta http-equiv="Content-Security-Policy" id="frozen-csp" content="{CSP}">\n'
             f'<style id="frozen-style">{STYLE}</style>\n'
             f'<script type="application/json" id="frozen-logbook">{_json(book)}</script>\n'
             f'<script type="application/json" id="frozen-console">{_json(con)}</script>\n'
             f'<script id="frozen-shim">{SHIM}</script>\n{END}')
    banner = (f'{BEGIN}<div id="frozen-banner" role="note"><b>Frozen snapshot</b> of {html.escape(label)}. '
              'Read-only: no console, tower or plane behind it, and nothing on this page can be sent.</div>\n'
              f'{END}')
    first_script = page.find("<script", head)
    at = first_script if 0 <= first_script < body else page.find("</head>", head)
    if at < 0:
        raise Refused("the page has no <head> or no <body>")
    body_end = page.index(">", body) + 1
    return page[:at] + block + page[at:body_end] + banner + page[body_end:]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--logbook", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--page", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                   "console", "index.html"))
    ap.add_argument("--label")
    ap.add_argument("--prefix", help="put before the label, then a comma (docs/adr/0089 §5)")
    a = ap.parse_args(argv)
    try:
        try:
            with open(a.logbook, encoding="utf-8") as f:
                text = f.read()
            with open(a.page, encoding="utf-8") as f:
                page = f.read()
        except OSError as e:
            raise Refused(f"{e.filename}: {e.strerror}") from e
        out = freeze(page, text, a.label, a.prefix)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(out)
    except Refused as e:
        print(e)
        return 1
    except OSError as e:
        print(f"{a.out}: {e.strerror}")
        return 1
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
