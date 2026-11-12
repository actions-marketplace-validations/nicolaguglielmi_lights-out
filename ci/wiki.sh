#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-wiki: docs/adr/0077, engine-free and network-free; written from the
# ADR, not from the scripts.
#   render    package/wiki.py on this repository: exactly the pages of §2
#             (Home, Tutorial, Use-it-on-your-own-codebase, Reference,
#             Production, Architecture, Decisions, Releases, _Sidebar,
#             _Footer); each page from a document opens with a line naming
#             it at the tag, and the rest is the document with its link
#             targets blanked; outside fenced code no target is relative;
#             every wiki link names a rendered page and every link at the
#             tag a path that exists; Decisions has one row per ADR, each
#             linked; the sidebar links every page, the footer names the
#             tag; Releases names the version; two renderings are equal.
#   fixture   package/wiki.py on a small tree, written from §3: a page
#             link with its anchor, a link whose text spans lines, an
#             image and an HTML src (raw/), a file (blob/), a directory
#             (tree/), docs/adr/ (Decisions), an anchor and an absolute
#             URL kept, a fenced block copied as it is; Releases newest
#             first; a link to a missing path: exit 1 naming it, no OUT.
#   sync      package/sync-wiki.sh against local bare repositories: a dry
#             run leaves the remote unmoved; --push leaves exactly the
#             rendered pages on the remote's branch (a stale page gone),
#             committed by the owner's noreply identity with no trailer;
#             again with --push, exit 0 and the remote unmoved; a remote
#             that does not exist: exit 1 naming the Wiki tab's first page;
#             an https remote with no WIKI_TOKEN: exit 1 naming it, before any
#             clone.
#   workflow  (PyYAML) package.yml's job wiki needs release, has the
#             github.com guard and nothing else, holds exactly contents:
#             write, names no secret, renders with package/wiki.py, and
#             every step that pushes runs on a v* tag only, beside a dry
#             run on any other ref (§4).
# Each judge then runs on copies with one planted defect (the workflow as
# data; the scripts by an edit naming their real text: if the text moved,
# the edit is not applied and this says the check cannot fail).
# shellcheck disable=SC2016 # edits and expressions are text
set -eu
name=wiki
. ci/lib.sh

for t in git python3; do command -v "$t" >/dev/null 2>&1 || nogo "$t is not on PATH (./go ci runs in the workbench)"; done
python3 -c 'import yaml' 2>/dev/null || nogo "python3 cannot import yaml (PyYAML, workbench/uv.lock)"
for f in package/wiki.py package/sync-wiki.sh .github/workflows/package.yml lights-out; do
  [ -e "$f" ] || nogo "$f not found"
done

root=$(pwd -P)
w=$(mktemp -d)
trap 'rm -rf "$w"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_AUTHOR_NAME=ci GIT_AUTHOR_EMAIL=ci@lights-out.invalid \
  GIT_COMMITTER_NAME=ci GIT_COMMITTER_EMAIL=ci@lights-out.invalid
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE WIKI_TOKEN WIKI_REMOTE

# --- render and fixture -----------------------------------------------------------
cat > "$w/render.py" <<'PY'
import filecmp, os, re, shutil, subprocess, sys

script, root, w = sys.argv[1:]
GH = "https://github.com/nicolaguglielmi/lights-out"
WIKI = GH + "/wiki/"
DOCS = {"Home": "README.md", "Tutorial": "docs/tutorial.md", "Use-it-on-your-own-codebase": "docs/use-on-your-repo.md",
        "Reference": "docs/reference.md", "Production": "docs/production.md", "Architecture": "docs/ARCHITECTURE.md"}
PAGES = set(DOCS) | {"Decisions", "Releases", "_Sidebar", "_Footer"}
TARGET = re.compile(r"(?m)\]\(([^)\s]*)|\b(?:src|href)=\"([^\"]*)\"|^ {0,3}\[[^\]]+\]:[ \t]+(\S+)")


