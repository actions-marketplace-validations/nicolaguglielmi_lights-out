# lights-out docs

Where to read what. Everything here is in English except `PLAN.md`.

## Start here

| Document | Read it when |
|---|---|
| [README](../README.md) | You want the pitch, the install table and `./go demo` in five minutes. It also says what is real, what is recorded and what is hand-written. |
| [Tutorial](tutorial.md) | You have an hour. The demo read stage by stage, the short looks, the gates on your own repository, a ticket at L1, and the ops commands, each with output taken from this repository's CI runs. |

## Using it

| Document | Read it when |
|---|---|
| [Use it on your own codebase](use-on-your-repo.md) | You are putting your repository behind the gates: every key of `.lights-out/` and its provenance, the plane half, `policy.env`, tickets, the GitHub Action and the hook recipes for coding agents. It opens with what is proven and what is not. |
| [Reference](reference.md) | You need one command, one level or one service: the status by milestone, every `./go` target, the levels L0 to L3, the L0 plane, the release controller, the PR gates, how `./go` runs, the repository layout. |

## How it is built

| Document | Read it when |
|---|---|
| [Architecture](ARCHITECTURE.md) | You want the ports and their adapters, and how the levels compose. |
| [Decisions (ADRs)](adr/) | You want to know why something is the way it is. One file per structural decision, numbered, each with the alternatives it rejected. |

## The launch

| Document | Read it when |
|---|---|
| [Launch checklist](launch/checklist.md) | You want what is left before the repository goes public, split between the owner's steps and the repository's. |
| [Good first issues](launch/good-first-issues.md) | You want a first contribution: issue drafts, each from a real finding. |

## Working documents

- [PLAN.md](PLAN.md): the owner's working plan, in Italian. It is the brief
  for every milestone, with dated status notes.
- [plans/](plans/): file-by-file plans and reports written for single
  milestones.
- [ROADMAP](../ROADMAP.md), [CONTRIBUTING](../CONTRIBUTING.md) and
  [SECURITY](../SECURITY.md) are at the repository root.
