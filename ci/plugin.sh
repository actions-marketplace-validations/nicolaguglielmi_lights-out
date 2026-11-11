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
#   (d) the amendment of 2026-11-11 (§2-§6, §8, §9): the Codex marketplace,
#       manifest (only the documented keys, no hooks key or hooks/ directory,
#       the version), three skills with `allow_implicit_invocation: false`;
#       the Gemini manifest (name equal to the directory), the two TOML
#       commands (tomllib), the BeforeTool hooks.json, scripts byte-equal to
#       the Claude plugin's; Codex's hook.sh on scratch repositories (the
#       recipe's entry, a second install changes nothing, foreign hooks
#       survive, remove restores, bad JSON and no repository refused, one
#       stdout line) and its command run as Codex runs it; the Gemini hook
#       with Gemini's stdin shape. Planted: a one-byte copy, a Codex hooks
#       key and directory, an implicit skill, a Gemini timeout of 30, a
#       wrong name and versions, {{args}} in gates, a hook.sh that appends
#       twice, drops a hook, prints two lines or writes nothing.
set -eu
name=plugin
. ci/lib.sh

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY
root=$(pwd)
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
PLUGIN=plugins/lights-out
CODEX=plugins/lights-out-codex
GEMINI=plugins/lights-out-gemini
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

# The Codex plugin and the Gemini extension (docs/adr/0069, amendment
# 2026-11-11 §2-§6, §8): the files, not the scripts.
cat > "$t/ext.py" <<'PY'
import json, os, re, sys

root = sys.argv[1]
flaws = []
CODEX = "plugins/lights-out-codex"
GEMINI = "plugins/lights-out-gemini"
CODEX_KEYS = set("name version description author homepage repository license keywords skills".split())
CODEX_REQUIRED = ("name", "version", "description", "skills")
GATES_CMD = "!{lights-out-gates --light STAGED=1 2>&1 || true}"
SPEC_CMD = "!{lights-out-gates spec {{args}} 2>&1 || true}"
GEMINI_HOOK = 'sh "${extensionPath}/scripts/pre-commit.sh"'


def flaw(text):
    flaws.append(text)


def path(rel):
    return os.path.join(root, rel)


def load(rel):
    if not os.path.isfile(path(rel)):
        flaw(f"{rel} is missing")
        return None
    try:
        with open(path(rel), encoding="utf-8") as handle:
            return json.load(handle)
    except ValueError as error:
        flaw(f"{rel} is not JSON: {error}")
        return None


def text_of(rel):
    if not os.path.isfile(path(rel)):
        flaw(f"{rel} is missing")
        return None
    with open(path(rel), encoding="utf-8") as handle:
        return handle.read()


def project_version():
    inside = False
    for line in (text_of("pyproject.toml") or "").splitlines():
        if line.startswith("["):
            inside = line.strip() == "[project]"
        elif inside:
            m = re.match(r'version\s*=\s*"([^"]+)"', line)
            if m:
                return m.group(1)
    flaw("pyproject.toml has no [project] version")
    return None


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


want = project_version()

# --- Codex: the marketplace ---
codex_dir = CODEX
market = load(".agents/plugins/marketplace.json")
if isinstance(market, dict):
    if market.get("name") != "lights-out":
        flaw("codex marketplace.json: name is not lights-out")
    plugins = market.get("plugins")
    if not (isinstance(plugins, list) and len(plugins) == 1 and isinstance(plugins[0], dict)):
        flaw("codex marketplace.json: plugins is not a list of one entry")
    else:
        entry = plugins[0]
        if entry.get("name") != "lights-out":
            flaw("codex marketplace.json: the entry's name is not lights-out")
        source = entry.get("source")
        if not (isinstance(source, dict) and source.get("source") == "local" and isinstance(source.get("path"), str)):
            flaw('codex marketplace.json: source is not {"source": "local", "path": "./..."}')
        else:
            p = source["path"]
            if not p.startswith("./"):
                flaw("codex marketplace.json: the source path does not start with ./")
            elif ".." in p.split("/"):
                flaw("codex marketplace.json: the source path has a .. in it")
            elif not os.path.isdir(path(p[2:])):
                flaw(f"codex marketplace.json: the source path {p} is not a directory")
            else:
                codex_dir = p[2:].rstrip("/")
            if p != "./" + CODEX:
                flaw(f"codex marketplace.json: the source path is {p}, want ./{CODEX}")
        if not isinstance(entry.get("policy"), dict):
            flaw("codex marketplace.json: the entry has no policy object")
        if not nonempty(entry.get("category")):
            flaw("codex marketplace.json: the entry has no category")
