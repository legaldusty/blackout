import json
import time
import urllib.request

import numpy as np

from eye import serve
from eye.app import run
from eye.pipeline import Pipeline
from eye.serve import Outbox, start
from tests.scene import FPS, HEIGHT, WIDTH, Actor, Scene


class Feed:
    def __init__(self, scene):
        self.scene = scene
        self.index = 0

    def read(self):
        seconds = self.index / FPS
        self.index += 1
        image, infrared = self.scene.frames(seconds)
        return seconds, image, infrared

    def heard(self, seconds):
        return self.scene.heard(seconds)


def decode(jpeg):
    import cv2

    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)


def test_live_loop_publishes_only_erased_frames():
    tagged = Actor("tag", 140, code=2)
    scene = Scene([tagged])
    feed = Feed(scene)
    outbox = Outbox(WIDTH, HEIGHT, quality=95)
    run(feed, feed, Pipeline(detector=scene), outbox, frames=240)
    jpeg, state = outbox.latest()
    image = decode(jpeg)
    left, top, right, bottom = tagged.box(0.0)
    assert state["live"] and state["erased"] == 1 and state["asking"] == 1
    assert image[top + 5 : bottom - 5, left + 5 : right - 5].max() < 30
    assert image[10:40, 10:40].mean() > 60


def test_stalled_camera_shows_black(monkeypatch):
    outbox = Outbox(WIDTH, HEIGHT)
    outbox.publish(np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8), {"erased": 0})
    assert decode(outbox.latest()[0]).mean() > 150
    monkeypatch.setattr(serve, "STALE_SECONDS", 0.05)
    time.sleep(0.12)
    jpeg, state = outbox.latest()
    assert decode(jpeg).max() < 10
    assert state["live"] is False and state["stalled"] is True


def test_server_hands_out_the_frame_and_the_state():
    outbox = Outbox(WIDTH, HEIGHT)
    outbox.publish(np.full((HEIGHT, WIDTH, 3), 128, dtype=np.uint8), {"erased": 3})
    server = start(outbox, 0, host="127.0.0.1")
    port = server.server_address[1]
    try:
        state = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/state.json", timeout=3).read())
        jpeg = urllib.request.urlopen(f"http://127.0.0.1:{port}/operator.jpg", timeout=3).read()
    finally:
        server.shutdown()
    assert state["erased"] == 3 and state["live"] is True
    assert abs(float(decode(jpeg).mean()) - 128) < 4
