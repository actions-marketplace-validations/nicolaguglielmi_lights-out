#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-package: docs/adr/0045 §8, engine-free and network-free (the engine half
# is `./go demo-package`); written from the ADR, not from the wrapper.
#   wrapper    lights-out is an executable #!/bin/sh file, clean under
#              `shellcheck -s sh` (ci/shell.sh does not list it), one semver
#              version= line, no socket, --env-file or :z in its code; an
#              unknown subcommand or KEY=VALUE is refused, naming the accepted
#              ones, before any engine is touched; with no engine on PATH an
#              engine subcommand exits non-zero with one stderr line and
#              nothing on stdout; `version` still works.
#   allowlist  the wrapper's KEY=* case arms equal package/entrypoint.sh's and
#              each is taken.
#   yaml       (PyYAML) action.yml is composite, runs $GITHUB_ACTION_PATH/../
#              lights-out gates, calls no REST path but check-runs; jobs that
#              use ./action hold at most contents: read + checks: write;
#              packages: write only package.yml's publish (v* tag or
#              workflow_dispatch); every job has the github.com guard (ADR 0039).
#   doctor     core/doctor.sh with no engine: one `NO-GO: doctor —` line naming
#              the engine, exit 1, no ANSI.
# Each judge is then run on copies of the real files with one defect each (the
# edits name the real text; if it moves, the defect is not applied and this
# says it cannot fail).
# shellcheck disable=SC2016,SC2086 # edits are text; word lists are split on purpose
set -eu
name=package
. ci/lib.sh

for t in shellcheck python3; do command -v "$t" >/dev/null 2>&1 || nogo "$t is not on PATH (./go ci runs in the workbench)"; done
python3 -c 'import yaml' 2>/dev/null || nogo "python3 cannot import yaml (PyYAML, workbench/uv.lock)"
for f in lights-out package/entrypoint.sh action/action.yml .github/workflows/package.yml core/doctor.sh; do
  [ -e "$f" ] || nogo "$f not found"
done

root=$(pwd -P)
sh_bin=$(command -v sh)
w=$(mktemp -d)
trap 'rm -rf "$w"' EXIT
# tools: a PATH of plain tools and no engine. trip: a podman and docker that only leave a mark.
mkdir "$w/tools" "$w/trip" "$w/repo"
for t in git awk sed grep tr sort head tail cut cksum cat uname basename dirname mkdir rm mktemp id env wc; do
  p=$(command -v "$t" 2>/dev/null || true)
  case "$p" in /*) ln -s "$p" "$w/tools/$t" ;; esac
done
printf '#!/bin/sh\n: > %s/tripped\n' "$w" > "$w/trip/podman"
cp "$w/trip/podman" "$w/trip/docker"
chmod +x "$w/trip/podman" "$w/trip/docker"
git init -q "$w/repo" >/dev/null 2>&1 || nogo "git init failed in a temporary directory"

lines() { awk 'END{print NR}' "$1"; }
has_all() { hf=$1; shift; for hx; do grep -qw -- "$hx" "$hf" || return 1; done; }
# run PATH CMD...: CMD in an empty environment but PATH; stdout in $w/o, stderr in $w/e, status in $rc.
run() { rp=$1; shift; rm -f "$w/tripped"; (cd "$w/repo" && env -i PATH="$rp" HOME="$w" "$@") >"$w/o" 2>"$w/e" && rc=0 || rc=$?; }
# keys FILE: the KEY of each KEY=* case arm outside comments, sorted.
keys() { grep -Ev '^[[:space:]]*#' "$1" | grep -oE '[A-Z][A-Z0-9_]*=/?\*' | sed 's/=.*//' | LC_ALL=C sort -u | tr '\n' ' '; }

