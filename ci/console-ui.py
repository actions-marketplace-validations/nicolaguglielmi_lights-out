#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""console-ui: the console's interactions, proved in a browser (docs/adr/0059 §5).

    python3 ci/console-ui.py

Prints exactly one line on stdout, as every gate does (CLAUDE.md): `GO:
console-ui` or `NO-GO: console-ui — <why>`, exit 0 or 1; everything else goes
to stderr. It is not in `./go ci`: the workbench has no browser. It runs as a
job of .github/workflows/ci.yml, in the Playwright image site.yml pins.

Written from docs/adr/0059 and the DOM contract it names (and, for t-z, from
docs/adr/0071; for `agents`, from docs/adr/0073), not from console/index.html.
It starts console/serve.py itself, in snapshot mode, over
fixtures/logbook/golden-1.3.json, and drives it with Playwright:

  a. every interaction of the kanban in a scripted sequence (search, each
     filter, grouping, hiding the empty columns, collapsing, a click on a
     card, the arrows, Enter, Escape and `/`): after each step every card
     sits in the column the logbook puts it in, the cards shown are those the
     step's rule gives, the hash carries the view, and no POST was sent;
  b. a view set by interactions, read from location.hash and opened in a new
     page, draws the same lanes, columns, collapsed columns, cards and drawer;
     so does a hash written by hand;
  c. every screen's main text, #network's included, is the same under the system
     theme (light and dark), the light and the dark theme, and with localStorage
     refusing;
  d. the editor: its line is the one gates/spec.sh prints on its preview;
  e. the board's theme switch changes its theme and nothing it says;
  f. the ADR search, over a logbook read from this repository's own map,
     finds an ADR by its number, by a word of its title and by a file it
     cites;
  g. the board fits (docs/adr/0063 §1): at 1440x900 the page and the board do
     not scroll sideways, the empty columns are narrow and never collapsed,
     every column sits in its band under a band name in the logbook's order;
     at 390x844 the columns stack, the page does not scroll sideways and the
     nav is one line;
  h. the now line (§2): one on every card, in the drawer and on the timeline,
     the same text, its turn and words by the DOM contract's rules; "Your turn"
     exactly on 0009, 0007, 0004 and 0005 over the golden, plus the held
     canary of a logbook derived from it; the launch screen names that ticket;
  i. the overview's first panel, #your-turn, lists exactly those tickets;
  j. the timeline (§3): its rows are the logbook's, in order, its four stages
     are marked, a ticket opened directly skips Spec, and the back link opens
     the kanban with that card's drawer;
  k. the editor (§5): the gate's line and the Request button are in the
     viewport while a criterion has the focus, at both sizes; a save answered
     GO (intercepted: the server side is ci/logbook.sh's runtime check) clears
     the draft, disables Request and links the new ticket;
  l. the card's face (docs/adr/0068 §2): the labels (priority, feature with its
     hue), the title with the search's <mark>, the actor badge by the table's
     rule, the time in state against the reference "now", the rework pips;
  m. the card's back (§3): a modal dialog#card-back holding aside#drawer, focus
     in and the board inert, the now line, the strip and the compact rows equal
     the timeline's, the one action and the open question, Esc and a click on
     the backdrop close it and the focus returns to the card, full screen at
     390 px, no POST;
  n. "Your turn only" (§5): button#only-mine[aria-pressed], the cards, the hash
     key `turn=you` in its place in the key order, a page opened on that hash;
  o. the flight and the announcement (§4), on a LIVE console SIMULATED in the
     browser (page.route answers /v1/console.json with mode "live" and
     /v1/logbook.json first with the golden, then with one card moved): the
     moved card is marked, announced, and runs an animation unless the
     visitor prefers reduced motion;
  p. a long column scrolls inside itself with its header in view (§4);
  q. contrast and focus (§6), light and dark: every text in the board and in the
     open back against the first opaque background behind it (WCAG 2.1 AA), a
     focused card's outline at 3:1; the same for #network (an SVG text by its
     fill), every control the keyboard reaches there at 2 px and 3:1, and the
     replay label;
  r. the phone's band bar (§5);
  s. no drag: no draggable attribute, no drag or drop listener registered, on the
     board and on #network (which sends no POST either);

ADR 0071, the governed network (every expectation is worked out from the golden's
own fields at run time; the CLI is core/network.py run as a subprocess):

  t. the route `#network[/<id>][?attempt=<n>&replay=1]` (keys in that order,
     defaults left out), the nav link, the default ticket (newest updated_at,
     ties to the highest id), select#net-ticket writing the link, a link opened
     in a new page drawing the same screen (same .net-fact set, same data-
     attributes), ?attempt=1 lighting attempt 1's gates, #network-words equal to
     `core/network.py --table`;
  u. section 2's contract for every golden ticket: section#net, #net-tower, the
     six .net-role and their data-ran, the .net-worker of each member (harness,
     model, replayed, hand-written), the .net-gate edges in run order then the
     Makefile's remaining GATES as not-run, #net-review, #net-rework only when
     there is a rework, the .net-stage nodes, #net-human; the stream (lines
     verbatim, the patch equal to the logbook's or its withheld reason); the
     tr.net-file rows with their tests, ADR links and holders;
  v. on logbooks derived from the golden: a patch over the cap shows
     data-truncated="true" and the CLI says so; an attempt rejected at perimeter
     shows one NO-GO edge and its withheld patch;
  w. the .net-fact texts of section#net are exactly the CLI's fact lines (the
     lines that start with a space) for each golden ticket at its default
     attempt, and for the default ticket;
  x. the replay, on Playwright's clock: label visible, data-row counting 0..N on
     the 2000 ms beat, data-replay=done with the static drawing at the end, no
     request sent, by the button and by ?replay=1;
  y. live, SIMULATED (page.route answers /v1/console.json with mode "live" and
     /v1/logbook.json first with a logbook derived from the golden where 0010 is
     at attempt 1 and ci-failed, then with the golden): net-new on what changed,
     #announce naming 0010, an animation unless prefers-reduced-motion, where
     none runs and the mark stays; the screen without an id follows the newest
     ticket;
  z. a 1.2 logbook (golden-1.2.json, a second console) draws the one
     .net-gate[data-gate=gates] and says the old_logbook sentence of the page's
     own #network-words, the perimeter still shown.

ADR 0073, what the contract gives the agents (every expectation is worked out
from the golden's own fields at run time):

  agents. the Thresholds screen's Agents panel prints the logbook's lines
     (docs/adr/0073 §10), and each card's back shows its task's MCP calls and
     its review's instructions, and no such row when they are null.

Every comparison is shown first to fail on a wrong input (self_checks, and
the probes in a_board and a_posts): a gate that cannot fail is not a gate.
"""
import datetime
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
GOLDEN = ROOT / "fixtures" / "logbook" / "golden-1.3.json"
SCREENS = ["overview", "kanban", "tickets", "ticket/{id}", "specs", "request", "adrs", "incidents", "launch", "thresholds", "network", "network/0010"]
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

HASH_KEYS = ("q", "feature", "priority", "turn", "group", "empty", "collapsed", "card")


def enc(value):
    """encodeURIComponent, for the characters these views hold."""
    return urllib.parse.quote(value, safe="-_.!~*'()")


class View:
    """The page's one view; every interaction changes it and nothing else."""

    def __init__(self, **kw):
        self.q, self.feature, self.priority, self.turn, self.group, self.empty = "", "", "", "", "", ""
        self.collapsed, self.card = [], ""
        self.__dict__.update(kw)

    def hash(self):
        """#kanban?q=..&feature=..&priority=..&turn=you&group=..&empty=hide&collapsed=a,b&card=0005,
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
    // textContent, not innerText: a column's words are the DOM's, and the
    // CSS that sets their case is presentation, like the theme.
    cards: [...c.querySelectorAll('.card[data-id]')].map((k) => k.dataset.id), text: c.textContent}));
  const drawer = document.querySelector('aside#drawer');
  const q = document.querySelector('input#kanban-q');
  const val = (n) => { const s = document.querySelector('main select[name=' + n + ']'); return s ? s.value : null; };
  const active = document.activeElement;
  const mine = document.querySelector('button#only-mine');
  return {only_mine: mine ? mine.getAttribute('aria-pressed') : null, cols, lanes: [...document.querySelectorAll('.lane[data-lane]')].map((l) => l.dataset.lane),
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


def matches(ticket, q="", feature="", priority="", turn="", you=()):
    """Whether the card of TICKET shows under the search Q and the filters:
    the search is over the id, the title and the perimeter, a path matching a
    card when one of its globs matches it (`*` crosses `/`) or contains it;
    TURN "you" keeps the tickets of YOU, the ids whose turn is a person's."""
    if feature and ticket.get("feature") != feature:
        return False
    if priority and ticket.get("priority") != priority:
        return False
    if turn == "you" and ticket["id"] not in you:
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
        self.you = {i for i, e in turns_of(golden).items() if e["turn"] == "you"}
        self.view = View()

    def board(self):
        return self.page.evaluate(BOARD_JS)

    def expect(self, what, **kw):
        """Wait until the cards shown are the ones the rule gives, then check the board and the hash."""
        want = {t["id"] for t in self.tickets if matches(t, kw.get("q", self.view.q), kw.get("feature", self.view.feature),
                                                         kw.get("priority", self.view.priority), kw.get("turn", self.view.turn), self.you)}
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

    def only_mine(self, on, what):
        """Press or release button#only-mine; its aria-pressed must say which."""
        self.view.turn = "you" if on else ""
        self.page.click("button#only-mine")
        self.tab.wait("want => { const b = document.querySelector('button#only-mine'); return !!b && b.getAttribute('aria-pressed') === want; }",
                      "true" if on else "false", f"kanban, {what}: button#only-mine never became aria-pressed={'true' if on else 'false'}")
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


# --- ADR 0063: whose turn it is ---------------------------------------------------------
# Written from docs/adr/0063 and its DOM contract, not from console/index.html.

def _load_tower():
    """core/tower.py, for its NEXT table, as ci/board.sh imports it (loaded by path: core/ stays off sys.path)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("lights_out_tower", ROOT / "core" / "tower.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


tower = _load_tower()

# The ADR's bands (§1): a state no band names goes under "other".
BAND_OF = {"requested": "spec", "questions": "spec", "spec-ready": "spec", "opened": "build", "pr-opened": "build",
           "review": "test", "ci-passed": "test", "ci-failed": "test", "needs-human": "test",
           "merged": "release", "main-green": "release", "held": "release", "rolled-back": "release"}
STAGES = ["spec", "build", "test", "release"]
# The ADR's numbers: a narrow column is 40 px, a card column at least 140 (§1,
# decisions); a few px of slack for rounding; the stack's "a few px" is 4.
NARROW_PX, WIDE_MIN_PX, SLACK_PX, STACK_PX = 40, 140, 0.5, 4
# §7: "Your turn" appears exactly on these over the golden.
YOUR_TURN_GOLDEN = ["0009", "0007", "0004", "0005"]
DESKTOP, PHONE = {"width": 1440, "height": 900}, {"width": 390, "height": 844}


def derive(golden, tmp):
    """Two logbooks derived from the golden, written to TMP (as d_editor derives an L1 one):
    held, where ticket 0002 is the held canary the launch record names, and holders, where
    ticket 0005 waits for ticket 0003's files."""
    held = json.loads(json.dumps(golden))
    two = next(t for t in held["tickets"] if t["id"] == "0002")
    two["release"]["version"] = held["launch"]["record"]["version"]
    two["outcome"] = {"verdict": "GO", "judge": "verify", "line": "GO: launchpad — held at 25%"}
    holders = json.loads(json.dumps(golden))
    next(t for t in holders["tickets"] if t["id"] == "0005")["wait"]["holders"] = ["0003"]
    # faces (ADR 0068 §2): a feature whose name holds an astral character (two UTF-16 code
    # units) and one with an accent, a priority on a ticket that had none, a ticket whose last
    # history entry is not its state (no time in state) and one with no attempt (no pips).
    faces = json.loads(json.dumps(golden))
    by_id = {t["id"]: t for t in faces["tickets"]}
    by_id["0005"]["feature"], by_id["0005"]["priority"] = "launch-\U0001F600", "P3"
    by_id["0004"]["feature"] = "été"
    by_id["0003"]["priority"] = "P2"
    by_id["0003"]["history"][-1]["state"] = "pr-opened"
    by_id["0007"]["attempt"] = None
    # long (§4): twenty more tickets in ci-failed, copies of 0003 under new ids.
    long = json.loads(json.dumps(golden))
    proto = next(t for t in long["tickets"] if t["id"] == "0003")
    column = next(c for c in long["kanban"] if c["state"] == "ci-failed")
    for n in range(20):
        copy = json.loads(json.dumps(proto))
        copy["id"] = f"{100 + n:04d}"
        long["tickets"].append(copy)
        column["tickets"].append(copy["id"])
    paths = {}
    for name, book in (("held", held), ("holders", holders), ("faces", faces), ("long", long)):
        paths[name] = tmp / f"{name}.json"
        paths[name].write_text(json.dumps(book), encoding="utf-8")
    return {"held": held, "holders": holders, "faces": faces, "long": long}, paths


def expected_now(t, launch, max_attempts, who=None):
    """What the now line of ticket T must be, by the first rule that matches (the DOM contract):
    {turn, contains, starts, href}. WHO is the page's own sentence per step, when it is known."""
    out, wait, state, ident = t.get("outcome") or {}, t.get("wait"), t["state"], t["id"]
    if out.get("verdict") == "stranded" or wait:
        if (wait or {}).get("holders"):
            return {"turn": "stopped", "contains": [], "starts": None, "href": None}
        return {"turn": "you", "contains": [f"./go resume TICKET={ident}"], "starts": None, "href": None}
    questions = t.get("questions") or []
    if state == "questions" and questions and not questions[-1].get("answer"):
        who_asked = "spec gate's" if questions[-1].get("from") == "spec" else "product role's"
        return {"turn": "you", "contains": [who_asked], "starts": None, "href": f"#ticket/{ident}"}
    if state == "needs-human":
        return {"turn": "you", "contains": [], "starts": None, "href": f"#ticket/{ident}"}
    if state == "held" and out.get("judge") == "human":
        return {"turn": "done", "contains": [], "starts": None, "href": None}
    record = (launch or {}).get("record") or {}
    if state == "held" and (t.get("release") or {}).get("version") == record.get("version") \
            and "promoted" not in record and "rejected" not in record:
        return {"turn": "you", "contains": ["go-for-launch"], "starts": None, "href": "#launch"}
    if state == "rolled-back":
        return {"turn": "done", "contains": [], "starts": None, "href": None}
    if state == "ci-failed":
        attempt = t.get("attempt") or 1
        return {"turn": "tower", "contains": ["dev-worker", f"attempt {attempt + 1} of {max_attempts}"], "starts": None, "href": None}
    if state in tower.NEXT and who:
        return {"turn": "tower", "contains": [], "starts": who[tower.NEXT[state]], "href": None}
    return {"turn": "tower", "contains": [], "starts": None, "href": None}


def max_attempts_of(book):
    return int(next(x["value"] for x in book["thresholds"] if x["key"] == "REWORK_MAX_ATTEMPTS"))


def turns_of(book):
    return {t["id"]: expected_now(t, book["launch"], max_attempts_of(book)) for t in book["tickets"]}


def now_problems(got, exp):
    """Why a now line {turn, text, hrefs} is not EXP, or None. HREFS is checked when the caller passes it."""
    text = got["text"]
    if got["turn"] != exp["turn"]:
        return f"data-turn is {got['turn']!r}, want {exp['turn']!r}: {text[:120]!r}"
    if exp["turn"] == "you" and not text.startswith("Your turn"):
        return f"a line for a person's turn does not start with 'Your turn': {text[:120]!r}"
    if exp["turn"] != "you" and "Your turn" in text:
        return f"a line that is not a person's turn says 'Your turn': {text[:120]!r}"
    for needle in exp["contains"]:
        if needle not in text:
            return f"the line does not say {needle!r}: {text[:160]!r}"
    if exp["starts"] and not text.startswith(exp["starts"]):
        return f"the line does not start with {exp['starts']!r}: {text[:160]!r}"
    if exp["href"] and got.get("hrefs") is not None and got["hrefs"] != [exp["href"]]:
        return f"the line's action links {got['hrefs']}, want [{exp['href']!r}]"
    return None


def fit_problems(info, order):
    """What is wrong with the desktop board INFO (the geometry the page measured)."""
    bad = []
    if info["doc"]["sw"] > info["doc"]["cw"]:
        bad.append(f"the page scrolls sideways: scrollWidth {info['doc']['sw']} > clientWidth {info['doc']['cw']}")
    if info["board"] is None:
        bad.append("there is no .board")
    elif info["board"]["sw"] > info["board"]["cw"]:
        bad.append(f"the board scrolls sideways: scrollWidth {info['board']['sw']} > clientWidth {info['board']['cw']}")
    states = [c["state"] for c in info["cols"]]
    if states != order:
        bad.append(f"the columns in DOM order are {states}, the logbook's kanban order is {order}")
    if not any(c["empty"] for c in info["cols"]):
        bad.append("no column is .empty: the golden has columns with no card")
    for c in info["cols"]:
        if c["band"] is None:
            bad.append(f"the column {c['state']} sits in no .band[data-band]")
        elif c["band"] != BAND_OF.get(c["state"], "other"):
            bad.append(f"the column {c['state']} sits in band {c['band']!r}, the ADR's is {BAND_OF.get(c['state'], 'other')!r}")
        if not c["name"]:
            bad.append(f"the column {c['state']}'s band has no .band-name")
        if (c["cards"] == 0) != c["empty"]:
            bad.append(f"the column {c['state']} holds {c['cards']} cards and is {'' if c['empty'] else 'not '}.empty")
        if c["empty"] and c["collapsed"]:
            bad.append(f"the empty column {c['state']} is .collapsed: emptiness never collapses")
        if c["empty"] and c["w"] > NARROW_PX + SLACK_PX:
            bad.append(f"the empty column {c['state']} is {c['w']:.1f} px wide, at most {NARROW_PX}")
        if not c["empty"] and c["w"] < WIDE_MIN_PX - SLACK_PX:
            bad.append(f"the column {c['state']} holds cards and is {c['w']:.1f} px wide, at least {WIDE_MIN_PX}")
    return bad


def stack_problems(info):
    """What is wrong with the phone board INFO: sideways page scroll, columns side by side, a nav of several lines."""
    bad = []
    if info["doc"]["sw"] > info["doc"]["cw"]:
        bad.append(f"the page scrolls sideways: scrollWidth {info['doc']['sw']} > clientWidth {info['doc']['cw']}")
    lefts = info["lefts"]
    if not lefts or max(lefts) - min(lefts) > STACK_PX:
        bad.append(f"the columns do not stack: their left edges are {sorted(set(round(x) for x in lefts))}")
    tops = info["nav_tops"]
    if len(tops) < 5:
        bad.append(f"nav#nav holds {len(tops)} links")
    elif max(tops) - min(tops) > 2:
        bad.append(f"nav#nav is not one line: its links' tops are {sorted(set(round(x) for x in tops))}")
    return bad


def inside(rect, vw, vh):
    """Whether a rect that was measured (top, left, bottom, right, h) is inside a VW x VH viewport and has a size."""
    return bool(rect) and rect["h"] > 0 and rect["top"] >= 0 and rect["left"] >= 0 and rect["bottom"] <= vh and rect["right"] <= vw


FIT_JS = """() => {
  const board = document.querySelector('.board');
  const de = document.documentElement;
  return {doc: {sw: de.scrollWidth, cw: de.clientWidth},
    board: board ? {sw: board.scrollWidth, cw: board.clientWidth} : null,
    lefts: [...document.querySelectorAll('.col')].map((c) => c.getBoundingClientRect().left),
    nav_tops: [...document.querySelectorAll('nav#nav a')].map((a) => a.getBoundingClientRect().top),
    cols: [...document.querySelectorAll('.col[data-state]')].map((c) => {
      const band = c.closest('.band[data-band]');
      const name = band ? band.querySelector('.band-name') : null;
      return {state: c.dataset.state, band: band ? band.dataset.band : null, name: name ? name.textContent.trim() : '',
        empty: c.classList.contains('empty'), collapsed: c.classList.contains('collapsed'),
        cards: c.querySelectorAll('.card').length, w: c.getBoundingClientRect().width};
    })};
}"""
NOW_JS = """(sel) => [...document.querySelectorAll(sel)].map((n) => ({turn: n.dataset.turn || null,
  text: n.textContent.replace(/\\s+/g, ' ').trim(), hrefs: [...n.querySelectorAll('a.act[href]')].map((a) => a.getAttribute('href'))}))"""
CARDS_JS = """() => [...document.querySelectorAll('.card')].map((c) => ({id: c.dataset.id, nows: c.querySelectorAll('.now').length}))"""
TIMELINE_JS = """() => ({
  phases: [...document.querySelectorAll('tr[data-phase]')].map((r) => r.dataset.phase),
  band_rows: [...document.querySelectorAll('tr.band-row[data-band]')].map((r) => r.dataset.band),
  stages: [...document.querySelectorAll('ol#stages li')].map((l) => ({band: l.dataset.band, mark: l.dataset.mark, current: l.getAttribute('aria-current')})),
  lists: document.querySelectorAll('ol#stages').length,
  back: (document.querySelector('a#back-to-kanban') || {getAttribute: () => null}).getAttribute('href')})"""


def one_now(tab, selector, what):
    """The one now line SELECTOR finds, or a NO-GO that says how many it found."""
    found = tab.page.evaluate(NOW_JS, selector)
    need(len(found) == 1, f"{what}: {len(found)} .now lines under {selector}, want exactly one")
    return found[0]


def wait_for(tab, selector, what):
    tab.wait("s => !!document.querySelector(s)", selector, f"{what}: {selector} never appeared")


def draw_kanban(tab, what):
    tab.page.goto("about:blank")
    tab.load("#kanban")
    wait_for(tab, ".col[data-state]", what)
    wait_for(tab, ".card[data-id]", what)


# --- g. the board fits ---------------------------------------------------------------------

def g_fit(browser, bases, golden):
    order = [c["state"] for c in golden["kanban"]]
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    draw_kanban(tab, "g, 1440x900")
    tab.page.wait_for_timeout(300)
    info = tab.page.evaluate(FIT_JS)
    bad = fit_problems(info, order)
    need(not bad, f"g, 1440x900: {bad[0] if bad else ''}", *bad)
    tab.audit("g, 1440x900")
    ctx.close()
    ctx = browser.new_context(viewport=PHONE)
    tab = Tab(ctx, bases["golden"])
    draw_kanban(tab, "g, 390x844")
    tab.page.wait_for_timeout(300)
    info = tab.page.evaluate(FIT_JS)
    bad = stack_problems(info)
    need(not bad, f"g, 390x844: {bad[0] if bad else ''}", *bad)
    tab.audit("g, 390x844")
    ctx.close()


# --- h. the now line -------------------------------------------------------------------------

def check_now_of(tab, base, name, book, ids):
    """Every card of BOOK holds one now line that is the rule's; for each of IDS the drawer's and the
    timeline's lines are one and the same text. The action's link is the card's and the drawer's: the
    timeline's head may point at its own screen another way."""
    turns = turns_of(book)
    draw_kanban(tab, f"h ({name})")
    cards = tab.page.evaluate(CARDS_JS)
    need(sorted(c["id"] for c in cards) == sorted(t["id"] for t in book["tickets"]),
         f"h ({name}): the cards are {sorted(c['id'] for c in cards)}, the tickets are {sorted(t['id'] for t in book['tickets'])}")
    for c in cards:
        need(c["nows"] == 1, f"h ({name}): card {c['id']} holds {c['nows']} .now lines, want exactly one")
    on_card = {}
    for ident, exp in turns.items():
        got = one_now(tab, f".card[data-id='{ident}'] .now", f"h ({name}), card {ident}")
        problem = now_problems(got, exp)
        need(problem is None, f"h ({name}), card {ident}: {problem}")
        on_card[ident] = got["text"]
    for ident in ids:
        exp = turns[ident]
        tab.page.goto("about:blank")
        tab.load(f"#kanban?card={ident}")
        tab.wait("id => { const d = document.querySelector('aside#drawer'); return !!d && d.dataset.id === id; }", ident,
                 f"h ({name}): the drawer of {ident} never showed")
        got = one_now(tab, "aside#drawer .now", f"h ({name}), drawer {ident}")
        problem = now_problems(got, exp)
        need(problem is None, f"h ({name}), drawer {ident}: {problem}")
        need(got["text"] == on_card[ident], f"h ({name}), {ident}: the drawer says {got['text'][:100]!r}, the card says {on_card[ident][:100]!r}")
        tab.page.goto("about:blank")
        tab.load(f"#ticket/{ident}")
        wait_for(tab, "#ticket-now", f"h ({name}), timeline {ident}")
        got = one_now(tab, "#ticket-now .now", f"h ({name}), timeline {ident}")
        problem = now_problems({**got, "hrefs": None}, exp)
        need(problem is None, f"h ({name}), timeline {ident}: {problem}")
        need(got["text"] == on_card[ident], f"h ({name}), {ident}: the timeline says {got['text'][:100]!r}, the card says {on_card[ident][:100]!r}")
    tab.audit(f"h ({name})")
    return turns


def h_now(browser, bases, golden, books):
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    turns = check_now_of(tab, bases["golden"], "golden", golden, [t["id"] for t in golden["tickets"]])
    you = sorted(i for i, e in turns.items() if e["turn"] == "you")
    need(you == sorted(YOUR_TURN_GOLDEN), f"h: the golden's rules give {you} as a person's turn, the ADR names {sorted(YOUR_TURN_GOLDEN)}")
    # The launch screen of the golden: no ticket carries the record's version, and it names none.
    tab.page.goto("about:blank")
    tab.load("#launch")
    wait_for(tab, "#launch-ticket", "h, the golden's launch screen")
    need(tab.page.locator("#launch-ticket a[href^='#ticket/']").count() == 0,
         "h: the golden's launch screen links a ticket, but no ticket carries the record's version")
    ctx.close()
    # The held canary the launch record names: a person's turn, for go-for-launch, and the launch screen names it.
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["held"])
    turns = check_now_of(tab, bases["held"], "held and pressable", books["held"], ["0002"])
    need(turns["0002"]["turn"] == "you" and turns["0002"]["href"] == "#launch", f"h: the held canary's rule gave {turns['0002']}")
    draw_kanban(tab, "h (held)")
    need(tab.page.locator(".card[data-id='0002'] .now a.act[href='#launch']").count() == 1, "h (held): card 0002 has no .now a.act[href='#launch']")
    tab.page.goto("about:blank")
    tab.load("#launch")
    wait_for(tab, "#launch-ticket", "h (held), the launch screen")
    need(tab.page.locator("#launch-ticket a[href='#ticket/0002']").count() == 1,
         "h (held): #launch-ticket does not link #ticket/0002, the ticket whose release is the record's")
    tab.audit("h (held), the launch screen")
    ctx.close()
    # A ticket that waits for holders is stopped, and nobody's turn.
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["holders"])
    turns = check_now_of(tab, bases["holders"], "waiting for holders", books["holders"], ["0005"])
    need(turns["0005"]["turn"] == "stopped", f"h: the rule for a ticket with holders gave {turns['0005']}")
    ctx.close()


