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


def find_white_regions(image_array: np.ndarray, min_area: int | None = None) -> list[tuple]:
    """Find white rectangular regions that could be bib numbers.

    Args:
        image_array: RGB image as numpy array.
        min_area: Minimum contour area to consider (defaults to MIN_CONTOUR_AREA).

    Returns:
        List of (x, y, w, h) tuples for candidate regions.
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

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue

        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(contour)

        # Filter by aspect ratio (bibs are roughly square or wider than tall)
        aspect_ratio = w / h if h > 0 else 0
        if aspect_ratio < MIN_ASPECT_RATIO or aspect_ratio > MAX_ASPECT_RATIO:
            continue

        # Filter by size relative to image (not too small, not too large)
        relative_area = (w * h) / (img_width * img_height)
        if relative_area < MIN_RELATIVE_AREA or relative_area > MAX_RELATIVE_AREA:
            continue

        # Validate region is predominantly white (not just scattered bright pixels)
        # This filters out false positives like light text on dark backgrounds
        region = gray[y:y+h, x:x+w]
        median_brightness = np.median(region)
        mean_brightness = np.mean(region)
        if median_brightness < MEDIAN_BRIGHTNESS_THRESHOLD or mean_brightness < MEAN_BRIGHTNESS_THRESHOLD:
            continue

        # Add padding around the region
        padding = int(min(w, h) * REGION_PADDING_RATIO)
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(img_width - x, w + 2 * padding)
        h = min(img_height - y, h + 2 * padding)

        candidates.append((x, y, w, h))

    return candidates