elif market is not None:
    flaw("codex marketplace.json is not an object")

# --- Codex: the manifest ---
manifest = load(os.path.join(codex_dir, ".codex-plugin/plugin.json"))
if isinstance(manifest, dict):
    if manifest.get("name") != "lights-out":
        flaw(f"codex plugin.json: name is {manifest.get('name')!r}, want lights-out")
    if "hooks" in manifest:
        flaw("codex plugin.json: has a hooks key (a plugin with hooks is not eligible for the directory)")
    for key in sorted(set(manifest) - CODEX_KEYS - {"hooks"}):
        flaw(f"codex plugin.json: {key} is not one of the documented keys")
    for key in CODEX_REQUIRED:
        if key not in manifest:
            flaw(f"codex plugin.json: no {key}")
    if want is not None and manifest.get("version") != want:
        flaw(f"codex plugin.json: version is {manifest.get('version')!r}, pyproject.toml has {want}")
    if manifest.get("skills") != "./skills/":
        flaw("codex plugin.json: skills is not ./skills/")

for dirpath, dirnames, _ in os.walk(path(codex_dir)):
    if "hooks" in dirnames:
        flaw(f"codex plugin: a hooks/ directory under {os.path.relpath(dirpath, root)}")

# --- Codex: the three skills ---
SKILL_WORDS = {
    "gates": ("lights-out-gates --light", "STAGED=1", "uv tool install lights-out-gates"),
    "spec": ("lights-out-gates spec", "uv tool install lights-out-gates"),
    "hook": (),
}
for skill, words in SKILL_WORDS.items():
    rel = os.path.join(codex_dir, "skills", skill, "SKILL.md")
    text = text_of(rel)
    if text is not None:
        lines = text.splitlines()
        front = {}
        if lines and lines[0].strip() == "---" and "---" in [l.strip() for l in lines[1:]]:
            end = [l.strip() for l in lines[1:]].index("---") + 1
            for i, l in enumerate(lines[1:end], 1):
                m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", l)
                if m:
                    value = m.group(2).strip()
                    if value in (">", "|", ">-", "|-") and i + 1 < end and lines[i + 1].strip():
                        value = lines[i + 1].strip()
                    front[m.group(1)] = value
        else:
            flaw(f"{rel}: no YAML frontmatter between --- lines")
        if front.get("name") != skill:
            flaw(f"{rel}: name is {front.get('name')!r}, want {skill} (the directory)")
        if not front.get("description"):
            flaw(f"{rel}: no description")
        for word in words:
            if word not in text:
                flaw(f"{rel}: does not mention {word}")
    rel = os.path.join(codex_dir, "skills", skill, "agents/openai.yaml")
    text = text_of(rel)
    if text is not None:
        inside = False
        value = None
        for line in text.splitlines():
            if line.strip() == "policy:" and not line[:1].isspace():
                inside = True
            elif inside and line.strip() and not line[:1].isspace():
                inside = False
            elif inside:
                m = re.match(r"^\s+allow_implicit_invocation:\s*(\S+)", line)
                if m:
                    value = m.group(1)
        if value != "false":
            flaw(f"{rel}: policy.allow_implicit_invocation is {value!r}, want false")
