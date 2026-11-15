from collections import Counter, deque
from dataclasses import dataclass, field

import numpy as np

from eye.beacon import Policy
from eye.erase import erase_person
from eye.people import Detector, Person, Tracker
from eye.radio import Heard
from eye.spots import Spots
from eye.watch import Direct


@dataclass
class Settings:
    delay_seconds: float = 2.5
    tag_reach: float = 0.15
    blind_seconds: float = 0.8
    to_scene: np.ndarray | None = None


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
    asking: int


@dataclass
class _Sighting:
    seconds: float
    people: list[Person]


@dataclass
class _Match:
    code: int
    policy: Policy


@dataclass
class Pipeline:
    detector: Detector | None = None
    settings: Settings = field(default_factory=Settings)
    tracker: Tracker = field(default_factory=Tracker)
    spots: Spots = field(default_factory=Spots)
    eyes: object = None
    tripped: str | None = None
    _sightings: deque = field(default_factory=deque)
    _matches: dict[int, _Match] = field(default_factory=dict)
    _protected: dict[int, tuple[float, Policy]] = field(default_factory=dict)
    _born: dict[int, float] = field(default_factory=dict)
    _hold_since: float | None = None
    _hold_births: list[float] = field(default_factory=list)
    _held: list[tuple[float, float]] = field(default_factory=list)
    _queue: deque = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.eyes is None:
            self.eyes = Direct(self.detector)

    def push(self, seconds: float, scene: np.ndarray, infrared: np.ndarray, heard: list[Heard]) -> list[Released]:
        if self.tripped is None:
            try:
                self._advance(seconds, scene, infrared, heard)
            except Exception as error:
                self.tripped = f"{type(error).__name__}: {error}"
        self._queue.append(_Frame(seconds, scene, len(heard)))
        return self._release(seconds)

    def flush(self, seconds: float) -> list[Released]:
        return self._release(seconds + self.settings.delay_seconds)

    def _advance(self, seconds: float, scene: np.ndarray, infrared: np.ndarray, heard: list[Heard]) -> None:
        gray = infrared if infrared.ndim == 2 else infrared.max(axis=2)
        self.spots.update(seconds, gray)

        for sight_seconds, detections in self.eyes.look(seconds, scene):
            people = self.tracker.update(detections, sight_seconds)
            self._sightings.append(_Sighting(sight_seconds, people))
            for person in people:
                self._born.setdefault(person.track, sight_seconds)
        latest = self._sightings[-1] if self._sightings else None
        alive = {person.track for person in latest.people} if latest else set()
        for track in list(self._born):
            if track not in alive:
                del self._born[track]
        for track in list(self._matches):
            if track not in alive:
                self._protected[track] = (seconds, self._matches.pop(track).policy)

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
        fresh = latest is not None and seconds - latest.seconds <= self.settings.blind_seconds
        open_codes = [code for code, count in announced.items() if count > matched[code]]
        if fresh and open_codes:
            for sighted in self.spots.read(open_codes):
                if announced[sighted.code] <= matched[sighted.code]:
                    continue
                owner = self._owner(sighted.x, sighted.y, latest.people)
                if owner is None:
                    continue
                self._matches[owner.track] = _Match(sighted.code, policies[sighted.code])
                matched[sighted.code] += 1
                if was_holding:
                    self._hold_births.append(self._born[owner.track])

        surplus = any(count > matched[code] for code, count in announced.items())
        if surplus and self._hold_since is None:
            self._hold_since = seconds
        if not surplus and self._hold_since is not None:
            settled = max(self._hold_births) if self._hold_births else seconds
            if settled > self._hold_since:
                self._held.append((self._hold_since, settled))
            self._hold_since = None
            self._hold_births = []

        horizon = seconds - self.settings.delay_seconds - 1.0
        while len(self._sightings) > 2 and self._sightings[1].seconds < horizon:
            self._sightings.popleft()
        self._held = [span for span in self._held if span[1] >= horizon]
        self._protected = {k: v for k, v in self._protected.items() if v[0] >= horizon}

    def _owner(self, x: float, y: float, people: list[Person]) -> Person | None:
        if self.settings.to_scene is not None:
            moved = self.settings.to_scene @ np.array([x, y, 1.0])
            x, y = float(moved[0] / moved[2]), float(moved[1] / moved[2])
        best = None
        best_rank = None
        for person in people:
            if person.track in self._matches or person.coasting:
                continue
            box = person.box
            pad_x = (box[2] - box[0]) * self.settings.tag_reach
            pad_y = (box[3] - box[1]) * self.settings.tag_reach
            if not (box[0] - pad_x <= x <= box[2] + pad_x and box[1] - pad_y <= y <= box[3] + pad_y):
                continue
            on_body = 1
            body = person.body
            if body is not None and body.size:
                row = int(y - box[1])
                col = int(x - box[0])
                patch = body[max(row - 6, 0) : max(row + 7, 0), max(col - 6, 0) : max(col + 7, 0)]
                if patch.size and patch.any():
                    on_body = 0
            center_x = (box[0] + box[2]) / 2
            center_y = (box[1] + box[3]) / 2
            rank = (on_body, abs(x - center_x) / max(box[2] - box[0], 1) + abs(y - center_y) / max(box[3] - box[1], 1))
            if best_rank is None or rank < best_rank:
                best, best_rank = person, rank
        return best

    def _holding(self, seconds: float) -> bool:
        if self._hold_since is not None and seconds >= self._hold_since:
            return True
        return any(start <= seconds <= end for start, end in self._held)

    def _around(self, seconds: float) -> list[_Sighting]:
        before = None
        after = None
        for sighting in self._sightings:
            if sighting.seconds <= seconds:
                before = sighting
            else:
                after = sighting
                break
        near = [s for s in (before, after) if s is not None and abs(s.seconds - seconds) <= self.settings.blind_seconds]
        return near

    def _release(self, now: float) -> list[Released]:
        out = []
        while self._queue and self._queue[0].seconds <= now - self.settings.delay_seconds:
            out.append(self._compose(self._queue.popleft()))
        return out

    def _compose(self, frame: _Frame) -> Released:
        sightings = [] if self.tripped is not None else self._around(frame.seconds)
        if not sightings:
            return Released(frame.seconds, np.zeros_like(frame.scene), 0, False, frame.asking, True)
        image = frame.scene.copy()
        holding = self._holding(frame.seconds)
        erased: set[int] = set()
        for sighting in sightings:
            for person in sighting.people:
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
                erase_person(image, person, policy)
                erased.add(person.track)
        return Released(frame.seconds, image, len(erased), holding, frame.asking, False)
