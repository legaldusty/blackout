from collections import deque
from dataclasses import dataclass

import numpy as np

from eye.beacon import PERIOD_SECONDS, Policy, samples_per_period, template

SAMPLE_RATE = 30.0
MIN_SCORE = 0.72
MIN_AMPLITUDE = 12.0
MIN_MARGIN = 0.15
CONFIRM_PERIODS = 2
MAX_SHIFT_DRIFT = 1


@dataclass(frozen=True)
class Reading:
    cell: int
    policy: Policy
    score: float
    amplitude: float
    shift: int


def _unit_templates(sample_rate: float) -> dict[Policy, np.ndarray]:
    out = {}
    for policy in Policy:
        values = template(policy, sample_rate)
        centered = values - values.mean()
        out[policy] = centered / np.linalg.norm(centered)
    return out


def score_window(window: np.ndarray, sample_rate: float = SAMPLE_RATE):
    count = samples_per_period(sample_rate)
    if window.shape[0] != count:
        raise ValueError("window must cover exactly one code period")
    centered = window - window.mean(axis=0, keepdims=True)
    energy = np.linalg.norm(centered, axis=0)
    safe = np.where(energy > 1e-9, energy, 1.0)
    spectrum = np.fft.rfft(centered, axis=0)
    scores = {}
    shifts = {}
    for policy, unit in _unit_templates(sample_rate).items():
        reference = np.conj(np.fft.rfft(unit))[:, None]
        correlation = np.fft.irfft(spectrum * reference, n=count, axis=0)
        best = correlation.argmax(axis=0)
        peak = correlation.max(axis=0) / safe
        scores[policy] = np.where(energy > 1e-9, peak, 0.0)
        shifts[policy] = best
    return scores, shifts


def read_window(
    window: np.ndarray,
    sample_rate: float = SAMPLE_RATE,
    min_score: float = MIN_SCORE,
    min_amplitude: float = MIN_AMPLITUDE,
    min_margin: float = MIN_MARGIN,
) -> list[Reading]:
    scores, shifts = score_window(window, sample_rate)
    policies = list(scores)
    stacked = np.stack([scores[p] for p in policies])
    order = np.argsort(stacked, axis=0)
    winner = order[-1]
    cells = np.arange(window.shape[1])
    top = stacked[winner, cells]
    runner_up = stacked[order[-2], cells] if len(policies) > 1 else np.zeros_like(top)
    readings = []
    for cell in np.nonzero((top >= min_score) & (top - runner_up >= min_margin))[0]:
        policy = policies[int(winner[cell])]
        shift = int(shifts[policy][cell])
        pattern = np.roll(template(policy, sample_rate), shift) > 0.5
        column = window[:, cell]
        amplitude = float(column[pattern].mean() - column[~pattern].mean())
        if amplitude < min_amplitude:
            continue
        readings.append(Reading(int(cell), policy, float(top[cell]), amplitude, shift))
    return readings


class Reader:
    def __init__(self, sample_rate: float = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.count = samples_per_period(sample_rate)
        self._times: deque[float] = deque()
        self._values: deque[np.ndarray] = deque()

    def push(self, seconds: float, values: np.ndarray) -> None:
        self._times.append(float(seconds))
        self._values.append(np.asarray(values, dtype=np.float64))
        horizon = seconds - (CONFIRM_PERIODS + 0.3) * PERIOD_SECONDS
        while self._times and self._times[0] < horizon:
            self._times.popleft()
            self._values.popleft()

    def ready(self, periods: int = 1) -> bool:
        if len(self._times) < 2:
            return False
        return self._times[-1] - self._times[0] >= periods * PERIOD_SECONDS

    def window(self, periods_back: int = 0) -> np.ndarray:
        times = np.array(self._times)
        values = np.stack(self._values)
        end = times[-1] - periods_back * PERIOD_SECONDS
        grid = end - (self.count - 1 - np.arange(self.count)) / self.sample_rate
        right = np.clip(np.searchsorted(times, grid), 1, len(times) - 1)
        left = right - 1
        nearest = np.where(grid - times[left] <= times[right] - grid, left, right)
        return values[nearest]

    def read(self, **limits) -> list[Reading]:
        if not self.ready():
            return []
        return read_window(self.window(), self.sample_rate, **limits)

    def read_confirmed(self, **limits) -> list[Reading]:
        if not self.ready(CONFIRM_PERIODS):
            return []
        latest = {r.cell: r for r in read_window(self.window(0), self.sample_rate, **limits)}
        for back in range(1, CONFIRM_PERIODS):
            earlier = {r.cell: r for r in read_window(self.window(back), self.sample_rate, **limits)}
            kept = {}
            for cell, reading in latest.items():
                match = earlier.get(cell)
                if match is None or match.policy != reading.policy:
                    continue
                drift = (reading.shift - match.shift) % self.count
                if min(drift, self.count - drift) > MAX_SHIFT_DRIFT:
                    continue
                kept[cell] = reading
            latest = kept
        return list(latest.values())
