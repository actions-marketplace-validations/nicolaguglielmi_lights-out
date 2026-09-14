import pytest


def _signup_and_login(client, email, password="hunter2"):
    client.post("/api/signup", json={"email": email, "password": password})
    login = client.post("/api/login", json={"email": email, "password": password})
    return login.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_full_happy_path(client, geocoder_server):
    token = _signup_and_login(client, "happy@example.com")
    headers = _auth(token)

    create = client.post(
        "/api/meetups",
        json={
            "title": "PromQL night",
            "starts_at": "2026-03-01T18:00:00Z",
            "venue": "Milano, Duomo",
            "capacity": 10,
        },
        headers=headers,
    )
    assert create.status_code == 201
    body = create.json()
    meetup_id = body["id"]
    assert body["venue_lat"] == pytest.approx(45.4641)
    assert body["venue_lon"] == pytest.approx(9.1919)

    listing = client.get("/api/meetups")
    assert listing.status_code == 200
    assert any(m["id"] == meetup_id for m in listing.json())

    got = client.get(f"/api/meetups/{meetup_id}")
    assert got.status_code == 200
    assert got.json()["id"] == meetup_id

    register = client.post(
        f"/api/meetups/{meetup_id}/registrations", headers=headers
    )
    assert register.status_code == 201


def test_get_unknown_meetup_is_404(client):
    resp = client.get("/api/meetups/999999")
    assert resp.status_code == 404


def test_capacity_full_is_409_when_flag_off(client, geocoder_server):
    owner_token = _signup_and_login(client, "owner@example.com")
    create = client.post(
        "/api/meetups",
        json={
            "title": "Small room",
            "starts_at": "2026-03-01T18:00:00Z",
            "venue": "Roma, Colosseo",
            "capacity": 1,
        },
        headers=_auth(owner_token),
    )
    meetup_id = create.json()["id"]

    first_token = _signup_and_login(client, "first@example.com")
    second_token = _signup_and_login(client, "second@example.com")

    first = client.post(
        f"/api/meetups/{meetup_id}/registrations", headers=_auth(first_token)
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/meetups/{meetup_id}/registrations", headers=_auth(second_token)
    )
    assert second.status_code == 409


def test_registering_same_user_twice_is_409(client, geocoder_server):
    owner_token = _signup_and_login(client, "owner2@example.com")
    create = client.post(
        "/api/meetups",
        json={
            "title": "Big room",
            "starts_at": "2026-03-01T18:00:00Z",
            "venue": "Roma, Colosseo",
            "capacity": 5,
        },
        headers=_auth(owner_token),
    )
    meetup_id = create.json()["id"]

    token = _signup_and_login(client, "twice@example.com")
    headers = _auth(token)
    first = client.post(f"/api/meetups/{meetup_id}/registrations", headers=headers)
    assert first.status_code == 201
    second = client.post(f"/api/meetups/{meetup_id}/registrations", headers=headers)
    assert second.status_code == 409
