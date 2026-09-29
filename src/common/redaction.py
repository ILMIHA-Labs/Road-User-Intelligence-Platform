"""Privacy redaction utilities.

Heuristic, dependency-free identity redaction: rather than run a dedicated
face/plate detector, blur regions derived from the person/vehicle bounding
boxes the pipeline already produces — the upper portion of a person box (face)
and the lower-central portion of a vehicle box (licence plate). Approximate but
deterministic and adds no new dependencies. Also provides k-anonymity
suppression for aggregate counts.
"""
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from common import constants

# Classes whose upper region may contain a face, and whose lower region may
# contain a licence plate. Motorcycles appear in both (rider face + plate).
FACE_CLASSES = frozenset({"pedestrian", "person", "rider", "cyclist", "bicycle", "motorcycle"})
PLATE_CLASSES = frozenset({"car", "bus", "truck", "motorcycle"})

Box = Tuple[int, int, int, int]


@dataclass
class RedactionConfig:
    enabled: bool = True
    redact_faces: bool = True
    redact_plates: bool = True
    method: str = "blur"  # "blur" or "pixelate"
    strength: int = constants.REDACTION_STRENGTH


def _flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def redaction_config_from_env() -> RedactionConfig:
    """Build a config from environment so the backend and the standalone
    video-analysis process share one source of truth."""
    method = (os.getenv("REDACTION_METHOD", "blur") or "blur").strip().lower()
    if method not in {"blur", "pixelate"}:
        method = "blur"
    try:
        strength = int(os.getenv("REDACTION_STRENGTH", str(constants.REDACTION_STRENGTH)))
    except ValueError:
        strength = constants.REDACTION_STRENGTH
    return RedactionConfig(
        enabled=_flag("REDACTION_ENABLED", True),
        redact_faces=_flag("REDACT_FACES", True),
        redact_plates=_flag("REDACT_PLATES", True),
        method=method,
        strength=max(1, strength),
    )


# ---------------------------------------------------------------------------
# Region geometry
# ---------------------------------------------------------------------------

def _as_box(bbox: Sequence[float]) -> Optional[Box]:
    if not bbox or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = (int(round(v)) for v in bbox)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def face_region(bbox: Sequence[float]) -> Optional[Box]:
    """Upper portion of a person/rider box, where a face is most likely."""
    box = _as_box(bbox)
    if box is None:
        return None
    x1, y1, x2, y2 = box
    height = y2 - y1
    return x1, y1, x2, y1 + max(1, int(round(height * constants.FACE_REGION_HEIGHT_RATIO)))


def plate_region(bbox: Sequence[float]) -> Optional[Box]:
    """Lower-central portion of a vehicle box, where a plate is most likely."""
    box = _as_box(bbox)
    if box is None:
        return None
    x1, y1, x2, y2 = box
    height = y2 - y1
    width = x2 - x1
    margin = int(round(width * constants.PLATE_REGION_SIDE_MARGIN_RATIO))
    top = y2 - max(1, int(round(height * constants.PLATE_REGION_HEIGHT_RATIO)))
    left = min(x2 - 1, x1 + margin)
    right = max(left + 1, x2 - margin)
    return left, top, right, y2


# ---------------------------------------------------------------------------
# Blurring
# ---------------------------------------------------------------------------

def blur_region(frame: np.ndarray, box: Optional[Box], method: str, strength: int) -> None:
    """Blur ``box`` in-place on ``frame``. No-op if the region is empty."""
    if box is None:
        return
    h, w = frame.shape[:2]
    x1 = max(0, min(box[0], w - 1))
    y1 = max(0, min(box[1], h - 1))
    x2 = max(x1 + 1, min(box[2], w))
    y2 = max(y1 + 1, min(box[3], h))
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return
    if method == "pixelate":
        blocks = max(1, int(strength))
        small = cv2.resize(
            roi,
            (max(1, (x2 - x1) // blocks), max(1, (y2 - y1) // blocks)),
            interpolation=cv2.INTER_LINEAR,
        )
        frame[y1:y2, x1:x2] = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
    else:
        kernel = int(strength) | 1  # kernel size must be odd
        kernel = max(3, kernel)
        frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (kernel, kernel), 0)


def redact_frame(
    frame: np.ndarray,
    detections: Iterable[Tuple[Optional[str], Sequence[float]]],
    cfg: RedactionConfig,
) -> np.ndarray:
    """Blur face/plate regions for each ``(class_name, bbox)`` detection in-place."""
    if not cfg.enabled:
        return frame
    for class_name, bbox in detections:
        name = (class_name or "").lower()
        if cfg.redact_faces and name in FACE_CLASSES:
            blur_region(frame, face_region(bbox), cfg.method, cfg.strength)
        if cfg.redact_plates and name in PLATE_CLASSES:
            blur_region(frame, plate_region(bbox), cfg.method, cfg.strength)
    return frame


# ---------------------------------------------------------------------------
# k-anonymity
# ---------------------------------------------------------------------------

def suppress_value(value: Optional[int], k: int) -> Optional[int]:
    if value is None or k < 2:
        return value
    return None if 0 < value < k else value


def suppress_small_counts(mapping: Dict[str, Optional[int]], k: int) -> Dict[str, Optional[int]]:
    """Replace any positive count below ``k`` with None (k-anonymity)."""
    if k < 2:
        return dict(mapping)
    return {key: suppress_value(value, k) for key, value in mapping.items()}


def suppress_small_counts_list(values: Sequence[Optional[int]], k: int) -> List[Optional[int]]:
    if k < 2:
        return list(values)
    return [suppress_value(value, k) for value in values]