# --- i. the overview opens with what waits for a person --------------------------------------

def i_overview(browser, bases, golden, books):
    for name, key, book in (("golden", "golden", golden), ("held and pressable", "held", books["held"]),
                            ("waiting for holders", "holders", books["holders"])):
        base = bases[key]
        want = sorted(i for i, e in turns_of(book).items() if e["turn"] == "you")
        ctx = browser.new_context(viewport=DESKTOP)
        tab = Tab(ctx, base)
        tab.load("#overview")
        wait_for(tab, "#your-turn", f"i ({name})")
        first = tab.page.evaluate("() => document.querySelector('main .panel') === document.getElementById('your-turn')")
        need(first, f"i ({name}): #your-turn is not the first .panel in main")
        tab.page.wait_for_timeout(300)
        got = tab.page.evaluate("() => [...document.querySelectorAll('#your-turn li[data-id]')].map((l) => l.dataset.id)")
        need(sorted(got) == want, f"i ({name}): #your-turn lists {sorted(got)}, the tickets whose turn is a person's are {want}")
        tab.audit(f"i ({name})")
        ctx.close()


# --- j. the timeline ----------------------------------------------------------------------------

def j_timeline(browser, bases, golden):
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    turns = turns_of(golden)
    for t in golden["tickets"]:
        ident = t["id"]
        tab.page.goto("about:blank")
        tab.load(f"#ticket/{ident}")
        wait_for(tab, "tr[data-phase]", f"j, {ident}")
        info = tab.page.evaluate(TIMELINE_JS)
        want = [row["phase"] for row in t["timeline"]]
        need(info["phases"] == want, f"j, {ident}: the rows' phases are {info['phases']}, the logbook's timeline is {want}")
        need(info["band_rows"] and all(b in STAGES + ["other"] for b in info["band_rows"]),
             f"j, {ident}: the heading rows tr.band-row[data-band] are {info['band_rows']}")
        stages = info["stages"]
        need(info["lists"] == 1 and [s["band"] for s in stages] == STAGES,
             f"j, {ident}: ol#stages has the bands {[s['band'] for s in stages]} in {info['lists']} list(s), want {STAGES}")
        marks = [s["mark"] for s in stages]
        need(all(m in ("done", "now", "stopped", "ahead", "skipped") for m in marks), f"j, {ident}: the stage marks are {marks}")
        current = [s["band"] for s in stages if s["current"] == "step"]
        active = [s["band"] for s in stages if s["mark"] in ("now", "stopped")]
        need(current == active and len(active) <= 1,
             f"j, {ident}: aria-current='step' is on {current}, the stages marked now or stopped are {active}: exactly the one, or neither")
        # A state no band names sits under Other (ADR 0063 §1): the strip has no
        # band to mark for it, so only a ticket in one of the four bands must have one.
        if turns[ident]["turn"] != "done" and t["state"] in BAND_OF:
            need(len(active) == 1, f"j, {ident}: the turn is {turns[ident]['turn']} and no stage is marked now or stopped: {marks}")
        if t["state"] not in BAND_OF:
            need(not active, f"j, {ident}: its state {t['state']} is in no band, but the strip marks {active}")
        opened_directly = bool(t["history"]) and t["history"][0]["step"] == "open"
        need((stages[0]["mark"] == "skipped") == opened_directly,
             f"j, {ident}: {'opened directly' if opened_directly else 'requested'}, and spec is marked {stages[0]['mark']!r}")
        if ident == "0001":
            need(stages[3]["mark"] == "stopped", f"j, 0001: rolled back, and release is marked {stages[3]['mark']!r}, want 'stopped'")
        need(info["back"] == f"#kanban?card={ident}", f"j, {ident}: a#back-to-kanban links {info['back']!r}, want '#kanban?card={ident}'")
        tab.page.click("a#back-to-kanban")
        tab.wait("id => { const d = document.querySelector('aside#drawer'); return !!d && d.dataset.id === id; }", ident,
                 f"j, {ident}: the back link did not open the drawer of {ident}")
        keys, view = read_hash(tab.page.evaluate("location.hash"))
        need(view is not None and view.get("card") == ident, f"j, {ident}: after the back link the hash is {tab.page.evaluate('location.hash')!r}")
        tab.audit(f"j, {ident}")
    ctx.close()


# --- k. the editor keeps its verdict in view and files once ------------------------------------

RECTS_JS = """() => {
  const r = (s) => { const e = document.querySelector(s); if (!e) return null;
    const b = e.getBoundingClientRect(); return {top: b.top, left: b.left, bottom: b.bottom, right: b.right, h: b.height}; };
  return {vw: document.documentElement.clientWidth, vh: innerHeight, line: r('#spec-line'), save: r('button#save'), bar: r('#savebar')};
}"""
SPEC_LINE_JS = "() => /^(GO|NO-GO): spec/.test((document.querySelector('#spec-line') || {textContent: ''}).textContent)"


def k_editor(browser, bases):
    for name, size in (("1440x900", DESKTOP), ("390x844", PHONE)):
        ctx = browser.new_context(viewport=size)
        tab = Tab(ctx, bases["golden"])
        tab.load("#request")
        wait_for(tab, "#spec-line", f"k ({name})")
        fill_editor(tab.page, draft())
        tab.wait(SPEC_LINE_JS, None, f"k ({name}): #spec-line never showed the gate's line")
        tab.page.evaluate("window.scrollTo(0, 0)")
        tab.page.locator(".criterion").first.locator("input[name=then]").focus()
        tab.page.wait_for_timeout(300)
        rects = tab.page.evaluate(RECTS_JS)
        for what in ("line", "save"):
            need(inside(rects[what], rects["vw"], rects["vh"]),
                 f"k ({name}): {'#spec-line' if what == 'line' else 'button#save'} is at {rects[what]} with the focus in a criterion's Then, "
                 f"outside the {rects['vw']}x{rects['vh']} viewport")
        for part in ("#spec-chip", "#spec-line", "button#save"):
            need(tab.page.locator(f"#savebar {part}").count() == 1, f"k ({name}): #savebar does not hold {part}")
        tab.audit(f"k ({name})", allow=("/v1/spec-check",))
        ctx.close()
    # A save. The server side (what /v1/request writes, who it refuses) is ci/logbook.sh's runtime
    # check; this proves the page: a 200 {ticket, line: "GO: request", exit: 0} is intercepted here
    # with page.route, and the page must clear the draft, disable Request and link the new ticket.
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    sent = []

    def answer(route):
        sent.append(route.request.post_data or "")
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ticket": "0099", "line": "GO: request", "exit": 0}))

    tab.page.route("**/v1/request", answer)
    tab.load("#request")
    fill_editor(tab.page, draft())
    tab.wait(SPEC_LINE_JS, None, "k, the save: #spec-line never showed the gate's line")
    need(tab.page.locator("#saved a#new-ticket").count() == 0, "k, the save: #saved links a new ticket before anything was saved")
    need(tab.page.input_value("input[name=title]") == GOOD["title"], "k, the save: the title is not in the form before the save")
    need(tab.page.is_disabled("button#save"), "k, the save: button#save is enabled in snapshot mode")
    tab.page.evaluate("() => { const b = document.querySelector('button#save'); b.disabled = false; b.click(); }")
    tab.wait("() => !!document.querySelector('#saved a#new-ticket')", None, "k, the save: #saved never linked the new ticket")
    need(tab.page.get_attribute("#saved a#new-ticket", "href") == "#ticket/0099",
         f"k, the save: a#new-ticket links {tab.page.get_attribute('#saved a#new-ticket', 'href')!r}, want '#ticket/0099'")
    need(len(sent) == 1 and GOOD["title"] in sent[0], f"k, the save: the page sent {len(sent)} request(s) to /v1/request, the first {sent[0][:120] if sent else ''!r}")
    need(tab.page.input_value("input[name=title]") == "", f"k, the save: the title is {tab.page.input_value('input[name=title]')!r} after a GO, want it cleared")
    need(tab.page.is_disabled("button#save"), "k, the save: button#save is enabled after a GO, want it disabled until the next edit")
    tab.audit("k, the save", allow=("/v1/spec-check", "/v1/request"))
    ctx.close()


# --- ADR 0068: the kanban that is looked at ------------------------------------------------
# Written from docs/adr/0068, its acceptance criteria in docs/PLAN.md and the DOM contract
# the task names, not from console/index.html.

ACTORS = ("product", "spec", "dev", "gates", "reviewer", "tower", "canary")
# §2: the actor of each step of core/tower.py's PRECONDITION.
ACTOR_OF_STEP = {"clarify": "product", "answer": "product", "spec": "spec", "assign": "dev", "rework": "dev",
                 "ci": "gates", "review": "reviewer", "merge": "tower", "mainline": "tower", "release": "canary"}
MOVED_ID, MOVED_FROM, MOVED_TO = "0005", "opened", "pr-opened"
# Live, the age counts to the console's read_at: days after the golden's newest entry, so that it
# differs from the snapshot's reference.
READ_AT = "2026-11-12T08:10:07Z"
# Provenance, external: WCAG 2.1 SC 1.4.3 and 1.4.11 (ADR 0068 §6).
MIN_TEXT, MIN_LARGE, MIN_FOCUS = 4.5, 3.0, 3.0


def norm(text):
    return " ".join(str(text).split())


def actor_of(t, exp):
    """The badge of ticket T whose now line is EXP (§2): the table's actor of the step the tower
    requests when it is the tower's turn, else the turn itself; None for a state with no step."""
    if exp["turn"] != "tower":
        return exp["turn"]
    questions = t.get("questions") or []
    if t["state"] == "questions" and questions and questions[-1].get("answer"):
        step = "answer"
    else:
        step = tower.NEXT.get(t["state"])
    return ACTOR_OF_STEP[step] if step else None


def hue_of(name):
    """The sum of the UTF-16 code units of NAME, modulo 6 (§2)."""
    raw = name.encode("utf-16-le")
    return sum(int.from_bytes(raw[i:i + 2], "little") for i in range(0, len(raw), 2)) % 6


def parse_at(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def age_text(seconds):
    """Floor minutes below 60, else floor hours below 24, else floor days (§2)."""
    seconds = max(0, int(seconds))
    if seconds // 60 < 60:
        return f"{seconds // 60}m"
    if seconds // 3600 < 24:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def snapshot_ref(book):
    """The newest history `at` of every ticket: the snapshot's "now" (§2)."""
    return max(h["at"] for t in book["tickets"] for h in t["history"])


def expected_age(t, ref):
    """(datetime, text) of ticket T measured to REF, or None when the last history entry is not its state."""
    history = t.get("history") or []
    if not history or history[-1].get("state") != t["state"]:
        return None
    i = len(history)
    while i > 0 and history[i - 1].get("state") == t["state"]:
        i -= 1
    at = history[i]["at"]
    return at, age_text((parse_at(ref) - parse_at(at)).total_seconds())


def expected_pips(t, book):
    """(max, filled) from the thresholds' REWORK_MAX_ATTEMPTS and the ticket's attempt, or None."""
    try:
        top = int(next(x["value"] for x in book["thresholds"] if x["key"] == "REWORK_MAX_ATTEMPTS"))
        filled = t.get("attempt")
        if filled is None or isinstance(filled, bool):
            return None
        filled = int(filled)
    except (StopIteration, KeyError, TypeError, ValueError):
        return None
    return (top, filled) if top > 0 and filled >= 0 else None


def face_problems(face, t, exp, book, ref):
    """Why the card FACE (what the page drew) is not what ADR 0068 §2 says for ticket T, or []."""
    bad = []
    kinds = sorted(l["kind"] for l in face["labels"])
    want_kinds = sorted(k for k, v in (("priority", t.get("priority")), ("feature", t.get("feature"))) if v)
    if kinds != want_kinds:
        bad.append(f"the labels are {kinds}, the ticket has {want_kinds}")
    for label in face["labels"]:
        if label["kind"] == "priority" and label["text"] != t.get("priority"):
            bad.append(f"the priority label says {label['text']!r}, the ticket's is {t.get('priority')!r}")
        if label["kind"] == "feature":
            if label["text"] != t.get("feature"):
                bad.append(f"the feature label says {label['text']!r}, the ticket's is {t.get('feature')!r}")
            elif label["hue"] != str(hue_of(t["feature"])):
                bad.append(f"the feature {t['feature']!r} has data-hue {label['hue']!r}, the sum of its UTF-16 units mod 6 is {hue_of(t['feature'])}")
    if face["title"] is None or norm(t.get("title") or "") not in face["title"]:
        bad.append(f"the .title is {face['title']!r}, the ticket's name is {t.get('title')!r}")
    if face["nows"] != 1:
        bad.append(f"{face['nows']} .now lines, want one")
    want_actor = actor_of(t, exp)
    if face["who"] != ([want_actor] if want_actor else []):
        bad.append(f"the .who badges are {face['who']}, want {[want_actor] if want_actor else 'none'} (turn {exp['turn']}, state {t['state']})")
    age = expected_age(t, ref)
    if face["age"] != ([{"datetime": age[0], "text": age[1]}] if age else []):
        bad.append(f"the time.age is {face['age']}, want {[{'datetime': age[0], 'text': age[1]}] if age else 'none'}")
    pips = expected_pips(t, book)
    want_pips = [{"max": str(pips[0]), "filled": str(pips[1]), "pip": pips[0], "on": pips[1]}] if pips else []
    if face["pips"] != want_pips:
        bad.append(f"the .pips are {face['pips']}, want {want_pips or 'none'}")
    return bad


def mark_problems(face, t, q):
    """Why the <mark>s in the title of a card shown under the search Q are wrong: each is the match,
    case ignored, as many as the title holds; none for a card the perimeter or the id alone matched."""
    title, low = norm(t.get("title") or ""), q.lower()
    n = title.lower().count(low)
    if len(face["marks"]) != n:
        return f"the title {title!r} holds {n} match(es) of {q!r}, the page marks {len(face['marks'])}"
    if any(m.lower() != low for m in face["marks"]):
        return f"a <mark> says {face['marks']}, want only {q!r}, whatever the case"
    return None


FACE_JS = """() => [...document.querySelectorAll('.card[data-id]')].map((c) => {
  const title = c.querySelector('.title');
  return {id: c.dataset.id,
    labels: [...c.querySelectorAll('.label')].map((l) => ({kind: l.dataset.kind || null, hue: l.dataset.hue === undefined ? null : l.dataset.hue, text: l.textContent.trim()})),
    title: title ? title.textContent.replace(/\\s+/g, ' ').trim() : null,
    marks: title ? [...title.querySelectorAll('mark')].map((m) => m.textContent) : [],
    nows: c.querySelectorAll('.now').length,
    who: [...c.querySelectorAll('.who')].map((w) => (w.dataset.actor === undefined ? null : w.dataset.actor)),
    age: [...c.querySelectorAll('time.age')].map((a) => ({datetime: a.getAttribute('datetime'), text: a.textContent.trim()})),
    pips: [...c.querySelectorAll('.pips')].map((p) => ({max: p.dataset.max === undefined ? null : p.dataset.max,
      filled: p.dataset.filled === undefined ? null : p.dataset.filled,
      pip: p.querySelectorAll('.pip').length, on: p.querySelectorAll('.pip.on').length}))};
})"""


def check_faces(tab, book, what, ref=None):
    """Every card of BOOK has the face the ADR gives it, the age measured to REF (the snapshot's by default)."""
    turns, ref = turns_of(book), ref or snapshot_ref(book)
    faces = {f["id"]: f for f in tab.page.evaluate(FACE_JS)}
    need(sorted(faces) == sorted(t["id"] for t in book["tickets"]), f"{what}: the cards are {sorted(faces)}")
    for t in book["tickets"]:
        bad = face_problems(faces[t["id"]], t, turns[t["id"]], book, ref)
        need(not bad, f"{what}, card {t['id']}: {bad[0] if bad else ''}", *bad)
    return faces


def l_face(browser, bases, golden, books):
    for scheme in ("light", "dark"):
        ctx = browser.new_context(color_scheme=scheme, viewport=DESKTOP)
        tab = Tab(ctx, bases["golden"])
        draw_kanban(tab, f"l ({scheme})")
        tab.page.wait_for_timeout(300)
        check_faces(tab, golden, f"l, the golden, {scheme}")
        tab.audit(f"l, the golden, {scheme}")
        ctx.close()
    # A logbook with an astral feature, an accent, a priority and no time in state or pips on some tickets.
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["faces"])
    draw_kanban(tab, "l, faces")
    tab.page.wait_for_timeout(300)
    faces = check_faces(tab, books["faces"], "l, the derived logbook")
    need(faces["0003"]["age"] == [], "l: card 0003's last history entry is not its state, but it shows a time in state")
    need(faces["0007"]["pips"] == [], "l: card 0007 has no attempt, but it shows pips")
    tab.audit("l, the derived logbook")
    ctx.close()
    # The search wraps the match in <mark> inside the title, case ignored; a card the perimeter alone matched has none.
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    draw_kanban(tab, "l, search")
    k = Kanban(tab, golden)
    marked = plain = False
    for q in ("waitlist", "WAITLIST", "app/backend/geocoder/cache.py", "readme", "0009"):
        tab.page.fill("input#kanban-q", q)
        want = {t["id"] for t in golden["tickets"] if matches(t, q)}
        for _ in range(60):
            if set(shown(k.board())) == want:
                break
            tab.page.wait_for_timeout(50)
        need(set(shown(k.board())) == want, f"l, search {q!r}: the cards shown are {sorted(shown(k.board()))}, want {sorted(want)}")
        tab.page.wait_for_timeout(150)
        for f in tab.page.evaluate(FACE_JS):
            t = next(t for t in golden["tickets"] if t["id"] == f["id"])
            if f["id"] not in want:
                continue
            problem = mark_problems(f, t, q)
            need(problem is None, f"l, search {q!r}, card {f['id']}: {problem}")
            marked, plain = marked or bool(f["marks"]), plain or not f["marks"]
    need(marked and plain, "l: the searches never gave both a marked title and a card shown with no mark")
    tab.audit("l, search")
    ctx.close()