# wrapper_flaws ROOT: what is wrong with ROOT/lights-out, one line each.
wrapper_flaws() {
  f=$1/lights-out
  k=$(keys "$1/package/entrypoint.sh")
  v=$(sed -n 's/^version=//p' "$f")
  { [ -x "$f" ] && [ "$(head -n 1 "$f")" = '#!/bin/sh' ]; } || echo "the wrapper is not an executable #!/bin/sh file"
  shellcheck -s sh --color=never "$f" >"$w/sc" 2>&1 || { echo "shellcheck -s sh reports problems in the wrapper"; cat "$w/sc"; }
  { [ "$(grep -c '^version=' "$f")" = 1 ] && printf '%s\n' "$v" | grep -Eq '^(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){2}$'; } \
    || echo "the wrapper needs exactly one version= line, semver X.Y.Z"
  ! grep -Ev '^[[:space:]]*#' "$f" | grep -qE '\.sock|DOCKER_HOST|RemoteSocket|--env-file|[:,][zZ]([^A-Za-z0-9_]|$)' \
    || echo "the wrapper names an engine socket, --env-file or a :z/:Z mount"
  { [ -n "$k" ] && [ "$k" = "$(keys "$f")" ]; } || echo "the allowlists differ: the wrapper takes [$(keys "$f")], the entrypoint [$k]"
  run "$w/trip:$w/tools" "$f" frobnicate
  { [ "$rc" -ne 0 ] && [ ! -e "$w/tripped" ] && [ ! -s "$w/o" ] && has_all "$w/e" init gates triage postmortem doctor version; } \
    || echo "an unknown subcommand is not refused on stderr, before any engine, naming the six"
  for a in "init NOPE=1" "gates NOPE=1" "triage BASEX=1" "postmortem base=x"; do
    run "$w/trip:$w/tools" "$f" $a
    { [ "$rc" -ne 0 ] && [ ! -e "$w/tripped" ] && has_all "$w/e" $k; } || echo "'$a' is not refused before any engine, naming $k"
  done
  for x in $k; do
    run "$w/trip:$w/tools" "$f" gates "$x=x"
    [ -e "$w/tripped" ] || echo "$x= is in the entrypoint's allowlist and the wrapper refuses it"
  done
  for a in init gates "triage ALERT=a" "postmortem INCIDENT=i"; do
    run "$w/tools" "$f" $a
    { [ "$rc" -ne 0 ] && [ ! -s "$w/o" ] && [ "$(lines "$w/e")" = 1 ] && grep -qi engine "$w/e"; } \
      || echo "'$a' with no engine: want non-zero, nothing on stdout, one stderr line naming the engine"
  done
  run "$w/tools" "$f" version
  { [ "$rc" -eq 0 ] && grep -qF -- "${v:-?}" "$w/o"; } || echo "version does not work with no engine"
  :
}

# doctor_flaws ROOT: ROOT/core/doctor.sh, run from the repository root with no engine on PATH.
doctor_flaws() {
  (cd "$root" && env -i PATH="$w/tools" HOME="$w" "$sh_bin" "$1/core/doctor.sh") >"$w/o" 2>"$w/e" && rc=0 || rc=$?
  { [ "$rc" -eq 1 ] && [ "$(lines "$w/o")" = 1 ] && grep -qE '^NO-GO: doctor — .*engine' "$w/o" && ! grep -q "$(printf '\033')" "$w/o"; } \
    || echo "core/doctor.sh with no engine: want exit 1 and the one line NO-GO: doctor — naming the engine, no ANSI; got exit $rc: $(cat "$w/o")"
  :
}

cat > "$w/chk.py" <<'PY'
import copy, glob, os, re, sys, yaml

root, mode = sys.argv[1], sys.argv[2]
PKG, ACT = ".github/workflows/package.yml", "action/action.yml"
S = "github.server_url == 'https://github.com'"
TAG, DISP = r"startsWith\(github\.ref, 'refs/tags/v'\)", r"github\.event_name == 'workflow_dispatch'"
PUB = re.compile(re.escape(S) + r" && \((%s \|\| %s|%s \|\| %s)\)" % (TAG, DISP, DISP, TAG))
names = glob.glob(".github/workflows/*.y*ml", root_dir=root) + [ACT]
d0 = {n: yaml.safe_load(open(os.path.join(root, n))) for n in names if os.path.isfile(os.path.join(root, n))}


def uses(j):
    return any(str(s.get("uses", "")).startswith("./action") for s in j.get("steps") or [])


def pw(p):
    return p == "write-all" or (isinstance(p, dict) and p.get("packages") == "write")


