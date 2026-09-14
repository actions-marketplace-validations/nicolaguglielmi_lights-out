import pytest


def test_signup_then_login_authenticates_protected_route(client, geocoder_server):
    signup = client.post(
        "/api/signup", json={"email": "auth@example.com", "password": "hunter2"}
    )
    assert signup.status_code == 201

    login = client.post(
        "/api/login", json={"email": "auth@example.com", "password": "hunter2"}
    )
    assert login.status_code == 200
    token = login.json()["token"]

    resp = client.post(
        "/api/meetups",
        json={
            "title": "Talk",
            "starts_at": "2026-01-01T10:00:00Z",
            "venue": "Milano, Duomo",
            "capacity": 5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


def test_login_wrong_password_is_401(client):
    client.post(
        "/api/signup", json={"email": "wp@example.com", "password": "correct"}
    )
    resp = client.post(
        "/api/login", json={"email": "wp@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_login_unknown_email_is_401(client):
    resp = client.post(
        "/api/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "garbage"},
        {"Authorization": "Bearer not-a-real-token"},
    ],
)
def test_protected_route_rejects_missing_or_garbage_token(client, headers):
    resp = client.post(
        "/api/meetups",
        json={
            "title": "t",
            "starts_at": "2026-01-01T10:00:00Z",
            "venue": "x",
            "capacity": 1,
        },
        headers=headers,
    )
    assert resp.status_code == 401


def test_signup_same_email_twice_is_409(client):
    body = {"email": "dup@example.com", "password": "hunter2"}
    assert client.post("/api/signup", json=body).status_code == 201
    assert client.post("/api/signup", json=body).status_code == 409
