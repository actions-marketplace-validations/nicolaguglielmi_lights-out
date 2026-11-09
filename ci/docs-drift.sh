#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-docs-drift: every path, `./go` or `make` target and `NAME=` key a page
# of this repository cites exists (docs/adr/0054 §3), and the landing page
# names the wrapper's version and cites nothing that is gone (the
# amendment of 2026-11-09). It replaces
# ci/readme.sh, which read the README's `./go` words only. core/map.py reads
# the working tree and prints each citation that names nothing; MAP_EXCLUDE
# (the Makefile) leaves the plans and .claude/ alone, and ADRs and tickets
# are not pages. CONTAINER_CONNECTION is podman's own variable (ADR 0051),
# spelled nowhere in the code.
set -eu
name=docs-drift
. ci/lib.sh

: "${MAP_EXCLUDE:?MAP_EXCLUDE not set; run this via ./go ci}"
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT

out=$(make --no-print-directory help 2>&1) || nogo "make --no-print-directory help exited nonzero" "$out"
printf '%s\n' "$out" | awk '/^  [a-z]/{print $1}' > "$t/targets"

# The check must be able to fail: a page citing a missing path, an unknown
# target and an unknown key gives exactly those three findings.
probe="$t/probe"
mkdir -p "$probe/docs"
git -C "$probe" init -q
printf 'x\n' > "$probe/docs/real.sh"
# shellcheck disable=SC2016 # the backticks are the page's Markdown, not a command
printf '# Page\n\n`docs/real.sh`, `docs/gone.sh`, `./go no-such-target`, `NO_SUCH_KEY=1`.\n' > "$probe/docs/page.md"
found=$(python3 core/map.py drift --repo "$probe" --targets "$t/targets" 2>&1) \
  && nogo "a page citing a missing path, target and key passed"
[ "$found" = "docs/page.md:3: command ./go no-such-target names nothing
docs/page.md:3: key NO_SUCH_KEY names nothing
docs/page.md:3: path docs/gone.sh names nothing" ] || nogo "the probe page did not give its three findings" "$found"

found=$(python3 core/map.py drift --repo . --targets "$t/targets" --exclude "$MAP_EXCLUDE" \
  --known CONTAINER_CONNECTION 2>&1) \
  || nogo "$(printf '%s\n' "$found" | wc -l | tr -d ' ') citation(s) name nothing" "$found"

# The landing page (docs/adr/0054, amendment 2026-11-09): the release it
# names is the wrapper's version=, every link into this repository at main
# names a path that exists, every ./go <target> names a target. Prints one
# finding per line, nothing when the page is aligned.
site_drift() {  # REPO TARGETS
  python3 - "$1" "$2" <<'PY'
import os, re, sys
repo, targets = sys.argv[1], sys.argv[2]
page = "site/index.html"
version = None
with open(os.path.join(repo, "lights-out"), encoding="utf-8") as f:
    for line in f:
        m = re.match(r'version=([0-9]+\.[0-9]+\.[0-9]+)\s*$', line)
        if m:
            version = m.group(1)
            break
if not version:
    print("lights-out: no version=<major>.<minor>.<patch> line")
    sys.exit(0)
known = set(open(targets, encoding="utf-8").read().split())
link = re.compile(r'https://github\.com/nicolaguglielmi/lights-out/(?:blob|tree)/main/([^"\'#?<>\s]+)')
with open(os.path.join(repo, page), encoding="utf-8") as f:
    for n, line in enumerate(f, 1):
        for v in sorted(set(re.findall(r'(?<![\w.])v([0-9]+\.[0-9]+\.[0-9]+)\b', line))):
            if v != version:
                print(f"{page}:{n}: version v{v} is not the wrapper's {version}")
        for v in sorted(set(re.findall(r'ghcr\.io/nicolaguglielmi/[a-z0-9-]+:([0-9]+\.[0-9]+\.[0-9]+)\b', line))):
            if v != version:
                print(f"{page}:{n}: image tag {v} is not the wrapper's {version}")
        for path in sorted(set(link.findall(line))):
            if not os.path.exists(os.path.join(repo, path.rstrip("/"))):
                print(f"{page}:{n}: link to {path} names nothing")
        for target in sorted(set(re.findall(r'\./go ([a-z][a-z0-9-]*)', line))):
            if target not in known:
                print(f"{page}:{n}: command ./go {target} names nothing")
PY
}

# It must be able to fail: a planted page with a stale version, a dead
# link and an unknown target gives exactly those three findings, and none
# for what is right beside them.
sp="$t/site-probe"
mkdir -p "$sp/site" "$sp/docs"
printf '#!/bin/sh\nversion=1.2.3\n' > "$sp/lights-out"
printf 'x\n' > "$sp/docs/real.md"
cat > "$sp/site/index.html" <<'HTML'
<p>v1.2.3 and v1.2.2, ghcr.io/nicolaguglielmi/lights-out-gates:1.2.3</p>
<a href="https://github.com/nicolaguglielmi/lights-out/blob/main/docs/real.md#x">ok</a><a href="https://github.com/nicolaguglielmi/lights-out/tree/main/docs">ok</a>
<a href="https://github.com/nicolaguglielmi/lights-out/blob/main/docs/gone.md">gone</a> <code>./go help</code> <code>./go no-such-target</code>
HTML
found=$(site_drift "$sp" "$t/targets" 2>&1)
[ "$found" = "site/index.html:1: version v1.2.2 is not the wrapper's 1.2.3
site/index.html:3: link to docs/gone.md names nothing
site/index.html:3: command ./go no-such-target names nothing" ] \
  || nogo "the probe landing page did not give its three findings" "$found"

found=$(site_drift . "$t/targets" 2>&1)
[ -z "$found" ] || nogo "the landing page: $(printf '%s\n' "$found" | wc -l | tr -d ' ') finding(s)" "$found"
go
