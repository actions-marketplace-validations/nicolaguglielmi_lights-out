#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""console-ui: the console's interactions, proved in a browser (docs/adr/0059 §5).

    python3 ci/console-ui.py

Prints exactly one line on stdout, as every gate does (CLAUDE.md): `GO:
console-ui` or `NO-GO: console-ui — <why>`, exit 0 or 1; everything else goes
to stderr. It is not in `./go ci`: the workbench has no browser. It runs as a
job of .github/workflows/ci.yml, in the Playwright image site.yml pins.

Written from docs/adr/0059 and the DOM contract it names, not from
console/index.html. It starts console/serve.py itself, in snapshot mode, over
fixtures/logbook/golden-1.2.json, and drives it with Playwright:

  a. every interaction of the kanban in a scripted sequence (search, each
     filter, grouping, hiding the empty columns, collapsing, a click on a
     card, the arrows, Enter, Escape and `/`): after each step every card
     sits in the column the logbook puts it in, the cards shown are those the
     step's rule gives, the hash carries the view, and no POST was sent;
  b. a view set by interactions, read from location.hash and opened in a new
     page, draws the same lanes, columns, collapsed columns, cards and drawer;
     so does a hash written by hand;
  c. every screen's main text is the same under the system theme (light and
     dark), the light and the dark theme, and with localStorage refusing;
  d. the editor: its line is the one gates/spec.sh prints on its preview;
  e. the board's theme switch changes its theme and nothing it says;
  f. the ADR search, over a logbook read from this repository's own map,
     finds an ADR by its number, by a word of its title and by a file it
     cites.

Every comparison is shown first to fail on a wrong input (self_checks, and
the probes in a_board and a_posts): a gate that cannot fail is not a gate.
"""
import fnmatch
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

NAME = "console-ui"
ROOT = pathlib.Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "fixtures" / "logbook" / "golden-1.2.json"
SCREENS = ["overview", "kanban", "tickets", "ticket/{id}", "specs", "request", "adrs", "incidents", "launch", "thresholds"]
THEME_KEY = "lights-out.theme"
TIMEOUT_MS = 5000


class Fail(Exception):
    """A NO-GO: one line for stdout, the details already on stderr."""


def say(*parts):
    print(*parts, file=sys.stderr, flush=True)


def need(cond, why, *details):
    if not cond:
        for d in details:
            say(d)
        raise Fail(why)


# --- what a view is, and how the hash writes it (docs/adr/0059 §1) --------------

HASH_KEYS = ("q", "feature", "priority", "group", "empty", "collapsed", "card")


def enc(value):
    """encodeURIComponent, for the characters these views hold."""
    return urllib.parse.quote(value, safe="-_.!~*'()")


class View:
    """The page's one view; every interaction changes it and nothing else."""

    def __init__(self, **kw):
        self.q, self.feature, self.priority, self.group, self.empty = "", "", "", "", ""
        self.collapsed, self.card = [], ""
        self.__dict__.update(kw)

    def hash(self):
        """#kanban?q=..&feature=..&priority=..&group=..&empty=hide&collapsed=a,b&card=0005,
        keys in that order, the defaults left out."""
        parts = []
        for key in HASH_KEYS:
            value = getattr(self, key)
            if value:
                parts.append(f"{key}=" + (",".join(enc(v) for v in value) if key == "collapsed" else enc(value)))
        return "#kanban" + ("?" + "&".join(parts) if parts else "")


def read_hash(raw):
    """(keys in the order written, {key: value}) of a #kanban hash, decoded; collapsed is a list."""
    head, _, query = raw.partition("?")
    if head != "#kanban":
        return None, None
    keys, view = [], {}
    for pair in filter(None, query.split("&")):
        key, _, value = pair.partition("=")
        keys.append(key)
        if key == "collapsed":  # a, b joined by a comma, whether or not the comma is itself escaped
            view[key] = [s for v in value.split(",") for s in urllib.parse.unquote(v).split(",") if s]
        else:
            view[key] = urllib.parse.unquote(value)
    return keys, view


def view_problems(raw, view):
    """Why the hash RAW is not the view VIEW, or None."""
    keys, got = read_hash(raw)
    if keys is None:
        return f"location.hash is {raw!r}, want a #kanban hash"
    if keys != [k for k in HASH_KEYS if k in keys]:
        return f"the hash {raw!r} writes its keys out of order {keys}, want the order {list(HASH_KEYS)}"
    want = {k: getattr(view, k) for k in HASH_KEYS if getattr(view, k)}
    if "collapsed" in got:
        got["collapsed"] = sorted(got["collapsed"])
    if "collapsed" in want:
        want["collapsed"] = sorted(want["collapsed"])
    if got != want:
        return f"the hash {raw!r} says {got}, the view is {want}"
    if len(view.collapsed) <= 1 and raw != view.hash():
        return f"the hash is {raw!r}, want exactly {view.hash()!r}"
    return None


# --- the board, as the page draws it ------------------------------------------

BOARD_JS = """() => {
  const lane = (el) => { const l = el.closest('.lane[data-lane]'); return l ? l.dataset.lane : null; };
  const cols = [...document.querySelectorAll('.col[data-state]')].map((c) => ({
    state: c.dataset.state, lane: lane(c), collapsed: c.classList.contains('collapsed'),
    cards: [...c.querySelectorAll('.card[data-id]')].map((k) => k.dataset.id), text: c.innerText}));
  const drawer = document.querySelector('aside#drawer');
  const q = document.querySelector('input#kanban-q');
  const val = (n) => { const s = document.querySelector('main select[name=' + n + ']'); return s ? s.value : null; };
  const active = document.activeElement;
  return {cols, lanes: [...document.querySelectorAll('.lane[data-lane]')].map((l) => l.dataset.lane),
    drawer: drawer ? drawer.dataset.id : null, hash: location.hash, history: history.length,
    controls: {q: q ? q.value : null, feature: val('feature'), priority: val('priority'), group: val('group'), empty: val('empty')},
    active: active ? {tag: active.tagName, id: active.id, card: active.dataset ? active.dataset.id || null : null,
                      inCard: !!(active.closest && active.closest('.card[data-id]'))} : null};
}"""


def board_problems(board, col_of):
    """What is wrong with the cards on the board: a card outside the column the
    logbook puts it in, a card twice, a collapsed column that shows a card."""
    bad, seen = [], set()
    for col in board["cols"]:
        if col["collapsed"] and col["cards"]:
            bad.append(f"the collapsed column {col['state']} shows {col['cards']}")
        for card in col["cards"]:
            if card in seen:
                bad.append(f"card {card} is drawn twice")
            seen.add(card)
            if col_of.get(card) != col["state"]:
                bad.append(f"card {card} sits in the column {col['state']}, the logbook's is {col_of.get(card)}")
    return bad


