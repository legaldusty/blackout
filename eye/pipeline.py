from collections import Counter, deque
from dataclasses import dataclass, field

import numpy as np

from eye.beacon import Policy
from eye.erase import erase_person
from eye.people import Detector, Person, Tracker
from eye.radio import Heard
from eye.reader import CONFIRM_PERIODS, SAMPLE_RATE, Reader
from eye.sampling import brightest_per_cell, cell_center, grow_box, map_box


@dataclass
class Settings:
    delay_seconds: float = 2.5
    rows: int = 10
    cols: int = 6
    sample_growth: float = 0.08
    erase_growth: float = 0.06
    transform: np.ndarray | None = None
    sample_rate: float = SAMPLE_RATE


@dataclass(frozen=True)
class Released:
    seconds: float
    image: np.ndarray
    erased: int
    holding: bool
    asking: int
    tripped: bool


@dataclass
class _Frame:
    seconds: float
    scene: np.ndarray
    people: list[Person]
    asking: int


@dataclass
class _Match:
    code: int
    policy: Policy


@dataclass
class Pipeline:
    detector: Detector
    settings: Settings = field(default_factory=Settings)
    tracker: Tracker = field(default_factory=Tracker)
    tripped: str | None = None
    _readers: dict[int, Reader] = field(default_factory=dict)
    _matches: dict[int, _Match] = field(default_factory=dict)
    _protected: dict[int, tuple[float, Policy]] = field(default_factory=dict)
    _hold_since: float | None = None
    _hold_births: list[float] = field(default_factory=list)
    _born: dict[int, float] = field(default_factory=dict)
    _held: list[tuple[float, float]] = field(default_factory=list)
    _queue: deque = field(default_factory=deque)

    def push(self, seconds: float, scene: np.ndarray, infrared: np.ndarray, heard: list[Heard]) -> list[Released]:
        if self.tripped is None:
            try:
                self._advance(seconds, scene, infrared, heard)
            except Exception as error:
                self.tripped = f"{type(error).__name__}: {error}"
        if self.tripped is not None:
            self._queue.append(_Frame(seconds, scene, [], len(heard)))
        return self._release(seconds)

    def flush(self, seconds: float) -> list[Released]:
        return self._release(seconds + self.settings.delay_seconds)

    def _advance(self, seconds: float, scene: np.ndarray, infrared: np.ndarray, heard: list[Heard]) -> None:
        settings = self.settings
        people = self.tracker.update(self.detector.detect(scene), seconds)
        alive = {person.track for person in people}
        for track in list(self._readers):
            if track not in alive:
                del self._readers[track]
                self._born.pop(track, None)
        for track in list(self._matches):
            if track not in alive:
                self._protected[track] = (seconds, self._matches.pop(track).policy)

        gray = infrared if infrared.ndim == 2 else infrared.max(axis=2)
        scene_height, scene_width = scene.shape[:2]
        infrared_height, infrared_width = gray.shape[:2]
        grown = {}
        for person in people:
            box = grow_box(person.box, settings.sample_growth, scene_width, scene_height)
            grown[person.track] = box
            source = map_box(box, settings.transform, infrared_width, infrared_height)
            values = brightest_per_cell(gray, source, settings.rows, settings.cols)
            if person.track not in self._readers:
                self._readers[person.track] = Reader(settings.sample_rate)
                self._born[person.track] = seconds
            self._readers[person.track].push(seconds, values)

        announced = Counter(entry.code for entry in heard)
        policies: dict[int, Policy] = {}
        for entry in heard:
            if policies.get(entry.code) is not Policy.HIDE_ALL:
                policies[entry.code] = entry.policy
        for track, match in list(self._matches.items()):
            if match.code not in announced:
                self._protected[track] = (seconds, match.policy)
                del self._matches[track]
            else:
                match.policy = policies[match.code]

        matched = Counter(match.code for match in self._matches.values())
        was_holding = self._hold_since is not None
        for person in people:
            if person.track in self._matches or person.coasting:
                continue
            open_codes = [code for code, count in announced.items() if count > matched[code]]
            if not open_codes:
                break
            reader = self._readers[person.track]
            if not reader.ready(CONFIRM_PERIODS):
                continue
            best = None
            for reading in reader.read_confirmed(codes=open_codes):
                if not self._on_body(person, grown[person.track], reading.cell):
                    continue
                if best is None or reading.score > best.score:
                    best = reading
            if best is not None:
                self._matches[person.track] = _Match(best.code, policies[best.code])
                matched[best.code] += 1
                if was_holding:
                    self._hold_births.append(self._born[person.track])

        surplus = any(count > matched[code] for code, count in announced.items())
        if surplus and self._hold_since is None:
            self._hold_since = seconds
        if not surplus and self._hold_since is not None:
            settled = max(self._hold_births) if self._hold_births else seconds
            if settled > self._hold_since:
                self._held.append((self._hold_since, settled))
            self._hold_since = None
            self._hold_births = []

        self._queue.append(_Frame(seconds, scene, people, len(heard)))
        horizon = seconds - settings.delay_seconds - 1.0
        self._held = [span for span in self._held if span[1] >= horizon]
        self._protected = {k: v for k, v in self._protected.items() if v[0] >= horizon}

    def _on_body(self, person: Person, grown, cell: int) -> bool:
        body = person.body
        if body is None or body.size == 0:
            return True
        x, y = cell_center(cell, grown, self.settings.rows, self.settings.cols)
        cell_width = (grown[2] - grown[0]) / self.settings.cols
        cell_height = (grown[3] - grown[1]) / self.settings.rows
        left = int(np.floor(x - cell_width - person.box[0]))
        right = int(np.ceil(x + cell_width - person.box[0]))
        top = int(np.floor(y - cell_height - person.box[1]))
        bottom = int(np.ceil(y + cell_height - person.box[1]))
        patch = body[max(top, 0) : max(bottom, 0), max(left, 0) : max(right, 0)]
        return patch.size > 0 and bool(patch.any())

    def _holding(self, seconds: float) -> bool:
        if self._hold_since is not None and seconds >= self._hold_since:
            return True
        return any(start <= seconds <= end for start, end in self._held)

    def _release(self, now: float) -> list[Released]:
        out = []
        while self._queue and self._queue[0].seconds <= now - self.settings.delay_seconds:
            out.append(self._compose(self._queue.popleft()))
        return out

    def _compose(self, frame: _Frame) -> Released:
        if self.tripped is not None:
            return Released(frame.seconds, np.zeros_like(frame.scene), 0, False, frame.asking, True)
        image = frame.scene.copy()
        holding = self._holding(frame.seconds)
        erased = 0
        for person in frame.people:
            policy = None
            match = self._matches.get(person.track)
            protected = self._protected.get(person.track)
            if match is not None:
                policy = match.policy
            elif protected is not None and frame.seconds <= protected[0]:
                policy = protected[1]
            if holding and policy is not Policy.HIDE_ALL:
                policy = Policy.HIDE_ALL
            if policy is None:
                continue
            erase_person(image, person, policy, self.settings.erase_growth)
            erased += 1
        return Released(frame.seconds, image, erased, holding, frame.asking, False)
