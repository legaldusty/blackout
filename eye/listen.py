import asyncio
import threading
import time

from eye.radio import COMPANY_ID, Roster, parse_payload


class Listener:
    def __init__(self, roster: Roster):
        self.roster = roster
        self.error: str | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def heard(self, seconds: float):
        return self.roster.heard(seconds)

    def _run(self) -> None:
        try:
            asyncio.run(self._scan())
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"

    async def _scan(self) -> None:
        from bleak import BleakScanner

        def on_advert(device, advert) -> None:
            body = advert.manufacturer_data.get(COMPANY_ID)
            if body is None:
                return
            heard = parse_payload(device.address, bytes(body))
            if heard is not None:
                self.roster.note(time.monotonic(), heard)

        async with BleakScanner(on_advert):
            while not self._stop.is_set():
                await asyncio.sleep(0.2)