# --- m. the back of a card ----------------------------------------------------------------------

OPEN_JS = "() => { const d = document.querySelector('dialog#card-back'); return !!d && d.open; }"
CLOSED_JS = "() => { const d = document.querySelector('dialog#card-back'); return (!d || !d.open) && !document.querySelector('aside#drawer'); }"
BACK_JS = """(id) => {
  const d = document.querySelector('dialog#card-back');
  const txt = (n) => (n ? n.textContent.replace(/\\s+/g, ' ').trim() : null);
  const r = d ? d.getBoundingClientRect() : null;
  const board = document.querySelector('.board');
  const a = document.activeElement;
  return {exists: !!d, open: !!d && d.open, modal: !!d && d.matches(':modal'),
    drawers: document.querySelectorAll('aside#drawer').length,
    drawer: d && d.querySelector('aside#drawer') ? d.querySelector('aside#drawer').dataset.id : null,
    inside: !!d && d.contains(a),
    nows: d ? [...d.querySelectorAll('.nowbox .now')].map(txt) : [],
    acts: d ? [...d.querySelectorAll('.nowbox a.act')].map((x) => ({href: x.getAttribute('href'), primary: x.classList.contains('primary')})) : [],
    stage_lists: d ? d.querySelectorAll('ol.stages').length : 0,
    stages: d ? [...d.querySelectorAll('ol.stages li[data-band][data-mark]')].map((l) => ({band: l.dataset.band, mark: l.dataset.mark})) : [],
    phases: d ? [...d.querySelectorAll('ol.compact li[data-phase]')].map((l) => l.dataset.phase) : [],
    questions: d ? [...d.querySelectorAll('.question')].map(txt) : [],
    link: d ? d.querySelectorAll("a[href='#ticket/" + id + "']").length : 0,
    rect: r ? {w: r.width, h: r.height} : null, hash: location.hash, history: history.length,
    active: a ? {card: a.closest('.card[data-id]') ? a.closest('.card[data-id]').dataset.id : null, inBoard: !!(board && board.contains(a))} : null};
}"""
# The first card other than ID whose centre is on screen, and what is on top of that point.
INERT_JS = """(id) => {
  for (const c of document.querySelectorAll('.card[data-id]')) {
    if (c.dataset.id === id) continue;
    const b = c.getBoundingClientRect();
    const x = b.left + b.width / 2, y = b.top + b.height / 2;
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
    const top = document.elementFromPoint(x, y);
    const hit = top && top.closest('.card[data-id]');
    return {found: true, other: c.dataset.id, card: hit ? hit.dataset.id : null};
  }
  return {found: false};
}"""


def back_problems(info, ident, now_text, stages, phases, exp, question):
    """Why the open back INFO of ticket IDENT is not ADR 0068 §3's: its card's now line NOW_TEXT, the
    timeline's STAGES and PHASES, EXP the rule's now line, QUESTION the open question's text or None."""
    bad = []
    if not info["exists"] or not info["open"]:
        return ["dialog#card-back is not open"]
    if not info["modal"]:
        bad.append("the dialog is open but not modal (it was not opened with showModal())")
    if info["drawers"] != 1 or info["drawer"] != ident:
        bad.append(f"{info['drawers']} aside#drawer in the page, the one in the dialog is for {info['drawer']!r}, want exactly one for {ident}")
    if not info["inside"]:
        bad.append("the focus is not inside the dialog")
    if len(info["nows"]) != 1 or info["nows"][0] != now_text:
        bad.append(f"the back's .nowbox .now is {info['nows']}, the card's is {now_text!r}")
    if info["stage_lists"] != 1 or info["stages"] != stages:
        bad.append(f"the back's strip is {info['stages']}, the timeline's ol#stages is {stages}")
    if info["phases"] != phases:
        bad.append(f"the compact rows are {info['phases']}, the logbook's timeline order is {phases}")
    if exp["href"]:
        if len(info["acts"]) != 1 or not info["acts"][0]["primary"] or info["acts"][0]["href"] != exp["href"]:
            bad.append(f"the nowbox's actions are {info['acts']}, want exactly one a.act.primary to {exp['href']!r}")
    elif len(info["acts"]) > 1:
        bad.append(f"the nowbox has {len(info['acts'])} actions, want at most one")
    if question and not any(question in q for q in info["questions"]):
        bad.append(f"no .question holds {question!r}: {info['questions']}")
    if info["link"] < 1:
        bad.append(f"no a[href='#ticket/{ident}'] in the back")
    return bad


def closed_problems(info, ident):
    """Why the board after the back of IDENT was closed is wrong: still open, a drawer left, a card= in
    the hash, the focus not on the card."""
    bad = []
    if info["open"]:
        bad.append("the dialog is still open")
    if info["drawers"]:
        bad.append("an aside#drawer is still in the DOM")
    if "card=" in info["hash"]:
        bad.append(f"the hash {info['hash']!r} still has card=")
    if not info["active"] or info["active"]["card"] != ident:
        bad.append(f"the focus is on {info['active']}, want the card {ident}")
    return bad


def open_back(tab, ident, how="click"):
    page = tab.page
    if how == "click":
        page.locator(f".card[data-id='{ident}'] .title").first.click()
    else:
        page.focus(f".card[data-id='{ident}']")
        page.keyboard.press("Enter")
    tab.wait(OPEN_JS, None, f"m, {ident}: dialog#card-back never opened ({how})")
    page.wait_for_timeout(500)  # the back scales in; a box is measured once it has
    return page.evaluate(BACK_JS, ident)


def close_back(tab, ident, how):
    if how == "Escape":
        tab.page.keyboard.press("Escape")
    else:
        tab.page.mouse.click(5, 5)  # outside the box: the back is at most 720 px wide at 1440
    tab.wait(CLOSED_JS, None, f"m, {ident}: the back never closed ({how})")
    tab.page.wait_for_timeout(150)
    info = tab.page.evaluate(BACK_JS, ident)
    bad = closed_problems(info, ident)
    need(not bad, f"m, {ident}, closed by {how}: {bad[0] if bad else ''}", *bad)
    return info


def m_back(browser, bases, golden):
    ctx = browser.new_context(viewport=DESKTOP)
    tab, tl = Tab(ctx, bases["golden"]), Tab(ctx, bases["golden"])
    turns = turns_of(golden)
    stages_of = {}
    for t in golden["tickets"]:
        tl.page.goto("about:blank")
        tl.load(f"#ticket/{t['id']}")
        wait_for(tl, "ol#stages li", f"m, the timeline of {t['id']}")
        stages_of[t["id"]] = [{"band": s["band"], "mark": s["mark"]} for s in tl.page.evaluate(TIMELINE_JS)["stages"]]
    draw_kanban(tab, "m")
    tab.page.wait_for_timeout(300)
    closed = tab.page.evaluate(BACK_JS, "0009")
    need(not closed["open"] and closed["drawers"] == 0, f"m: with no card opened, the dialog is open={closed['open']} and {closed['drawers']} aside#drawer are in the DOM")
    sensitive = tab.page.evaluate(INERT_JS, "0009")
    need(sensitive["found"] and sensitive["card"] == sensitive["other"],
         f"m: with the back closed, the point on card {sensitive.get('other')} does not hit a card: the inert probe proves nothing: {sensitive}")
    for t in golden["tickets"]:
        ident, exp = t["id"], turns[t["id"]]
        now_text = one_now(tab, f".card[data-id='{ident}'] .now", f"m, card {ident}")["text"]
        phases = [row["phase"] for row in t["timeline"]]
        qs = t.get("questions") or []
        question = qs[-1]["question"] if t["state"] == "questions" and qs and not qs[-1].get("answer") else None
        info = open_back(tab, ident)
        bad = back_problems(info, ident, now_text, stages_of[ident], phases, exp, question)
        need(not bad, f"m, the back of {ident}: {bad[0] if bad else ''}", *bad)
        need(info["hash"] == View(card=ident).hash(), f"m, the back of {ident}: the hash is {info['hash']!r}, want {View(card=ident).hash()!r}")
        w = info["rect"]["w"]
        need(w <= 720 + 1, f"m, the back of {ident} is {w:.0f} px wide at 1440, at most 720")
        inert = tab.page.evaluate(INERT_JS, ident)
        need(inert["found"] and inert["card"] is None, f"m, the back of {ident}: a point on card {inert.get('other')} still hits a card ({inert}): the board is not inert")
        close_back(tab, ident, "Escape")
        tab.audit(f"m, {ident}")
    # Enter on the focused card opens it; a click on the backdrop closes it.
    nine = next(t for t in golden["tickets"] if t["id"] == "0009")
    now_nine = one_now(tab, ".card[data-id='0009'] .now", "m, card 0009")["text"]
    info = open_back(tab, "0009", "Enter")
    bad = back_problems(info, "0009", now_nine, stages_of["0009"], [r["phase"] for r in nine["timeline"]], turns["0009"], nine["questions"][-1]["question"])
    need(not bad, f"m, Enter on 0009: {bad[0] if bad else ''}", *bad)
    close_back(tab, "0009", "backdrop")
    # The focus stays in the back: Tab never reaches the board.
    open_back(tab, "0009")
    for n in range(12):
        tab.page.keyboard.press("Tab")
        now = tab.page.evaluate(BACK_JS, "0009")
        need(now["active"] and not now["active"]["inBoard"], f"m: Tab number {n + 1} moved the focus into the board behind the back: {now['active']}")
    tab.page.keyboard.press("Escape")
    tab.wait(CLOSED_JS, None, "m: the back never closed after Tab")
    tab.audit("m, the back at 1440")
    ctx.close()
    # The phone: the back is the screen.
    ctx = browser.new_context(viewport=PHONE)
    tab = Tab(ctx, bases["golden"])
    draw_kanban(tab, "m, 390x844")
    info = open_back(tab, "0009")
    r = info["rect"]
    need(r["w"] >= PHONE["width"] - 1 and r["h"] >= PHONE["height"] - 1,
         f"m: at 390x844 the back is {r['w']:.0f}x{r['h']:.0f}, want the whole viewport {PHONE['width']}x{PHONE['height']}")
    tab.audit("m, 390x844")
    ctx.close()


# --- n. Your turn only ---------------------------------------------------------------------------

def n_only_mine(browser, bases, golden):
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    k = Kanban(tab, golden)
    tab.load("#kanban")
    wait_for(tab, ".card[data-id]", "n")
    need(k.board()["only_mine"] == "false", f"n: button#only-mine has aria-pressed {k.board()['only_mine']!r} at the start, want 'false'")
    k.expect("n, the default view")
    h0 = k.board()["history"]
    b = k.only_mine(True, "Your turn only pressed")
    need(sorted(shown(b)) == sorted(YOUR_TURN_GOLDEN), f"n: pressed, the cards are {sorted(shown(b))}, want {sorted(YOUR_TURN_GOLDEN)}")
    need(b["hash"] == "#kanban?turn=you", f"n: pressed, the hash is {b['hash']!r}, want '#kanban?turn=you'")
    raw = b["hash"]
    # A page opened on that link shows the same, the button pressed.
    again = Tab(ctx, bases["golden"])
    again.load(raw)
    second = Kanban(again, golden)
    again.wait("() => { const b = document.querySelector('button#only-mine'); return !!b && b.getAttribute('aria-pressed') === 'true'; }", None,
               "n: a page opened on turn=you never showed button#only-mine pressed")
    for _ in range(40):
        if set(shown(second.board())) == set(YOUR_TURN_GOLDEN):
            break
        again.page.wait_for_timeout(50)
    need(sorted(shown(second.board())) == sorted(YOUR_TURN_GOLDEN), f"n: a page opened on {raw!r} shows {sorted(shown(second.board()))}")
    again.audit("n, the page opened on the link")
    # With the other keys, the order is q, feature, priority, turn, group, empty, collapsed, card.
    k.select("priority", "P0", "Your turn only and priority P0")
    k.select("group", "feature", "Your turn only, P0, grouped")
    k.select("empty", "hide", "Your turn only, P0, grouped, empties hidden")
    k.open_card("0009", "Your turn only, and a card open")
    need(k.board()["hash"] == "#kanban?priority=P0&turn=you&group=feature&empty=hide&card=0009",
         f"n: the combined hash is {k.board()['hash']!r}, want '#kanban?priority=P0&turn=you&group=feature&empty=hide&card=0009'")
    k.view.card = ""
    k.key("Escape", "Escape closes the back")
    k.select("empty", "", "empties shown")
    k.select("group", "", "ungrouped")
    k.select("priority", "", "priority cleared")
    b = k.only_mine(False, "Your turn only released")
    need(sorted(shown(b)) == sorted(t["id"] for t in golden["tickets"]), f"n: released, the cards are {sorted(shown(b))}, want every ticket")
    need("turn" not in b["hash"], f"n: released, the hash is still {b['hash']!r}")
    need(b["history"] == h0, f"n: the toggle added {b['history'] - h0} history entries; it must replaceState")
    tab.audit("n, the whole sequence")
    ctx.close()


# --- o. the flight and the announcement ---------------------------------------------------------

RECORD_ANIMATE = """(() => { window.__animated = []; const orig = Element.prototype.animate;
  Element.prototype.animate = function (...args) { window.__animated.push({id: this.dataset ? this.dataset.id : null}); return orig.apply(this, args); }; })();"""
MOVED_JS = """(id) => {
  const c = document.querySelector(".card[data-id='" + id + "']");
  const col = c ? c.closest('.col[data-state]') : null;
  const a = document.getElementById('announce');
  return {moved: !!c && c.classList.contains('moved'), from: c && c.dataset.from !== undefined ? c.dataset.from : null,
    col: col ? col.dataset.state : null, live: a ? a.getAttribute('aria-live') : null,
    announce: a ? a.textContent.replace(/\\s+/g, ' ').trim() : null,
    animated: (window.__animated || []).filter((x) => x.id === id).length};
}"""


def moved_logbook(golden):
    """The golden with one card moved by the tower: MOVED_ID from MOVED_FROM to MOVED_TO."""
    book = json.loads(json.dumps(golden))
    next(t for t in book["tickets"] if t["id"] == MOVED_ID)["state"] = MOVED_TO
    for col in book["kanban"]:
        if MOVED_ID in col["tickets"]:
            col["tickets"].remove(MOVED_ID)
        if col["state"] == MOVED_TO:
            col["tickets"].append(MOVED_ID)
    return book


def flight_problems(info, reduced):
    """Why the board after the move is wrong: the card is not marked, from the old state, in the new
    column; the region is not polite or does not say the move; it animated (or not) against REDUCED."""
    bad = []
    if not info["moved"]:
        bad.append(f"card {MOVED_ID} is not .moved")
    if info["from"] != MOVED_FROM:
        bad.append(f"data-from is {info['from']!r}, want {MOVED_FROM!r}")
    if info["col"] != MOVED_TO:
        bad.append(f"the card sits in {info['col']!r}, want {MOVED_TO!r}")
    if info["live"] != "polite":
        bad.append(f"#announce has aria-live {info['live']!r}, want 'polite'")
    bad += announce_problems(info["announce"] or "")
    if reduced and info["animated"]:
        bad.append(f"with reduced motion the card ran {info['animated']} animation(s), want none")
    if not reduced and not info["animated"]:
        bad.append("without reduced motion the card ran no animation (Element.animate was never called on it)")
    return bad


def announce_problems(text):
    """The announcement names the id, the old state, then the new (ADR 0068 §4: "<id> moved from <old> to <new>")."""
    bad = []
    if MOVED_ID not in text or MOVED_FROM not in text or MOVED_TO not in text:
        bad.append(f"#announce says {text!r}, want {MOVED_ID}, {MOVED_FROM} and {MOVED_TO}")
    elif not text.find(MOVED_FROM) < text.find(MOVED_TO):
        bad.append(f"#announce says {text!r}: the old state {MOVED_FROM} does not come before the new {MOVED_TO}")
    return bad


def o_flight(browser, bases, golden):
    """A LIVE console, SIMULATED in the browser: page.route answers /v1/console.json with the real answer
    turned live (a mode and a read_at) and /v1/logbook.json with the golden, then with one card moved; the
    page polls every 2 s in live mode (ADR 0047 §4). The server is the snapshot server and is never asked."""
    real = json.loads(urllib.request.urlopen(bases["golden"] + "/v1/console.json", timeout=5).read())
    live = {**real, "mode": "live", "read_at": READ_AT}
    moved = moved_logbook(golden)
    # The recorder can see a call: a probe page that animates an element.
    ctx = browser.new_context()
    ctx.add_init_script(RECORD_ANIMATE)
    probe = ctx.new_page()
    probe.goto(bases["golden"] + "/v1/console.json")
    probe.evaluate("() => { const d = document.createElement('div'); d.dataset.id = 'probe'; document.body.append(d); d.animate([{opacity: 0}, {opacity: 1}], 10); }")
    need(probe.evaluate("window.__animated") == [{"id": "probe"}], f"o: the animation recorder did not see a call: {probe.evaluate('window.__animated')}")
    ctx.close()
    for reduced in (False, True):
        what = "o, reduced motion" if reduced else "o, motion"
        ctx = browser.new_context(viewport=DESKTOP, reduced_motion="reduce" if reduced else "no-preference")
        ctx.add_init_script(RECORD_ANIMATE)
        tab = Tab(ctx, bases["golden"])
        phase = {"moved": False}

        def console_route(route):
            route.fulfill(status=200, content_type="application/json", headers={"Cache-Control": "no-store"}, body=json.dumps(live))

        def logbook_route(route):
            route.fulfill(status=200, content_type="application/json",
                          headers={"Cache-Control": "no-store", "ETag": '"moved"' if phase["moved"] else '"golden"'},
                          body=json.dumps(moved if phase["moved"] else golden))

        tab.page.route("**/v1/console.json", console_route)
        tab.page.route("**/v1/logbook.json", logbook_route)
        draw_kanban(tab, what)
        tab.page.wait_for_timeout(600)
        need(tab.page.evaluate(MOVED_JS, MOVED_ID)["col"] == MOVED_FROM, f"{what}: card {MOVED_ID} did not start in {MOVED_FROM}")
        if not reduced:
            check_faces(tab, golden, f"{what}, ages in live mode", ref=READ_AT)
        phase["moved"] = True
        tab.wait("id => { const c = document.querySelector(\".card[data-id='\" + id + \"']\"); const a = document.getElementById('announce');"
                 " return !!c && c.classList.contains('moved') && !!a && a.textContent.trim() !== ''; }",
                 MOVED_ID, f"{what}: the moved card was never marked and announced within the polls", timeout=9000)
        tab.page.wait_for_timeout(100)
        info = tab.page.evaluate(MOVED_JS, MOVED_ID)
        bad = flight_problems(info, reduced)
        need(not bad, f"{what}: {bad[0] if bad else ''}", *bad)
        tab.audit(what)
        ctx.close()


# --- p. a long column -----------------------------------------------------------------------------

LONG_JS = """() => {
  const col = document.querySelector(".col[data-state='ci-failed']");
  const h3 = col ? col.querySelector('h3') : null;
  if (!col || !h3) return null;
  const before = {sh: col.scrollHeight, ch: col.clientHeight, overflow: getComputedStyle(col).overflowY};
  col.scrollTop = 400;
  const c = col.getBoundingClientRect(), h = h3.getBoundingClientRect();
  return {...before, top: col.scrollTop, gap: h.top - c.top, h3_top: h.top, vh: innerHeight, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth};
}"""


def long_problems(info):
    """Why the long column INFO does not scroll inside itself with its header in view."""
    if info is None:
        return ["there is no .col[data-state=ci-failed] with an h3"]
    bad = []
    if not info["sh"] > info["ch"]:
        bad.append(f"the column is not taller inside than out: scrollHeight {info['sh']}, clientHeight {info['ch']}")
    if info["overflow"] not in ("auto", "scroll"):
        bad.append(f"the column's overflow-y is {info['overflow']!r}, want auto or scroll")
    if not info["top"] > 0:
        bad.append(f"scrollTop stayed {info['top']} after being set to 400")
    if abs(info["gap"]) > 2:
        bad.append(f"after scrolling, the h3 is {info['gap']:.1f} px from the column's top, want within 2")
    if not 0 <= info["h3_top"] < info["vh"]:
        bad.append(f"after scrolling, the h3's top is at {info['h3_top']:.0f}, outside the {info['vh']} px viewport")
    if info["sw"] > info["cw"]:
        bad.append(f"the page scrolls sideways: {info['sw']} > {info['cw']}")
    return bad