def flaws(d):
    a = d.get(ACT)
    if not isinstance(a, dict) or (a.get("runs") or {}).get("using") != "composite":
        yield "action/action.yml is missing or is not a composite action"
    else:
        run = "\n".join(str(s.get("run", "")) for s in a["runs"].get("steps") or [])
        if not re.search(r"(\$GITHUB_ACTION_PATH|\$\{GITHUB_ACTION_PATH\}|\$\{\{\s*github\.action_path\s*\}\})/\.\./lights-out\"?\s+gates", run):
            yield "action/action.yml does not run $GITHUB_ACTION_PATH/../lights-out gates"
        for p in re.findall(r"(?:GITHUB_API_URL\}?|api\.github\.com)(/[^\s\"'?]*)", run) + re.findall(r"\bgh\s+api\s+(\S+)", run):
            if not p.endswith("check-runs"):
                yield "action/action.yml calls %s, a permission beyond checks: write" % p
    for path, doc in d.items():
        for n, j in (doc.get("jobs") or {}).items() if path != ACT else ():
            p = j.get("permissions", doc.get("permissions"))
            if pw(p) and not (path == PKG and n == "publish"):
                yield "%s: job %s holds packages: write; only package.yml's publish may" % (path, n)
            if uses(j) and not (isinstance(p, dict) and all(v == "none" or (k, v) in (("contents", "read"), ("checks", "write")) for k, v in p.items())):
                yield "%s: job %s uses ./action with permissions %s, want at most contents: read and checks: write" % (path, n, p)
    jobs = (d.get(PKG) or {}).get("jobs") or {}
    if "publish" not in jobs:
        yield "package.yml has no publish job"
    for n, j in jobs.items():
        c = re.sub(r"^\$\{\{(.*)\}\}$", r"\1", str(j.get("if", "")).strip()).strip()
        if n == "publish":
            if not PUB.fullmatch(c):
                yield "package.yml: job publish: if: %r is not the github.com guard and a v* tag or workflow_dispatch" % c
            if not (isinstance(j.get("permissions"), dict) and j["permissions"].get("packages") == "write"):
                yield "package.yml: job publish has no packages: write"
        elif not re.fullmatch(re.escape(S) + r"( && [^|]*)?", c):
            yield "package.yml: job %s: if: %r is not the github.com guard (ADR 0039)" % (n, c)


J = lambda d: d[PKG]["jobs"]
A = lambda d: next(j for j in J(d).values() if uses(j))
Q = lambda d: next(j for n, j in J(d).items() if n != "publish" and not uses(j))


def other(d):
    d[".github/workflows/o.yml"] = {"jobs": {"x": {"permissions": {"packages": "write"}, "steps": []}}}


def no_perms(d):
    A(d).pop("permissions")
    d[PKG].pop("permissions", None)


def runs(d, a, b):
    for s in d[ACT]["runs"]["steps"]:
        s["run"] = str(s.get("run", "")).replace(a, b)


CASES = [
    ("the Action job holds packages: write", lambda d: A(d)["permissions"].update(packages="write"), "uses ./action"),
    ("the Action job sets no permissions", no_perms, "uses ./action"),
    ("another job holds packages: write", lambda d: Q(d).update(permissions={"packages": "write"}), "only package.yml's publish"),
    ("another workflow holds packages: write", other, "only package.yml's publish"),
    ("publish runs on every push", lambda d: J(d)["publish"].update({"if": S}), "job publish: if"),
    ("publish: && and || ungrouped", lambda d: J(d)["publish"].update({"if": S + " && startsWith(github.ref, 'refs/tags/v') || github.event_name == 'workflow_dispatch'"}), "job publish: if"),
    ("publish without packages: write", lambda d: J(d)["publish"].pop("permissions"), "no packages: write"),
    ("a job without the github.com guard", lambda d: Q(d).pop("if"), "ADR 0039"),
    ("a job whose guard has an ||", lambda d: Q(d).update({"if": S + " || github.event_name == 'push'"}), "ADR 0039"),
    ("action.yml is not composite", lambda d: d[ACT]["runs"].update(using="node20"), "composite"),
    ("action.yml does not reach ../lights-out", lambda d: runs(d, "/../lights-out", "/../x"), "does not run"),
    ("action.yml calls another REST path", lambda d: runs(d, "check-runs", "issues/1/comments"), "beyond"),
]
if mode == "check":
    print("\n".join(flaws(d0)))
else:
    for desc, mutate, want in CASES:
        d = copy.deepcopy(d0)
        mutate(d)
        got = "\n".join(flaws(d))
        if want not in got:
            print("it cannot fail: %s -> [%s]" % (desc, got[:160]))
            break