def run(cwd, out):
    return subprocess.run([sys.executable, "-I", script, out], cwd=cwd, capture_output=True, text=True)


def unfenced(t):
    out, f = [], False
    for line in t.split("\n"):
        if re.match(r"^\s*(```|~~~)", line):
            f = not f
        elif not f:
            out.append(line)
    return "\n".join(out)


def targets(t):
    return [next(g for g in m.groups() if g is not None) for m in TARGET.finditer(unfenced(t))]


def blank(t):
    t = re.sub(r"\]\([^)\s]*", "](", t)
    t = re.sub(r"\b(src|href)=\"[^\"]*\"", r'\1=""', t)
    return re.sub(r"(?m)^( {0,3}\[[^\]]+\]:[ \t]+)\S+", r"\1", t)


def repo_flaws():
    v = next(l.split("=", 1)[1].strip() for l in open(os.path.join(root, "lights-out")) if l.startswith("version="))
    tag = "v" + v
    out1, out2 = os.path.join(w, "r1"), os.path.join(w, "r2")
    for o in (out1, out2):
        shutil.rmtree(o, ignore_errors=True)
        r = run(root, o)
        if r.returncode != 0:
            yield "package/wiki.py on this repository exited %d: %s" % (r.returncode, r.stderr.strip()[:200])
            return
    got = {f[:-3] for f in os.listdir(out1) if f.endswith(".md")}
    if got != PAGES or len(os.listdir(out1)) != len(PAGES):
        yield "the pages are %s, want exactly %s (ADR 0077 §2)" % (sorted(os.listdir(out1)), sorted(PAGES))
        return
    cmp = filecmp.dircmp(out1, out2)
    if cmp.diff_files or cmp.left_only or cmp.right_only:
        yield "two renderings differ: %s" % (cmp.diff_files + cmp.left_only + cmp.right_only)
    text = {p: open(os.path.join(out1, p + ".md"), encoding="utf-8").read() for p in PAGES}
    for p, src in DOCS.items():
        first, _, rest = text[p].partition("\n")
        if not first.startswith("> Generated from [`%s`](%s/blob/%s/%s)" % (src, GH, tag, src)):
            yield "%s does not open with the line naming %s at %s (ADR 0077 §3)" % (p, src, tag)
        if blank(rest.lstrip("\n")) != blank(open(os.path.join(root, src), encoding="utf-8").read()):
            yield "%s is not %s with its link targets blanked (ADR 0077 §3)" % (p, src)
    for p, t in text.items():
        for x in targets(t):
            if not re.match(r"(https?:|mailto:|#)", x):
                yield "%s keeps the relative link %s (ADR 0077 §3)" % (p, x)
            elif x.startswith(WIKI):
                if x[len(WIKI):].split("#")[0] not in PAGES:
                    yield "%s links the wiki page %s, which is not rendered" % (p, x)
            else:
                m = re.match(re.escape(GH) + r"/(?:blob|raw|tree)/" + re.escape(tag) + r"/([^#]+)", x)
                if m and not os.path.exists(os.path.join(root, m.group(1).rstrip("/"))):
                    yield "%s links %s, and %s does not exist at the tag" % (p, x, m.group(1))
    adrs = sorted(f for f in os.listdir(os.path.join(root, "docs/adr")) if re.match(r"^\d{4}-.*\.md$", f))
    rows = [l for l in text["Decisions"].split("\n") if re.match(r"^\| \d{4} \|", l)]
    if len(rows) != len(adrs) or any("%s/blob/%s/docs/adr/%s)" % (GH, tag, f) not in text["Decisions"] for f in adrs):
        yield "Decisions has %d rows for %d ADRs, or one is not linked at %s (ADR 0077 §2)" % (len(rows), len(adrs), tag)
    for p in PAGES - {"_Sidebar", "_Footer"}:
        if "(%s%s)" % (WIKI, p) not in text["_Sidebar"]:
            yield "the sidebar does not link %s" % p
    if tag not in text["_Footer"] or "Generated" not in text["_Footer"]:
        yield "the footer does not say it is generated at %s" % tag
    if "**%s**" % v not in text["Releases"]:
        yield "Releases does not name the version %s" % v