def signature(board):
    """What a view draws: lanes, columns with their lane and collapse, the cards, the drawer."""
    return {"lanes": board["lanes"], "cols": [(c["lane"], c["state"], c["collapsed"], c["cards"]) for c in board["cols"]],
            "drawer": board["drawer"]}


def shown(board):
    return {card: col["state"] for col in board["cols"] for card in col["cards"]}


def matches(ticket, q="", feature="", priority=""):
    """Whether the card of TICKET shows under the search Q and the two filters:
    the search is over the id, the title and the perimeter, a path matching a
    card when one of its globs matches it (`*` crosses `/`) or contains it."""
    if feature and ticket.get("feature") != feature:
        return False
    if priority and ticket.get("priority") != priority:
        return False
    if not q:
        return True
    low = q.lower()
    globs = ticket["perimeter"] if isinstance(ticket.get("perimeter"), list) else []
    return (low in ticket["id"].lower() or low in str(ticket.get("title") or "").lower()
            or any(low in g.lower() or fnmatch.fnmatchcase(q, g) for g in globs))


def text_diff(a, b):
    """The first line two texts differ at, for a message; None when they are the same."""
    if a == b:
        return None
    la, lb = a.splitlines(), b.splitlines()
    for i in range(max(len(la), len(lb))):
        x, y = (la[i] if i < len(la) else "<end>"), (lb[i] if i < len(lb) else "<end>")
        if x != y:
            return f"line {i + 1}: {x[:100]!r} against {y[:100]!r}"
    return "the texts differ in their line ends"


# --- processes ------------------------------------------------------------------

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Served:
    """A server process of this repository, on a free loopback port, until the block ends."""

    def __init__(self, argv, env, probe):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.log = tempfile.TemporaryFile()
        self.argv, self.env, self.probe = argv, dict(env), probe

    def __enter__(self):
        self.env.update(self.listen(self.port))
        self.proc = subprocess.Popen(self.argv, cwd=ROOT, env=self.env, stdout=subprocess.DEVNULL, stderr=self.log)
        for _ in range(100):
            if self.proc.poll() is not None:
                break
            try:
                urllib.request.urlopen(self.base + self.probe, timeout=1).close()
                return self
            except OSError:
                time.sleep(0.1)
        self.log.seek(0)
        err = self.log.read().decode(errors="replace")[-600:]
        self.proc.kill()
        raise Fail(f"{' '.join(self.argv[-1:])} did not answer on {self.base}{self.probe}: {err.strip()[-300:]}")

    def __exit__(self, *exc):
        self.proc.kill()
        self.proc.wait()
        self.log.close()

    @staticmethod
    def listen(port):
        return {}


class Console(Served):
    def __init__(self, logbook, **env):
        base = {k: v for k, v in os.environ.items() if not k.startswith("CONSOLE_")}
        super().__init__([sys.executable, str(ROOT / "console" / "serve.py")],
                         {**base, "CONSOLE_SNAPSHOT": str(logbook), **env}, "/v1/console.json")

    @staticmethod
    def listen(port):
        return {"CONSOLE_LISTEN": str(port), "CONSOLE_PORT": str(port)}


class Board(Served):
    def __init__(self):
        base = {k: v for k, v in os.environ.items() if not k.startswith(("BOARD_", "STATE_STORE"))}
        super().__init__([sys.executable, str(ROOT / "board" / "serve.py")], {**base, "BOARD_STATIC": "1"}, "/")

    @staticmethod
    def listen(port):
        return {"BOARD_LISTEN": str(port), "BOARD_PORT": str(port)}