if not os.path.isfile(path(os.path.join(codex_dir, "skills/hook/scripts/hook.sh"))):
    flaw(f"{codex_dir}/skills/hook/scripts/hook.sh is missing")

# --- Gemini: the manifest ---
manifest = load(os.path.join(GEMINI, "gemini-extension.json"))
if isinstance(manifest, dict):
    if manifest.get("name") != os.path.basename(GEMINI):
        flaw(f"gemini-extension.json: name is {manifest.get('name')!r}, want {os.path.basename(GEMINI)} (the directory)")
    for key in sorted(set(manifest) - {"name", "version", "description"}):
        flaw(f"gemini-extension.json: {key} is not name, version or description")
    if not nonempty(manifest.get("description")):
        flaw("gemini-extension.json: no description")
    if want is not None and manifest.get("version") != want:
        flaw(f"gemini-extension.json: version is {manifest.get('version')!r}, pyproject.toml has {want}")

# --- Gemini: the two commands ---
try:
    import tomllib
except ImportError:
    tomllib = None
    flaw("python3 has no tomllib (3.11 or later is needed)")
if tomllib:
    for command, must, banned in (("gates", GATES_CMD, "{{args}}"), ("spec", SPEC_CMD, None)):
        rel = os.path.join(GEMINI, "commands/lights-out", command + ".toml")
        text = text_of(rel)
        if text is None:
            continue
        try:
            doc = tomllib.loads(text)
        except ValueError as error:
            flaw(f"{rel} is not TOML: {error}")
            continue
        if not nonempty(doc.get("description")):
            flaw(f"{rel}: no description")
        prompt = doc.get("prompt")
        if not isinstance(prompt, str):
            flaw(f"{rel}: no prompt string")
            continue
        if must not in prompt:
            flaw(f"{rel}: the prompt does not hold {must}")
        if banned and banned in prompt:
            flaw(f"{rel}: the prompt holds {banned}")

# --- Gemini: the hook ---
hooks = load(os.path.join(GEMINI, "hooks/hooks.json"))
if isinstance(hooks, dict):
    inner = hooks.get("hooks")
    before = inner.get("BeforeTool") if isinstance(inner, dict) else None
    if not (isinstance(before, list) and len(before) == 1 and isinstance(before[0], dict)):
        flaw("gemini hooks.json: hooks.BeforeTool is not one group")
    else:
        group = before[0]
        if group.get("matcher") != "run_shell_command":
            flaw("gemini hooks.json: the matcher is not run_shell_command")
        hl = group.get("hooks")
        if not (isinstance(hl, list) and len(hl) == 1 and isinstance(hl[0], dict)):
            flaw("gemini hooks.json: the group has not one hook")
        else:
            hook = hl[0]
            if hook.get("type") != "command":
                flaw("gemini hooks.json: the hook's type is not command")
            if hook.get("timeout") != 30000 or isinstance(hook.get("timeout"), bool):
                flaw("gemini hooks.json: the hook's timeout is not the integer 30000")
            if hook.get("command") != GEMINI_HOOK:
                flaw(f"gemini hooks.json: the command is not {GEMINI_HOOK}")
elif hooks is not None:
    flaw("gemini hooks.json is not an object")

# --- Gemini: the copies ---
for script in ("pre-commit.sh", "run.sh"):
    mine, theirs = path(os.path.join(GEMINI, "scripts", script)), path(os.path.join("plugins/lights-out/scripts", script))
    if not os.path.isfile(mine):
        flaw(f"{GEMINI}/scripts/{script} is missing")
    elif not os.path.isfile(theirs):
        flaw(f"plugins/lights-out/scripts/{script} is missing")
    else:
        with open(mine, "rb") as a, open(theirs, "rb") as b:
            if a.read() != b.read():
                flaw(f"{GEMINI}/scripts/{script} differs from plugins/lights-out/scripts/{script}")

print("\n".join(sorted(set(flaws))))
PY

