import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

STALE_SECONDS = 1.0
BOUNDARY = "frame"


class Outbox:
    def __init__(self, width: int = 1280, height: int = 720, quality: int = 80):
        self._lock = threading.Lock()
        self._quality = quality
        self._black = self._encode(np.zeros((height, width, 3), dtype=np.uint8))
        self._jpeg = self._black
        self._stamp = 0.0
        self._state: dict = {"live": False}

    def _encode(self, image: np.ndarray) -> bytes:
        ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self._quality])
        if not ok:
            raise RuntimeError("could not encode frame")
        return data.tobytes()

    def publish(self, image: np.ndarray, state: dict) -> None:
        jpeg = self._encode(image)
        with self._lock:
            self._jpeg = jpeg
            self._stamp = time.monotonic()
            self._state = state

    def latest(self) -> tuple[bytes, dict]:
        with self._lock:
            fresh = time.monotonic() - self._stamp <= STALE_SECONDS
            if fresh:
                return self._jpeg, dict(self._state, live=True)
            return self._black, dict(self._state, live=False, stalled=True)


def _handler(outbox: Outbox):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            return

        def _common(self, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

        def do_GET(self) -> None:
            if self.path.startswith("/state.json"):
                _, state = outbox.latest()
                self._common("application/json")
                self.wfile.write(json.dumps(state).encode())
                return
            if self.path.startswith("/operator.jpg"):
                jpeg, _ = outbox.latest()
                self._common("image/jpeg")
                self.wfile.write(jpeg)
                return
            if self.path.startswith("/operator.mjpg"):
                self._common(f"multipart/x-mixed-replace; boundary={BOUNDARY}")
                try:
                    while True:
                        jpeg, _ = outbox.latest()
                        self.wfile.write(f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode())
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                        time.sleep(1 / 20)
                except (BrokenPipeError, ConnectionResetError):
                    return
            self.send_response(404)
            self.end_headers()

    return Handler


def start(outbox: Outbox, port: int, host: str = "0.0.0.0") -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), _handler(outbox))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
