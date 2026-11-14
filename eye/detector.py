import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as tasks
from mediapipe.tasks.python import vision

from eye import models
from eye.people import Detection
from eye.sampling import clip_box

CROP_PADDING = 0.12
OUTLINE_CONFIDENCE = 0.35
HEAD_FRACTION = 0.45
FACE_GROWTH = 0.35
FACE_INPUT_WIDTH = 256
LEG_FRACTION = 0.7
FOOT_FRACTION = 0.85


def _image(rgb: np.ndarray) -> mp.Image:
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))


def _flat(view: np.ndarray) -> np.ndarray:
    return view[:, :, 0] if view.ndim == 3 else view


def reach_the_ground(body: np.ndarray) -> np.ndarray:
    height = body.shape[0]
    if height < 8:
        return body
    legs = body[int(height * LEG_FRACTION) :].any(axis=0)
    out = body.copy()
    out[int(height * FOOT_FRACTION) :, legs] = True
    return out


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
        found = self._finder.detect(_image(rgb))
        out = []
        for item in found.detections:
            raw = item.bounding_box
            box = clip_box((raw.origin_x, raw.origin_y, raw.origin_x + raw.width, raw.origin_y + raw.height), width, height)
            out.append(Detection(box, self._body(rgb, box), self._face(rgb, box)))
        return out

    def _body(self, rgb: np.ndarray, box) -> np.ndarray:
        height, width = rgb.shape[:2]
        pad_x = int((box[2] - box[0]) * CROP_PADDING)
        pad_y = int((box[3] - box[1]) * CROP_PADDING)
        wide = clip_box((box[0] - pad_x, box[1] - pad_y, box[2] + pad_x, box[3] + pad_y), width, height)
        crop = rgb[wide[1] : wide[3], wide[0] : wide[2]]
        confidence = _flat(self._outliner.segment(_image(crop)).confidence_masks[0].numpy_view())
        if confidence.shape[:2] != crop.shape[:2]:
            confidence = cv2.resize(confidence, (crop.shape[1], crop.shape[0]))
        inner = confidence[box[1] - wide[1] : box[3] - wide[1], box[0] - wide[0] : box[2] - wide[0]]
        return reach_the_ground(inner > OUTLINE_CONFIDENCE)

    def _face(self, rgb: np.ndarray, box) -> np.ndarray | None:
        box_width = box[2] - box[0]
        box_height = box[3] - box[1]
        head_height = max(1, int(box_height * HEAD_FRACTION))
        head = rgb[box[1] : box[1] + head_height, box[0] : box[2]]
        scale = max(1.0, FACE_INPUT_WIDTH / max(1, box_width))
        if scale > 1.0:
            head = cv2.resize(head, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        found = self._faces.detect(_image(head)).detections
        if not found:
            return None
        mask = np.zeros((box_height, box_width), dtype=bool)
        for item in found:
            raw = item.bounding_box
            left = raw.origin_x / scale
            top = raw.origin_y / scale
            face_width = raw.width / scale
            face_height = raw.height / scale
            grow_x = face_width * FACE_GROWTH
            grow_y = face_height * FACE_GROWTH
            x0 = max(0, int(left - grow_x))
            y0 = max(0, int(top - grow_y * 1.6))
            x1 = min(box_width, int(np.ceil(left + face_width + grow_x)))
            y1 = min(box_height, int(np.ceil(top + face_height + grow_y)))
            mask[y0:y1, x0:x1] = True
        return mask if mask.any() else None