# ext_flaw ROOT: what is wrong with the Codex plugin and the Gemini
# extension under ROOT, one per line, or nothing.
ext_flaw() { python3 "$t/ext.py" "$1"; }

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
GCOMMIT='{"tool_name":"run_shell_command","tool_input":{"command":"git commit -m x"}}'
GLS='{"tool_name":"run_shell_command","tool_input":{"command":"ls"}}'

# hook PLUGIN REPO PATH STDIN: run PLUGIN's pre-commit.sh in REPO; its exit
# code in $hook_rc, stdout and stderr in $t/hook.out and $t/hook.err.
hook() {
  hook_rc=0
  (cd "$2" && printf '%s' "$4" | env PATH="$3" CLAUDE_PLUGIN_ROOT="$1" CLAUDE_PROJECT_DIR="$2" \
    sh "$1/scripts/pre-commit.sh") >"$t/hook.out" 2>"$t/hook.err" || hook_rc=$?
}
lines_of() { awk 'END{print NR}' "$1"; }

# hook_flaw ROOT [gemini]: what is wrong with ROOT's pre-commit.sh, or
# nothing; stdin in Claude's shape, or in Gemini's when asked.
hook_flaw() {
  COMMIT_IN=$COMMIT
  LS_IN=$LS
  if [ "${2:-}" = gemini ]; then COMMIT_IN=$GCOMMIT; LS_IN=$GLS; fi
  [ -f "$1/scripts/pre-commit.sh" ] || { printf '%s/scripts/pre-commit.sh is missing' "$1"; return; }
  with="$shim:$PATH"
  hook "$1" "$t/r-weak" "$with" "$COMMIT_IN"
  [ "$hook_rc" -eq 2 ] || { printf 'a staged weakening: exit %s, want 2' "$hook_rc"; return; }
  [ "$(lines_of "$t/hook.err")" -eq 1 ] || { printf 'a staged weakening: stderr has %s lines, want 1' "$(lines_of "$t/hook.err")"; return; }
  case "$(cat "$t/hook.err")" in
    "NO-GO: gates-light"*) ;;
    *) printf 'a staged weakening: stderr is not the gates line: %s' "$(cat "$t/hook.err")"; return ;;
  esac
  [ ! -s "$t/hook.out" ] || { printf 'a staged weakening: stdout is not empty'; return; }
  hook "$1" "$t/r-clean" "$with" "$COMMIT_IN"
  [ "$hook_rc" -eq 0 ] || { printf 'a clean staged change: exit %s, want 0' "$hook_rc"; return; }
  [ ! -s "$t/hook.out" ] || { printf 'a clean staged change: stdout is not empty'; return; }
  hook "$1" "$t/r-none" "$with" "$COMMIT_IN"
  { [ "$hook_rc" -eq 0 ] && [ ! -s "$t/hook.out" ] && [ ! -s "$t/hook.err" ]; } \
    || { printf 'no contract at HEAD: not exit 0 and silent (exit %s)' "$hook_rc"; return; }
  hook "$1" "$t/r-weak" "$with" "$LS_IN"
  { [ "$hook_rc" -eq 0 ] && [ ! -s "$t/hook.out" ] && [ ! -s "$t/hook.err" ]; } \
    || { printf 'a command that is no git commit: not exit 0 and silent (exit %s)' "$hook_rc"; return; }
  hook "$1" "$t/r-weak" "$bare" "$COMMIT_IN"
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

# --- Codex's hook.sh (amendment §3, §9) ---

# cj.py MODE FILE [ORIG]: judges a .codex/hooks.json. The recipe is the one
# verified in docs/use-on-your-repo.md. Prints the flaw and exits 1, or exits 0.
#   ours    FILE holds exactly our entry and nothing else
#   merged  FILE is ORIG's value plus our one group, ORIG's groups intact
#   same    FILE and ORIG are the same JSON value
#   command prints the command of the first PreToolUse hook
cat > "$t/cj.py" <<'PY'
import json, sys

