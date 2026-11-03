# Security policy

## Reporting a vulnerability

Report it privately: the repository's **Security** tab, then **Report a
vulnerability**. Please do not open a public issue for it.

lights-out is maintained by one person in their spare time. You will get
an answer, but not within hours.

Only the latest commit on `main` is supported, and once there are
releases, the latest release.

## What to report privately

- A way for a ticket, a pull request, a fixture, an attached repository's
  `.lights-out/` or an agent's output to run code on the host outside the
  toolchain container, or to read `.env`.
- A way for content an agent or a contributor controls to merge a change,
  or send it traffic, without the gates and the policy of the base branch
  judging it.
- A secret reaching a log, a recording under `fixtures/`, or the audit
  chain.

An agent walking around a gate in a way that needs a human to help it is
still worth knowing about: open a public issue with the **gate bypass**
template.

## Known and documented, not vulnerabilities

- For plane commands, `./go` hands its toolchain container your engine's
  socket, which means full control of the engine (README, "What is real
  and what is recorded"). Scripts in an attached repository's
  `.lights-out/` run there too (docs/use-on-your-repo.md).
- The local plane is for a development machine. Its services (Gitea, Zot,
  Prometheus, Envoy, flagd and the app) use development credentials and
  publish their ports on every interface of the host (`compose.yaml`).
  Run it on a network you trust, and never expose it.
