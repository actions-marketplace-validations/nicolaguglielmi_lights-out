def test_metrics_exposes_stable_http_semconv_shape(client):
    client.get("/api/meetups")
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
