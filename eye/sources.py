import time

import cv2
import numpy as np


class WebcamPair:
    def __init__(self, scene_index: int, infrared_index: int | None = None, width: int = 1280, height: int = 720):
        self._scene = self._open(scene_index, width, height)
        self._infrared = None if infrared_index is None else self._open(infrared_index, width, height)

    @staticmethod
    def _open(index: int, width: int, height: int) -> cv2.VideoCapture:
        capture = cv2.VideoCapture(index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_FPS, 30)
        if not capture.isOpened():
            raise RuntimeError(f"camera {index} did not open")
        return capture

    def read(self):
        ok, scene = self._scene.read()
        seconds = time.monotonic()
        if not ok:
            raise RuntimeError("scene camera stopped")
        if self._infrared is None:
            return seconds, scene, cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY)
        ok, infrared = self._infrared.read()
        if not ok:
            raise RuntimeError("infrared camera stopped")
        return seconds, scene, cv2.cvtColor(infrared, cv2.COLOR_BGR2GRAY)

    def close(self) -> None:
        self._scene.release()
        if self._infrared is not None:
            self._infrared.release()


class PiPair:
    def __init__(
        self,
        scene_port: int = 0,
        infrared_port: int = 1,
        width: int = 1280,
        height: int = 720,
        infrared_exposure_us: int = 4000,
        infrared_gain: float = 4.0,
    ):
        from picamera2 import Picamera2

        self._scene = Picamera2(scene_port)
        self._infrared = Picamera2(infrared_port)
        frame_time = (33333, 33333)
        self._scene.configure(
            self._scene.create_video_configuration(
                main={"size": (width, height), "format": "RGB888"},
                controls={"FrameDurationLimits": frame_time},
            )
        )
        self._infrared.configure(
            self._infrared.create_video_configuration(
                main={"size": (width, height), "format": "YUV420"},
                controls={
                    "FrameDurationLimits": frame_time,
                    "AeEnable": False,
                    "ExposureTime": infrared_exposure_us,
                    "AnalogueGain": infrared_gain,
                },
            )
        )
        self._height = height
        self._scene.start()
        self._infrared.start()

    def read(self):
        scene = self._scene.capture_array("main")
        infrared = self._infrared.capture_array("main")
        seconds = time.monotonic()
        return seconds, np.ascontiguousarray(scene), np.ascontiguousarray(infrared[: self._height])

    def close(self) -> None:
        self._scene.stop()
        self._infrared.stop()
