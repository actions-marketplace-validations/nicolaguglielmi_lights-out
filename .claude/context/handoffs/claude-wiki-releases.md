# Handoff: the wiki rendered at the tag (ADR 0077), 2026-11-12

Branch `claude/wiki-releases-4fda66`, cut from `origin/main` at 472a1fc. It is pushed with no pull request. Nothing is merged, tagged or pushed to the wiki. The coordinator merges.

## What changed

- **ADR 0077, "The wiki is rendered from the repository at the tag, never edited by hand".** It rejects a hand-kept wiki, GitHub Pages only, no wiki, a third-party wiki Action, rendering on every push to `main`, and a fine-grained token as a secret. It amends ADR 0075 §1 (a sixth job) and ADR 0065 §1 (the `plan` exemption), with a note in 0075's header.
- **`package/wiki.py OUT`** renders ten files, from the repository only:

  | page | source |
  |---|---|
  | `Home` | `README.md` |
  | `Tutorial` | `docs/tutorial.md` |
  | `Use-it-on-your-own-codebase` | `docs/use-on-your-repo.md` |
  | `Reference` | `docs/reference.md` |
  | `Production` | `docs/production.md` |
  | `Architecture` | `docs/ARCHITECTURE.md` |
  | `Decisions` | one row per `docs/adr/NNNN-*.md` |
  | `Releases` | the wrapper's `version=` and `docs/releases/v*.md`, newest first |
  | `_Sidebar`, `_Footer` | the page list; the tag and "generated" |

  Each page from a document opens with one line naming it at the tag. The rest is the document with its link targets rewritten: a page's source becomes its absolute wiki URL (a relative one breaks on `Home`, served at `/wiki`), `docs/adr/` becomes `Decisions`, and anything else becomes `raw/`, `blob/` or `tree/` at `v<version>`. Fenced code is copied as it is. A relative link to a missing path stops the rendering.
- **`package/sync-wiki.sh PAGES DIR [--push]`** clones the wiki, replaces every file with the pages, and commits as the owner's noreply identity. It pushes only with `--push`, and pushes nothing when the pages are unchanged. A wiki with no repository fails with a message naming the Wiki tab's first page. `WIKI_TOKEN` goes to git through `GIT_CONFIG_*`, as in `sync-action.sh`.
- **`package.yml`, job `wiki`**: it needs `release`, has the github.com guard, and holds exactly `contents: write`. It renders on every ref. On a `v*` tag it pushes with `WIKI_TOKEN: ${{ github.token }}`, and on a dispatch it only prints the push. There is no new secret.
- **`ci/wiki.sh`**, `wiki` in `CI_CHECKS` before `contract`, is written from the ADR and checks four things:
  - **render**: the repository renders exactly the ten pages, each body equals its source with targets blanked, no relative target is left, wiki and tag links resolve, there is one Decisions row per ADR, and two renderings are equal.
  - **fixture**: a small tree produces each link form of §3, Releases newest first, and a missing path refused.
  - **sync**: against local bare repositories.
  - **workflow**: the job's shape, as YAML.

  Each judge is shown to fail: 10 workflow cases and 13 planted script edits.
- **`ci/plan.sh`** exempts `wiki` with the other release jobs.
- **Docs**:
  - `docs/launch/checklist.md`: a new section "The wiki (ADR 0077)" with the owner's steps, and a row in "Done in the repository".
  - `docs/reference.md`: the release paragraph names the wiki.
  - `docs/README.md`: one paragraph.
  - The README does not link the wiki yet, because it is empty until the next tag.

## Verified

- On the host: `sh ci/wiki.sh` GO, `sh ci/plan.sh` GO, `sh ci/release.sh` GO, `shellcheck -s sh` clean, and docs-drift GO with `MAP_EXCLUDE='docs/PLAN.md docs/plans/* .claude/*'`.
- `./go ci` from a clean clone under `.crew/`, and the branch's workflows: see the coordinator note in the shared notes folder (`wiki-releases-notes.md`).

## Not verified, and why

- **That `GITHUB_TOKEN` can push to `lights-out.wiki.git`.** GitHub's docs do not say. The evidence is third-party: the `Andrew-Chen-Wang/github-wiki-action` README, and PRs that fixed a 403 with `contents: write`. It cannot be tried before the wiki exists, and pushing to the wiki was out of scope. The first tag tests it. A 403 in `wiki` means a token and an amendment. By then the rest of the release is already drafted.
- **How the pages look on github.com.** Absolute links and heading anchors follow GitHub's markdown, but nobody has seen them rendered as a wiki.

## The owner's steps, once, before the next tag

1. Wiki tab → "Create the first page" → Save. GitHub creates the wiki's repository only then.
2. Keep Settings → Features → Wikis → "Restrict editing to collaborators only" ticked (the default).
3. After the tag, read the `wiki` job.

## Merge conflicts to expect

- `Makefile` `CI_CHECKS`: `wiki` sits between `release` and `contract`.
- `ci/plan.sh`: the `RELEASE` set and its comment.
- `docs/launch/checklist.md`: the new section after "Release automation" and its "Each release" list, plus one row in the table.
- `package.yml`: the header comment ("six jobs") and the job appended at the end.
