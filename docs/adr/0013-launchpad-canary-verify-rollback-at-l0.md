# ADR 0013 — Launchpad at M3: a second compose revision behind Envoy runtime weights, `slo.promql` selects canary vs stable by `service_version` through `target_info`, thresholds live in `verify/slo.sh`, freeze and kill switch are flags

- Status: accepted (amends ADR 0003 stage list; ADR 0011 §1 query text and §4 gate rules; ADR 0012 §4 canary cluster, §7 ports; ADR 0007 §4 declared design becomes executable). Amended by ADR 0014 §1 and §4: a canary that clears 5% and 25% is held there at exit 0 for the human gate instead of being retracted, and `demo-hold` proves that branch. Amended by ADR 0019 §5, §8: Zot stays empty through M6; `100%: NOT YET (M7, go-for-launch)`. Amended by ADR 0020 [launchpad writes `RELEASE_RECORD`; the held line names `./go promote`].
- Date: 2026-09-14
- Milestone: M3

## Context

M3 (plan §7): release controller with stages staging, 5%, 25%, 100%; the
verify runner evaluating `verify/slo.promql` canary vs stable; automatic
rollback; global freeze; kill switch via flag. Done when `./go demo-rollback`
at L0, with no model call, releases a version that fails verify and rolls
back on its own, and the log shows the decision with the numbers. Plan §2
now binds: `./go demo` cold to the rollback in < 900 s (M2 cold: 258 s).
Facts verified 2026-09-14: Envoy v1.39.1 `weighted_clusters.runtime_key_prefix`
reads weights from runtime keys `<prefix>.<cluster>` with the file value as
default; `POST /runtime_modify` needs a `layered_runtime` with an
`admin_layer`; Envoy's file watcher is inotify, absent on virtiofs. The
app's `/metrics` carries `service_version` only on `target_info`; the OTel
Prometheus compatibility spec designates `target_info` joined
`on (job, instance) group_left` as the way to reach resource attributes.
`APP_VERSION` is the `version` attribute of every flag evaluation (ADR
0007 §3). flagd polls its file. Prometheus scrapes every 5 s (ADR 0012 §8).

## Decision

