import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as tasks
from mediapipe.tasks.python import vision

from eye import models
from eye.people import Detection
from eye.sampling import clip_box

FIND_WIDTH = 640
CROP_PADDING = 0.14
OUTLINE_CONFIDENCE = 0.4
OUTLINE_SIZE = 256
GROW_FRACTION = 0.035
SMOOTH_FRACTION = 0.02
HEAD_FRACTION = 0.5
FACE_GROWTH = 0.4
FACE_INPUT_WIDTH = 256


def _image(rgb: np.ndarray) -> mp.Image:
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))


def _flat(view: np.ndarray) -> np.ndarray:
    return view[:, :, 0] if view.ndim == 3 else view


def _odd(value: float, least: int = 3) -> int:
    return max(least, int(round(value))) | 1


def clean_outline(confidence: np.ndarray, width: int, height: int) -> np.ndarray:
    small = (confidence > OUTLINE_CONFIDENCE).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(small, connectivity=8)
    if count > 2:
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = np.flatnonzero(areas >= 0.15 * areas.max()) + 1
        small = np.isin(labels, keep).astype(np.uint8)
    side = small.shape[0]
    small = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_odd(side * 0.04), _odd(side * 0.04))))
    small = cv2.dilate(small, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_odd(side * GROW_FRACTION * 2), _odd(side * GROW_FRACTION * 2))))
    soft = cv2.resize(small.astype(np.float32), (width, height), interpolation=cv2.INTER_LINEAR)
    blur = _odd(max(width, height) * SMOOTH_FRACTION)
    soft = cv2.GaussianBlur(soft, (blur, blur), 0)
    return soft > 0.35


class PeopleDetector:
    def __init__(self, min_score: float = 0.35, max_people: int = 6):
        self._finder = vision.ObjectDetector.create_from_options(
            vision.ObjectDetectorOptions(
                base_options=tasks.BaseOptions(model_asset_path=str(models.path("people.tflite"))),
                category_allowlist=["person"],
                score_threshold=min_score,
                max_results=max_people,
            )
        )
        self._outliner = vision.ImageSegmenter.create_from_options(
            vision.ImageSegmenterOptions(
                base_options=tasks.BaseOptions(model_asset_path=str(models.path("outline.tflite"))),
                output_category_mask=False,
                output_confidence_masks=True,
            )
        )
        self._faces = vision.FaceDetector.create_from_options(
            vision.FaceDetectorOptions(
                base_options=tasks.BaseOptions(model_asset_path=str(models.path("face.tflite"))),
                min_detection_confidence=0.3,
            )
        )

    def detect(self, scene: np.ndarray) -> list[Detection]:
        height, width = scene.shape[:2]
        rgb = cv2.cvtColor(scene, cv2.COLOR_BGR2RGB)
        scale = min(1.0, FIND_WIDTH / width)
        small = rgb if scale == 1.0 else cv2.resize(rgb, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
        found = self._finder.detect(_image(small))
        out = []
        for item in found.detections:
            raw = item.bounding_box
            tight = clip_box(
                (raw.origin_x / scale, raw.origin_y / scale, (raw.origin_x + raw.width) / scale, (raw.origin_y + raw.height) / scale),
                width,
                height,
            )
            pad_x = int((tight[2] - tight[0]) * CROP_PADDING)
            pad_y = int((tight[3] - tight[1]) * CROP_PADDING)
            box = clip_box((tight[0] - pad_x, tight[1] - pad_y, tight[2] + pad_x, tight[3] + pad_y), width, height)
            out.append(Detection(box, self._body(rgb, box), self._face(rgb, tight, box)))
        return out

    def _body(self, rgb: np.ndarray, box) -> np.ndarray:
        crop = cv2.resize(rgb[box[1] : box[3], box[0] : box[2]], (OUTLINE_SIZE, OUTLINE_SIZE), interpolation=cv2.INTER_AREA)
        confidence = _flat(self._outliner.segment(_image(crop)).confidence_masks[0].numpy_view())
        if confidence.shape[:2] != (OUTLINE_SIZE, OUTLINE_SIZE):
            confidence = cv2.resize(confidence, (OUTLINE_SIZE, OUTLINE_SIZE))
        return clean_outline(confidence, box[2] - box[0], box[3] - box[1])

    def _face(self, rgb: np.ndarray, tight, box) -> np.ndarray | None:
        tight_width = tight[2] - tight[0]
        head_height = max(1, int((tight[3] - tight[1]) * HEAD_FRACTION))
        head = rgb[tight[1] : tight[1] + head_height, tight[0] : tight[2]]
        scale = FACE_INPUT_WIDTH / max(1, tight_width)
        head = cv2.resize(head, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        found = self._faces.detect(_image(head)).detections
        if not found:
            return None
        mask = np.zeros((box[3] - box[1], box[2] - box[0]), dtype=np.uint8)
        for item in found:
            raw = item.bounding_box
            center_x = tight[0] - box[0] + (raw.origin_x + raw.width / 2) / scale
            center_y = tight[1] - box[1] + (raw.origin_y + raw.height / 2) / scale
            half_x = raw.width / scale * (0.5 + FACE_GROWTH)
            half_y = raw.height / scale * (0.5 + FACE_GROWTH * 1.3)
            cv2.ellipse(mask, (int(center_x), int(center_y - half_y * 0.12)), (int(half_x), int(half_y)), 0, 0, 360, 1, -1)
        return mask.astype(bool) if mask.any() else None