PY

# judge WHAT FLAWS: the first flaw is the one line, all of them go to stderr.
judge() { [ -z "$2" ] || nogo "$1: $(printf '%s\n' "$2" | head -n 1)" "$2"; }
judge wrapper "$(wrapper_flaws "$root")"
judge doctor "$(doctor_flaws "$root")"
judge yaml "$(python3 -I "$w/chk.py" "$root" check)"

# --- the checks must be able to fail ----------------------------------------------
# try JUDGE WANT EDIT: JUDGE on a copy of the real files with EDIT applied names WANT.
try() {
  rm -rf "$w/m"
  mkdir -p "$w/m/package" "$w/m/core"
  cp lights-out "$w/m/"
  cp package/entrypoint.sh "$w/m/package/"
  cp core/doctor.sh "$w/m/core/"
  (cd "$w/m" && eval "$3")
  got=$($1 "$w/m")
  case "$got" in
    *"$2"*) ;;
    "") nogo "ci/package.sh cannot fail: it accepted: $3" ;;
    *) nogo "ci/package.sh named the wrong problem for: $3" "wanted: $2" "got: $got" ;;
  esac
}
try wrapper_flaws "engine socket" 'sed -i "1a : -v /var/run/docker.sock:/s" lights-out'
try wrapper_flaws "--env-file" 'sed -i "1a : --env-file .env" lights-out'
try wrapper_flaws ":z" 'sed -i "1a : -v x:/repo:ro,z" lights-out'
try wrapper_flaws "not an executable" 'chmod -x lights-out'
try wrapper_flaws "not an executable" 'sed -i "1s|.*|#!/bin/bash|" lights-out'
try wrapper_flaws "shellcheck" 'sed -i "1a [[ -n x ]] || :" lights-out'
try wrapper_flaws "semver" 'sed -i "s/^version=.*/version=1.2/" lights-out'
try wrapper_flaws "semver" 'sed -i "/^version=/p" lights-out'
try wrapper_flaws "unknown subcommand is not refused" 'sed -i "s/^  \*) die .unknown command.*/  *) ;;/" lights-out'
try wrapper_flaws "is not refused before any engine, naming" 'sed -i "s/^    BASE=\*|/    *|BASE=*|/" lights-out'
try wrapper_flaws "is not refused before any engine, naming" 'sed -i "s/ one of BASE= HEAD= STAGED= ALERT= INCIDENT= PROFILE= MODEL_PROVIDER= MODEL=//" lights-out'
try wrapper_flaws "unknown subcommand is not refused" 'sed -i "1a podman info" lights-out'
try wrapper_flaws "with no engine" 'sed -i "s/^  die .no container engine found.*/  echo no engine found; exit 1/" lights-out'
try wrapper_flaws "with no engine" 'sed -i "s/^  die .no container engine found.*/  echo no engine found >\&2; exit 0/" lights-out'
try wrapper_flaws "version does not work" 'sed -i "s/= version \]/= nonesuch ]/" lights-out'
try wrapper_flaws "allowlists differ" 'sed -i "s/INCIDENT=\*|//" lights-out'
try wrapper_flaws "allowlists differ" 'printf "case x in FOO=*) ;; esac\n" >> package/entrypoint.sh'
try doctor_flaws "want exit 1" 'sed -i "/^\. ci\/lib.sh/a echo second" core/doctor.sh'
try doctor_flaws "want exit 1" 'printf "#!/bin/sh\necho NO-GO: doctor — key\nexit 1\n" > core/doctor.sh'
try doctor_flaws "want exit 1" 'printf "#!/bin/sh\necho GO: doctor\nexit 0\n" > core/doctor.sh'
try doctor_flaws "want exit 1" 'printf "#!/bin/sh\nprintf \"\\033[31mNO-GO: doctor — engine\\033[0m\\n\"\nexit 1\n" > core/doctor.sh'
try doctor_flaws "want exit 1" 'printf "#!/bin/sh\necho NO-GO: doctor — engine\nexit 0\n" > core/doctor.sh'
st=$(python3 -I "$w/chk.py" "$root" selftest) || nogo "the YAML self-test crashed; see stderr"
[ -z "$st" ] || nogo "ci/package.sh $st"

go
