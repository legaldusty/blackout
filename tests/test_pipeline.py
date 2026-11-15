import numpy as np

from eye.beacon import Policy
from eye.pipeline import Pipeline, Settings
from tests.scene import Actor, Scene, run


def build(scene):
    return Pipeline(detector=scene)


def test_output_runs_behind_by_the_delay():
    scene = Scene([Actor("a", 100)])
    pipeline = build(scene)
    released = run(scene, pipeline, 4.0)
    assert released[0].seconds == 0.0
    assert abs(released[-1].seconds - (4.0 - 1 / 30 - pipeline.settings.delay_seconds)) < 0.04


def test_nobody_is_erased_when_no_tag_is_around():
    scene = Scene([Actor("a", 60), Actor("b", 200)])
    released = run(scene, build(scene), 5.0)
    assert all(r.erased == 0 for r in released)
    assert min(scene.visible_fraction(scene.actors[0], r) for r in released) == 1.0


def test_tagged_person_never_appears_and_the_other_always_does():
    tagged = Actor("tag", 20, speed=18, code=2)
    other = Actor("other", 240, speed=-6)
    scene = Scene([tagged, other], flicker=True)
    released = run(scene, build(scene), 9.0)
    assert len(released) > 150
    assert max(scene.visible_fraction(tagged, r) for r in released) == 0.0
    assert min(scene.visible_fraction(other, r) for r in released) == 1.0


def test_two_tags_with_different_codes_are_both_erased():
    first = Actor("one", 20, code=0)
    second = Actor("two", 140, code=5)
    third = Actor("three", 250)
    scene = Scene([first, second, third])
    released = run(scene, build(scene), 8.0)
    assert max(scene.visible_fraction(first, r) for r in released) == 0.0
    assert max(scene.visible_fraction(second, r) for r in released) == 0.0
    assert min(scene.visible_fraction(third, r) for r in released) == 1.0


def test_heard_but_not_seen_erases_everyone():
    covered = Actor("covered", 40, code=3, light_until=0.0)
    other = Actor("other", 220)
    scene = Scene([covered, other])
    released = run(scene, build(scene), 7.0)
    assert all(r.holding for r in released)
    assert max(scene.visible_fraction(covered, r) for r in released) == 0.0
    assert max(scene.visible_fraction(other, r) for r in released) == 0.0


def test_others_come_back_once_the_light_is_found():
    late = Actor("late", 40, code=3, light_from=3.0)
    other = Actor("other", 220)
    scene = Scene([late, other])
    released = run(scene, build(scene), 12.0)
    assert max(scene.visible_fraction(late, r) for r in released) == 0.0
    early = [r for r in released if r.seconds < 2.0]
    settled = [r for r in released if r.seconds > 6.5]
    assert max(scene.visible_fraction(other, r) for r in early) == 0.0
    assert min(scene.visible_fraction(other, r) for r in settled) == 1.0


def test_a_blinking_light_nobody_announced_changes_nothing():
    rogue = Actor("rogue", 60, code=4, radio_until=0.0)
    scene = Scene([rogue])
    released = run(scene, build(scene), 6.0)
    assert all(r.erased == 0 for r in released)


def test_switching_the_tag_off_brings_the_person_back_only_for_later_frames():
    person = Actor("p", 120, code=1, light_until=6.0, radio_until=6.0)
    scene = Scene([person])
    released = run(scene, build(scene), 12.0)
    before = [r for r in released if r.seconds < 6.0]
    after = [r for r in released if r.seconds > 6.2]
    assert max(scene.visible_fraction(person, r) for r in before) == 0.0
    assert min(scene.visible_fraction(person, r) for r in after) == 1.0


def test_radio_lost_before_any_match_keeps_those_frames_dark():
    covered = Actor("covered", 40, code=3, light_until=0.0, radio_until=3.0)
    other = Actor("other", 220)
    scene = Scene([covered, other])
    released = run(scene, build(scene), 9.0)
    during = [r for r in released if r.seconds < 3.0]
    later = [r for r in released if r.seconds > 3.1]
    assert max(scene.visible_fraction(other, r) for r in during) == 0.0
    assert min(scene.visible_fraction(other, r) for r in later) == 1.0


def test_face_only_wish_hides_the_face_and_keeps_the_body():
    person = Actor("p", 120, code=6, policy=Policy.HIDE_FACE)
    scene = Scene([person])
    released = run(scene, build(scene), 8.0)
    assert max(scene.visible_fraction(person, r, rows=(0, 25)) for r in released) < 0.45
    assert min(scene.visible_fraction(person, r, rows=(70, 120)) for r in released) == 1.0


def test_detector_failure_turns_the_output_black():
    person = Actor("p", 120)
    scene = Scene([person], detector_fails_at=3.0)
    pipeline = build(scene)
    released = run(scene, pipeline, 8.0)
    assert pipeline.tripped is not None
    late = [r for r in released if r.seconds > 0.6]
    early = [r for r in released if r.seconds < 0.4]
    assert late and all(r.tripped and not r.image.any() for r in late)
    assert early and all(not r.tripped for r in early)


def test_losing_track_of_a_tagged_person_puts_everyone_on_hold():
    tagged = Actor("tag", 40, code=2, hidden_from_detector=(5.0, 8.0))
    other = Actor("other", 220)
    scene = Scene([tagged, other])
    released = run(scene, build(scene), 11.0)
    gap = [r for r in released if 6.0 < r.seconds < 8.0]
    assert gap and all(r.holding for r in gap)
    assert max(scene.visible_fraction(other, r) for r in gap) == 0.0
    visible_frames = [r for r in released if r.seconds < 4.9]
    assert max(scene.visible_fraction(tagged, r) for r in visible_frames) == 0.0


def test_frames_are_never_altered_in_place():
    scene = Scene([Actor("p", 120, code=1)])
    pipeline = build(scene)
    image, infrared = scene.frames(0.0)
    keep = image.copy()
    pipeline.push(0.0, image, infrared, scene.heard(0.0))
    assert np.array_equal(image, keep)


def test_room_tag_hides_everyone_without_any_light():
    from eye.radio import Heard

    first = Actor("one", 60)
    second = Actor("two", 220)
    scene = Scene([first, second])
    pipeline = build(scene)
    released = []
    for index in range(300):
        moment = index / 30.0
        image, infrared = scene.frames(moment)
        heard = [Heard("room", 0, Policy.ROOM)] if 2.0 <= moment < 6.0 else []
        released.extend(pipeline.push(moment, image, infrared, heard))
    before = [r for r in released if r.seconds < 1.9]
    during = [r for r in released if 2.1 < r.seconds < 5.9]
    after = [r for r in released if r.seconds > 6.2]
    assert min(scene.visible_fraction(first, r) for r in before) == 1.0
    assert during and all(r.room and r.erased == 2 for r in during)
    assert max(scene.visible_fraction(second, r) for r in during) == 0.0
    assert after and min(scene.visible_fraction(first, r) for r in after) == 1.0
    assert not any(r.room for r in after)
