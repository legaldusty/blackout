import threading

from eye.people import Detection, Detector

Sightings = list[tuple[float, list[Detection]]]


class Direct:
    def __init__(self, detector: Detector):
        self._detector = detector

    def look(self, seconds: float, scene) -> Sightings:
        return [(seconds, self._detector.detect(scene))]


class Background:
    def __init__(self, detector: Detector):
        self._detector = detector
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._pending = None
        self._done: Sightings = []
        self.error: str | None = None
        threading.Thread(target=self._run, daemon=True).start()

    def look(self, seconds: float, scene) -> Sightings:
        if self.error is not None:
            raise RuntimeError(self.error)
        with self._lock:
            self._pending = (seconds, scene)
            done, self._done = self._done, []
        self._wake.set()
        return done

    def _run(self) -> None:
        while True:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                job, self._pending = self._pending, None
            if job is None:
                continue
            try:
                found = self._detector.detect(job[1])
            except Exception as error:
                self.error = f"{type(error).__name__}: {error}"
                return
            with self._lock:
                self._done.append((job[0], found))