def p_long(browser, bases):
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["long"])
    draw_kanban(tab, "p")
    tab.page.wait_for_timeout(300)
    info = tab.page.evaluate(LONG_JS)
    bad = long_problems(info)
    need(not bad, f"p, a column of 22 cards at 1440x900: {bad[0] if bad else ''}", *bad)
    tab.audit("p")
    ctx.close()


# --- q. contrast and focus ------------------------------------------------------------------------

def lum(rgb):
    """WCAG 2.1 relative luminance of an sRGB colour of three 0-255 channels."""
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def is_large(px, weight):
    """WCAG's large text: 24 px, or 18.66 px (14 pt) bold."""
    return px >= 24 or (px >= 18.66 and weight >= 700)


def contrast_problems(items, where):
    """Why the measured texts ITEMS (fg and bg composited to opaque, size, weight, a background-image flag) fail AA."""
    bad = []
    for it in items:
        label = f"{where}: {it['tag']}.{it['cls']} {it['text']!r}"
        if it["image"]:
            bad.append(f"{label} sits over a background-image; the ADR wants solid backgrounds")
            continue
        need_ = MIN_LARGE if is_large(it["px"], it["weight"]) else MIN_TEXT
        ratio = contrast(it["fg"], it["bg"])
        if ratio + 1e-9 < need_:
            bad.append(f"{label} has contrast {ratio:.2f}:1, want {need_}:1 ({it['px']}px, weight {it['weight']}, "
                       f"rgb{tuple(round(c) for c in it['fg'])} on rgb{tuple(round(c) for c in it['bg'])})")
    return bad


def focus_problems(info):
    """Why the outline of a focused card INFO is not a visible one at 3:1 against the column's background."""
    if info is None:
        return ["the Tab key never reached a .card"]
    bad = []
    if info["style"] == "none":
        bad.append("the focused card has outline-style none")
    if info["width"] < 2:
        bad.append(f"the focused card's outline is {info['width']}px wide, want at least 2px")
    ratio = contrast(info["color"], info["bg"])
    if ratio + 1e-9 < MIN_FOCUS:
        bad.append(f"the focused card's outline has contrast {ratio:.2f}:1 against its column, want {MIN_FOCUS}:1")
    return bad


# Colour helpers shared by the two measures: any CSS colour to [r, g, b, a] (a canvas reads those that are
# not rgb()), the first opaque background up the chain with the translucent ones composited over it.
COLOR_JS = """
const cv = document.createElement('canvas'); cv.width = cv.height = 1;
const g2 = cv.getContext('2d', {willReadFrequently: true});
const parse = (c) => {
  const m = /^rgba?\\(\\s*([\\d.]+)[\\s,]+([\\d.]+)[\\s,]+([\\d.]+)(?:\\s*[,/]\\s*([\\d.]+)(%?))?\\s*\\)$/.exec(c);
  if (m) { let a = m[4] === undefined ? 1 : parseFloat(m[4]); if (m[5]) a /= 100; return [+m[1], +m[2], +m[3], a]; }
  g2.clearRect(0, 0, 1, 1); g2.fillStyle = '#000'; g2.fillStyle = c; g2.fillRect(0, 0, 1, 1);
  const d = g2.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255];
};
const over = (f, b) => [0, 1, 2].map((i) => f[i] * f[3] + b[i] * (1 - f[3]));
const bgOf = (el) => {
  const layers = []; let image = false;
  for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    const s = getComputedStyle(n);
    if (s.backgroundImage !== 'none') image = true;
    const c = parse(s.backgroundColor);
    if (c[3] > 0) layers.push(c);
    if (c[3] >= 1) break;
  }
  let base = [255, 255, 255];
  if (layers.length && layers[layers.length - 1][3] >= 1) base = layers.pop().slice(0, 3);
  for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base);
  return {rgb: base, image};
};
"""
MEASURE_JS = "(sel) => {" + COLOR_JS + """
  const root = document.querySelector(sel);
  if (!root) return null;
  const out = [];
  for (const el of [root, ...root.querySelectorAll('*')]) {
    if (!['SCRIPT', 'STYLE'].includes(el.tagName) && ![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim() !== '')) continue;
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || s.visibility !== 'visible') continue;
    if (r.width < 2 && r.height < 2) continue;  // a visually hidden label
    if (el.closest('button:disabled, input:disabled, select:disabled, textarea:disabled, fieldset:disabled')) continue;
    let opacity = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) opacity *= parseFloat(getComputedStyle(n).opacity);
    const bg = bgOf(el), fg = parse(s.color);
    out.push({tag: el.tagName.toLowerCase(), cls: String(el.getAttribute('class') || ''),
      text: [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(' ').slice(0, 40),
      fg: over([fg[0], fg[1], fg[2], fg[3] * opacity], bg.rgb), bg: bg.rgb, image: bg.image,
      px: parseFloat(s.fontSize), weight: parseInt(s.fontWeight, 10) || 400});
  }
  return out;
}"""
FOCUS_JS = "() => {" + COLOR_JS + """
  const a = document.activeElement;
  const card = a && a.closest ? a.closest('.card[data-id]') : null;
  if (!card || a !== card) return null;
  const s = getComputedStyle(card), col = card.closest('.col') || card.parentElement;
  const bg = bgOf(col).rgb, c = parse(s.outlineColor);
  return {id: card.dataset.id, style: s.outlineStyle, width: parseFloat(s.outlineWidth), color: over(c, bg), bg};
}"""


def q_contrast(browser, bases):
    for scheme in ("light", "dark"):
        ctx = browser.new_context(color_scheme=scheme, viewport=DESKTOP)
        tab = Tab(ctx, bases["golden"])
        draw_kanban(tab, f"q ({scheme})")
        tab.page.wait_for_timeout(500)
        items = tab.page.evaluate(MEASURE_JS, ".board")
        need(items and len(items) >= 20, f"q ({scheme}): the walker found {len(items or [])} texts in .board, want a board's worth")
        bad = contrast_problems(items, f"q ({scheme}), the board")
        need(not bad, bad[0] if bad else "", *bad[:20])
        # The keyboard reaches a card, and the card says so.
        tab.page.focus("#kanban-q")
        info = None
        for _ in range(40):
            tab.page.keyboard.press("Tab")
            info = tab.page.evaluate(FOCUS_JS)
            if info:
                break
        bad = focus_problems(info)
        need(not bad, f"q ({scheme}): {bad[0] if bad else ''}", *bad)
        # The open back.
        open_back(tab, "0009")
        items = tab.page.evaluate(MEASURE_JS, "dialog#card-back")
        need(items and len(items) >= 10, f"q ({scheme}): the walker found {len(items or [])} texts in the back, want the back's worth")
        bad = contrast_problems(items, f"q ({scheme}), the back of 0009")
        need(not bad, bad[0] if bad else "", *bad[:20])
        tab.audit(f"q ({scheme})")
        ctx.close()


# --- r. the phone's band bar --------------------------------------------------------------------

BAND_TOP_JS = "(b) => { const e = document.querySelector(\".band[data-band='\" + b + \"']\"); return e ? e.getBoundingClientRect().top : null; }"


def r_bands(browser, bases, golden):
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    draw_kanban(tab, "r, 1440")
    shown_bar = tab.page.evaluate("() => [...document.querySelectorAll('.band-jump')].some((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })")
    need(not shown_bar, "r: the band bar is drawn at 1440, it belongs below 720 px")
    ctx.close()
    ctx = browser.new_context(viewport=PHONE)
    tab = Tab(ctx, bases["golden"])
    draw_kanban(tab, "r, 390x844")
    tab.page.wait_for_timeout(300)
    want = sorted({BAND_OF.get(t["state"], "other") for t in golden["tickets"]})
    got = tab.page.evaluate("() => [...document.querySelectorAll('.band-jump button[data-band]')].map((b) => b.dataset.band)")
    need(sorted(got) == want and len(got) == len(set(got)), f"r: the band bar has {got}, want one button for each band that holds a card: {want}")
    tab.page.evaluate("() => window.scrollTo(0, 0)")
    before = tab.page.evaluate(BAND_TOP_JS, "release")
    need(before is not None and before >= PHONE["height"], f"r: the Release band is at {before} before the click, already in the viewport: the jump proves nothing")
    hash0, hist0 = tab.page.evaluate("[location.hash, history.length]")
    tab.page.click(".band-jump button[data-band='release']")
    top, last = None, None
    for _ in range(40):  # smooth scrolling: until two reads agree
        tab.page.wait_for_timeout(100)
        top = tab.page.evaluate(BAND_TOP_JS, "release")
        if top == last:
            break
        last = top
    need(top is not None and 0 <= top < PHONE["height"], f"r: after the click the Release band's top is at {top}, want inside [0, {PHONE['height']})")
    hash1, hist1 = tab.page.evaluate("[location.hash, history.length]")
    need((hash1, hist1) == (hash0, hist0), f"r: the jump changed the hash {hash0!r} -> {hash1!r} or the history {hist0} -> {hist1}")
    tab.audit("r")
    ctx.close()


# --- s. no drag -----------------------------------------------------------------------------------

RECORD_EVENTS = """(() => { window.__events = []; const orig = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type, ...rest) { window.__events.push(String(type)); return orig.call(this, type, ...rest); }; })();"""


def drag_problems(events, draggable):
    """Why a session's registered event types and its [draggable=true] count mean a card can be dragged."""
    bad = [f"a listener for {t!r} was registered" for t in sorted(set(events)) if t == "drop" or t.startswith("drag")]
    if draggable:
        bad.append(f"{draggable} element(s) are draggable=true")
    return bad


def s_nodrag(browser, bases):
    ctx = browser.new_context(viewport=DESKTOP)
    ctx.add_init_script(RECORD_EVENTS)
    probe = ctx.new_page()
    probe.goto(bases["golden"] + "/v1/console.json")
    probe.evaluate("() => { document.addEventListener('dragstart', () => {}); document.addEventListener('drop', () => {}); }")
    seen = probe.evaluate("window.__events")
    need("dragstart" in seen and "drop" in seen, f"s: the listener recorder did not see a dragstart and a drop registered: {seen}")
    need(drag_problems(seen, 0), "s: a session that registered dragstart and drop is accepted")
    tab = Tab(ctx, bases["golden"])
    draw_kanban(tab, "s")
    tab.page.wait_for_timeout(300)
    open_back(tab, "0009")
    tab.page.keyboard.press("Escape")
    tab.wait(CLOSED_JS, None, "s: the back never closed")
    tab.page.click("button#only-mine")
    tab.page.wait_for_timeout(200)
    tab.page.click("button#only-mine")
    tab.page.wait_for_timeout(200)
    events = tab.page.evaluate("window.__events")
    need(len(events) > 5, f"s: the recorder saw {len(events)} registrations in a whole session: it is not recording")
    bad = drag_problems(events, tab.page.evaluate("document.querySelectorAll('[draggable=true]').length"))
    need(not bad, f"s: {bad[0] if bad else ''}", *bad)
    tab.audit("s")
    ctx.close()


def t_agents(browser, bases, golden):
    """ADR 0073 §10: the Thresholds screen's Agents panel prints the logbook's lines verbatim, the same text `./go agents` prints."""
    lines = (golden.get("agents") or {}).get("lines")
    need(isinstance(lines, list) and lines, f"agents: the golden has no agents lines: {json.dumps(golden.get('agents'))[:200]}")
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    tab.load("#thresholds")
    tab.page.wait_for_selector("h2:text-is('Agents')", timeout=5000)
    shown_text = tab.page.evaluate("() => { const h = [...document.querySelectorAll('h2')].find((x) => x.textContent === 'Agents'); const pre = h && h.nextElementSibling && h.nextElementSibling.querySelector('pre'); return pre ? pre.textContent : null; }")
    need(shown_text == "\n".join(lines), f"agents: the Agents panel shows {shown_text!r}, the logbook's lines are {lines!r}")
    # The ticket's back shows the review's instructions and run.json's mcp.calls; nothing when null.
    both = [t for t in golden["tickets"] if len(expected_agent_rows(t)) == 2]
    need(both, "agents: no golden ticket has both a task's mcp and a review's instructions: the back's check proves nothing")
    draw_kanban(tab, "agents")
    for t in golden["tickets"]:
        open_back(tab, t["id"])
        got = tab.page.evaluate(BACK_ROWS_JS)
        want = expected_agent_rows(t)
        seen = {k: v for k, v in got.items() if k in AGENT_ROWS}
        need(seen == want, f"agents, the back of {t['id']}: its agent rows are {seen}, want {want}")
        close_back(tab, t["id"], "Escape")
    ctx.close()


AGENT_ROWS = ("MCP", "Reviewer instructions")
BACK_ROWS_JS = """() => Object.fromEntries([...document.querySelectorAll('dialog#card-back aside#drawer dl > dt')]
  .map((dt) => [dt.textContent.trim(), dt.nextElementSibling ? dt.nextElementSibling.textContent.replace(/\\s+/g, ' ').trim() : null]))"""


def expected_agent_rows(t):
    """ADR 0073 §10, the back's rows from ticket T: `MCP` lists the dev-worker's calls as
    `server.tool ×count`, and `Reviewer instructions` names the file, its sha256's first 12 hex and
    the base's first 7; a null `mcp` or `instructions` gives no row."""
    out = {}
    mcp = (t.get("task") or {}).get("mcp")
    if mcp:
        out["MCP"] = ", ".join(f"{c['server']}.{c['tool']} ×{c['count']}" for c in mcp.get("calls") or []) or "declared, no calls"
    ins = (t.get("review") or {}).get("instructions")
    if ins:
        out["Reviewer instructions"] = f"{ins['file']} (sha256 {ins['sha256'][:12]}, from base {ins['base'][:7]})"
    return out


# --- ADR 0071: the governed network, on screen and in text ---------------------------------
# Written from docs/adr/0071 (§2 the DOM contract, §3 live and replay, §5 the words, §6
# degradation, §8 proof) and the interface contract fixed with it, never from
# console/index.html or core/network.py. Every expectation is computed from the golden's own
# fields at run time (the logbook 1.3 shape is in the ADR §1), and the CLI's view is the one
# `python3 core/network.py --logbook <file> --ticket <id>` prints.

GOLDEN_12 = ROOT / "fixtures" / "logbook" / "golden-1.2.json"
NETWORK_TICKET = "0010"
REPLAY_LABEL = "Replay of the recorded logbook: nothing is running"
BEAT_MS = 2000  # ADR 0071 §3: one timeline row per 2 s (provenance there: one live poll, a decision)
MARK_MS = 4000  # ADR 0059 §1 / 0071 §3: the live mark lasts 4 s
CLOCK_T0 = 1_800_000_000_000  # a fixed epoch, in ms, for page.clock
TRUNCATED_BYTES = 70000  # over the cap of 65,536 (contract-0071: PATCH_CAP); only "larger than the text" matters to the probe
SHORT = {"true": True, "false": False}


def makefile_gates():
    """The Makefile's `GATES :=` list, in order."""
    found = re.search(r"^GATES\s*:=\s*(.*)$", (ROOT / "Makefile").read_text(encoding="utf-8"), re.M)
    need(found and found.group(1).split(), "the Makefile has no `GATES :=` line")
    return found.group(1).split()


def roles_dirs():
    return sorted(p.name for p in (ROOT / "roles").iterdir() if p.is_dir())


def version_of(book):
    """'1.3' of 'lights-out/logbook/1.3'."""
    return book["schema"].rsplit("/", 1)[1]


def default_ticket(book):
    """The ticket with the newest updated_at (null last), ties to the highest id (ADR 0071 §2)."""
    return max(book["tickets"], key=lambda t: (t.get("updated_at") is not None, t.get("updated_at") or "", t["id"]))["id"]


def attempts_of(t):
    got = {x["attempt"] for x in t.get("tasks") or [] if x.get("attempt") is not None}
    got |= {r["attempt"] for r in t.get("rework") or [] if r.get("attempt") is not None}
    if t.get("attempt") is not None:
        got.add(t["attempt"])
    return sorted(got)


def gates_of(t, n, latest):
    """The gates of attempt N (contract-0071): the rework entry of that attempt, else the ticket's ci when N is
    the latest attempt, else none."""
    for r in t.get("rework") or []:
        if r.get("attempt") == n:
            return r.get("gates")
    if n == latest and t.get("ci"):
        return t["ci"].get("gates")
    return None


def task_of(t, n, latest):
    for x in t.get("tasks") or []:
        if x.get("attempt") == n:
            return x
    return t.get("task") if n == latest else None


def release_of(book, t):
    version = (t.get("release") or {}).get("version")
    return next((r for r in book.get("releases") or [] if version and r.get("version") == version), None)


def stage_verdict(raw):
    return "NO-GO" if str(raw).startswith("NO-GO") else "GO"


def gates_of_pairs(rows, table_gates):
    ran = {r["gate"] for r in rows}
    return [(r["gate"], r["verdict"]) for r in rows] + [(g, "not-run") for g in table_gates if g not in ran]


def expect_net(book, tid, attempt, table_gates, roles):
    """What section#net must say for ticket TID at ATTEMPT (None: the latest), from the record alone."""
    t = next(x for x in book["tickets"] if x["id"] == tid)
    atts = attempts_of(t)
    latest = atts[-1] if atts else None
    n = attempt if attempt is not None else latest
    rows = [r for r in (gates_of(t, n, latest) or []) if r.get("gate")]
    gate_pairs = gates_of_pairs(rows, table_gates)
    # A judge recorded with no gate lines (before 1.3 recorded them): one
    # summary edge with its verdict, as for a 1.2 logbook (docs/adr/0071 §6);
    # eight `not-run` edges would draw history the record does not hold. A
    # rework entry the reviewer or main's check wrote followed a gates GO.
    back = next((r for r in t.get("rework") or [] if r.get("attempt") == n), None)
    judge = back if back is not None else (t.get("ci") if n == latest and isinstance(t.get("ci"), dict) else None)
    if judge is not None and judge.get("gates") is None:
        v = ("GO" if back.get("judge") != "gates" else "NO-GO") if back is not None else judge.get("verdict")
        gate_pairs = [("gates", v if v in ("GO", "NO-GO") else "not-run")]
    named = {x.get("role") for x in t.get("tasks") or []} | {(t.get("task") or {}).get("role"), (t.get("review") or {}).get("role")}
    if (t.get("product") or {}).get("consulted"):
        named.add("product")
    task = task_of(t, n, latest)
    if task is None:
        workers = None
    elif task.get("members"):
        workers = [{"worker": m["id"], "harness": m.get("harness") or "", "model": m.get("model") or "", "replayed": m.get("replayed"),
                    "hand": m.get("hand_written") is True} for m in task["members"]]
    else:
        workers = [{"worker": None, "harness": task.get("harness") or "", "model": task.get("model") or "", "replayed": task.get("replayed"), "hand": False}]
    top = next((x["value"] for x in book.get("thresholds") or [] if x.get("key") == "REWORK_MAX_ATTEMPTS"), None)
    rel = release_of(book, t)
    answer = (rel or {}).get("answer")
    if answer:
        human = {"verdict": answer["answer"], "contains": [answer["by"], answer["via"]]}
    elif rel and rel.get("verdict") == "held":
        human = {"verdict": "waiting", "contains": []}
    else:
        human = {"verdict": "not-reached", "contains": []}
    stream = []
    for a in reversed(atts):
        task_a = task_of(t, a, latest) or {}
        patch = task_a.get("patch")
        if isinstance(patch, dict) and "text" in patch:
            shown_patch = ("text", patch["text"], bool(patch.get("truncated")))
        elif isinstance(patch, dict) and patch.get("ok") is False:
            shown_patch = ("withheld", patch["error"])
        else:
            shown_patch = None
        stream.append({"attempt": str(a), "open": a == n, "patch": shown_patch, "members": [m["id"] for m in task_a.get("members") or []],
                       "lines": [(r["gate"], r["verdict"], r["line"]) for r in (gates_of(t, a, latest) or []) if r.get("gate")]})
    return {"ticket": tid, "version": version_of(book), "attempt": n, "roles": sorted(roles), "ran": {r: r in named for r in roles},
            "workers": workers, "gates": gate_pairs, "gate_attempt": "" if n is None else str(n),
            # The graph lights the attempt shown (docs/adr/0071 §2, `attempt`):
            # the record's review belongs to the latest; an earlier attempt was
            # sent back by the reviewer, or never reached it.
            "review": "changes-requested" if any(r.get("attempt") == n and r.get("judge") == "review" for r in t.get("rework") or [])
                      else ((t.get("review") or {}).get("verdict") if n == latest else "not-reached"),
            "rework": {"count": str(len(t["rework"])), "max": None if top is None else str(top)} if t.get("rework") else None,
            "stages": [(str(s["pct"]), stage_verdict(s["verdict"])) for s in (rel or {}).get("stages") or []],
            "human": human, "stream": stream, "files": t.get("files"), "perimeter": t.get("perimeter")}


def expect_net_old(book, tid):
    """A 1.2 logbook (ADR 0071 §6): one summary edge, from the rework entry's line or ci.verdict; gates None when the record has neither."""
    t = next(x for x in book["tickets"] if x["id"] == tid)
    atts = attempts_of(t)
    latest = atts[-1] if atts else None
    entry = next((r for r in t.get("rework") or [] if r.get("attempt") == latest), None)
    if entry is not None:
        verdict = stage_verdict(entry.get("line") or "")
    elif t.get("ci"):
        verdict = t["ci"].get("verdict")
    else:
        return {"gates": None, "perimeter": t.get("perimeter")}
    return {"gates": [("gates", verdict)], "perimeter": t.get("perimeter")}


