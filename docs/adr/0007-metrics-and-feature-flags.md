# ADR 0007 — OTel FastAPI metrics in Prometheus text with the stable HTTP semconv; OpenFeature via flagd file resolver; the flag is `waitlist`

- Status: accepted
- Date: 2026-09-14
- Milestone: M1

## Context

Plan §3: "PromQL everywhere". `verify/slo.promql` (M3) is one file that
must run unchanged on local Prometheus and on Managed Prometheus, so the
exact metric and label names the app emits are a contract fixed here. Plan
§4: flags go through OpenFeature, adapters `flagd` and `unleash`; M2 adds
the flagd container. Package facts verified on PyPI and in the upstream
sources on 2026-09-14.

## Decision

1. **Packages.** `opentelemetry-sdk 1.44.0`,
   `opentelemetry-instrumentation-fastapi 0.65b0`,
   `opentelemetry-exporter-prometheus 0.65b0` (pins `opentelemetry-sdk
   ~=1.44.0` and `prometheus-client <1.0`). `PrometheusMetricReader` feeds
   a `MeterProvider`; `GET /metrics` returns
   `prometheus_client.generate_latest()`. `FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,metrics")`
   so probes and scrapes do not dilute the error rate. Resource
   `service.name=meetups`, `service.version=$APP_VERSION`.
2. **Stable HTTP semantic conventions, opted in.** The image sets
   `ENV OTEL_SEMCONV_STABILITY_OPT_IN=http`. Verified in
   `opentelemetry-instrumentation/_semconv.py`: unset means old names only;
   `http` means new names only. With the exporter's unit mapping
   (`s` → `seconds`, applied as a name suffix by prometheus_client) the text
   form is:

   ```
   http_server_request_duration_seconds_bucket{http_request_method="POST",http_response_status_code="201",http_route="/api/meetups",url_scheme="http",network_protocol_version="1.1",le="0.25",...}
   http_server_request_duration_seconds_count{...}
   http_server_request_duration_seconds_sum{...}
   http_server_active_requests{...}
   ```

   Buckets are the semconv defaults in seconds (0.005 … 10). The exporter
   also adds `otel_scope_name`/`otel_scope_version` labels and a
   `target_info` series; queries ignore them. The error rate is
   `rate(..._count{http_response_status_code=~"5.."})` over
   `rate(..._count)`; no separate request counter exists or is needed.
   A test asserts these exact names and labels in `/metrics` after one
   request; it is the executable form of this section.
3. **Flags.** `openfeature-sdk 0.10.0`, `openfeature-provider-flagd 0.5.2`.
   Code does `api.set_provider(FlagdProvider())` and nothing else; the
   resolver comes from the environment. Verified in the provider's
   `config.py`: `FLAGD_RESOLVER` accepts `rpc`, `in-process`, `file`, and
   `FLAGD_OFFLINE_FLAG_SOURCE_PATH` selects the file (polled every 5 s).
   M1 compose sets `FLAGD_RESOLVER=file` and points at
   `app/flags/flags.json` (flagd's own JSON format, `$schema
   https://flagd.dev/schema/v0/flags.json`) copied into the image. M2
   switches to `FLAGD_RESOLVER=in-process FLAGD_HOST=flagd
   FLAGD_SYNC_PORT=8015` with the same file mounted into flagd: no code change.
   Every evaluation passes `EvaluationContext(attributes={"version":
   APP_VERSION})` so M3 can target a flag at the canary only.
4. **The flag is `waitlist`**, boolean, default `off`. It is exactly the
   flag §8 toggles. At M1 the waitlist does not exist, so when the meetup is
   full and the flag is on, `POST /api/meetups/{id}/registrations` answers
   `501 {"detail":"waitlist is not implemented; see the golden path ticket"}`.
   That is a declared missing feature, not a mock, and it gives M3 a real 5xx
   behind a real flag without any model call.

## Alternatives rejected

- Default (old) semconv: `http_server_duration_milliseconds` with
  `http_status_code`, deprecated since 2023; Cloud Run's collector and
  Managed Prometheus examples use the stable names, and L0 must match L2.
- `http/dup`: doubles every series to keep both names; nobody consumes the old ones.
- A hand-rolled `prometheus_client` Counter/Histogram: three lines less
  code, but the metric names would be ours, not the semconv's, and the
  `Metrics` port promises the same PromQL against a managed backend.
- Flag file path hardcoded in Python, or a `flags.py` abstraction over
  OpenFeature: the SDK is already the abstraction (plan §4).
- A second flag (`chaos.*`) for M3's failing version: one more knob to
  explain on stage; the 501 under `waitlist` tells the same story truthfully.

## Consequences

- The Prometheus exporter has no multiprocess support: one uvicorn worker,
  forever, or the metrics silently split. ADR 0005 already fixes one worker.
- `openfeature-provider-flagd` drags in `grpcio` and `protobuf` (~20 MB of
  wheels) even in file mode. Accepted: M2 needs them in-process anyway.
- `OTEL_SEMCONV_STABILITY_OPT_IN` is an env var; unset it and every metric
  name changes without an error. The image `ENV` and the names test are the
  two guards. `verify/slo.promql` is written against section 2 verbatim.
- The 501 only fires on a full meetup; M3's load generator must create a
  capacity-1 meetup and register twice. That is a feature of the demo
  script, not of the app.

## Golden-rule check

No collector, no server, no key: `/metrics` is plain text on the app port.
Passes.