def gate_line(markdown):
    """The one line gates/spec.sh prints on this Markdown, run in the repository."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(markdown)
    try:
        done = subprocess.run(["sh", "gates/spec.sh", fh.name], cwd=ROOT, capture_output=True, text=True, check=False)
    finally:
        os.unlink(fh.name)
    return done.stdout.strip()


# --- a page with watchers --------------------------------------------------------

class Tab:
    """A page that records what it asks for and what it throws."""

    def __init__(self, ctx, base):
        self.page, self.base = ctx.new_page(), base
        self.posts, self.foreign, self.errors, self.inflight = [], [], [], 0
        self.page.on("request", self._request)
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("response", self._done)
        self.page.on("requestfailed", self._done)

    def _request(self, r):
        path = urllib.parse.urlparse(r.url).path
        if r.method == "POST":
            self.posts.append(path)
            self.inflight += path == "/v1/spec-check"
        if not r.url.startswith(self.base) and not r.url.startswith(("data:", "about:", "blob:")):
            self.foreign.append(r.url)

    def _done(self, r):
        req = getattr(r, "request", r)
        if req.method == "POST" and urllib.parse.urlparse(req.url).path == "/v1/spec-check":
            self.inflight = max(0, self.inflight - 1)

    def audit(self, what, allow=()):
        need(not self.errors, f"{what}: the page threw {self.errors[0][:200] if self.errors else ''}", *self.errors)
        need(not self.foreign, f"{what}: the page asked the network for {self.foreign[:2]}")
        bad = [p for p in self.posts if p not in allow]
        need(not bad, f"{what}: the page sent a POST to {bad} ({'only ' + str(list(allow)) + ' allowed' if allow else 'no POST allowed'})")

    def load(self, hash_):
        self.page.goto(self.base + "/" + hash_)
        try:
            self.page.wait_for_selector("main h1", timeout=TIMEOUT_MS)
        except Exception:  # noqa: BLE001 - a page that draws no screen is a NO-GO that says what it threw
            raise Fail(f"the page drew no main h1 for {hash_} in {TIMEOUT_MS} ms; it threw {self.errors[:2] or 'nothing'}") from None

    def stable_text(self, what, selector="main", rounds=2, gap=400):
        """The text of SELECTOR once it has stopped changing."""
        last = None
        for _ in range(20):
            now = self.page.inner_text(selector)
            if now == last:
                rounds -= 1
                if rounds <= 0:
                    return now
            else:
                last, rounds = now, 1
            self.page.wait_for_timeout(gap // 2)
        raise Fail(f"{what}: the text of {selector} never settled")

    def wait(self, js, arg, what, timeout=TIMEOUT_MS):
        try:
            self.page.wait_for_function(js, arg=arg, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - a timeout becomes the NO-GO that names what was awaited
            raise Fail(f"{what}: {str(exc).splitlines()[0][:200]}") from None


# --- a. the kanban --------------------------------------------------------------

class Kanban:
    """The kanban screen, one step at a time, each step checked."""

    def __init__(self, tab, golden):
        self.tab, self.page = tab, tab.page
        self.tickets = golden["tickets"]
        self.col_of = {c: col["state"] for col in golden["kanban"] for c in col["tickets"]}
        self.order = {col["state"]: col["tickets"] for col in golden["kanban"]}
        self.view = View()

    def board(self):
        return self.page.evaluate(BOARD_JS)

    def expect(self, what, **kw):
        """Wait until the cards shown are the ones the rule gives, then check the board and the hash."""
        want = {t["id"] for t in self.tickets if matches(t, kw.get("q", self.view.q), kw.get("feature", self.view.feature),
                                                         kw.get("priority", self.view.priority))}
        got = {}
        for _ in range(60):
            b = self.board()
            got = shown(b)
            if set(got) == want and not board_problems(b, self.col_of):
                break
            self.page.wait_for_timeout(50)
        need(set(got) == want, f"kanban, {what}: the cards shown are {sorted(got)}, want {sorted(want)}")
        self.check(what)
        return b

    def check(self, what):
        """The board and the hash after a step: the hash is allowed a moment to follow."""
        for _ in range(20):
            b = self.board()
            problem = view_problems(b["hash"], self.view)
            if problem is None:
                break
            self.page.wait_for_timeout(50)
        bad = board_problems(b, self.col_of)
        need(not bad, f"kanban, {what}: {bad[0] if bad else ''}", *bad)
        need(problem is None, f"kanban, {what}: {problem}")
        self.tab.audit(f"kanban, {what}")
        return b

    def search(self, q, what):
        self.view.q = q
        self.page.fill("input#kanban-q", q)
        return self.expect(what)

    def select(self, name, value, what, loose=False):
        """Choose VALUE in a select. A value the logbook's tickets do not carry (a
        'none' the page may offer) is not given a set of cards, only the invariants."""
        setattr(self.view, name, value)
        self.page.select_option(f"main select[name={name}]", value)
        if loose:
            self.page.wait_for_timeout(200)
            return self.check(what)
        return self.expect(what)

    def options(self, name):
        return self.page.evaluate("n => [...document.querySelectorAll('main select[name=' + n + '] option')].map(o => o.value)", name)

    def toggle(self, state, what):
        """Click the toggle of a column (the first, when lanes repeat it)."""
        self.page.locator(f".col[data-state='{state}'] button.col-toggle").first.click()
        if state in self.view.collapsed:
            self.view.collapsed.remove(state)
        else:
            self.view.collapsed.append(state)
        self.tab.wait("([s, want]) => document.querySelector(\".col[data-state='\" + s + \"']\").classList.contains('collapsed') === want",
                      [state, state in self.view.collapsed], f"kanban, {what}: the column never {'collapsed' if state in self.view.collapsed else 'expanded'}")
        return self.check(what)

    def card(self, ident):
        return f".card[data-id='{ident}']"

    def open_card(self, ident, what):
        self.page.click(self.card(ident))
        self.view.card = ident
        self.drawer_is(ident, what)

    def drawer_is(self, ident, what):
        self.tab.wait("id => { const d = document.querySelector('aside#drawer'); return (d ? d.dataset.id : '') === id; }",
                      ident, f"kanban, {what}: the drawer of {ident} never showed" if ident else f"kanban, {what}: the drawer never closed")
        self.check(what)

    def key(self, key, what):
        self.page.keyboard.press(key)
        self.page.wait_for_timeout(120)
        return self.check(what)


def a_posts(browser, base):
    """The probe that makes 'no POST was sent' mean something: a POST the page
    makes is seen by the tab's watcher."""
    ctx = browser.new_context()
    tab = Tab(ctx, base)
    tab.load("#overview")
    tab.page.evaluate("fetch('/v1/answer', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'}).catch(() => 0)")
    tab.page.wait_for_timeout(300)
    need(tab.posts == ["/v1/answer"], f"the POST watcher did not see a POST the page made: {tab.posts}")
    need(not tab.foreign, f"the console asked the network for {tab.foreign}")
    ctx.close()
    # The same for a request off the origin, from a page with no content security policy.
    ctx = browser.new_context()
    tab = Tab(ctx, base)
    tab.page.set_content("<img src='http://assets.invalid/x.png'>")
    tab.page.wait_for_timeout(500)
    need(tab.foreign, "the network watcher did not see a request off the origin")
    ctx.close()