FIX = {
    "lights-out": "#!/bin/sh\nversion=7.8.9\n",
    "README.md": "# Fixture\n\n<img src=\"docs/assets/a.png\" alt=\"a\">\n",
    "docs/tutorial.md": "\n".join([
        "# T",
        "[home](../README.md#install) and [the",
        "reference](reference.md), ![pic](assets/a.png), [script](../ci/x.sh),",
        "[ci](../ci/), [why](adr/), [here](#here), [out](https://example.com/x.md).",
        "```",
        "[fenced](nowhere.md)",
        "```",
        "[after](production.md)", ""]),
    "docs/use-on-your-repo.md": "# U\n", "docs/reference.md": "# R\n", "docs/production.md": "# P\n",
    "docs/ARCHITECTURE.md": "# A\n", "docs/adr/0001-one.md": "# ADR 0001 — One\n\n- Status: accepted\n",
    "docs/assets/a.png": "png", "ci/x.sh": "true\n",
    "docs/releases/v7.8.9.md": "OLDER-PROSE\n", "docs/releases/v7.10.0.md": "NEWER-PROSE\n",
}
WANT = [
    ("Tutorial", "[home](%sHome#install)" % WIKI),
    ("Tutorial", "reference](%sReference)" % WIKI),
    ("Tutorial", "![pic](%s/raw/v7.8.9/docs/assets/a.png)" % GH),
    ("Tutorial", "[script](%s/blob/v7.8.9/ci/x.sh)" % GH),
    ("Tutorial", "[ci](%s/tree/v7.8.9/ci)" % GH),
    ("Tutorial", "[why](%sDecisions)" % WIKI),
    ("Tutorial", "[here](#here)"),
    ("Tutorial", "[out](https://example.com/x.md)"),
    ("Tutorial", "```\n[fenced](nowhere.md)\n```"),
    ("Tutorial", "[after](%sProduction)" % WIKI),
    ("Home", 'src="%s/raw/v7.8.9/docs/assets/a.png"' % GH),
    ("Decisions", "| 0001 | [One](%s/blob/v7.8.9/docs/adr/0001-one.md) | accepted |" % GH),
]


def fixture_flaws():
    fx = os.path.join(w, "fx")
    shutil.rmtree(fx, ignore_errors=True)
    for p, t in FIX.items():
        os.makedirs(os.path.dirname(os.path.join(fx, p)), exist_ok=True)
        open(os.path.join(fx, p), "w").write(t)
    out = os.path.join(w, "fxout")
    shutil.rmtree(out, ignore_errors=True)
    r = run(fx, out)
    if r.returncode != 0:
        yield "package/wiki.py on the fixture exited %d: %s" % (r.returncode, r.stderr.strip()[:200])
        return
    for page, want in WANT:
        t = open(os.path.join(out, page + ".md"), encoding="utf-8").read() if os.path.exists(os.path.join(out, page + ".md")) else ""
        if want not in t:
            yield "fixture: %s lacks %r (ADR 0077 §3)" % (page, want)
    rel = open(os.path.join(out, "Releases.md"), encoding="utf-8").read() if os.path.exists(os.path.join(out, "Releases.md")) else ""
    if not (0 <= rel.find("NEWER-PROSE") < rel.find("OLDER-PROSE")):
        yield "fixture: Releases does not hold v7.10.0's prose before v7.8.9's (ADR 0077 §2)"
    open(os.path.join(fx, "docs/production.md"), "w").write("# P\n\n[gone](missing.md)\n")
    shutil.rmtree(out, ignore_errors=True)
    r = run(fx, out)
    if r.returncode == 0 or "missing.md" not in r.stderr or os.path.exists(out):
        yield "fixture: a link to a missing path was not refused with exit 1, its name and no OUT (ADR 0077 §3)"


