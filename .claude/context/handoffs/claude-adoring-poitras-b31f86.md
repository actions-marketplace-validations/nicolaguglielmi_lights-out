# Handoff: the harness-conformance flake was the proof's port picker, 2026-11-11

Branch `claude/adoring-poitras-b31f86`, on `main` 85f213f. Fix in 474bc90 (`gates/harness-conformance/proof.sh`, one line in the `Makefile`'s comment); this file in the commit after it. Pushed, no pull request, not merged: landing is the owner's. No ADR: no structure changed, no abstraction added (ADR 0070 not used).

## Cause

Not podman, not DNS, not the real suite. Both failures happened inside `harness-conformance-proof` (`gates/harness-conformance/proof.sh`), the self-test that runs the suite on `fake-cli` with a stand-in `docker-compose`, before the suite judges claude-code.

The proof picked each listener's port by binding `("127.0.0.1", 0)` and closing it; the listener (`stub.py` and `core/egress.py`) then binds `0.0.0.0` on that port. The proof's egress stand-in (`egress_wrap.py`) opens the proxy's outgoing sockets from `("127.0.0.2", 0)`, from the same kernel allocator and the same parity of the ephemeral range. A port held, or in TIME_WAIT (60 s), on `127.0.0.2` looks free to a pick on `127.0.0.1` but conflicts with a bind on `0.0.0.0`: the listener dies with `OSError: [Errno 98] Address already in use`.

- The stub dies: the suite waits 60 s for `ready` and says `the scripted model did not answer within 60 s` (the podman failures).
- The proxy dies: `core/egress.sh` waits 30 s and run.sh exits 1, `fake-cli case 1: run.sh exited 1, want 0` (the same race in the docker `ci` workflow, runs 42524406996 attempt 1 and 42418075123: very likely the "DNS flake" of past handoffs).

The proof printed only the verdict line and the stand-in's `logs conformance-model` printed nothing, so the CI logs never showed the EADDRINUSE.

## Evidence

Timelines on GitHub (harness-conformance-podman, from the workbench image tagged to the end):

```
fail 42641009840/1 (c876840)  built 15:05:55  proof NO-GO 15:07:56 (+2:01)  case 9c's suite  -> real suite never ran
fail 42787299067/1 (995ba3f)  built 09:03:00  proof NO-GO 09:06:01 (+3:01)  key-on-stop's suite
pass 42641009840/2            built 15:19:06  proof GO 15:21:21 (+2:15)  suite GO 345 s
pass 42787299067/2            built 09:16:09  proof GO 09:18:20 (+2:11)  suite GO 152 s
pass 42789092047/1            built 09:15:49  proof GO 09:17:56 (+2:07)  suite GO 182 s
```

No image pull, DNS or network step differs: the failing step is a local Python listener inside the workbench container (own network namespace, nothing else on 127.0.0.2).

Local, workbench image on the podman VM (kernel 7.2.7), `--network none`, scripts in the session scratchpad:

- Mechanism: a TIME_WAIT socket on `127.0.0.2:X` (no SO_REUSEADDR, as `create_connection` leaves it) lets `bind(("127.0.0.1", X))` succeed and makes `ThreadingHTTPServer(("0.0.0.0", X))` fail EADDRINUSE; an open one does too.
- Allocator: with 300 proxy-like sockets on 127.0.0.2 (all odd ports), 51 of 2000 picks on 127.0.0.1 landed on one of them. With 7000 planted, 95/200 picks on 127.0.0.1 failed the stub's bind; 0/200 picks on `0.0.0.0` did.
- Normal load: four instrumented proof runs, 136 picks: mean 4.7, max 12 TIME_WAIT sockets on 127.0.0.2 at each pick, no collision in that sample (a ~1%-per-run event; GitHub's 2 in 40 podman runs is within the noise of a sample that small).
- Amplified load (120 proxy-like connections a second from 127.0.0.2 during the run), unmodified proof: 5 of 5 failed, three with the exact CI message (stub traceback ending `[Errno 98] Address already in use`), two with `case 1: run.sh exited 1` (`egress: the egress proxy did not report ready within 30 s`).
- Same load, fixed proof: 4 of 4 `GO: harness-conformance-proof` (115–118 s).

## What changed

- `proof.sh`: one picker, `$work/bin/freeport`, binds `("0.0.0.0", 0)` (the address the listeners bind, so the kernel skips ports held on any address); the stand-in compose's `up egress`, `prove` and the probe's proof use it. A pick is taken only while no proxy runs, so nothing takes the port before the listener binds.
- `proof.sh`: the picker is proved first, under the proxy's load: a quarter of the ephemeral range planted as TIME_WAIT from `("127.0.0.2", 0)`, then 20 picks, each bound the way `stub.py` and `core/egress.py` bind. With the old picker it fails on the first pick in about 1 s (3 of 3 runs); provenance of the quarter and the 20 in the comment (measurement 2026-11-11 plus decision). Costs about 0.4 s.
- `proof.sh`: the stand-in's `logs conformance-model` prints the stub's stderr, as an engine would; a "refused for another reason" NO-GO prints the suite's stderr tail.

## Acceptance

`./go ci` from a clean clone of 474bc90: `GO: ci`, `GO: contract`.

GitHub Actions on 474bc90, all green: podman 21 of 21 (push 42974800214, dispatched 42974819936, 42974823776, 42974827354, 42974830678, 42974834304, 42974837950, 42974841376, 42974844672, 42974848877, 42974852309, 42974855948, 42974859518, 42974863070, 42974866248, 42974869264, 42974872593, 42974876355, 42974879672, 42974883072, 42974886574); ci 42974800139 (its docker harness-conformance runs the same proof), self 42974800253, package 42974800215, stranger 42974800209. site runs only on `site/**`, untouched here.

Failure rates: before, podman 2 of 40 runs on main (5%), docker `ci` harness-conformance 2 of the last 100 ci runs; after, 0 of 21 podman. 21 green runs alone would only weakly rule out a 5% flake (0.95^21 ≈ 34%): the proof is the amplified-load test (5/5 failing before, 4/4 green after) and the picker check, which fails the old picker deterministically.

## Found, not fixed here

- The suite's 60 s wait for the stub (`gates/harness-conformance.sh`) does not notice a stub that has already exited; on a real engine `logs` then shows why, but only after the full minute. Left alone: the cause is gone, and a liveness check on the real engine is a new place to flake.
