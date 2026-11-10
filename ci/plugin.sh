#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-plugin: proves docs/adr/0069 §1-§4 and §7 cold, no engine, no network,
# no Claude Code.
#   (a) the plugin's files hold the documented fields: the marketplace, the
#       manifest (kebab-case, not reserved, only documented keys, a version
#       equal to pyproject.toml's), hooks.json, .mcp.json and the two
#       SKILL.md; every ./ and ${CLAUDE_PLUGIN_ROOT}/ path they name exists.
#   (b) the scripts, run on scratch repositories with a PATH shim holding a
#       `lights-out-gates` that runs this checkout's package: pre-commit.sh
#       denies (exit 2, one stderr line) a staged weakening, passes a clean
#       change, is silent where HEAD has no .lights-out/workload.env or the
#       command is no `git commit`, and denies with the resolver's line when
#       the binary is missing; skill.sh prints the one `spec` line and exits
#       0 on a good and on a bad spec.
#   (c) both checks are shown to fail on planted input: a wrong version, a
#       reserved name, a path with `..`, a skill without
#       disable-model-invocation, a hooks.json with another timeout; a hook
#       that never denies, a hook that always denies, a skill.sh that never
#       says NO-GO. Each goes through the same functions the real checks use.
set -eu
name=plugin
. ci/lib.sh

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY
root=$(pwd)
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
PLUGIN=plugins/lights-out
PLANTS=$t/plants
# The scratch repositories get their own identity and no global config.
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null HOME="$t/home"
export GIT_AUTHOR_NAME=scratch GIT_AUTHOR_EMAIL=scratch@localhost.invalid
export GIT_COMMITTER_NAME=scratch GIT_COMMITTER_EMAIL=scratch@localhost.invalid
mkdir -p "$HOME"

# --- (a) the JSON and Markdown files ---

cat > "$t/check.py" <<'PY'
import json, os, re, sys

root = sys.argv[1]
flaws = []
RESERVED_PREFIX = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
RESERVED = ("claude", "anthropic", "anthropics", "claude-code", "claude-mods")
KEYS = set("""$schema name displayName version description author homepage repository license
keywords metadata icon documentationUrl supportUrl privacyPolicyUrl termsOfServiceUrl defaultEnabled
dependencies settings userConfig types channels skills commands agents hooks mcpServers lspServers
outputStyles workflows experimental""".split())
PLUGIN_VAR = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_./-]+)")


def flaw(text):
    flaws.append(text)


def load(rel):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        flaw(f"{rel} is missing")
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except ValueError as error:
        flaw(f"{rel} is not JSON: {error}")
        return None


def text_of(rel):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        flaw(f"{rel} is missing")
        return None
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def project_version():
    text = text_of("pyproject.toml") or ""
    inside = False
    for line in text.splitlines():
        if line.startswith("["):
            inside = line.strip() == "[project]"
        elif inside:
            m = re.match(r'version\s*=\s*"([^"]+)"', line)
            if m:
                return m.group(1)
    flaw("pyproject.toml has no [project] version")
    return None


# marketplace.json
market = load(".claude-plugin/marketplace.json")
entry = {}
plugin_dir = "plugins/lights-out"
if isinstance(market, dict):
    if market.get("name") != "lights-out":
        flaw("marketplace.json: name is not lights-out")
    owner = market.get("owner")
    if not (isinstance(owner, dict) and isinstance(owner.get("name"), str) and owner["name"].strip()):
        flaw("marketplace.json: owner.name is missing or empty")
    plugins = market.get("plugins")
    if not (isinstance(plugins, list) and len(plugins) == 1 and isinstance(plugins[0], dict)):
        flaw("marketplace.json: plugins is not a list of one entry")
    else:
        entry = plugins[0]
        if entry.get("name") != "lights-out":
            flaw("marketplace.json: the entry's name is not lights-out")
        if not (isinstance(entry.get("description"), str) and entry["description"].strip()):
            flaw("marketplace.json: the entry has no description")
        source = entry.get("source")
        if source != "./plugins/lights-out":
            flaw(f"marketplace.json: source is {source!r}, want ./plugins/lights-out")
        if isinstance(source, str):
            if not source.startswith("./"):
                flaw("marketplace.json: source does not start with ./")
            if ".." in source.split("/") or ".." in source:
                flaw("marketplace.json: source has a .. in it")
            elif not os.path.isdir(os.path.join(root, source)):
                flaw(f"marketplace.json: source {source} is not a directory")
            else:
                plugin_dir = source[2:]

