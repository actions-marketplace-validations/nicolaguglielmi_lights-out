"""Client for the geocoder dependency, fake or real (docs/adr/0006)."""

import os

import httpx

TIMEOUT_SECONDS = 2.0


class GeocoderUnavailable(Exception):
    pass


def geocode(venue: str) -> tuple[float | None, float | None]:
    base_url = os.environ["GEOCODER_URL"]
    try:
        response = httpx.get(
            f"{base_url}/search",
            params={"q": venue, "format": "jsonv2", "limit": 1},
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise GeocoderUnavailable(str(exc)) from exc
    if response.status_code >= 500:
        raise GeocoderUnavailable(f"status {response.status_code}")
    results = response.json()
    if not results:
        return None, None
    match = results[0]
    return float(match["lat"]), float(match["lon"])
