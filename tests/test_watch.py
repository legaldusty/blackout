import time

import numpy as np
import pytest

from eye.people import Detection
from eye.pipeline import Pipeline
from eye.watch import Background
from tests.scene import FPS, Actor, Scene


class Steady:
    def __init__(self, pause=0.02, fail=False):
        self.pause = pause
        self.fail = fail

    def detect(self, scene):
        time.sleep(self.pause)
        if self.fail:
            raise RuntimeError("detector stopped")
        return [Detection((1, 2, 3, 4), np.ones((2, 2), dtype=bool))]


def test_background_results_keep_the_time_of_their_frame():
    eyes = Background(Steady())
    assert eyes.look(1.0, "frame") == []
    time.sleep(0.15)
    done = eyes.look(2.0, "frame")
    assert [seconds for seconds, _ in done] == [1.0]
    assert done[0][1][0].box == (1, 2, 3, 4)


def test_background_failure_is_raised_to_the_caller():
    eyes = Background(Steady(fail=True))
    eyes.look(1.0, "frame")
    time.sleep(0.15)
    with pytest.raises(RuntimeError):
        eyes.look(2.0, "frame")


class Late:
    def __init__(self, scene, every=4, lag=3):
        self.scene = scene
        self.every = every
        self.lag = lag
        self.count = 0
        self.waiting = []

    def look(self, seconds, image):
        if self.count % self.every == 0:
            self.waiting.append((self.count + self.lag, seconds, self.scene.detect(image)))
        ready = [(s, found) for due, s, found in self.waiting if due <= self.count]
        self.waiting = [item for item in self.waiting if item[0] > self.count]
        self.count += 1
        return ready


def run(scene, pipeline, seconds):
    out = []
    for index in range(int(round(seconds * FPS))):
        moment = index / FPS
        image, infrared = scene.frames(moment)
        out.extend(pipeline.push(moment, image, infrared, scene.heard(moment)))
    return out


def test_slow_late_detection_still_never_shows_a_moving_tagged_person():
    tagged = Actor("tag", 20, speed=15, code=1)
    other = Actor("other", 262, speed=-2)
    scene = Scene([tagged, other])
    pipeline = Pipeline(eyes=Late(scene))
    released = run(scene, pipeline, 10.0)
    assert len(released) > 200
    assert max(scene.visible_fraction(tagged, r) for r in released) == 0.0
    assert min(scene.visible_fraction(other, r) for r in released) == 1.0


def test_detector_that_stops_answering_turns_frames_black():
    scene = Scene([Actor("p", 120)])

    class Quiet:
        def __init__(self):
            self.count = 0

        def look(self, seconds, image):
            self.count += 1
            return [(seconds, scene.detect(image))] if seconds < 2.0 else []

    released = run(scene, Pipeline(eyes=Quiet()), 8.0)
    early = [r for r in released if r.seconds < 1.5]
    late = [r for r in released if r.seconds > 2.8]
    assert early and all(not r.tripped for r in early)
    assert late and all(r.tripped and not r.image.any() for r in late)
