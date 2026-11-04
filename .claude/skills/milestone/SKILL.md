---
name: milestone
description: Run one milestone of the lights-out implementation plan end to end, from reading the acceptance criteria to leaving the repo green. Use when the user says /milestone followed by a milestone id such as M0, M3 or M7.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task, WebSearch, WebFetch
---

# Milestone

Run milestone **$ARGUMENTS** of `docs/PLAN.md`. One milestone per session. Do not start the next one.

## 1. Frame it

Read the milestone in section 7 of `docs/PLAN.md`, plus sections 2, 3 and 4 for the rules it has to respect.

Restate, in under ten lines:

- the deliverables
- the acceptance criterion, verbatim, in the form of the command that proves it
- what is explicitly out of scope for this milestone

Stop if the acceptance criterion is not mechanically checkable. Say why and propose a version that is.

## 2. Plan, do not write

Stay read-only until the plan is approved. Produce a file-by-file plan: what gets created, what gets modified, what gets deleted.

Delegate to the `architect` subagent anything that adds a package, an abstraction, an adapter, or a dependency. Wait for the ADR before planning around it.

Then stop and wait for approval. Do not touch a file before it comes.

## Models and effort per task

Plan §5 fixes the construction models; `docs/plans/third-arc-execution.md`
assigns them per milestone. When you delegate, pass the effort below.

| Task | Subagent | Effort |
|---|---|---|
| ADR, structural decision | `architect` (opus) | high |
| Gates, ci checks, tests from the spec | `gate-writer` (sonnet) | medium |
| README, docs, commit messages | `doc-scribe` (haiku) | low |
| A cross-cutting problem the session has missed twice | a one-shot task on fable | xhigh |

## 3. Build

- Delegate tests, gates and the verify query to the `gate-writer` subagent.
- Delegate README, docs and commit messages to the `doc-scribe` subagent.
- Keep the main session for the integration work.

Smallest change that satisfies the criterion. If you find yourself building for a future milestone, stop and remove it.

## 4. Prove it

Run the acceptance command on a clean container. Paste the real output. If it fails, fix and run it again; never describe a result you have not seen.

Then run `make demo` for the whole repo. A milestone that breaks the demo is not done, whatever else works.

## 5. Hand off

Close the session with:

- the acceptance command and its output
- what changed, in five lines
- anything you found that contradicts `docs/PLAN.md`, which is more valuable than the code
- the first thing the next milestone should look at

Write this to `.claude/context/HANDOFF.md`, commit, and remind the user to clear the context before starting the next milestone.
