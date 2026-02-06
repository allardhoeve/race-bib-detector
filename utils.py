"""Shared utility functions for bib number recognizer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PIL import Image
from config import SNIPPET_PADDING_RATIO
from geometry import Bbox, bbox_to_rect

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from detection import Detection, BibCandidate

CACHE_DIR = Path(__file__).parent / "cache"
GRAY_BBOX_DIR = CACHE_DIR / "gray_bounding"
CANDIDATES_DIR = CACHE_DIR / "candidates"
SNIPPETS_DIR = CACHE_DIR / "snippets"


def get_gray_bbox_path(cache_path: Path) -> Path:
    """Get the grayscale bounding box image path for a given cache path."""
    return GRAY_BBOX_DIR / cache_path.name


def get_candidates_path(cache_path: Path) -> Path:
    """Get the candidates visualization image path for a given cache path."""
    return CANDIDATES_DIR / cache_path.name


def compute_bbox_hash(bbox: Bbox) -> str:
    """Compute a short hash from a bounding box for unique identification.

    Args:
        bbox: Bounding box as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]

    Returns:
        8-character hash string
    """
    import hashlib
    bbox_str = str(bbox)
    return hashlib.sha256(bbox_str.encode()).hexdigest()[:8]


def get_snippet_path(cache_path: Path, bib_number: str, bbox: Bbox) -> Path:
    """Get the snippet image path for a detected bib.

    Args:
        cache_path: Path to the cached photo
        bib_number: The detected bib number
        bbox: Bounding box coordinates (used to generate unique hash)

    Returns:
        Path to the snippet image file
    """
    stem = cache_path.stem
    bbox_hash = compute_bbox_hash(bbox)
    return SNIPPETS_DIR / f"{stem}_bib{bib_number}_{bbox_hash}.jpg"


def save_bib_snippet(
    image: np.ndarray,
    bbox: Bbox,
    output_path: Path,
    padding_ratio: float | None = None,
) -> bool:
    """Save a cropped snippet of a detected bib region.

    Args:
        image: Source image (RGB or grayscale numpy array)
        bbox: Bounding box as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        output_path: Where to save the snippet
        padding_ratio: Extra padding around the bounding box (defaults to SNIPPET_PADDING_RATIO)

    Returns:
        True on success
    """
    if padding_ratio is None:
        padding_ratio = SNIPPET_PADDING_RATIO

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get bounding rectangle from quadrilateral
        x_min, y_min, x_max, y_max = bbox_to_rect(bbox)

        # Add padding
        width = x_max - x_min
        height = y_max - y_min
        pad_x = int(width * padding_ratio)
        pad_y = int(height * padding_ratio)

        # Ensure we stay within image bounds
        img_height, img_width = image.shape[:2]
        x_min = max(0, x_min - pad_x)
        y_min = max(0, y_min - pad_y)
        x_max = min(img_width, x_max + pad_x)
        y_max = min(img_height, y_max + pad_y)

        # Crop the region
        snippet = image[y_min:y_max, x_min:x_max]

        # Convert to BGR if needed for cv2
        if len(snippet.shape) == 2:
            # Grayscale
            cv2.imwrite(str(output_path), snippet)
        elif snippet.shape[2] == 3:
            # RGB -> BGR for cv2
            cv2.imwrite(str(output_path), cv2.cvtColor(snippet, cv2.COLOR_RGB2BGR))
        else:
            cv2.imwrite(str(output_path), snippet)

        return True

    except Exception as e:
        logger.exception("Error saving bib snippet: %s", e)
        return False


def draw_bounding_boxes_on_gray(
    gray_image: np.ndarray,
    detections: list[Detection],
    output_path: Path,
) -> bool:
    """Draw bounding boxes on a grayscale image and save it.

    Args:
        gray_image: Grayscale image as numpy array (2D or 3D single channel)
        detections: List of Detection objects
        output_path: Where to save the annotated image

    Returns:
        True on success
    """
    try:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert grayscale to BGR for colored annotations
        if gray_image.ndim == 2:
            image = cv2.cvtColor(gray_image, cv2.COLOR_GRAY2BGR)
        else:
            image = gray_image.copy()

        # Draw each detection
        for det in detections:
            bbox = det.bbox
            bib_number = det.bib_number
            confidence = det.confidence

            # bbox is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] - a quadrilateral
            pts = np.array(bbox, np.int32)
            pts = pts.reshape((-1, 1, 2))

            # Draw the polygon outline (green on grayscale stands out)
            cv2.polylines(image, [pts], isClosed=True, color=(0, 255, 0), thickness=3)

            # Get top-left point for label
            x_min, y_min, _, _ = bbox_to_rect(bbox)

            # Draw label background
            label = f"{bib_number} ({confidence:.0%})"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.8
            thickness = 2
            (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)

            # Position label above the box
            label_y = max(y_min - 10, text_height + 10)
            label_x = x_min

            # Draw background rectangle for text
            cv2.rectangle(
                image,
                (label_x, label_y - text_height - 5),
                (label_x + text_width + 10, label_y + 5),
                (0, 255, 0),
                -1
            )

            # Draw text
            cv2.putText(
                image, label,
                (label_x + 5, label_y),
                font, font_scale, (0, 0, 0), thickness
            )

        # Save the annotated image
        cv2.imwrite(str(output_path), image)
        return True

    except Exception as e:
        logger.exception("Error drawing bounding boxes on grayscale: %s", e)
        return False


def draw_candidates_on_image(
    image: np.ndarray,
    candidates: list[BibCandidate],
    output_path: Path,
) -> bool:
    """Draw bib candidates on an image and save it.

    Passed candidates are drawn in green, rejected in red.
    Each candidate shows its rejection reason if rejected.

    Args:
        image: Source image as numpy array (RGB or grayscale)
        candidates: List of BibCandidate objects
        output_path: Where to save the annotated image

    Returns:
        True on success
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to BGR for colored annotations
        if image.ndim == 2:
            img = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.shape[2] == 3:
            img = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        else:
            img = image.copy()

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1

        for candidate in candidates:
            x, y, w, h = candidate.bbox

            # Green for passed, red for rejected
            if candidate.passed:
                color = (0, 255, 0)  # Green (BGR)
                label = "PASS"
            else:
                color = (0, 0, 255)  # Red (BGR)
                # Shorten rejection reasons for display
                reason = candidate.rejection_reason or "rejected"
                if reason.startswith("aspect_ratio"):
                    label = "aspect"
                elif reason.startswith("relative_area"):
                    label = "size"
                elif reason.startswith("brightness"):
                    label = "dark"
                else:
                    label = reason[:8]

            # Draw rectangle
            cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)

            # Draw label background
            (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            label_y = max(y - 5, text_height + 5)

            cv2.rectangle(
                img,
                (x, label_y - text_height - 4),
                (x + text_width + 6, label_y + 2),
                color,
                -1
            )

            # Draw label text (black on colored background)
            cv2.putText(
                img, label,
                (x + 3, label_y - 2),
                font, font_scale, (0, 0, 0), thickness
            )

        cv2.imwrite(str(output_path), img)
        return True

    except Exception as e:
        logger.exception("Error drawing candidates: %s", e)
        return False