def a_board(browser, base, golden):
    ctx = browser.new_context(viewport={"width": 1600, "height": 900})
    tab = Tab(ctx, base)
    k = Kanban(tab, golden)
    tab.load("#kanban")
    start = k.board()
    h0 = start["history"]

    # The probe that makes the invariant mean something: a card moved to another
    # column by hand is a violation it must name.
    probe = json.loads(json.dumps(start))
    first = next(c for c in probe["cols"] if len(c["cards"]) > 0)
    other = next(c for c in probe["cols"] if c is not first)
    other["cards"].append(first["cards"].pop())
    need(board_problems(probe, k.col_of), "the board invariant accepted a card moved to another column")
    probe["cols"][0]["collapsed"], probe["cols"][0]["cards"] = True, ["x"]
    need(len(board_problems(probe, k.col_of)) >= 1, "the board invariant accepted a collapsed column that shows a card")

    # The default view: every ticket on its card, in the column and the order the logbook says.
    all_ids = {t["id"] for t in k.tickets}
    b = k.expect("the default view")
    need(set(shown(b)) == all_ids, f"kanban: the default view shows {sorted(shown(b))}, want every ticket {sorted(all_ids)}")
    for col in b["cols"]:
        want = k.order.get(col["state"])
        need(want is not None, f"kanban: the column {col['state']} is not one of the logbook's: {sorted(k.order)}")
        need(col["cards"] == want, f"kanban: the column {col['state']} holds {col['cards']}, the logbook's order is {want}")
    need(all(c["lane"] in ("", None) for c in b["cols"]) and set(b["lanes"]) <= {""}, f"kanban: not grouped, but the lanes are {b['lanes']}")
    need(k.view.hash() == "#kanban", "the default view is not the bare #kanban")

    # Search: the id, the title, and the perimeter, a path by a glob or by containing it.
    searches = ["waitlist", "app/backend/geocoder/cache.py", "router.py", "0009", "README", "zzz-nothing"]
    for q in searches:
        k.search(q, f"search {q!r}")
    need(shown(k.board()) == {}, "kanban: a search that matches nothing still shows cards")
    k.search("", "search cleared")
    need(set(shown(k.board())) == all_ids, "kanban: clearing the search does not bring every card back")
    need(any(matches(t, "app/backend/geocoder/cache.py") for t in k.tickets), "the golden has no ticket a glob matches: the search of a path proves nothing")

    # Each filter, each value it offers, alone and together.
    for name in ("feature", "priority"):
        values = k.options(name)
        carried = {t.get(name) for t in k.tickets if t.get(name)}
        need("" in values and carried <= set(values), f"kanban: the {name} filter offers {values}, want '' and {sorted(carried)}")
        for value in values:
            if value:
                k.select(name, value, f"{name} = {value}", loose=value not in carried)
        k.select(name, "", f"{name} cleared")
    feature = next((t["feature"] for t in k.tickets if t.get("feature") and t.get("priority")), None)
    if feature:
        prio = next(t["priority"] for t in k.tickets if t.get("feature") == feature)
        k.select("feature", feature, f"feature {feature}")
        k.select("priority", prio, f"feature {feature} and priority {prio}")
        k.search("a", "feature, priority and a search together")
        k.search("", "the search cleared")
        k.select("priority", "", "priority cleared")
        k.select("feature", "", "feature cleared")

    # Grouping: lanes by feature, by priority, and back.
    for group, field in (("feature", "feature"), ("priority", "priority")):
        b = k.select("group", group, f"grouped by {group}")
        lanes = set(b["lanes"])
        need(len(lanes) >= 2, f"kanban: grouped by {group}, the lanes are {sorted(lanes)}")
        for col in b["cols"]:
            for card in col["cards"]:
                t = next(t for t in k.tickets if t["id"] == card)
                if t.get(field):
                    need(col["lane"] == t[field], f"kanban: grouped by {group}, card {card} ({t[field]}) is in the lane {col['lane']!r}")
                else:
                    need(col["lane"] not in {x.get(field) for x in k.tickets if x.get(field)},
                         f"kanban: grouped by {group}, card {card} has none but sits in the lane {col['lane']!r}")
    b = k.select("group", "", "ungrouped")
    need(set(b["lanes"]) <= {""}, f"kanban: ungrouped, the lanes are {b['lanes']}")

    # Hiding the empty columns, and with a filter on.
    b = k.select("empty", "hide", "empty columns hidden")
    need(all(c["cards"] or c["collapsed"] for c in b["cols"]), "kanban: hiding the empty columns left one with no card")
    need({c["state"] for c in b["cols"]} == {k.col_of[i] for i in all_ids}, f"kanban: hiding the empty columns leaves {[c['state'] for c in b['cols']]}")
    if feature:
        k.select("feature", feature, "empty columns hidden and a feature")
        b = k.board()
        need(all(c["cards"] for c in b["cols"]), "kanban: hidden empties and a filter left an empty column")
        k.select("feature", "", "feature cleared again")
    k.select("empty", "", "empty columns shown")

    # Collapsing and expanding a column: its state and count only, no card.
    full = next(c for c in k.board()["cols"] if len(c["cards"]) >= 2)
    b = k.toggle(full["state"], f"collapse {full['state']}")
    col = next(c for c in b["cols"] if c["state"] == full["state"])
    need(col["collapsed"] and not col["cards"], f"kanban: {full['state']} collapsed still shows {col['cards']}")
    need(full["state"] in col["text"] and str(len(full["cards"])) in col["text"],
         f"kanban: the collapsed column shows {col['text']!r}, want its state {full['state']} and its count {len(full['cards'])}")
    b = k.toggle(full["state"], f"expand {full['state']}")
    col = next(c for c in b["cols"] if c["state"] == full["state"])
    need(not col["collapsed"] and col["cards"] == full["cards"], f"kanban: {full['state']} expanded shows {col['cards']}, want {full['cards']}")
    two = [c["state"] for c in k.board()["cols"] if c["cards"]][:2]
    for state in two:
        k.toggle(state, f"collapse {state} beside another")
    need(sorted(k.view.collapsed) == sorted(two) and sum(c["collapsed"] for c in k.board()["cols"]) == 2, f"kanban: two collapsed columns, the page shows {k.board()['hash']}")
    for state in two:
        k.toggle(state, f"expand {state} beside another")
    k.expect("both expanded")

    # A click on a card opens the drawer; Escape closes it; Enter opens it again.
    target = next((t["id"] for t in k.tickets if any(n not in t["id"] and n not in str(t.get("title")) for n in t.get("adrs") or [])), None)
    need(target, "the golden has no ticket governed by an ADR whose number is not in the ticket's own: the drawer's ADRs prove nothing")
    k.open_card(target, f"a click on card {target}")
    drawer = k.page.inner_text("aside#drawer")
    t = next(t for t in k.tickets if t["id"] == target)
    need(t["state"] in drawer, f"kanban: the drawer of {target} does not say its state {t['state']}", drawer[:300])
    need(k.page.locator(f"aside#drawer a[href='#ticket/{target}']").count() >= 1, f"kanban: the drawer of {target} links no #ticket/{target}", drawer[:300])
    for n in t["adrs"]:
        if n not in t["id"] and n not in str(t.get("title")):
            need(n in drawer, f"kanban: the drawer of {target} does not name ADR {n}, which governs its perimeter", drawer[:300])
    k.view.card = ""
    k.key("Escape", "Escape closes the drawer")
    k.drawer_is("", "after Escape")
    k.page.focus(k.card(target))
    need(k.board()["active"]["card"] == target, f"kanban: card {target} cannot be focused: {k.board()['active']}")
    k.page.keyboard.press("Enter")
    k.view.card = target
    k.drawer_is(target, "Enter opens the drawer of the focused card")
    k.view.card = ""
    k.key("Escape", "Escape closes it again")
    k.drawer_is("", "after Escape again")

    # The arrows: up and down inside a column, left and right across columns, and `/`.
    b = k.board()
    col = next(c for c in b["cols"] if len(c["cards"]) >= 2)
    one, two = col["cards"][0], col["cards"][1]
    k.page.focus(k.card(one))
    k.key("ArrowDown", "ArrowDown")
    need(k.board()["active"]["card"] == two, f"kanban: ArrowDown from {one} did not reach {two}: {k.board()['active']}")
    k.key("ArrowUp", "ArrowUp")
    need(k.board()["active"]["card"] == one, f"kanban: ArrowUp from {two} did not return to {one}: {k.board()['active']}")
    cols = [c for c in k.board()["cols"] if c["cards"]]
    need(len(cols) >= 2, "the golden has fewer than two columns with cards: the left and right arrows prove nothing")
    left = cols[0]

    def column_of_focus(now):
        found = [c["state"] for c in now["cols"] if now["active"] and now["active"]["card"] in c["cards"]]
        return [c["state"] for c in now["cols"]].index(found[0]) if found else None

    order = [c["state"] for c in k.board()["cols"]]
    k.page.focus(k.card(left["cards"][0]))
    k.key("ArrowRight", "ArrowRight")
    reached = column_of_focus(k.board())
    need(reached is not None and reached > order.index(left["state"]),
         f"kanban: ArrowRight from {left['cards'][0]} in {left['state']} did not reach a card in a column to its right: {k.board()['active']}")
    k.key("ArrowLeft", "ArrowLeft")
    back = column_of_focus(k.board())
    need(back is not None and back < reached, f"kanban: ArrowLeft from column {order[reached]} did not reach a card in a column to its left: {k.board()['active']}")
    k.page.focus(k.card(one))
    k.page.keyboard.press("/")
    k.page.wait_for_timeout(100)
    need(k.board()["active"]["id"] == "kanban-q", f"kanban: / did not focus the search: {k.board()['active']}")
    k.check("the / key")

    # The probe for the hash: interactions use replaceState, so none added a history entry.
    need(k.board()["history"] == h0, f"kanban: interactions added {k.board()['history'] - h0} history entries; they must replaceState")
    k.tab.audit("kanban, the whole sequence")

    # Back to the defaults: the hash is bare again.
    k.page.keyboard.press("Escape")
    k.page.fill("input#kanban-q", "")
    k.view = View(collapsed=[], card="")
    k.page.evaluate("location.hash = '#kanban'")
    k.expect("reset")
    ctx.close()


