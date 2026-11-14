import numpy as np
import pytest

from eye.beacon import CODE_LENGTH, CODES
from eye.reader import Reader, read_window, score_window
from tests.synthetic import ALL, feed, led_series, seconds_of


def test_codes_are_balanced_with_short_runs():
    for chips in CODES:
        assert len(chips) == CODE_LENGTH
        assert sum(chips) in (7, 8)
        doubled = chips + chips
        longest = max(len(run) for run in "".join(map(str, doubled)).replace("01", "0 1").replace("10", "1 0").split())
        assert longest <= 4


def test_codes_do_not_look_like_shifted_copies_of_themselves():
    for chips in CODES:
        signed = np.array(chips) * 2 - 1
        side = max(abs(int(np.dot(signed, np.roll(signed, s)))) for s in range(1, CODE_LENGTH))
        assert side <= 5


def test_codes_do_not_look_like_each_other():
    for a in range(len(CODES)):
        for b in range(a + 1, len(CODES)):
            x = np.array(CODES[a]) * 2 - 1
            y = np.array(CODES[b]) * 2 - 1
            assert max(int(np.dot(x, np.roll(y, s))) for s in range(CODE_LENGTH)) <= 7


@pytest.mark.parametrize("code", ALL)
def test_reads_a_clean_tag_at_any_phase(code):
    rng = np.random.default_rng(11)
    for _ in range(200):
        times, values = led_series(code, rng.uniform(0, 9), seconds_of(2), jitter=0.003, rng=rng)
        values = values + rng.normal(0, 3, len(values))
        readings = feed([values], times).read_confirmed()
        assert [r.code for r in readings] == [code]


@pytest.mark.parametrize("fps", [30.0, 60.0])
def test_reads_at_common_frame_rates(fps):
    rng = np.random.default_rng(5)
    misses = 0
    for trial in range(200):
        code = ALL[trial % len(ALL)]
        times, values = led_series(code, rng.uniform(0, 9), seconds_of(2), fps=fps, jitter=0.002, rng=rng)
        readings = feed([values + rng.normal(0, 3, len(values))], times).read_confirmed()
        misses += [r.code for r in readings] != [code]
    assert misses == 0


def test_dropped_frames_do_not_break_the_read():
    rng = np.random.default_rng(8)
    misses = 0
    for trial in range(200):
        code = ALL[trial % len(ALL)]
        times, values = led_series(code, rng.uniform(0, 9), seconds_of(2), rng=rng)
        keep = rng.random(len(times)) > 0.1
        readings = feed([values[keep]], times[keep]).read_confirmed()
        misses += [r.code for r in readings] != [code]
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
            worst = max(worst, float(scores[:, 0].max()))
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
    times, tag = led_series(2, 2.37, seconds_of(2), rng=rng)
    flicker = 100 + 30 * np.sin(2 * np.pi * 1.7 * times)
    columns = [flicker + rng.normal(0, 3, len(times)) for _ in range(50)]
    columns[17] = tag + 0.3 * (flicker - 100) + rng.normal(0, 3, len(times))
    readings = feed(columns, times).read_confirmed()
    assert [(r.cell, r.code) for r in readings] == [(17, 2)]


def test_dim_tag_below_amplitude_gate_is_ignored():
    rng = np.random.default_rng(6)
    times, values = led_series(2, 1.0, seconds_of(2), on=44.0, off=40.0, rng=rng)
    assert feed([values + rng.normal(0, 3, len(values))], times).read_confirmed() == []


def test_needs_two_full_periods_before_confirming():
    times, values = led_series(2, 0.0, 1.5)
    assert feed([values], times).read_confirmed() == []


def test_a_code_nobody_announced_is_ignored():
    times, values = led_series(5, 0.4, seconds_of(2))
    reader = feed([values], times)
    assert reader.read_confirmed(codes=[1, 2]) == []
    assert [r.code for r in reader.read_confirmed(codes=[5])] == [5]
