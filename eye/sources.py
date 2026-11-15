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
        infrared_port: int | None = 1,
        width: int = 1280,
        height: int = 720,
        infrared_exposure_us: int = 4000,
        infrared_gain: float = 4.0,
    ):
        from picamera2 import Picamera2

        self._scene = Picamera2(scene_port)
        self._infrared = None if infrared_port is None else Picamera2(infrared_port)
        frame_time = (33333, 33333)
        self._scene.configure(
            self._scene.create_video_configuration(
                main={"size": (width, height), "format": "RGB888"},
                controls={"FrameDurationLimits": frame_time},
            )
        )
        self._height = height
        self._scene.start()
        if self._infrared is not None:
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
            self._infrared.start()

    def read(self):
        scene = np.ascontiguousarray(self._scene.capture_array("main"))
        if self._infrared is None:
            return time.monotonic(), scene, cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY)
        infrared = self._infrared.capture_array("main")
        return time.monotonic(), scene, np.ascontiguousarray(infrared[: self._height])

    def close(self) -> None:
        self._scene.stop()
        if self._infrared is not None:
            self._infrared.stop()


def find_webcam() -> str:
    import glob

    found = sorted(glob.glob("/dev/v4l/by-id/*-video-index0"))
    if not found:
        raise RuntimeError("no USB webcam found")
    return found[0]


class Webcam:
    def __init__(self, device: str | int | None = None, width: int = 1280, height: int = 720):
        import threading

        target = find_webcam() if device is None else device
        self._capture = cv2.VideoCapture(target, cv2.CAP_V4L2) if isinstance(target, str) else cv2.VideoCapture(target)
        self._capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._capture.set(cv2.CAP_PROP_FPS, 30)
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._capture.isOpened():
            raise RuntimeError("webcam did not open")
        self._lock = threading.Lock()
        self._frame = None
        self._stamp = 0.0
        self._alive = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._alive:
            ok, frame = self._capture.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self._lock:
                self._frame = frame
                self._stamp = time.monotonic()

    def latest(self, patience: float = 3.0):
        waited = time.monotonic()
        while True:
            with self._lock:
                frame, stamp = self._frame, self._stamp
            if frame is not None and time.monotonic() - stamp <= 1.0:
                return frame
            if time.monotonic() - waited > patience:
                raise RuntimeError("webcam stopped")
            time.sleep(0.01)

    def close(self) -> None:
        self._alive = False
        self._thread.join(timeout=1.0)
        self._capture.release()


class TagEyeWithWebcam:
    def __init__(
        self,
        tag_port: int = 0,
        webcam: str | int | None = None,
        width: int = 1280,
        height: int = 720,
        exposure_us: int = 4000,
        gain: float = 4.0,
    ):
        from picamera2 import Picamera2

        self._webcam = Webcam(webcam, width, height)
        self._tag = Picamera2(tag_port)
        self._tag.configure(
            self._tag.create_video_configuration(
                main={"size": (width, height), "format": "YUV420"},
                controls={
                    "FrameDurationLimits": (33333, 33333),
                    "AeEnable": False,
                    "ExposureTime": exposure_us,
                    "AnalogueGain": gain,
                },
            )
        )
        self._height = height
        self._tag.start()

    def read(self):
        infrared = self._tag.capture_array("main")
        return time.monotonic(), self._webcam.latest(), np.ascontiguousarray(infrared[: self._height])

    def close(self) -> None:
        self._tag.stop()
        self._webcam.close()
