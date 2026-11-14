import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from eye.beacon import Policy
from eye.radio import Heard, Roster


class Recorder:
    def __init__(self, folder: Path):
        self.folder = folder
        (folder / "scene").mkdir(parents=True, exist_ok=True)
        (folder / "infrared").mkdir(parents=True, exist_ok=True)
        self._log = (folder / "frames.jsonl").open("w")
        self.count = 0

    def add(self, seconds: float, scene: np.ndarray, infrared: np.ndarray, heard: list[Heard]) -> None:
        name = f"{self.count:06d}"
        cv2.imwrite(str(self.folder / "scene" / f"{name}.jpg"), scene, [cv2.IMWRITE_JPEG_QUALITY, 92])
        cv2.imwrite(str(self.folder / "infrared" / f"{name}.png"), infrared)
        entry = {"seconds": seconds, "heard": [[h.sender, h.code, h.policy.value] for h in heard]}
        self._log.write(json.dumps(entry) + "\n")
        self.count += 1

    def close(self) -> None:
        self._log.close()


def replay(folder: Path):
    with (folder / "frames.jsonl").open() as log:
        for index, line in enumerate(log):
            entry = json.loads(line)
            name = f"{index:06d}"
            scene = cv2.imread(str(folder / "scene" / f"{name}.jpg"))
            infrared = cv2.imread(str(folder / "infrared" / f"{name}.png"), cv2.IMREAD_GRAYSCALE)
            heard = [Heard(sender, code, Policy(policy)) for sender, code, policy in entry["heard"]]
            yield entry["seconds"], scene, infrared, heard


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--pi", action="store_true")
    parser.add_argument("--scene", type=int, default=0)
    parser.add_argument("--infrared", type=int, default=None)
    args = parser.parse_args()

    from eye.listen import Listener
    from eye.sources import PiPair, WebcamPair

    source = PiPair() if args.pi else WebcamPair(args.scene, args.infrared)
    listener = Listener(Roster())
    listener.start()
    folder = Path(__file__).resolve().parents[1] / "recordings" / args.name
    recorder = Recorder(folder)
    began = time.monotonic()
    try:
        while time.monotonic() - began < args.seconds:
            seconds, scene, infrared = source.read()
            recorder.add(seconds, scene, infrared, listener.heard(seconds))
    finally:
        recorder.close()
        source.close()
        listener.stop()
    print(f"{recorder.count} frames saved to {folder}")


if __name__ == "__main__":
    main()