print("\n".join(list(repo_flaws()) + list(fixture_flaws())))
PY
render_flaws() { python3 -I "$w/render.py" "$1" "$root" "$w" 2>&1 || echo "the render judge itself failed"; }

# --- sync -------------------------------------------------------------------------
# sync_flaws SCRIPT: package/sync-wiki.sh's contract, one line per flaw.
sync_flaws() {
  s=$1 r=$w/wiki.git
  rm -rf "$w"/wiki.git "$w"/seed "$w"/pages "$w"/clone*
  git init -q --bare -b master "$r"
  git clone -q "$r" "$w/seed" 2>/dev/null
  echo old > "$w/seed/Home.md" && echo stale > "$w/seed/Stale.md"
  git -C "$w/seed" add -A && git -C "$w/seed" commit -q -m "the first page" && git -C "$w/seed" push -q origin HEAD:master
  mkdir -p "$w/pages" && echo new > "$w/pages/Home.md" && echo side > "$w/pages/_Sidebar.md"
  before=$(git -C "$r" rev-parse master)
  WIKI_REMOTE=$r sh "$s" "$w/pages" "$w/clone0" >"$w/o" 2>"$w/e" || { echo "a dry run exited non-zero: $(head -n 3 "$w/e")"; return 0; }
  [ "$(git -C "$r" rev-parse master)" = "$before" ] || echo "a dry run changed the remote"
  WIKI_REMOTE=$r sh "$s" "$w/pages" "$w/clone1" --push >"$w/o" 2>"$w/e" || echo "--push exited non-zero: $(head -n 3 "$w/e")"
  [ "$(git -C "$r" ls-tree --name-only master | tr '\n' ' ')" = "Home.md _Sidebar.md " ] && [ "$(git -C "$r" show master:Home.md 2>/dev/null)" = new ] \
    || echo "after --push the remote's master does not hold exactly the rendered pages: $(git -C "$r" ls-tree --name-only master | tr '\n' ' ')"
  au=$(git -C "$r" log -1 --format='%an <%ae>|%cn <%ce>' master 2>/dev/null || true)
  o="Nicola <45848139+nicolaguglielmi@users.noreply.github.com>"
  [ "$au" = "$o|$o" ] || echo "the commit's author and committer are '$au', not the owner's noreply identity"
  ! git -C "$r" log -1 --format=%B master 2>/dev/null | grep -qi 'co-authored-by' || echo "the commit carries a co-author trailer"
  after=$(git -C "$r" rev-parse master)
  WIKI_REMOTE=$r sh "$s" "$w/pages" "$w/clone2" --push >"$w/o" 2>"$w/e" || echo "--push again, on the same pages, exited non-zero: $(head -n 3 "$w/e")"
  [ "$(git -C "$r" rev-parse master)" = "$after" ] || echo "--push again moved the remote's master"
  if WIKI_REMOTE=$w/none.git sh "$s" "$w/pages" "$w/clone3" --push >"$w/o" 2>"$w/e"; then
    echo "a wiki with no repository was not refused"
  elif ! grep -q "Wiki tab" "$w/e"; then echo "a wiki with no repository: the refusal does not name the Wiki tab's first page"; fi
  if WIKI_REMOTE=https://example.invalid/x.wiki.git sh "$s" "$w/pages" "$w/clone4" --push >"$w/o" 2>"$w/e"; then
    echo "an https remote with no WIKI_TOKEN was not refused"
  elif ! grep -q "needs WIKI_TOKEN" "$w/e" || grep -q "cannot clone" "$w/e"; then echo "an https remote with no WIKI_TOKEN: not refused before the clone, naming WIKI_TOKEN"; fi
  :
}

