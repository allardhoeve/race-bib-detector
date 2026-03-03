"""
White region detection for candidate bib areas.

Bibs are typically white rectangles with dark numbers. This module finds
candidate white regions that could contain bib numbers.

Also provides `validate_detection_region()` to apply the same filtering
logic to any detection bbox.
"""

from __future__ import annotations

import logging
import cv2
import numpy as np

from config import (
    CandidateFindMethod,
    MIN_CONTOUR_AREA,
    WHITE_THRESHOLD,
    WHITE_MAX_SATURATION,
    MIN_ASPECT_RATIO,
    MAX_ASPECT_RATIO,
    MIN_RELATIVE_AREA,
    MAX_RELATIVE_AREA,
    MEDIAN_BRIGHTNESS_THRESHOLD,
    MEAN_BRIGHTNESS_THRESHOLD,
    REGION_PADDING_RATIO,
)

from .types import BibCandidate
from geometry import Bbox, bbox_to_rect

logger = logging.getLogger(__name__)


def _check_candidate_filters(
    aspect_ratio: float,
    relative_area: float,
    median_brightness: float,
    mean_brightness: float,
) -> str | None:
    """Check candidate against standard filters. Returns rejection reason or None."""
    if aspect_ratio < MIN_ASPECT_RATIO or aspect_ratio > MAX_ASPECT_RATIO:
        return f"aspect_ratio {aspect_ratio:.2f} outside [{MIN_ASPECT_RATIO}, {MAX_ASPECT_RATIO}]"
    if relative_area < MIN_RELATIVE_AREA or relative_area > MAX_RELATIVE_AREA:
        return f"relative_area {relative_area:.4f} outside [{MIN_RELATIVE_AREA}, {MAX_RELATIVE_AREA}]"
    if median_brightness < MEDIAN_BRIGHTNESS_THRESHOLD or mean_brightness < MEAN_BRIGHTNESS_THRESHOLD:
        return f"brightness (median={median_brightness:.0f}, mean={mean_brightness:.0f}) below threshold"
    return None


def validate_detection_region(
    bbox: Bbox,
    gray_image: np.ndarray,
) -> BibCandidate:
    """Validate a detection bounding box using the same criteria as white region candidates.

    Checks aspect ratio, relative area, and brightness thresholds.

    Args:
        bbox: Bounding box as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] (quadrilateral from OCR)
        gray_image: Grayscale image to check brightness

    Returns:
        BibCandidate with passed=True if valid, or passed=False with rejection_reason
    """
    img_height, img_width = gray_image.shape[:2]
    total_image_area = img_width * img_height

    # Convert quadrilateral bbox to axis-aligned rect
    x_min, y_min, x_max, y_max = bbox_to_rect(bbox)
    x_min = max(0, x_min)
    y_min = max(0, y_min)
    x_max = min(img_width, x_max)
    y_max = min(img_height, y_max)

    w = x_max - x_min
    h = y_max - y_min

    if w <= 0 or h <= 0:
        return BibCandidate.create_rejected(
            bbox=(x_min, y_min, max(1, w), max(1, h)),
            area=0,
            aspect_ratio=0.0,
            median_brightness=0.0,
            mean_brightness=0.0,
            relative_area=0.0,
            reason="invalid_bbox (zero size)",
        )

    bbox_area = w * h
    aspect_ratio = w / h
    relative_area = bbox_area / total_image_area

    # Get brightness metrics
    region = gray_image[y_min:y_max, x_min:x_max]
    median_brightness = float(np.median(region))
    mean_brightness = float(np.mean(region))

    rejection_reason = _check_candidate_filters(
        aspect_ratio, relative_area, median_brightness, mean_brightness,
    )
    passed = rejection_reason is None

    return BibCandidate(
        bbox=(x_min, y_min, w, h),
        area=bbox_area,
        aspect_ratio=aspect_ratio,
        median_brightness=median_brightness,
        mean_brightness=mean_brightness,
        relative_area=relative_area,
        passed=passed,
        rejection_reason=rejection_reason,
    )


