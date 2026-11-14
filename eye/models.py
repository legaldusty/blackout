import urllib.request
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "models"
SOURCES = {
    "people.tflite": "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/latest/efficientdet_lite0.tflite",
    "outline.tflite": "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
    "face.tflite": "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite",
}


def path(name: str) -> Path:
    target = FOLDER / name
    if not target.exists():
        FOLDER.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".part")
        urllib.request.urlretrieve(SOURCES[name], partial)
        partial.rename(target)
    return target
