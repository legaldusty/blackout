import argparse
import time

import cv2
import numpy as np

from eye.reader import Reader
from eye.sampling import brightest_per_cell

ROWS = 18
COLS = 32


def annotate(view: np.ndarray, readings, rows: int, cols: int) -> None:
    height, width = view.shape[:2]
    for reading in readings:
        row, col = divmod(reading.cell, cols)
        left = int(col * width / cols)
        top = int(row * height / rows)
        right = int((col + 1) * width / cols)
        bottom = int((row + 1) * height / rows)
        cv2.rectangle(view, (left, top), (right, bottom), (255, 255, 255), 2)
        label = f"code {reading.code}  {reading.score:.2f}  {reading.amplitude:.0f}"
        cv2.putText(view, label, (left, max(18, top - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pi", action="store_true")
    parser.add_argument("--scene", type=int, default=0)
    parser.add_argument("--infrared", type=int, default=None)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    from eye.sources import PiPair, WebcamPair

    source = PiPair() if args.pi else WebcamPair(args.scene, args.infrared)
    reader = Reader()
    last_report = time.monotonic()
    frames = 0
    try:
        while True:
            seconds, _, infrared = source.read()
            box = (0, 0, infrared.shape[1], infrared.shape[0])
            reader.push(seconds, brightest_per_cell(infrared, box, ROWS, COLS))
            readings = reader.read_confirmed()
            frames += 1
            if seconds - last_report >= 1.0:
                found = ", ".join(f"code {r.code} score {r.score:.2f} strength {r.amplitude:.0f}" for r in readings) or "no tag"
                print(f"{frames} frames per second, brightest {int(infrared.max())}, {found}")
                frames = 0
                last_report = seconds
            if not args.headless:
                view = cv2.cvtColor(infrared, cv2.COLOR_GRAY2BGR)
                annotate(view, readings, ROWS, COLS)
                cv2.imshow("tag reader bench", view)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
    finally:
        source.close()


if __name__ == "__main__":
    main()
