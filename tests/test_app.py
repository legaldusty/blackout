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


def test_camera_that_never_started_is_off_not_stalled():
    jpeg, state = Outbox(WIDTH, HEIGHT).latest()
    assert decode(jpeg).max() < 10
    assert state == {"live": False, "stalled": False}


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


def test_relay_takes_frames_only_with_the_key():
    from eye.uplink import Uplink

    relay_box = Outbox(WIDTH, HEIGHT)
    relay = start(relay_box, 0, host="127.0.0.1", key="secret", site=None)
    address = f"http://127.0.0.1:{relay.server_address[1]}"
    camera_box = Outbox(WIDTH, HEIGHT)
    camera_box.publish(np.full((HEIGHT, WIDTH, 3), 90, dtype=np.uint8), {"erased": 2})
    try:
        wrong = Uplink(camera_box, address, "guess")
        try:
            wrong.send_once()
            refused = False
        except OSError:
            refused = True
        assert refused and relay_box.latest()[1]["live"] is False
        assert Uplink(camera_box, address, "secret").send_once() is True
        state = json.loads(urllib.request.urlopen(address + "/state.json", timeout=3).read())
    finally:
        relay.shutdown()
    assert state["erased"] == 2 and state["live"] is True


def test_site_files_are_served_and_nothing_outside_the_folder(tmp_path):
    (tmp_path / "index.html").write_text("<p>hello</p>")
    (tmp_path / "notes.txt").write_text("private")
    server = start(Outbox(WIDTH, HEIGHT), 0, host="127.0.0.1", site=tmp_path)
    address = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(address + "/", timeout=3).read()
        blocked = []
        for path in ("/notes.txt", "/../eye/app.py", "/%2e%2e/.env"):
            try:
                urllib.request.urlopen(address + path, timeout=3)
                blocked.append(False)
            except OSError:
                blocked.append(True)
    finally:
        server.shutdown()
    assert page == b"<p>hello</p>" and all(blocked)


def test_stream_sends_each_new_frame():
    outbox = Outbox(WIDTH, HEIGHT)
    server = start(outbox, 0, host="127.0.0.1", site=None)
    address = f"http://127.0.0.1:{server.server_address[1]}/operator.mjpg"
    try:
        stream = urllib.request.urlopen(address, timeout=3)
        outbox.publish(np.full((HEIGHT, WIDTH, 3), 60, dtype=np.uint8), {})
        first = stream.read(400)
        outbox.publish(np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8), {})
        rest = stream.read(3000)
        stream.close()
    finally:
        server.shutdown()
    assert first.startswith(b"--frame") and b"image/jpeg" in first
    assert (first + rest).count(b"--frame") >= 2
