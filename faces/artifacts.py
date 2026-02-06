"""Face artifact generation helpers (snippets, previews, evidence JSON)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2
import numpy as np

from config import FACE_SNIPPET_PADDING_RATIO
from geometry import Bbox, bbox_to_rect
from .types import FaceCandidate, FaceDetection

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


def save_face_candidates_preview(
    image_rgb: np.ndarray,
    candidates: list[FaceCandidate],
    output_path: Path,
    thickness: int = 2,
) -> bool:
    """Save a visualization of face candidates (passed/rejected)."""
    try:
        _ensure_parent(output_path)
        image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        text_thickness = 1

        for candidate in candidates:
            color = (0, 255, 0) if candidate.passed else (0, 0, 255)
            pts = np.array(candidate.bbox, np.int32).reshape((-1, 1, 2))
            cv2.polylines(image, [pts], isClosed=True, color=color, thickness=thickness)

            x_min, y_min, _, _ = bbox_to_rect(candidate.bbox)
            if candidate.confidence is None:
                label = "pass" if candidate.passed else "rej"
            else:
                label = f"{candidate.confidence:.2f}"

            (text_width, text_height), _ = cv2.getTextSize(label, font, font_scale, text_thickness)
            label_y = max(y_min - 5, text_height + 5)

            cv2.rectangle(
                image,
                (x_min, label_y - text_height - 4),
                (x_min + text_width + 6, label_y + 2),
                color,
                -1,
            )
            cv2.putText(
                image,
                label,
                (x_min + 3, label_y - 2),
                font,
                font_scale,
                (0, 0, 0),
                text_thickness,
            )

        cv2.imwrite(str(output_path), image)
        return True
    except Exception as e:
        logger.exception("Error saving face candidates preview: %s", e)
        return False


def save_face_evidence_json(
    output_path: Path,
    photo_hash: str,
    face_detections: list[FaceDetection],
    bib_detections: list[dict],
    face_candidates: list[FaceCandidate] | None = None,
) -> bool:
    """Persist face/bib evidence metadata for later linking or inspection."""
    try:
        _ensure_parent(output_path)
        candidates = face_candidates or []
        payload = {
            "photo_hash": photo_hash,
            "faces": [face.to_dict(include_embedding=False) for face in face_detections],
            "bibs": bib_detections,
            "face_candidates": [candidate.to_dict() for candidate in candidates],
        }
        with open(output_path, "w") as f:
            json.dump(payload, f, indent=2)
        return True
    except Exception as e:
        logger.exception("Error saving face evidence JSON: %s", e)
        return False