# plugin.json
manifest = load(os.path.join(plugin_dir, ".claude-plugin/plugin.json"))
if isinstance(manifest, dict):
    name = manifest.get("name")
    if name != "lights-out":
        flaw(f"plugin.json: name is {name!r}, want lights-out")
    if isinstance(name, str):
        low = name.lower()
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
            flaw(f"plugin.json: name {name!r} is not kebab-case")
        if low in RESERVED or low.startswith(RESERVED_PREFIX):
            flaw(f"plugin.json: name {name!r} is reserved")
        if entry and entry.get("name") != name:
            flaw("plugin.json: name differs from the marketplace entry's")
    for key in sorted(set(manifest) - KEYS):
        flaw(f"plugin.json: {key} is not a documented top-level key")
    author = manifest.get("author")
    if not (isinstance(author, dict) and isinstance(author.get("name"), str) and author["name"].strip()):
        flaw("plugin.json: author.name is missing")
    home = manifest.get("homepage")
    if not (isinstance(home, str) and re.match(r"^https://[^/\s]+(/\S*)?$", home)):
        flaw("plugin.json: homepage is not an https URL")
    want = project_version()
    if want is not None and manifest.get("version") != want:
        flaw(f"plugin.json: version is {manifest.get('version')!r}, pyproject.toml has {want}")

# hooks.json
hooks = load(os.path.join(plugin_dir, "hooks/hooks.json"))
if isinstance(hooks, dict):
    pre = (hooks.get("hooks") or {}).get("PreToolUse") if isinstance(hooks.get("hooks"), dict) else None
    if pre is None:
        flaw("hooks.json: no top-level hooks.PreToolUse")
    else:
        bash = [e for e in pre if isinstance(e, dict) and e.get("matcher") == "Bash"]
        if len(bash) != 1 or len(pre) != 1:
            flaw("hooks.json: PreToolUse is not one entry with matcher Bash")
        else:
            inner = bash[0].get("hooks")
            if not (isinstance(inner, list) and len(inner) == 1 and isinstance(inner[0], dict)):
                flaw("hooks.json: the Bash entry has not one hook")
            else:
                hook = inner[0]
                if hook.get("type") != "command":
                    flaw("hooks.json: the hook's type is not command")
                if hook.get("timeout") != 30 or isinstance(hook.get("timeout"), bool):
                    flaw("hooks.json: the hook's timeout is not 30")
                if not re.search(r'"\$\{CLAUDE_PLUGIN_ROOT\}[^"]*scripts/pre-commit\.sh"', str(hook.get("command"))):
                    flaw('hooks.json: the command does not quote "${CLAUDE_PLUGIN_ROOT}/scripts/pre-commit.sh"')
elif hooks is not None:
    flaw("hooks.json is not an object")

# .mcp.json
mcp = load(os.path.join(plugin_dir, ".mcp.json"))
if isinstance(mcp, dict):
    servers = mcp.get("mcpServers")
    if not (isinstance(servers, dict) and len(servers) == 1):
        flaw(".mcp.json: mcpServers is not one server")
    else:
        (server,) = servers.values()
        want = ["${CLAUDE_PLUGIN_ROOT}/scripts/run.sh", "mcp", "--repo", "${CLAUDE_PROJECT_DIR}"]
        if not isinstance(server, dict) or server.get("command") != "sh" or server.get("args") != want:
            flaw(".mcp.json: the server is not sh with the args of ADR 0069 §7")