1. **The L0 canary revision is a second compose service `backend-canary`,
   same image and build as `backend`, `APP_VERSION` from `CANARY_VERSION`,
   in compose profile `canary`.** It is not running after `./go up`; the
   delivery adapter's deploy stage starts it. Envoy's `canary` cluster
   becomes STRICT_DNS → `backend-canary:8000` (amends ADR 0012 §4: the
   upstream is now a real second process, not the stable one). Prometheus
   keeps one job `backend` with two static targets, `backend:8000` and
   `backend-canary:8000`: one service, two revisions, which is what Managed
   Prometheus sees on Cloud Run; the canary target is `down` until deploy,
   and `adapters/prometheus/ready.sh` already matches on any `1`. The
   "failing version" is the version string the committed targeting rule in
   `app/flags/flags.json` turns `waitlist` on for: `"targeting": {"if":
   [{"==": [{"var": "version"}, "0.2.0-waitlist"]}, "on", "off"]}`,
   `defaultVariant` stays `off`, so stable (`0.1.0-m2`) and an empty
   context (flagd `ready.sh`) still get `false`. The Makefile default
   `CANARY_VERSION ?= 0.2.0-waitlist` must match that rule; a drift makes
   the release pass and `demo-rollback`'s assertion (point 4) fails loudly.
   Same code, different flag targeting: the README says so in one line ("at
   L0 the failing version is the same image with `waitlist` targeted at its
   version; the first real code diff arrives with the M5 worker"). **Zot
   does not enter M3**: nothing is built or pushed, the README line "empty
   until M3" becomes "empty until a merged PR is built into an image (M5 at
   the earliest)".
2. **`verify/slo.promql` gains a third query and a selector; window
   `[5m]` → `[1m]`** (amends ADR 0011 §1). Every query multiplies its
   `rate()` by `on (job, instance) group_left (service_version) target_info`
   and aggregates `by (service_version)` (`by (service_version, le)` for
   the histogram). Queries, verbatim:

   ```
   # name: traffic
   sum by (service_version) (rate(http_server_request_duration_seconds_count[1m]) * on (job, instance) group_left (service_version) target_info)

   # name: error_rate
   sum by (service_version) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1m]) * on (job, instance) group_left (service_version) target_info) / sum by (service_version) (rate(http_server_request_duration_seconds_count[1m]) * on (job, instance) group_left (service_version) target_info)

   # name: latency_p95
   histogram_quantile(0.95, sum by (service_version, le) (rate(http_server_request_duration_seconds_bucket[1m]) * on (job, instance) group_left (service_version) target_info))
   ```

   No placeholder: the file stays real PromQL and the runner picks the
   canary and the stable element of each result vector by `service_version`.
   `traffic` exists to close the ADR 0011 named bug: a version with
   `traffic` absent or 0 is **NO-GO "no data"**; a version with `traffic > 0`
   and no `error_rate` element has **zero errors**. No cross-query inference
   from NaN. **Window 1m, provenance: decision, forced by L0's reused
   `instance`.** The http series carry no version label; the join stamps the
   *current* `target_info` on the whole window, and at L0 every canary
   revision reuses `instance="backend-canary:8000"`, so any window longer
   than the stage would attribute a previous canary's 5xx to the next one
   (the M6 golden path runs a failing and a passing release back to back).
   Rule: the stage's observation time is ≥ the window, so the window holds
   only this stage of this canary; ADR 0011's `[5m]` had no provenance and
   would cost 10 minutes of stages. At 5 s scrapes 1m holds 12 samples, six
   times the two `rate()` needs (Prometheus, external constraint).
   `verify/metric-shape.sh` (amends ADR 0011 §4): exactly the three names
   above; `target_info` counts as a referenced family when the query text
   contains it; every extracted label (`by (...)` and `=`/`=~`) must appear
   on at least one family the query references, so `service_version` is
   looked for on `target_info` and `http_response_status_code` on the http
   family; `on (...)` and `group_left (...)` are not extracted (`job`,
   `instance` are stamped by Prometheus, not scraped). It stays GO.
3. **Envoy weights move through the admin API.** `envoy.yaml`:
   `weighted_clusters.runtime_key_prefix: weights` (file weights 100/0 stay
   as defaults), `layered_runtime` with one `admin_layer`, `admin` on
   `0.0.0.0:9901`, published `9901:9901` (amends ADR 0012 §7; provenance:
   Envoy's conventional admin port). The Envoy image has no shell or curl,
   so `docker-compose exec` cannot reach it; the port is the only path from
   workbench through `PLANE_HOST`, and it is one more unauthenticated port
   on the trusted L0 network the README already declares. Shift =
   `POST /runtime_modify?weights.stable=<100-p>&weights.canary=<p>`,
   verified by `GET /runtime`; rollback = `weights.canary=0&weights.stable=100`.
   The admin layer is in-memory: a restarted Envoy is 100/0, the safe
   default. File-based xDS is rejected (no inotify on virtiofs).
4. **The controller is `core/launchpad.sh`, POSIX sh, vendor-free; adapters
   are three scripts per delivery adapter and one per metrics adapter.**
   Names from plan §1: the pipeline is `launchpad`, the human gate
   `go-for-launch`. `adapters/$DELIVERY/deploy.sh <version>` (L0:
   `docker-compose up -d backend-canary`, then poll `docker-compose exec -T
   backend-canary python3 -c '<urllib GET /healthz>'` until `.version` equals
   the argument, `READY_TIMEOUT` as elsewhere: the revision answers
   directly, not through Envoy), `shift.sh <canary-percent>`, `rollback.sh`
   (idempotent: all traffic on stable); `adapters/$METRICS/query.sh
   '<promql>'` (L0: curl `/api/v1/query`, prints the JSON; `managed-prometheus`
   differs by URL and auth, which is why it is an adapter). The verify runner
   is `verify/slo.sh`, a gate (`. ci/lib.sh`, name `slo`, unique across
   `ci/ gates/ verify/`): reads `CANARY_VERSION` and `STABLE_VERSION`, NO-GO
   instantly when either is unset (what `ci/contract.sh` sees cold), runs
   each named query through `query.sh`, prints the numbers on stderr always
   and in the NO-GO reason: `NO-GO: slo — canary 0.2.0-waitlist error_rate
   1.000 vs stable 0.000, max delta 0.010`. Stages: `launchpad` first calls
   `rollback.sh` (known state), reads `STABLE_VERSION` from `GET
   $APP_URL/healthz` through the edge at 100/0 (no duplicated constant),
   evaluates `release-freeze` (point 6), then `staging` = `deploy.sh`;
   `5%` and `25%` = freeze check, `shift.sh`, sleep `STAGE_SECONDS`,
   `verify/slo.sh`; NO-GO at any stage → `rollback.sh` and the stderr line
   `[launchpad] 5%: NO-GO: slo — … → rollback`; `100%` prints
   `[launchpad] 100%: NOT YET (M6, go-for-launch)` in the ADR 0003 style,
   and a release that passed 25% is retracted with `rollback.sh` because
   promotion is not built: nothing is left half-shifted. The controller
   generates no traffic: production has real traffic. At L0 the Makefile
   target starts `app/load.sh` beside it (one user, one capacity-1 meetup,
   a loop of registration POSTs through Envoy: 409 on stable, 501 on the
   failing canary, no state growth) and kills it when `launchpad` exits.
   Makefile: `release` runs `launchpad` with `CANARY_VERSION`;
   `demo-rollback` = `release` with the failing default, asserts the
   controller exited 1 with the NO-GO at `5%`, then asserts Envoy runtime
   `weights.canary` final value `0` and 10 of 10 `GET $APP_URL/healthz`
   report `STABLE_VERSION` (10: decision; routing at 100/0 is deterministic,
   any count proves it in under a second). The canary container stays up at
   weight 0, as a Cloud Run revision stays after a rollback; the next
   `deploy.sh` recreates it. `demo` replaces its `deploy`, `verify`,
   `rollback` stub lines with one call to `demo-rollback` (amends ADR 0003:
   the three stages are one flow); `metric-shape` stays as the `verify`
   stage before it. The second `up` inside `demo` stays (HANDOFF item 8).
5. **Thresholds and durations, in `verify/slo.sh` as env-overridable
   defaults with a provenance comment each** (ADR 0011: next to the
   comparison logic; the M8 hash test then keeps them identical at every
   level). Compared per version, canary against stable, absolute deltas:
   ratios divide by a stable error rate of zero. `ERROR_RATE_MAX_DELTA=0.01`:
   decision; one extra failure per hundred requests. Sample-size caveat named:
   at the demo's ~1–2 rps on the canary one stray 5xx in the window is about
   one point, and stable and canary share the code path, so a stray 5xx is a
   bug worth seeing. `LATENCY_P95_MAX_DELTA=0.25` s: decision; the semconv
   buckets below 250 ms are 5, 10, 25, 50, 75, 100, 250 ms and
   `histogram_quantile` interpolates inside a bucket, so at local single-digit
   ms a canary and a stable p95 can land in adjacent buckets; 250 ms is the
   first boundary an order of magnitude above that region. The demo has no
   latency failure to detect, the number is deliberately loose, and M8
   re-sets both from L2 measurements. `STAGE_SECONDS=60`: constraint, equal
   to the 1m window (point 2). Budget: staging ≤ 15 s (M2 measured
   readiness), one stage 60 s + verify ~1 s + rollback ~1 s + assertions
   ~2 s: about 80 s on top of 258 s, ~340 s cold, ~35 % of 900.
6. **Kill switch and freeze are flags in the one `app/flags/flags.json`,
   edited from workbench with `jq`; `demo-rollback` never writes the tree.**
   `./go kill-switch`: `del(.flags.waitlist.targeting)` and `defaultVariant
   = "off"`, then asserts through OFREP with `{"context":{"version":
   "$CANARY_VERSION"}}` that the value is `false`; live in seconds, no
   deploy (plan §8 step 9). `release-freeze`, boolean, default `off`, in
   the same file: `./go freeze` / `./go unfreeze` flip `defaultVariant`;
   `launchpad` evaluates it through OFREP (`:8016`, the same Flags port at
   every level) before deploy and before each shift; `on` → `rollback.sh`
   and `NO-GO: launchpad — release-freeze is on`. Both edits dirty the
   committed file: accepted and declared. At L0 the flag file is the flag
   store, `git diff app/flags/flags.json` is the audit trail and `git
   checkout app/flags/flags.json` the undo; each target prints that on
   stderr. The demo reads flags only, so a clean clone stays clean after
   `./go demo`.
7. **The 900 s ceiling is measured by `./go` and judged by `make demo`.**
   `go` records `LIGHTS_OUT_T0=$(date +%s)` before `engine-compat` (the cold
   pulls live there) and passes it into workbench; `make demo` ends with
   `GO: demo, milestone M3, <elapsed> s to rollback (budget 900 s, plan §2)`
   or `NO-GO: demo — rollback reached, but <elapsed> s > 900 s budget (plan
   §2)`. `DEMO_BUDGET_SECONDS ?= 900` (provenance: plan §2, external
   constraint on this repo); `0` disables the verdict on a known-slow
   network, the elapsed is printed regardless. Host and podman-machine
   clocks may differ by seconds; irrelevant at this scale. The cold figure
   that counts is the clean-container run at milestone close (CLAUDE.md),
   recorded in HANDOFF and README; the GitHub `engine-compat` job runs
   `./go demo` instead of `./go engine-compat`, so the canonical stranger
   (a fresh runner) measures it on every push.

## Alternatives rejected

- Zot push/pull of a tagged image as the release artefact: nothing differs
  between the images at M3; a registry round trip to prove nothing.
- A second Prometheus job for the canary: `job` would then say "revision",
  which no other level means by it; the selector is `service_version` anyway.
- Selector on a Prometheus target label (`version` static label) or on
  `job`: exactly the compose-only label the HANDOFF forbids.
- Placeholder substitution for the window or the selector: the file stops
  being PromQL, and M8's hash test guards a template, not a query.
- Two queries and a runner that infers "no data" from a NaN or absent
  `latency_p95`: the coupling ADR 0011 predicted would become the M3 bug.
- `A / (B > 0) or 0 * (B > 0)` inside `error_rate`: correct, unreadable on
  a slide; `traffic` says the same thing in one short line.
- Keeping `[5m]`: no provenance, ten minutes of stages, and wrong at L0 for
  consecutive releases (point 2).
- Unique `instance` per L0 revision (DNS SD, docker SD, config reload): IPs
  get reused, the socket is not in the Prometheus container, the config is
  baked into the image (ADR 0012 §2).
- Reaching the admin API with `docker-compose exec envoy`: no curl or shell
  in the image.
- `LOAD_GENERATOR` profile variable read by the controller: a level-specific
  concept in `core/`; the Makefile target that needs traffic starts it.
- Promotion at M3 (recreate `backend` at the new version, canary to 100%):
  not in the done-when, and the human gate it must wait for is M6.
- Freeze as a file under `policy/` (M4) or a Firestore document (M6): a
  file is local to one checkout, not global; Firestore is two milestones
  away; the Flags port is live today at every level.
- A separate platform flag file or a second flagd `--uri`: one more mount to
  prove for namespace hygiene.
- Kill switch as `state: DISABLED`: flagd's OFREP answer for a disabled flag
  is not something `ready.sh` was written against.
- A gitignored copy of the flag file mounted instead of the committed one:
  copy-if-missing semantics, a second path, and a runtime state nobody can
  `git diff`.
- Timing verdict inside `make demo` only: misses the cold pulls, which are
  the bulk. Verdict inside `go`: two sources of the final line.
- `demo-rollback` under a 900 s verdict: warm by definition, proves nothing.

## Consequences

- `service_version` is stamped from the *current* `target_info`: the rule
  "stage time ≥ window" is what makes the numbers mean this canary; whoever
  lengthens the window must lengthen `STAGE_SECONDS`, and the comment in
  `slo.sh` says so. On Cloud Run every revision is a fresh `instance` and
  the problem disappears; L0 is the constrained side, as it should be.
- Both thresholds are decisions, deliberately loose, and the error delta is
  sample-size sensitive at demo traffic. M8 owns replacing them with
  measured numbers; until then the README must not call them SLOs.
- A canary at weight 0 keeps running after every release; `make down` needs
  `--profile canary`, and STRICT_DNS on an absent `backend-canary` puts a
  DNS warning in Envoy's log every 5 s between `up` and the first deploy.
- `9901` is one more unauthenticated port with `/quitquitquit` on it.
- `kill-switch`, `freeze`, `unfreeze` dirty the tree; a stranger who runs
  them and then `./go demo` gets a demo whose canary passes (waitlist off
  for everyone) and `demo-rollback` NO-GOs with "expected NO-GO at 5%": the
  assertion is the guard, the stderr line names `git checkout`.
- The demo's final line can go red on a slow network although every stage
  passed; the reason says the rollback was reached.
- `traffic` is a third query in the file that decides everything; three
  lines is still one file.
- `CANARY_VERSION` appears in the Makefile default and the committed
  targeting rule; ADR 0007 §4's declared 501 becomes load-bearing.

## Golden-rule check

No new image, no key, no account: Envoy admin is config, `backend-canary`
is the app image already built, `launchpad` and the adapters are sh, curl,
jq. Added cold time is bounded by design at about 80 s (point 5): projected
~340 s against 900. Passes; the clean-container figure is recorded at M3
close and the GitHub job measures it on every push.
