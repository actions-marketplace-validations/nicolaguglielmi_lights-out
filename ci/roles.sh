#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-roles: the number of roles the repo states is the number it has. A
# role is a directory under roles/ with a role.env. Every "<number>
# agents", "<number> roles" or "<number> agent roles" in the living text —
# README.md, CONTRIBUTING.md, ROADMAP.md, docs/*.md but docs/PLAN.md (the
# owner's working document, Italian), board/index.html and each role's
# prompt.md — must say that number. ADRs are records of a decision at its
# date and are not read. A seventh role, or a fifth, fails here until the
# tagline changes with it: the count is a decision, not a drift.
set -eu
name=roles
. ci/lib.sh

[ -d roles ] || nogo "roles/ not found"

out=$(python3 - <<'PY' 2>&1
import glob, re, sys
roles = sorted(p.split("/")[1] for p in glob.glob("roles/*/role.env"))
if not roles:
    sys.exit("no roles/*/role.env")
words = "zero one two three four five six seven eight nine ten eleven twelve".split()
files = ["README.md", "CONTRIBUTING.md", "ROADMAP.md", "board/index.html"]
files += [f for f in sorted(glob.glob("docs/*.md")) if f != "docs/PLAN.md"]
files += sorted(glob.glob("roles/*/prompt.md"))
claim = re.compile(r"\b(" + "|".join(words) + r"|\d+) (?:agent roles|agents|roles)\b", re.I)
bad = []
for f in files:
    try:
        text = open(f, encoding="utf-8").read()
    except FileNotFoundError:
        continue
    for n, line in enumerate(text.splitlines(), 1):
        for m in claim.finditer(line):
            said = m.group(1).lower()
            said = int(said) if said.isdigit() else words.index(said)
            if said != len(roles):
                bad.append(f"{f}:{n}: says {m.group(0)!r}")
if bad:
    print(f"roles/ has {len(roles)}: {', '.join(roles)}")
    print("\n".join(bad))
    sys.exit(1)
PY
) || nogo "a stated role count disagrees with roles/" "$out"

go