# --- b. a view in the link --------------------------------------------------------

def b_hash(browser, base, golden):
    ctx = browser.new_context(viewport={"width": 1600, "height": 900})
    tab = Tab(ctx, base)
    k = Kanban(tab, golden)
    tab.load("#kanban")
    k.search("app", "search app")
    k.select("group", "priority", "grouped by priority")
    k.select("empty", "hide", "empty columns hidden")
    states = [c["state"] for c in k.board()["cols"] if c["cards"]]
    pick = states[-1]
    k.toggle(pick, f"collapse {pick}")
    ident = next(c["cards"][0] for c in k.board()["cols"] if c["cards"] and c["state"] != pick)
    k.open_card(ident, f"open {ident}")
    raw = k.board()["hash"]
    expected = f"#kanban?q=app&group=priority&empty=hide&collapsed={enc(pick)}&card={ident}"
    need(raw == expected, f"b: the hash of the view is {raw!r}, want {expected!r}")
    first = signature(k.board())
    need(first["drawer"] == ident and any(c[2] for c in first["cols"]) and len(first["lanes"]) >= 2, f"b: the view is not what was set: {first}")

    # A new page on that hash draws the same.
    again = Tab(ctx, base)
    again.load(raw)
    again.wait("id => { const d = document.querySelector('aside#drawer'); return !!d && d.dataset.id === id; }", ident,
               "b: the new page never opened the drawer")
    second = Kanban(again, golden)
    other = signature(second.board())
    need(other == first, f"b: the page opened on {raw!r} draws {other}, the page that wrote it drew {first}")
    need(second.board()["controls"] == k.board()["controls"], f"b: the controls differ: {second.board()['controls']} against {k.board()['controls']}")
    bad = board_problems(second.board(), second.col_of)
    need(not bad, f"b: the page opened on the hash: {bad[0] if bad else ''}")
    again.audit("b, the page opened on a hash")

    # A reload keeps the view.
    again.page.reload()
    again.page.wait_for_selector("main h1", timeout=TIMEOUT_MS)
    again.wait("id => { const d = document.querySelector('aside#drawer'); return !!d && d.dataset.id === id; }", ident, "b: a reload lost the drawer")
    need(signature(second.board()) == first, "b: a reload does not draw the same board")

    # A hash written by hand, with the keys in the order the page writes them:
    # grouped by feature, the empty columns hidden, one column collapsed, and
    # the drawer of a card in another column open.
    opened = next(t for t in golden["tickets"] if t.get("feature"))
    folded = golden_state(golden, next(t["id"] for t in golden["tickets"] if golden_state(golden, t["id"]) != golden_state(golden, opened["id"])))
    hand = f"#kanban?group=feature&empty=hide&collapsed={enc(folded)}&card={opened['id']}"
    hand_tab = Tab(ctx, base)
    hand_tab.load(hand)
    hand_tab.wait("id => { const d = document.querySelector('aside#drawer'); return !!d && d.dataset.id === id; }", opened["id"],
                  "b: a hash written by hand did not open the drawer")
    hk = Kanban(hand_tab, golden)
    b = hk.board()
    want = {t["id"] for t in golden["tickets"] if golden_state(golden, t["id"]) != folded}
    need(not board_problems(b, hk.col_of), f"b: the hash {hand!r}: {board_problems(b, hk.col_of)[:1]}")
    need(set(shown(b)) == want, f"b: the hash {hand!r} shows {sorted(shown(b))}, want every card but those of {folded}: {sorted(want)}")
    need(any(c["collapsed"] and c["state"] == folded for c in b["cols"]), f"b: the hash {hand!r} did not collapse {folded}")
    need(all(c["cards"] or c["collapsed"] for c in b["cols"]), f"b: the hash {hand!r} hides the empty columns, but one shows nothing")
    need(opened["feature"] in b["lanes"] and len(b["lanes"]) >= 2, f"b: the hash {hand!r} groups by feature, but the lanes are {b['lanes']}")
    hand_tab.audit("b, a hash written by hand")
    ctx.close()


def golden_state(golden, ident):
    return next(col["state"] for col in golden["kanban"] if ident in col["tickets"])


# --- c. the theme -----------------------------------------------------------------

STORAGE_THROWS = """
Object.defineProperty(window, 'localStorage', {configurable: true, get() { throw new DOMException('storage is refused', 'SecurityError'); }});
"""
VARIANTS = [
    # name, the OS's scheme, the switch's choice, the dataset the choice gives, storage works
    ("system, light OS", "light", None, None, True),
    ("system, dark OS", "dark", None, None, True),
    ("light, light OS", "light", "light", "light", True),
    ("dark, light OS", "light", "dark", "dark", True),
    ("light, dark OS", "dark", "light", "light", True),
    ("dark, dark OS", "dark", "dark", "dark", True),
    ("storage refused, dark chosen", "light", "dark", "dark", False),
    ("storage refused, nothing chosen", "dark", None, None, False),
]


