import threading

import pytest

from fakes.geocoder.server import create_server
from meetups.geocoder_client import GeocoderUnavailable, geocode


@pytest.fixture
def fake_server(monkeypatch):
    server = create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("GEOCODER_URL", f"http://127.0.0.1:{server.server_address[1]}")
    yield server
    server.shutdown()
    server.server_close()


def test_geocode_matching_venue_returns_contract_coordinates(fake_server):
    lat, lon = geocode("Milano, Duomo")
    assert lat == pytest.approx(45.4641)
    assert lon == pytest.approx(9.1919)


def test_geocode_no_match_returns_none_none(fake_server):
    assert geocode("Nowhere, Atlantis") == (None, None)


def test_geocode_raises_when_geocoder_unreachable(fake_server):
    fake_server.shutdown()
    fake_server.server_close()
    with pytest.raises(GeocoderUnavailable):
        geocode("Milano, Duomo")


def test_create_meetup_returns_502_when_geocoder_unreachable(client, fake_server):
    fake_server.shutdown()
    fake_server.server_close()

    client.post("/api/signup", json={"email": "geo@example.com", "password": "hunter2"})
    token = client.post(
        "/api/login", json={"email": "geo@example.com", "password": "hunter2"}
    ).json()["token"]

    resp = client.post(
        "/api/meetups",
        json={
            "title": "t",
            "starts_at": "2026-01-01T10:00:00Z",
            "venue": "Milano, Duomo",
            "capacity": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 502
