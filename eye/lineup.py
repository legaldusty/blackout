import argparse
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from eye.beacon import CODE_COUNT
from eye.sources import find_webcam
from eye.spots import Spots

HOME = Path(__file__).resolve().parents[1]


class WebcamSpots:
    def __init__(self, exposure: int, level: int):
        self.capture = cv2.VideoCapture(find_webcam(), cv2.CAP_V4L2)
        self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.capture.set(cv2.CAP_PROP_FPS, 30)
        self.capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
        self.capture.set(cv2.CAP_PROP_EXPOSURE, exposure)
        self.spots = Spots(level=level)
        self.lock = threading.Lock()
        self.frames = 0
        self.last = None
        self.alive = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while self.alive:
            ok, frame = self.capture.read()
            if not ok:
                continue
            gray = frame.max(axis=2)
            with self.lock:
                self.spots.update(time.monotonic(), gray)
                self.frames += 1
                self.last = frame

    def read(self):
        with self.lock:
            return self.spots.read(range(CODE_COUNT))

    def close(self) -> None:
        self.alive = False
        time.sleep(0.2)
        self.capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)
        self.capture.release()


def solve(source: np.ndarray, target: np.ndarray, full: bool) -> np.ndarray:
    ones = np.ones(len(source))
    if full:
        design = np.column_stack([source, ones])
        found = np.linalg.lstsq(design, target, rcond=None)[0]
        return np.vstack([found.T, [0.0, 0.0, 1.0]])
    x, y = source[:, 0], source[:, 1]
    zeros = np.zeros(len(source))
    design = np.vstack([np.column_stack([x, -y, ones, zeros]), np.column_stack([y, x, zeros, ones])])
    a, b, tx, ty = np.linalg.lstsq(design, np.concatenate([target[:, 0], target[:, 1]]), rcond=None)[0]
    return np.array([[a, -b, tx], [b, a, ty], [0.0, 0.0, 1.0]])


def fit(data: np.ndarray):
    source, target = data[:, :2], data[:, 2:]
    spread = source.max(axis=0) - source.min(axis=0)
    full = len(data) >= 14 and spread[0] > 300 and spread[1] > 200
    kept = np.ones(len(data), dtype=bool)
    for _ in range(6):
        matrix = solve(source[kept], target[kept], full)
        moved = source @ matrix[:2, :2].T + matrix[:2, 2]
        errors = np.hypot(*(moved - target).T)
        fresh = errors <= max(2.0 * float(np.median(errors[kept])), 12.0)
        if fresh.sum() < 6 or (fresh == kept).all():
            break
        kept = fresh
    return matrix, kept, errors, full


def report(data: np.ndarray, out: str) -> None:
    matrix, kept, errors, full = fit(data)
    source = data[:, :2]
    kind = "wide" if full else "narrow"
    print(f"{kind} fit from {int(kept.sum())} of {len(data)} pairs, typical miss {np.median(errors[kept]):.1f} px, worst kept {errors[kept].max():.1f} px")
    print(f"tag picture covered x {source[:, 0].min():.0f} to {source[:, 0].max():.0f}, y {source[:, 1].min():.0f} to {source[:, 1].max():.0f}")
    np.save(out, matrix)
    print("saved", out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", default="")
    parser.add_argument("--seconds", type=float, default=45.0)
    parser.add_argument("--exposure", type=int, default=60)
    parser.add_argument("--web-level", type=int, default=150)
    parser.add_argument("--tag-level", type=int, default=120)
    parser.add_argument("--upside-down", action="store_true")
    parser.add_argument("--out", default=str(HOME / "align.npy"))
    args = parser.parse_args()
    if args.pairs:
        report(np.load(args.pairs), args.out)
        return

    from picamera2 import Picamera2

    web = WebcamSpots(args.exposure, args.web_level)
    tag = Picamera2(0)
    tag.configure(
        tag.create_video_configuration(
            main={"size": (1280, 720), "format": "YUV420"},
            controls={"FrameDurationLimits": (33333, 33333), "AeEnable": False, "ExposureTime": 4000, "AnalogueGain": 4.0},
        )
    )
    tag.start()
    tag_spots = Spots(level=args.tag_level)
    pairs: list[tuple[float, float, float, float]] = []
    seen = {"tag": 0, "web": 0}
    began = time.monotonic()
    next_check = began + 2.5
    frames = 0
    last_gray = None
    while time.monotonic() - began < args.seconds:
        gray = tag.capture_array("main")[:720]
        if args.upside_down:
            gray = gray[::-1, ::-1]
        now = time.monotonic()
        tag_spots.update(now, np.ascontiguousarray(gray))
        last_gray = gray
        frames += 1
        if now < next_check:
            continue
        next_check = now + 0.2
        from_tag = tag_spots.read(range(CODE_COUNT))
        from_web = web.read()
        seen["tag"] += bool(from_tag)
        seen["web"] += bool(from_web)
        if not from_tag or not from_web:
            continue
        a = from_tag[0]
        matches = [b for b in from_web if b.code == a.code]
        if not matches:
            continue
        b = matches[0]
        if pairs and np.hypot(a.x - pairs[-1][0], a.y - pairs[-1][1]) < 12:
            continue
        pairs.append((a.x, a.y, b.x, b.y))
    tag.stop()
    elapsed = time.monotonic() - began
    print(f"tag camera {frames / elapsed:.1f} frames a second, webcam {web.frames / elapsed:.1f}")
    print(f"checks that saw the tag: tag camera {seen['tag']}, webcam {seen['web']}, pairs {len(pairs)}")
    scratch = Path.home() / "scratch"
    if web.last is not None:
        cv2.imwrite(str(scratch / "lineup_web.jpg"), cv2.resize(web.last, (640, 360)))
    if last_gray is not None:
        cv2.imwrite(str(scratch / "lineup_tag.jpg"), cv2.resize(np.ascontiguousarray(last_gray), (640, 360)))
    web.close()
    if len(pairs) < 6:
        print("not enough pairs to line up the cameras")
        return
    data = np.array(pairs, dtype=np.float64)
    np.save(str(scratch / "lineup_pairs.npy"), data)
    report(data, args.out)

if __name__ == "__main__":
    main()