NET_JS = """() => {
  const s = document.querySelector('section#net');
  if (!s) return null;
  const norm = (x) => x.replace(/\\s+/g, ' ').trim();
  const a = (e, n) => (e ? e.getAttribute(n) : null);
  const q = (sel) => [...s.querySelectorAll(sel)];
  const out = (e) => !e.closest('#net-stream');
  const one = (sel) => document.querySelector(sel);
  const shown = (e) => !!e && !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
  const label = one('#net-replay-label');
  const rework = one('#net-rework'), human = one('#net-human'), review = one('#net-review');
  const sel = one('select#net-ticket');
  return {ticket: a(s, 'data-ticket'), schema: a(s, 'data-schema'), replay: a(s, 'data-replay'), row: a(s, 'data-row'),
    tower: !!one('#net-tower'),
    roles: q('.net-role').map((e) => ({role: a(e, 'data-role'), ran: a(e, 'data-ran')})),
    workers: q('.net-worker').filter(out).map((e) => ({worker: a(e, 'data-worker'), harness: a(e, 'data-harness'), model: a(e, 'data-model'),
      replayed: a(e, 'data-replayed'), hand: a(e, 'data-hand-written')})),
    gates: q('.net-gate').filter(out).map((e) => ({gate: a(e, 'data-gate'), verdict: a(e, 'data-verdict'), attempt: a(e, 'data-attempt')})),
    review: review ? a(review, 'data-verdict') : null,
    rework: rework ? {count: a(rework, 'data-count'), max: a(rework, 'data-max')} : null,
    stages: q('.net-stage').map((e) => ({pct: a(e, 'data-pct'), verdict: a(e, 'data-verdict')})),
    human: human ? {verdict: a(human, 'data-verdict'), text: norm(human.textContent)} : null,
    stream: q('ol#net-stream > li.net-attempt').map((li) => {
      const d = li.querySelector('details.net-patch'), pre = d ? d.querySelector('pre') : null;
      return {attempt: a(li, 'data-attempt'), text: norm(li.textContent),
        lines: [...li.querySelectorAll('li.net-line')].map((l) => ({gate: a(l, 'data-gate'), verdict: a(l, 'data-verdict'), text: l.textContent.trim()})),
        patch: d ? {truncated: a(d, 'data-truncated'), open: d.open, text: pre ? pre.textContent : null} : null};
    }),
    files: q('tr.net-file').map((r) => {
      const t = r.querySelector('.net-tests'), d = r.querySelector('.net-adrs');
      return {path: a(r, 'data-path'), glob: a(r, 'data-glob'), member: a(r, 'data-member'), held: a(r, 'data-held-by'),
        tests: t ? norm(t.textContent) : null, adrs: d ? [...d.querySelectorAll('a[href]')].map((x) => x.getAttribute('href')) : null};
    }),
    facts: q('.net-fact').map((e) => norm(e.textContent)),
    text: norm(s.textContent), stream_text: norm((one('#net-stream') || {textContent: ''}).textContent),
    label: label ? {visible: shown(label), text: norm(label.textContent)} : null,
    select: sel ? {value: sel.value, options: [...sel.options].map((o) => o.value)} : null};
}"""


def net_info(tab):
    return tab.page.evaluate(NET_JS)


def net_open(tab, hash_, what):
    """Load the screen at HASH and wait until it has drawn a ticket."""
    tab.page.goto("about:blank")
    tab.load(hash_)
    wait_for(tab, "section#net[data-ticket]", what)
    tab.page.wait_for_timeout(300)
    return net_info(tab)


def net_problems(info, exp):
    """Why the screen INFO (what NET_JS read) is not what EXP says (§2), or [] when it is."""
    if info is None:
        return ["there is no section#net"]
    bad = []

    def eq(what, got, want):
        if got != want:
            bad.append(f"{what} is {got!r}, want {want!r}")

    eq("section#net data-ticket", info["ticket"], exp["ticket"])
    if not (info["schema"] or "").endswith(exp["version"]):
        bad.append(f"section#net data-schema is {info['schema']!r}, want the logbook's {exp['version']}")
    if not info["tower"]:
        bad.append("there is no #net-tower")
    eq("the .net-role[data-role] nodes", sorted(r["role"] for r in info["roles"]), exp["roles"])
    eq("the roles' data-ran", {r["role"]: r["ran"] for r in info["roles"]}, {r: str(v).lower() for r, v in exp["ran"].items()})
    if exp["workers"] is not None:
        got = sorted(info["workers"], key=lambda w: w["worker"] or "")
        want = sorted(exp["workers"], key=lambda w: w["worker"] or "")
        if len(got) != len(want):
            bad.append(f"the graph draws {len(got)} .net-worker, the record has {len(want)}")
        for g, w in zip(got, want):
            if w["worker"] is not None:
                eq("a .net-worker's data-worker", g["worker"], w["worker"])
            eq(f"worker {w['worker']}: data-harness", g["harness"] or "", w["harness"])
            eq(f"worker {w['worker']}: data-model", g["model"] or "", w["model"])
            eq(f"worker {w['worker']}: data-hand-written", g["hand"] == "true", w["hand"])
            if w["replayed"] is not None:
                eq(f"worker {w['worker']}: data-replayed", SHORT.get(g["replayed"]), bool(w["replayed"]))
    eq("the .net-gate edges (gate, verdict) in order", [(g["gate"], g["verdict"]) for g in info["gates"]], exp["gates"])
    for g in info["gates"]:
        if g["attempt"] is None:
            bad.append(f"the edge {g['gate']} has no data-attempt")
        elif g["verdict"] != "not-run" and g["attempt"] != exp["gate_attempt"]:
            bad.append(f"the edge {g['gate']} says data-attempt {g['attempt']!r}, the attempt lit is {exp['gate_attempt']}")
    if exp["review"] is not None:
        eq("#net-review data-verdict", info["review"], exp["review"])
    eq("#net-rework (data-count, data-max), drawn only when the record has a rework",
       None if info["rework"] is None else (info["rework"]["count"], info["rework"]["max"]),
       None if exp["rework"] is None else (exp["rework"]["count"], exp["rework"]["max"]))
    eq("the .net-stage nodes (data-pct, data-verdict)", [(s["pct"], s["verdict"]) for s in info["stages"]], exp["stages"])
    if info["human"] is None:
        bad.append("there is no #net-human")
    else:
        eq("#net-human data-verdict", info["human"]["verdict"], exp["human"]["verdict"])
        for word in exp["human"]["contains"]:
            if word not in info["human"]["text"]:
                bad.append(f"#net-human says {info['human']['text']!r}, want it to name {word!r}")
    eq("the attempts of ol#net-stream, newest first", [s["attempt"] for s in info["stream"]], [s["attempt"] for s in exp["stream"]])
    for got, want in zip(info["stream"], exp["stream"]):
        n = want["attempt"]
        eq(f"attempt {n}: its li.net-line (gate, verdict, text)", [(x["gate"], x["verdict"], x["text"]) for x in got["lines"]], want["lines"])
        for member in want["members"]:
            if member not in got["text"]:
                bad.append(f"attempt {n}: the stream entry does not name its worker {member!r}")
        patch = got["patch"]
        if want["patch"] is not None:
            if patch is None:
                bad.append(f"attempt {n}: no details.net-patch")
            elif want["patch"][0] == "text":
                eq(f"attempt {n}: the patch text", patch["text"], want["patch"][1])
                eq(f"attempt {n}: data-truncated", patch["truncated"], str(want["patch"][2]).lower())
            elif want["patch"][1] not in (patch["text"] or ""):
                bad.append(f"attempt {n}: the withheld patch says {(patch['text'] or '')[:120]!r}, want the reason {want['patch'][1]!r}")
        if patch is not None:
            eq(f"attempt {n}: its details.net-patch open", patch["open"], want["open"])
    if exp["files"] is not None:
        rows = {f["path"]: f for f in info["files"]}
        eq("the tr.net-file paths", sorted(rows), sorted(f["path"] for f in exp["files"]))
        for f in exp["files"]:
            r = rows.get(f["path"])
            if r is None:
                continue
            eq(f"{f['path']}: data-glob", r["glob"] or "", f["glob"] or "")
            eq(f"{f['path']}: data-member", r["member"] or "", f["member"] or "")
            eq(f"{f['path']}: data-held-by", sorted(set(re.findall(r"[0-9A-Za-z-]+", r["held"] or ""))), sorted(f["held_by"] or []))
            if r["tests"] is None or r["adrs"] is None:
                bad.append(f"{f['path']}: the row has no .net-tests or no .net-adrs cell")
                continue
            for test in f["tests"] or []:
                if test not in r["tests"]:
                    bad.append(f"{f['path']}: .net-tests says {r['tests']!r}, want it to name {test}")
            if f["adrs"] is not None:
                eq(f"{f['path']}: the links of .net-adrs", sorted(r["adrs"]), sorted(f"#adr/{n}" for n in f["adrs"]))
    if not info["facts"]:
        bad.append("the screen has no .net-fact")
    return bad


def net_old_problems(info, exp, sentence):
    """§6: a 1.2 logbook draws the one summary edge, says it records no patches or gate lines (stream and files), shows the perimeter."""
    if info is None:
        return ["there is no section#net"]
    bad = []
    if exp["gates"] is not None:
        got = [(g["gate"], g["verdict"]) for g in info["gates"]]
        if got != exp["gates"]:
            bad.append(f"the .net-gate edges are {got}, a 1.2 logbook has the one {exp['gates']}")
    if sentence not in info["stream_text"]:
        bad.append(f"#net-stream does not say {sentence!r}: {info['stream_text'][:160]!r}")
    if info["text"].count(sentence) < 2:
        bad.append(f"the sentence {sentence!r} is said {info['text'].count(sentence)} time(s) in section#net, want the stream's and the files'")
    perimeter = exp["perimeter"]
    if isinstance(perimeter, dict) and perimeter.get("ok") is False:
        # An unread perimeter (a ticket with no `## Perimeter`): its reason is shown instead.
        if perimeter.get("error", "") not in info["text"]:
            bad.append(f"the perimeter could not be read, and the screen does not say why: {perimeter.get('error')!r}")
        perimeter = []
    for glob in perimeter or []:
        if glob not in info["text"]:
            bad.append(f"the perimeter {glob!r} is not shown")
    if any(s["lines"] for s in info["stream"]):
        bad.append("a 1.2 logbook has no gate lines, but the stream lists some")
    return bad


# --- the CLI's view: the facts are the lines that start with a space -----------------------

def cli_run(path, ticket=None, attempt=None):
    argv = [sys.executable, "core/network.py", "--logbook", str(path)]
    if ticket:
        argv += ["--ticket", ticket]
    if attempt:
        argv += ["--attempt", str(attempt)]
    done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
    need(done.returncode == 0, f"core/network.py {' '.join(argv[2:])} exited {done.returncode}", done.stderr.strip()[-300:])
    return done.stdout


def cli_facts(text):
    """The set of fact lines of a view: every line that starts with a space, stripped, whitespace collapsed; the patch
    block (between the two marker lines at column 0) holds no fact."""
    facts, inside = set(), False
    for line in text.splitlines():
        if re.match(r"--- patch of attempt \d+ ---$", line):
            inside = True
        elif line == "--- end of patch ---":
            inside = False
        elif not inside and line.startswith(" ") and line.strip():
            facts.add(" ".join(line.split()))
    return facts


def fact_problems(page, cli):
    """Why the .net-fact texts of the page are not the CLI's fact lines, or []."""
    page, cli = set(page), set(cli)
    bad = [f"the page says, the CLI does not: {x[:140]!r}" for x in sorted(page - cli)[:5]]
    bad += [f"the CLI says, the page does not: {x[:140]!r}" for x in sorted(cli - page)[:5]]
    if not cli:
        bad.append("the CLI printed no fact line (a line that starts with a space)")
    return bad


def net_hash(ticket="", attempt="", replay=False):
    """#network[/<id>][?attempt=<n>&replay=1]: keys in this order, defaults left out."""
    query = ([f"attempt={attempt}"] if attempt else []) + (["replay=1"] if replay else [])
    return "#network" + (f"/{ticket}" if ticket else "") + ("?" + "&".join(query) if query else "")


def net_hash_problems(raw, want):
    if raw == want:
        return None
    return f"location.hash is {raw!r}, want exactly {want!r} (keys in the order attempt, replay; defaults left out)"


def table_words(tab):
    """The page's #network-words, parsed, checked against what the CLI prints with --table."""
    raw = tab.page.evaluate("() => { const e = document.getElementById('network-words'); return e ? e.textContent : null; }")
    need(raw, "the page has no script#network-words")
    words = json.loads(raw)
    done = subprocess.run([sys.executable, "core/network.py", "--table"], cwd=ROOT, capture_output=True, text=True, check=False)
    need(done.returncode == 0, "core/network.py --table failed", done.stderr.strip()[-300:])
    need(json.loads(done.stdout) == words, "#network-words is not what core/network.py --table prints")
    need(words["roles"] == roles_dirs() and words["gates"] == makefile_gates(), f"the table's roles {words['roles']} and gates {words['gates']} are not roles/ and the Makefile's GATES")
    need("old_logbook" in words["words"] and "not_run" in words["words"], f"the table's words have {sorted(words['words'])}, want old_logbook and not_run")
    return words


# --- derived logbooks (as derive() does): over the cap, rejected at perimeter, early ---------------

def derive_net(golden, tmp):
    """Logbooks derived from the golden, written to TMP: trunc (ticket 0010's last patch is over the cap), perimeter (its last
    attempt was rejected at the perimeter gate, its patch withheld) and early (0010 is at attempt 1, ci-failed; 0009 is no longer
    the newest ticket), the live simulation's first answer."""
    trunc = json.loads(json.dumps(golden))
    t = next(x for x in trunc["tickets"] if x["id"] == NETWORK_TICKET)
    last = t["tasks"][-1]
    need(isinstance(last.get("patch"), dict) and "text" in last["patch"], f"the golden's ticket {NETWORK_TICKET} has no shown patch on its last attempt")
    last["patch"] = {**last["patch"], "bytes": TRUNCATED_BYTES, "truncated": True}
    if isinstance(t.get("task"), dict) and isinstance(t["task"].get("patch"), dict):
        t["task"]["patch"] = dict(last["patch"])
    perimeter = json.loads(json.dumps(golden))
    t = next(x for x in perimeter["tickets"] if x["id"] == NETWORK_TICKET)
    line = "NO-GO: perimeter — app/backend/other.py is outside the declared perimeter"
    t["ci"] = {**t["ci"], "verdict": "NO-GO", "failed": "perimeter", "line": line, "gates": [{"gate": "perimeter", "verdict": "NO-GO", "line": line}]}
    t["tasks"][-1]["patch"] = {"ok": False, "error": f"withheld: the secrets gate did not say GO on attempt {t['tasks'][-1]['attempt']}"}
    if isinstance(t.get("task"), dict) and "patch" in t["task"]:
        t["task"]["patch"] = dict(t["tasks"][-1]["patch"])
    early = json.loads(json.dumps(golden))
    t = next(x for x in early["tickets"] if x["id"] == NETWORK_TICKET)
    first = t["rework"][0]
    cut = t["history"][2]["at"]
    t["state"], t["attempt"] = "ci-failed", 1
    t["history"] = t["history"][:3]
    t["timeline"] = [r for r in t["timeline"] if r.get("at") is not None and r["at"] <= cut]
    t["tasks"] = t["tasks"][:1]
    t["task"] = {k: v for k, v in t["tasks"][0].items() if k != "attempt"}
    t["rework"], t["review"], t["merge"], t["release"], t["outcome"] = [], None, None, None, None
    t["ci"] = {**t["ci"], "verdict": "NO-GO", "failed": "mutation", "line": first["line"], "head_sha": first["head_sha"], "gates": first["gates"]}
    t["updated_at"] = cut
    t["files"] = [f for f in t["files"] if 1 in f["attempts"]]
    for f in t["files"]:
        f["attempts"] = [1]
    for col in early["kanban"]:
        if NETWORK_TICKET in col["tickets"]:
            col["tickets"].remove(NETWORK_TICKET)
        if col["state"] == "ci-failed":
            col["tickets"].append(NETWORK_TICKET)
    next(x for x in early["tickets"] if x["id"] == default_ticket(golden))["updated_at"] = "2026-11-02T00:00:00Z"
    paths = {}
    for name, book in (("net-trunc", trunc), ("net-perimeter", perimeter), ("net-early", early)):
        paths[name] = tmp / f"{name}.json"
        paths[name].write_text(json.dumps(book), encoding="utf-8")
    return {"trunc": trunc, "perimeter": perimeter, "early": early}, paths


# --- t. the route, the nav link, the default ticket, the select, the link reopened ----------------

def t_route(browser, bases, book):
    gates, roles = makefile_gates(), roles_dirs()
    ids = [x["id"] for x in book["tickets"]]
    default = default_ticket(book)
    need(default != NETWORK_TICKET, f"t: the golden's newest ticket is {NETWORK_TICKET}: the default ticket and an explicit one prove nothing apart")
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    tab.load("#overview")
    need(tab.page.locator("nav#nav a[data-s=network]").count() == 1, "t: nav#nav has no a[data-s=network] (exactly one)")
    tab.page.click("nav#nav a[data-s=network]")
    wait_for(tab, "section#net[data-ticket]", "t, the nav link")
    tab.page.wait_for_timeout(300)
    info = net_info(tab)
    problem = net_hash_problems(tab.page.evaluate("location.hash"), net_hash())
    need(problem is None, f"t, the nav link: {problem}")
    need(info["ticket"] == default, f"t: #network shows ticket {info['ticket']!r}, the newest updated_at (ties to the highest id) is {default}")
    need(info["select"] and info["select"]["value"] == default and sorted(info["select"]["options"]) == sorted(ids),
         f"t: select#net-ticket is {info['select']}, want {default} chosen among {sorted(ids)}")
    bad = net_problems(info, expect_net(book, default, None, gates, roles))
    need(not bad, f"t, the default ticket {default}: {bad[0] if bad else ''}", *bad)
    table_words(tab)
    # The select writes the link (ADR 0071 §2): a ticket that is not the default, then the link reopened in a new page.
    other = next(i for i in ids if i not in (default, NETWORK_TICKET))
    tab.page.select_option("select#net-ticket", other)
    tab.wait("id => { const s = document.querySelector('section#net'); return !!s && s.dataset.ticket === id; }", other, f"t: choosing {other} did not draw it")
    tab.page.wait_for_timeout(300)
    problem = net_hash_problems(tab.page.evaluate("location.hash"), net_hash(other))
    need(problem is None, f"t, the select: {problem}")
    first = net_info(tab)
    again = Tab(ctx, bases["golden"])
    second = net_open(again, net_hash(other), "t, the link reopened")
    need(first == second, f"t: the link {net_hash(other)} reopened in a new page draws another screen: {text_diff(json.dumps(first, indent=1), json.dumps(second, indent=1))}")
    again.audit("t, the link reopened")
    # An attempt in the link lights that attempt (0010's first was rejected at mutation).
    n1 = net_open(again, net_hash(NETWORK_TICKET, attempt=1), "t, ?attempt=1")
    problem = net_hash_problems(again.page.evaluate("location.hash"), net_hash(NETWORK_TICKET, attempt=1))
    need(problem is None, f"t, ?attempt=1: {problem}")
    exp1 = expect_net(book, NETWORK_TICKET, 1, gates, roles)
    need(("mutation", "NO-GO") in exp1["gates"] and ("test-proof", "not-run") in exp1["gates"],
         f"t: the golden's attempt 1 of {NETWORK_TICKET} is not a mutation NO-GO with test-proof not run: {exp1['gates']}")
    bad = net_problems(n1, exp1)
    need(not bad, f"t, {NETWORK_TICKET} at attempt 1: {bad[0] if bad else ''}", *bad)
    latest = net_open(again, net_hash(NETWORK_TICKET), "t, 0010 at its latest attempt")
    need([g["verdict"] for g in n1["gates"]] != [g["verdict"] for g in latest["gates"]], "t: ?attempt=1 lights the same gates as the latest attempt")
    again.page.reload()
    again.page.wait_for_selector("section#net[data-ticket]", timeout=TIMEOUT_MS)
    again.page.wait_for_timeout(300)
    need(net_info(again) == latest, "t: a reload draws another screen")
    again.audit("t, ?attempt=1")
    tab.audit("t")
    ctx.close()


# --- u. the contract of §2 for every golden ticket, the files, and the stream ------------------------

def u_contract(browser, bases, book):
    gates, roles = makefile_gates(), roles_dirs()
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    seen = {"gates": 0, "workers": 0, "rework": 0, "stages": 0, "human": set(), "patch": set(), "files": 0}
    for t in book["tickets"]:
        ident = t["id"]
        info = net_open(tab, net_hash(ident), f"u, {ident}")
        exp = expect_net(book, ident, None, gates, roles)
        bad = net_problems(info, exp)
        need(not bad, f"u, {ident}: {bad[0] if bad else ''}", *bad)
        seen["gates"] += sum(g["verdict"] != "not-run" for g in info["gates"])
        seen["workers"] += len(info["workers"])
        seen["rework"] += info["rework"] is not None
        seen["stages"] += len(info["stages"])
        seen["human"].add(info["human"]["verdict"])
        seen["patch"] |= {x["patch"][0] for x in exp["stream"] if x["patch"]}
        seen["files"] += len(info["files"])
        tab.audit(f"u, {ident}")
    # The golden must hold what the checks above need, or they prove nothing.
    need(seen["gates"] and seen["workers"] and seen["rework"] and seen["stages"] and seen["files"], f"u: the golden is too thin for the contract: {seen}")
    need({"GO", "not-reached"} <= seen["human"], f"u: the golden's human gates are {sorted(seen['human'])}, want GO and not-reached among them")
    need(seen["patch"] == {"text", "withheld"}, f"u: the golden's patches are {sorted(seen['patch'])}, want a shown one and a withheld one")
    # The ADR's network ticket, by name (§8): its members, rework, stages, human gate.
    info = net_open(tab, net_hash(NETWORK_TICKET), "u, the network ticket")
    need(sorted(w["worker"] for w in info["workers"]) == ["impl", "tests"], f"u: {NETWORK_TICKET} draws the workers {[w['worker'] for w in info['workers']]}, want impl and tests")
    byid = {w["worker"]: w for w in info["workers"]}
    need(byid["impl"]["model"] == "gemini-3.8-flash" and byid["impl"]["hand"] != "true" and not byid["tests"]["model"] and byid["tests"]["hand"] == "true",
         f"u: {NETWORK_TICKET}'s workers are {byid}: impl on gemini-3.8-flash, tests hand-written with no model")
    need(info["stages"] == [{"pct": "5", "verdict": "GO"}, {"pct": "25", "verdict": "GO"}], f"u: {NETWORK_TICKET}'s stages are {info['stages']}, want 5 and 25, GO")
    need(info["human"]["verdict"] == "GO" and "bob" in info["human"]["text"] and "cli" in info["human"]["text"],
         f"u: {NETWORK_TICKET}'s human gate is {info['human']}, want GO by bob through cli")
    need(info["rework"] is not None and info["rework"]["count"] == "1", f"u: {NETWORK_TICKET}'s rework is {info['rework']}, want count 1")
    need([g["verdict"] for g in info["gates"]] == ["GO"] * len(gates), f"u: {NETWORK_TICKET}'s latest attempt is {[g['verdict'] for g in info['gates']]}, want eight GO")
    need(info["review"] == "approved", f"u: {NETWORK_TICKET}'s review is {info['review']!r}, want approved")
    ran = {r["role"] for r in info["roles"] if r["ran"] == "true"}
    need({"dev-worker", "test-reviewer"} <= ran, f"u: {NETWORK_TICKET}'s roles that ran are {sorted(ran)}")
    rolled = net_open(tab, net_hash("0001"), "u, the rollback")
    need(rolled["stages"] == [{"pct": "5", "verdict": "NO-GO"}] and rolled["human"]["verdict"] == "not-reached",
         f"u: 0001's stages {rolled['stages']} and human gate {rolled['human']}: want 5% NO-GO and not-reached")
    inflight = net_open(tab, net_hash("0004"), "u, the attempt in flight")
    need(any(s["patch"] and "withheld" in (s["patch"]["text"] or "") for s in inflight["stream"]), f"u: 0004's attempt in flight does not show its patch as withheld: {inflight['stream']}")
    tab.audit("u")
    ctx.close()


