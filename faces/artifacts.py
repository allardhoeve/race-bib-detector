"""Face artifact generation helpers (snippets, previews, evidence JSON)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2
import numpy as np

from config import FACE_SNIPPET_PADDING_RATIO
from geometry import Bbox, bbox_to_rect
from .types import FaceDetection

logger = logging.getLogger(__name__)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_face_snippet(
    image_rgb: np.ndarray,
    bbox: Bbox,
    output_path: Path,
    padding_ratio: float | None = None,
) -> bool:
    """Save a cropped face snippet."""
    if padding_ratio is None:
        padding_ratio = FACE_SNIPPET_PADDING_RATIO

    try:
        _ensure_parent(output_path)
        x_min, y_min, x_max, y_max = bbox_to_rect(bbox)

        width = x_max - x_min
        height = y_max - y_min
        pad_x = int(width * padding_ratio)
        pad_y = int(height * padding_ratio)

        img_height, img_width = image_rgb.shape[:2]
        x_min = max(0, x_min - pad_x)
        y_min = max(0, y_min - pad_y)
        x_max = min(img_width, x_max + pad_x)
        y_max = min(img_height, y_max + pad_y)

        if x_max <= x_min or y_max <= y_min:
            return False

        snippet = image_rgb[y_min:y_max, x_min:x_max]
        bgr = cv2.cvtColor(snippet, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(output_path), bgr)
        return True
    except Exception as e:
        logger.exception("Error saving face snippet: %s", e)
        return False


def save_face_boxed_preview(
    image_rgb: np.ndarray,
    bbox: Bbox,
    output_path: Path,
    color: tuple[int, int, int] = (0, 255, 0),
    thickness: int = 2,
) -> bool:
    """Save a boxed preview image for a face."""
    try:
        _ensure_parent(output_path)
        image = image_rgb.copy()
        pts = np.array(bbox, np.int32).reshape((-1, 1, 2))
        cv2.polylines(image, [pts], isClosed=True, color=color, thickness=thickness)
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(output_path), bgr)
        return True
    except Exception as e:
        logger.exception("Error saving boxed face preview: %s", e)
        return False


def save_face_evidence_json(
    output_path: Path,
    photo_hash: str,
    face_detections: list[FaceDetection],
    bib_detections: list[dict],
) -> bool:
    """Persist face/bib evidence metadata for later linking or inspection."""
    try:
        _ensure_parent(output_path)
        payload = {
            "photo_hash": photo_hash,
            "faces": [face.to_dict(include_embedding=False) for face in face_detections],
            "bibs": bib_detections,
        }
        with open(output_path, "w") as f:
            json.dump(payload, f, indent=2)
        return True
    except Exception as e:
        logger.exception("Error saving face evidence JSON: %s", e)
        return False
