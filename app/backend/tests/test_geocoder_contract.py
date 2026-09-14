import json
import threading
from pathlib import Path

import httpx
import pytest

from fakes.geocoder.server import create_server

EXAMPLES_PATH = (
    Path(__file__).resolve().parent.parent / "contracts" / "geocoder" / "examples.json"
)


@pytest.fixture
def fake_server():
    server = create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield base_url
    server.shutdown()
    server.server_close()


def _examples():
    with open(EXAMPLES_PATH) as f:
        return json.load(f)


@pytest.mark.parametrize("example", _examples(), ids=lambda e: e["request"]["q"])
def test_fake_answers_every_example_verbatim(fake_server, example):
    resp = httpx.get(
        f"{fake_server}/search",
        params={"q": example["request"]["q"], "format": "jsonv2", "limit": 1},
    )
    assert resp.status_code == example["response"]["status"]
    assert resp.json() == example["response"]["body"]


def test_query_not_in_the_contract_is_404(fake_server):
    resp = httpx.get(f"{fake_server}/search", params={"q": "definitely not in the contract"})
    assert resp.status_code == 404