# --- v. derived logbooks: a patch over the cap, an attempt rejected at perimeter ---------------------

def v_derived(browser, nbooks, npaths):
    gates, roles = makefile_gates(), roles_dirs()
    with Console(npaths["net-trunc"]) as c:
        ctx = browser.new_context(viewport=DESKTOP)
        tab = Tab(ctx, c.base)
        info = net_open(tab, net_hash(NETWORK_TICKET), "v, a patch over the cap")
        exp = expect_net(nbooks["trunc"], NETWORK_TICKET, None, gates, roles)
        need(exp["stream"][0]["patch"][2] is True, "v: the derived logbook's last patch is not truncated")
        bad = net_problems(info, exp)
        need(not bad, f"v, a patch over the cap: {bad[0] if bad else ''}", *bad)
        need(info["stream"][0]["patch"]["truncated"] == "true", f"v: the truncated patch says data-truncated={info['stream'][0]['patch']['truncated']!r}, want 'true'")
        need(info["stream"][-1]["patch"]["truncated"] == "false", "v: an untruncated patch says data-truncated other than 'false'")
        said = re.compile(r"truncat|cut off|cut at|70000|70,000", re.I)
        out = cli_run(npaths["net-trunc"], NETWORK_TICKET)
        need(any(said.search(f) for f in cli_facts(out)), "v: the CLI does not say, in a fact line, that the patch is truncated")
        need(any(said.search(f) for f in info["facts"]), "v: the screen does not say, in a .net-fact, that the patch is truncated")
        bad = fact_problems(info["facts"], cli_facts(out))
        need(not bad, f"v, a patch over the cap: the .net-fact set is not the CLI's: {bad[0] if bad else ''}", *bad)
        tab.audit("v, a patch over the cap")
        ctx.close()
    with Console(npaths["net-perimeter"]) as c:
        ctx = browser.new_context(viewport=DESKTOP)
        tab = Tab(ctx, c.base)
        info = net_open(tab, net_hash(NETWORK_TICKET), "v, rejected at perimeter")
        exp = expect_net(nbooks["perimeter"], NETWORK_TICKET, None, gates, roles)
        need(exp["gates"][0] == ("perimeter", "NO-GO") and len(exp["gates"]) == 1 + len(gates), f"v: the derived expectation is {exp['gates']}")
        bad = net_problems(info, exp)
        need(not bad, f"v, rejected at perimeter: {bad[0] if bad else ''}", *bad)
        need([g["verdict"] for g in info["gates"]].count("NO-GO") == 1 and info["gates"][0]["gate"] == "perimeter",
             f"v: an attempt rejected at perimeter draws {[(g['gate'], g['verdict']) for g in info['gates']]}, want one NO-GO edge, perimeter, first")
        need("withheld" in (info["stream"][0]["patch"]["text"] or ""), f"v: the rejected attempt's patch says {info['stream'][0]['patch']}, want the reason it is withheld")
        out = cli_run(npaths["net-perimeter"], NETWORK_TICKET)
        bad = fact_problems(info["facts"], cli_facts(out))
        need(not bad, f"v, rejected at perimeter: the .net-fact set is not the CLI's: {bad[0] if bad else ''}", *bad)
        tab.audit("v, rejected at perimeter")
        ctx.close()


# --- w. every .net-fact is a line of the CLI's view ---------------------------------------------------

def w_cli(browser, bases, book):
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    for t in book["tickets"]:
        info = net_open(tab, net_hash(t["id"]), f"w, {t['id']}")
        out = cli_run(GOLDEN, t["id"])
        first = out.splitlines()[0] if out else ""
        need(first.startswith(f"ticket {t['id']} — "), f"w: the CLI's first line for {t['id']} is {first!r}")
        bad = fact_problems(info["facts"], cli_facts(out))
        need(not bad, f"w, {t['id']}: the .net-fact set is not the CLI's fact lines: {bad[0] if bad else ''}", *bad)
        tab.audit(f"w, {t['id']}")
    # With no ticket the CLI and the screen choose the same one (the newest updated_at).
    info = net_open(tab, net_hash(), "w, the default ticket")
    out = cli_run(GOLDEN)
    first = out.splitlines()[0] if out else ""
    need(first.startswith(f"ticket {default_ticket(book)} — "), f"w: the CLI's default ticket is not {default_ticket(book)}: {first!r}")
    bad = fact_problems(info["facts"], cli_facts(out))
    need(not bad, f"w, the default ticket: {bad[0] if bad else ''}", *bad)
    ctx.close()


# --- x. the replay, on Playwright's clock -------------------------------------------------------------

def replay_problems(info, replay, row, static, final_count, last_count):
    """Why the screen INFO is not at ROW rows revealed with data-replay REPLAY: the label, the facts against the STATIC
    drawing's, the rework count against its final value and the one before it."""
    bad = []
    if info["replay"] != replay:
        bad.append(f"data-replay is {info['replay']!r}, want {replay!r}")
    if info["row"] != str(row):
        bad.append(f"data-row is {info['row']!r}, want {row}")
    label = info["label"]
    if not label or not label["visible"] or label["text"] != REPLAY_LABEL:
        bad.append(f"#net-replay-label is {label}, want it visible and reading {REPLAY_LABEL!r}")
    extra = set(info["facts"]) - set(static)
    if extra:
        bad.append(f"the replay shows a fact the static drawing does not hold: {sorted(extra)[0][:120]!r}")
    if replay == "done" and set(info["facts"]) != set(static):
        bad.append(f"the final frame lacks {sorted(set(static) - set(info['facts']))[:1]}: it must equal the static drawing")
    if replay == "on" and row == 0 and set(info["facts"]) == set(static):
        bad.append("at row 0 the replay already shows the whole drawing")
    count = int(info["rework"]["count"]) if info["rework"] else 0
    if count > final_count or count < last_count:
        bad.append(f"the rework count is {count} at row {row}: it counts the rows revealed so far (final {final_count}, previous {last_count})")
    if replay == "done" and count != final_count:
        bad.append(f"the final rework count is {count}, want {final_count}")
    return bad


def drive_replay(tab, rows, static, final_count, what):
    """Advance the paused clock one beat at a time: after 1999 ms nothing moved, after 2000 ms one more row; the last row is
    followed by data-replay=done (within one more beat); the label is visible throughout."""
    clock, last = tab.page.clock, 0
    for i in range(rows):
        info = net_info(tab)
        bad = replay_problems(info, "on", i, static, final_count, last)
        need(not bad, f"{what}, before beat {i + 1}: {bad[0] if bad else ''}", *bad)
        last = int(info["rework"]["count"]) if info["rework"] else 0
        clock.run_for(BEAT_MS - 1)
        tab.page.wait_for_timeout(30)
        early = net_info(tab)
        need(early["row"] == str(i), f"{what}: {BEAT_MS - 1} ms into beat {i + 1} data-row is {early['row']!r}, want {i}: the beat is {BEAT_MS} ms")
        clock.run_for(1)
        tab.page.wait_for_timeout(30)
    info = net_info(tab)
    if info["replay"] != "done":
        clock.run_for(BEAT_MS)
        tab.page.wait_for_timeout(30)
        info = net_info(tab)
    bad = replay_problems(info, "done", rows, static, final_count, last)
    need(not bad, f"{what}, after {rows} rows: {bad[0] if bad else ''}", *bad)
    return info


def x_replay(browser, bases, book):
    t = next(x for x in book["tickets"] if x["id"] == NETWORK_TICKET)
    rows = len(t["timeline"])
    final_count = len(t["rework"])
    need(rows >= 4, f"x: {NETWORK_TICKET}'s timeline has {rows} rows: the replay proves nothing")
    # The probe that makes 'no request was sent' mean something: a fetch a page makes is seen by the recorder.
    ctx = browser.new_context()
    seen = []
    probe = ctx.new_page()
    probe.on("request", lambda r: seen.append(r.url))
    probe.goto(bases["golden"] + "/v1/console.json")
    probe.evaluate("() => fetch('/v1/console.json').then(() => 0)")
    probe.wait_for_timeout(300)
    need(len(seen) >= 2, f"x: the request recorder saw {len(seen)} requests of a page that made two")
    ctx.close()
    # By the button.
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    tab.page.clock.install(time=CLOCK_T0 / 1000)  # Playwright for Python takes seconds
    info = net_open(tab, net_hash(NETWORK_TICKET), "x, the static drawing")
    static = info["facts"]
    need(info["replay"] == "off" and not (info["label"] and info["label"]["visible"]),
         f"x: before it is asked, the screen is data-replay={info['replay']!r} with the label {info['label']}: want off and no visible label")
    need(tab.page.locator("#net-replay").count() == 1, "x: there is no #net-replay button")
    tab.page.clock.pause_at((tab.page.evaluate("Date.now()") + 20) / 1000)
    requests = []
    tab.page.on("request", lambda r: requests.append(f"{r.method} {r.url}"))
    tab.page.click("#net-replay")
    tab.wait("() => { const s = document.querySelector('section#net'); return !!s && s.dataset.replay === 'on'; }", None, "x: #net-replay did not start the replay")
    tab.page.wait_for_timeout(50)
    raw = tab.page.evaluate("location.hash")
    need(net_hash_problems(raw, net_hash(NETWORK_TICKET)) is None or net_hash_problems(raw, net_hash(NETWORK_TICKET, replay=True)) is None,
         f"x: pressing the replay leaves the hash {raw!r}")
    final = drive_replay(tab, rows, static, final_count, "x, the button")
    need(final["label"]["visible"], "x: the replay label went away when the replay ended")
    need(not requests, f"x: the replay sent {len(requests)} request(s): {requests[:3]}")
    tab.audit("x, the button")
    ctx.close()
    # By the link.
    ctx = browser.new_context(viewport=DESKTOP)
    tab = Tab(ctx, bases["golden"])
    tab.page.clock.install(time=CLOCK_T0 / 1000)  # Playwright for Python takes seconds
    tab.page.goto("about:blank")
    # Paused before the load: the beat counts from the moment the page starts
    # the replay, which is then the clock's own, not a race with this script.
    tab.page.clock.pause_at((tab.page.evaluate("Date.now()") + 20) / 1000)
    tab.load(net_hash(NETWORK_TICKET, replay=True))
    wait_for(tab, "section#net[data-replay=on]", "x, ?replay=1 did not start the replay")
    start = net_info(tab)
    need(start["row"] == "0", f"x, ?replay=1: data-row is {start['row']!r} a moment after the load, want 0")
    drive_replay(tab, rows, static, final_count, "x, ?replay=1")
    tab.audit("x, ?replay=1")
    ctx.close()


# --- y. live, SIMULATED ---------------------------------------------------------------------------------

NET_ANIMATE = """(() => { window.__netAnimated = [];
  const note = (el) => { if (el && el.closest && el.closest('section#net')) window.__netAnimated.push(String(el.getAttribute('class') || el.tagName)); };
  const orig = Element.prototype.animate;
  Element.prototype.animate = function (...args) { note(this); return orig.apply(this, args); };
  for (const type of ['animationstart', 'transitionrun']) window.addEventListener(type, (e) => note(e.target), true); })();"""
NET_NEW_JS = "() => [...document.querySelectorAll('section#net .net-new')].length"
NET_ANNOUNCE_JS = """() => { const a = document.getElementById('announce');
  return {live: a ? a.getAttribute('aria-live') : null, text: a ? a.textContent.replace(/\\s+/g, ' ').trim() : null, animated: (window.__netAnimated || []).length}; }"""


def live_problems(marked, announce, reduced):
    """Why the screen after a new logbook is not marked, announced and (un)animated as §3 says."""
    bad = []
    if marked < 1:
        bad.append("no element of section#net carries the class net-new")
    if announce["live"] != "polite":
        bad.append(f"#announce has aria-live {announce['live']!r}, want 'polite'")
    if NETWORK_TICKET not in (announce["text"] or ""):
        bad.append(f"#announce says {announce['text']!r}, want it to name ticket {NETWORK_TICKET}")
    if reduced and announce["animated"]:
        bad.append(f"with reduced motion {announce['animated']} animation(s) ran in section#net, want none")
    if not reduced and not announce["animated"]:
        bad.append("without reduced motion nothing in section#net animated (no Element.animate, no CSS animation, no transition)")
    return bad


def y_live(browser, bases, golden, nbooks):
    """A LIVE console, SIMULATED in the browser: ctx.route answers /v1/console.json with the real answer turned live (a mode and a
    read_at) and /v1/logbook.json first with a logbook derived from the golden where ticket 0010 is at attempt 1, ci-failed, then
    with the golden. The snapshot server behind is never asked; the page polls every 2 s in live mode (ADR 0047 §4)."""
    real = json.loads(urllib.request.urlopen(bases["golden"] + "/v1/console.json", timeout=5).read())
    live = {**real, "mode": "live", "read_at": READ_AT}
    early, gates, roles = nbooks["early"], makefile_gates(), roles_dirs()
    need(default_ticket(early) != default_ticket(golden), "y: the early logbook and the golden have the same default ticket")
    for reduced in (False, True):
        what = "y, reduced motion" if reduced else "y, motion"
        ctx = browser.new_context(viewport=DESKTOP, reduced_motion="reduce" if reduced else "no-preference")
        ctx.add_init_script(NET_ANIMATE)
        phase = {"moved": False}
        ctx.route("**/v1/console.json", lambda route: route.fulfill(status=200, content_type="application/json", headers={"Cache-Control": "no-store"}, body=json.dumps(live)))
        ctx.route("**/v1/logbook.json", lambda route: route.fulfill(
            status=200, content_type="application/json", headers={"Cache-Control": "no-store", "ETag": '"golden"' if phase["moved"] else '"early"'},
            body=json.dumps(golden if phase["moved"] else early)))
        pinned = Tab(ctx, bases["golden"])
        net_open(pinned, net_hash(NETWORK_TICKET), f"{what}, the pinned ticket")
        following = Tab(ctx, bases["golden"])
        info = net_open(following, net_hash(), f"{what}, the default ticket")
        need(info["ticket"] == default_ticket(early), f"{what}: #network shows {info['ticket']!r}, the early logbook's default is {default_ticket(early)}")
        before = net_info(pinned)
        bad = net_problems(before, expect_net(early, NETWORK_TICKET, None, gates, roles))
        need(not bad, f"{what}, the early drawing of {NETWORK_TICKET}: {bad[0] if bad else ''}", *bad)
        n_new = pinned.page.evaluate(NET_NEW_JS)
        need(len(before["stream"]) == 1 and n_new == 0, f"{what}: before the move the stream has {len(before['stream'])} attempt(s) and {n_new} marked elements")
        pinned.page.evaluate("window.__netAnimated = []")
        phase["moved"] = True
        pinned.wait("() => document.querySelectorAll('section#net .net-new').length > 0", None,
                    f"{what}: nothing in section#net was ever marked net-new within the polls", timeout=9000)
        pinned.page.wait_for_timeout(100)
        marked = pinned.page.evaluate(NET_NEW_JS)
        pinned.wait("() => { const a = document.getElementById('announce'); return !!a && a.textContent.trim() !== ''; }", None, f"{what}: #announce said nothing", timeout=9000)
        bad = live_problems(marked, pinned.page.evaluate(NET_ANNOUNCE_JS), reduced)
        need(not bad, f"{what}: {bad[0] if bad else ''}", *bad)
        pinned.wait("() => document.querySelectorAll(\"ol#net-stream > li.net-attempt[data-attempt='2']\").length === 1", None,
                    f"{what}: the new attempt never joined the stream", timeout=9000)
        # With reduced motion the mark stays and only the motion goes (docs/adr/
        # 0071 §3, ADR 0059 §1's mark): it was drawn above, with no animation
        # (live_problems); like any mark it lasts MARK_MS.
        pinned.wait("() => document.querySelectorAll('section#net .net-new').length === 0", None,
                    f"{what}: the mark never went away (it lasts {MARK_MS} ms)", timeout=MARK_MS + 5000)
        bad = net_problems(net_info(pinned), expect_net(golden, NETWORK_TICKET, None, gates, roles))
        need(not bad, f"{what}, the drawing after the poll: {bad[0] if bad else ''}", *bad)
        following.wait("t => { const s = document.querySelector('section#net'); return !!s && s.dataset.ticket === t; }", default_ticket(golden),
                       f"{what}: the screen without an id did not follow the newest ticket to {default_ticket(golden)}", timeout=9000)
        sel = following.page.evaluate("document.querySelector('select#net-ticket').value")
        need(sel == default_ticket(golden), f"{what}: after following, select#net-ticket is {sel!r}, want {default_ticket(golden)}")
        pinned.audit(what)
        following.audit(what)
        ctx.close()


# --- z. the 1.2 degradation -------------------------------------------------------------------------------

def z_old(browser, book12):
    with Console(GOLDEN_12) as c:
        ctx = browser.new_context(viewport=DESKTOP)
        tab = Tab(ctx, c.base)
        info = net_open(tab, net_hash(), "z, a 1.2 logbook")
        words = table_words(tab)
        sentence = words["words"]["old_logbook"].format(version=version_of(book12))
        need("1.2" in sentence, f"z: the old_logbook sentence is {sentence!r}: it names no version")
        need(info["ticket"] == default_ticket(book12), f"z: #network over 1.2 shows {info['ticket']!r}, want {default_ticket(book12)}")
        checked = 0
        for t in book12["tickets"]:
            info = net_open(tab, net_hash(t["id"]), f"z, {t['id']}")
            exp = expect_net_old(book12, t["id"])
            bad = net_old_problems(info, exp, sentence)
            need(not bad, f"z, {t['id']}: {bad[0] if bad else ''}", *bad)
            if exp["gates"] is not None:
                need([g["gate"] for g in info["gates"]] == ["gates"], f"z, {t['id']}: the 1.2 edges are {[g['gate'] for g in info['gates']]}, want the one .net-gate[data-gate=gates]")
                checked += 1
            tab.audit(f"z, {t['id']}")
        need(checked >= 3, f"z: only {checked} 1.2 tickets have a ci or a rework line: the summary edge is hardly proved")
        ctx.close()
    with Console(GOLDEN) as c:
        ctx = browser.new_context(viewport=DESKTOP)
        tab = Tab(ctx, c.base)
        info = net_open(tab, net_hash(NETWORK_TICKET), "z, the 1.3 golden")
        need(sentence not in info["text"], f"z: the 1.3 golden says the 1.2 sentence {sentence!r}")
        ctx.close()


# --- s. (the network's part) no POST, no drag --------------------------------------------------------------

def net_nodrag(browser, bases):
    ctx = browser.new_context(viewport=DESKTOP)
    ctx.add_init_script(RECORD_EVENTS)
    tab = Tab(ctx, bases["golden"])
    net_open(tab, net_hash(NETWORK_TICKET), "s, the network")
    tab.page.click("#net-replay")
    tab.page.wait_for_timeout(300)
    tab.page.select_option("select#net-ticket", "0003")
    tab.page.wait_for_timeout(300)
    events = tab.page.evaluate("window.__events")
    need(len(events) > 5, f"s: the recorder saw {len(events)} registrations in a whole session on #network: it is not recording")
    bad = drag_problems(events, tab.page.evaluate("document.querySelectorAll('[draggable]').length"))
    need(not bad, f"s, #network: {bad[0] if bad else ''}", *bad)
    tab.audit("s, #network")
    ctx.close()


# --- q. (the network's part) contrast and focus -----------------------------------------------------------

# SVG text is painted with `fill`, not `color`: the walker reads the fill there.
NET_MEASURE_JS = MEASURE_JS.replace("fg = parse(s.color)", "fg = parse(el instanceof SVGElement && s.fill !== 'none' ? s.fill : s.color)")
NET_FOCUS_JS = "() => {" + COLOR_JS + """
  const a = document.activeElement;
  if (!a || a === document.body || !a.closest || !a.closest('main')) return null;
  const s = getComputedStyle(a), bg = bgOf(a).rgb, c = parse(s.outlineColor);
  return {tag: a.tagName.toLowerCase(), id: a.id, style: s.outlineStyle, width: parseFloat(s.outlineWidth), color: over(c, bg), bg};
}"""


