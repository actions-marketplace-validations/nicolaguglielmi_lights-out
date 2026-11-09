#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""site/render.py: the board's scenarios as video, for the landing page (docs/adr/0048).

    python3 site/render.py <site dir>

Serves board/index.html alone, so its /state.json answers 404 and the board
is in its hosted, explainer-only mode (docs/adr/0035 §6). Drives it with
Playwright through its own buttons, records each take with recordVideo, and
encodes the takes with ffmpeg into <site dir>/media/:

    overview.mp4, overview.jpg   one walk through the pipeline, chapter captions on top
    hero.webm, hero.mp4, hero.gif, hero.jpg   a short loop, cropped to the diagram
    <scenario>.mp4, <scenario>.jpg            one clip per scenario on the board
    scenarios.json               id, name, blurb and seconds of each clip
    console-<screen>.jpg         stills of the console's screens (CONSOLE below), the
                                 ADR search over a logbook built from this repository's map

Every frame says what it shows: the board's scripted walks, the real code
paths with example versions and numbers. With SHOTS=<dir> it also takes
screenshots of the built landing at desktop and phone width.

Runs in the Playwright Python image with ffmpeg added (.github/workflows/
site.yml); nothing here is meant for the host.
"""
import asyncio
import functools
import http.server
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
W, H = 1600, 900
LABEL = "the board's scripted walk · real code paths, example numbers"

# The overview: (scenario, first step, last step, caption, words the board
# says at the last step). Steps count from 0, as the board's timeline does.
# If the board's scenarios change, the words stop matching and the render
# stops, instead of putting a caption over the wrong step.
OVERVIEW = [
    ("ship", 0, 3, "A ticket declares its files. A coding agent works it in a sandbox.", "the PR opens"),
    ("ship", 4, 8, "Eight gates judge the pull request. Each prints one line: GO or NO-GO.", "Risk low"),
    ("fake", 5, 6, "A test that tests nothing passes. Mutation testing says NO-GO.", "mutants survive"),
    ("perimeter", 1, 2, "A change outside the ticket's files never becomes a pull request.", "No PR is opened"),
    ("ship", 9, 15, "Merged at the judged commit, built, signed, then 5% of real traffic.", "The decision is a number"),
    ("rollback", 14, 16, "A bad canary: the numbers say NO-GO, and it rolls itself back.", "rolls back on its own"),
    ("ship", 16, 19, "Held at 25%. One human says GO before 100%. Silence never promotes.", "takes every request"),
]

CSS = """
header,#explain-bar,.sec,#explain-controls,.inv,#tour,#drawer{display:none!important}
html,body{overflow:hidden}
.wrap{max-width:none;padding:68px 16px 0}
.diagram{border-color:transparent;background:transparent}
.say{min-height:0;margin-top:2px;padding:10px 16px}
.say p{font-size:17px;line-height:1.45;max-width:none}
.say .ref{font-size:12px}
.grid{grid-template-columns:1fr 1.1fr 1.2fr;margin-top:10px}
.card{height:206px;overflow:hidden;padding:10px 12px}
#doc{max-height:118px;overflow:hidden}
.locks{grid-template-columns:1fr 1fr;gap:4px}
.locks li{padding:4px 6px}
.locks li .d{display:none}
.stdout{max-height:92px}
#vcap{position:fixed;left:0;right:0;top:0;height:56px;z-index:50;display:flex;align-items:center;gap:20px;padding:0 24px;
  background:#05080c;border-bottom:1px solid #1c2733;color:#e8eef4;font:600 21px/1.2 'DejaVu Sans',system-ui,sans-serif}