def c_themes(browser, base, golden):
    tid = next((t["id"] for t in golden["tickets"] if t["id"] == "0009"), golden["tickets"][0]["id"])
    screens = [s.format(id=tid) for s in SCREENS]
    texts, backgrounds = {}, {}
    for name, scheme, choice, dataset, storage in VARIANTS:
        ctx = browser.new_context(color_scheme=scheme, viewport={"width": 1440, "height": 900})
        if not storage:
            ctx.add_init_script(STORAGE_THROWS)
        tab = Tab(ctx, base)
        for screen in screens:
            tab.page.goto("about:blank")
            tab.load("#" + screen)
            head = tab.page.evaluate("document.querySelector('select#theme') ? document.querySelector('select#theme').value : null")
            need(head is not None, f"c ({name}): {screen} has no select#theme in the header")
            options = tab.page.evaluate("[...document.querySelectorAll('select#theme option')].map(o => o.value)")
            need(sorted(options) == ["dark", "light", "system"], f"c ({name}): select#theme offers {options}, want system, light, dark")
            if choice and (screen == screens[0] or not storage):
                tab.page.select_option("select#theme", choice)
                tab.page.wait_for_timeout(100)
            got = tab.page.evaluate("document.documentElement.dataset.theme ?? null")
            need(got == dataset, f"c ({name}): on {screen}, data-theme is {got!r}, want {dataset!r}")
            if choice and storage:
                need(tab.page.evaluate("document.querySelector('select#theme').value") == choice,
                     f"c ({name}): the switch does not show the choice kept in localStorage on {screen}")
                kept = tab.page.evaluate(f"localStorage.getItem('{THEME_KEY}')")
                need(kept == choice, f"c ({name}): localStorage['{THEME_KEY}'] is {kept!r}, want {choice!r}")
            texts.setdefault(screen, {})[name] = tab.stable_text(f"c ({name}) {screen}")
            tab.audit(f"c ({name}) {screen}", allow=("/v1/spec-check",))
            if screen == "overview":
                backgrounds[name] = tab.page.evaluate("getComputedStyle(document.body).backgroundColor")
        ctx.close()
    # The same words in every theme, on every screen.
    probe = {"a": "one\ntwo", "b": "one\ntwo!"}
    need(text_diff(probe["a"], probe["b"]) is not None, "the text comparison does not see a changed word")
    for screen, by_variant in texts.items():
        base_name, base_text = next(iter(by_variant.items()))
        need(len(base_text.strip()) > 20, f"c: the {screen} screen says almost nothing: {base_text[:60]!r}")
        for name, text in by_variant.items():
            diff = text_diff(base_text, text)
            need(diff is None, f"c: {screen} reads differently under {name} than under {base_name}: {diff}")
    # And the theme is colour: light and dark differ, and `system` follows the OS.
    need(backgrounds["light, light OS"] != backgrounds["dark, light OS"],
         f"c: the light and dark themes paint the same background {backgrounds['light, light OS']}")
    need(backgrounds["system, light OS"] == backgrounds["light, light OS"], "c: system in a light OS is not the light theme")
    need(backgrounds["system, dark OS"] == backgrounds["dark, dark OS"], "c: system in a dark OS is not the dark theme")
    need(backgrounds["dark, light OS"] == backgrounds["dark, dark OS"], "c: the dark theme depends on the OS")
    need(backgrounds["storage refused, dark chosen"] == backgrounds["dark, dark OS"], "c: a switch that cannot store does not switch")


# --- d. the editor ------------------------------------------------------------------

GOOD = {"title": "A waiting list when a meetup is full", "context": "A full meetup refuses every further signup.",
        "criteria": [("a meetup at capacity", "a new member signs up", "they join the waiting list and see their position")],
        "perimeter": "app/backend/waitlist/*\ndocs/waitlist.md", "feature": "waiting-list", "priority": "P1"}


def draft(**change):
    return {**json.loads(json.dumps(GOOD)), **change}


# name, fields, the gate's verdict (`-` leaves the form of an empty field to the draft)
DRAFTS = [
    ("a draft the gate passes", draft(), "GO"),
    ("no context, feature or priority", draft(context="", feature="", priority=""), "GO"),
    ("two criteria", draft(criteria=[GOOD["criteria"][0], ("a waiting list with one member", "an attendee cancels", "the first member on the list becomes an attendee")]), "GO"),
    ("no criterion", draft(criteria=[]), "NO-GO"),
    ("a Then with no outcome", draft(criteria=[("a meetup at capacity", "a new member signs up", "")]), "NO-GO"),
    ("a vague outcome", draft(criteria=[("a meetup at capacity", "a new member signs up", "it works")]), "NO-GO"),
    ("a second criterion that is vague", draft(criteria=[GOOD["criteria"][0], ("x", "y", "it is handled correctly")]), "NO-GO"),
    ("no perimeter path", draft(perimeter=""), "NO-GO"),
    ("a Feature that is not a slug", draft(feature="Waiting List"), "NO-GO"),
    ("an empty Given", draft(criteria=[("", "a new member signs up", "they join the waiting list and see their position")]), "-"),
    ("an empty When", draft(criteria=[("a meetup at capacity", "", "they join the waiting list and see their position")]), "-"),
]


def fill_editor(page, fields):
    page.fill("input[name=title]", fields["title"])
    page.fill("textarea[name=context]", fields["context"])
    while page.locator(".criterion").count() < len(fields["criteria"]):
        page.click("button#add-criterion")
    for i, (given, when, then) in enumerate(fields["criteria"]):
        row = page.locator(".criterion").nth(i)
        row.locator("input[name=given]").fill(given)
        row.locator("input[name=when]").fill(when)
        row.locator("input[name=then]").fill(then)
    page.fill("textarea[name=perimeter]", fields["perimeter"])
    page.fill("input[name=feature]", fields["feature"])
    page.select_option("select[name=priority]", fields["priority"])


def typed(fields):
    """What a finished draft must show in its preview: every value typed, verbatim."""
    want = [fields["title"], fields["context"], fields["feature"], fields["priority"]]
    want += [v for row in fields["criteria"] for v in row]
    want += [line for line in fields["perimeter"].splitlines()]
    return [w for w in want if w]


def d_editor(browser, base, golden):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1100})
    tab = Tab(ctx, base)
    probe_good, probe_bad = gate_line("# 0099 — x\n\n## Acceptance criteria\n\nGiven a\nWhen b\nThen the page shows c\n\n## Perimeter\n\n- `a/b`\n"), \
        gate_line("# 0099 — x\n\n## Acceptance criteria\n\nGiven a\nWhen b\nThen it works\n\n## Perimeter\n\n- `a/b`\n")
    need(probe_good == "GO: spec" and probe_bad.startswith("NO-GO: spec — "), f"gates/spec.sh does not tell a good spec from a vague one: {probe_good!r}, {probe_bad!r}")
    for name, fields, verdict in DRAFTS:
        tab.page.goto("about:blank")
        tab.load("#request")
        need(tab.page.locator("#l0-note").count() >= 1, "d: the golden's source.level is l0, but the editor has no #l0-note")
        need(tab.page.is_disabled("button#save"), "d: button#save is enabled in snapshot mode")
        need(sorted(tab.page.evaluate("[...document.querySelectorAll('select[name=priority] option')].map(o => o.value)"))
             == ["", "P0", "P1", "P2", "P3"], "d: select[name=priority] does not offer '', P0, P1, P2, P3")
        fill_editor(tab.page, fields)
        want = typed(fields)
        got_line = got_md = ""
        for _ in range(100):
            tab.page.wait_for_timeout(100)
            got_md = tab.page.text_content("#spec-preview") or ""
            got_line = tab.page.text_content("#spec-line") or ""
            if all(w in got_md for w in want) and re.match(r"(GO|NO-GO): spec", got_line) and tab.inflight == 0:
                tab.page.wait_for_timeout(400)
                if (tab.page.text_content("#spec-preview") or "") == got_md and (tab.page.text_content("#spec-line") or "") == got_line:
                    break
        need(all(w in got_md for w in want) and re.match(r"(GO|NO-GO): spec", got_line),
             f"d ({name}): the preview never showed the draft ({want}) with a gate line", f"preview: {got_md[:400]!r}", f"line: {got_line!r}")
        gate = gate_line(got_md)
        need(got_line == gate, f"d ({name}): #spec-line is {got_line!r}, gates/spec.sh says {gate!r} on #spec-preview", got_md)
        is_ = "GO" if gate == "GO: spec" else "NO-GO"
        need(verdict == "-" or is_ == verdict, f"d ({name}): the gate says {gate!r}, want {verdict}", got_md)
        tab.page.evaluate("document.querySelector('#save').click()")
        tab.page.wait_for_timeout(100)
        tab.audit(f"d ({name})", allow=("/v1/spec-check",))
    # One call per pause, not per key.
    tab.page.goto("about:blank")
    tab.load("#request")
    tab.page.wait_for_timeout(1000)
    n = len(tab.posts)
    tab.page.click("input[name=title]")
    tab.page.keyboard.type("Typed key by key", delay=25)
    tab.page.wait_for_timeout(1500)
    calls = len(tab.posts) - n
    need(1 <= calls <= 2, f"d: sixteen keystrokes 25 ms apart made {calls} spec checks, want one per pause")
    ctx.close()
    # No #l0-note above L0.
    with tempfile.TemporaryDirectory() as tmp:
        above = json.loads(json.dumps(golden))
        above["source"]["level"] = "l1"
        path = pathlib.Path(tmp) / "l1.json"
        path.write_text(json.dumps(above), encoding="utf-8")
        with Console(path) as c:
            ctx = browser.new_context()
            t = Tab(ctx, c.base)
            t.load("#request")
            t.page.wait_for_timeout(500)
            need(t.page.locator("#l0-note").count() == 0, "d: the editor says it is at L0 on a logbook whose source.level is l1")
            ctx.close()


