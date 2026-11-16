# Handoff: M64, from zero to hero and a start with nothing installed (ADR 0097)

Branch `claude/m64-zero-to-hero-214bf3`, pushed, not merged, no PR. No live LLM run, no API spend. The plane was
never started on this Mac (the shared slot stayed free on rootless and rootful podman); every plane run is on GitHub
Actions.

## Acceptance

| Criterion | Result |
|---|---|
| `./go ci` from a full clone under `.crew/` | `GO: ci` at aa45508, 57 GO lines and no NO-GO, `GO: zero-to-hero` among them, 532 s on this Mac (load ~11), clone `.crew/m64` |
| `./go demo` green | stranger run 43969827161, job demo 133660201322 (podman): `GO: demo, milestone M9, 511s to rollback`; ci run 43969827123, job engine-compat 133660321700 (docker): `682s to rollback` |
| the dev container job, timed | `GO: demo, milestone M9, 668s to rollback` at aa45508 (stranger run 43969827161, job codespace 133660201332, 22:30:08–22:42:17Z); first run 669 s at f205507 (run 43968199663, job 133653156720), container built in 57 s |
| every workflow green | aa45508 (the last code commit): ci 43969827123, stranger 43969827161, self 43969827384, podman 43969827166, package 43969827388, site 43969827312, all success; the commits after it are docs only |

## What changed, in five lines

1. **ADR 0097**, then `ci/zero-to-hero.sh` (logic `ci/checks/zero_to_hero.py`, 36 tests in `ci/tests/test_zero_to_hero.py`,
   written from §5 and committed red before the docs), on `CI_CHECKS` after `first-run`.
2. **The path** opens `docs/tutorial.md`: seven levels, each with Time, You need, You will see, Go deeper and one verdict
   line from a real run with its source comment. The tutorial's sections lost their numbers.
3. **README**: "Five ways in" and "0. Look" removed; "From zero to hero" (a table linking each level) after a new
   "Quick start" (the former "2. The whole loop", now with the Codespaces badge and its quota sentence); the other
   numbered headings lost their numbers (anchors fixed in the site, the guide and the tutorial).
4. **`.devcontainer/devcontainer.json`** (base 3.0.13-noble by digest, docker-in-docker 4.1.3, `CONTAINER_ENGINE=docker`,
   4 CPUs / 8 GB / 32 GB, 8098/8080/3000/9090 forwarded) and the `stranger` workflow's `codespace` job
   (`devcontainers/ci` at 513af61, `./go demo` inside, timed).
5. **The site's hero**: "See it in 10 seconds" (the frozen console on ticket 0001) first, then "Run it", then "Try it on
   your repo"; the tour moved into the note line; "Try it" gained the Codespaces paragraph. Reference row and paragraph,
   PLAN entry in Italian.

## Measured times per level

| Level | Time in the guide | Measured | Source |
|---|---|---|---|
| 0 | 1 min | the page and one click; the snapshot is 1.4 MB | the site's console/snapshot.html, frozen from ci run 43501367427 |
| 1 | about 10 min | 427 s and 511 s (podman, clean runner); 668–669 s in the dev container, plus 57 s to build it | stranger runs 43925636189 (job 133504261420), 43969827161 (jobs 133660201322, 133660201332), 43968199663 (job 133653156720) |
| 2 | about 15 min | `./go try` 40 s first, 14 s warm, on this Mac (load ~11); the Action 37 s on the probe | local, commit f205507; lights-out-probe run 42591256328 |
| 3 | about 30 min | `./go intake` 7 s, two `./go answer` 4 s and 8 s | local, commit f205507 |
| 4 | 1–2 h | `./go demo-seam`'s six steps 212 s | ci run 43925636171 job seam 133504261637 |
| 5 | about 30 min | not run (key and spend); tenacity-03's dev-worker 70 s, live on Anthropic | M24 handoff §6, 2026-11-11 |
| 6 | it depends | Flagger 726 s, GitLab CI 309 s, Jenkins 154 s | ci run 43925636171 |

## What was removed from the docs

- README: the "Five ways in" table (5 rows), the "0. Look" section, and the numbers of its four step headings.
- Tutorial: the five-step list and its two lines on keys (replaced by the levels), the numbers of its six sections;
  two outdated "not proven" bullets corrected from `docs/scoreboard/m24-tenacity.json` (Claude Code ran live on
  tenacity, 10/10 merged; Codex never ran against its API), and the "nothing in this section has real output" line.
- No new document: the path is the tutorial's opening.

## The site's first screen

Screenshots in the notes folder (`m64-shots/`): `site-first-screen-1440-dark.jpg`, `site-first-screen-1440-light.jpg`,
`site-first-screen-390-dark.jpg`. The site keeps one dark palette under both colour schemes, so the two desktop shots are
the same page; measured rendered in Chromium, every hero text node at least 5.27:1 in both (18 nodes, WCAG AA 4.5:1),
no horizontal scroll at 390 px. The site workflow's own stills of aa45508 (site run 43969827312, artifact `site-review`) are copied there as `ci-desktop-1-hero.png`, `ci-phone-1-hero.png`, `ci-desktop-7-try.png`, and the console the first button opens, `ci-snapshot-ticket-0001-dark.png` and `-light.png`: that page follows the visitor's scheme.

## Found, against the plan or the docs

- **`./go intake-confirm` needs the plane.** It confirms, opens the ticket through the spec gate, then assigns it, and the
  assign pushes to Gitea: on a clone with no plane it ends `NO-GO: intake-confirm — a step failed` after `GO: spec`
  (`bootstrap-gitea: … /var/run/docker.sock`). The tutorial's intake section says "No plane is needed"; level 3 now says
  to confirm with the plane up. The intake section itself still needs that sentence fixed.
- **README "What is real" is behind M24**: "the first live run on Claude … Nothing merged" and "nothing is proven yet on a
  codebase that was not written for lights-out" predate M24's 10/10 on tenacity. Not changed here.
- **No workflow runs `./go try`**: level 2's output is a local run. A `try` step in `stranger` would make it a CI capture.
- The site's frozen console is from ci run 43501367427 (2026-11-13): the site rebuilds it only on a push that touches its
  paths on main.
- `docs/use-on-your-repo.md`'s anchor `#the-eleven-keys` in the tutorial was broken (the heading is "The twelve keys"):
  fixed.

## The first thing the next milestone should look at

A codespace on the owner's account, once: press the README's button, run `./go demo`, then `./go console` on the
forwarded 8098. CI proves the container, not Codespaces' VM.