def _validate_contours(
    contours,
    gray: np.ndarray,
    img_width: int,
    img_height: int,
    min_area: int,
    include_rejected: bool,
) -> list[BibCandidate]:
    """Validate contours against size, aspect ratio, and brightness filters.

    Shared by both GRAYSCALE_THRESHOLD and HSV_WHITE candidate finders.
    """
    total_image_area = img_width * img_height
    candidates = []

    for contour in contours:
        contour_area = cv2.contourArea(contour)
        if contour_area < min_area:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        bbox_area = w * h

        aspect_ratio = w / h if h > 0 else 0
        relative_area = bbox_area / total_image_area

        # Brightness metrics always on grayscale (backward compat)
        region = gray[y:y+h, x:x+w]
        median_brightness = float(np.median(region))
        mean_brightness = float(np.mean(region))

        rejection_reason = _check_candidate_filters(
            aspect_ratio, relative_area, median_brightness, mean_brightness,
        )
        passed = rejection_reason is None

        if passed:
            padding = int(min(w, h) * REGION_PADDING_RATIO)
            x = max(0, x - padding)
            y = max(0, y - padding)
            w = min(img_width - x, w + 2 * padding)
            h = min(img_height - y, h + 2 * padding)

        candidate = BibCandidate(
            bbox=(x, y, w, h),
            area=bbox_area,
            aspect_ratio=aspect_ratio,
            median_brightness=median_brightness,
            mean_brightness=mean_brightness,
            relative_area=relative_area,
            passed=passed,
            rejection_reason=rejection_reason,
        )

        if passed or include_rejected:
            candidates.append(candidate)

    return candidates


def find_bib_candidates(
    image_array: np.ndarray,
    min_area: int | None = None,
    include_rejected: bool = False,
    method: CandidateFindMethod | None = None,
) -> list[BibCandidate]:
    """Find white rectangular regions that could be bib numbers.

    Returns structured BibCandidate objects with metadata for debugging.

    Args:
        image_array: Grayscale or RGB image as numpy array.
        min_area: Minimum contour area to consider (defaults to MIN_CONTOUR_AREA).
        include_rejected: If True, include candidates that failed filters
                         (with rejection_reason set).
        method: Candidate finding strategy. None defaults to GRAYSCALE_THRESHOLD.

    Returns:
        List of BibCandidate objects. If include_rejected=False, only
        candidates that passed all filters are returned.
    """
    if method is None:
        method = CandidateFindMethod.GRAYSCALE_THRESHOLD

    if method == CandidateFindMethod.NONE:
        return []

    if min_area is None:
        min_area = MIN_CONTOUR_AREA

    img_height, img_width = image_array.shape[:2]

    if method == CandidateFindMethod.HSV_WHITE:
        if image_array.ndim != 3:
            logger.warning(
                "HSV_WHITE requires RGB input but got grayscale; "
                "falling back to GRAYSCALE_THRESHOLD"
            )
            method = CandidateFindMethod.GRAYSCALE_THRESHOLD

    # Grayscale: needed for thresholding (GRAYSCALE_THRESHOLD) and brightness metrics
    if image_array.ndim == 3:
        gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = image_array

    if method == CandidateFindMethod.HSV_WHITE:
        # HSV-based: high value (bright) AND low saturation (white, not colorful)
        hsv = cv2.cvtColor(image_array, cv2.COLOR_RGB2HSV)
        v_channel = hsv[:, :, 2]
        s_channel = hsv[:, :, 1]
        mask = (v_channel > WHITE_THRESHOLD) & (s_channel < WHITE_MAX_SATURATION)
        thresh = mask.astype(np.uint8) * 255
    else:
        # GRAYSCALE_THRESHOLD: original brightness threshold
        _, thresh = cv2.threshold(gray, WHITE_THRESHOLD, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    return _validate_contours(
        contours, gray, img_width, img_height, min_area, include_rejected,
    )
