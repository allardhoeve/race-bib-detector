"""
White region detection for candidate bib areas.

Bibs are typically white rectangles with dark numbers. This module finds
candidate white regions that could contain bib numbers.
"""

import cv2
import numpy as np

from config import (
    MIN_CONTOUR_AREA,
    WHITE_THRESHOLD,
    MIN_ASPECT_RATIO,
    MAX_ASPECT_RATIO,
    MIN_RELATIVE_AREA,
    MAX_RELATIVE_AREA,
    MEDIAN_BRIGHTNESS_THRESHOLD,
    MEAN_BRIGHTNESS_THRESHOLD,
    REGION_PADDING_RATIO,
)

from .types import BibCandidate


def find_bib_candidates(
    image_array: np.ndarray,
    min_area: int | None = None,
    include_rejected: bool = False,
) -> list[BibCandidate]:
    """Find white rectangular regions that could be bib numbers.

    Returns structured BibCandidate objects with metadata for debugging.

    Args:
        image_array: RGB image as numpy array.
        min_area: Minimum contour area to consider (defaults to MIN_CONTOUR_AREA).
        include_rejected: If True, include candidates that failed filters
                         (with rejection_reason set).

    Returns:
        List of BibCandidate objects. If include_rejected=False, only
        candidates that passed all filters are returned.
    """
    if min_area is None:
        min_area = MIN_CONTOUR_AREA

    # Convert to grayscale
    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)

    # Threshold to find white regions (bibs are white/light colored)
    _, thresh = cv2.threshold(gray, WHITE_THRESHOLD, 255, cv2.THRESH_BINARY)

    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    img_height, img_width = image_array.shape[:2]
    total_image_area = img_width * img_height

    for contour in contours:
        contour_area = cv2.contourArea(contour)
        if contour_area < min_area:
            continue

        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(contour)
        bbox_area = w * h

        # Calculate metrics for this candidate
        aspect_ratio = w / h if h > 0 else 0
        relative_area = bbox_area / total_image_area

        # Get brightness metrics
        region = gray[y:y+h, x:x+w]
        median_brightness = float(np.median(region))
        mean_brightness = float(np.mean(region))

        # Check filters and determine if passed
        rejection_reason = None

        if aspect_ratio < MIN_ASPECT_RATIO or aspect_ratio > MAX_ASPECT_RATIO:
            rejection_reason = f"aspect_ratio {aspect_ratio:.2f} outside [{MIN_ASPECT_RATIO}, {MAX_ASPECT_RATIO}]"
        elif relative_area < MIN_RELATIVE_AREA or relative_area > MAX_RELATIVE_AREA:
            rejection_reason = f"relative_area {relative_area:.4f} outside [{MIN_RELATIVE_AREA}, {MAX_RELATIVE_AREA}]"
        elif median_brightness < MEDIAN_BRIGHTNESS_THRESHOLD or mean_brightness < MEAN_BRIGHTNESS_THRESHOLD:
            rejection_reason = f"brightness (median={median_brightness:.0f}, mean={mean_brightness:.0f}) below threshold"

        passed = rejection_reason is None

        # Apply padding for passed candidates
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