RECIPE = r"""sh -c 'if grep -q "git commit"; then lights-out-gates --light STAGED=1 >&2 || exit 2; fi'"""
OURS = {"matcher": "*", "hooks": [{"type": "command", "command": RECIPE, "timeout": 30}]}


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def bad(text):
    print(text)
    sys.exit(1)


mode, path = sys.argv[1], sys.argv[2]
try:
    got = load(path)
except (OSError, ValueError) as error:
    bad(f"{path} is not readable JSON: {error}")
if mode == "ours":
    if got != {"hooks": {"PreToolUse": [OURS]}}:
        bad(f"not exactly our entry: {json.dumps(got)}")
elif mode == "same":
    if got != load(sys.argv[3]):
        bad(f"changed: {json.dumps(got)}")
elif mode == "merged":
    orig = load(sys.argv[3])
    pre = (got.get("hooks") or {}).get("PreToolUse")
    if not isinstance(pre, list) or pre.count(OURS) != 1:
        bad(f"our group is not there exactly once: {json.dumps(got)}")
    pre.remove(OURS)
    if not pre:
        del got["hooks"]["PreToolUse"]
    if got != orig:
        bad(f"the rest differs from the original: {json.dumps(got)}")
elif mode == "command":
    print(got["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
PY

# chook HOOK CWD ACTION: run `sh HOOK ACTION` in CWD; $chook_rc, stdout in
# $t/ch.out, stderr in $t/ch.err.
chook() {
  chook_rc=0
  (cd "$2" && sh "$1" "$3") >"$t/ch.out" 2>"$t/ch.err" </dev/null || chook_rc=$?
}
# chook_line KIND: the last run printed one stdout line, GO or NO-GO as KIND.
chook_line() {
  [ "$(lines_of "$t/ch.out")" -eq 1 ] || { printf '%s stdout lines, want 1' "$(lines_of "$t/ch.out")"; return 1; }
  case "$1:$(cat "$t/ch.out")" in
    "GO:GO: hook — "?*) ;;
    "NO-GO:NO-GO: hook — "?*) ;;
    *) printf 'stdout is not a %s hook line: %s' "$1" "$(cat "$t/ch.out")"; return 1 ;;
  esac
}
CODEX_STDIN='{"tool_input":{"command":"git commit -m x"}}'
CODEX_LS='{"tool_input":{"command":"ls"}}'