# --- workflow ---------------------------------------------------------------------
cat > "$w/wf.py" <<'PY'
import copy, json, re, sys, yaml

path, mode = sys.argv[1], sys.argv[2]
d0 = yaml.safe_load(open(path))
S = "github.server_url == 'https://github.com'"
TAG = "startsWith(github.ref, 'refs/tags/v')"


def cond(x):
    return re.sub(r"\s+", " ", re.sub(r"^\$\{\{(.*)\}\}$", r"\1", str(x or "").strip()).strip())


def live(r):
    # what a run executes: the text an echo prints (a dry run shows commands) is not run
    return re.sub(r"""\becho\s+("(?:[^"\\]|\\.)*"|'[^']*')""", "echo", str(r or ""))


def flaws(d):
    j = (d.get("jobs") or {}).get("wiki")
    if not isinstance(j, dict):
        yield "package.yml has no job wiki (ADR 0077 §4)"
        return
    n = j.get("needs") or []
    if "release" not in ({n} if isinstance(n, str) else set(n)):
        yield "job wiki does not need release (ADR 0077 §4)"
    if cond(j.get("if")) != S:
        yield "job wiki: if: %r is not the github.com guard alone (ADR 0077 §4)" % cond(j.get("if"))
    if j.get("permissions") != {"contents": "write"}:
        yield "job wiki holds %s, want exactly contents: write (ADR 0077 §4)" % j.get("permissions")
    if "secrets." in json.dumps(j):
        yield "job wiki names a secret: it pushes with the job's GITHUB_TOKEN (ADR 0077 §4)"
    steps = j.get("steps") or []
    if not any("package/wiki.py" in live(s.get("run")) and not cond(s.get("if")) for s in steps):
        yield "job wiki does not render with package/wiki.py on every ref (ADR 0077 §4)"
    pushes = [s for s in steps if re.search(r"--push\b|\bgit\b[^\n]*\bpush\b", live(s.get("run")))]
    if not any("package/sync-wiki.sh" in live(s.get("run")) for s in pushes):
        yield "job wiki does not push with package/sync-wiki.sh --push (ADR 0077 §3)"
    for s in pushes:
        c = cond(s.get("if"))
        if not (TAG in c and "!" + TAG not in c and "workflow_dispatch" not in c):
            yield "job wiki: the step %r pushes outside a v* tag (ADR 0077 §4)" % s.get("name")
    if not any(cond(s.get("if")) == "!" + TAG for s in steps):
        yield "job wiki has no dry-run step for any other ref (ADR 0077 §4)"


def J(d):
    return d["jobs"]["wiki"]


def push(d):
    return next(s for s in J(d)["steps"] if "--push" in live(s.get("run")))


CASES = [
    ("no wiki job", lambda d: d["jobs"].pop("wiki"), "no job wiki"),
    ("wiki does not need release", lambda d: J(d).update(needs="publish"), "does not need release"),
    ("wiki runs only on main", lambda d: J(d).update({"if": S + " || github.ref == 'refs/heads/main'"}), "github.com guard alone"),
    ("wiki holds packages: write", lambda d: J(d)["permissions"].update(packages="write"), "want exactly contents: write"),
    ("wiki reads a secret", lambda d: push(d)["env"].update(WIKI_TOKEN="${{ secrets.WIKI_TOKEN }}"), "names a secret"),
    ("wiki pushes on a dispatch", lambda d: push(d).pop("if"), "pushes outside a v* tag"),
    ("wiki pushes on other refs", lambda d: push(d).update({"if": "!" + TAG}), "pushes outside a v* tag"),
    ("the dry run pushes for real", lambda d: next(s for s in J(d)["steps"] if cond(s.get("if")) == "!" + TAG).update(run="git push origin HEAD"), "pushes outside a v* tag"),
    ("no dry run", lambda d: J(d).update(steps=[s for s in J(d)["steps"] if cond(s.get("if")) != "!" + TAG]), "no dry-run step"),
    ("no rendering", lambda d: J(d).update(steps=[s for s in J(d)["steps"] if "package/wiki.py" not in live(s.get("run"))]), "does not render"),
]
if mode == "check":
    print("\n".join(flaws(d0)))
