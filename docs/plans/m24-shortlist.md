# M24 step 1: a shortlist of legacy repositories

- Status: a proposal for the owner to pick from. Nothing is decided here.
- Date: 2026-11-04, one cloud session, branch `claude/admiring-shannon-7qlb8s`.
- Scope: step 1 of M24 in [third-arc-execution.md](third-arc-execution.md)
  ("Pick the repository and the ticket batch"), against
  [PLAN.md](../PLAN.md) §14 (the criteria and the exit criterion) and §16 M24
  (every ticket three times, once per provider, verdicts published).
- Nobody was contacted and nothing was opened on any repository. Every
  candidate was read from a shallow clone in the session's scratch space.

## How this was made, and what it could not do

| What | How | Provenance |
|---|---|---|
| Stars, license, size, last push, open issues | GitHub search API (`search/repositories` with `repo:` qualifiers) | measured 2026-11-04 |
| Files, code, policies, history | `git clone --depth 50` of the default branch, at the commit given per candidate | read 2026-11-04 |
| What `./go init` would draft | lights-out's own `core/init.py --repo <clone> --out <scratch>`, run as is: stack, scope, `TEST_CMD`, `TOOLCHAIN_IMAGE`, or the refusal line | measured, this commit of lights-out |
| Mutant count over init's scope | cosmic-ray 8.7.0 from `stacks/python/runners/uv.lock`, `init` plus `cr-filter-operators` (the same excluded operators as `stacks/python/runners/mutation.sh`) and `cr-filter-pragma`. This parses the sources and runs none of them | measured |
| Lint debt | ruff 0.15.0, `--isolated` (the candidate's own config ignored). Totals are from `--target-version py310 --select UP,C901,SIM,B,PERF`; a ticket's check names its own rules and target. Static: runs nothing from the clone | measured |

Not done, so not claimed:

- **No candidate's test suite was run.** The session's permission policy
  refused to execute third-party code. Suite wall times are unmeasured.
  Every "baseline" figure below is an extrapolation, labelled as such.
- **No lockfile was checked for advisories.** `api.osv.dev` was refused by
  the environment's proxy (403). The `deps` gate judges a lockfile whole on
  the first run ([use-on-your-repo.md](../use-on-your-repo.md), "A first
  commit is judged whole"), so an advisory there is a NO-GO on day one.
  Check this first, with `./go gates`, on whichever candidate is picked.
- **No CI history, PR merge rate or review latency.** The GitHub repository
  API answered 403 for repositories outside this session's scope. Only
  search worked. "Active" below means commits in the clone's history and
  the last push date, nothing more.
- **Maintainers' stance comes from what the repository says**:
  CONTRIBUTING, PR templates, AGENTS.md, AI policies. Where a repository
  says nothing, the stance is "not stated", not "welcome".

## 1. The checklist, written before the search

From PLAN §14 (the thesis and its exit criterion), §16 M24 (three
providers), and [use-on-your-repo.md](../use-on-your-repo.md) (what
lights-out supports today).

**The experiment**

1. Open source, not controlled by the owner.
2. Real users, so that "proven on a codebase not written for lights-out"
   means something to a reader.
3. Python (§14, amended 2026-09-23: the experiment measures the thesis, not
   language independence). JavaScript only as a reserve.
4. Mechanical debt of the kinds §14 names: a dependency upgrade, dead code,
   tests on untested code, migration off a deprecated API. Lint debt and
   Python 2 leftovers count.
5. A permissive license (MIT, BSD, Apache-2.0, ISC, Unlicense).
6. Active enough that a PR could be welcome. AI contributions not
   forbidden. A policy against *unsupervised* agents rules a candidate out
   for upstream PRs, because lights-out is exactly that.
7. Willing to be named in public: the diary publishes the verdicts and the
   audit chains.

**lights-out today**

8. `pyproject.toml` and `uv.lock` at the root. Without `uv.lock`, init
   answers NO-GO and names it. Adding one is a commit the owner makes to
   the fork before any ticket runs.
9. `requires-python` admits 3.13. Then `TOOLCHAIN_IMAGE=workbench`, which
   is also the only form the wrapper accepts.
10. A pytest suite under `tests/` or `test/`, runnable as init drafts it:
    `uv run --locked pytest tests -q -p no:cacheprovider`. Otherwise
    `TEST_CMD` is edited in `.lights-out/workload.env`. That edit is not a
    change to the repository.
11. One package directory as the mutation scope. Init measures the baseline
    over all of it, once. The only per-mutant rate measured in this repo is
    the bundled app's: 792 s for 205 mutants, about 3.9 s each
    (`app/workload.env`). The 300 s budget is proven on two tiny examples
    only (ADR 0042, Consequences).
12. The plane half (`compose.yaml`, `/healthz` and `/metrics` on `:8000`,
    the flag file, smoke and load) exists only for a service. A library gets
    gates, PR and audit, and no canary.
13. Tickets go in `.lights-out/tickets/`, each with a `## Perimeter` that
    names real paths, and changes code that tests cover or can cover.

## 2. What was searched

- `search/repositories`, Python: `stars:800..8000 size:<1500` (and `<2000`,
  `<3000`) `pushed:>2026-09-01 archived:false`, with topics `library`,
  `parser`, `cli` and `flask`. The pool came from these results plus
  well-known small libraries.
- `search/repositories`, JavaScript: well-known libraries with plain-JS
  sources in `src/` or `lib/`.
- 32 repositories cloned and read: 18 Python, 14 JavaScript. Why the ones
  not shortlisted were left out is in section 4.

## 3. The ranked shortlist

Baseline extrapolation: mutants × 3.9 s, the bundled app's measured rate.
That rate is not a measurement of these suites. Each suite's own wall time
sets the real figure, and none was run.

| # | Repository | License | Stars | Commit read | Prep before ticket 1 | Mutants (scope) | Baseline, extrapolated | AI stance, from the repo | Debt, measured |
|---|---|---|---|---|---|---|---|---|---|
| 1 | [andialbrecht/sqlparse](https://github.com/andialbrecht/sqlparse) | BSD-3-Clause | 4,022 | `09dbe1eec31ed1b3cd05366748865f11ba427d32` (2026-11-01) | **none** | 2,944 (`sqlparse/`) | ~3.2 h | ships `AGENTS.md` and `CLAUDE.md`, and AI code review is on | 8 TODO/FIXME lines; ruff: 8 C901, `validate_options` at complexity 28; repo's own `max-complexity = 31` |
| 2 | [python-validators/validators](https://github.com/python-validators/validators) | MIT | 1,133 | `22786cc6e7283a0fa452c179797e447f798db9f0` (2026-10-22) | none to the repo; `TEST_CMD` edited in `.lights-out/` | 3,304 (`src/validators/`) | ~3.5 h | not stated | ruff: 31 findings, 20 of them old-style typing (UP006, UP007, UP035, UP045), 5 `zip()` without `strict` |
| 3 | [gruns/furl](https://github.com/gruns/furl) | Unlicense | 2,812 | `bb77c48c6735929b469954ab6e54b33e17ac5121` (2026-10-18) | `pyproject.toml` and `uv.lock` (packaging is `setup.py` only) | 1,460 (`furl/`) | ~1.6 h | not stated | `six` in 12 calls plus imports; Python 2 branches in `compat.py`; ruff: 49 findings |
| 4 | [kislyuk/yq](https://github.com/kislyuk/yq) | Apache-2.0 | 3,002 | `a98d746b96d3e6e60d3cc6e9e38a57e5005482c6` (2026-10-10) | `uv.lock`; `TEST_CMD` edited (unittest, not pytest) | 1,430 (`yq/`) | ~1.5 h | ships `AGENTS.md` with rules for agents | ruff: 10 C901, function `yq` at complexity 78 |
| 5 | [jd/tenacity](https://github.com/jd/tenacity) | Apache-2.0 | 8,818 | `aac059c906170ee7b6ce1aa086a226f3aded5c99` (2026-11-01) | `uv.lock` (CI already uses `uv run`) | 1,713 (`tenacity/`) | ~1.8 h | not stated | low: clean under its own ruff config; public strategies that no test names |
| 6 | [jmespath/jmespath.py](https://github.com/jmespath/jmespath.py) | MIT | 2,457 | `2812594e69d43098ef60f81f4efc404c071b0418` (2026-01-22) | `pyproject.toml` and `uv.lock` (`setup.py` and `requirements.txt` only) | 1,409 (`jmespath/`) | ~1.5 h | not stated | Python 2 shims in `compat.py`; ruff: 52 findings, 23 `%` formats, 6 `super(Class, self)` |

Why this order: the experiment's claim is "no human touched the code", so a
candidate that needs no commit before ticket 1 ranks first. Next comes
mechanical debt, then how much prep is needed, then signs that a PR would
be read. Every candidate's baseline misses "minutes" (see section 6).

## 4. Considered and not shortlisted

| Repository | Why not |
|---|---|
| [hynek/structlog](https://github.com/hynek/structlog) | `.github/AI_POLICY.md`: "Absolutely **no** unsupervised agentic tools", and "No LLM bots in `Co-authored-by:`s". Rejected |
| [Python-Markdown/markdown](https://github.com/Python-Markdown/markdown) | `docs/contributing.md`, "AI Contributions": "The use of an AI agent to submit a pull request, issue, or comment autonomously is not permitted." Also 8,456 mutants. Rejected |
| [mahmoud/boltons](https://github.com/mahmoud/boltons) | The best debt in the pool (53 Python 2 leftovers, 108 `%` formats) and an explicit welcome: "AI-assisted PRs are welcome here", with tool, model and prompts disclosed. But 13,283 mutants, about 14 h extrapolated, and no `uv.lock`. Worth a second look only if the baseline problem in section 6 is solved |
| [sloria/environs](https://github.com/sloria/environs) | Inits as is (`uv.lock`, tests group by default), 1,477 mutants, but clean under ruff `ALL`. No mechanical debt to give tickets |
| [pallets/itsdangerous](https://github.com/pallets/itsdangerous) | Inits as is. Last commit 2025-06-14, ruff finds 5 issues, 37 tests. Low debt, quiet |
| [psf/httpbin](https://github.com/psf/httpbin) | The only Flask service in the pool, so the only one where the plane could run. But CONTRIBUTING says "frozen for new features and only accepting backwards-compatible bug fixes", open an issue first |
| [python-humanize/humanize](https://github.com/python-humanize/humanize), [prettytable/prettytable](https://github.com/prettytable/prettytable) | Modern, low debt; no `uv.lock`; tests need extras. humanize profiles every issue and PR author (`profile-pr-authors.yml`) |
| [jazzband/tablib](https://github.com/jazzband/tablib) | Tests need optional format dependencies (xlsx, ods, pandas); 2,623 mutants; low debt |
| [arrow-py/arrow](https://github.com/arrow-py/arrow) | 3,916 mutants; last commit in the clone 2026-04-30 |
| [mahmoud/glom](https://github.com/mahmoud/glom), [coleifer/sqlite-web](https://github.com/coleifer/sqlite-web) | glom: no `pyproject.toml`, tests inside the package. sqlite-web: no test suite |
| JavaScript: [json5/json5](https://github.com/json5/json5) | **The JS reserve.** Inits as is (`lib/`, `package-lock.json`, Node `>=22.12` → workbench). Very active: six commits by six different authors, 2026-10-22 to 10-29. But it is modern ESM with 100 % coverage enforced in `npm test`: little mechanical debt |
| JavaScript: [tj/commander.js](https://github.com/tj/commander.js), [caolan/async](https://github.com/caolan/async), [moment/luxon](https://github.com/moment/luxon), [iamkun/dayjs](https://github.com/iamkun/dayjs), [NaturalIntelligence/fast-xml-parser](https://github.com/NaturalIntelligence/fast-xml-parser), [showdownjs/showdown](https://github.com/showdownjs/showdown) | Init drafts all of them. Each runs its whole `npm test` per mutant (Stryker's command runner), and their scopes are 4,000 to 16,000 lines. commander's `npm test` also type-checks. dayjs's runs the suite once per time zone |
| JavaScript: [nodeca/js-yaml](https://github.com/nodeca/js-yaml), [markedjs/marked](https://github.com/markedjs/marked) | Sources are TypeScript; the runner mutates `.js`, `.mjs` and `.cjs` only. marked is also refused by init (section 6) |
| JavaScript: [validatorjs/validator.js](https://github.com/validatorjs/validator.js), [handlebars-lang/handlebars.js](https://github.com/handlebars-lang/handlebars.js), [npm/node-semver](https://github.com/npm/node-semver) | No `package-lock.json` committed |
| JavaScript: [jshint/jshint](https://github.com/jshint/jshint), [janl/mustache.js](https://github.com/janl/mustache.js) | Last commit 2022-12-28 and 2023-01-21 |

## 5. The candidates, with evidence and five tickets each

The tickets follow the shape of `tickets/0013.md`: problem, acceptance
criteria in Given/When/Then, perimeter. They are drafts in English for
`.lights-out/tickets/` in the fork. Paths are relative to each repository's
root, at the commit given. Each ticket changes code the suite covers, or
adds the test that covers it, so the `test` and line-scoped `mutation`
gates have something to judge.

### 5.1 andialbrecht/sqlparse (rank 1)

**Evidence.** Commit `09dbe1eec31ed1b3cd05366748865f11ba427d32`.

- BSD-3-Clause (`LICENSE`). 4,022 stars, 325 open issues.
- Maintainer active: 32 of the clone's commits since 2026-05 are by the
  author.
- `AGENTS.md` ("guidance to Agents when working with code in this
  repository"), and `CLAUDE.md` is `@AGENTS.md`. `.github/PULL_REQUEST_TEMPLATE.md`
  says the repository "has automated AI code reviews enabled".
- Init, run as is: `STACK=python`, `WORKLOAD_MUTATION_SCOPE=sqlparse/`,
  `TOOLCHAIN_IMAGE=workbench` (`requires-python >=3.10`),
  `TEST_CMD=uv run --locked pytest tests -q -p no:cacheprovider`.
- pytest is in the `dev` dependency group, which `uv run` syncs by default.
  CI runs `uv run --group dev pytest tests/` on Python 3.10 to 3.14.
- 325 test functions in 12 files. `uv.lock` has 85 packages, among them the
  docs toolchain (sphinx, furo). All of them are in the `deps` gate's scope.
- 2,944 mutants. The largest files are `reindent.py` (554), `sql.py` (461)
  and `grouping.py` (413).
- Plane: none, it is a library.
- What `.lights-out/` needs: the draft as is, plus the tickets.

**Tickets.**

#### sqlparse-01: Test `Token.match(regex=True)` on a non-keyword token

Problem: `sqlparse/sql.py:120` carries `# TODO: Add test for regex with
is_keyword = false`. The branch compiles patterns with `re.IGNORECASE`
only for keywords. The only test that passes `regex=True` is
`tests/test_grouping.py:530`, and it does so on a keyword.

Acceptance criteria:

Given a `Name` token for `foo`, from `sqlparse.parse("select foo")`
When `token.match(T.Name, r"^FOO$", regex=True)` is called
Then it returns `False`, and `r"^foo$"` returns `True`.

Given the test above
When `flag = re.IGNORECASE if self.is_keyword else 0` is changed to always
use `re.IGNORECASE`
Then the test fails.

Given the test is in place
When `sqlparse/sql.py` is read
Then the TODO at line 120 is gone.

Perimeter: `sqlparse/sql.py`, `tests/test_tokenize.py`

#### sqlparse-02: Resolve the "never match" FIXME on the look-behind rule

Problem: `sqlparse/keywords.py:157` says `# FIXME(atronah): never match,
because re.match doesn't work with look-behind regexp feature`, above
`(r'(?<=\.)[A-ZÀ-Ü]\w*', tokens.Name)`. The lexer compiles each rule and
calls `pattern.match(text, pos)` (`sqlparse/lexer.py:84`, `:153`). With
that call, a look-behind does see the text before `pos`. Whether the rule
ever fires was not verified here.

Acceptance criteria:

Given `sqlparse.lexer.tokenize("a.b")` and `tokenize("a.select")`
When the tokens are listed
Then the token after the `.` is `Name` in both, and a test asserts it.

Given that test
When the look-behind rule is removed from `SQL_REGEX`
Then either the test fails, in which case the rule stays and the FIXME is
deleted, or the whole suite still passes, in which case the rule and the
FIXME are both deleted.

Perimeter: `sqlparse/keywords.py`, `tests/test_tokenize.py`

#### sqlparse-03: Bring `validate_options` under the complexity limit

Problem: `sqlparse/formatter.py:14`, `validate_options`, has McCabe
complexity 28 (ruff 0.15.0, C901). The repository sets
`[tool.ruff.lint.mccabe] max-complexity = 31` in `pyproject.toml` to let it
pass. `tests/test_format.py` has 14 `pytest.raises(SQLParseError)` cases
that pin its behaviour.

Acceptance criteria:

Given the refactored `validate_options`
When `ruff check --select C901 --config 'lint.mccabe.max-complexity=14'
sqlparse/formatter.py` runs
Then it reports nothing.

Given every invalid option already covered by `tests/test_format.py`
When the suite runs
Then each raises `SQLParseError` with the same message as before.

Perimeter: `sqlparse/formatter.py`, `tests/test_format.py`

#### sqlparse-04: Cover the lexer's `bytes` input paths

Problem: `sqlparse/lexer.py:124-133` decodes `bytes` with an explicit
`encoding`, else UTF-8, else falls back to `unicode-escape`, and raises
`TypeError` for any other type. No test file mentions `bytes`, `decode` or
`unicode-escape`. The encoding tests (`tests/test_cli.py:76-82`) go through
the CLI, and whether they reach these lines was not verified, since no
coverage was run.

Acceptance criteria:

Given `b"select 1"` and no encoding
When it is tokenized
Then the tokens equal those of `"select 1"`.

Given bytes that are not valid UTF-8, such as `b"select '\xe4'"`
When they are tokenized with no encoding
Then no exception is raised, and the string literal is the
`unicode-escape` decoding.

Given `b"select '\xe4'"` and `encoding="latin-1"`
When it is tokenized
Then the literal is `'ä'`.

Given an `int`
When it is tokenized
Then `TypeError` is raised, and its message names the type.

Perimeter: `tests/test_tokenize.py`

#### sqlparse-05: Test `python -m sqlparse` and remove the stale CLI TODO

Problem: `sqlparse/cli.py:28` says `# TODO: Add CLI Tests`, while
`tests/test_cli.py` already has 22 tests. `sqlparse/__main__.py` (the
`python -m sqlparse` entry) is named by no test.

Acceptance criteria:

Given `python -m sqlparse -r -` with `select * from foo where bar = 1` on stdin
When it runs as a subprocess with `sys.executable`
Then it exits 0, and stdout is the reindented statement that
`sqlparse.format(..., reindent=True)` returns.

Given an unknown option
When `python -m sqlparse` runs with it
Then it exits non-zero, and stderr names the option.

Given both tests pass
When `sqlparse/cli.py` is read
Then the `Add CLI Tests` TODO is gone. The second TODO, on argparse `type`
arguments, stays.

Perimeter: `sqlparse/cli.py`, `tests/test_cli.py`

### 5.2 python-validators/validators (rank 2)

**Evidence.** Commit `22786cc6e7283a0fa452c179797e447f798db9f0`.

- MIT (`LICENSE.txt`). 1,133 stars, 27 open issues.
- Many contributors: the last 5 commits, all dated 2026-10-22, are by
  three different people and dependabot.
- CONTRIBUTING describes uv, tox and dependency groups. No AI policy.
- Init, run as is: `STACK=python`, `src/validators/`, `workbench`
  (`>=3.11`). The drafted `TEST_CMD` will fail as drafted: pytest is in the
  `testing` and `tooling` groups, there is no `dev` group, and there are no
  `default-groups`.
- The repository's own test environment (`[tool.tox.env_run_base]`) uses
  `dependency_groups = ["testing"]`, `extras = ["crypto-eth-addresses"]`
  and `pytest .`.
- Edit in `.lights-out/workload.env`, `TEST_CMD` and the test command inside
  `MUTATION_CMD`: `uv run --locked --group testing --extra
  crypto-eth-addresses pytest tests -q -p no:cacheprovider`. Unverified,
  because the suite was not run.
- 183 test functions in 31 files. `uv.lock` has 81 packages. 3,304 mutants;
  the largest files are `finance.py` (543) and `i18n/ru.py` (254).
- Plane: none, it is a library.

**Tickets.**

#### validators-01: PEP 604/585 annotations in `url.py` and `utils.py`

Problem: `requires-python >=3.11`, yet `src/validators/url.py` and
`src/validators/utils.py` import `Callable`, `Dict` and `Optional` from
`typing` (ruff UP035, UP045, UP006 at `url.py:6`, `:97`, `:175` and
`utils.py:8`, `:14`).

Acceptance criteria:

Given the two files
When `ruff check --isolated --target-version py311 --select UP` runs on them
Then it reports nothing.

Given the full suite
When it runs
Then it passes unchanged, and no test file is modified.

Perimeter: `src/validators/url.py`, `src/validators/utils.py`

#### validators-02: The same, in `domain.py`, `hostname.py` and `ip_address.py`

Problem: ruff UP035, UP045 and UP006 at `src/validators/domain.py:8`,
`:18`, `hostname.py:61`, `ip_address.py:19` and `:48`.

Acceptance criteria:

Given the three files
When `ruff check --isolated --target-version py311 --select UP` runs on them
Then it reports nothing.

Given `tests/test_domain.py`, `tests/test_hostname.py` and
`tests/test_ip_address.py`
When the suite runs
Then they pass unchanged.

Perimeter: `src/validators/domain.py`, `src/validators/hostname.py`,
`src/validators/ip_address.py`

#### validators-03: Make every `zip()` state its length contract

Problem: ruff B905, `zip()` without `strict=`, at
`src/validators/i18n/ru.py:41`, `:50`, `:52`, `i18n/fi.py:63` and
`utils.py:40`. A length mismatch is silently truncated today.

Acceptance criteria:

Given each of the five calls
When it is read
Then it passes `strict=True` where the two sequences are equal in length by
construction, and `strict=False` where truncation is intended. The commit
message names which is which, and why.

Given `tests/i18n/test_ru.py` and `tests/i18n/test_fi.py`
When the suite runs
Then they pass. For every call made `strict=True`, a test shows that an
input of the wrong length still returns a `ValidationError`, not an
uncaught `ValueError`.

Perimeter: `src/validators/i18n/ru.py`, `src/validators/i18n/fi.py`,
`src/validators/utils.py`, `tests/i18n/test_ru.py`, `tests/i18n/test_fi.py`

#### validators-04: Return conditions directly, keeping the public results

Problem: ruff SIM103, "if cond: return True / return False", at
`src/validators/uri.py:18`, `:24`, `cron.py:71` and
`crypto_addresses/bsc_address.py:33`. At `bsc_address.py` the condition is
`re.fullmatch(...)`, a match object rather than a bool.

Acceptance criteria:

Given the four sites rewritten as a single `return`
When `ruff check --isolated --select SIM103` runs on the three files
Then it reports nothing.

Given the valid and invalid inputs in `tests/test_uri.py`,
`tests/test_cron.py` and `tests/crypto_addresses/test_bsc_address.py`
When the suite runs
Then each public validator returns exactly what it returned before: `True`,
or a `ValidationError`.

Perimeter: `src/validators/uri.py`, `src/validators/cron.py`,
`src/validators/crypto_addresses/bsc_address.py`

#### validators-05: Split `uri()` below complexity 10

Problem: `src/validators/uri.py:75`, `uri`, has McCabe complexity 12
(ruff's default limit is 10). It dispatches per scheme inline.

Acceptance criteria:

Given the refactored `uri`
When `ruff check --isolated --select C901 src/validators/uri.py` runs
Then it reports nothing.

Given `tests/test_uri.py`
When it runs
Then it passes unchanged, and every scheme branch is reached by at least
one case. Missing cases are added.

Perimeter: `src/validators/uri.py`, `tests/test_uri.py`

### 5.3 gruns/furl (rank 3)

**Evidence.** Commit `bb77c48c6735929b469954ab6e54b33e17ac5121`.

- Unlicense (`LICENSE.md`). 2,812 stars.
- A second maintainer was announced on 2026-02-21 (commit `46d9ea7`). The
  last merged pull request in the clone is from 2025-03-25. The four
  commits of 2026-10-18 touch the README and `.project/` (assets and a
  script), not `furl/`.
- No CONTRIBUTING and no AI policy.
- Init: `no stack found`, because packaging is `setup.py` and `setup.cfg`
  only. Prep, by the owner in the fork: a `pyproject.toml` whose `[project]`
  mirrors `setup.py` (name `furl`, `requires-python >=3.8`, dependencies
  `six>=1.8.0` and `orderedmultidict>=1.0.1`), with a `dev` dependency group
  holding pytest and flake8, then `uv lock`.
- After the prep, init would infer the scope `furl/` from `[project].name`.
  This was not run, since the prep does not exist yet.
- CI tests 3.8 to 3.13 and pypy-3.10; tox's `envlist` is the same plus
  `codestyle` (flake8). 77 test functions in 2 files.
- 1,460 mutants, 1,390 of them in `furl.py`.
- The debt is the textbook kind:
  - `import six` and 12 `six.` calls in `furl/furl.py`.
  - `furl/compat.py` branches on `sys.version_info[0] == 2`, `basestring`,
    an `ordereddict` fallback, and a Python 2 `__str__`.
  - ruff finds 49 issues: 18 UP031 (`%` formats), 10 B028
    (`warnings.warn` without `stacklevel`), 6 UP004, 6 UP009 and 2 UP036.

**Tickets.**

#### furl-01: Drop the Python 2 branches in `compat.py`

Problem: `furl/compat.py:16` and `:32` test for Python 2 (ruff UP036). It
defines `string_types = basestring` and imports `ordereddict` on old
versions, while `setup.py` and CI support 3.8 and later only.

Acceptance criteria:

Given `furl/compat.py`
When ruff runs with `--isolated --target-version py38 --select UP036,UP004,UP009`
Then it reports nothing, and the module still exports `string_types`,
`OrderedDict` and `UnicodeMixin`, with their Python 3 values.

Given `tests/test_furl.py` and `tests/test_omdict1D.py`
When they run
Then they pass unchanged.

Perimeter: `furl/compat.py`

#### furl-02: `metaclass=abc.ABCMeta` instead of `six.add_metaclass`

Problem: `@six.add_metaclass(abc.ABCMeta)` decorates five classes, at
`furl/furl.py:704`, `:755`, `:783`, `:1134` and `:1302`.

Acceptance criteria:

Given each of the five classes
When it is declared with `metaclass=abc.ABCMeta`
Then `furl/furl.py` contains no `add_metaclass`.

Given a subclass of one of these interfaces that leaves an
`@abc.abstractmethod` unimplemented
When it is instantiated
Then `TypeError` is raised. A test is added if none exists.

Given the existing suite
When it runs
Then it passes.

Perimeter: `furl/furl.py`, `tests/test_furl.py`

#### furl-03: Builtins for `six.iteritems`, `six.string_types` and `six.moves.zip`

Problem: `six.iteritems` at `furl/furl.py:140`, `six.string_types` at
`:1096`, `:1401` and `:1848`, and `six.moves.zip` at `:1112`. On Python 3,
`six.string_types` is `(str,)`, not `compat.string_types`, which is
`(str, bytes)`.

Acceptance criteria:

Given a test that passes a `bytes` URL to `furl.furl()` and to
`Query.load`, written before the change
When the change is made
Then the same test passes: the `isinstance` checks keep `(str,)`
semantics.

Given `furl/furl.py`
When it is searched
Then it has no `six.iteritems`, `six.string_types` or `six.moves.zip`.

Perimeter: `furl/furl.py`, `tests/test_furl.py`

#### furl-04: Remove `six` from the code and the dependencies

Problem: after furl-02 and furl-03, `six` remains in the imports
(`furl/furl.py:19-21`, `six.moves.urllib`) and in `setup.py`
(`install_requires` and `tests_require`). Depends on furl-02 and furl-03.

Acceptance criteria:

Given `furl/furl.py`
When it is searched
Then `six` does not appear, and `urllib.parse` is imported directly.

Given `setup.py`, `pyproject.toml` and `uv.lock`
When they are read
Then `six` is no longer a dependency of furl, and `uv lock --check` passes.

Given the `deps` gate
When it judges the new lockfile
Then it answers GO.

Perimeter: `furl/furl.py`, `setup.py`, `pyproject.toml`, `uv.lock`

#### furl-05: `stacklevel` on every `warnings.warn`

Problem: ruff B028 finds 10 `warnings.warn` calls in `furl/furl.py` without
`stacklevel`, for example at `:677` and `:731`. The warning points at
furl's own line, not the caller's.

Acceptance criteria:

Given each warning call
When it is read
Then it passes `stacklevel=2`, or the depth that reaches user code, and
ruff B028 reports nothing on `furl/furl.py`.

Given a test that triggers one of these warnings through the public API
When it records the warning with `pytest.warns`
Then the warning's `filename` is the test file.

Perimeter: `furl/furl.py`, `tests/test_furl.py`

### 5.4 kislyuk/yq (rank 4)

**Evidence.** Commit `a98d746b96d3e6e60d3cc6e9e38a57e5005482c6`.

- Apache-2.0. 3,002 stars.
- Single maintainer, who released v4.4.3 to v4.4.5 on 2026-10-10.
- `AGENTS.md` speaks to agents directly. Among its rules: "Do not use
  `getattr()`", "Never roll your own parser", and "Benchmark parsing and I/O
  changes before accepting them". Tickets must stay out of parsing and I/O.
- Init: `pyproject.toml found but no uv.lock`. Prep: `uv lock` in the fork.
- Tests are unittest: `Makefile` runs `python ./test/test.py -v`, with 89
  test functions in `test/test.py`. pytest's default discovery would collect
  nothing from `test.py`. `TEST_CMD` and the test command in `MUTATION_CMD`
  become `uv run --locked python test/test.py`. Unverified.
- The suite drives the CLI, which needs the `jq` binary. The workbench
  installs `jq` (`workbench/Containerfile:62`).
- `requires-python >=3.8`, so the workbench applies. 1,430 mutants.
- ruff: 10 C901. `yq` (`yq/__init__.py:269`) is at complexity 78 and
  `get_dumper` (`yq/dumper.py:65`) at 31.

**Tickets.**

#### yq-01: Resolve `TODO: is this needed?` on `flatten_mapping`

Problem: `yq/loader.py:285` calls `loader.flatten_mapping(node)` with
`# TODO: is this needed?`. PyYAML's `flatten_mapping` expands `<<` merge
keys. `test/test.py:1797-1821` already builds documents with merge keys.

Acceptance criteria:

Given a YAML document with `b: {<<: *a, c: 1}`
When `yq .` reads it
Then the output has `a`'s keys merged into `b`, and a test asserts it.

Given that test
When the `flatten_mapping` call is removed
Then either a test fails, in which case the call stays and the TODO becomes
a comment saying why, or no test fails, in which case the call is removed.
This is no parsing change and no performance change, so `AGENTS.md`'s
benchmark rule does not apply.

Perimeter: `yq/loader.py`, `test/test.py`

#### yq-02: `contextlib.suppress` in the argument parser

Problem: ruff SIM105, `try`/`except Exception`/`pass`, at
`yq/parser.py:73`.

Acceptance criteria:

Given `yq/parser.py`
When `ruff check --isolated --select SIM105` runs
Then it reports nothing.

Given `yq --help` and the existing CLI tests
When the suite runs
Then it passes unchanged.

Perimeter: `yq/parser.py`

#### yq-03: Unit tests for the TOML bridge

Problem: `yq/toml_support.py`'s public functions `tomlkit_to_json` and
`tomlkit_from_json` are named by no test. They are exercised only through
`tomlq` in the CLI tests. ruff SIM108 is at `:169`.

Acceptance criteria:

Given a TOML document with a table, an array of tables, an inline table and
a datetime
When `tomlkit_to_json(tomlkit.parse(doc))` is called
Then it returns the JSON-compatible value, asserted in a new test case.

Given that value
When `tomlkit_from_json` turns it back into a document
Then `tomlkit.dumps` of the result equals the input.

Given `toml_support.py:169`
When ruff SIM108 runs
Then it reports nothing.

Perimeter: `yq/toml_support.py`, `test/test.py`

#### yq-04: Split `get_dumper` below complexity 15

Problem: `yq/dumper.py:65`, `get_dumper`, has McCabe complexity 31. It
builds the dumper class and its representers in one function. This is the
construction of the dumper, not the stream I/O.

Acceptance criteria:

Given the refactored module
When `ruff check --isolated --select C901 --config
'lint.mccabe.max-complexity=15' yq/dumper.py` runs
Then it reports nothing.

Given the CLI tests for `-y`, `-Y`, `--indentless` and the XML and TOML
outputs
When the suite runs
Then it passes unchanged.

Perimeter: `yq/dumper.py`

#### yq-05: Test the sign handling of YAML 1.2 integers

Problem: `yq/loader.py:150`, `construct_yaml_1_2_int`, is the loader's
constructor for `tag:yaml.org,2002:int` (`:337`). It strips `_`, reads a
leading `+` or `-`, then parses `0o`, `0x` or decimal.
`test/test.py:1875-1949` covers unsigned octal and hex. No case found there
has a sign. Whether the 1.2 resolver tags `-0o17` as an int at all was not
verified.

Acceptance criteria:

Given `[-0o17, +0x1F, -0x1F, -1_000]` on stdin
When `yq .` runs
Then the JSON output is asserted by a test. If the resolver tags them as
ints, that is `[-15, 31, -31, -1000]`. If it does not, the test pins
today's strings and the commit message says so.

Given the ints case
When `sign = -1` is removed from `construct_yaml_1_2_int`
Then a test fails.

Perimeter: `test/test.py`

### 5.5 jd/tenacity (rank 5)

**Evidence.** Commit `aac059c906170ee7b6ce1aa086a226f3aded5c99`.

- Apache-2.0. 8,818 stars, 86 open issues.
- Maintainer active: 21 commits by the author in the clone since 2026-05.
  Mergify (`.mergify.yml`).
- No CONTRIBUTING and no AI policy.
- Init: `no uv.lock`. Prep: `uv lock`; CI already runs
  `uv run --python ... poe <task>`.
- The `dev` group holds pytest, tornado and trio, so init's drafted
  `TEST_CMD` should work after the lock. Unverified.
- 195 test functions in 7 files. 1,713 mutants, 895 of them in
  `__init__.py`.
- The code is clean. Its ruff config selects 28 rule families and
  deliberately ignores B008 and B905, so no ticket targets those.
- The debt is untested public surface:
  - `stop_when_event_set` (`tenacity/stop.py:78`) and `sleep_using_event`
    (`tenacity/nap.py`) are named by no test.
  - `tests/test_utils.py` has 2 tests for `tenacity/_utils.py`'s 132 lines.

**Tickets.**

#### tenacity-01: Test `stop_when_event_set`

Problem: `tenacity/stop.py:78`, `stop_when_event_set.__call__`, returns
`self.event.is_set()`. No test names it.

Acceptance criteria:

Given a `threading.Event` that is not set and
`Retrying(stop=stop_when_event_set(event))` around a function that always
raises
When another thread sets the event after the third attempt
Then retrying stops with `RetryError`, and the attempt count is at least 3.

Given that test
When `__call__` returns `not self.event.is_set()`
Then the test fails.

Perimeter: `tests/test_tenacity.py`

#### tenacity-02: Test `sleep_using_event`

Problem: `tenacity/nap.py`, `sleep_using_event`, waits on an event with a
timeout. The NOTE in the code says it may return early when the event is
set. No test names it.

Acceptance criteria:

Given `sleep_using_event(event)` with the event not set
When it is called with `0.05`
Then it returns after at least 0.05 s.

Given the event set
When it is called with `10`
Then it returns in under 1 s.

Perimeter: `tests/test_tenacity.py`

#### tenacity-03: Tests for `_utils.to_seconds` and `get_callback_name`

Problem: `tenacity/_utils.py` has 132 lines and `tests/test_utils.py` has
2 tests (`is_coroutine_callable`, `find_ordinal`). `to_seconds` and
`get_callback_name` are untested by name.

Acceptance criteria:

Given an `int`, a `float` and a `datetime.timedelta`
When `to_seconds` is called
Then it returns the seconds as a float, one assertion each.

Given a function, a bound method, a `functools.partial` and a lambda
When `get_callback_name` is called
Then the qualified name each returns is asserted.

Perimeter: `tests/test_utils.py`

#### tenacity-04: Test the async `stop` and `wait` overrides

Problem: `tenacity/asyncio/__init__.py:148-165` overrides `_run_retry`,
`_run_wait` and `_run_stop` for coroutine strategies. `async_retry_base`
(`tenacity/asyncio/retry.py`) is named by no test.

Acceptance criteria:

Given an `AsyncRetrying` whose `retry` is a subclass of `async_retry_base`
with an `async __call__`
When the wrapped coroutine fails twice, then succeeds
Then the strategy was awaited 3 times, and the result is returned.

Given that test
When `_run_retry`'s `await` is removed
Then the test fails.

Perimeter: `tests/test_asyncio.py`

#### tenacity-05: Keep the `initial` deprecation honest

Problem: `tenacity/wait.py:300-311` deprecates `initial` in favour of
`multiplier`, and raises if both are given.
`tests/test_tenacity.py:734` tests the warning. Nothing tests the
`ValueError` or the value carried over from `initial`.

Acceptance criteria:

Given `wait_exponential_jitter(initial=2, multiplier=3)`
When it is constructed
Then `ValueError` is raised, and its message names both parameters.

Given `wait_exponential_jitter(initial=2, jitter=0)`
When it is constructed and called for attempt 1
Then it warns with `DeprecationWarning`, and its wait equals that of
`multiplier=2`.

Perimeter: `tests/test_tenacity.py`

### 5.6 jmespath/jmespath.py (rank 6)

**Evidence.** Commit `2812594e69d43098ef60f81f4efc404c071b0418`.

- MIT. 2,457 stars, 90 open issues.
- A dependency of botocore, hence of every boto3 install: very wide real
  use. That fact is from general knowledge, not from this clone.
- The last commit is 2026-01-22 (release 1.1.0). Maintenance is slow, and
  whether a PR would be read is the open question.
- No CONTRIBUTING and no AI policy.
- Init: `no stack found` (`setup.py`, `setup.cfg`, `requirements.txt`).
  Prep: a `pyproject.toml` (name `jmespath`, `requires-python >=3.9`, a
  `dev` group from `requirements.txt`: `pytest==8.4.1`, `pytest-cov==3.0.0`,
  `hypothesis==5.35.4`), then `uv lock`.
- CI runs `cd tests/ && python -m pytest --cov jmespath`. Running from the
  root (`pytest tests`) was not verified, since `test_compliance.py` locates
  its data with `os.path` relative to the test file.
- 74 test functions in 7 files, plus JSON compliance suites. 1,409 mutants.
- Debt:
  - `jmespath/compat.py` keeps no-op shims (`with_str_method`,
    `with_repr_method`, `text_type = str`), imported by four modules.
  - ruff finds 52 issues: 23 UP031, 6 UP008, 6 UP004, 3 B020 in
    `visitor.py`, and 3 B904.
  - The pinned test dependencies are old: `hypothesis==5.35.4`,
    `pytest-cov==3.0.0`.

**Tickets.**

#### jmespath-01: Inline the no-op compat shims

Problem: `jmespath/compat.py` defines `with_str_method` and
`with_repr_method`, which return the class unchanged, and
`text_type = string_type = str`. They are imported at
`jmespath/exceptions.py:1`, `functions.py:5-6`, `parser.py:29` and
`visitor.py:4`.

Acceptance criteria:

Given the four importing modules
When the shims are replaced by what they do (nothing, or `str`)
Then `compat.py` keeps only `get_methods`, or `get_methods` moves to
`functions.py`, and every decorator use is gone.

Given the compliance suites and `tests/`
When they run
Then they pass unchanged.

Perimeter: `jmespath/compat.py`, `jmespath/exceptions.py`,
`jmespath/functions.py`, `jmespath/parser.py`, `jmespath/visitor.py`

#### jmespath-02: f-strings in the exception messages

Problem: `jmespath/exceptions.py` builds its messages with `%` (ruff UP031,
6 sites) and calls `super(Class, self)` (UP008, 3 sites).

Acceptance criteria:

Given each exception class
When it is rendered with `str()` for the inputs already used in
`tests/test_parser.py` and `tests/test_lexer.py`
Then the message text is byte-for-byte what it was. A test pins the
messages first.

Given `jmespath/exceptions.py`
When ruff runs with `--isolated --target-version py39 --select UP031,UP008`
Then it reports nothing.

Perimeter: `jmespath/exceptions.py`, `tests/test_parser.py`

#### jmespath-03: `raise ... from` in the lexer

Problem: ruff B904 at `jmespath/lexer.py:172` and `:188`. A `LexerError`
is raised inside `except ValueError` without `from`, so the chained
traceback reads "During handling of the above exception, another exception
occurred". Line 172 is a backtick literal that is not valid JSON even when
quoted; line 188 is a quoted identifier that is not valid JSON.

Acceptance criteria:

Given one expression for each of the two cases
When `jmespath.compile` raises `LexerError`
Then `__cause__` is the original exception, or is `None` with
`__suppress_context__` set, asserted by a test.

Given `jmespath/lexer.py`
When ruff B904 runs on it
Then it reports nothing.

Perimeter: `jmespath/lexer.py`, `tests/test_lexer.py`

#### jmespath-04: Rename the loop variables that shadow their iterable

Problem: ruff B020 at three sites in `jmespath/visitor.py`: a loop variable
named `node` overrides the `node` it iterates.

Acceptance criteria:

Given the three loops
When the loop variable is renamed
Then ruff B020 reports nothing on `visitor.py`.

Given the compliance suites
When they run
Then they pass unchanged.

Perimeter: `jmespath/visitor.py`

#### jmespath-05: Format strings in the parser's error paths

Problem: `jmespath/parser.py` has 6 UP031 sites. Four build error messages
(`:126`, `:292`, `:443`, `:497`). Two build the method names the parser
looks up with `getattr` (`:133`, `:138`).

Acceptance criteria:

Given the parser's error messages for the invalid expressions in
`tests/test_parser.py`
When the `%` formats become f-strings
Then each message is unchanged, asserted by a test.

Given the compliance suites
When they run after the two `getattr` names are rewritten
Then they pass unchanged.

Given `jmespath/parser.py`
When ruff UP031 runs on it
Then it reports nothing.

Perimeter: `jmespath/parser.py`, `tests/test_parser.py`

## 6. Findings that hold whatever the owner picks

1. **No candidate's whole-scope baseline finishes in minutes.** The
   smallest scopes in the pool are 1,094 mutants (httpbin) and 1,409
   (jmespath). The runner mutates one directory, which `mutation.sh`
   requires, and cosmic-ray's `local` distributor runs one mutant at a
   time. At the app's measured 3.9 s per mutant that is 1.2 h and more.
   Two consequences:
   - The baseline is measured once per repository (`./go init`, `./go
     mutation-baseline`). Per ticket, the gate mutates only the changed
     lines (`MUTATION_LINES`), so a ticket like the ones above is tens of
     mutants, not thousands.
   - §14 already says to measure cosmic-ray's time on the first ticket.
     Before running it, the owner decides whether a one-off baseline of
     1.5 to 3.5 h is acceptable, or whether the runner needs a parallel
     distributor first, which would be a platform change with its own ADR.
     The first real `./go init` on the chosen repository is the measurement
     that replaces this extrapolation.
2. **Prep is a human commit.** Four of six need `uv.lock`, and two also
   need a `pyproject.toml`. The experiment's claim is that no human touches
   the code in a ticket. A prep commit on packaging only, made before
   ticket 1 and published as such, does not contradict that. It should
   still be named in the diary, and a PR sent upstream from the fork carries
   it unless it is rebased out. sqlparse needs none, and validators needs
   only an edit inside `.lights-out/`.
3. **No candidate has a plane.** All six are libraries. The experiment will
   prove assign → gates → PR → review → merge on foreign code, not the
   canary and rollback. The only service in the pool, httpbin, is frozen.
   Writing a plane (a `/healthz` and `/metrics` wrapper) for a library
   would be the owner's code, not the repository's.
4. **An init defect, found while reading** (not fixed: this branch is
   docs only). `core/init.py`'s `node_admits` splits a range on whitespace
   before matching the operator. So `engines.node = ">= 20"`, with a space,
   which npm accepts, is "admits none of the node majors init knows". This
   is marked's refusal. validator.js's `">= 0.10"` would fail the same way
   if it had a lockfile. Reproduced by calling `node_admits(">= 20", 24)`
   (False) and `node_admits(">=20", 24)` (True). `python_admits` does not
   have the flaw (`">= 3.10"` admits 3.13).
5. **Upstream PRs are the owner's act, under each project's policy.** At L1
   with `CODE_HOST=github`, the PR opens on the owner's fork (ADR 0043).
   Sending it upstream is a separate, human step. sqlparse's PR template
   asks for tests and `ruff`. validators has no PR template. None of the
   six asks for disclosure, but disclosing that the change was made
   by lights-out, with a link to the audit chain, is what the diary will
   say anyway.
6. **Python versions.** The workbench is Python 3.13. All six admit it, and
   their CI matrices cover 3.13. A ticket's green gate is evidence on 3.13
   only. A PR upstream also has to pass their matrix, which goes down to
   3.8 for furl, 3.9 for jmespath and 3.10 for the other four.

## 7. Recommendation

**sqlparse, with validators as the second repository if the owner wants
two.**

- sqlparse is the only candidate that meets every checklist line without a
  commit before ticket 1:
  - `uv.lock` committed and pytest in the default `dev` group, so init's
    draft is usable as is.
  - It states, through `AGENTS.md`, `CLAUDE.md` and AI review, that it
    expects agent-written code.
  - It has real users and an active maintainer.
  - Its debt is visible in its own TODOs and in its own `max-complexity =
    31`.
- Its cost is the largest whole-scope baseline among the zero-prep
  candidates, ~3.2 h extrapolated. That cost is paid once.
- validators also needs no commit, only a `TEST_CMD` edit inside
  `.lights-out/`. Its many contributors suggest PRs get read. Its
  tickets are the most mechanical in the batch.
- furl has the most legacy debt, and makes the best story for a talk
  ("removing `six` from a library with 2,800 stars"). It is the pick if the
  owner values the story over zero prep, at the price of a packaging commit
  and a maintainer whose last merge was in 2025.

Before the first ticket, whatever the pick:

- Run `./go init` on the fork and record the real baseline time, which
  replaces section 3's extrapolation.
- Run `./go gates` once, to see whether the committed lockfile already
  carries an advisory.
- Then run sqlparse-01, the smallest ticket, with the three providers.
