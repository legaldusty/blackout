from dataclasses import dataclass

import cv2
import numpy as np

from eye.reader import SAMPLE_RATE, Reader


@dataclass
class Spot:
    x: float
    y: float
    seen: float
    reader: Reader
    vx: float = 0.0
    vy: float = 0.0


@dataclass(frozen=True)
class Sighted:
    x: float
    y: float
    code: int
    score: float


class Spots:
    def __init__(
        self,
        level: int = 140,
        reach: float = 10.0,
        drift: float = 80.0,
        forget: float = 1.0,
        limit: int = 48,
        top_speed: float = 600.0,
        sample_rate: float = SAMPLE_RATE,
    ):
        self.level = level
        self.reach = reach
        self.drift = drift
        self.forget = forget
        self.limit = limit
        self.top_speed = top_speed
        self.sample_rate = sample_rate
        self._spots: list[Spot] = []

    def __len__(self) -> int:
        return len(self._spots)

    def update(self, seconds: float, gray: np.ndarray) -> None:
        height, width = gray.shape[:2]
        _, binary = cv2.threshold(gray, self.level, 255, cv2.THRESH_BINARY)
        count, _, stats, centers = cv2.connectedComponentsWithStats(binary, connectivity=8)
        blobs = [(float(centers[i][0]), float(centers[i][1]), int(stats[i, cv2.CC_STAT_AREA])) for i in range(1, count)]
        free = set(range(len(blobs)))
        for spot in self._spots:
            gap = seconds - spot.seen
            guess_x = spot.x + spot.vx * gap
            guess_y = spot.y + spot.vy * gap
            radius = self.reach + self.drift * gap
            nearest = None
            nearest_distance = radius
            for index in free:
                distance = float(np.hypot(blobs[index][0] - guess_x, blobs[index][1] - guess_y))
                if distance <= nearest_distance:
                    nearest = index
                    nearest_distance = distance
            if nearest is not None:
                free.discard(nearest)
                blob_x, blob_y, _ = blobs[nearest]
                if gap > 0:
                    speed_x = float(np.clip((blob_x - spot.x) / gap, -self.top_speed, self.top_speed))
                    speed_y = float(np.clip((blob_y - spot.y) / gap, -self.top_speed, self.top_speed))
                    spot.vx = 0.8 * spot.vx + 0.2 * speed_x
                    spot.vy = 0.8 * spot.vy + 0.2 * speed_y
                spot.x, spot.y, spot.seen = blob_x, blob_y, seconds
                guess_x, guess_y = blob_x, blob_y
            spot.reader.push(seconds, np.array([self._peak(gray, guess_x, guess_y, width, height)]))
        self._spots = [spot for spot in self._spots if seconds - spot.seen <= self.forget]
        for index in sorted(free, key=lambda i: blobs[i][2]):
            if len(self._spots) >= self.limit:
                break
            blob_x, blob_y, _ = blobs[index]
            spot = Spot(blob_x, blob_y, seconds, Reader(self.sample_rate))
            spot.reader.push(seconds, np.array([self._peak(gray, blob_x, blob_y, width, height)]))
            self._spots.append(spot)

    def _peak(self, gray: np.ndarray, x: float, y: float, width: int, height: int) -> float:
        half = int(self.reach)
        left = min(max(int(x) - half, 0), width - 1)
        top = min(max(int(y) - half, 0), height - 1)
        patch = gray[top : min(top + 2 * half + 1, height), left : min(left + 2 * half + 1, width)]
        return float(patch.max()) if patch.size else 0.0

    def read(self, codes) -> list[Sighted]:
        allowed = set(codes)
        if not allowed:
            return []
        found = []
        for spot in self._spots:
            for reading in spot.reader.read_confirmed(allowed):
                found.append(Sighted(spot.x, spot.y, reading.code, reading.score))
        return sorted(found, key=lambda sighted: -sighted.score)