else:
    for desc, mutate, want in CASES:
        d = copy.deepcopy(d0)
        try:
            mutate(d)
        except (KeyError, StopIteration) as e:
            print("it cannot fail: %s (the edit found nothing to change: %r)" % (desc, e))
            break
        got = "\n".join(flaws(d))
        if want not in got:
            print("it cannot fail: %s -> [%s]" % (desc, got[:200]))
            break
PY

judge() { [ -z "$2" ] || nogo "$1: $(printf '%s\n' "$2" | head -n 1)" "$2"; }
judge render "$(render_flaws "$root/package/wiki.py")"
judge sync "$(sync_flaws "$root/package/sync-wiki.sh")"
judge workflow "$(python3 -I "$w/wf.py" .github/workflows/package.yml check)"

# --- the checks must be able to fail -------------------------------------------------
out=$(python3 -I "$w/wf.py" .github/workflows/package.yml prove)
[ -z "$out" ] || nogo "workflow: $out"
# planted FILE JUDGE WANT FROM TO: JUDGE on a copy of FILE with FROM replaced by TO must name WANT.
planted() {
  ext=${1##*.}
  cp "$1" "$w/planted.$ext"
  python3 -I - "$w/planted.$ext" "$4" "$5" <<'PY' || nogo "$(basename "$1"): '$4' is not in the script, so the check cannot fail on it"
import sys
p, a, b = sys.argv[1:]
s = open(p).read()
sys.exit(1) if a not in s else open(p, "w").write(s.replace(a, b, 1))
PY
  got=$($2 "$w/planted.$ext")
  case "$got" in *"$3"*) ;; *) nogo "$(basename "$1"): it cannot fail on '$4' -> '$5': [$(printf '%s' "$got" | head -n 1)]" ;; esac
}
planted package/wiki.py render_flaws "keeps the relative link" 'return WIKI + PAGE_OF[p] + anchor' 'return t'
planted package/wiki.py render_flaws "want exactly" '("Production", "docs/production.md"),' ''
planted package/wiki.py render_flaws "missing path was not refused" 'if p.startswith("..") or not os.path.exists(p):' 'if False:'
planted package/wiki.py render_flaws "nowhere.md" 'if FENCE.match(line) and not fenced:' 'if False:'
planted package/wiki.py render_flaws "v7.10.0's prose before" 'key=key, reverse=True' 'key=key'
planted package/wiki.py render_flaws "Decisions has" 'rows.append(' '0 and rows.append('
planted package/wiki.py render_flaws "with its link targets blanked" 'links(open(src, encoding="utf-8").read(), src, tag)' 'links(open(src, encoding="utf-8").read().replace("\n\n", "\n", 1), src, tag)'
planted package/wiki.py render_flaws "raw/v7.8.9/docs/assets" 'kind = "raw" if image' 'kind = "blob" if image'
planted package/sync-wiki.sh sync_flaws "a dry run changed the remote" 'if [ "$push" = 1 ]; then' 'if true; then'
planted package/sync-wiki.sh sync_flaws "exactly the rendered pages" 'find "$dir" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +' ':'
planted package/sync-wiki.sh sync_flaws "not the owner's noreply identity" '45848139+nicolaguglielmi@users.noreply.github.com' 'someone@example.com'
planted package/sync-wiki.sh sync_flaws "no repository was not refused" 'exit 1 # no wiki repository' 'exit 0 # no wiki repository'
planted package/sync-wiki.sh sync_flaws "WIKI_TOKEN" '[ -n "${WIKI_TOKEN:-}" ] ||' 'true ||'

go_with "the wiki's pages, links, sync and job as ADR 0077 says, each check shown to fail"
