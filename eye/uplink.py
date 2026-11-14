import json
import threading
import time
import urllib.request

from eye.serve import Outbox


class Uplink:
    def __init__(self, outbox: Outbox, address: str, key: str, rate: float = 12.0):
        self.outbox = outbox
        self.address = address.rstrip("/") + "/push"
        self.key = key
        self.interval = 1.0 / rate
        self.failures = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def send_once(self) -> bool:
        jpeg, state = self.outbox.latest()
        if not state.get("live"):
            return False
        request = urllib.request.Request(
            self.address,
            data=jpeg,
            method="POST",
            headers={"X-Key": self.key, "X-State": json.dumps(state), "Content-Type": "image/jpeg"},
        )
        with urllib.request.urlopen(request, timeout=3) as answer:
            return answer.status == 200

    def _run(self) -> None:
        while not self._stop.is_set():
            began = time.monotonic()
            try:
                self.send_once()
            except OSError:
                self.failures += 1
            self._stop.wait(max(0.0, self.interval - (time.monotonic() - began)))