def q_network(browser, bases):
    need(NET_MEASURE_JS != MEASURE_JS, "q: the network's walker reads the same colour as the board's: SVG text would be measured by `color`")
    for scheme in ("light", "dark"):
        ctx = browser.new_context(color_scheme=scheme, viewport=DESKTOP)
        tab = Tab(ctx, bases["golden"])
        net_open(tab, net_hash(NETWORK_TICKET), f"q ({scheme}), the network")
        items = tab.page.evaluate(NET_MEASURE_JS, "section#net")
        need(items and len(items) >= 30, f"q ({scheme}): the walker found {len(items or [])} texts in section#net, want a network's worth")
        bad = contrast_problems(items, f"q ({scheme}), #network")
        need(not bad, bad[0] if bad else "", *bad[:20])
        # Focus: every control the keyboard reaches in main has a 2 px outline at 3:1 (§6).
        tab.page.focus("select#net-ticket")
        stops = []
        for _ in range(60):
            info = tab.page.evaluate(NET_FOCUS_JS)
            if info:
                stops.append(info)
            tab.page.keyboard.press("Tab")
            if not tab.page.evaluate("() => !!document.activeElement && !!document.activeElement.closest && !!document.activeElement.closest('main')"):
                break
        need(len(stops) >= 3, f"q ({scheme}): the keyboard reached {len(stops)} controls in #network, want at least 3 (the ticket select, the replay button, a patch)")
        need(any(s["tag"] == "summary" for s in stops), f"q ({scheme}): the keyboard never reached a details.net-patch summary: {[s['tag'] for s in stops]}")
        for s in stops:
            bad = focus_problems(s)
            need(not bad, f"q ({scheme}): the focused {s['tag']}#{s['id']} on #network: {bad[0] if bad else ''}", *bad)
        # The label of the replay is text too.
        tab.page.click("#net-replay")
        tab.page.wait_for_timeout(100)
        items = tab.page.evaluate(NET_MEASURE_JS, "#net-replay-label")
        need(items, f"q ({scheme}): the replay label has no measurable text")
        bad = contrast_problems(items, f"q ({scheme}), the replay label")
        need(not bad, bad[0] if bad else "", *bad)
        tab.audit(f"q ({scheme}), #network")
        ctx.close()


# --- the checks that the checks themselves can fail ------------------------------------

def self_checks():
    agent = {"task": {"mcp": {"calls": [{"server": "notes", "tool": "search_notes", "count": 1}]}},
             "review": {"instructions": {"file": ".lights-out/roles/test-reviewer.md", "sha256": "abcdef1234567890", "base": "1a2b3c4d5e"}}}
    need(expected_agent_rows(agent) == {"MCP": "notes.search_notes ×1",
                                        "Reviewer instructions": ".lights-out/roles/test-reviewer.md (sha256 abcdef123456, from base 1a2b3c4)"},
         f"the back's agent rows are wrong: {expected_agent_rows(agent)}")
    need(expected_agent_rows({"task": {"mcp": None}, "review": {"instructions": None}}) == {}, "a null mcp or instructions gives a row")
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
    # ADR 0063: the rules and the comparisons of g-k, each shown to fail.
    book = json.loads(GOLDEN.read_text(encoding="utf-8"))
    turns = turns_of(book)
    need(sorted(i for i, e in turns.items() if e["turn"] == "you") == sorted(YOUR_TURN_GOLDEN), f"the now rules give {turns} over the golden")
    need(turns["0003"]["contains"] == ["dev-worker", "attempt 2 of 4"] and turns["0008"]["contains"] == ["dev-worker", "attempt 2 of 4"],
         f"the rework line's words are {turns['0003']['contains']}")
    need(turns["0009"]["contains"] == ["spec gate's"] and turns["0009"]["href"] == "#ticket/0009", f"the question's rule is {turns['0009']}")
    need(turns["0001"]["turn"] == "done" and turns["0002"]["turn"] == "done", "a rolled-back and a human-judged held ticket are not done")
    you = {"turn": "you", "text": "Your turn: the spec gate's question", "hrefs": ["#ticket/0009"]}
    need(now_problems(you, turns["0009"]) is None, "a good line for a question is refused")
    need(now_problems({**you, "turn": "tower"}, turns["0009"]), "a line with the wrong data-turn is accepted")
    need(now_problems({**you, "text": "The spec gate's question"}, turns["0009"]), "a you line without 'Your turn' is accepted")
    need(now_problems({**you, "turn": "tower", "text": "Your turn to wait"}, turns["0003"]), "a tower line that says 'Your turn' is accepted")
    need(now_problems({**you, "text": "Your turn: the product role's question"}, turns["0009"]), "a question line that names the wrong asker is accepted")
    need(now_problems({**you, "hrefs": []}, turns["0009"]), "a line without its action is accepted")
    held = json.loads(json.dumps(book))
    two = next(t for t in held["tickets"] if t["id"] == "0002")
    two["release"]["version"] = held["launch"]["record"]["version"]
    two["outcome"] = {"verdict": "GO", "judge": "verify", "line": "GO: launchpad — held at 25%"}
    need(expected_now(two, held["launch"], 4)["turn"] == "you" and expected_now(two, held["launch"], 4)["href"] == "#launch",
         "a held ticket of the record's version is not a person's turn")
    held["launch"]["record"]["promoted"] = True
    need(expected_now(two, held["launch"], 4)["turn"] != "you", "a held ticket whose record was answered is still a person's turn")
    five = next(t for t in book["tickets"] if t["id"] == "0005")
    need(expected_now({**five, "wait": {**five["wait"], "holders": ["0003"]}}, book["launch"], 4)["turn"] == "stopped", "a ticket with holders is not stopped")
    order = [c["state"] for c in book["kanban"]]
    cols = [{"state": s, "band": BAND_OF.get(s, "other"), "name": "x", "empty": s != "held", "collapsed": False,
             "cards": 0 if s != "held" else 1, "w": 40 if s != "held" else 300} for s in order]
    fit = {"doc": {"sw": 1400, "cw": 1400}, "board": {"sw": 1300, "cw": 1300}, "cols": cols}
    need(fit_problems(fit, order) == [], f"a board that fits is refused: {fit_problems(fit, order)}")
    for what, bad in (("a page that scrolls sideways", {**fit, "doc": {"sw": 1500, "cw": 1400}}),
                      ("a board that scrolls sideways", {**fit, "board": {"sw": 1500, "cw": 1300}}),
                      ("columns out of the logbook's order", {**fit, "cols": cols[::-1]}),
                      ("an empty column that is wide", {**fit, "cols": [{**cols[0], "w": 41}] + cols[1:]}),
                      ("an empty column that is collapsed", {**fit, "cols": [{**cols[0], "collapsed": True}] + cols[1:]}),
                      ("a column with cards that is not marked", {**fit, "cols": [{**cols[0], "empty": False}] + cols[1:]}),
                      ("a column outside every band", {**fit, "cols": [{**cols[0], "band": None}] + cols[1:]}),
                      ("a column in the wrong band", {**fit, "cols": [{**cols[0], "band": "release"}] + cols[1:]}),
                      ("a band with no name", {**fit, "cols": [{**cols[0], "name": ""}] + cols[1:]}),
                      ("a column with cards that is narrow", {**fit, "cols": [{**c, "w": 100} if c["state"] == "held" else c for c in cols]})):
        need(fit_problems(bad, order), f"fit: {what} is accepted")
    phone = {"doc": {"sw": 390, "cw": 390}, "lefts": [10, 10, 11], "nav_tops": [5] * 6}
    need(stack_problems(phone) == [], f"a phone board that stacks is refused: {stack_problems(phone)}")
    for what, bad in (("a page that scrolls sideways", {**phone, "doc": {"sw": 900, "cw": 390}}),
                      ("columns side by side", {**phone, "lefts": [10, 200, 400]}),
                      ("a nav of two lines", {**phone, "nav_tops": [5, 5, 5, 40, 40, 40]}),
                      ("a nav of no links", {**phone, "nav_tops": []})):
        need(stack_problems(bad), f"stack: {what} is accepted")
    box = {"top": 700, "left": 10, "bottom": 740, "right": 300, "h": 40}
    need(inside(box, 1440, 900) and not inside({**box, "top": 880, "bottom": 920}, 1440, 900) and not inside({**box, "h": 0}, 1440, 900)
         and not inside(None, 1440, 900) and not inside({**box, "right": 500}, 390, 844), "the viewport test does not tell inside from outside")
    self_checks_0068(book)
    self_checks_0071()


def self_checks_0068(book):
    """ADR 0068's rules and comparisons (l-s), each shown to fail on a wrong input."""
    # The view: `turn` sits between priority and group.
    v = View(q="a", feature="f", priority="P0", turn="you", group="feature", empty="hide", collapsed=["held"], card="0009")
    need(v.hash() == "#kanban?q=a&feature=f&priority=P0&turn=you&group=feature&empty=hide&collapsed=held&card=0009", f"the hash writer is wrong with turn: {v.hash()}")
    need(view_problems(v.hash(), v) is None, "a hash with turn is not accepted for its own view")
    need(view_problems("#kanban?turn=you&priority=P0", View(priority="P0", turn="you")), "turn before priority is accepted")
    need(view_problems("#kanban?group=feature&turn=you", View(group="feature", turn="you")), "turn after group is accepted")
    need(view_problems("#kanban", View(turn="you")), "a hash with no turn is accepted for a view with it")
    need(view_problems("#kanban?turn=you", View()), "a hash with turn is accepted for a view without it")
    need(matches({"id": "0009", "title": "x"}, turn="you", you=("0009",)) and not matches({"id": "0003", "title": "x"}, turn="you", you=("0009",)),
         "the turn filter does not tell a person's ticket from the tower's")
    need(matches({"id": "0003", "title": "x"}, turn="", you=("0009",)), "no turn filter still hides a ticket")
    # The actor table and the badge's rule.
    need(set(ACTOR_OF_STEP) == set(tower.PRECONDITION) and set(ACTOR_OF_STEP.values()) <= set(ACTORS), "the actor table of this suite is not core/tower.py's steps")
    by_id = {t["id"]: t for t in book["tickets"]}
    turns = turns_of(book)
    want = {"0001": "done", "0002": "done", "0003": "dev", "0004": "you", "0005": "you", "0007": "you", "0008": "dev", "0009": "you", "0010": "done"}
    need({i: actor_of(by_id[i], turns[i]) for i in by_id} == want, f"the badge rule gives {({i: actor_of(by_id[i], turns[i]) for i in by_id})}, want {want}")
    answered = {"id": "9", "state": "questions", "questions": [{"question": "q", "answer": "a"}]}
    need(actor_of(answered, {"turn": "tower"}) == "product", "an answered question is not the product role's turn")
    need(actor_of({"id": "9", "state": "pr-opened"}, {"turn": "tower"}) == "gates" and actor_of({"id": "9", "state": "merged"}, {"turn": "tower"}) == "tower"
         and actor_of({"id": "9", "state": "main-green"}, {"turn": "tower"}) == "canary" and actor_of({"id": "9", "state": "review"}, {"turn": "tower"}) == "reviewer"
         and actor_of({"id": "9", "state": "spec-ready"}, {"turn": "tower"}) == "spec" and actor_of({"id": "9", "state": "requested"}, {"turn": "tower"}) == "product",
         "the badge of a tower step is wrong")
    need(actor_of({"id": "9", "state": "held"}, {"turn": "tower"}) is None, "a state with no step has a badge")
    need(actor_of({"id": "9", "state": "assigned"}, {"turn": "stopped"}) == "stopped", "a stopped ticket's badge is not stopped")
    # The hue: UTF-16 code units, not code points.
    need(hue_of("abc") == 0 and hue_of("a") == 1 and hue_of("") == 0, "the hue of a plain name is wrong")
    need(hue_of("\U0001F600") == 1 and ord("\U0001F600") % 6 == 4, "the hue of an astral character is not its two code units' sum")
    # The age: the boundaries, the run, the reference.
    need([age_text(s) for s in (0, 59, 3599, 3600, 86399, 86400, 3 * 86400 + 85000)] == ["0m", "0m", "59m", "1h", "23h", "1d", "3d"], "the age's units are wrong")
    ref = snapshot_ref(book)
    need(ref == "2026-11-07T08:10:07Z", f"the snapshot's reference is {ref}")
    need(expected_age(by_id["0004"], ref) == ("2026-11-03T09:01:00Z", "3d"), f"the age of 0004 is {expected_age(by_id['0004'], ref)}: the run of assigned starts at 09:01")
    need(expected_age(by_id["0009"], ref) == ("2026-11-07T08:10:07Z", "0m"), f"the age of 0009 is {expected_age(by_id['0009'], ref)}")
    stale = json.loads(json.dumps(by_id["0003"]))
    stale["history"][-1]["state"] = "pr-opened"
    need(expected_age(stale, ref) is None, "a ticket whose last history entry is not its state has an age")
    need(expected_age(by_id["0009"], READ_AT)[1] == "5d", f"the live age is {expected_age(by_id['0009'], READ_AT)}")
    need(expected_pips(by_id["0007"], book) == (4, 4) and expected_pips(by_id["0001"], book) == (4, 1) and expected_pips(by_id["0003"], book) is None,
         "the pips are wrong: 0007 (4, 4), 0001 (4, 1), 0003 none")
    need(expected_pips(by_id["0001"], {"thresholds": []}) is None and expected_pips({**by_id["0001"], "attempt": "x"}, book) is None, "unreadable pips are not left out")
    # The face: every ticket's good face is accepted; each wrong one is refused.

    def good_face(t, exp, ref):
        labels = ([{"kind": "priority", "hue": None, "text": t["priority"]}] if t.get("priority") else []) + \
                 ([{"kind": "feature", "hue": str(hue_of(t["feature"])), "text": t["feature"]}] if t.get("feature") else [])
        age, pips, who = expected_age(t, ref), expected_pips(t, book), actor_of(t, exp)
        return {"id": t["id"], "labels": labels, "title": norm(t["title"]), "marks": [], "nows": 1, "who": [who] if who else [],
                "age": [{"datetime": age[0], "text": age[1]}] if age else [],
                "pips": [{"max": str(pips[0]), "filled": str(pips[1]), "pip": pips[0], "on": pips[1]}] if pips else []}
    for t in book["tickets"]:
        bad = face_problems(good_face(t, turns[t["id"]], ref), t, turns[t["id"]], book, ref)
        need(bad == [], f"a good face of {t['id']} is refused: {bad}")
    nine, seven, two = by_id["0009"], by_id["0007"], by_id["0002"]
    face9, face7, face2 = good_face(nine, turns["0009"], ref), good_face(seven, turns["0007"], ref), good_face(two, turns["0002"], ref)
    for what, face, t in (("a priority label missing", {**face9, "labels": face9["labels"][1:]}, nine),
                          ("a label of another kind", {**face9, "labels": face9["labels"] + [{"kind": "owner", "hue": None, "text": "x"}]}, nine),
                          ("a wrong hue", {**face9, "labels": [face9["labels"][0], {**face9["labels"][1], "hue": str((hue_of("waiting-list") + 1) % 6)}]}, nine),
                          ("a wrong priority text", {**face9, "labels": [{**face9["labels"][0], "text": "P1"}, face9["labels"][1]]}, nine),
                          ("a title that is not the name", {**face9, "title": "other"}, nine),
                          ("two now lines", {**face9, "nows": 2}, nine),
                          ("a wrong actor", {**face9, "who": ["tower"]}, nine),
                          ("no actor", {**face9, "who": []}, nine),
                          ("a badge for a state with no step", {**face2, "who": ["tower"]}, two),
                          ("a wrong time", {**face9, "age": [{"datetime": "2026-11-07T08:10:07Z", "text": "1h"}]}, nine),
                          ("a time on a ticket that has none", {**face9, "age": []}, nine),
                          ("pips of another size", {**face7, "pips": [{**face7["pips"][0], "pip": 3}]}, seven),
                          ("pips filled wrong", {**face7, "pips": [{**face7["pips"][0], "on": 2}]}, seven),
                          ("pips where there is no attempt", {**face9, "pips": face7["pips"]}, nine)):
        need(face_problems(face, t, turns[t["id"]], book, ref), f"face: {what} is accepted")
    need(mark_problems({"marks": ["Wait"]}, {"title": "Add a waitlist"}, "wait") is None, "a mark of the match is refused")
    need(mark_problems({"marks": []}, {"title": "Add a waitlist"}, "wait"), "a title that holds the match and shows no mark is accepted")
    need(mark_problems({"marks": ["wait"]}, {"title": "Tidy the README"}, "wait"), "a mark on a title that does not hold the match is accepted")
    need(mark_problems({"marks": ["waitl"]}, {"title": "Add a waitlist"}, "wait"), "a mark wider than the match is accepted")
    # The back.
    exp9 = turns["0009"]
    stages = [{"band": b, "mark": "done"} for b in STAGES]
    good = {"exists": True, "open": True, "modal": True, "drawers": 1, "drawer": "0009", "inside": True, "nows": ["Your turn"], "acts": [{"href": "#ticket/0009", "primary": True}],
            "stage_lists": 1, "stages": stages, "phases": ["a", "b"], "questions": ["no ## Perimeter section"], "link": 1,
            "rect": {"w": 700, "h": 800}, "hash": "#kanban?card=0009", "history": 1, "active": {"card": None, "inBoard": False}}
    args = ("0009", "Your turn", stages, ["a", "b"], exp9, "no ## Perimeter section")
    need(back_problems(good, *args) == [], f"a good back is refused: {back_problems(good, *args)}")
    for what, bad in (("a closed dialog", {**good, "open": False}), ("a dialog that is not modal", {**good, "modal": False}),
                      ("a drawer of another ticket", {**good, "drawer": "0007"}), ("two drawers", {**good, "drawers": 2}),
                      ("the focus outside", {**good, "inside": False}), ("another now line", {**good, "nows": ["The tower"]}),
                      ("two now lines", {**good, "nows": ["Your turn", "Your turn"]}), ("another strip", {**good, "stages": stages[::-1]}),
                      ("other rows", {**good, "phases": ["b", "a"]}), ("no action", {**good, "acts": []}),
                      ("an action that is not primary", {**good, "acts": [{"href": "#ticket/0009", "primary": False}]}),
                      ("an action to elsewhere", {**good, "acts": [{"href": "#launch", "primary": True}]}),
                      ("two actions", {**good, "acts": good["acts"] * 2}), ("no question text", {**good, "questions": []}),
                      ("no link to the timeline", {**good, "link": 0})):
        need(back_problems(bad, *args), f"back: {what} is accepted")
    closed = {"open": False, "drawers": 0, "hash": "#kanban", "active": {"card": "0009"}}
    need(closed_problems(closed, "0009") == [], f"a closed back is refused: {closed_problems(closed, '0009')}")
    for what, bad in (("still open", {**closed, "open": True}), ("a drawer left", {**closed, "drawers": 1}), ("card= left", {**closed, "hash": "#kanban?card=0009"}),
                      ("the focus on another card", {**closed, "active": {"card": "0003"}}), ("the focus nowhere", {**closed, "active": None})):
        need(closed_problems(bad, "0009"), f"closed: {what} is accepted")
    # The flight and the announcement.
    moved = {"moved": True, "from": MOVED_FROM, "col": MOVED_TO, "live": "polite", "announce": f"{MOVED_ID} moved from {MOVED_FROM} to {MOVED_TO}", "animated": 2}
    need(flight_problems(moved, False) == [] and flight_problems({**moved, "animated": 0}, True) == [], "a good flight is refused")
    for what, bad, reduced in (("a card not marked", {**moved, "moved": False}, False), ("a wrong data-from", {**moved, "from": "review"}, False),
                               ("the card in the old column", {**moved, "col": MOVED_FROM}, False), ("a region that is not polite", {**moved, "live": "assertive"}, False),
                               ("an empty announcement", {**moved, "announce": ""}, False),
                               ("an announcement that swaps the states", {**moved, "announce": f"{MOVED_ID} moved from {MOVED_TO} to {MOVED_FROM}"}, False),
                               ("an announcement with no id", {**moved, "announce": f"moved from {MOVED_FROM} to {MOVED_TO}"}, False),
                               ("no animation without reduced motion", {**moved, "animated": 0}, False),
                               ("an animation with reduced motion", moved, True)):
        need(flight_problems(bad, reduced), f"flight: {what} is accepted")
    mv = moved_logbook(book)
    need(next(c for c in mv["kanban"] if c["state"] == MOVED_TO)["tickets"] == [MOVED_ID] and MOVED_ID not in next(c for c in mv["kanban"] if c["state"] == MOVED_FROM)["tickets"]
         and next(t for t in mv["tickets"] if t["id"] == MOVED_ID)["state"] == MOVED_TO, "the moved logbook does not move the card")
    # The long column.
    okcol = {"sh": 2000, "ch": 800, "overflow": "auto", "top": 400, "gap": 0, "h3_top": 60, "vh": 900, "sw": 1440, "cw": 1440}
    need(long_problems(okcol) == [], f"a good long column is refused: {long_problems(okcol)}")
    for what, bad in (("a column that does not overflow", {**okcol, "sh": 800}), ("overflow visible", {**okcol, "overflow": "visible"}),
                      ("a column that does not scroll", {**okcol, "top": 0}), ("a header that scrolled away", {**okcol, "gap": -400, "h3_top": -340}),
                      ("a header below the viewport", {**okcol, "h3_top": 950, "gap": 0}), ("a page that scrolls sideways", {**okcol, "sw": 1500}), ("no column", None)):
        need(long_problems(bad), f"long column: {what} is accepted")
    # Contrast: the formula on known pairs, and each way to fail.
    need(abs(contrast((0, 0, 0), (255, 255, 255)) - 21) < 1e-9, "black on white is not 21:1")
    need(abs(contrast((255, 255, 255), (0, 0, 0)) - 21) < 1e-9, "the contrast depends on the order")
    need(abs(contrast((0x76, 0x76, 0x76), (255, 255, 255)) - 4.54) < 0.01, f"#767676 on white is {contrast((0x76, 0x76, 0x76), (255, 255, 255)):.3f}, want about 4.54")
    need(contrast((0x77, 0x77, 0x77), (255, 255, 255)) < 4.5, "#777777 on white reaches 4.5:1")
    need(is_large(24, 400) and is_large(18.66, 700) and not is_large(18.66, 400) and not is_large(18, 700) and not is_large(14, 700), "the large-text rule is wrong")
    ink = {"tag": "p", "cls": "x", "text": "t", "image": False, "px": 14, "weight": 400}
    need(contrast_problems([{**ink, "fg": (0x76, 0x76, 0x76), "bg": (255, 255, 255)}], "w") == [], "text at 4.54:1 is refused")
    need(contrast_problems([{**ink, "fg": (0x80, 0x80, 0x80), "bg": (255, 255, 255)}], "w"), "grey 14px text at 3.95:1 is accepted")
    need(contrast_problems([{**ink, "fg": (0x80, 0x80, 0x80), "bg": (255, 255, 255), "px": 24}], "w") == [], "large text at 3.95:1 is refused")
    need(contrast_problems([{**ink, "fg": (0x95, 0x95, 0x95), "bg": (255, 255, 255), "px": 24}], "w"), "large text at 2.9:1 is accepted")
    need(contrast_problems([{**ink, "fg": (0, 0, 0), "bg": (255, 255, 255), "image": True}], "w"), "a text over a background-image is accepted")
    outline = {"style": "solid", "width": 2.0, "color": (0, 0, 0), "bg": (255, 255, 255)}
    need(focus_problems(outline) == [], f"a good focus ring is refused: {focus_problems(outline)}")
    for what, bad in (("no outline", {**outline, "style": "none"}), ("a 1px outline", {**outline, "width": 1.0}),
                      ("a pale outline", {**outline, "color": (0xcc, 0xcc, 0xcc)}), ("no card reached", None)):
        need(focus_problems(bad), f"focus: {what} is accepted")
    # No drag.
    need(drag_problems(["click", "keydown"], 0) == [], "a session with no drag listener is refused")
    for what, events, draggable in (("dragstart", ["click", "dragstart"], 0), ("dragover", ["dragover"], 0), ("drop", ["drop"], 0), ("draggable", ["click"], 1)):
        need(drag_problems(events, draggable), f"no drag: {what} is accepted")


