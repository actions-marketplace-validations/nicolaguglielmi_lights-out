"""The geocoder fake: stdlib only, answers verbatim from the committed
contract (docs/adr/0006). Same module runs as the compose service and in the
test suite's background thread — there is no second implementation."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

EXAMPLES_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "contracts"
    / "geocoder"
    / "examples.json"
)


def _load_examples() -> dict[str, dict]:
    with open(EXAMPLES_PATH) as f:
        examples = json.load(f)
    return {example["request"]["q"]: example["response"] for example in examples}


_EXAMPLES_BY_QUERY = _load_examples()


class GeocoderHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/search":
            self.send_response(404)
            self.end_headers()
            return
        query = parse_qs(parsed.query).get("q", [None])[0]
        example = _EXAMPLES_BY_QUERY.get(query)
        if example is None:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(example["body"]).encode()
        self.send_response(example["status"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), GeocoderHandler)


if __name__ == "__main__":
    port = int(os.environ.get("GEOCODER_PORT", "8001"))
    create_server(host="0.0.0.0", port=port).serve_forever()