# codex_hook_flaw HOOK: what is wrong with a Codex hook.sh, run on scratch
# repositories, or nothing. A second install is judged JSON-equal (not
# byte-equal): the amendment says "changes nothing".
codex_hook_flaw() {
  [ -f "$1" ] || { printf '%s is missing' "$1"; return; }
  h=$t/hk
  rm -rf "$h"
  mkdir -p "$h"
  # a repository with no hooks file, driven from a subdirectory
  make_repo "$h/a" yes
  mkdir -p "$h/a/sub/dir"
  chook "$1" "$h/a/sub/dir" install
  [ "$chook_rc" -eq 0 ] || { printf 'install: exit %s, want 0' "$chook_rc"; return; }
  msg=$(chook_line GO) || { printf 'install: %s' "$msg"; return; }
  case "$(cat "$t/ch.out")" in
    *".codex/hooks.json"*"/hooks"*) ;;
    *) printf 'install: the GO line does not name .codex/hooks.json and /hooks: %s' "$(cat "$t/ch.out")"; return ;;
  esac
  msg=$(python3 "$t/cj.py" ours "$h/a/.codex/hooks.json" 2>&1) || { printf 'install: %s' "$msg"; return; }
  [ ! -e "$h/a/sub/dir/.codex" ] || { printf 'install: wrote .codex below the repository root'; return; }
  chook "$1" "$h/a/sub" install
  [ "$chook_rc" -eq 0 ] || { printf 'second install: exit %s, want 0' "$chook_rc"; return; }
  msg=$(chook_line GO) || { printf 'second install: %s' "$msg"; return; }
  msg=$(python3 "$t/cj.py" ours "$h/a/.codex/hooks.json" 2>&1) || { printf 'second install changed the file: %s' "$msg"; return; }
  chook "$1" "$h/a" remove
  [ "$chook_rc" -eq 0 ] || { printf 'remove: exit %s, want 0' "$chook_rc"; return; }
  msg=$(chook_line GO) || { printf 'remove: %s' "$msg"; return; }
  [ ! -e "$h/a/.codex/hooks.json" ] || { printf 'remove: .codex/hooks.json is still there after our entry was the only one'; return; }
  # a repository whose hooks file holds others
  make_repo "$h/b" yes
  mkdir -p "$h/b/.codex"
  printf '%s\n' '{"hooks":{"PostToolUse":[{"matcher":"*","hooks":[{"type":"command","command":"echo post","timeout":5}]}],"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"echo pre","timeout":5}]}]},"other":1}' > "$h/b/.codex/hooks.json"
  cp "$h/b/.codex/hooks.json" "$h/b.orig"
  chook "$1" "$h/b" install
  [ "$chook_rc" -eq 0 ] || { printf 'install beside others: exit %s, want 0' "$chook_rc"; return; }
  msg=$(python3 "$t/cj.py" merged "$h/b/.codex/hooks.json" "$h/b.orig" 2>&1) || { printf 'install beside others: %s' "$msg"; return; }
  chook "$1" "$h/b" install
  msg=$(python3 "$t/cj.py" merged "$h/b/.codex/hooks.json" "$h/b.orig" 2>&1) || { printf 'second install beside others: %s' "$msg"; return; }
  chook "$1" "$h/b" remove
  [ "$chook_rc" -eq 0 ] || { printf 'remove beside others: exit %s, want 0' "$chook_rc"; return; }
  msg=$(python3 "$t/cj.py" same "$h/b/.codex/hooks.json" "$h/b.orig" 2>&1) || { printf 'remove beside others: %s' "$msg"; return; }
  # unreadable JSON: refused, the file untouched, for both actions
  make_repo "$h/c" yes
  mkdir -p "$h/c/.codex"
  printf '%s' '{"hooks": [oops' > "$h/c/.codex/hooks.json"
  cp "$h/c/.codex/hooks.json" "$h/c.orig"
  for action in install remove; do
    chook "$1" "$h/c" "$action"
    [ "$chook_rc" -eq 1 ] || { printf 'unreadable JSON, %s: exit %s, want 1' "$action" "$chook_rc"; return; }
    msg=$(chook_line NO-GO) || { printf 'unreadable JSON, %s: %s' "$action" "$msg"; return; }
    cmp -s "$h/c/.codex/hooks.json" "$h/c.orig" || { printf 'unreadable JSON, %s: the file changed' "$action"; return; }
  done
  # no repository: refused, nothing written
  mkdir -p "$h/norepo"
  for action in install remove; do
    chook_rc=0
    (cd "$h/norepo" && GIT_CEILING_DIRECTORIES=$h sh "$1" "$action") >"$t/ch.out" 2>"$t/ch.err" </dev/null || chook_rc=$?
    [ "$chook_rc" -eq 1 ] || { printf 'no repository, %s: exit %s, want 1' "$action" "$chook_rc"; return; }
    msg=$(chook_line NO-GO) || { printf 'no repository, %s: %s' "$action" "$msg"; return; }
    [ -z "$(find "$h/norepo" -mindepth 1)" ] || { printf 'no repository, %s: wrote something' "$action"; return; }
  done
  # the written command, run as Codex runs it: the tool input on stdin
  for kind in weak clean; do
    make_repo "$h/$kind" yes
    if [ "$kind" = weak ]; then weaken "$h/$kind"; else clean_change "$h/$kind"; fi
    chook "$1" "$h/$kind" install
    [ "$chook_rc" -eq 0 ] || { printf 'install in the %s repository: exit %s' "$kind" "$chook_rc"; return; }
    cmd=$(python3 "$t/cj.py" command "$h/$kind/.codex/hooks.json")
    rc=0
    (cd "$h/$kind" && printf '%s' "$CODEX_STDIN" | env PATH="$shim:$PATH" sh -c "$cmd") >"$t/ch.out" 2>"$t/ch.err" || rc=$?
    case $kind:$rc in
      weak:2 | clean:0) ;;
      *) printf 'the written command on a %s staged change: exit %s' "$kind" "$rc"; return ;;
    esac
  done
  rc=0
  (cd "$h/weak" && printf '%s' "$CODEX_LS" | env PATH="$shim:$PATH" sh -c "$cmd") >"$t/ch.out" 2>"$t/ch.err" || rc=$?
  [ "$rc" -eq 0 ] || { printf 'the written command on a command that is no git commit: exit %s, want 0' "$rc"; return; }
}

