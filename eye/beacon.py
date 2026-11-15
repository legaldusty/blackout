from enum import Enum

import numpy as np

CHIP_RATE = 15.0
CODE_LENGTH = 15
PERIOD_SECONDS = CODE_LENGTH / CHIP_RATE

CODES: tuple[tuple[int, ...], ...] = (
    (0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1),
    (0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 1),
    (0, 0, 0, 0, 1, 1, 1, 0, 1, 1, 0, 0, 1, 0, 1),
    (0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1),
    (0, 0, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 1, 0, 1),
    (0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1, 1, 1),
    (0, 0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1),
    (0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 0, 0, 1, 1),
)
CODE_COUNT = len(CODES)


class Policy(Enum):
    HIDE_ALL = 1
    HIDE_FACE = 2
    ROOM = 3


def chip_at(code: int, seconds: float) -> int:
    index = int(np.floor(seconds * CHIP_RATE)) % CODE_LENGTH
    return CODES[code][index]


def samples_per_period(sample_rate: float) -> int:
    return int(round(PERIOD_SECONDS * sample_rate))


def template(code: int, sample_rate: float) -> np.ndarray:
    count = samples_per_period(sample_rate)
    centers = (np.arange(count) + 0.5) / sample_rate
    return np.array([chip_at(code, t) for t in centers], dtype=np.float64)
