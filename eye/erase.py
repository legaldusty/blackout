import cv2
import numpy as np

from eye.beacon import Policy
from eye.people import Person
from eye.sampling import grow_box

WEAK_MASK_FRACTION = 0.2
FACE_BAND_FRACTION = 0.28


def _kernel(box_width: int, box_height: int, growth: float) -> np.ndarray:
    size = max(3, int(round(max(box_width, box_height) * growth)) | 1)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def _placed(mask: np.ndarray, inner, outer) -> np.ndarray:
    canvas = np.zeros((outer[3] - outer[1], outer[2] - outer[0]), dtype=np.uint8)
    height = min(mask.shape[0], inner[3] - inner[1], canvas.shape[0] - (inner[1] - outer[1]))
    width = min(mask.shape[1], inner[2] - inner[0], canvas.shape[1] - (inner[0] - outer[0]))
    top = inner[1] - outer[1]
    left = inner[0] - outer[0]
    canvas[top : top + height, left : left + width] = mask[:height, :width]
    return canvas


def erase_person(image: np.ndarray, person: Person, policy: Policy, growth: float) -> None:
    height, width = image.shape[:2]
    if person.coasting:
        growth *= 2.0
    inner = grow_box(person.box, 0.0, width, height)
    outer = grow_box(person.box, growth, width, height)
    region = image[outer[1] : outer[3], outer[0] : outer[2]]
    box_width = inner[2] - inner[0]
    box_height = inner[3] - inner[1]
    body = person.body
    weak = body is None or body.size == 0 or float(np.count_nonzero(body)) / body.size < WEAK_MASK_FRACTION
    if policy is Policy.HIDE_FACE:
        face = person.face
        if face is not None and np.count_nonzero(face) > 0:
            canvas = _placed(face.astype(np.uint8), inner, outer)
            canvas = cv2.dilate(canvas, _kernel(box_width, box_height, growth * 2.0))
            region[canvas > 0] = 0
            return
        band = int(round(box_height * FACE_BAND_FRACTION))
        region[: (inner[1] - outer[1]) + band] = 0
        return
    if weak:
        region[:] = 0
        return
    canvas = _placed(body.astype(np.uint8), inner, outer)
    canvas = cv2.dilate(canvas, _kernel(box_width, box_height, growth))
    region[canvas > 0] = 0
