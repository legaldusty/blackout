import numpy as np

from eye.beacon import PERIOD_SECONDS, Policy, chip_at
from eye.reader import Reader


def led_series(policy, start, seconds, fps=30.0, exposure=1 / 120, on=120.0, off=40.0, jitter=0.0, rng=None):
    rng = rng or np.random.default_rng(0)
    count = int(round(seconds * fps))
    times = start + np.arange(count) / fps + rng.normal(0.0, jitter, count)
    values = np.empty(count)
    for index, moment in enumerate(times):
        slices = np.linspace(moment, moment + exposure, 8)
        duty = np.mean([chip_at(policy, s) for s in slices])
        values[index] = off + (on - off) * duty
    return np.sort(times), values


def feed(columns, times):
    reader = Reader()
    stacked = np.stack(columns, axis=1)
    for moment, row in zip(times, stacked):
        reader.push(moment, row)
    return reader


def seconds_of(periods):
    return periods * PERIOD_SECONDS + 0.2


ALL = list(Policy)
