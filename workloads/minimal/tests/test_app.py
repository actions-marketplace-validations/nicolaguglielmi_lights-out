"""Routes and flag behaviour for the minimal workload (docs/adr/0030 §6):
/healthz, /ping (200 normally, 501 while `outage` is on) and /metrics.
"""

import json
import os
import time
from pathlib import Path

from minimal.app import APP_VERSION, outage_enabled

FLAG_FILE = Path(os.environ["FLAGD_OFFLINE_FLAG_SOURCE_PATH"])
# Captured once, at collection time, before any test mutates FLAG_FILE: the
# exact bytes committed for `outage` (docs/adr/0030 §6) -- `targeting`
# present, `defaultVariant` "off". "off" below restores this verbatim, so a
# run that fails partway through still leaves FLAG_FILE exactly as committed,
# never a targeting-less approximation of it.
_COMMITTED_FLAGS_TEXT = FLAG_FILE.read_text()


def _set_default_variant(variant: str) -> None:
    if variant == "off":
        FLAG_FILE.write_text(_COMMITTED_FLAGS_TEXT)
        return
    # The committed targeting rule (workloads/minimal/flags/flags.json)
    # resolves to a variant name for every context, so flagd never falls
    # through to defaultVariant while it is present. Drop it so
    # defaultVariant governs again.
    data = json.loads(_COMMITTED_FLAGS_TEXT)
    data["flags"]["outage"].pop("targeting", None)
    data["flags"]["outage"]["defaultVariant"] = "on"
    FLAG_FILE.write_text(json.dumps(data))


def _wait_until(expected: bool, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if outage_enabled() is expected:
            return
        time.sleep(0.05)
    raise AssertionError(f"outage_enabled() did not become {expected} within {timeout}s")


def test_outage_enabled_fails_open_when_the_flag_is_unresolvable():
    # Found by cosmic-ray, not by inspection (docs/adr/0015 §3): every other
    # test here resolves `outage` through its defaultVariant or its
    # targeting rule, so `get_boolean_value`'s own `default_value=False`
    # fallback (minimal/app.py) was never on any code path a test took --
    # cosmic-ray's ReplaceFalseWithTrue mutant on that line survived. Fail
    # *open* (serve traffic) rather than *closed* (501 everything) when the
    # flag itself cannot be resolved is the deliberate posture -- the same
    # one meetups.flags.waitlist_enabled() relies on -- so a flagd hiccup
    # never takes this workload down by itself; this is the test that would
    # catch it silently flipping to fail-closed. Forced on first, and
    # waited on, so the assertion below proves the deletion actually moved
    # the observed value -- the flag already defaults off, so deleting it
    # and immediately observing "off" would pass whether or not the
    # deletion was ever picked up.
    _set_default_variant("on")
    try:
        _wait_until(True)

        data = json.loads(_COMMITTED_FLAGS_TEXT)
        del data["flags"]["outage"]
        FLAG_FILE.write_text(json.dumps(data))

        _wait_until(False)
        assert outage_enabled() is False
    finally:
        _set_default_variant("off")
        _wait_until(False)


def test_healthz_returns_ok_status_and_version(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": APP_VERSION}


def test_ping_returns_ok_when_outage_flag_is_off(client):
    _wait_until(False)
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_ping_returns_501_when_outage_flag_forced_on(client):
    _set_default_variant("on")
    try:
        _wait_until(True)
        resp = client.get("/ping")
        assert resp.status_code == 501
        assert resp.json()["detail"] == "outage"
    finally:
        _set_default_variant("off")
        _wait_until(False)


def test_metrics_exposes_stable_http_semconv_shape(client):
    client.get("/ping")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text

    assert "http_server_request_duration_seconds_count" in text
    assert "http_server_request_duration_seconds_bucket" in text
    assert "http_response_status_code" in text
    assert "http_route" in text
    assert 'le="0.005"' in text
    assert 'le="+Inf"' in text

    for line in text.splitlines():
        if line.startswith("#"):
            continue
        assert 'http_route="/healthz"' not in line
        assert 'http_route="/metrics"' not in line