#vcap .w{font:700 19px/1 'DejaVu Sans Mono',monospace;letter-spacing:1px;color:#e8eef4}
#vcap .w i{font-style:normal;color:#3fb950}
#vcap .k{font:600 14px/1 'DejaVu Sans Mono',monospace;color:#e3b341;letter-spacing:2px}
#vcap .l{margin-left:auto;font:400 13px/1 'DejaVu Sans Mono',monospace;color:#6f7d8b}
#vcard{position:fixed;inset:0;z-index:60;display:flex;flex-direction:column;justify-content:center;gap:26px;padding:0 150px;
  background:radial-gradient(1200px 600px at 75% 70%,#0f2a1a 0%,transparent 60%),#05080c;transition:opacity .6s;color:#e8eef4}
#vcard.off{opacity:0}
#vcard .t{font:700 84px/1.05 'DejaVu Sans',system-ui,sans-serif;letter-spacing:-1px}
#vcard .t i{font-style:normal;color:#3fb950}
#vcard .s{font:400 34px/1.3 'DejaVu Sans',system-ui,sans-serif;color:#c5d1dd;max-width:1150px}
#vcard pre{margin:0;font:400 28px/1.5 'DejaVu Sans Mono',monospace;color:#56d364}
#vcard .f{font:400 18px/1.4 'DejaVu Sans Mono',monospace;color:#6f7d8b;letter-spacing:.5px}
"""

OVERLAY = """
() => {
  const cap = document.createElement('div'); cap.id = 'vcap'; document.body.appendChild(cap);
  const card = document.createElement('div'); card.id = 'vcard'; card.className = 'off'; document.body.appendChild(card);
  const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  window.__v = {
    cap(k, text, label) {
      cap.innerHTML = '<span class="w">lights<i>-</i>out</span><span class="k">' + esc(k) + '</span><span>' + esc(text) + '</span><span class="l">' + esc(label) + '</span>';
    },
    card(t, s, f, pre) {
      card.innerHTML = '<div class="t">' + t + '</div>' + (s ? '<div class="s">' + esc(s) + '</div>' : '') + (pre ? '<pre>' + esc(pre) + '</pre>' : '') + '<div class="f">' + esc(f) + '</div>';
      card.classList.remove('off');
    },
    uncard() { card.classList.add('off'); },
  };
  // The tower document's newest entry is the one worth seeing.
  const doc = document.getElementById('doc');
  new MutationObserver(() => { doc.scrollTop = doc.scrollHeight; }).observe(doc, {childList: true, subtree: true});
}
"""

WORDMARK = "lights<i>-</i>out"


def log(*a):
    print("render:", *a, file=sys.stderr, flush=True)


class Quiet(http.server.SimpleHTTPRequestHandler):
    # The image's /etc/mime.types may not know webm; Pages does.
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".webm": "video/webm", ".mp4": "video/mp4", ".json": "application/json"}

    def log_message(self, *a):
        pass


def serve(directory):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"


def ff(*args):
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], capture_output=True, text=True)
    if p.returncode:
        err = p.stderr.strip().splitlines()
        sys.exit(f"render: ffmpeg exited {p.returncode}: {err[-1] if err else 'no stderr'}")


def seconds(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return round(float(p.stdout.strip()))


# ---- the board, through its own controls -----------------------------------

async def open_board(ctx, base):
    page = await ctx.new_page()
    await page.goto(base + "/board/index.html")
    try:
        # /state.json answered 404: the board dropped LIVE (docs/adr/0035 §6).
        await page.wait_for_selector("#m-live.hide", state="attached", timeout=15000)
    except Exception:
        sys.exit("render: the board never reached its hosted, explainer-only mode (#m-live hidden after a 404 on state.json)")
    await page.add_style_tag(content=CSS)
    await page.evaluate(OVERLAY)
    return page


async def pick(page, sc):
    await page.evaluate("""id => { const b = document.querySelector(`#scenarios button[data-id="${id}"]`);
      if (!b) throw new Error('the board has no scenario ' + id); b.click(); }""", sc)


async def jump(page, i):
    await page.evaluate("""i => { const t = document.querySelector(`#timeline i[data-i="${i}"]`);
      if (!t) throw new Error('the scenario has no step ' + i); t.click(); }""", i)


async def forward(page):
    await page.evaluate("() => document.getElementById('b-next').click()")


async def says(page):
    return await page.evaluate("() => document.querySelector('#say p').textContent")


async def check(page, sc, i, words):
    said = await says(page)
    if words not in said:
        sys.exit(f"render: board scenario {sc!r} step {i + 1} no longer says {words!r} (it says {said!r}); "
                 "update OVERVIEW in site/render.py to follow the board")


async def inventory(browser, base):
    """Every scenario on the board: id, name, blurb and what each step says."""
    ctx = await browser.new_context(viewport={"width": W, "height": H}, color_scheme="dark")
    page = await open_board(ctx, base)
    scs = await page.evaluate("""() => [...document.querySelectorAll('#scenarios button')].map(b =>
      ({id: b.dataset.id, name: b.firstChild.textContent.trim(), blurb: b.title}))""")
    for s in scs:
        await pick(page, s["id"])
        n = await page.evaluate("() => document.querySelectorAll('#timeline i').length")
        s["says"] = []
        for i in range(n):
            await jump(page, i)
            s["says"].append(await says(page))
    await ctx.close()
    if not scs:
        sys.exit("render: the board lists no scenario")
    return scs


# ---- takes -------------------------------------------------------------------

async def take(browser, base, body):
    """Record one take; returns the raw video, the seconds to trim from its start, and what body returned."""
    raw = tempfile.mkdtemp()
    ctx = await browser.new_context(viewport={"width": W, "height": H}, color_scheme="dark", record_video_dir=raw,
                                    record_video_size={"width": W, "height": H})
    t0 = time.monotonic()
    page = await open_board(ctx, base)
    lead = {}

    async def start():
        await asyncio.sleep(0.4)
        lead["s"] = time.monotonic() - t0

    extra = await body(page, start)
    await ctx.close()
    return pathlib.Path(await page.video.path()), lead["s"], extra


async def overview(page, start):
    await page.evaluate("([t, s, f]) => __v.card(t, s, f)", [WORDMARK, "The safety system for a dark factory of AI coding agents.", LABEL])
    await start()
    await asyncio.sleep(3.4)
    for k, (sc, a, b, text, words) in enumerate(OVERVIEW, 1):
        await pick(page, sc)
        await jump(page, a)
        await page.evaluate("([k, t, l]) => __v.cap(k, t, l)", [f"{k}/{len(OVERVIEW)}", text, LABEL])
        if k == 1:
            await page.evaluate("() => __v.uncard()")
        await asyncio.sleep(2.6)
        for i in range(a + 1, b + 1):
            await forward(page)
            await asyncio.sleep(2.0 + (1.4 if i == b else 0))
        await check(page, sc, b, words)
    await page.evaluate("([t, s, f, p]) => __v.card(t, s, f, p)", [
        WORDMARK, "Runs complete on your laptop: no account, no API key, no cloud.",
        "nicolaguglielmi.github.io/lights-out",
        "git clone https://github.com/nicolaguglielmi/lights-out.git\ncd lights-out && ./go demo"])
    await asyncio.sleep(5.0)


async def hero(page, start):
    await page.evaluate("() => document.getElementById('vcap').remove()")
    await pick(page, "ship")
    await jump(page, 3)
    box = await page.locator(".diagram").bounding_box()
    await start()
    await asyncio.sleep(0.8)
    for _ in range(4):
        await forward(page)
        await asyncio.sleep(1.5)
    poster = await page.screenshot(type="png", clip=box)
    await pick(page, "rollback")
    await jump(page, 13)
    await asyncio.sleep(1.2)
    for _ in range(3):
        await forward(page)
        await asyncio.sleep(1.7)
    await asyncio.sleep(0.8)
    return {"box": box, "poster": poster}


def dwell(text):
    # Reading time for one step, a decision: a glance plus about four and a
    # half words a second, at least 2.2 s so the handoff animation (up to
    # 1.1 s) lands first, at most 5.5 s; the clip can be paused.
    return min(5.5, max(2.2, 1.2 + len(text.split()) / 4.5))


async def clip(page, start, s, ship):
    await page.evaluate("([t, s, f]) => __v.card(t, s, f)", [s["name"], s["blurb"], LABEL])
    await pick(page, s["id"])
    await start()
    await asyncio.sleep(2.4)
    await page.evaluate("([k, t, l]) => __v.cap(k, t, l)", [s["name"].upper(), s["blurb"], LABEL])
    await page.evaluate("() => __v.uncard()")
    # Steps this scenario shares with "ship" from the start were explained
    # there; they pass quickly here.
    same = 0
    if s["id"] != "ship":
        while same < min(len(ship), len(s["says"])) and ship[same] == s["says"][same]:
            same += 1
    for i, text in enumerate(s["says"]):
        if i:
            await forward(page)
        await asyncio.sleep(1.3 if i < same else dwell(text))
    poster = await page.screenshot(type="png")
    await asyncio.sleep(1.6)
    return {"poster": poster}


# ---- encoding ----------------------------------------------------------------

def even(x):
    return int(x) // 2 * 2


def jpg(png, dst, width):
    src = pathlib.Path(tempfile.mkdtemp()) / "p.png"
    src.write_bytes(png)
    ff("-i", src, "-vf", f"scale={width}:-2:flags=lanczos", "-q:v", "4", dst)


def mp4(src, lead, dst, crf=23, vf=None):
    ff("-ss", f"{lead:.2f}", "-i", src, "-an", *(["-vf", vf] if vf else []), "-c:v", "libx264", "-preset", "slow",
       "-crf", crf, "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst)


async def render(site):
    media = site / "media"
    media.mkdir(parents=True, exist_ok=True)
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"render: {tool} is not on PATH (the site workflow installs it in the Playwright image)")
    board = pathlib.Path(tempfile.mkdtemp())
    (board / "board").mkdir()
    shutil.copy(ROOT / "board" / "index.html", board / "board" / "index.html")
    base = serve(board)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        scs = await inventory(browser, base)
        ship = next((s["says"] for s in scs if s["id"] == "ship"), None)
        if ship is None:
            sys.exit("render: the board has no 'ship' scenario, which the overview and the clips start from")
        log(f"{len(scs)} scenarios: " + ", ".join(f"{s['id']} ({len(s['says'])} steps)" for s in scs))
        # Three takes at a time: each records in real time.
        gate = asyncio.Semaphore(3)

        async def run(name, body):
            async with gate:
                t = time.monotonic()
                out = await take(browser, base, body)
                log(f"recorded {name} in {time.monotonic() - t:.0f}s")
                return name, out

        jobs = [run("overview", overview), run("hero", hero)]
        jobs += [run(s["id"], functools.partial(clip, s=s, ship=ship)) for s in scs]
        takes = dict(await asyncio.gather(*jobs))
        await browser.close()

    src, lead, _ = takes["overview"]
    mp4(src, lead, media / "overview.mp4", crf=22)
    ff("-ss", f"{lead + 9:.2f}", "-i", src, "-frames:v", "1", "-vf", "scale=1280:-2:flags=lanczos", "-q:v", "4", media / "overview.jpg")

    src, lead, extra = takes["hero"]
    b = extra["box"]
    crop = f"crop={even(b['width'])}:{even(b['height'])}:{even(b['x'])}:{even(b['y'])}"
    mp4(src, lead, media / "hero.mp4", crf=26, vf=f"{crop},scale=1200:-2:flags=lanczos")
    ff("-ss", f"{lead:.2f}", "-i", src, "-an", "-vf", f"{crop},scale=1200:-2:flags=lanczos", "-c:v", "libvpx-vp9",
       "-b:v", "0", "-crf", "36", "-row-mt", "1", media / "hero.webm")
    ff("-ss", f"{lead:.2f}", "-i", src, "-vf",
       f"fps=12,{crop},scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];"
       "[b][p]paletteuse=dither=bayer:bayer_scale=4", media / "hero.gif")
    jpg(extra["poster"], media / "hero.jpg", 1200)

    index = []
    for s in scs:
        src, lead, extra = takes[s["id"]]
        mp4(src, lead, media / f"{s['id']}.mp4", crf=24)
        jpg(extra["poster"], media / f"{s['id']}.jpg", 800)
        index.append({"id": s["id"], "name": s["name"], "blurb": s["blurb"], "seconds": seconds(media / f"{s['id']}.mp4")})
    (media / "scenarios.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    for f in sorted(media.iterdir()):
        log(f"{f.name}: {f.stat().st_size // 1024} KiB" + (f", {seconds(f)} s" if f.suffix in (".mp4", ".webm") else ""))


async def shots(site, out):
    """The built landing at desktop and phone width, a few viewports each."""
    out.mkdir(parents=True, exist_ok=True)
    base = serve(site)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for name, opts in (("desktop", {"viewport": {"width": 1440, "height": 900}}),
                           ("phone", {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2,
                                      "is_mobile": True, "has_touch": True})):
            ctx = await browser.new_context(**opts)
            page = await ctx.new_page()
            await page.goto(base + "/index.html")
            await asyncio.sleep(2.5)
            await page.screenshot(path=out / f"{name}-1-hero.png")
            for i, sel in enumerate(("#how", "#how-3", "#how-4", "#scenarios", "#real", "#try"), 2):
                if await page.locator(sel).count() == 0:
                    sys.exit(f"render: the landing has no {sel}")
                await page.locator(sel).scroll_into_view_if_needed()
                await page.evaluate("s => document.querySelector(s).scrollIntoView({block: 'start'})", sel)
                await asyncio.sleep(2.2)
                await page.screenshot(path=out / f"{name}-{i}-{sel[1:]}.png")
            await page.screenshot(path=out / f"{name}-full.png", full_page=True)
            await ctx.close()
        await browser.close()


# ---- the console --------------------------------------------------------------

# The console's screens as stills (docs/adr/0047, 0055, 0059), served by
# console/serve.py itself in snapshot mode, where nothing can be pressed:
# (still, logbook, screen with its view, viewport, theme, what to type).
# The kanban, the ticket, the overview and the editor read the logbook
# ci/logbook.sh builds over stub sources, the one with tickets in more
# states than one demo leaves; the landing says so under them. The ADR
# search reads a logbook built here from this repository's own project map
# (REPO below): its ADRs are the real ones. A demo's own logbook is not
# committed: a threshold's name in its `key` field reads as a secret to
# gitleaks, and a change cannot excuse its own finding (docs/adr/0049 §4).
GOLDEN = "fixtures/logbook/golden-1.2.json"
REPO = "this repository's map"
DRAFT = [("input[name=title]", "Show who requested a ticket on its card"),
         ("textarea[name=context]", "A card says what a ticket is, not who asked for it."),
         ("input[name=given]", "a ticket requested from the console"),
         ("input[name=when]", "the kanban draws its card"),
         ("input[name=then]", "the card shows the identity on the request row and `via console`"),
         ("textarea[name=perimeter]", "console/index.html"),
         ("input[name=feature]", "console")]
# The kanban is drawn whole, at the landing's desktop width: since ADR 0063
# the board fits it, with every card's now line; the rollback still is a
# ticket's timeline down to the automatic rollback.
CONSOLE = [
    ("console-kanban", GOLDEN, "kanban", (1440, 820), "light", None),
    ("console-ticket", GOLDEN, "ticket/0009", (1440, 1040), "light", None),
    ("console-rollback", GOLDEN, "ticket/0001", (1440, 900), "dark", None),
    ("console-overview", GOLDEN, "overview", (1440, 1000), "light", None),
    ("console-request", GOLDEN, "request", (1440, 1200), "light", DRAFT),
    ("console-adrs", REPO, "adrs?q=kanban", (1440, 1000), "dark", None),
]


def repo_logbook(tmp):
    """A logbook whose ADRs are this repository's, from its project map at HEAD;
    no plane, so its tickets say they could not be read."""
    out, book, targets = tmp / "map.sqlite", tmp / "logbook.json", tmp / "targets"
    # The Makefile's targets, read here: the Playwright image has no make,
    # which core/map.py would run for `make help` without --targets.
    targets.write_text("\n".join(sorted(set(re.findall(r"^([a-z][a-z0-9-]*):", (ROOT / "Makefile").read_text(
        encoding="utf-8"), re.M)))) + "\n", encoding="utf-8")
    for argv in (["python3", "core/map.py", "build", "--repo", ".", "--rev", "HEAD", "--tickets", "tickets",
                  "--targets", str(targets), "--exclude", "docs/PLAN.md docs/plans/* .claude/*", "--out", str(out)],
                 ["python3", "core/logbook.py", "--out", str(book)]):
        p = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                           env={k: v for k, v in {**os.environ, "MAP_FILE": str(out),
                                                    # The header names them; this map is of the repository
                                                    # itself, read with no key.
                                                    "WORKLOAD": "lights-out", "LEVEL": "l0"}.items()
                                if k != "STATE_STORE"})
        if p.returncode != 0:
            sys.exit(f"render: {' '.join(argv[:3])} failed: {(p.stderr or p.stdout)[-400:]}")
    return book


def console(logbook):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "CONSOLE_SNAPSHOT": str(ROOT / logbook), "CONSOLE_LISTEN": str(port), "CONSOLE_PORT": str(port)}
    proc = subprocess.Popen([sys.executable, str(ROOT / "console" / "serve.py")], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/v1/console.json", timeout=1).close()
            return proc, base
        except OSError:
            time.sleep(0.1)
    proc.kill()
    sys.exit(f"render: console/serve.py over {logbook} did not answer: {proc.stderr.read().decode()[-400:]}")


async def stills(site):
    media = site / "media"
    media.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="render-map-") as tmp:
        repo = repo_logbook(pathlib.Path(tmp))
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            for name, logbook, screen, (w, h), theme, typed in CONSOLE:
                proc, base = console(repo if logbook == REPO else logbook)
                try:
                    ctx = await browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2,
                                                    color_scheme=theme)
                    page = await ctx.new_page()
                    await page.goto(f"{base}/#{screen}")
                    await page.wait_for_selector("main h1")
                    for selector, text in typed or ():
                        await page.fill(selector, text)
                    if typed:
                        # A selector, not a string predicate: the console's CSP refuses eval.
                        await page.wait_for_selector("#spec-line:has-text('spec')")
                    await page.wait_for_timeout(300)
                    who = await page.inner_text("#who")
                    if "?" in who:
                        sys.exit(f"render: {name}: the console's header has an unknown field: {who}")
                    jpg(await page.screenshot(type="png"), media / f"{name}.jpg", w)
                    await ctx.close()
                finally:
                    proc.kill()
                log(f"still {name}: {screen} over {logbook}, {theme}")
            await browser.close()


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python3 site/render.py <site dir>")
    site = pathlib.Path(sys.argv[1]).resolve()
    if not (site / "index.html").is_file():
        sys.exit(f"render: {site}/index.html not found; build the site directory first")
    asyncio.run(render(site))
    asyncio.run(stills(site))
    if os.environ.get("SHOTS"):
        asyncio.run(shots(site, pathlib.Path(os.environ["SHOTS"]).resolve()))


if __name__ == "__main__":
    main()
