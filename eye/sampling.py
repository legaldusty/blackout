import numpy as np

from eye.people import Box


def clip_box(box: Box, width: int, height: int) -> Box:
    left = min(max(int(box[0]), 0), width - 1)
    top = min(max(int(box[1]), 0), height - 1)
    right = min(max(int(box[2]), left + 1), width)
    bottom = min(max(int(box[3]), top + 1), height)
    return left, top, right, bottom


def grow_box(box: Box, fraction: float, width: int, height: int) -> Box:
    pad_x = int(round((box[2] - box[0]) * fraction))
    pad_y = int(round((box[3] - box[1]) * fraction))
    return clip_box((box[0] - pad_x, box[1] - pad_y, box[2] + pad_x, box[3] + pad_y), width, height)


def _edges(length: int, parts: int) -> np.ndarray:
    return np.unique(np.floor(np.arange(parts) * length / parts).astype(int))


def brightest_per_cell(gray: np.ndarray, box: Box, rows: int, cols: int) -> np.ndarray:
    crop = gray[box[1] : box[3], box[0] : box[2]]
    out = np.zeros((rows, cols), dtype=np.float64)
    if crop.size == 0:
        return out.ravel()
    row_edges = _edges(crop.shape[0], rows)
    col_edges = _edges(crop.shape[1], cols)
    pooled = np.maximum.reduceat(np.maximum.reduceat(crop, row_edges, axis=0), col_edges, axis=1)
    out[: pooled.shape[0], : pooled.shape[1]] = pooled
    return out.ravel()
