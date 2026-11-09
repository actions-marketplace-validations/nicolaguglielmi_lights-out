# ADR 0011 — `verify/slo.promql` ships at M1 with the production queries; `verify/metric-shape.sh` checks them against a live `/metrics` and declares what it cannot evaluate

- Status: accepted (amends ADR 0010 §5 and the `verify` stage of ADR 0003)
- Date: 2026-09-14
- Milestone: M1

## Context

Plan §3 makes `verify/slo.promql` one file that runs unchanged from L0 to
L3. ADR 0007 fixes the metric and label names the app emits. Writing the
file only at M3 means the query text and the app's metric shape are never
confronted until the canary depends on both. There is no Prometheus before
M2, and `rate()`/`histogram_quantile()` cannot be evaluated from a single
`/metrics` scrape: there is no time dimension. So at M1 the queries can be
checked for agreement with the app, not evaluated.

## Decision

1. **`verify/slo.promql`, two named queries, production text.** Format: a
   `# name: <id>` comment line, then exactly one non-empty query line. Only
   two blocks, `error_rate` and `latency_p95`, verbatim:

   ```
   # name: error_rate
   sum(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[5m])) / sum(rate(http_server_request_duration_seconds_count[5m]))

   # name: latency_p95
   histogram_quantile(0.95, sum(rate(http_server_request_duration_seconds_bucket[5m])) by (le))
   ```

   No thresholds, no canary/stable selector: M3 owns both.

2. **`verify/metric-shape.sh`**, gate name `metric-shape`, `. ci/lib.sh`.
   It takes the app base URL from `APP_URL`, a Makefile variable defaulting
   to `http://host.containers.internal:8080` and shared with the ADR 0010 §5
   smoke check (curl `--connect-timeout 1 --max-time 3`). Steps:
   a. Parse `slo.promql`: NO-GO unless exactly the two names above are
      present, each with one non-empty query line.
   b. From each query, extract by regex the metric names (identifier
      followed by `{` or `[`) and label names (identifier followed by `=`
      or `=~`, plus the identifiers inside `by (...)`). A query that
      references no `http_`-prefixed metric is a NO-GO: that is the rule
      that stops the file from being gutted into a vacuous pass.
   c. `GET $APP_URL/api/meetups` once (200, no auth) so at least one
      instrumented request exists, then `GET $APP_URL/metrics`. Any failure
      is `NO-GO: metric-shape — app not reachable at $APP_URL; run ./go up`.
   d. Every extracted metric name must appear as a series in the scrape,
      and every extracted label name (`http_response_status_code`, `le`)
      must appear on that family. Missing name → NO-GO naming it.
   e. Histogram usable by `histogram_quantile`: `le="+Inf"`, `le="0.005"`
      and `le="10"` or `le="10.0"` must be present — the semconv seconds
      buckets of ADR 0007 §2, so a unit or bucket change fails here.
   f. Every observed value of `http_response_status_code` matches
      `^[1-5][0-9][0-9]$`, so `=~"5.."` is a well-formed matcher against
      the real value space.
   g. On GO, stderr gets two declaration lines, always: what was checked
      (query/app agreement against one live scrape) and what was not
      (`rate()` and `histogram_quantile()` need a TSDB — Prometheus at M2,
      canary vs stable comparison at M3). The README repeats them.

3. **Invocation.** Makefile target `verify` (`## Check verify/slo.promql
   against the live app (M1: metric shape only, evaluated at M3)`), running
   `sh verify/metric-shape.sh`. It replaces `[demo] verify: NOT YET (M3)`:
   the `demo` stage list is unchanged, the `verify` stage becomes partially
   real and prints `[demo] verify: metric shape only, evaluation at M3`.
   It runs after `up` and the smoke check; the smoke check drops its
   `/metrics` grep, which this subsumes. No socket needed, so `go` is
   untouched; `./go verify` works standalone after `./go up`.

4. **`ci/contract.sh` scans `ci/`, `gates/` and `verify/`**, skipping
   directories that do not exist yet, as CLAUDE.md already states. The gate
   verdict does not matter there, only the shape, so `metric-shape` failing
   inside `ci` with the app down is correct behaviour. Gate basenames must
   therefore be unique across the three directories.

   *Amended 2026-11-09 (ADR 0062 §3):* the scan is unchanged; under
   `./go ci` a `ci/` check the run has already executed is judged on the
   record of that run, its stdout and exit code, and not run again. Every
   `gates/` and `verify/` script, and any `ci/` check with no record, is
   still run cold.

## Alternatives rejected

- Gate fails with "arrives with M2": honest but proves nothing, and a
  permanently red gate inside `demo` teaches everyone to ignore it.
- Evaluating the PromQL for real at M1 (embedded TSDB, or `promtool`): a
  Prometheus in compose one milestone early, which is M2's budget.
- A tiny PromQL subset interpreter over one scrape: a parser to maintain and
  a second dialect to keep in sync; the file must stay real PromQL.
- M1-only simplified queries, rewritten at M3: exactly the L0/L2 divergence
  plan §3 exists to prevent.
- The gate drives a real 5xx (capacity-1 meetup, flag on, two registrations):
  that scenario is M3's load generator (ADR 0007); here it would mean auth,
  fixtures and state inside a shape check.
- Thresholds in `slo.promql` now: M3 needs them next to the comparison
  logic, and guessing them at M1 invents numbers nobody measured.

## Consequences

- The gate proves the shape, not the semantics. A query that is
  syntactically fine, references real metrics and is still numerically
  wrong passes M1. Only M3 finds that, and this ADR must not be quoted as
  if it did more.
- No 5xx series exists at M1, so the numerator selector matches nothing. In
  PromQL that yields an empty vector, not 0, and M3's runner must treat an
  empty numerator as zero errors instead of "no data" — the most likely M3
  bug, named here in advance.
- M3 needs canary vs stable, so the two queries will gain a label selector
  (a `job`/`version` matcher supplied by the runner). That is the one edit
  this file is expected to take, and it is a milestone change with an ADR,
  not a quiet one.
- `make ci` now runs the gate through `contract.sh` while the app is down:
  a few seconds of curl timeouts and a NO-GO line on stderr during every
  `ci`, including the one at the head of `demo`.
- `APP_URL` is the single place the workbench-to-host hostname is written.
  If `host.containers.internal` is not resolvable on some engine, one
  default changes and the NO-GO message already points at the variable.

## Golden-rule check

curl, grep and sh inside workbench; no key, no account, ~2 s added to
`demo` after `up`. Passes.