# --- e. the board ---------------------------------------------------------------------

def e_board(browser):
    with Board() as b:
        ctx = browser.new_context(color_scheme="light", viewport={"width": 1600, "height": 900})
        tab = Tab(ctx, b.base)
        tab.page.goto(b.base + "/")
        tab.page.wait_for_selector("select#theme", timeout=TIMEOUT_MS)
        tab.page.wait_for_timeout(500)
        before = tab.page.inner_text("body")
        tab.page.wait_for_timeout(600)
        need(tab.page.inner_text("body") == before, "e: the board's text is not stable before the switch is touched")
        need(tab.page.evaluate("document.documentElement.dataset.theme ?? null") is None, "e: the board has a data-theme before anything is chosen")
        looks = {}
        for value in ("dark", "light", "system", "dark"):
            tab.page.select_option("select#theme", value)
            tab.page.wait_for_timeout(200)
            got = tab.page.evaluate("document.documentElement.dataset.theme ?? null")
            need(got == (None if value == "system" else value), f"e: the board's switch set to {value} leaves data-theme {got!r}")
            diff = text_diff(before, tab.page.inner_text("body"))
            need(diff is None, f"e: the board reads differently under {value}: {diff}")
            looks[value] = tab.page.evaluate("getComputedStyle(document.body).backgroundColor")
        need(looks["dark"] != looks["light"], f"e: the board's light and dark themes paint the same background {looks['dark']}")
        need(looks["system"] == looks["light"], "e: the board's system theme in a light OS is not the light theme")
        tab.page.select_option("select#theme", "dark")
        need(tab.page.evaluate(f"localStorage.getItem('{THEME_KEY}')") == "dark", f"e: the board keeps no '{THEME_KEY}'")
        tab.page.reload()
        tab.page.wait_for_selector("select#theme", timeout=TIMEOUT_MS)
        need(tab.page.evaluate("document.documentElement.dataset.theme ?? null") == "dark", "e: the board forgets the theme on reload")
        need(tab.page.evaluate("document.querySelector('select#theme').value") == "dark", "e: the board's switch does not show the kept theme")
        tab.audit("e, the board", allow=())
        ctx.close()
        ctx = browser.new_context(color_scheme="dark", viewport={"width": 1600, "height": 900})
        ctx.add_init_script(STORAGE_THROWS)
        tab = Tab(ctx, b.base)
        tab.page.goto(b.base + "/")
        tab.page.wait_for_selector("select#theme", timeout=TIMEOUT_MS)
        tab.page.select_option("select#theme", "light")
        need(tab.page.evaluate("document.documentElement.dataset.theme ?? null") == "light", "e: a board whose storage is refused cannot switch")
        ctx.close()


# --- f. the ADR search, over this repository's own map ----------------------------------

