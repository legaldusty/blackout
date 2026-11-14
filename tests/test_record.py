from eye.pipeline import Pipeline
from eye.record import Recorder, replay
from tests.scene import FPS, Actor, Scene


def test_a_recording_replays_to_the_same_result(tmp_path):
    tagged = Actor("tag", 60, speed=10, code=4)
    other = Actor("other", 230)
    scene = Scene([tagged, other])
    recorder = Recorder(tmp_path / "clip")
    live = Pipeline(detector=scene)
    live_out = []
    for index in range(210):
        seconds = index / FPS
        image, infrared = scene.frames(seconds)
        heard = scene.heard(seconds)
        recorder.add(seconds, image, infrared, heard)
        live_out.extend(live.push(seconds, image, infrared, heard))
    recorder.close()

    again = Scene([tagged, other])
    replayed = Pipeline(detector=again)
    replay_out = []
    for seconds, image, infrared, heard in replay(tmp_path / "clip"):
        again.now = seconds
        replay_out.extend(replayed.push(seconds, image, infrared, heard))

    assert len(replay_out) == len(live_out) > 100
    assert [r.erased for r in replay_out] == [r.erased for r in live_out]
    assert max(again.visible_fraction(tagged, r) for r in replay_out) < 0.02
