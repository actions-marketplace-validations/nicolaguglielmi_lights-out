# lights-out

![lights-out: six agents ship it, one human turns the lights back on](docs/assets/lights-out.jpg)

**[The site](https://nicolaguglielmi.github.io/lights-out/)** explains it in five steps, with [a video tour](https://nicolaguglielmi.github.io/lights-out/media/overview.mp4) and a clip per scenario, all rendered from [the board](board/index.html).

**The safety system for a dark factory of AI coding agents.** A lights-out factory runs in the dark because its safety systems are trusted. lights-out is that system, the guardrails for agents that write and ship code, with Claude Code, Gemini CLI or Codex at the keyboard.

**Autonomous agents take a ticket to production on a codebase you do not trust. Numeric gates decide, the ticket's perimeter holds, a failing canary rolls itself back, and one human approves the last step.**

It runs complete on your laptop: no account, no API key, no cloud.

| | |
|---|---|
| **Six gates on every PR** | risk, secrets, dependencies, static analysis, tests, mutation. Each prints one line, `GO` or `NO-GO` with the reason, and every threshold says where it comes from. A PR is judged by its base's policy, never its own. |
| **A perimeter per ticket** | the diff must stay inside the files the ticket declares, checked before a PR exists. |
| **A canary that rolls itself back** | one signed image per merge, 5% then 25% of real traffic, compared with stable on errors and p95 latency. A bad number rolls it back with nobody paged. |
| **One human gate** | the step to 100% waits for a person's GO. Silence never promotes. |
| **Your model, your coding CLI** | Gemini, Claude or OpenAI, through `gemini-cli`, `claude-code` or `codex`, all behind the same guard; on Gemini, Antigravity CLI too (`antigravity-cli`, experimental) ([coding harnesses](docs/reference.md#coding-harnesses)). |
| **Gates on your repository** | `./go init` drafts the contract from your repository and `./go gates` judges your last commit, with no plane and no key. |
| **Ops, too** | an alert becomes ranked hypotheses; an incident becomes a post mortem anchored to the audit chain, with each action item a ticket. |

What is proven and what is not yet is said plainly below, in [What is real and what is recorded](#what-is-real-and-what-is-recorded).

## Try it

**1. Install a container engine (once)**

| Your machine | Run |
|---|---|
| macOS | `brew install podman`<br>`podman machine init --cpus 4 --memory 6144`<br>`podman machine start` |
| Linux | `sudo apt-get install -y podman` (Debian, Ubuntu) or `sudo dnf install -y podman` (Fedora), then<br>`systemctl --user enable --now podman.socket` |
| Docker on Linux | start Docker and put `CONTAINER_ENGINE=docker` before every `./go` (what CI runs) |

**2. Clone and run**

```sh
git clone https://github.com/nicolaguglielmi/lights-out.git
cd lights-out
./go demo
```

**3. Watch**

- An agent turns a ticket into a pull request.
- Six gates judge it: risk, secrets, dependencies, static analysis, tests, mutation.
- It merges, builds and signs a release, and sends it 5% of the traffic.
- Verify sees the errors and rolls the canary back on its own. No human involved.
- The run ends with `GO: demo`, then prints where to open the app, Gitea and Prometheus.

The first run downloads about 1.2 GB and builds the toolchain image (3–6 minutes), so expect 10–15 minutes. After that a run takes about 7 (measured: 434 s on a MacBook with podman).

**Shorter looks**

```sh
./go demo-triage     # an alert becomes ranked hypotheses, 3 seconds, nothing to start
./go incident        # build an incident document from the last release record: NAME= FROM= TO= [LOGS=<file>] [TICKET=<id>]
./go postmortem INCIDENT=<file>   # an incident document becomes a post mortem and tickets
./go demo-postmortem # replay the post mortem of the demo-rollback incident (needs a recording, see below)
./go record-postmortem PROFILE=l1 # record that answer once, with your Gemini key
./go up              # start the local plane (about 15 s once downloaded)
./go demo-rollback   # just the self-rollback, about a minute
./go board           # the pipeline explained, and live while the plane runs: localhost:8099
./go map             # the project map: tickets, files, tests, ADRs and pages of one commit, in .crew/map.sqlite
./go console         # the client's view: each ticket's timeline from request to release, post mortems, thresholds, go-for-launch: localhost:8098
./go request TICKET=<id>   # start a ticket before the code: the product role asks or confirms, then the spec gate
./go answer TICKET=<id> ANSWER="<text>"   # answer its open question, then the product role again
./go down            # stop everything
```

**Ops without the plane**

An incident document holds the alerts, the release record, a log excerpt and the time window. `./go postmortem` turns it into a post mortem in `.crew/postmortem/<name>/`. Each timeline entry is anchored to an id the document holds (the release, a stage, a log line, an alert, and the PR or ticket when the tower released it), and core prints that evidence beside it. Every action item is filed as a ticket in `tickets/`. The ticket has no perimeter: a human adds one before `./go assign`. An anchored timeline is not a true one: the check stops invented releases and log lines, not a wrong story about real ones.

To judge your own metrics, run `./go verify METRICS_URL=<any Prometheus-compatible endpoint> CANARY_VERSION=<v> STABLE_VERSION=<s>`. It uses the unchanged `verify/slo.promql`. "Any Prometheus-compatible endpoint" means one that answers `/api/v1/query` with the OTel HTTP semconv histogram joined to `target_info{service_version}`. On other metrics the answer is NO-GO with "no data". An auth header goes in `.env` as `METRICS_AUTH_HEADER`.

## If something goes wrong

Run `./go doctor` first. It prints one line per item: the engine and whether it answers, the podman API socket, git, whether the workbench image is built, whether the plane's ports (3000, 5050, 8016, 8085, 8086, 9090, 9901 and `APP_PORT`) are free or held by the lights-out plane, and whether the key your profile needs is set in `.env` (the name, never the value). It ends with `GO: doctor` or `NO-GO: doctor — <items>`. `./go` also checks your engine before it builds anything and prints the command that fixes what is missing. The other cases:

| You see | Do this |
|---|---|
| A port is already in use | Put `APP_PORT=9000` in a file named `.env` for the app port. Ports 3000, 5050, 8016, 8085, 8086, 9090 and 9901 must be free. |
| `Cannot allocate memory`, or everything crawls | `podman machine stop`, `podman machine set --memory 6144`, `podman machine start` |
| `GO: demo … a first run: over the 900s budget, reported, not judged` | Everything worked; the first download and the toolchain build were slow. Your first run reports its time instead of failing on it. Later runs and CI are judged against the 900 s ([ADR 0013](docs/adr/0013-launchpad-canary-verify-rollback-at-l0.md), amendment 2026-11-04). |
| `NO-GO: demo — rollback reached, but … > 900s budget` | Everything worked, but a run after the first one took longer than 900 s. The engine is usually short of memory or CPU (see the row above), or other containers are running. `./go down`, then `./go demo` again. |
| Anything else | `./go down`, then `./go demo` again. Still stuck? Open an issue with the last 30 lines. |

## On your own repository

From a clone of lights-out:

```sh
./go init ~/code/your-repo   # attaches a clone of its HEAD and drafts the gates half of .lights-out/ in the clone
./go gates                   # judges the last commit: no plane, no key, no engine socket when the toolchain is the workbench
```

`./go init` never writes to your repository. It infers the stack from the files at the root (python or javascript), and writes `workload.env` with a provenance line over every value, plus `worker.md`, `policy.env` and the stack's runners. It measures `MUTATION_BASELINE` by running the mutation command over the whole scope. Its last line gives the stack, the draft's location and the baseline. Copy `.attached/.lights-out/` into your repository and commit it.

A toolchain gate's GO line says where it ran: `in workbench`, or the image or service the contract names. On the workbench, `./go gates` runs your repository's tests in lights-out's toolchain container, on this machine. Attach only a repository you would run here.

**Without cloning lights-out, from inside your repository.** The `lights-out` wrapper runs the same init and gates from the published image, `ghcr.io/nicolaguglielmi/lights-out:0.1.0` (amd64 and arm64). You need podman or docker, and git. The first run pulls the image, about 1.8 GB unpacked.

```sh
mkdir -p ~/.local/bin   # any directory on your PATH
curl -fsSL -o ~/.local/bin/lights-out https://raw.githubusercontent.com/nicolaguglielmi/lights-out/v0.1.0/lights-out
chmod +x ~/.local/bin/lights-out
```

```sh
cd ~/code/your-repo
lights-out doctor                  # engine, image, key: one line each
lights-out init                    # drafts .lights-out/ outside your repository
cp -R ~/.local/state/lights-out/your-repo/.lights-out/. .lights-out/
git add .lights-out && git commit -m "add lights-out contract"
lights-out gates                   # judges the last commit
```

Tags are mutable and the image is unsigned: to pin it, set `LIGHTS_OUT_IMAGE=ghcr.io/nicolaguglielmi/lights-out@sha256:d1a227d4b3ebfa47b0c21268276279ee80e5c7ffdc345e4cde49ae866e8cc840`. `lights-out init` prints where the draft is. `LIGHTS_OUT_OUT` moves it. Keep the `/.` in the `cp` command: without it, `cp -R` into an existing `.lights-out/` nests the draft one level deeper. The wrapper mounts your repository read-only and never gives the image your engine's socket. `lights-out gates` judges the last commit, a range (`BASE=` and `HEAD=`), or what is staged (`STAGED=1`). It works with `TOOLCHAIN_IMAGE=workbench` only; a `compose:` or image form is judged from a clone with `./go gates`.

The plane comes next: attach, up, smoke, verify and rollback on your repository. It needs more of the contract: a compose file, a flag file, and smoke and load scripts.

What works today, and what does not yet:

- **Works:** the eight gates on the gates half alone. With the plane half, the canary and its rollback on your stable image, judged by the thresholds you set in `.lights-out/policy.env`. A change to `.lights-out/` never merges on its own.
- **Time:** `./go demo-init` proves init and gates in under 300 s on two small example repositories. Init measures the whole scope, so a large suite takes longer.
- **Needs a model key.** There are no recordings of your code, so on your repository the agents run at L1 only, and say so at L0: `GEMINI_API_KEY` for the coding roles (the free tier), or `AGENT_HARNESS=claude-code` with `ANTHROPIC_API_KEY`, or `AGENT_HARNESS=codex` with `OPENAI_API_KEY` (with `MODEL_PROVIDER` and `MODEL`; the ADK roles take the same keys). The dev-worker may spend up to 2.6M tokens per run (`roles/dev-worker/role.env`).
- **Release and pull requests at L1.** A merged change is built from your repository's own Containerfile, signed and released on the local plane. By default merges land on the plane's Gitea and you `git fetch` them back; with `CODE_HOST=github` and a token in `.env` the pull request lands on your GitHub repository instead. Both are implemented and not yet run end to end on a repository of yours ([ADR 0043](docs/adr/0043-github-code-host-and-attached-release.md)). There is no deploy to your production.
- **Delivery on Kubernetes, opt-in.** If you already ship with Argo Rollouts, `DELIVERY=argo-rollouts` drives your Rollout with kubectl, stage by stage, instead of Envoy. It needs a traffic router and a Rollout with the steps [its README](adapters/argo-rollouts/README.md) lists. `./go argo-conformance` proves it with the same conformance suite, on a k3s node beside the plane; under podman that needs a rootful engine. It has not been run on a cluster of yours yet ([ADR 0051](docs/adr/0051-delivery-on-kubernetes-with-argo-rollouts.md)).

[The guide](docs/use-on-your-repo.md) says what `.lights-out/` holds, what each key says, what the plane needs, how to write tickets, the hook recipes for coding agents and the GitHub Action.

## What is real and what is recorded

- **Real:** the gates, the signed build, the canary, the metrics, the rollback and the audit chain. Nothing in them is simulated.
- **Recorded:** without a key no model is called. The agents replay answers recorded once against the Gemini API (`fixtures/`), and `./go demo-rework`, `./go demo-network` and `./go demo-mainline` replay patches written by hand and say `model none`. With a key and `PROFILE=l1` the agents run live. The first live run on Claude (`claude-code` 2.1.311, `claude-sonnet-5-5`, ticket 0001, 2026-11-04) is the gates doing their job: the three ADK roles passed their evals, and the coding role's change was stopped by the mutation gate, 5 of 8 mutants killed on the changed lines, 0.625 under the 0.666 threshold. Nothing merged.
- **Before the ticket, at L0:** `./go demo` now starts ticket 0001 at `requested`. The product role has no recording for that request, so it is not consulted: the timeline says so, takes the criteria the ticket states, and the spec gate judges them for real ([ADR 0055](docs/adr/0055-the-dev-phase-visible-from-request-to-release.md) §3). A question and its answer replay only for the one request the role was recorded on (`./go ci` proves it), and under replay the answer's text is not compared with the recording: any answer replays the recorded criteria. Recording the product role on ticket 0001 takes `./go record-evals PROFILE=l1` and a key.
- **lights-out judges itself:** every push and pull request here runs the Action on its own change, with the contract in [`.lights-out/`](.lights-out/workload.env) and a judge built from the base ([ADR 0049](docs/adr/0049-lights-out-judges-itself.md)). Risk, secrets and deps cover the whole repository; the test gate is `make ci`, the thirty self-checks; SAST and mutation cover `core/` only, about 5% of the code, against a measured baseline of 0.39. The shell, three quarters of the code, has no mutation score: there is no mutation tool for POSIX sh to run.
- **Where shell is allowed:** on the host (`./go`), in adapter verbs, in the gate wrapper that prints the one line, and in thin entry points; logic goes to Python under `core/`, with unit tests from the ADRs. `ci/shell-boundary.sh` holds a `core/` shell file to 30 code lines and names the files over it as debt that can only shrink ([ADR 0052](docs/adr/0052-where-shell-is-allowed.md)).
- **The project map:** a SQLite file rebuilt from one commit at every merge, with no model ([ADR 0054](docs/adr/0054-the-project-map.md)). A merge that changes a path a page or an ADR cites files a docs ticket for the coding role, and `ci/docs-drift.sh` fails when a page cites a path, a `./go` command or a key that no longer exists. Putting the map's slice in the worker's brief is off by default (`MAP_BRIEF=off`) until the experiment on an outside repository measures whether it helps.
- **Not yet:** the GitHub Action is proven in lights-out's own workflows only; nothing is proven yet on a codebase that was not written for lights-out; the Google Cloud profiles are designed, not run; the coding harnesses' network stays open, because each must reach its provider; with the experimental `antigravity-cli` harness, a repository's own `.agents/hooks.json` runs its commands inside the worker's container, outside the guard (ADR 0050 §7), and agy is a proprietary Google binary you run under Google's terms. For plane commands `./go` hands its toolchain container your engine's socket, which means full control of the engine: run it where that is acceptable.

Every item, level by level: [what is real and what is recorded, in full](docs/reference.md#what-is-real-and-what-is-recorded).

## Next

- [The tutorial: the demo read stage by stage, then your own repository](docs/tutorial.md)
- [How it works, every command, every level, the coding harnesses](docs/reference.md)
- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/adr/)
- [Contributing](CONTRIBUTING.md) and [roadmap](ROADMAP.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).