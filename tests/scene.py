from dataclasses import dataclass, field

import numpy as np

from eye.beacon import Policy, chip_at
from eye.people import Detection
from eye.radio import Heard

WIDTH = 320
HEIGHT = 240
FPS = 30.0
BACKGROUND = 90
SKIN = 200


@dataclass
class Actor:
    name: str
    start_x: float
    speed: float = 0.0
    width: int = 40
    height: int = 120
    top: int = 80
    code: int | None = None
    policy: Policy = Policy.HIDE_ALL
    light_from: float = 0.0
    light_until: float = 1e9
    radio_from: float = 0.0
    radio_until: float = 1e9
    hidden_from_detector: tuple[float, float] | None = None

    def box(self, seconds: float):
        left = int(round(self.start_x + self.speed * seconds))
        return left, self.top, left + self.width, self.top + self.height

    def lamp(self, seconds: float):
        left, top, right, _ = self.box(seconds)
        return (left + right) // 2, top + 45


@dataclass
class Scene:
    actors: list[Actor]
    flicker: bool = False
    detector_fails_at: float | None = None
    now: float = 0.0
    _rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(0))

    def frames(self, seconds: float):
        self.now = seconds
        scene = np.full((HEIGHT, WIDTH, 3), BACKGROUND, dtype=np.uint8)
        infrared = self._rng.integers(0, 6, (HEIGHT, WIDTH), dtype=np.uint8)
        if self.flicker:
            infrared[10:30, 10:60] = int(120 + 100 * np.sin(2 * np.pi * 1.3 * seconds))
        for actor in self.actors:
            left, top, right, bottom = actor.box(seconds)
            scene[top:bottom, left:right] = SKIN
            lit = actor.code is not None and actor.light_from <= seconds < actor.light_until
            if lit and chip_at(actor.code, seconds):
                x, y = actor.lamp(seconds)
                infrared[y - 1 : y + 2, x - 1 : x + 2] = 255
        return scene, infrared

    def heard(self, seconds: float):
        return [
            Heard(actor.name, actor.code, actor.policy)
            for actor in self.actors
            if actor.code is not None and actor.radio_from <= seconds < actor.radio_until
        ]

    def detect(self, scene):
        if self.detector_fails_at is not None and self.now >= self.detector_fails_at:
            raise RuntimeError("detector stopped")
        found = []
        for actor in self.actors:
            gap = actor.hidden_from_detector
            if gap is not None and gap[0] <= self.now < gap[1]:
                continue
            left, top, right, bottom = actor.box(self.now)
            body = np.ones((bottom - top, right - left), dtype=bool)
            face = np.zeros_like(body)
            face[:25, 8:-8] = True
            found.append(Detection((left, top, right, bottom), body, face))
        return found

    def visible_fraction(self, actor: Actor, released, rows=None):
        left, top, right, bottom = actor.box(released.seconds)
        patch = released.image[top:bottom, left:right, 0]
        if rows is not None:
            patch = patch[rows[0] : rows[1]]
        return float(np.count_nonzero(patch == SKIN)) / patch.size


def run(scene: Scene, pipeline, seconds: float):
    out = []
    count = int(round(seconds * FPS))
    for index in range(count):
        moment = index / FPS
        image, infrared = scene.frames(moment)
        out.extend(pipeline.push(moment, image, infrared, scene.heard(moment)))
    return out
