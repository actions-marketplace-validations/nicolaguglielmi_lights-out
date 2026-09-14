#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# verify-metric-shape: checks verify/slo.promql against one live scrape of
# the running app (docs/adr/0011). It proves the queries reference metric
# and label names the app actually emits, with the semconv seconds buckets;
# it does not evaluate rate() or histogram_quantile() — that needs a TSDB
# (Prometheus at M2, canary vs stable comparison at M3).
set -eu
name=metric-shape
. ci/lib.sh

: "${APP_URL:=http://host.containers.internal:8080}"

promql=verify/slo.promql
[ -f "$promql" ] || nogo "$promql not found"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

if ! curl -fsS --connect-timeout 1 --max-time 3 "$APP_URL/api/meetups" >/dev/null 2>"$tmp/meetups.err"; then
  cat "$tmp/meetups.err" >&2
  nogo "app not reachable at $APP_URL; run ./go up"
fi

if ! curl -fsS --connect-timeout 1 --max-time 3 "$APP_URL/metrics" >"$tmp/metrics.txt" 2>"$tmp/metrics.err"; then
  cat "$tmp/metrics.err" >&2
  nogo "app not reachable at $APP_URL; run ./go up"
fi

reason=$(python3 - "$promql" "$tmp/metrics.txt" <<'PY'
import re
import sys


def fail(message: str) -> None:
    print(message)
    sys.exit(1)


try:
    promql_path, metrics_path = sys.argv[1], sys.argv[2]

    with open(promql_path) as f:
        promql_text = f.read()

    blocks = [b for b in promql_text.split("\n\n") if b.strip()]
    queries: dict[str, str] = {}
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if len(lines) != 2 or not lines[0].startswith("# name:"):
            fail(f"malformed block in {promql_path}: {block!r}")
        qname = lines[0].split("# name:", 1)[1].strip()
        qtext = lines[1].strip()
        if not qtext:
            fail(f"query {qname} has no query line")
        queries[qname] = qtext

    expected_names = {"error_rate", "latency_p95"}
    if set(queries) != expected_names:
        fail(
            f"{promql_path} must define exactly {sorted(expected_names)}, "
            f"found {sorted(queries)}"
        )

    metric_re = re.compile(r"\b([a-zA-Z_:][a-zA-Z0-9_:]*)\s*(?=[{\[])")
    label_re = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=~?")
    by_re = re.compile(r"by\s*\(([^)]*)\)")

    with open(metrics_path) as f:
        metrics_text = f.read()
    metrics_lines = metrics_text.splitlines()

    def family_lines(metric: str) -> list[str]:
        pat = re.compile(r"^" + re.escape(metric) + r"(\{|\s)")
        return [ln for ln in metrics_lines if pat.match(ln)]

    for qname, qtext in queries.items():
        q_metrics = set(metric_re.findall(qtext))
        if not any(m.startswith("http_") for m in q_metrics):
            fail(f"query {qname} references no http_-prefixed metric")

        q_labels = set(label_re.findall(qtext))
        for group in by_re.findall(qtext):
            q_labels |= {g.strip() for g in group.split(",") if g.strip()}

        for metric in q_metrics:
            flines = family_lines(metric)
            if not flines:
                fail(f"metric {metric} (from query {qname}) not found in /metrics scrape")
            for label in q_labels:
                if not any(f'{label}="' in ln for ln in flines):
                    fail(
                        f"label {label} not found on metric {metric} "
                        f"(from query {qname}) in /metrics scrape"
                    )

    for marker in ('le="0.005"', 'le="+Inf"'):
        if marker not in metrics_text:
            fail(f"missing histogram bucket boundary {marker} in /metrics scrape")
    if 'le="10"' not in metrics_text and 'le="10.0"' not in metrics_text:
        fail('missing histogram bucket boundary le="10" (or "10.0") in /metrics scrape')

    status_re = re.compile(r'http_response_status_code="([^"]*)"')
    statuses = set(status_re.findall(metrics_text))
    if not statuses:
        fail("http_response_status_code label not observed in /metrics scrape")
    bad = sorted(s for s in statuses if not re.fullmatch(r"[1-5][0-9][0-9]", s))
    if bad:
        fail(f"http_response_status_code value(s) not well-formed: {bad}")
except SystemExit:
    raise
except Exception as exc:  # keep the contract: one stdout line, always
    fail(f"unexpected error checking {sys.argv[1]} against {sys.argv[2]}: {exc}")
PY
) && ok=1 || ok=0

if [ "$ok" -ne 1 ]; then
  nogo "$reason"
fi

printf 'metric-shape: checked query/app agreement against one live scrape (metric and label names, semconv seconds buckets, status-code value format)\n' >&2
printf 'metric-shape: did not evaluate rate() or histogram_quantile() — needs a TSDB (Prometheus at M2, canary vs stable comparison at M3)\n' >&2
go
