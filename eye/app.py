import argparse
import time

import cv2
import numpy as np

from eye.pipeline import Pipeline, Released, Settings
from eye.radio import Roster
from eye.serve import Outbox, start


def state_of(released: Released, rate: float) -> dict:
    return {
        "seconds": round(released.seconds, 3),
        "erased": released.erased,
        "holding": released.holding,
        "asking": released.asking,
        "tripped": released.tripped,
        "rate": round(rate, 1),
    }


def run(source, radio, pipeline: Pipeline, outbox: Outbox, show: bool = False, frames: int | None = None) -> None:
    done = 0
    last = time.monotonic()
    rate = 0.0
    while frames is None or done < frames:
        seconds, scene, infrared = source.read()
        for released in pipeline.push(seconds, scene, infrared, radio.heard(seconds)):
            outbox.publish(released.image, state_of(released, rate))
            if show:
                cv2.imshow("what leaves the camera", released.image)
        if show:
            cv2.imshow("sensor, never leaves", scene)
            if cv2.waitKey(1) & 0xFF == 27:
                break
        now = time.monotonic()
        rate = 0.9 * rate + 0.1 / max(now - last, 1e-6)
        last = now
        done += 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pi", action="store_true")
    parser.add_argument("--one-camera", action="store_true")
    parser.add_argument("--webcam", action="store_true")
    parser.add_argument("--spot-level", type=int, default=None)
    parser.add_argument("--scene", type=int, default=0)
    parser.add_argument("--infrared", type=int, default=None)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--align", type=str, default=None)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--relay", type=str, default=None)
    args = parser.parse_args()

    from eye.detector import PeopleDetector
    from eye.listen import Listener
    from eye.sources import PiPair, TagEyeWithWebcam, WebcamPair
    from eye.spots import Spots
    from eye.watch import Background

    settings = Settings()
    if args.align:
        settings.to_scene = np.load(args.align)
    if args.webcam:
        source = TagEyeWithWebcam(width=args.width, height=args.height)
    elif args.pi:
        source = PiPair(infrared_port=None if args.one_camera else 1, width=args.width, height=args.height)
    else:
        source = WebcamPair(args.scene, args.infrared, args.width, args.height)
    listener = Listener(Roster())
    listener.start()
    outbox = Outbox(args.width, args.height)
    start(outbox, args.port)
    if args.relay:
        import os

        from eye.uplink import Uplink

        Uplink(outbox, args.relay, os.environ["BLACKOUT_KEY"]).start()
    try:
        spots = Spots() if args.spot_level is None else Spots(level=args.spot_level)
        run(source, listener, Pipeline(settings=settings, spots=spots, eyes=Background(PeopleDetector())), outbox, args.show)
    finally:
        source.close()
        listener.stop()


if __name__ == "__main__":
    main()