# --- the real checks ---

flaw=$(json_flaw "$root" | head -n 1) || :
[ -z "$flaw" ] || nogo "$flaw" "$(json_flaw "$root")"
flaw=$(hook_flaw "$root/$PLUGIN")
[ -z "$flaw" ] || nogo "pre-commit.sh: $flaw" "$(cat "$t/hook.err" 2>/dev/null)"
flaw=$(skill_flaw "$root/$PLUGIN")
[ -z "$flaw" ] || nogo "skill.sh: $flaw" "$(cat "$t/skill.err" 2>/dev/null)"
flaw=$(ext_flaw "$root" | head -n 1) || :
[ -z "$flaw" ] || nogo "$flaw" "$(ext_flaw "$root")"
flaw=$(hook_flaw "$root/$GEMINI" gemini)
[ -z "$flaw" ] || nogo "gemini pre-commit.sh: $flaw" "$(cat "$t/hook.err" 2>/dev/null)"
flaw=$(codex_hook_flaw "$root/$CODEX/skills/hook/scripts/hook.sh")
[ -z "$flaw" ] || nogo "codex hook.sh: $flaw" "$(cat "$t/ch.err" 2>/dev/null)"

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

# --- (c) again: the Codex plugin, the Gemini extension, Codex's hook.sh ---

plant_ext() {  # NAME: a copy of what ext.py reads
  rm -rf "${t:?}/xplant-$1"
  mkdir -p "$t/xplant-$1"
  cp -R .agents plugins pyproject.toml "$t/xplant-$1/"
}
ext_must_flag() {  # NAME WORD: ext_flaw rejects the planted tree, naming WORD
  got=$(ext_flaw "$t/xplant-$1")
  case "$got" in
    *"$2"*) ;;
    *) nogo "the extension check did not reject the planted '$1' (want a flaw naming '$2')" "got: ${got:-nothing}" ;;
  esac
}
plant_ext gemini-byte
printf '#' >> "$t/xplant-gemini-byte/$GEMINI/scripts/pre-commit.sh"
ext_must_flag gemini-byte "differs"
plant_ext codex-hooks
mutate "$t/xplant-codex-hooks/$CODEX/.codex-plugin/plugin.json" 'd["hooks"] = "./hooks/hooks.json"'
ext_must_flag codex-hooks "hooks key"
plant_ext codex-hooks-dir
mkdir -p "$t/xplant-codex-hooks-dir/$CODEX/hooks"
ext_must_flag codex-hooks-dir "hooks/ directory"
plant_ext implicit
sed 's/allow_implicit_invocation: false/allow_implicit_invocation: true/' "$t/xplant-implicit/$CODEX/skills/spec/agents/openai.yaml" > "$t/openai.new"
cp "$t/openai.new" "$t/xplant-implicit/$CODEX/skills/spec/agents/openai.yaml"
ext_must_flag implicit "allow_implicit_invocation"
plant_ext gemini-timeout
mutate "$t/xplant-gemini-timeout/$GEMINI/hooks/hooks.json" 'd["hooks"]["BeforeTool"][0]["hooks"][0]["timeout"] = 30'
ext_must_flag gemini-timeout "timeout"
plant_ext gemini-name
mutate "$t/xplant-gemini-name/$GEMINI/gemini-extension.json" 'd["name"] = "lights-out"'
ext_must_flag gemini-name "(the directory)"
plant_ext gemini-version
mutate "$t/xplant-gemini-version/$GEMINI/gemini-extension.json" 'd["version"] = "0.0.0-planted"'
ext_must_flag gemini-version "version"
plant_ext codex-version
mutate "$t/xplant-codex-version/$CODEX/.codex-plugin/plugin.json" 'd["version"] = "0.0.0-planted"'
ext_must_flag codex-version "version"
plant_ext gemini-args
sed 's/lights-out-gates --light STAGED=1/lights-out-gates --light {{args}} STAGED=1/' "$t/xplant-gemini-args/$GEMINI/commands/lights-out/gates.toml" > "$t/gates.new"
cp "$t/gates.new" "$t/xplant-gemini-args/$GEMINI/commands/lights-out/gates.toml"
ext_must_flag gemini-args "gates.toml"

