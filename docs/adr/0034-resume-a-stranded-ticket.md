# ADR 0034 — A failed tower step leaves one `error` entry in the history; `tower.sh resume` requests that step again, and `./go resume TICKET=<id>` runs it

- Status: accepted (amends ADR 0019 §1 [a failed step no longer leaves the document byte-for-byte untouched: it appends one history entry, state and every other field unchanged] and §3 [a new operator verb beside `open` and `step`]; consistent with ADR 0031 §4 [same entry shape, `error`; 0031 may later fill it with the step's last stderr line])
- Date: 2026-11-02
- Milestone: before the public launch (ticket 0009)

## Context

Ticket 0009. When a step fails — a transient Gitea error in `status.sh`,
a store read that fails, a review harness error — `core/tower.sh` exits 1,
the `inproc` orchestrator acks the message, and the document stays in the
step's starting state with nothing queued. ADR 0019 §1 made the failure
leave the document untouched, so nothing in the record says the ticket is
stuck, and the only way on is `tower.sh open`, which rewrites the document
and wipes the history the audit chain is built from.

The EventBus port has three verbs (ADR 0019 §3): publish, pull, ack. It
cannot be peeked, so "is a step for this ticket still queued?" has no
answer from the bus.

## Decision

1. **A failed attempt is recorded.** When the step script exits non-zero,
   prints no state, or the next step's event cannot be published, the
   tower appends `{step, state, at, error: <why>}` to `history` — the
   state and every other field stay as they were — writes the document,
   and exits 1 as before. `<why>` is `step exited <rc>`, `step printed no
   state` or `could not publish <step>`. For the publish case `step` is
   the step that was not requested and `state` the one just written. If
   that write fails too, the tower says so on stderr and the document is
   as ADR 0019 left it. Idempotency does not change: the precondition
   reads only `.state`.
2. **Stranded means the last history entry has `error`.** `tower.sh resume
   <ticket>` requires it, and requires the failed step's precondition to
   be the current state; then it appends `{step: "resume", state, at,
   resumed: <step>}` and publishes that step. The write comes first, so a
   step that starts at once (a job at L2) is never overwritten by it; a
   publish that fails records itself as in 1, so the ticket stays
   resumable. Anything else — a ticket in flight, a terminal one,
   one resumed already — is refused with exit 1 and a `not stranded` line,
   and nothing is published. The history ends up as the failed attempt,
   the resume, the new attempt.
3. **`./go resume TICKET=<id>`** runs `tower.sh resume`, then the
   orchestrator until the queue is empty, and prints `GO: resume` or
   `NO-GO: resume — <why>`. It gets the engine socket, like `e2e`, because
   the steps it re-runs (`ci`, `release`) need it.

`./go audit` reads fields, not history, so it rebuilds the chain of a
resumed ticket unchanged; `ci/tower.sh` case (g) proves it on stubs.

## Alternatives rejected

- **Resume = publish the step for the current state, no record.** Without
  a peek verb, it cannot tell a stranded ticket from one whose event is
  still queued, and puts a duplicate on the bus for a step in flight:
  harmless with one `inproc` loop, but at M8, with two workers on the
  topic and no compare-and-set (ADR 0019 §2), both could run it. It also
  leaves the failure out of the record.
- **A `peek`/`list` verb on the EventBus port.** A port change for every
  adapter (Pub/Sub has no cheap non-consuming read) to answer a question
  the document can answer itself.
- **Retries inside the tower.** ADR 0019 §1 has no retries on purpose: a
  step that fails twice in a row needs an operator, not a loop.
- **Keep `open` as the way on, but copy the old history.** `open` would
  then mean two things, and the chain fields (`pr`, `ci`, …) are lost all
  the same.

## Consequences

- `ci/tower.sh` case (e) becomes "state and fields untouched, one `error`
  entry appended"; cases (g) and (g') add resume and its refusal.
- A failure that cannot be written (the store is down) still strands the
  ticket with no `error` entry; resume refuses it. The operator's way on
  is the plane first, then `open` — rare, and stated here rather than
  hidden.
- `./go`'s socket list gains `resume`.

## Golden-rule check

`./go demo` does not call `resume`; on its golden path no step fails and
the history is the one ADR 0019 described. Milliseconds in `ci`. Passes.