def f_adrs(browser):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        env = {k: v for k, v in os.environ.items() if k not in ("STATE_STORE", "DELIVERY", "MAP_FILE", "LOGBOOK_FILE")}
        targets = tmp / "targets.txt"
        targets.write_text("\n".join(sorted(set(re.findall(r"^([a-z][a-z0-9-]*):", (ROOT / "Makefile").read_text(encoding="utf-8"), re.M)))) + "\n",
                           encoding="utf-8")
        built = subprocess.run([sys.executable, "core/map.py", "build", "--repo", ".", "--rev", "HEAD", "--tickets", "tickets", "--targets", str(targets),
                                "--exclude", "docs/PLAN.md docs/plans/* .claude/*", "--out", str(tmp / "map.sqlite")],
                               cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        need(built.returncode == 0, "f: core/map.py could not build this repository's map", built.stderr.strip()[-400:])
        made = subprocess.run([sys.executable, "core/logbook.py", "--out", str(tmp / "lb.json")], cwd=ROOT, capture_output=True, text=True, check=False,
                              env={**env, "MAP_FILE": str(tmp / "map.sqlite")})
        need(made.returncode == 0, "f: core/logbook.py could not write the logbook", made.stdout.strip()[-300:], made.stderr.strip()[-400:])
        book = json.loads((tmp / "lb.json").read_text(encoding="utf-8"))
        items = book.get("adrs", {}).get("items") if isinstance(book.get("adrs"), dict) else None
        need(items, f"f: the logbook has no ADR: {json.dumps(book.get('adrs'))[:200]}")
        numbers = {i["number"] for i in items}
        need({"0054", "0055"} <= numbers, f"f: the map does not hold ADR 0054 and 0055: {sorted(numbers)[:5]}")
        cited = next(i for i in items if i["number"] == "0055")["files"]
        need("core/spec.py" in cited, f"f: the map says ADR 0055 cites {cited}, not core/spec.py")
        with Console(tmp / "lb.json") as c:
            ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
            tab = Tab(ctx, c.base)
            tab.load("#adrs")

            listing = "[...document.querySelectorAll('.adr[data-number]')].map((a) => a.dataset.number)"

            def results(q, what):
                """The ADR numbers listed once the list stops changing after the query is typed."""
                tab.page.fill("input#adr-q", q)
                last, same = None, 0
                for _ in range(40):
                    tab.page.wait_for_timeout(100)
                    got = tab.page.evaluate(listing)
                    same = same + 1 if got == last else 0
                    last = got
                    if same >= 2:
                        break
                tab.audit(f"f, {what}")
                return last

            first = results("0055", "the number")
            need(first and first[0] == "0055", f"f: searching 0055 lists {first[:5]} first, want 0055 first")
            need(tab.page.locator(".adr[data-number='0055'] a").count() >= 1, "f: the result for ADR 0055 links nothing (its files, tickets and ADRs are links)")
            for q in ("59", "ADR 0059", "0059"):
                got = results(q, f"the number {q}")
                need("0059" in got, f"f: searching {q!r} lists {got[:6]}, want 0059 among them")
            need("0054" in results("project map", "a word of the title"), "f: searching the title words 'project map' does not find ADR 0054")
            need("0054" in results("MAP PROJECT", "the title words, upside down and in capitals"),
                 "f: searching 'MAP PROJECT' does not find ADR 0054: every word, in one ADR, case ignored")
            # Case is ignored: a capitalised word an ADR never writes in lower case, searched in both.
            pick = next(((i["number"], w) for i in items for w in re.findall(r"\b[A-Z][a-z]{5,}\b", i["text"]) if w.lower() not in i["text"]), None)
            need(pick, "f: no ADR has a capitalised word it never writes in lower case: the case of a query proves nothing")
            for q in (pick[1].lower(), pick[1].upper()):
                need(pick[0] in results(q, f"the word {q}"), f"f: searching {q!r} does not find ADR {pick[0]}, which has {pick[1]!r}: case is ignored")
            need("0055" in results("core/spec.py", "a file it cites"), "f: searching the file core/spec.py does not find ADR 0055, which cites it")
            need(results("zzzzqqqq-nothing", "nothing") == [], "f: a query that matches nothing still lists ADRs")
            # The link: #adrs?q=<query> sets the query.
            tab.page.goto("about:blank")
            tab.load("#adrs?q=0055")
            tab.page.wait_for_timeout(600)
            need(tab.page.input_value("input#adr-q") == "0055", f"f: #adrs?q=0055 leaves the query {tab.page.input_value('input#adr-q')!r}")
            got = tab.page.evaluate(listing)
            need(got and got[0] == "0055", f"f: #adrs?q=0055 lists {got[:5]} first, want 0055")
            tab.audit("f, the link")
            ctx.close()
        # No map, no ADR: the screen says so (docs/adr/0059 §3).
        book["adrs"] = {"ok": False, "error": "no map at .crew/map.sqlite; build it with ./go map"}
        (tmp / "none.json").write_text(json.dumps(book), encoding="utf-8")
        with Console(tmp / "none.json") as c:
            ctx = browser.new_context()
            tab = Tab(ctx, c.base)
            tab.load("#adrs")
            tab.page.wait_for_timeout(400)
            need("./go map" in tab.page.inner_text("main"), "f: with no map, the ADR screen does not say to run ./go map")
            ctx.close()


# --- the checks that the checks themselves can fail ------------------------------------

def self_checks():
    v = View(q="a/b c", feature="venues", collapsed=["ci-failed", "held"], card="0005")
    need(v.hash() == "#kanban?q=a%2Fb%20c&feature=venues&collapsed=ci-failed,held&card=0005", f"the hash writer is wrong: {v.hash()}")
    need(View().hash() == "#kanban", "the default view is not the bare #kanban")
    need(view_problems(v.hash(), v) is None, "a hash is not accepted for its own view")
    need(view_problems("#kanban?feature=venues&q=a", View(q="a", feature="venues")), "a hash with its keys out of order is accepted")
    need(view_problems("#kanban?q=b", View(q="a")), "a hash that says another search is accepted")
    need(view_problems("#kanban", View(q="a")), "a hash that omits the search is accepted")
    need(view_problems("#overview", View()), "a hash of another screen is accepted for the kanban")
    need(view_problems("#kanban?q=a&card=1", View(q="a")), "a hash with an extra key is accepted")
    need(read_hash("#kanban?collapsed=a%2Cb,c")[1] == {"collapsed": ["a", "b", "c"]}, "a collapsed list is not read with its comma, escaped or not")
    need(view_problems("#kanban?collapsed=b,a", View(collapsed=["a", "b"])) is None, "two collapsed columns are an ordered pair")
    need(view_problems("#kanban?collapsed=a", View(collapsed=["a", "b"])), "a hash with one collapsed column is accepted for two")
    need(not matches({"id": "0001", "title": "x", "perimeter": ["a/*"]}, q="b/c"), "a search for a path no glob matches matches")
    need(matches({"id": "0001", "title": "x", "perimeter": ["a/*"]}, q="a/b/c"), "a glob that crosses / does not match a path")
    need(matches({"id": "0001", "title": "Tidy", "perimeter": {"ok": False}}, q="tid"), "a title is not searched")
    need(not matches({"id": "0001", "title": "x", "perimeter": [], "feature": "f"}, feature="g"), "a filter on another feature matches")
    need(signature({"lanes": [""], "cols": [], "drawer": "1"}) != signature({"lanes": [""], "cols": [], "drawer": None}), "the signature ignores the drawer")
    need(text_diff("a\nb", "a\nc") and text_diff("a", "a") is None, "the text comparison is wrong")
    need(gate_line("# 1\n") .startswith("NO-GO: spec"), "gates/spec.sh does not refuse an empty spec")


def main():
    real = sys.stdout
    sys.stdout = sys.stderr  # a library that prints must not break the one-line contract
    try:
        need(GOLDEN.is_file(), f"{GOLDEN.relative_to(ROOT)} not found")
        need((ROOT / "console" / "serve.py").is_file(), "console/serve.py not found")
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        need(any(t.get("adrs") for t in golden["tickets"]), "the golden has no ticket with adrs: it is not a 1.2 logbook")
        self_checks()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                with Console(GOLDEN) as c:
                    say(f"console-ui: the console over {GOLDEN.name} on {c.base}")
                    a_posts(browser, c.base)
                    a_board(browser, c.base, golden)
                    b_hash(browser, c.base, golden)
                    c_themes(browser, c.base, golden)
                    d_editor(browser, c.base, golden)
                e_board(browser)
                f_adrs(browser)
            finally:
                browser.close()
        line, code = f"GO: {NAME}", 0
    except Fail as fail:
        line, code = f"NO-GO: {NAME} — {' '.join(str(fail).split())}", 1
    except Exception as exc:  # noqa: BLE001 - whatever else breaks is a NO-GO with its name, never a traceback on stdout
        import traceback
        traceback.print_exc()
        line, code = f"NO-GO: {NAME} — {type(exc).__name__}: {' '.join(str(exc).split())[:300]}", 1
    print(line, file=real, flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