# The Gemini hook check must fail on a hook that never denies.
rm -rf "${PLANTS:?}/gemini-allow"
mkdir -p "$PLANTS/gemini-allow"
cp -R "$GEMINI/." "$PLANTS/gemini-allow/"
printf 'cat >/dev/null\nexit 0\n' > "$PLANTS/gemini-allow/scripts/pre-commit.sh"
[ -n "$(hook_flaw "$PLANTS/gemini-allow" gemini)" ] || nogo "the hook check accepted a Gemini hook that never denies"

# The hook.sh check must fail on naive scripts: one that appends twice, one
# that drops a foreign hook, one that prints two lines, one that writes nothing.
cat > "$t/naive.py" <<'PY'
import json, os, sys

mode, action, repo = sys.argv[1:4]
RECIPE = r"""sh -c 'if grep -q "git commit"; then lights-out-gates --light STAGED=1 >&2 || exit 2; fi'"""
OURS = {"matcher": "*", "hooks": [{"type": "command", "command": RECIPE, "timeout": 30}]}
path = os.path.join(repo, ".codex", "hooks.json")
if action == "install":
    d = {}
    if os.path.exists(path) and mode != "clobber":
        d = json.load(open(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pre = d.setdefault("hooks", {}).setdefault("PreToolUse", [])
    if mode == "twice" or OURS not in pre:
        pre.append(OURS)
    json.dump(d, open(path, "w"))
elif os.path.exists(path):
    d = json.load(open(path))
    d["hooks"]["PreToolUse"] = [g for g in d["hooks"]["PreToolUse"] if g != OURS]
    d["hooks"] = {k: v for k, v in d["hooks"].items() if v}
    if d["hooks"]:
        json.dump(d, open(path, "w"))
    else:
        os.remove(path)
print("GO: hook — wrote .codex/hooks.json; trust it in /hooks")
if mode == "noisy":
    print("done")
PY
for mode in twice clobber noisy; do
  mkdir -p "$PLANTS/hook-$mode"
  # shellcheck disable=SC2016 # $1 and the command substitution are the planted script's
  printf 'exec python3 "%s" %s "$1" "$(git rev-parse --show-toplevel)"\n' "$t/naive.py" "$mode" > "$PLANTS/hook-$mode/hook.sh"
  [ -n "$(codex_hook_flaw "$PLANTS/hook-$mode/hook.sh")" ] || nogo "the hook.sh check accepted a hook.sh that is '$mode'"
done
mkdir -p "$PLANTS/hook-none"
printf 'echo "GO: hook — nothing"\n' > "$PLANTS/hook-none/hook.sh"
[ -n "$(codex_hook_flaw "$PLANTS/hook-none/hook.sh")" ] || nogo "the hook.sh check accepted a hook.sh that writes nothing"

go
