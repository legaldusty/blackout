from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class Detection:
    box: Box
    body: np.ndarray
    face: np.ndarray | None = None


@dataclass(frozen=True)
class Person:
    track: int
    box: Box
    body: np.ndarray
    face: np.ndarray | None
    coasting: bool


class Detector(Protocol):
    def detect(self, scene: np.ndarray) -> list[Detection]: ...


def overlap(a: Box, b: Box) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    shared = (right - left) * (bottom - top)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return shared / float(area_a + area_b - shared)


@dataclass
class _Track:
    number: int
    detection: Detection
    seen: float


@dataclass
class Tracker:
    min_overlap: float = 0.25
    coast_seconds: float = 0.7
    _tracks: list[_Track] = field(default_factory=list)
    _next: int = 1

    def update(self, detections: list[Detection], seconds: float) -> list[Person]:
        pairs = []
        for t_index, track in enumerate(self._tracks):
            for d_index, detection in enumerate(detections):
                score = overlap(track.detection.box, detection.box)
                if score >= self.min_overlap:
                    pairs.append((score, t_index, d_index))
        pairs.sort(reverse=True)
        taken_tracks: set[int] = set()
        taken_detections: set[int] = set()
        for _, t_index, d_index in pairs:
            if t_index in taken_tracks or d_index in taken_detections:
                continue
            taken_tracks.add(t_index)
            taken_detections.add(d_index)
            self._tracks[t_index].detection = detections[d_index]
            self._tracks[t_index].seen = seconds
        for d_index, detection in enumerate(detections):
            if d_index in taken_detections:
                continue
            self._tracks.append(_Track(self._next, detection, seconds))
            self._next += 1
        self._tracks = [t for t in self._tracks if seconds - t.seen <= self.coast_seconds]
        return [
            Person(t.number, t.detection.box, t.detection.body, t.detection.face, t.seen < seconds)
            for t in self._tracks
        ]
