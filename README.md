# lights-out

Six agents ship it. One human turns the lights back on.

**Autonomous agents take a ticket to production on a codebase you do not trust. Numeric gates decide, the ticket's perimeter holds, a failing canary rolls itself back, and one human approves the last step.**

It runs complete on your laptop: no account, no API key, no cloud.

## Try it

**1. Install a container engine (once)**

| Your machine | Run |
|---|---|
| macOS | `brew install podman`<br>`podman machine init --cpus 4 --memory 6144`<br>`podman machine start` |
| Linux | install podman, then<br>`systemctl --user enable --now podman.socket` |
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
./go up              # start the local plane (about 15 s once downloaded)
./go demo-rollback   # just the self-rollback, about a minute
./go board           # the pipeline explained, and live while the plane runs: localhost:8099
./go down            # stop everything
```

## If something goes wrong

`./go` checks your engine before it builds anything and prints the command that fixes what is missing. The other cases:

| You see | Do this |
|---|---|
| A port is already in use | Put `APP_PORT=9000` in a file named `.env` for the app port. Ports 3000, 5050, 8016, 8085, 8086, 9090 and 9901 must be free. |
| `Cannot allocate memory`, or everything crawls | `podman machine stop`, `podman machine set --memory 6144`, `podman machine start` |
| `NO-GO: demo — rollback reached, but … > 900s budget` | Everything worked; the first download was slow. Run `./go demo` again. |
| Anything else | `./go down`, then `./go demo` again. Still stuck? Open an issue with the last 30 lines. |

## What is real and what is recorded

- **Real:** the gates, the signed build, the canary, the metrics, the rollback, the audit chain. Nothing in them is simulated.
- **Recorded:** no model is called without a key. The agents replay answers recorded once against the Gemini API (`fixtures/`), and the promotion brief at this level is rendered from the release record and labelled so. With `GEMINI_API_KEY` in `.env` and `PROFILE=l1`, the agents run live. The model is the profile's choice (ADR 0040): `MODEL_PROVIDER` and `MODEL` in `profiles/` or `.env`, Gemini by default, Claude or OpenAI for the three ADK roles with that provider's key; the coding roles run Gemini only until the `claude-code` and `codex` harnesses (M19). Gemini's free tier is the only free path; Claude and OpenAI charge per run. Every recording in `fixtures/` is Gemini's, and `run.json` says which provider and model answered.
- **Hand-written (rework):** `./go demo-rework` sends ticket 0013's first attempt back to the worker with the gates' verdict (ADR 0038). No rework has been recorded against the Gemini API yet, so at L0 both attempts replay patches written by hand (`fixtures/0013/`, `hand_written: true`), and the run says `model none`. The gates that reject the first attempt and pass the second, the tower, the loop and the cap are real.
- **Hand-written (network):** `./go demo-network` splits ticket 0012 between two workers behind one harness port (ADR 0036). No network run has been recorded yet, so at L0 the two workers replay patches written by hand, and the run, the PR and the audit say `model none`. The governance around them (perimeters, gates, canary, rollback, audit) is real.
- **Local only:** merges happen on a Gitea inside the plane, never on this repository.
- **Your engine:** for plane commands, `./go` hands its toolchain container your engine's socket, which means full control of the engine. Run it where that is acceptable.
- **Cloud:** Google Cloud profiles are designed, not yet run.

## On your own codebase

```sh
./go attach ~/code/your-repo   # your repository gets one directory, .lights-out/; lights-out never writes to it
```

What works today, and what does not yet:

- **Works:** the plane, the six gates, the canary and its rollback on your stable image, judged by the thresholds you set in `.lights-out/policy.env`. A change to `.lights-out/` never merges on its own.
- **Needs a model key.** There are no recordings of your code, so on your repository the agents run at L1 only, and say so at L0: `GEMINI_API_KEY` for the coding roles (the free tier), or `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` with `MODEL_PROVIDER` and `MODEL` for the ADK roles. The dev-worker may spend up to 2.6M tokens per run (`roles/dev-worker/role.env`).
- **Python 3.13 and Node 24 only.** That is the dev-worker's toolchain; other stacks are the next milestone.
- **Stops at release at L1.** A merged change is not yet built and released from your repository.
- **Local only.** Merges land on the plane's Gitea and you `git fetch` them back. No pull requests on GitHub yet, and no deploy to your production.
- **Not yet proven** on a codebase that was not written for lights-out.

[The guide](docs/use-on-your-repo.md) says what `.lights-out/` holds, how to measure your mutation baseline and how to write tickets.

## Next

- [How it works, every command, every level](docs/reference.md)
- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/adr/)
- [Contributing](CONTRIBUTING.md) and [roadmap](ROADMAP.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
