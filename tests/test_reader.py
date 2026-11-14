import numpy as np
import pytest

from eye.beacon import CHIPS, CODE_LENGTH, Policy
from eye.reader import Reader, read_window, score_window
from tests.synthetic import ALL, feed, led_series, seconds_of


def test_codes_are_balanced_and_sharp():
    for policy in ALL:
        chips = np.array(CHIPS[policy]) * 2 - 1
        assert len(chips) == CODE_LENGTH
        side = [int(np.dot(chips, np.roll(chips, s))) for s in range(1, CODE_LENGTH)]
        assert set(side) == {-1}


def test_codes_do_not_look_like_each_other():
    a = np.array(CHIPS[Policy.HIDE_ALL]) * 2 - 1
    b = np.array(CHIPS[Policy.HIDE_FACE]) * 2 - 1
    cross = max(int(np.dot(a, np.roll(b, s))) for s in range(CODE_LENGTH))
    assert cross <= 7


@pytest.mark.parametrize("policy", ALL)
def test_reads_a_clean_tag_at_any_phase(policy):
    rng = np.random.default_rng(11)
    for _ in range(200):
        times, values = led_series(policy, rng.uniform(0, 9), seconds_of(2), jitter=0.003, rng=rng)
        values = values + rng.normal(0, 3, len(values))
        readings = feed([values], times).read_confirmed()
        assert [r.policy for r in readings] == [policy]


@pytest.mark.parametrize("fps", [30.0, 60.0])
def test_reads_at_common_frame_rates(fps):
    rng = np.random.default_rng(5)
    misses = 0
    for trial in range(200):
        policy = ALL[trial % 2]
        times, values = led_series(policy, rng.uniform(0, 9), seconds_of(2), fps=fps, jitter=0.002, rng=rng)
        readings = feed([values + rng.normal(0, 3, len(values))], times).read_confirmed()
        misses += [r.policy for r in readings] != [policy]
    assert misses == 0


def test_dropped_frames_do_not_break_the_read():
    rng = np.random.default_rng(8)
    misses = 0
    for trial in range(200):
        policy = ALL[trial % 2]
        times, values = led_series(policy, rng.uniform(0, 9), seconds_of(2), rng=rng)
        keep = rng.random(len(times)) > 0.1
        readings = feed([values[keep]], times[keep]).read_confirmed()
        misses += [r.policy for r in readings] != [policy]
    assert misses <= 4


def test_sensor_noise_never_reads_as_a_tag():
    rng = np.random.default_rng(2)
    window = rng.normal(100, 3, (30, 100_000))
    assert read_window(window) == []


def test_mains_flicker_never_reads_as_a_tag():
    seconds = np.arange(30) / 30.0
    worst = 0.0
    for beat in np.linspace(0.2, 15, 300):
        for phase in np.linspace(0, 2 * np.pi, 16):
            window = (100 + 50 * np.sin(2 * np.pi * beat * seconds + phase))[:, None]
            scores, _ = score_window(window)
            worst = max(worst, max(float(scores[p][0]) for p in ALL))
    assert worst < 0.72


def test_a_light_switched_once_never_reads_as_a_tag():
    for start in range(30):
        for length in range(1, 30):
            window = np.zeros((30, 1))
            window[(np.arange(length) + start) % 30, 0] = 100.0
            assert read_window(window) == []


def test_random_flashing_is_rejected_by_confirmation():
    rng = np.random.default_rng(3)
    cells = 20_000
    frames = 70
    flips = rng.random((frames, cells)) < 0.2
    values = (np.cumsum(flips, axis=0) % 2) * 100.0
    reader = Reader()
    for index in range(frames):
        reader.push(index / 30.0, values[index])
    assert len(reader.read_confirmed()) <= 2


def test_tag_among_flicker_and_noise_is_found_in_the_right_cell():
    rng = np.random.default_rng(4)
    times, tag = led_series(Policy.HIDE_ALL, 2.37, seconds_of(2), rng=rng)
    flicker = 100 + 30 * np.sin(2 * np.pi * 1.7 * times)
    columns = [flicker + rng.normal(0, 3, len(times)) for _ in range(50)]
    columns[17] = tag + 0.3 * (flicker - 100) + rng.normal(0, 3, len(times))
    readings = feed(columns, times).read_confirmed()
    assert [(r.cell, r.policy) for r in readings] == [(17, Policy.HIDE_ALL)]


def test_dim_tag_below_amplitude_gate_is_ignored():
    rng = np.random.default_rng(6)
    times, values = led_series(Policy.HIDE_ALL, 1.0, seconds_of(2), on=44.0, off=40.0, rng=rng)
    assert feed([values + rng.normal(0, 3, len(values))], times).read_confirmed() == []


def test_needs_two_full_periods_before_confirming():
    times, values = led_series(Policy.HIDE_ALL, 0.0, 1.5)
    assert feed([values], times).read_confirmed() == []