# the two skills
referenced = []
for skill in ("gates", "spec"):
    rel = os.path.join(plugin_dir, "skills", skill, "SKILL.md")
    text = text_of(rel)
    if text is None:
        continue
    lines = text.splitlines()
    front = {}
    if lines and lines[0].strip() == "---" and "---" in [l.strip() for l in lines[1:]]:
        end = [l.strip() for l in lines[1:]].index("---") + 1
        for l in lines[1:end]:
            m = re.match(r"^([A-Za-z-]+):\s*(.*)$", l)
            if m:
                front[m.group(1)] = m.group(2).strip()
        body = lines[end + 1:]
    else:
        flaw(f"{rel}: no YAML frontmatter between --- lines")
        body = lines
    if not front.get("description"):
        flaw(f"{rel}: no description")
    if front.get("disable-model-invocation") != "true":
        flaw(f"{rel}: disable-model-invocation is not true")
    if "allowed-tools" not in front:
        flaw(f"{rel}: no allowed-tools")
    shell = '!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/skill.sh" ' + skill + ' $ARGUMENTS`'
    if shell not in [l.strip() for l in body]:
        flaw(f"{rel}: no line {shell}")
    referenced.append(text)

# every path the files name exists
for rel in ("scripts/run.sh", "scripts/skill.sh", "scripts/pre-commit.sh"):
    if not os.path.isfile(os.path.join(root, plugin_dir, rel)):
        flaw(f"{plugin_dir}/{rel} is missing")


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)


for doc, base in ((manifest, plugin_dir), (hooks, plugin_dir), (mcp, plugin_dir)):
    for s in strings(doc):
        if s.startswith("./") and not os.path.exists(os.path.join(root, base, s[2:])):
            flaw(f"{base}: {s} does not exist")
        for rel in PLUGIN_VAR.findall(s):
            if not os.path.exists(os.path.join(root, plugin_dir, rel)):
                flaw(f"{plugin_dir}/{rel} does not exist")
for text in referenced:
    for rel in PLUGIN_VAR.findall(text):
        if not os.path.exists(os.path.join(root, plugin_dir, rel)):
            flaw(f"{plugin_dir}/{rel} does not exist")

print("\n".join(sorted(set(flaws))))
PY

# json_flaw ROOT: what is wrong with the plugin's files under ROOT, one per
# line, or nothing.
json_flaw() { python3 "$t/check.py" "$1"; }

# --- (b) the scripts ---

version_of() {  # the manifest's version, else pyproject's
  python3 - "$1" <<'PY'
import json, re, sys
try:
    with open(sys.argv[1] + "/plugins/lights-out/.claude-plugin/plugin.json", encoding="utf-8") as h:
        print(json.load(h)["version"])
except Exception:
    for line in open(sys.argv[1] + "/pyproject.toml", encoding="utf-8"):
        m = re.match(r'version\s*=\s*"([^"]+)"', line)
        if m:
            print(m.group(1))
            break
PY
}
version=$(version_of "$root")

# The shim a user's `uv tool install` would give: it answers `version` with the
# manifest's version and runs this checkout's package otherwise.
shim=$t/shim
mkdir -p "$shim"
cat > "$shim/lights-out-gates" <<SHIM
#!/bin/sh
if [ "\${1:-}" = version ]; then
  echo "lights-out-gates $version (the light tier: --light)"
  exit 0
fi
exec python3 -c 'import sys; sys.path.insert(0, "$root"); from core.__main__ import gates_main; sys.exit(gates_main())' "\$@"
SHIM
chmod +x "$shim/lights-out-gates"

