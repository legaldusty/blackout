import argparse
import hmac
import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

STALE_SECONDS = 1.5
MAX_PUSH_BYTES = 2_000_000
SITE = Path(__file__).resolve().parents[1] / "site"
STATIC_TYPES = {".html", ".css", ".js", ".svg", ".woff2", ".png", ".jpg", ".json", ".ico", ".webmanifest"}


class Outbox:
    def __init__(self, width: int = 1280, height: int = 720, quality: int = 80):
        self._lock = threading.Lock()
        self._quality = quality
        self._black = self._encode(np.zeros((height, width, 3), dtype=np.uint8))
        self._jpeg = self._black
        self._stamp = 0.0
        self._state: dict = {}

    def _encode(self, image: np.ndarray) -> bytes:
        ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self._quality])
        if not ok:
            raise RuntimeError("could not encode frame")
        return data.tobytes()

    def publish(self, image: np.ndarray, state: dict) -> None:
        self.publish_jpeg(self._encode(image), state)

    def publish_jpeg(self, jpeg: bytes, state: dict) -> None:
        with self._lock:
            self._jpeg = jpeg
            self._stamp = time.monotonic()
            self._state = state

    def latest(self) -> tuple[bytes, dict]:
        with self._lock:
            if self._stamp == 0.0:
                return self._black, {"live": False, "stalled": False}
            if time.monotonic() - self._stamp <= STALE_SECONDS:
                return self._jpeg, dict(self._state, live=True, stalled=False)
            return self._black, dict(self._state, live=False, stalled=True)


def _handler(outbox: Outbox, key: str | None, site: Path | None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            return

        def _send(self, status: int, content_type: str, body: bytes, cache: str = "no-store") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            route = self.path.split("?", 1)[0]
            if route == "/state.json":
                self._send(200, "application/json", json.dumps(outbox.latest()[1]).encode())
                return
            if route == "/operator.jpg":
                self._send(200, "image/jpeg", outbox.latest()[0])
                return
            if site is not None:
                name = "index.html" if route == "/" else route.lstrip("/")
                target = (site / name).resolve()
                inside = site.resolve() in target.parents
                if inside and target.is_file() and target.suffix in STATIC_TYPES:
                    kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                    self._send(200, kind, target.read_bytes(), "no-cache")
                    return
            self._send(404, "text/plain", b"not found")

        def do_POST(self) -> None:
            route = self.path.split("?", 1)[0]
            given = self.headers.get("X-Key", "")
            if route != "/push" or key is None or not hmac.compare_digest(given, key):
                self._send(403, "text/plain", b"no")
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_PUSH_BYTES:
                self._send(413, "text/plain", b"too large")
                return
            body = self.rfile.read(length)
            try:
                state = json.loads(self.headers.get("X-State", "{}"))
            except json.JSONDecodeError:
                state = {}
            if not isinstance(state, dict) or not body.startswith(b"\xff\xd8"):
                self._send(400, "text/plain", b"bad frame")
                return
            outbox.publish_jpeg(body, state)
            self._send(200, "text/plain", b"ok")

    return Handler


def start(outbox: Outbox, port: int, host: str = "0.0.0.0", key: str | None = None, site: Path | None = SITE) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), _handler(outbox, key, site))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    key = os.environ.get("BLACKOUT_KEY")
    if not key:
        raise SystemExit("set BLACKOUT_KEY")
    start(Outbox(), args.port, args.host, key)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
