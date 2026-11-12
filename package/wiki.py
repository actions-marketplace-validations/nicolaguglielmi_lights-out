#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# package/wiki.py OUT (docs/adr/0077): the GitHub wiki, rendered from the
# repository into the directory OUT, one .md file per page plus _Sidebar.md
# and _Footer.md. Run from the lights-out repository's root; the version is
# the wrapper's version=, and every link into the repository points at the
# tag v<version>. A relative link to a path that does not exist: exit 1,
# naming it, and OUT is left untouched. Standard library only.
import os
import re
import sys

REPO = "nicolaguglielmi/lights-out"
GH = "https://github.com/" + REPO
WIKI = GH + "/wiki/"
# docs/adr/0077 §2: the pages from a document, in the sidebar's order.
DOCS = [
    ("Home", "README.md"),
    ("Tutorial", "docs/tutorial.md"),
    ("Use-it-on-your-own-codebase", "docs/use-on-your-repo.md"),
    ("Reference", "docs/reference.md"),
    ("Production", "docs/production.md"),
    ("Architecture", "docs/ARCHITECTURE.md"),
]
PAGE_OF = {src: page for page, src in DOCS}
PAGE_OF["docs/adr"] = "Decisions"
IMAGE = re.compile(r"\.(png|jpe?g|gif|svg|webp)$", re.I)
ABSOLUTE = re.compile(r"^(https?:|mailto:)", re.I)
FENCE = re.compile(r"^\s*(```|~~~)")
# a markdown link or image target, an HTML src/href, a reference definition
INLINE = re.compile(r"(!?)(\[(?:[^\[\]]|\[[^\[\]]*\])*\]\()(<[^>]*>|[^)\s]*)((?:\s+\"[^\"]*\")?\))")
ATTR = re.compile(r"\b(src|href)=\"([^\"]*)\"")
REFDEF = re.compile(r"(?m)^( {0,3}\[[^\]]+\]:[ \t]+)(\S+)(.*)$")


class Broken(Exception):
    pass


def version():
    for line in open("lights-out"):
        if line.startswith("version="):
            return line.split("=", 1)[1].strip()
    raise Broken("the wrapper lights-out has no version= line")


def target(t, src, tag, image):
    """docs/adr/0077 §3: where a link target of the document src points in the wiki."""
    bare = t[1:-1] if t.startswith("<") and t.endswith(">") else t
    if not bare or bare.startswith("#") or ABSOLUTE.match(bare):
        return t
    path, _, anchor = bare.partition("#")
    anchor = "#" + anchor if anchor else ""
    p = os.path.normpath(os.path.join(os.path.dirname(src), path))
    if p.startswith("..") or not os.path.exists(p):
        raise Broken("%s links %s, which does not exist" % (src, t))
    if p in PAGE_OF:
        return WIKI + PAGE_OF[p] + anchor
    if os.path.isdir(p):
        return "%s/tree/%s/%s%s" % (GH, tag, p, anchor)
    kind = "raw" if image or IMAGE.search(p) and not anchor else "blob"
    return "%s/%s/%s/%s%s" % (GH, kind, tag, p, anchor)


def chunks(text):
    """The text cut into (fenced, chunk) runs of whole lines: a link's text may span lines, a fence's never matters."""
    out, cur, fenced = [], [], False
    for line in text.split("\n"):
        if FENCE.match(line) and not fenced:
            out.append((False, cur))
            cur, fenced = [line], True
        elif FENCE.match(line) and fenced:
            out.append((True, cur + [line]))
            cur, fenced = [], False
        else:
            cur.append(line)
    out.append((fenced, cur))
    return [(f, "\n".join(c)) for f, c in out if c]


def links(text, src, tag):
    out = []
    for fenced, c in chunks(text):
        if not fenced:
            c = INLINE.sub(lambda m: m.group(1) + m.group(2) + target(m.group(3), src, tag, m.group(1) == "!") + m.group(4), c)
            c = ATTR.sub(lambda m: '%s="%s"' % (m.group(1), target(m.group(2), src, tag, m.group(1) == "src")), c)
            c = REFDEF.sub(lambda m: m.group(1) + target(m.group(2), src, tag, False) + m.group(3), c)
        out.append(c)
    return "\n".join(out)


def note(src, tag):
    return "> Generated from [`%s`](%s/blob/%s/%s) at %s. Edit that file in the repository, not this page.\n\n" % (src, GH, tag, src, tag)


def decisions(tag):
    rows = []
    for f in sorted(os.listdir("docs/adr")):
        m = re.match(r"^(\d{4})-.*\.md$", f)
        if not m:
            continue
        lines = open(os.path.join("docs/adr", f), encoding="utf-8").read().split("\n")
        title = next((x[2:] for x in lines if x.startswith("# ")), f)
        title = re.sub(r"^ADR\s+\d+\s*[—:-]\s*", "", title).replace("|", "\\|")
        status = next((x.split(":", 1)[1].split() for x in lines if x.startswith("- Status:")), [])
        word = re.sub(r"[^A-Za-z-]", "", status[0]) if status else ""
        rows.append("| %s | [%s](%s/blob/%s/docs/adr/%s) | %s |" % (m.group(1), title, GH, tag, f, word))
    head = "# Decisions\n\n" + note("docs/adr/", tag)
    head += "One row per architecture decision record, oldest first. Each one says what was decided, the alternatives it rejected and why.\n\n"
    return head + "| ADR | Decision | Status |\n|---|---|---|\n" + "\n".join(rows) + "\n"


def releases(v, tag):
    def key(f):
        return tuple(int(x) for x in re.findall(r"\d+", f))
    notes = sorted((f for f in os.listdir("docs/releases") if re.match(r"^v\d+\.\d+\.\d+\.md$", f)), key=key, reverse=True) if os.path.isdir("docs/releases") else []
    out = "# Releases\n\n" + note("lights-out", tag)
    out += "The current release is **%s**: [its release on GitHub](%s/releases/tag/%s), with the images' digests and how to verify their signatures. [Every release](%s/releases).\n" % (v, GH, tag, GH)
    for f in notes:
        out += "\n## %s\n\n" % f[:-3] + links(open("docs/releases/" + f, encoding="utf-8").read().rstrip("\n"), "docs/releases/" + f, tag) + "\n"
    return out


def render():
    v = version()
    tag = "v" + v
    pages = {}
    for page, src in DOCS:
        pages[page] = note(src, tag) + links(open(src, encoding="utf-8").read(), src, tag)
    pages["Decisions"] = decisions(tag)
    pages["Releases"] = releases(v, tag)
    order = [p for p, _ in DOCS] + ["Decisions", "Releases"]
    pages["_Sidebar"] = "**lights-out %s**\n\n" % v + "".join("- [%s](%s%s)\n" % (p.replace("-", " "), WIKI, p) for p in order)
    pages["_Footer"] = "Generated from [%s](%s) at [%s](%s/tree/%s) by `package/wiki.py` (docs/adr/0077). Every release replaces every page: edit the source file in the repository, not the wiki.\n" % (REPO, GH, tag, GH, tag)
    return pages


def main():
    if len(sys.argv) != 2:
        print("usage: package/wiki.py OUT", file=sys.stderr)
        return 2
    try:
        pages = render()
    except (Broken, OSError) as e:
        print("wiki: %s" % e, file=sys.stderr)
        return 1
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for page, text in pages.items():
        with open(os.path.join(out, page + ".md"), "w", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