# bare: a PATH with the tools a POSIX script needs and neither
# lights-out-gates nor uvx. Wrappers, not symlinks: some python3 are shims
# that look at how they were called.
bare=$t/bare
mkdir -p "$bare"
for tool in git sh python3 grep awk sed cat tr head tail cut dirname basename env mkdir rm mktemp sort wc expr tee uname cp mv ls true false test; do
  found=$(command -v "$tool" 2>/dev/null || :)
  case "$found" in
    /*) printf '#!/bin/sh\nexec %s "$@"\n' "$found" > "$bare/$tool"; chmod +x "$bare/$tool" ;;
  esac
done

# Scratch repositories: a calculator, its tests, and the contract of the M35
# hook-recipe run (ADR 0061 §8). One with the contract, one without.
CALC='def add(a, b):
    return a + b
'
TESTS='import unittest

import calc


class CalcTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(calc.add(1, 2), 3)
        self.assertEqual(calc.add(2, 2), 4)
'
make_repo() {  # DIR CONTRACT(yes|no)
  mkdir -p "$1/tests"
  git -C "$1" init -q -b main
  printf '%s\n' "$CALC" > "$1/calc.py"
  printf '%s\n' "$TESTS" > "$1/tests/test_calc.py"
  : > "$1/tests/__init__.py"
  if [ "$2" = yes ]; then
    mkdir -p "$1/.lights-out"
    printf '%s\n' 'WORKLOAD_TEST_PATHS=tests/test_*.py' 'TEST_CMD=python3 -m unittest discover -s tests' \
      'TOOLCHAIN_IMAGE=workbench' 'WORKLOAD_TEST_ROOT=' > "$1/.lights-out/workload.env"
  fi
  git -C "$1" add -A
  git -C "$1" -c commit.gpgsign=false commit -q -m base
}
weaken() {  # DIR: stage the removal of an assertion
  grep -v 'calc.add(2, 2)' "$1/tests/test_calc.py" > "$1/tests/test_calc.py.new"
  mv "$1/tests/test_calc.py.new" "$1/tests/test_calc.py"
  git -C "$1" add -A
}
clean_change() {  # DIR: stage a docstring in the module
  printf '"""A calculator."""\n%s\n' "$CALC" > "$1/calc.py"
  git -C "$1" add -A
}
make_repo "$t/r-weak" yes && weaken "$t/r-weak"
make_repo "$t/r-clean" yes && clean_change "$t/r-clean"
make_repo "$t/r-none" no && weaken "$t/r-none"

COMMIT='{"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}'
LS='{"tool_name":"Bash","tool_input":{"command":"ls"}}'

# hook PLUGIN REPO PATH STDIN: run PLUGIN's pre-commit.sh in REPO; its exit
# code in $hook_rc, stdout and stderr in $t/hook.out and $t/hook.err.
hook() {
  hook_rc=0
  (cd "$2" && printf '%s' "$4" | env PATH="$3" CLAUDE_PLUGIN_ROOT="$1" CLAUDE_PROJECT_DIR="$2" \
    sh "$1/scripts/pre-commit.sh") >"$t/hook.out" 2>"$t/hook.err" || hook_rc=$?
}
lines_of() { awk 'END{print NR}' "$1"; }

# hook_flaw PLUGIN: what is wrong with PLUGIN's pre-commit.sh, or nothing.
hook_flaw() {
  [ -f "$1/scripts/pre-commit.sh" ] || { printf '%s/scripts/pre-commit.sh is missing' "$1"; return; }
  with="$shim:$PATH"
  hook "$1" "$t/r-weak" "$with" "$COMMIT"
  [ "$hook_rc" -eq 2 ] || { printf 'a staged weakening: exit %s, want 2' "$hook_rc"; return; }
  [ "$(lines_of "$t/hook.err")" -eq 1 ] || { printf 'a staged weakening: stderr has %s lines, want 1' "$(lines_of "$t/hook.err")"; return; }
  case "$(cat "$t/hook.err")" in
    "NO-GO: gates-light"*) ;;
    *) printf 'a staged weakening: stderr is not the gates line: %s' "$(cat "$t/hook.err")"; return ;;
  esac
  [ ! -s "$t/hook.out" ] || { printf 'a staged weakening: stdout is not empty'; return; }
  hook "$1" "$t/r-clean" "$with" "$COMMIT"
  [ "$hook_rc" -eq 0 ] || { printf 'a clean staged change: exit %s, want 0' "$hook_rc"; return; }
  [ ! -s "$t/hook.out" ] || { printf 'a clean staged change: stdout is not empty'; return; }
  hook "$1" "$t/r-none" "$with" "$COMMIT"
  { [ "$hook_rc" -eq 0 ] && [ ! -s "$t/hook.out" ] && [ ! -s "$t/hook.err" ]; } \
    || { printf 'no contract at HEAD: not exit 0 and silent (exit %s)' "$hook_rc"; return; }
  hook "$1" "$t/r-weak" "$with" "$LS"
  { [ "$hook_rc" -eq 0 ] && [ ! -s "$t/hook.out" ] && [ ! -s "$t/hook.err" ]; } \
    || { printf 'a command that is no git commit: not exit 0 and silent (exit %s)' "$hook_rc"; return; }
  hook "$1" "$t/r-weak" "$bare" "$COMMIT"
  [ "$hook_rc" -eq 2 ] || { printf 'no binary: exit %s, want 2' "$hook_rc"; return; }
  [ "$(lines_of "$t/hook.err")" -eq 1 ] || { printf 'no binary: stderr has %s lines, want 1' "$(lines_of "$t/hook.err")"; return; }
  case "$(cat "$t/hook.err")" in
    "NO-GO: lights-out — lights-out-gates $version not found"*) ;;
    *) printf 'no binary: stderr is not the resolver line: %s' "$(cat "$t/hook.err")"; return ;;
  esac
  [ ! -s "$t/hook.out" ] || { printf 'no binary: stdout is not empty'; return; }
}

# skill_flaw PLUGIN: what is wrong with PLUGIN's skill.sh on a good and a
# bad spec, or nothing.
# shellcheck disable=SC2016 # the backticks are the spec's markdown
printf '%s\n' '# 0099 — a request' '' '## Problem' '' 'Something is wrong.' '' '## Acceptance criteria' '' \
  'Given a calculator with two numbers' 'When the caller adds them' 'Then the result is their sum' '' \
  '## Perimeter' '' '- `calc.py`' > "$t/good.md"
sed 's/Then the result is their sum/Then the calculator works correctly/' "$t/good.md" > "$t/bad.md"
skill_flaw() {
  [ -f "$1/scripts/skill.sh" ] || { printf '%s/scripts/skill.sh is missing' "$1"; return; }
  for case in good bad; do
    rc=0
    (cd "$t" && env PATH="$shim:$PATH" CLAUDE_PLUGIN_ROOT="$1" CLAUDE_PROJECT_DIR="$t" \
      sh "$1/scripts/skill.sh" spec "$t/$case.md") >"$t/skill.out" 2>"$t/skill.err" </dev/null || rc=$?
    [ "$rc" -eq 0 ] || { printf 'skill.sh spec on a %s spec: exit %s, want 0' "$case" "$rc"; return; }
    [ "$(lines_of "$t/skill.out")" -eq 1 ] || { printf 'skill.sh spec on a %s spec: %s stdout lines, want 1' "$case" "$(lines_of "$t/skill.out")"; return; }
    case "$case:$(cat "$t/skill.out")" in
      "good:GO: spec") ;;
      "bad:NO-GO: spec — "?*) ;;
      *) printf 'skill.sh spec on a %s spec printed: %s' "$case" "$(cat "$t/skill.out")"; return ;;
    esac
  done
}

# --- the real checks ---

flaw=$(json_flaw "$root" | head -n 1) || :
[ -z "$flaw" ] || nogo "$flaw" "$(json_flaw "$root")"
flaw=$(hook_flaw "$root/$PLUGIN")
[ -z "$flaw" ] || nogo "pre-commit.sh: $flaw" "$(cat "$t/hook.err" 2>/dev/null)"
flaw=$(skill_flaw "$root/$PLUGIN")
[ -z "$flaw" ] || nogo "skill.sh: $flaw" "$(cat "$t/skill.err" 2>/dev/null)"

# --- (c) each check must be able to fail ---

# plant NAME PYEXPR: a copy of the files under $t/plant-NAME with PYEXPR run on
# the JSON file named by $PLANT_FILE as `d` (a dict), or a sed script.
plant_tree() {  # NAME: a copy of what the JSON check reads
  rm -rf "$t/plant-$1"
  mkdir -p "$t/plant-$1"
  cp -R .claude-plugin plugins pyproject.toml "$t/plant-$1/"
}
mutate() {  # FILE PYEXPR: load FILE as `d`, run PYEXPR, write it back
  python3 - "$1" "$2" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as h:
    d = json.load(h)
exec(sys.argv[2])
with open(sys.argv[1], "w", encoding="utf-8") as h:
    json.dump(d, h)
PY
}
must_flag() {  # NAME WORD: the planted tree is rejected, and the flaw names WORD
  got=$(json_flaw "$t/plant-$1")
  case "$got" in
    *"$2"*) ;;
    *) nogo "the JSON check did not reject the planted '$1' (want a flaw naming '$2')" "got: ${got:-nothing}" ;;
  esac
}

plant_tree version
mutate "$t/plant-version/$PLUGIN/.claude-plugin/plugin.json" 'd["version"] = "0.0.0-planted"'
must_flag version "version"
plant_tree reserved
mutate "$t/plant-reserved/$PLUGIN/.claude-plugin/plugin.json" 'd["name"] = "Claude-Lights-Out"'
must_flag reserved "reserved"
plant_tree dotdot
mutate "$t/plant-dotdot/.claude-plugin/marketplace.json" 'd["plugins"][0]["source"] = "./plugins/../plugins/lights-out"'
must_flag dotdot ".."
plant_tree nokey
mutate "$t/plant-nokey/$PLUGIN/.claude-plugin/plugin.json" 'd["planted"] = 1'
must_flag nokey "planted"
plant_tree timeout
mutate "$t/plant-timeout/$PLUGIN/hooks/hooks.json" 'd["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 31'
must_flag timeout "timeout"
plant_tree skill
sed '/^disable-model-invocation:/d' "$t/plant-skill/$PLUGIN/skills/gates/SKILL.md" > "$t/skill.new"
cp "$t/skill.new" "$t/plant-skill/$PLUGIN/skills/gates/SKILL.md"
must_flag skill "disable-model-invocation"
plant_tree missing
rm "$t/plant-missing/$PLUGIN/scripts/run.sh"
must_flag missing "run.sh"

plant_scripts() {  # NAME: a copy of the plugin directory in $PLANTS/NAME
  rm -rf "${PLANTS:?}/$1"
  mkdir -p "$PLANTS/$1"
  cp -R "$PLUGIN/." "$PLANTS/$1/"
}
expect_hook_flaw() {  # NAME: hook_flaw rejects $PLANTS/NAME
  [ -n "$(hook_flaw "$PLANTS/$1")" ] || nogo "the hook check accepted the planted '$1' hook"
}
plant_scripts allow
printf 'cat >/dev/null\nexit 0\n' > "$PLANTS/allow/scripts/pre-commit.sh"
expect_hook_flaw allow
plant_scripts deny
printf 'cat >/dev/null\necho "NO-GO: gates-light — planted" >&2\nexit 2\n' > "$PLANTS/deny/scripts/pre-commit.sh"
expect_hook_flaw deny
plant_scripts always-go
printf 'echo "GO: spec"\nexit 0\n' > "$PLANTS/always-go/scripts/skill.sh"
[ -n "$(skill_flaw "$PLANTS/always-go")" ] || nogo "the skill check accepted a skill.sh that never says NO-GO"
plant_scripts exit-1
printf 'echo "NO-GO: spec — planted"\nexit 1\n' > "$PLANTS/exit-1/scripts/skill.sh"
[ -n "$(skill_flaw "$PLANTS/exit-1")" ] || nogo "the skill check accepted a skill.sh that exits 1"

go
