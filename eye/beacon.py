from enum import Enum

import numpy as np

CHIP_RATE = 15.0
CODE_LENGTH = 15
PERIOD_SECONDS = CODE_LENGTH / CHIP_RATE


class Policy(Enum):
    HIDE_ALL = "hide_all"
    HIDE_FACE = "hide_face"


def _shift_register_sequence(taps: tuple[int, ...]) -> tuple[int, ...]:
    state = [1, 0, 0, 0]
    out = []
    for _ in range(CODE_LENGTH):
        out.append(state[-1])
        feedback = 0
        for tap in taps:
            feedback ^= state[tap]
        state = [feedback] + state[:-1]
    return tuple(out)


_BASE = _shift_register_sequence((0, 3))

CHIPS: dict[Policy, tuple[int, ...]] = {
    Policy.HIDE_ALL: _BASE,
    Policy.HIDE_FACE: tuple(reversed(_BASE)),
}


def chip_at(policy: Policy, seconds: float) -> int:
    index = int(np.floor(seconds * CHIP_RATE)) % CODE_LENGTH
    return CHIPS[policy][index]


def samples_per_period(sample_rate: float) -> int:
    return int(round(PERIOD_SECONDS * sample_rate))


def template(policy: Policy, sample_rate: float) -> np.ndarray:
    count = samples_per_period(sample_rate)
    centers = (np.arange(count) + 0.5) / sample_rate
    values = np.array([chip_at(policy, t) for t in centers], dtype=np.float64)
    return values
