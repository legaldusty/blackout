from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

import numpy as np

from eye.beacon import CODE_COUNT, PERIOD_SECONDS, samples_per_period, template

SAMPLE_RATE = 30.0
MIN_SCORE = 0.72
MIN_AMPLITUDE = 12.0
MIN_MARGIN = 0.15
CONFIRM_PERIODS = 2
MAX_SHIFT_DRIFT = 1


@dataclass(frozen=True)
class Reading:
    cell: int
    code: int
    score: float
    amplitude: float
    shift: int


@lru_cache(maxsize=4)
def _reference_spectra(sample_rate: float) -> np.ndarray:
    rows = []
    for code in range(CODE_COUNT):
        values = template(code, sample_rate)
        centered = values - values.mean()
        rows.append(np.conj(np.fft.rfft(centered / np.linalg.norm(centered))))
    return np.stack(rows)


def score_window(window: np.ndarray, sample_rate: float = SAMPLE_RATE):
    count = samples_per_period(sample_rate)
    if window.shape[0] != count:
        raise ValueError("window must cover exactly one code period")
    centered = window - window.mean(axis=0, keepdims=True)
    energy = np.linalg.norm(centered, axis=0)
    alive = energy > 1e-9
    safe = np.where(alive, energy, 1.0)
    spectrum = np.fft.rfft(centered, axis=0)
    references = _reference_spectra(sample_rate)
    product = spectrum[None, :, :] * references[:, :, None]
    correlation = np.fft.irfft(product, n=count, axis=1)
    shifts = correlation.argmax(axis=1)
    scores = np.where(alive[None, :], correlation.max(axis=1) / safe[None, :], 0.0)
    return scores, shifts


def read_window(
    window: np.ndarray,
    codes: Iterable[int] | None = None,
    sample_rate: float = SAMPLE_RATE,
    min_score: float = MIN_SCORE,
    min_amplitude: float = MIN_AMPLITUDE,
    min_margin: float = MIN_MARGIN,
) -> list[Reading]:
    allowed = set(range(CODE_COUNT)) if codes is None else set(codes)
    if not allowed:
        return []
    scores, shifts = score_window(window, sample_rate)
    order = np.argsort(scores, axis=0)
    winner = order[-1]
    cells = np.arange(window.shape[1])
    top = scores[winner, cells]
    runner_up = scores[order[-2], cells]
    readings = []
    for cell in np.nonzero((top >= min_score) & (top - runner_up >= min_margin))[0]:
        code = int(winner[cell])
        if code not in allowed:
            continue
        shift = int(shifts[code, cell])
        pattern = np.roll(template(code, sample_rate), shift) > 0.5
        column = window[:, cell]
        amplitude = float(column[pattern].mean() - column[~pattern].mean())
        if amplitude < min_amplitude:
            continue
        readings.append(Reading(int(cell), code, float(top[cell]), amplitude, shift))
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

    def span(self) -> float:
        if len(self._times) < 2:
            return 0.0
        return self._times[-1] - self._times[0]

    def ready(self, periods: int = 1) -> bool:
        return self.span() >= periods * PERIOD_SECONDS

    def window(self, periods_back: int = 0) -> np.ndarray:
        times = np.array(self._times)
        values = np.stack(self._values)
        end = times[-1] - periods_back * PERIOD_SECONDS
        grid = end - (self.count - 1 - np.arange(self.count)) / self.sample_rate
        right = np.clip(np.searchsorted(times, grid), 1, len(times) - 1)
        left = right - 1
        nearest = np.where(grid - times[left] <= times[right] - grid, left, right)
        return values[nearest]

    def read(self, codes: Iterable[int] | None = None, **limits) -> list[Reading]:
        if not self.ready():
            return []
        return read_window(self.window(), codes, self.sample_rate, **limits)

    def read_confirmed(self, codes: Iterable[int] | None = None, **limits) -> list[Reading]:
        if not self.ready(CONFIRM_PERIODS):
            return []
        allowed = None if codes is None else set(codes)
        latest = {r.cell: r for r in read_window(self.window(0), allowed, self.sample_rate, **limits)}
        for back in range(1, CONFIRM_PERIODS):
            earlier = {r.cell: r for r in read_window(self.window(back), allowed, self.sample_rate, **limits)}
            kept = {}
            for cell, reading in latest.items():
                match = earlier.get(cell)
                if match is None or match.code != reading.code:
                    continue
                drift = (reading.shift - match.shift) % self.count
                if min(drift, self.count - drift) > MAX_SHIFT_DRIFT:
                    continue
                kept[cell] = reading
            latest = kept
        return list(latest.values())