def self_checks_0071():
    """ADR 0071: the expectations and every comparison of t-z, each shown to fail on a wrong input. They run over a small logbook
    written here, not over the golden: the golden is the reader's output, and these checks must stand before it exists."""
    import copy
    gates = ["risk", "secrets", "mutation", "test-proof"]
    roles = ["architect", "dev-worker", "ops-triage", "product", "release", "test-reviewer"]
    err = "withheld: the secrets gate did not say GO on attempt 2"
    row = lambda g, v, d="": {"gate": g, "verdict": v, "line": f"{v}: {g}" + (f" — {d}" if d else "")}  # noqa: E731
    mini = {"schema": "lights-out/logbook/1.3", "thresholds": [{"key": "REWORK_MAX_ATTEMPTS", "value": "4"}],
            "releases": [{"version": "1.0", "ticket": "0010", "verdict": "held", "answer": {"answer": "GO", "by": "bob", "via": "cli"},
                          "stages": [{"pct": 5, "verdict": "GO"}, {"pct": 25, "verdict": "GO"}]},
                         {"version": "2.0", "ticket": "0011", "verdict": "held", "answer": None, "stages": [{"pct": 5, "verdict": "NO-GO: x — y"}]}],
            "tickets": [
                {"id": "0010", "title": "T", "updated_at": "2026-01-02T00:00:00Z", "attempt": 2, "state": "held", "perimeter": ["a/*"],
                 "tasks": [{"role": "dev-worker", "attempt": 1, "harness": "network", "model": None,
                            "members": [{"id": "a", "harness": "replay", "model": "m", "replayed": True, "hand_written": None},
                                        {"id": "b", "harness": "replay", "model": None, "replayed": True, "hand_written": True}],
                            "patch": {"text": "diff A\n", "bytes": 7, "truncated": False}},
                           {"role": "dev-worker", "attempt": 2, "harness": "network", "model": None,
                            "members": [{"id": "a", "harness": "replay", "model": "m", "replayed": True, "hand_written": None},
                                        {"id": "b", "harness": "replay", "model": None, "replayed": True, "hand_written": True}],
                            "patch": {"ok": False, "error": err}}],
                 "rework": [{"attempt": 1, "gates": [row("risk", "GO", "low"), row("mutation", "NO-GO", "3 survived")]}],
                 "ci": {"gates": [row("risk", "GO"), row("secrets", "GO"), row("mutation", "GO")]},
                 "review": {"role": "test-reviewer", "verdict": "approved"}, "product": {"consulted": False}, "release": {"version": "1.0"},
                 "files": [{"path": "a/x.py", "glob": "a/*", "member": "a", "attempts": [1, 2], "tests": ["t/x.py"], "adrs": ["0005"], "held_by": ["0002"]}]},
                {"id": "0011", "title": "U", "updated_at": "2026-01-01T00:00:00Z", "attempt": None, "state": "held", "perimeter": ["b/*"],
                 "tasks": [], "rework": [], "ci": None, "review": None, "product": {"consulted": True}, "release": {"version": "2.0"}, "files": []},
                {"id": "0012", "title": "V", "updated_at": "2026-01-02T00:00:00Z", "attempt": None, "state": "opened", "perimeter": [],
                 "tasks": [], "rework": [], "ci": None, "review": None, "product": None, "release": None, "files": None}]}
    need(default_ticket(mini) == "0012", f"the default ticket of the small logbook is {default_ticket(mini)}: ties go to the highest id")
    mini["tickets"][2]["updated_at"] = None
    need(default_ticket(mini) == "0010", "a ticket with no updated_at is not last")
    need(attempts_of(mini["tickets"][0]) == [1, 2] and attempts_of(mini["tickets"][1]) == [], "the attempts are wrong")
    need(version_of(mini) == "1.3", "the version is wrong")
    need(len(makefile_gates()) == 8 and "mutation" in makefile_gates() and len(roles_dirs()) == 6, f"the Makefile's gates {makefile_gates()} or roles/ {roles_dirs()} are not read")
    exp = expect_net(mini, "0010", None, gates, roles)
    need(exp["gates"] == [("risk", "GO"), ("secrets", "GO"), ("mutation", "GO"), ("test-proof", "not-run")], f"the gates of the latest attempt are {exp['gates']}")
    need(expect_net(mini, "0010", 1, gates, roles)["gates"] == [("risk", "GO"), ("mutation", "NO-GO"), ("secrets", "not-run"), ("test-proof", "not-run")],
         "the gates of attempt 1 are not the rework entry's, then the rest as not-run")
    need([r for r, v in exp["ran"].items() if v] == ["dev-worker", "test-reviewer"], f"the roles that ran are {exp['ran']}")
    need(expect_net(mini, "0011", None, gates, roles)["human"]["verdict"] == "waiting" and expect_net(mini, "0011", None, gates, roles)["stages"] == [("5", "NO-GO")]
         and expect_net(mini, "0012", None, gates, roles)["human"]["verdict"] == "not-reached" and expect_net(mini, "0011", None, gates, roles)["ran"]["product"],
         "a held release with no answer is not waiting, or a NO-GO stage is a GO, or a ticket with no release is reached, or product did not run")
    info = {"ticket": "0010", "schema": "lights-out/logbook/1.3", "tower": True,
            "roles": [{"role": r, "ran": "true" if r in ("dev-worker", "test-reviewer") else "false"} for r in roles],
            "workers": [{"worker": "a", "harness": "replay", "model": "m", "replayed": "true", "hand": "false"},
                        {"worker": "b", "harness": "replay", "model": "", "replayed": "true", "hand": "true"}],
            "gates": [{"gate": g, "verdict": v, "attempt": "2"} for g, v in exp["gates"]],
            "review": "approved", "rework": {"count": "1", "max": "4"},
            "stages": [{"pct": "5", "verdict": "GO"}, {"pct": "25", "verdict": "GO"}],
            "human": {"verdict": "GO", "text": "Held at 25%: answered GO by bob through cli"},
            "stream": [{"attempt": "2", "text": "attempt 2 a b", "lines": [{"gate": g, "verdict": "GO", "text": f"GO: {g}"} for g in ("risk", "secrets", "mutation")],
                        "patch": {"truncated": None, "open": True, "text": err}},
                       {"attempt": "1", "text": "attempt 1 a b",
                        "lines": [{"gate": "risk", "verdict": "GO", "text": "GO: risk — low"}, {"gate": "mutation", "verdict": "NO-GO", "text": "NO-GO: mutation — 3 survived"}],
                        "patch": {"truncated": "false", "open": False, "text": "diff A\n"}}],
            "files": [{"path": "a/x.py", "glob": "a/*", "member": "a", "held": "0002", "tests": "t/x.py", "adrs": ["#adr/0005"]}],
            "facts": ["a fact"], "label": None, "replay": "off", "row": None}
    need(net_problems(info, exp) == [], f"a screen that is what the record says is refused: {net_problems(info, exp)}")
    need(net_problems(None, exp), "a page with no section#net is accepted")

    def mutated(what, change):
        bad = copy.deepcopy(info)
        change(bad)
        need(net_problems(bad, exp), f"net_problems accepts {what}")

    mutated("another ticket", lambda i: i.update(ticket="0011"))
    mutated("a schema of another version", lambda i: i.update(schema="lights-out/logbook/1.2"))
    mutated("no tower", lambda i: i.update(tower=False))
    mutated("five roles", lambda i: i["roles"].pop())
    mutated("a role that ran, dark", lambda i: i["roles"][1].update(ran="false"))
    mutated("a role that did not run, lit", lambda i: i["roles"][0].update(ran="true"))
    mutated("a worker on another model", lambda i: i["workers"][0].update(model="x"))
    mutated("a worker with a model that has none", lambda i: i["workers"][1].update(model="m"))
    mutated("a hand-written worker not marked", lambda i: i["workers"][1].update(hand="false"))
    mutated("a model-run worker marked hand-written", lambda i: i["workers"][0].update(hand="true"))
    mutated("a replayed worker not marked", lambda i: i["workers"][0].update(replayed="false"))
    mutated("a missing worker", lambda i: i["workers"].pop())
    mutated("another harness", lambda i: i["workers"][0].update(harness="adk"))
    mutated("a gate with the wrong verdict", lambda i: i["gates"][0].update(verdict="NO-GO"))
    mutated("a gate that ran, not-run", lambda i: i["gates"][1].update(verdict="not-run"))
    mutated("gates out of the order run", lambda i: i["gates"].reverse())
    mutated("a missing not-run gate", lambda i: i["gates"].pop())
    mutated("an edge with no attempt", lambda i: i["gates"][0].update(attempt=None))
    mutated("an edge of another attempt", lambda i: i["gates"][0].update(attempt="1"))
    mutated("another review verdict", lambda i: i.update(review="changes-requested"))
    mutated("no rework loop", lambda i: i.update(rework=None))
    mutated("another rework count", lambda i: i["rework"].update(count="2"))
    mutated("no rework max", lambda i: i["rework"].update(max=None))
    mutated("a canary stage missing", lambda i: i["stages"].pop())
    mutated("a stage with the wrong verdict", lambda i: i["stages"][0].update(verdict="NO-GO"))
    mutated("no human gate", lambda i: i.update(human=None))
    mutated("a human gate waiting", lambda i: i["human"].update(verdict="waiting"))
    mutated("a human gate that does not say who", lambda i: i["human"].update(text="Held at 25%: answered GO through cli"))
    mutated("a stream oldest first", lambda i: i["stream"].reverse())
    mutated("a changed gate line", lambda i: i["stream"][1]["lines"][1].update(text="NO-GO: mutation — 4 survived"))
    mutated("a line with another verdict", lambda i: i["stream"][1]["lines"][1].update(verdict="GO"))
    mutated("a missing line", lambda i: i["stream"][0]["lines"].pop())
    mutated("a stream entry that names no worker", lambda i: i["stream"][0].update(text="attempt 2"))
    mutated("a changed patch", lambda i: i["stream"][1]["patch"].update(text="diff B\n"))
    mutated("a truncated flag that is wrong", lambda i: i["stream"][1]["patch"].update(truncated="true"))
    mutated("no patch", lambda i: i["stream"][1].update(patch=None))
    mutated("a withheld patch with another reason", lambda i: i["stream"][0]["patch"].update(text="nothing"))
    mutated("the wrong patch open", lambda i: i["stream"][1]["patch"].update(open=True))
    mutated("a file row of another glob", lambda i: i["files"][0].update(glob="b/*"))
    mutated("a file row of another member", lambda i: i["files"][0].update(member="b"))
    mutated("a file held by another", lambda i: i["files"][0].update(held="0003"))
    mutated("a file with no test", lambda i: i["files"][0].update(tests="none"))
    mutated("an ADR link that is not #adr/NNNN", lambda i: i["files"][0].update(adrs=["#adrs?q=0005"]))
    mutated("a file with no ADR link", lambda i: i["files"][0].update(adrs=[]))
    mutated("a file row missing", lambda i: i.update(files=[]))
    mutated("a screen with no fact", lambda i: i.update(facts=[]))
    # A network ticket's tests: files with no row is a problem only when the record has files.
    need(net_problems({**info, "files": []}, {**exp, "files": None}) == [], "a record with unread files still demands file rows")
    # §6: the 1.2 degradation.
    sentence = "this logbook (1.2) records no patches or gate lines"
    old = {"gates": [{"gate": "gates", "verdict": "NO-GO", "attempt": "1"}], "stream_text": f"attempt 1 {sentence}", "text": f"{sentence} a/* {sentence}",
           "stream": [{"lines": []}]}
    exp_old = {"gates": [("gates", "NO-GO")], "perimeter": ["a/*"]}
    need(net_old_problems(old, exp_old, sentence) == [], f"a good 1.2 screen is refused: {net_old_problems(old, exp_old, sentence)}")
    for what, bad in (("two edges", {**old, "gates": old["gates"] + [{"gate": "risk", "verdict": "GO", "attempt": "1"}]}),
                      ("another verdict", {**old, "gates": [{"gate": "gates", "verdict": "GO", "attempt": "1"}]}),
                      ("a stream that does not say it", {**old, "stream_text": "attempt 1"}),
                      ("a sentence said once", {**old, "text": f"{sentence} a/*"}),
                      ("no perimeter", {**old, "text": f"{sentence} {sentence}"}),
                      ("gate lines in a 1.2 stream", {**old, "stream": [{"lines": [{"gate": "risk"}]}]})):
        need(net_old_problems(bad, exp_old, sentence), f"the 1.2 check accepts {what}")
    need(net_old_problems(None, exp_old, sentence), "a 1.2 check accepts a page with no section#net")
    t12 = {"id": "1", "attempt": 2, "rework": [{"attempt": 2, "line": "NO-GO: gates — x"}], "ci": {"verdict": "GO"}, "tasks": [], "perimeter": []}
    need(expect_net_old({"tickets": [t12]}, "1")["gates"] == [("gates", "NO-GO")] and expect_net_old({"tickets": [{**t12, "rework": []}]}, "1")["gates"] == [("gates", "GO")]
         and expect_net_old({"tickets": [{**t12, "rework": [], "ci": None}]}, "1")["gates"] is None, "the 1.2 summary edge's rule is wrong")
    # The CLI's facts: the lines that start with a space, outside the patch block.
    view = "ticket 0010 — T · attempt 2\ngraph\n  role dev-worker: ran\n   gate risk:   GO\nstream\n  attempt 2\n--- patch of attempt 2 ---\n  not a fact\n--- end of patch ---\nfiles by perimeter\n  a/x.py\n"
    need(cli_facts(view) == {"role dev-worker: ran", "gate risk: GO", "attempt 2", "a/x.py"}, f"the CLI's facts are read as {sorted(cli_facts(view))}")
    need(fact_problems(["a"], ["a"]) == [] and fact_problems(["a", "b"], ["a"]) and fact_problems(["a"], ["a", "b"]) and fact_problems([], []),
         "the fact comparison does not see an extra, a missing or an empty set")
    # The link.
    need(net_hash() == "#network" and net_hash("0010") == "#network/0010" and net_hash("0010", 1) == "#network/0010?attempt=1"
         and net_hash("0010", 1, True) == "#network/0010?attempt=1&replay=1" and net_hash("", "", True) == "#network?replay=1", "the link writer is wrong")
    need(net_hash_problems("#network/0010?attempt=1", net_hash("0010", 1)) is None and net_hash_problems("#network/0010?replay=1&attempt=1", net_hash("0010", 1, True))
         and net_hash_problems("#network/0010", net_hash()) and net_hash_problems("#kanban", net_hash()), "the link comparison is wrong")
    # The replay.
    static = ["a", "b", "c"]
    on = {"replay": "on", "row": "1", "label": {"visible": True, "text": REPLAY_LABEL}, "facts": ["a"], "rework": {"count": "0"}}
    need(replay_problems(on, "on", 1, static, 1, 0) == [], f"a good replay frame is refused: {replay_problems(on, 'on', 1, static, 1, 0)}")
    done = {**on, "replay": "done", "row": "5", "facts": static, "rework": {"count": "1"}}
    need(replay_problems(done, "done", 5, static, 1, 0) == [], f"a good final frame is refused: {replay_problems(done, 'done', 5, static, 1, 0)}")
    for what, frame, args in (("another state", {**on, "replay": "done"}, ("on", 1)), ("another row", {**on, "row": "2"}, ("on", 1)),
                              ("no label", {**on, "label": None}, ("on", 1)), ("a hidden label", {**on, "label": {"visible": False, "text": REPLAY_LABEL}}, ("on", 1)),
                              ("another label", {**on, "label": {"visible": True, "text": "Replay"}}, ("on", 1)),
                              ("a fact the static drawing lacks", {**on, "facts": ["a", "z"]}, ("on", 1)),
                              ("a final frame that lacks a fact", {**done, "facts": ["a", "b"]}, ("done", 5)),
                              ("a whole drawing at row 0", {**on, "row": "0", "facts": static}, ("on", 0)),
                              ("a rework count above its final", {**on, "rework": {"count": "2"}}, ("on", 1)),
                              ("a final rework count that is short", {**done, "rework": {"count": "0"}}, ("done", 5))):
        need(replay_problems(frame, args[0], args[1], static, 1, 0), f"the replay check accepts {what}")
    need(replay_problems({**on, "rework": {"count": "0"}}, "on", 1, static, 1, 1), "a rework count that went back is accepted")
    # Live.
    announce = {"live": "polite", "text": "0010 attempt 2: mutation NO-GO", "animated": 2}
    need(live_problems(1, announce, False) == [] and live_problems(1, {**announce, "animated": 0}, True) == [], "a good live answer is refused")
    for what, args in (("no mark", (0, announce, False)), ("an assertive region", (1, {**announce, "live": "assertive"}, False)),
                       ("an announcement that does not name the ticket", (1, {**announce, "text": "something moved"}, False)),
                       ("motion that did not run", (1, {**announce, "animated": 0}, False)), ("motion under reduced motion", (1, announce, True))):
        need(live_problems(*args), f"the live check accepts {what}")
    # The colour the walker reads on SVG text, and the files the screen draws.
    need(NET_MEASURE_JS != MEASURE_JS and "s.fill" in NET_MEASURE_JS, "the network's contrast walker does not read an SVG text's fill")
    need(NET_MEASURE_JS.count(": s.color)") == 1 and "parse(s.color)" not in NET_MEASURE_JS, "the network's walker lost the colour of HTML text")


def main():
    real = sys.stdout
    sys.stdout = sys.stderr  # a library that prints must not break the one-line contract
    try:
        need(GOLDEN.is_file(), f"{GOLDEN.relative_to(ROOT)} not found")
        need((ROOT / "console" / "serve.py").is_file(), "console/serve.py not found")
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        need(golden.get("schema") == "lights-out/logbook/1.3", f"the golden's schema is {golden.get('schema')!r}, want lights-out/logbook/1.3")
        need(any(t.get("adrs") for t in golden["tickets"]), "the golden has no ticket with adrs: it is not a 1.2 or later logbook")
        need(GOLDEN_12.is_file(), f"{GOLDEN_12.relative_to(ROOT)} not found: the 1.2 degradation (z) reads it")
        book12 = json.loads(GOLDEN_12.read_text(encoding="utf-8"))
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
                with tempfile.TemporaryDirectory() as tmp:
                    books, paths = derive(golden, pathlib.Path(tmp))
                    nbooks, npaths = derive_net(golden, pathlib.Path(tmp))
                    with Console(GOLDEN) as plain, Console(paths["held"]) as held, Console(paths["holders"]) as waiting:
                        bases = {"golden": plain.base, "held": held.base, "holders": waiting.base}
                        with Console(paths["faces"]) as faces, Console(paths["long"]) as long:
                            bases.update({"faces": faces.base, "long": long.base})
                            l_face(browser, bases, golden, books)
                            m_back(browser, bases, golden)
                            n_only_mine(browser, bases, golden)
                            o_flight(browser, bases, golden)
                            p_long(browser, bases)
                            q_contrast(browser, bases)
                            r_bands(browser, bases, golden)
                            s_nodrag(browser, bases)
                            net_nodrag(browser, bases)
                            q_network(browser, bases)
                            t_route(browser, bases, golden)
                            u_contract(browser, bases, golden)
                            v_derived(browser, nbooks, npaths)
                            w_cli(browser, bases, golden)
                            x_replay(browser, bases, golden)
                            y_live(browser, bases, golden, nbooks)
                            z_old(browser, book12)
                            t_agents(browser, bases, golden)
                        g_fit(browser, bases, golden)
                        h_now(browser, bases, golden, books)
                        i_overview(browser, bases, golden, books)
                        j_timeline(browser, bases, golden)
                        k_editor(browser, bases)
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
