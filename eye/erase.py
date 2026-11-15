import numpy as np

from eye.beacon import Policy
from eye.people import Person
from eye.sampling import clip_box

WEAK_MASK_FRACTION = 0.08
FACE_BAND_FRACTION = 0.28


def _region(image: np.ndarray, box):
    height, width = image.shape[:2]
    inner = clip_box(box, width, height)
    return inner, image[inner[1] : inner[3], inner[0] : inner[2]]


def _fits(mask: np.ndarray, region: np.ndarray) -> np.ndarray:
    return mask[: region.shape[0], : region.shape[1]]


def erase_person(image: np.ndarray, person: Person, policy: Policy) -> None:
    inner, region = _region(image, person.box)
    if region.size == 0:
        return
    if policy is Policy.HIDE_FACE:
        face = person.face
        if face is not None and face.any():
            mask = _fits(face, region)
            region[: mask.shape[0], : mask.shape[1]][mask] = 0
            return
        region[: int(round(region.shape[0] * FACE_BAND_FRACTION))] = 0
        return
    body = person.body
    if body is None or body.size == 0 or np.count_nonzero(body) < WEAK_MASK_FRACTION * body.size:
        region[:] = 0
        return
    mask = _fits(body, region)
    region[: mask.shape[0], : mask.shape[1]][mask] = 0
