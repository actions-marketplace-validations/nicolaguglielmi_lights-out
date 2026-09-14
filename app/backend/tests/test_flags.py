import json
import os
import time
from pathlib import Path

from meetups.flags import waitlist_enabled

FLAG_FILE = Path(os.environ["FLAGD_OFFLINE_FLAG_SOURCE_PATH"])


def _set_default_variant(variant: str) -> None:
    data = json.loads(FLAG_FILE.read_text())
    data["flags"]["waitlist"]["defaultVariant"] = variant
    FLAG_FILE.write_text(json.dumps(data))


def _wait_until(expected: bool, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if waitlist_enabled() is expected:
            return
        time.sleep(0.05)
    raise AssertionError(f"waitlist_enabled() did not become {expected} within {timeout}s")


def test_waitlist_flag_defaults_off():
    _wait_until(False)
    assert waitlist_enabled() is False


def test_full_meetup_registration_is_501_when_flag_forced_on(client, geocoder_server):
    _set_default_variant("on")
    try:
        _wait_until(True)

        client.post(
            "/api/signup", json={"email": "flagowner@example.com", "password": "hunter2"}
        )
        owner_token = client.post(
            "/api/login", json={"email": "flagowner@example.com", "password": "hunter2"}
        ).json()["token"]
        create = client.post(
            "/api/meetups",
            json={
                "title": "Full room",
                "starts_at": "2026-03-01T18:00:00Z",
                "venue": "Milano, Duomo",
                "capacity": 1,
            },
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        meetup_id = create.json()["id"]

        client.post(
            "/api/signup", json={"email": "flagfirst@example.com", "password": "hunter2"}
        )
        first_token = client.post(
            "/api/login", json={"email": "flagfirst@example.com", "password": "hunter2"}
        ).json()["token"]
        first = client.post(
            f"/api/meetups/{meetup_id}/registrations",
            headers={"Authorization": f"Bearer {first_token}"},
        )
        assert first.status_code == 201

        client.post(
            "/api/signup", json={"email": "flagsecond@example.com", "password": "hunter2"}
        )
        second_token = client.post(
            "/api/login", json={"email": "flagsecond@example.com", "password": "hunter2"}
        ).json()["token"]
        second = client.post(
            f"/api/meetups/{meetup_id}/registrations",
            headers={"Authorization": f"Bearer {second_token}"},
        )
        assert second.status_code == 501
        assert "waitlist is not implemented" in second.json()["detail"]
    finally:
        _set_default_variant("off")
        _wait_until(False)
