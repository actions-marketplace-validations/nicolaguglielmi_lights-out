Rename metrics_text to render_metrics

The function renders the Prometheus text page; its name now says so.
app.py's /metrics route calls it by the new name, and a test asserts
the rendered page carries the request-duration histogram.

Hand-written L0 fixture for ticket 0020 (docs/adr/0056 §7): no model
wrote this change.
